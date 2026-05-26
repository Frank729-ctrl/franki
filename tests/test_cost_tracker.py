"""Tests for cost_tracker.py."""
import pytest
from franki.cost_tracker import CostTracker


def _record(ct: CostTracker, provider="groq", model="llama", input_t=1000,
            output_t=500, rate_in=0.05, rate_out=0.08, lat=1.5):
    pdata = {"cost_per_1m_input": rate_in, "cost_per_1m_output": rate_out}
    ct.record(provider, model, input_t, output_t, pdata, lat)


class TestCostTracker:
    def test_empty_tracker(self):
        ct = CostTracker()
        assert ct.total_calls() == 0
        assert ct.total_cost() == pytest.approx(0.0)
        assert ct.total_tokens() == 0
        assert ct.avg_latency() is None
        assert ct.by_provider() == {}
        assert ct.summary_lines() == []

    def test_single_record(self):
        ct = CostTracker()
        _record(ct, input_t=1000, output_t=500, rate_in=0.05, rate_out=0.08, lat=2.0)
        assert ct.total_calls() == 1
        assert ct.total_tokens() == 1500
        expected_cost = (1000 * 0.05 + 500 * 0.08) / 1_000_000
        assert ct.total_cost() == pytest.approx(expected_cost)
        assert ct.avg_latency() == pytest.approx(2.0)

    def test_multiple_providers(self):
        ct = CostTracker()
        _record(ct, provider="groq", input_t=1000, output_t=500, lat=1.0)
        _record(ct, provider="gemini", input_t=2000, output_t=800, lat=3.0)
        bp = ct.by_provider()
        assert "groq" in bp
        assert "gemini" in bp
        assert bp["groq"]["calls"] == 1
        assert bp["gemini"]["calls"] == 1

    def test_zero_rate_gives_zero_cost(self):
        ct = CostTracker()
        _record(ct, rate_in=0.0, rate_out=0.0)
        assert ct.total_cost() == pytest.approx(0.0)

    def test_avg_latency_across_calls(self):
        ct = CostTracker()
        _record(ct, lat=1.0)
        _record(ct, lat=3.0)
        assert ct.avg_latency() == pytest.approx(2.0)

    def test_summary_lines_has_totals(self):
        ct = CostTracker()
        _record(ct, provider="groq")
        _record(ct, provider="groq")
        lines = ct.summary_lines()
        assert len(lines) >= 2  # at least 1 provider + totals row
        total_line = lines[-1]
        assert "total" in total_line

    def test_by_provider_avg_latency(self):
        ct = CostTracker()
        _record(ct, provider="groq", lat=2.0)
        _record(ct, provider="groq", lat=4.0)
        bp = ct.by_provider()
        assert bp["groq"]["avg_latency_s"] == pytest.approx(3.0)
