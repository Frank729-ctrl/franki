"""
Per-session cost and latency tracker.

Token counts are approximated (chars / 4). Costs are estimates based on
per-provider rates the user can configure. Even approximate figures let users
make informed decisions about which provider to use.
"""
from __future__ import annotations
from dataclasses import dataclass, field


@dataclass
class _Entry:
    provider: str
    model: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    latency_s: float


class CostTracker:
    def __init__(self) -> None:
        self._entries: list[_Entry] = []

    def record(
        self,
        provider: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        pdata: dict,
        latency_s: float,
    ) -> None:
        rate_in = pdata.get("cost_per_1m_input", 0.0) or 0.0
        rate_out = pdata.get("cost_per_1m_output", 0.0) or 0.0
        cost = (input_tokens * rate_in + output_tokens * rate_out) / 1_000_000
        self._entries.append(_Entry(
            provider=provider,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost,
            latency_s=latency_s,
        ))

    # ── Aggregates ────────────────────────────────────────────────────────────

    def total_cost(self) -> float:
        return sum(e.cost_usd for e in self._entries)

    def total_tokens(self) -> int:
        return sum(e.input_tokens + e.output_tokens for e in self._entries)

    def total_calls(self) -> int:
        return len(self._entries)

    def avg_latency(self) -> float | None:
        if not self._entries:
            return None
        return sum(e.latency_s for e in self._entries) / len(self._entries)

    def by_provider(self) -> dict[str, dict]:
        result: dict[str, dict] = {}
        for e in self._entries:
            if e.provider not in result:
                result[e.provider] = {
                    "calls": 0, "tokens": 0, "cost_usd": 0.0, "latencies": []
                }
            d = result[e.provider]
            d["calls"] += 1
            d["tokens"] += e.input_tokens + e.output_tokens
            d["cost_usd"] += e.cost_usd
            d["latencies"].append(e.latency_s)
        # Replace latencies list with avg
        for d in result.values():
            lats = d.pop("latencies")
            d["avg_latency_s"] = round(sum(lats) / len(lats), 2) if lats else None
        return result

    def summary_lines(self) -> list[str]:
        """One-line summary per provider, plus totals row."""
        lines: list[str] = []
        for pname, d in self.by_provider().items():
            cost_str = f"${d['cost_usd']:.4f}" if d["cost_usd"] > 0 else "n/a"
            lat_str = f"{d['avg_latency_s']}s" if d["avg_latency_s"] else "n/a"
            lines.append(
                f"  {pname:<14} calls={d['calls']}  tokens={d['tokens']:,}  "
                f"cost={cost_str}  avg_latency={lat_str}"
            )
        if self._entries:
            tc = self.total_cost()
            total_cost_str = f"${tc:.4f}" if tc > 0 else "n/a (no cost rates configured)"
            lines.append(f"  {'total':<14} calls={self.total_calls()}  "
                         f"tokens={self.total_tokens():,}  cost={total_cost_str}")
        return lines
