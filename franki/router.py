from __future__ import annotations
import time
from typing import AsyncIterator, Callable

from franki.config import FrankiConfig
import sys

from franki.providers.generic import (
    ProviderRateLimitError,
    ProviderError,
    stream_chat,  # module-level name keeps test patches working
)
from franki.routing import RoutingTracker, build_routing_order


def _get_stream_fn(pdata: dict):
    """Return the right stream_chat for this provider's api_type."""
    api_type = (pdata or {}).get("api_type", "openai")
    if api_type == "anthropic":
        from franki.providers.anthropic import stream_chat as _fn
        return _fn
    if api_type == "cohere":
        from franki.providers.cohere import stream_chat as _fn
        return _fn
    if api_type == "azure":
        from franki.providers.azure import stream_chat as _fn
        return _fn
    return sys.modules[__name__].stream_chat


async def stream_with_fallback(
    cfg: FrankiConfig,
    messages: list[dict],
    skill: str = "coding",
    tracker: RoutingTracker | None = None,
    on_fallback: Callable[..., None] | None = None,
) -> AsyncIterator[str]:
    """
    Stream a response using capability-aware provider routing.

    - Providers are scored by capability match, latency history, and local-first flag.
    - Rate-limited providers are skipped and their state recorded in the tracker.
    - Other errors (bad key, model not found) fail immediately so the user sees them.
    - on_fallback(from_label, to_label, reason) called when switching providers.
    """
    _tracker = tracker or RoutingTracker()

    ordered = build_routing_order(cfg, skill, _tracker)

    if not ordered:
        raise ProviderError(
            "No providers configured.\n"
            "  Run 'franki init' or use /providers to add an API key."
        )

    last_error: Exception | None = None
    tried: list[tuple[str, str]] = []  # [(label, reason)]

    for name, pdata, reason in ordered:
        api_key = cfg.get_provider_key(name)
        base_url = pdata.get("base_url", "")
        model = pdata.get("model", "")

        if not base_url or not model:
            continue
        if not api_key and pdata.get("key_required", True):
            continue

        label = f"{name}/{model}"

        if tried and on_fallback:
            try:
                on_fallback(tried[-1][0], label, reason)
            except TypeError:
                # caller only accepts two positional args (backward-compat)
                on_fallback(tried[-1][0], label)

        tried.append((label, reason))

        stream_fn = _get_stream_fn(pdata)
        start = time.perf_counter()
        try:
            async for chunk in stream_fn(
                api_key, model, messages, base_url, provider_name=name
            ):
                yield chunk

            elapsed = time.perf_counter() - start
            _tracker.record_latency(name, elapsed)
            return

        except ProviderRateLimitError as exc:
            elapsed = time.perf_counter() - start
            _tracker.record_rate_limited(name)
            _tracker.record_latency(name, elapsed)
            last_error = exc
            continue

        except ProviderError as exc:
            # Config mistake (wrong key, wrong model) — surface immediately
            raise exc from None

        except Exception as exc:
            elapsed = time.perf_counter() - start
            _tracker.record_latency(name, elapsed)
            last_error = exc
            break

    if last_error is not None:
        raise ProviderError(str(last_error))
    raise ProviderError(
        "All configured providers are rate-limited or unavailable.\n"
        "  Add another provider with /providers or wait before retrying."
    )
