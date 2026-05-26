"""
Capability-aware, latency-aware routing engine.

Providers are scored rather than round-robined.
Score factors (highest wins):
  - Capability match for the current skill
  - Latency history (faster = higher score)
  - Local-first bonus when cfg.local_first is True
  - Rate-limit penalty (excluded from current session)
  - Priority number from config (lower priority number = slightly higher score)
"""
from __future__ import annotations
import time
from collections import defaultdict
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from franki.config import FrankiConfig

# Maps each skill to capabilities that give a routing score bonus
SKILL_TO_CAPS: dict[str, dict[str, int]] = {
    "coding":   {"coding": 25, "speed": 15, "reasoning": 5},
    "pentest":  {"reasoning": 25, "coding": 15, "security": 10},
    "soc":      {"reasoning": 25, "json": 15, "security": 10, "long-context": 10},
    "security": {"reasoning": 20, "coding": 10},
}

# Default capabilities inferred from well-known provider names
_PROVIDER_DEFAULT_CAPS: dict[str, list[str]] = {
    "groq":       ["speed", "coding"],
    "cerebras":   ["speed", "coding"],
    "ollama":     ["local", "coding", "cheap"],
    "lmstudio":   ["local", "coding", "cheap"],
    "openrouter": ["reasoning", "coding", "vision", "long-context"],
    "gemini":     ["long-context", "vision", "reasoning"],
    "together":   ["coding", "reasoning"],
    "mistral":    ["coding", "reasoning", "json"],
    "deepseek":   ["coding", "reasoning"],
}


_RATE_LIMIT_WINDOW = 90.0  # seconds before a rate-limited provider is retried


class RoutingTracker:
    """
    Per-REPL-session latency and rate-limit state.
    Passed through the router so routing decisions improve as the session runs.
    Rate limits expire automatically after _RATE_LIMIT_WINDOW seconds so long
    sessions can recover without restarting.
    """

    def __init__(self) -> None:
        self._latencies: dict[str, list[float]] = defaultdict(list)
        self._rate_limited_until: dict[str, float] = {}
        self._call_count: dict[str, int] = defaultdict(int)

    # ── Recording ─────────────────────────────────────────────────────────────

    def record_latency(self, provider: str, seconds: float) -> None:
        self._latencies[provider].append(seconds)
        self._call_count[provider] += 1

    def record_rate_limited(self, provider: str) -> None:
        self._rate_limited_until[provider] = time.monotonic() + _RATE_LIMIT_WINDOW

    # ── Queries ───────────────────────────────────────────────────────────────

    def avg_latency(self, provider: str) -> float | None:
        lats = self._latencies.get(provider, [])
        return sum(lats) / len(lats) if lats else None

    def is_rate_limited(self, provider: str) -> bool:
        until = self._rate_limited_until.get(provider)
        if until is None:
            return False
        if time.monotonic() >= until:
            del self._rate_limited_until[provider]
            return False
        return True

    def rate_limit_remaining(self, provider: str) -> float | None:
        """Seconds until the rate limit expires, or None if not limited."""
        until = self._rate_limited_until.get(provider)
        if until is None:
            return None
        remaining = until - time.monotonic()
        return max(0.0, remaining) if remaining > 0 else None

    def call_count(self, provider: str) -> int:
        return self._call_count.get(provider, 0)

    def stats(self) -> dict[str, dict]:
        names = set(self._latencies) | set(self._rate_limited_until) | set(self._call_count)
        result: dict[str, dict] = {}
        for name in names:
            avg = self.avg_latency(name)
            rl = self.is_rate_limited(name)
            remaining = self.rate_limit_remaining(name)
            result[name] = {
                "calls": self._call_count.get(name, 0),
                "avg_latency_s": round(avg, 2) if avg is not None else None,
                "rate_limited": rl,
                "rate_limit_remaining_s": round(remaining) if remaining else None,
            }
        return result


# ── Scoring ───────────────────────────────────────────────────────────────────

def _get_capabilities(provider_name: str, pdata: dict) -> list[str]:
    caps = pdata.get("capabilities") or []
    if not caps:
        caps = list(_PROVIDER_DEFAULT_CAPS.get(provider_name, []))
    if pdata.get("local") and "local" not in caps:
        caps = list(caps) + ["local"]
    return caps


def score_provider(
    name: str,
    pdata: dict,
    skill: str,
    local_first: bool,
    tracker: RoutingTracker,
) -> int:
    """Return a routing score — higher is better."""
    if tracker.is_rate_limited(name):
        return -9999

    # Base: lower priority number → higher score (1 → 99, 10 → 90)
    score = 100 - min(pdata.get("priority", 10), 99)

    # Capability bonus for this skill
    caps = _get_capabilities(name, pdata)
    cap_weights = SKILL_TO_CAPS.get(skill, {})
    for cap, weight in cap_weights.items():
        if cap in caps:
            score += weight

    # Local-first: large bonus so local providers almost always win
    if local_first and "local" in caps:
        score += 80

    # Latency history
    avg = tracker.avg_latency(name)
    if avg is not None:
        if avg < 2.0:
            score += 20
        elif avg < 5.0:
            score += 8
        elif avg > 10.0:
            score -= 15
        elif avg > 20.0:
            score -= 30

    return score


def routing_reason(
    name: str,
    pdata: dict,
    skill: str,
    local_first: bool,
    tracker: RoutingTracker,
) -> str:
    """Human-readable reason why this provider was chosen."""
    if tracker.is_rate_limited(name):
        return "rate-limited"
    caps = _get_capabilities(name, pdata)
    if local_first and "local" in caps:
        return "local-first"
    matched = [c for c in SKILL_TO_CAPS.get(skill, {}) if c in caps]
    if matched:
        return f"best for {skill} [{', '.join(matched)}]"
    avg = tracker.avg_latency(name)
    if avg is not None and avg < 2.0:
        return "fastest in session"
    return "priority order"


def build_routing_order(
    cfg: "FrankiConfig",
    skill: str,
    tracker: RoutingTracker,
) -> list[tuple[str, dict, str]]:
    """
    Return (name, pdata, reason) triples sorted best-first for this skill.
    Excludes providers that are unconfigured or rate-limited.
    """
    candidates: list[tuple[int, str, dict, str]] = []

    for name, pdata in cfg.providers.items():
        if not isinstance(pdata, dict):
            continue
        if not pdata.get("model") or not pdata.get("base_url"):
            continue
        key = cfg.get_provider_key(name)
        if not key and pdata.get("key_required", True):
            continue
        if tracker.is_rate_limited(name):
            continue  # excluded for this session until a new session starts

        s = score_provider(name, pdata, skill, cfg.local_first, tracker)
        reason = routing_reason(name, pdata, skill, cfg.local_first, tracker)
        candidates.append((s, name, pdata, reason))

    candidates.sort(key=lambda x: x[0], reverse=True)
    return [(name, pdata, reason) for _, name, pdata, reason in candidates]
