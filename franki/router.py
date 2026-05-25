from typing import AsyncIterator, Callable, Optional
from franki.config import FrankiConfig
from franki.providers import groq as groq_provider
from franki.providers import gemini as gemini_provider
from franki.providers import openrouter as openrouter_provider
from franki.providers import delkaai as delkaai_provider


RATE_LIMIT_ERRORS = (
    groq_provider.GroqRateLimitError,
    gemini_provider.GeminiRateLimitError,
    openrouter_provider.OpenRouterRateLimitError,
)


def _build_provider_order(cfg: FrankiConfig) -> list[tuple[str, str]]:
    active_provider = cfg.get_active_provider()
    active_model = cfg.get_active_model_name()

    entries = []

    # DelkaAI — only when enabled, gets priority 0
    delkaai_data = cfg.providers.get("delkaai", {})
    if isinstance(delkaai_data, dict) and delkaai_data.get("enabled", False):
        entries.append((0, "delkaai", "auto"))

    for name, pdata in cfg.providers.items():
        if not isinstance(pdata, dict) or name == "delkaai":
            continue
        priority = pdata.get("priority", 99)
        models = pdata.get("models", [])
        if not models:
            continue
        if name == active_provider:
            entries.append((priority, name, active_model))
        else:
            entries.append((priority, name, models[0]))

    entries.sort(key=lambda x: x[0])
    return [(name, model) for _, name, model in entries]


def _get_stream_fn(provider: str, cfg: FrankiConfig) -> Callable:
    if provider == "delkaai":
        delkaai_data = cfg.providers.get("delkaai", {})
        url = delkaai_data.get("url", "https://api.delkaai.com") if isinstance(delkaai_data, dict) else "https://api.delkaai.com"

        async def _delkaai_stream(api_key: str, model: str, messages: list[dict]):
            async for chunk in delkaai_provider.stream_chat(api_key, model, messages, url=url):
                yield chunk

        return _delkaai_stream

    fns = {
        "groq": groq_provider.stream_chat,
        "gemini": gemini_provider.stream_chat,
        "openrouter": openrouter_provider.stream_chat,
    }
    if provider not in fns:
        raise ValueError(f"Unknown provider: {provider}")
    return fns[provider]


async def stream_with_fallback(
    cfg: FrankiConfig,
    messages: list[dict],
    on_fallback: Optional[Callable[[str, str], None]] = None,
) -> AsyncIterator[str]:
    """
    Streams from the active provider. On 429/rate-limit, falls back to the
    next provider in priority order. on_fallback(from, to) fires before
    the fallback provider starts.

    DelkaAI errors are handled separately:
      DelkaAIFallbackError  → silent skip (connection errors / 401)
      DelkaAIRateLimitError → on_fallback notice, then skip to direct providers
    """
    order = _build_provider_order(cfg)
    fallback_enabled = cfg.fallback.enabled
    last = len(order) - 1

    i = 0
    while i <= last:
        provider, model = order[i]
        api_key = cfg.get_provider_key(provider)

        if not api_key:
            i += 1
            continue

        stream_fn = _get_stream_fn(provider, cfg)
        try:
            async for chunk in stream_fn(api_key, model, messages):
                yield chunk
            return  # clean finish

        except delkaai_provider.DelkaAIFallbackError:
            # Silent — connection error or 401; fall through to direct providers
            i += 1
            continue

        except delkaai_provider.DelkaAIRateLimitError:
            # Show notice, then fall through
            if on_fallback:
                next_direct = next(
                    ((n, m) for n, m in order[i + 1:] if cfg.get_provider_key(n)),
                    None,
                )
                to_label = f"{next_direct[0]}/{next_direct[1]}" if next_direct else "direct providers"
                on_fallback("delkaai/auto", to_label)
            i += 1
            continue

        except RATE_LIMIT_ERRORS:
            if not fallback_enabled or i == last:
                raise

            # Find next provider that has a key
            j = i + 1
            while j <= last:
                next_provider, next_model = order[j]
                if cfg.get_provider_key(next_provider):
                    break
                j += 1

            if j > last:
                raise RuntimeError("All providers exhausted — no remaining API keys.")

            if on_fallback:
                on_fallback(f"{provider}/{model}", f"{order[j][0]}/{order[j][1]}")

            i = j
            continue

    raise RuntimeError("All providers exhausted or have no API keys configured.")
