"""Tests for routing.py — capability scoring, latency tracking, routing order."""
import pytest
from franki.routing import (
    RoutingTracker,
    score_provider,
    routing_reason,
    build_routing_order,
    _get_capabilities,
)
from franki.config import FrankiConfig


def _make_cfg(**providers) -> FrankiConfig:
    return FrankiConfig(
        active_provider=next(iter(providers), ""),
        providers={
            name: {
                "api_key": "sk-test",
                "base_url": "https://api.example.com/v1",
                "model": "test-model",
                "priority": i + 1,
                "key_required": True,
                **pdata,
            }
            for i, (name, pdata) in enumerate(providers.items())
        },
    )


class TestRoutingTracker:
    def test_initial_state_clean(self):
        t = RoutingTracker()
        assert not t.is_rate_limited("groq")
        assert t.avg_latency("groq") is None
        assert t.call_count("groq") == 0

    def test_record_latency(self):
        t = RoutingTracker()
        t.record_latency("groq", 1.2)
        t.record_latency("groq", 0.8)
        assert t.avg_latency("groq") == pytest.approx(1.0)
        assert t.call_count("groq") == 2

    def test_record_rate_limited(self):
        t = RoutingTracker()
        t.record_rate_limited("openrouter")
        assert t.is_rate_limited("openrouter")
        assert not t.is_rate_limited("groq")

    def test_stats_contains_all_tracked(self):
        t = RoutingTracker()
        t.record_latency("groq", 1.0)
        t.record_rate_limited("openrouter")
        stats = t.stats()
        assert "groq" in stats
        assert "openrouter" in stats


class TestCapabilityInference:
    def test_explicit_caps_used(self):
        caps = _get_capabilities("groq", {"capabilities": ["speed", "vision"]})
        assert caps == ["speed", "vision"]

    def test_default_caps_from_known_name(self):
        caps = _get_capabilities("groq", {})
        assert "speed" in caps

    def test_local_flag_adds_local_cap(self):
        caps = _get_capabilities("mylocal", {"local": True})
        assert "local" in caps

    def test_unknown_provider_returns_empty(self):
        caps = _get_capabilities("unknown_provider_xyz", {})
        assert caps == []


class TestScoring:
    def test_rate_limited_gets_min_score(self):
        t = RoutingTracker()
        t.record_rate_limited("groq")
        pdata = {"priority": 1, "capabilities": ["speed", "coding"]}
        score = score_provider("groq", pdata, "coding", False, t)
        assert score == -9999

    def test_matching_capabilities_boost_score(self):
        t = RoutingTracker()
        pdata_with_coding = {"priority": 5, "capabilities": ["coding", "speed"]}
        pdata_no_coding = {"priority": 5, "capabilities": []}
        s_with = score_provider("a", pdata_with_coding, "coding", False, t)
        s_without = score_provider("b", pdata_no_coding, "coding", False, t)
        assert s_with > s_without

    def test_local_first_boosts_local_provider(self):
        t = RoutingTracker()
        local_pdata = {"priority": 5, "capabilities": ["local", "coding"]}
        cloud_pdata = {"priority": 1, "capabilities": ["coding", "speed"]}
        s_local = score_provider("ollama", local_pdata, "coding", True, t)
        s_cloud = score_provider("groq", cloud_pdata, "coding", True, t)
        assert s_local > s_cloud

    def test_low_latency_boosts_score(self):
        t = RoutingTracker()
        t.record_latency("fast", 1.0)
        t.record_latency("slow", 15.0)
        pdata = {"priority": 5, "capabilities": []}
        s_fast = score_provider("fast", pdata, "coding", False, t)
        s_slow = score_provider("slow", pdata, "coding", False, t)
        assert s_fast > s_slow


class TestBuildRoutingOrder:
    def test_empty_providers_returns_empty(self):
        cfg = FrankiConfig()
        t = RoutingTracker()
        assert build_routing_order(cfg, "coding", t) == []

    def test_best_capability_match_comes_first(self):
        cfg = _make_cfg(
            groq={"capabilities": ["speed", "coding"], "priority": 2},
            gemini={"capabilities": ["long-context", "vision"], "priority": 1},
        )
        t = RoutingTracker()
        ordered = build_routing_order(cfg, "coding", t)
        names = [name for name, _, _ in ordered]
        assert names[0] == "groq"

    def test_rate_limited_provider_excluded(self):
        cfg = _make_cfg(
            groq={"capabilities": ["speed", "coding"], "priority": 1},
            gemini={"capabilities": ["reasoning"], "priority": 2},
        )
        t = RoutingTracker()
        t.record_rate_limited("groq")
        ordered = build_routing_order(cfg, "coding", t)
        names = [name for name, _, _ in ordered]
        assert "groq" not in names

    def test_reason_string_populated(self):
        cfg = _make_cfg(groq={"capabilities": ["speed", "coding"], "priority": 1})
        t = RoutingTracker()
        ordered = build_routing_order(cfg, "coding", t)
        _, _, reason = ordered[0]
        assert isinstance(reason, str)
        assert len(reason) > 0
