"""
search.py — web search via Tavily, with two modes:

  1. DelkaAI  — POST {delkaai_url}/v1/search  (DelkaAI handles Tavily internally)
  2. Direct   — call api.tavily.com directly using TAVILY_API_KEY

The caller receives a normalised SearchResult dict regardless of mode.
"""
from __future__ import annotations
import os
import httpx
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from franki.config import FrankiConfig

_TAVILY_URL = "https://api.tavily.com/search"
_TIMEOUT    = 20.0


class SearchError(Exception):
    pass


# ── Result type ───────────────────────────────────────────────────────────────

class SearchResult:
    __slots__ = ("query", "answer", "results", "mode")

    def __init__(
        self,
        query: str,
        answer: str,
        results: list[dict],
        mode: str,
    ) -> None:
        self.query   = query
        self.answer  = answer
        self.results = results   # [{"title", "url", "content", "score?"}]
        self.mode    = mode      # "delkaai" | "tavily"

    def as_context(self) -> str:
        """Format results as a plain-text block for injection into the session."""
        lines = [f'[Web search results for "{self.query}"]', ""]
        if self.answer:
            lines += [f"Answer: {self.answer}", ""]
        for i, r in enumerate(self.results, 1):
            lines.append(f"{i}. {r.get('title', '(no title)')}")
            lines.append(f"   {r.get('url', '')}")
            content = r.get("content", "").strip()
            if content:
                # trim long snippets
                snippet = content[:300] + ("…" if len(content) > 300 else "")
                lines.append(f"   {snippet}")
            lines.append("")
        return "\n".join(lines).rstrip()


# ── Mode detection ────────────────────────────────────────────────────────────

def _tavily_key(cfg: "FrankiConfig") -> str:
    env = os.environ.get("TAVILY_API_KEY", "")
    if env:
        return env
    prov = cfg.providers.get("tavily", {})
    if isinstance(prov, dict):
        return prov.get("api_key", "")
    return ""


def _delkaai_enabled(cfg: "FrankiConfig") -> bool:
    prov = cfg.providers.get("delkaai", {})
    return isinstance(prov, dict) and prov.get("enabled", False)


def _delkaai_url(cfg: "FrankiConfig") -> str:
    prov = cfg.providers.get("delkaai", {})
    if isinstance(prov, dict):
        return prov.get("url", "https://api.delkaai.com")
    return "https://api.delkaai.com"


# ── Search implementations ────────────────────────────────────────────────────

async def _search_via_delkaai(
    cfg: "FrankiConfig",
    query: str,
    max_results: int,
) -> SearchResult:
    from franki.config import FrankiConfig  # noqa: F401  (type-only at runtime)
    api_key = cfg.get_provider_key("delkaai")
    if not api_key:
        raise SearchError("DelkaAI API key not configured.")

    url = f"{_delkaai_url(cfg).rstrip('/')}/v1/search"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    body = {"query": query, "max_results": max_results}

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.post(url, headers=headers, json=body)
            if resp.status_code == 401:
                raise SearchError("DelkaAI: unauthorized (401)")
            if resp.status_code >= 400:
                raise SearchError(f"DelkaAI search error: HTTP {resp.status_code}")
            data = resp.json()
    except (httpx.ConnectError, httpx.TimeoutException) as exc:
        raise SearchError(f"DelkaAI: connection error — {exc}") from exc

    return SearchResult(
        query=query,
        answer=data.get("answer", ""),
        results=data.get("results", [])[:max_results],
        mode="delkaai",
    )


async def _search_direct(
    api_key: str,
    query: str,
    max_results: int,
) -> SearchResult:
    body = {
        "api_key": api_key,
        "query": query,
        "search_depth": "basic",
        "max_results": max_results,
        "include_answer": True,
    }

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.post(_TAVILY_URL, json=body)
            if resp.status_code == 401:
                raise SearchError("Tavily: invalid API key.")
            if resp.status_code == 429:
                raise SearchError("Tavily: rate limit exceeded.")
            if resp.status_code >= 400:
                raise SearchError(f"Tavily error: HTTP {resp.status_code}")
            data = resp.json()
    except (httpx.ConnectError, httpx.TimeoutException) as exc:
        raise SearchError(f"Tavily: connection error — {exc}") from exc

    return SearchResult(
        query=query,
        answer=data.get("answer", ""),
        results=data.get("results", [])[:max_results],
        mode="tavily",
    )


# ── Availability check ───────────────────────────────────────────────────────

def is_search_available(cfg: "FrankiConfig") -> bool:
    """Return True if at least one search backend is configured."""
    return _delkaai_enabled(cfg) or bool(_tavily_key(cfg))


# ── Public entry point ────────────────────────────────────────────────────────

async def web_search(
    cfg: "FrankiConfig",
    query: str,
    max_results: int = 5,
) -> SearchResult:
    """
    Run a web search. Tries DelkaAI first when enabled, then falls back
    to direct Tavily if a key is configured.
    Raises SearchError if neither mode is available or both fail.
    """
    errors: list[str] = []

    if _delkaai_enabled(cfg):
        try:
            return await _search_via_delkaai(cfg, query, max_results)
        except SearchError as exc:
            errors.append(f"DelkaAI: {exc}")

    key = _tavily_key(cfg)
    if key:
        try:
            return await _search_direct(key, query, max_results)
        except SearchError as exc:
            errors.append(f"Tavily: {exc}")

    if errors:
        raise SearchError("Search failed — " + " | ".join(errors))

    raise SearchError(
        "No search backend configured. "
        "Set TAVILY_API_KEY or enable DelkaAI (/connect delkaai)."
    )
