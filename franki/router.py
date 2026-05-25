from __future__ import annotations
from typing import AsyncIterator, Callable

from franki.config import FrankiConfig
from franki.providers.generic import (
    stream_chat,
    ProviderRateLimitError,
    ProviderError,
)


async def stream_with_fallback(
    cfg: FrankiConfig,
    messages: list[dict],
    on_fallback: Callable[[str, str], None] | None = None,
) -> AsyncIterator[str]:
    """
    Stream a response from the active provider.
    On rate limit errors, tries the next provider by priority.
    On other errors (model not found, bad key, etc.), fails immediately with
    a clear message — no silent fallback on configuration mistakes.
    """
    providers = cfg.provider_list_by_priority()

    if not providers:
        raise ProviderError(
            "No providers configured.\n"
            "  Run 'franki init' or use /providers to add an API key."
        )

    last_error: Exception | None = None
    tried: list[str] = []

    for name, pdata in providers:
        api_key = cfg.get_provider_key(name)
        base_url = pdata.get("base_url", "")
        model = pdata.get("model", "")

        if not base_url or not model:
            continue
        if not api_key and pdata.get("key_required", True):
            continue

        label = f"{name}/{model}"

        if tried and on_fallback:
            on_fallback(tried[-1], label)

        tried.append(label)

        try:
            async for chunk in stream_chat(
                api_key, model, messages, base_url, provider_name=name
            ):
                yield chunk
            return
        except ProviderRateLimitError as exc:
            last_error = exc
            continue  # Rate limit: try next provider
        except ProviderError as exc:
            # Non-rate-limit error (bad key, model not found, etc.)
            # Fail immediately so the user sees the real issue
            raise exc from None
        except Exception as exc:
            last_error = exc
            break

    if last_error is not None:
        raise ProviderError(str(last_error))
    raise ProviderError(
        "All configured providers are rate-limited or unavailable.\n"
        "  Add another provider with /providers or wait before retrying."
    )
