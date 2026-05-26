"""
search.py — web search via Tavily (direct).

The caller receives a normalised SearchResult regardless of result size.
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
    __slots__ = ("query", "answer", "results")

    def __init__(self, query: str, answer: str, results: list[dict]) -> None:
        self.query   = query
        self.answer  = answer
        self.results = results  # [{"title", "url", "content"}]

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
                snippet = content[:300] + ("..." if len(content) > 300 else "")
                lines.append(f"   {snippet}")
            lines.append("")
        return "\n".join(lines).rstrip()


# ── Key resolution ────────────────────────────────────────────────────────────

def _tavily_key(cfg: "FrankiConfig") -> str:
    env = os.environ.get("TAVILY_API_KEY", "")
    if env:
        return env
    return getattr(cfg, "tavily_api_key", "")


def is_search_available(cfg: "FrankiConfig") -> bool:
    return bool(_tavily_key(cfg))


# ── Search implementation ─────────────────────────────────────────────────────

async def _search_direct(api_key: str, query: str, max_results: int) -> SearchResult:
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
    )


# ── Public entry point ────────────────────────────────────────────────────────

async def web_search(cfg: "FrankiConfig", query: str, max_results: int = 5) -> SearchResult:
    """
    Run a web search via Tavily. Raises SearchError if no key is configured or
    the request fails.
    """
    key = _tavily_key(cfg)
    if not key:
        raise SearchError(
            "No search backend configured. "
            "Set TAVILY_API_KEY or add it via /config."
        )
    return await _search_direct(key, query, max_results)
