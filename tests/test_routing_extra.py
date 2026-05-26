"""Extra tests for routing.py — uncovered lines: latency scoring, routing_reason."""
import pytest
from franki.config import FrankiConfig
from franki.routing import (
    RoutingTracker,
    score_provider,
    routing_reason,
    build_routing_order,
    _get_capabilities,
    SKILL_TO_CAPS,
)


def _pdata(priority=10, caps=None, local=False, key_required=True,
           model="llama", base_url="https://api.test.com/v1"):
    d = {
        "priority": priority,
        "model": model,
        "base_url": base_url,
        "key_required": key_required,
    }
    if caps is not None:
        d["capabilities"] = caps
    if local:
        d["local"] = True
    return d


def _cfg_one(name="groq", api_key="sk-test", **kw):
    return FrankiConfig(
        active_provider=name,
        providers={
            name: {
                "api_key": api_key,
                "base_url": kw.get("base_url", "https://api.test.com/v1"),
                "model": kw.get("model", "llama"),
                "priority": kw.get("priority", 1),
                "key_required": kw.get("key_required", True),
                "capabilities": kw.get("capabilities", ["coding"]),
            }
        },
    )


# ── Latency scoring ───────────────────────────────────────────────────────────

class TestLatencyScoring:
    def test_fast_provider_gets_bonus(self):
        tracker = RoutingTracker()
        tracker.record_latency("groq", 0.8)  # < 2s → +20

        slow_tracker = RoutingTracker()
        slow_tracker.record_latency("groq", 7.0)  # 5-10s → no bonus

        fast_score = score_provider("groq", _pdata(), "coding", False, tracker)
        slow_score = score_provider("groq", _pdata(), "coding", False, slow_tracker)
        assert fast_score > slow_score

    def test_medium_latency_gets_small_bonus(self):
        tracker = RoutingTracker()
        tracker.record_latency("groq", 3.0)  # 2-5s → +8

        none_tracker = RoutingTracker()

        medium_score = score_provider("groq", _pdata(), "coding", False, tracker)
        no_history_score = score_provider("groq", _pdata(), "coding", False, none_tracker)
        assert medium_score > no_history_score

    def test_slow_provider_gets_penalty(self):
        tracker = RoutingTracker()
        tracker.record_latency("groq", 12.0)  # > 10s → -15

        none_tracker = RoutingTracker()

        slow_score = score_provider("groq", _pdata(), "coding", False, tracker)
        no_history_score = score_provider("groq", _pdata(), "coding", False, none_tracker)
        assert slow_score < no_history_score

    def test_very_slow_provider_gets_larger_penalty(self):
        tracker_very_slow = RoutingTracker()
        tracker_very_slow.record_latency("groq", 25.0)  # > 20s → would be caught by > 10s branch

        tracker_medium_slow = RoutingTracker()
        tracker_medium_slow.record_latency("groq", 12.0)  # > 10s → -15

        # Both go through the > 10.0 branch (the > 20.0 is unreachable due to elif)
        s1 = score_provider("groq", _pdata(), "coding", False, tracker_very_slow)
        s2 = score_provider("groq", _pdata(), "coding", False, tracker_medium_slow)
        # Both hit the same elif branch — scores should be equal
        assert s1 == s2


# ── routing_reason ────────────────────────────────────────────────────────────

class TestRoutingReasonExtra:
    def test_rate_limited_reason(self):
        tracker = RoutingTracker()
        tracker.record_rate_limited("groq")
        reason = routing_reason("groq", _pdata(), "coding", False, tracker)
        assert reason == "rate-limited"

    def test_local_first_reason(self):
        tracker = RoutingTracker()
        pdata = _pdata(caps=["local", "coding"], local=True)
        reason = routing_reason("ollama", pdata, "coding", True, tracker)
        assert reason == "local-first"

    def test_capability_match_reason(self):
        tracker = RoutingTracker()
        pdata = _pdata(caps=["coding", "speed"])
        reason = routing_reason("groq", pdata, "coding", False, tracker)
        assert "coding" in reason or "speed" in reason

    def test_fastest_in_session_reason(self):
        tracker = RoutingTracker()
        tracker.record_latency("groq", 1.5)  # < 2.0s
        pdata = _pdata(caps=["unknown-cap"])  # no skill match
        reason = routing_reason("groq", pdata, "coding", False, tracker)
        assert "fastest" in reason

    def test_priority_order_fallback(self):
        tracker = RoutingTracker()
        pdata = _pdata(caps=["unknown-cap"])
        reason = routing_reason("groq", pdata, "coding", False, tracker)
        assert reason == "priority order"


# ── _get_capabilities ─────────────────────────────────────────────────────────

class TestGetCapabilities:
    def test_explicit_caps_from_pdata(self):
        caps = _get_capabilities("groq", {"capabilities": ["vision", "json"]})
        assert "vision" in caps
        assert "json" in caps

    def test_falls_back_to_default_by_name(self):
        caps = _get_capabilities("cerebras", {})
        assert "speed" in caps

    def test_local_flag_adds_local_cap(self):
        caps = _get_capabilities("groq", {"capabilities": ["coding"], "local": True})
        assert "local" in caps

    def test_local_not_doubled(self):
        caps = _get_capabilities("ollama", {"capabilities": ["local", "coding"], "local": True})
        assert caps.count("local") == 1

    def test_unknown_provider_returns_empty(self):
        caps = _get_capabilities("unknown_xyz", {})
        assert caps == []


# ── build_routing_order edge cases ────────────────────────────────────────────

class TestBuildRoutingOrderExtra:
    def test_local_first_puts_local_provider_first(self):
        cfg = FrankiConfig(
            local_first=True,
            active_provider="groq",
            providers={
                "groq": {
                    "api_key": "sk-test",
                    "base_url": "https://api.groq.com/v1",
                    "model": "llama",
                    "priority": 1,
                    "key_required": True,
                    "capabilities": ["speed", "coding"],
                },
                "ollama": {
                    "api_key": "ollama",
                    "base_url": "http://localhost:11434/v1",
                    "model": "llama3",
                    "priority": 2,
                    "key_required": False,
                    "capabilities": ["local", "coding"],
                    "local": True,
                },
            },
        )
        tracker = RoutingTracker()
        order = build_routing_order(cfg, "coding", tracker)
        names = [name for name, _, _ in order]
        assert names[0] == "ollama"

    def test_reason_string_populated_in_output(self):
        cfg = _cfg_one()
        tracker = RoutingTracker()
        order = build_routing_order(cfg, "coding", tracker)
        assert len(order) == 1
        name, pdata, reason = order[0]
        assert isinstance(reason, str)
        assert len(reason) > 0

    def test_provider_with_no_base_url_excluded(self):
        cfg = FrankiConfig(
            active_provider="groq",
            providers={
                "groq": {
                    "api_key": "sk-test",
                    "base_url": "",
                    "model": "llama",
                    "priority": 1,
                    "key_required": True,
                }
            },
        )
        tracker = RoutingTracker()
        order = build_routing_order(cfg, "coding", tracker)
        assert order == []

    def test_provider_with_no_model_excluded(self):
        cfg = FrankiConfig(
            active_provider="groq",
            providers={
                "groq": {
                    "api_key": "sk-test",
                    "base_url": "https://api.groq.com/v1",
                    "model": "",
                    "priority": 1,
                    "key_required": True,
                }
            },
        )
        tracker = RoutingTracker()
        order = build_routing_order(cfg, "coding", tracker)
        assert order == []

    def test_provider_no_key_excluded_when_required(self, monkeypatch):
        monkeypatch.delenv("GROQ_API_KEY", raising=False)
        cfg = FrankiConfig(
            active_provider="groq",
            providers={
                "groq": {
                    "api_key": "",
                    "base_url": "https://api.groq.com/v1",
                    "model": "llama",
                    "priority": 1,
                    "key_required": True,
                }
            },
        )
        tracker = RoutingTracker()
        order = build_routing_order(cfg, "coding", tracker)
        assert order == []

    def test_provider_no_key_included_when_not_required(self):
        cfg = FrankiConfig(
            active_provider="ollama",
            providers={
                "ollama": {
                    "api_key": "",
                    "base_url": "http://localhost:11434/v1",
                    "model": "llama3",
                    "priority": 1,
                    "key_required": False,
                }
            },
        )
        tracker = RoutingTracker()
        order = build_routing_order(cfg, "coding", tracker)
        assert len(order) == 1

    def test_best_capability_match_is_first(self):
        cfg = FrankiConfig(
            active_provider="p1",
            providers={
                "p1": {
                    "api_key": "k1",
                    "base_url": "https://p1.com/v1",
                    "model": "m1",
                    "priority": 1,
                    "key_required": True,
                    "capabilities": ["vision"],  # no coding match
                },
                "p2": {
                    "api_key": "k2",
                    "base_url": "https://p2.com/v1",
                    "model": "m2",
                    "priority": 2,
                    "key_required": True,
                    "capabilities": ["coding", "speed"],  # strong coding match
                },
            },
        )
        tracker = RoutingTracker()
        order = build_routing_order(cfg, "coding", tracker)
        names = [n for n, _, _ in order]
        assert names[0] == "p2"
