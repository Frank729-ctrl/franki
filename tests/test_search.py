"""Tests for utils/search.py — Tavily web search with httpx mocking."""
import asyncio
import json
import pytest
from unittest.mock import patch

from franki.config import FrankiConfig
from franki.utils.search import (
    SearchResult,
    SearchError,
    is_search_available,
    web_search,
    _search_direct,
    _tavily_key,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _cfg(key=""):
    return FrankiConfig(tavily_api_key=key)


class _MockResp:
    def __init__(self, status_code=200, data=None):
        self.status_code = status_code
        self._data = data or {}

    def json(self):
        return self._data


class _MockClient:
    def __init__(self, resp):
        self._resp = resp

    async def post(self, *args, **kwargs):
        return self._resp

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass


def _patch_client(resp):
    return patch("httpx.AsyncClient", return_value=_MockClient(resp))


# ── SearchResult ──────────────────────────────────────────────────────────────

class TestSearchResult:
    def _result(self, query="test", answer="", results=None):
        return SearchResult(query=query, answer=answer, results=results or [])

    def test_as_context_includes_query(self):
        sr = self._result(query="what is nmap")
        ctx = sr.as_context()
        assert "what is nmap" in ctx

    def test_as_context_includes_answer(self):
        sr = self._result(answer="Nmap is a scanner.")
        ctx = sr.as_context()
        assert "Nmap is a scanner." in ctx

    def test_as_context_includes_results(self):
        sr = self._result(results=[{
            "title": "Nmap docs",
            "url": "https://nmap.org",
            "content": "Nmap is used for network discovery.",
        }])
        ctx = sr.as_context()
        assert "Nmap docs" in ctx
        assert "https://nmap.org" in ctx

    def test_as_context_empty_results(self):
        sr = self._result()
        ctx = sr.as_context()
        assert "test" in ctx  # query

    def test_content_truncated_at_300(self):
        long_content = "x" * 400
        sr = self._result(results=[{"title": "t", "url": "u", "content": long_content}])
        ctx = sr.as_context()
        assert "..." in ctx
        # The snippet is capped at 300 chars + "..."
        assert len([l for l in ctx.splitlines() if "xxx" in l]) >= 1

    def test_no_answer_section_skipped(self):
        sr = self._result(answer="")
        ctx = sr.as_context()
        assert "Answer:" not in ctx


# ── Key resolution ────────────────────────────────────────────────────────────

class TestTavilyKey:
    def test_env_var_takes_precedence(self, monkeypatch):
        monkeypatch.setenv("TAVILY_API_KEY", "env-key")
        cfg = _cfg(key="config-key")
        assert _tavily_key(cfg) == "env-key"

    def test_falls_back_to_config(self, monkeypatch):
        monkeypatch.delenv("TAVILY_API_KEY", raising=False)
        cfg = _cfg(key="cfg-key")
        assert _tavily_key(cfg) == "cfg-key"

    def test_empty_when_neither_set(self, monkeypatch):
        monkeypatch.delenv("TAVILY_API_KEY", raising=False)
        cfg = _cfg(key="")
        assert _tavily_key(cfg) == ""


class TestIsSearchAvailable:
    def test_true_when_key_present(self, monkeypatch):
        monkeypatch.delenv("TAVILY_API_KEY", raising=False)
        assert is_search_available(_cfg(key="tv-abc")) is True

    def test_false_when_no_key(self, monkeypatch):
        monkeypatch.delenv("TAVILY_API_KEY", raising=False)
        assert is_search_available(_cfg(key="")) is False

    def test_true_from_env(self, monkeypatch):
        monkeypatch.setenv("TAVILY_API_KEY", "env-key")
        assert is_search_available(_cfg()) is True


# ── _search_direct ────────────────────────────────────────────────────────────

class TestSearchDirect:
    def _good_data(self):
        return {
            "answer": "The answer is 42",
            "results": [
                {"title": "Result 1", "url": "https://example.com", "content": "details"},
                {"title": "Result 2", "url": "https://other.com", "content": "more"},
            ],
        }

    def test_returns_search_result(self):
        resp = _MockResp(200, self._good_data())
        with _patch_client(resp):
            result = asyncio.run(_search_direct("key", "query", 5))
        assert isinstance(result, SearchResult)
        assert result.answer == "The answer is 42"
        assert len(result.results) == 2

    def test_max_results_capped(self):
        data = {"answer": "", "results": [{"title": f"r{i}", "url": "", "content": ""} for i in range(10)]}
        resp = _MockResp(200, data)
        with _patch_client(resp):
            result = asyncio.run(_search_direct("key", "query", 3))
        assert len(result.results) == 3

    def test_401_raises_search_error(self):
        resp = _MockResp(401)
        with _patch_client(resp):
            with pytest.raises(SearchError, match="invalid API key"):
                asyncio.run(_search_direct("key", "query", 5))

    def test_429_raises_search_error(self):
        resp = _MockResp(429)
        with _patch_client(resp):
            with pytest.raises(SearchError, match="rate limit"):
                asyncio.run(_search_direct("key", "query", 5))

    def test_other_4xx_raises_search_error(self):
        resp = _MockResp(400)
        with _patch_client(resp):
            with pytest.raises(SearchError, match="HTTP 400"):
                asyncio.run(_search_direct("key", "query", 5))

    def test_connect_error_raises_search_error(self):
        import httpx

        class BadClient:
            async def post(self, *args, **kwargs):
                raise httpx.ConnectError("refused")

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                pass

        with patch("httpx.AsyncClient", return_value=BadClient()):
            with pytest.raises(SearchError, match="connection error"):
                asyncio.run(_search_direct("key", "query", 5))

    def test_timeout_raises_search_error(self):
        import httpx

        class TimeoutClient:
            async def post(self, *args, **kwargs):
                raise httpx.TimeoutException("timeout")

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                pass

        with patch("httpx.AsyncClient", return_value=TimeoutClient()):
            with pytest.raises(SearchError, match="connection error"):
                asyncio.run(_search_direct("key", "query", 5))

    def test_empty_results_key(self):
        resp = _MockResp(200, {"answer": "x", "results": []})
        with _patch_client(resp):
            result = asyncio.run(_search_direct("key", "query", 5))
        assert result.results == []


# ── web_search ────────────────────────────────────────────────────────────────

class TestWebSearch:
    def test_raises_when_no_key(self, monkeypatch):
        monkeypatch.delenv("TAVILY_API_KEY", raising=False)
        cfg = _cfg(key="")
        with pytest.raises(SearchError, match="No search backend"):
            asyncio.run(web_search(cfg, "query"))

    def test_returns_result_when_key_set(self, monkeypatch):
        monkeypatch.delenv("TAVILY_API_KEY", raising=False)
        cfg = _cfg(key="tv-key")
        data = {"answer": "found it", "results": []}
        resp = _MockResp(200, data)
        with _patch_client(resp):
            result = asyncio.run(web_search(cfg, "test query"))
        assert result.answer == "found it"

    def test_uses_env_key(self, monkeypatch):
        monkeypatch.setenv("TAVILY_API_KEY", "env-tv-key")
        cfg = _cfg(key="")
        data = {"answer": "yes", "results": []}
        resp = _MockResp(200, data)
        with _patch_client(resp):
            result = asyncio.run(web_search(cfg, "q"))
        assert result.answer == "yes"
