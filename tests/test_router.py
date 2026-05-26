"""Tests for router.py — stream_with_fallback with mocked providers."""
import asyncio
import pytest
from unittest.mock import AsyncMock, patch

from franki.config import FrankiConfig
from franki.providers.generic import ProviderError, ProviderRateLimitError
from franki.routing import RoutingTracker
from franki.router import stream_with_fallback


# ── Helpers ───────────────────────────────────────────────────────────────────

def _cfg_with_provider(name="groq", api_key="sk-test", model="llama", key_required=True):
    return FrankiConfig(
        active_provider=name,
        providers={
            name: {
                "api_key": api_key,
                "base_url": "https://api.groq.com/openai/v1",
                "model": model,
                "priority": 1,
                "key_required": key_required,
            }
        },
    )


def _cfg_two_providers(key1="sk-a", key2="sk-b"):
    return FrankiConfig(
        active_provider="p1",
        providers={
            "p1": {
                "api_key": key1,
                "base_url": "https://api.p1.com/v1",
                "model": "model1",
                "priority": 1,
                "key_required": True,
            },
            "p2": {
                "api_key": key2,
                "base_url": "https://api.p2.com/v1",
                "model": "model2",
                "priority": 2,
                "key_required": True,
            },
        },
    )


async def _collect(gen):
    chunks = []
    async for chunk in gen:
        chunks.append(chunk)
    return chunks


async def _good_stream(*args, **kwargs):
    yield "hello"
    yield " world"


async def _rate_limited_stream(*args, **kwargs):
    raise ProviderRateLimitError("rate limit hit")
    yield  # make it a generator


async def _error_stream(*args, **kwargs):
    raise ProviderError("bad key")
    yield


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestStreamWithFallback:
    def test_no_providers_raises(self):
        cfg = FrankiConfig()  # no providers

        async def run():
            async for _ in stream_with_fallback(cfg, []):
                pass

        with pytest.raises(ProviderError, match="No providers"):
            asyncio.run(run())

    def test_yields_chunks_from_provider(self):
        cfg = _cfg_with_provider()

        with patch("franki.router.stream_chat", side_effect=_good_stream):
            chunks = asyncio.run(_collect(stream_with_fallback(cfg, [])))
        assert "".join(chunks) == "hello world"

    def test_rate_limit_falls_back_to_next(self):
        cfg = _cfg_two_providers()
        call_order = []

        async def first_rate_limited(api_key, model, *args, **kwargs):
            call_order.append(model)
            raise ProviderRateLimitError("rate limited")
            yield

        async def second_ok(api_key, model, *args, **kwargs):
            call_order.append(model)
            yield "ok"

        side_effects = [first_rate_limited, second_ok]
        call_index = [0]

        async def dispatch(api_key, model, *args, **kwargs):
            fn = side_effects[call_index[0]]
            call_index[0] += 1
            async for chunk in fn(api_key, model, *args, **kwargs):
                yield chunk

        with patch("franki.router.stream_chat", side_effect=dispatch):
            chunks = asyncio.run(_collect(stream_with_fallback(cfg, [])))
        assert "ok" in chunks

    def test_provider_error_raises_immediately(self):
        cfg = _cfg_with_provider()

        with patch("franki.router.stream_chat", side_effect=_error_stream):
            with pytest.raises(ProviderError, match="bad key"):
                asyncio.run(_collect(stream_with_fallback(cfg, [])))

    def test_on_fallback_called_on_provider_switch(self):
        cfg = _cfg_two_providers()
        fallback_calls = []

        def on_fallback(from_label, to_label, reason=""):
            fallback_calls.append((from_label, to_label))

        call_index = [0]

        async def dispatch(api_key, model, *args, **kwargs):
            if call_index[0] == 0:
                call_index[0] += 1
                raise ProviderRateLimitError("rate limited")
                yield
            else:
                yield "fallback response"

        with patch("franki.router.stream_chat", side_effect=dispatch):
            asyncio.run(_collect(stream_with_fallback(cfg, [], on_fallback=on_fallback)))
        assert len(fallback_calls) == 1

    def test_on_fallback_two_arg_compat(self):
        """on_fallback with only two positional params should not raise."""
        cfg = _cfg_two_providers()
        fallback_calls = []

        def on_fallback(from_label, to_label):  # no reason arg
            fallback_calls.append((from_label, to_label))

        call_index = [0]

        async def dispatch(api_key, model, *args, **kwargs):
            if call_index[0] == 0:
                call_index[0] += 1
                raise ProviderRateLimitError("rate limited")
                yield
            else:
                yield "ok"

        with patch("franki.router.stream_chat", side_effect=dispatch):
            asyncio.run(_collect(stream_with_fallback(cfg, [], on_fallback=on_fallback)))
        assert len(fallback_calls) == 1

    def test_tracker_records_latency_on_success(self):
        cfg = _cfg_with_provider()
        tracker = RoutingTracker()

        with patch("franki.router.stream_chat", side_effect=_good_stream):
            asyncio.run(_collect(stream_with_fallback(cfg, [], tracker=tracker)))

        assert tracker.avg_latency("groq") is not None

    def test_tracker_records_rate_limit(self):
        cfg = _cfg_two_providers()
        tracker = RoutingTracker()

        call_index = [0]

        async def dispatch(api_key, model, *args, **kwargs):
            if call_index[0] == 0:
                call_index[0] += 1
                raise ProviderRateLimitError("rl")
                yield
            else:
                yield "ok"

        with patch("franki.router.stream_chat", side_effect=dispatch):
            asyncio.run(_collect(stream_with_fallback(cfg, [], tracker=tracker)))

        assert tracker.is_rate_limited("p1")

    def test_all_rate_limited_raises(self):
        cfg = _cfg_with_provider()
        tracker = RoutingTracker()
        tracker.record_rate_limited("groq")

        async def run():
            async for _ in stream_with_fallback(cfg, [], tracker=tracker):
                pass

        with pytest.raises(ProviderError):
            asyncio.run(run())

    def test_provider_missing_base_url_skipped(self):
        cfg = FrankiConfig(
            active_provider="groq",
            providers={
                "groq": {
                    "api_key": "sk-test",
                    "base_url": "",  # empty
                    "model": "llama",
                    "priority": 1,
                    "key_required": True,
                }
            },
        )

        async def run():
            async for _ in stream_with_fallback(cfg, []):
                pass

        with pytest.raises(ProviderError):
            asyncio.run(run())

    def test_provider_missing_key_when_required_skipped(self):
        cfg = FrankiConfig(
            active_provider="groq",
            providers={
                "groq": {
                    "api_key": "",  # empty key, required
                    "base_url": "https://api.groq.com/v1",
                    "model": "llama",
                    "priority": 1,
                    "key_required": True,
                }
            },
        )

        async def run():
            async for _ in stream_with_fallback(cfg, []):
                pass

        with pytest.raises(ProviderError):
            asyncio.run(run())

    def test_general_exception_breaks_and_raises(self):
        cfg = _cfg_with_provider()

        async def explodes(*args, **kwargs):
            raise RuntimeError("unexpected crash")
            yield

        with patch("franki.router.stream_chat", side_effect=explodes):
            with pytest.raises(ProviderError):
                asyncio.run(_collect(stream_with_fallback(cfg, [])))

    def test_skill_passed_to_routing(self):
        cfg = _cfg_with_provider()

        with patch("franki.router.stream_chat", side_effect=_good_stream):
            with patch("franki.router.build_routing_order", wraps=__import__("franki.routing", fromlist=["build_routing_order"]).build_routing_order) as mock_bro:
                asyncio.run(_collect(stream_with_fallback(cfg, [], skill="pentest")))
                assert mock_bro.call_args[0][1] == "pentest"
