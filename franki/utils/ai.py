import asyncio
import sys
from rich.status import Status
from franki.config import FrankiConfig
from franki.router import stream_with_fallback


# ── Async primitives ──────────────────────────────────────────────────────────

async def _collect(cfg: FrankiConfig, messages: list[dict]) -> str:
    chunks: list[str] = []
    async for chunk in stream_with_fallback(cfg, messages):
        chunks.append(chunk)
    return "".join(chunks)


async def _stream_stdout(cfg: FrankiConfig, messages: list[dict]) -> str:
    """Write each chunk to stdout as it arrives. Returns the full collected text."""
    chunks: list[str] = []
    async for chunk in stream_with_fallback(cfg, messages):
        sys.stdout.write(chunk)
        sys.stdout.flush()
        chunks.append(chunk)
    sys.stdout.write("\n\n")
    sys.stdout.flush()
    return "".join(chunks)


# ── Public API ────────────────────────────────────────────────────────────────

def ask_ai(
    cfg: FrankiConfig,
    messages: list[dict],
    console=None,
    status_text: str = "thinking...",
    use_cache: bool = True,
) -> str:
    """
    Collect the full AI response (no live output).
    When console is provided, shows an animated Rich Status spinner.
    Rich Status refreshes in a background thread, so the spinner animates
    even while asyncio.run() blocks the main thread.
    Use for short responses where parsing the full text is needed (/mitre, /quiz, /compact).
    """
    from franki.cache import response_cache

    if use_cache:
        provider = cfg.active_provider
        model = cfg.get_active_model()
        cached = response_cache.get(provider, model, messages)
        if cached is not None:
            return cached

    if console:
        with Status(
            f"[#555555] {status_text}[/]",
            spinner="dots",
            spinner_style="#d4a853",
            console=console,
        ):
            result = asyncio.run(_collect(cfg, messages))
    else:
        result = asyncio.run(_collect(cfg, messages))

    if use_cache:
        response_cache.put(provider, model, messages, result)

    return result


def cache_stats() -> dict:
    """Return cache hit/miss stats."""
    from franki.cache import response_cache
    return {
        "size": response_cache.size,
        "hits": response_cache.hits,
        "misses": response_cache.misses,
        "hit_rate": f"{response_cache.hit_rate:.0%}",
    }


def stream_to_terminal(
    cfg: FrankiConfig,
    messages: list[dict],
) -> str:
    """
    Stream the AI response directly to stdout as chunks arrive.
    Returns the full collected text when done.
    Use for long-form prose responses (/report, /explain, /tools, /payload).
    """
    return asyncio.run(_stream_stdout(cfg, messages))
