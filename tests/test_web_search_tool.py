"""Tests for the web_search agent tool."""
from unittest.mock import patch, MagicMock
import pytest


def setup_function():
    from franki.agent.tools import set_tavily_key
    set_tavily_key("tvly-test-key")


def teardown_function():
    from franki.agent.tools import set_tavily_key
    set_tavily_key("")


# ── Schema inclusion ──────────────────────────────────────────────────────────

class TestWebSearchSchema:
    def test_always_included(self):
        from franki.agent.tools import get_all_tool_schemas, set_tavily_key
        set_tavily_key("")
        names = [s["function"]["name"] for s in get_all_tool_schemas()]
        assert "web_search" in names

    def test_included_with_key(self):
        from franki.agent.tools import get_all_tool_schemas, set_tavily_key
        set_tavily_key("tvly-test")
        names = [s["function"]["name"] for s in get_all_tool_schemas()]
        assert "web_search" in names

    def test_schema_has_query_param(self):
        from franki.agent.tools import get_all_tool_schemas
        schema = next(s for s in get_all_tool_schemas() if s["function"]["name"] == "web_search")
        props = schema["function"]["parameters"]["properties"]
        assert "query" in props

    def test_schema_has_max_results_param(self):
        from franki.agent.tools import get_all_tool_schemas
        schema = next(s for s in get_all_tool_schemas() if s["function"]["name"] == "web_search")
        props = schema["function"]["parameters"]["properties"]
        assert "max_results" in props


# ── Execution ─────────────────────────────────────────────────────────────────

class TestWebSearchExecution:
    def _mock_response(self, answer="", results=None):
        mock = MagicMock()
        mock.status_code = 200
        mock.json.return_value = {
            "answer": answer,
            "results": results or [
                {"title": "Python docs", "url": "https://docs.python.org", "content": "Python is great"},
                {"title": "PyPI", "url": "https://pypi.org", "content": "Find packages here"},
            ],
        }
        mock.raise_for_status = MagicMock()
        return mock

    def test_returns_results(self):
        from franki.agent.tools import execute_tool
        with patch("httpx.post", return_value=self._mock_response()):
            result = execute_tool("web_search", {"query": "python async"})
        assert "Python docs" in result
        assert "docs.python.org" in result

    def test_includes_answer_when_present(self):
        from franki.agent.tools import execute_tool
        with patch("httpx.post", return_value=self._mock_response(answer="Python is a language.")):
            result = execute_tool("web_search", {"query": "what is python"})
        assert "Python is a language." in result

    def test_query_in_header(self):
        from franki.agent.tools import execute_tool
        with patch("httpx.post", return_value=self._mock_response()):
            result = execute_tool("web_search", {"query": "fastapi routing"})
        assert "fastapi routing" in result

    def test_respects_max_results(self):
        from franki.agent.tools import execute_tool
        mock = self._mock_response(results=[
            {"title": f"Result {i}", "url": f"https://example.com/{i}", "content": "x"}
            for i in range(10)
        ])
        with patch("httpx.post") as mock_post:
            mock_post.return_value = mock
            execute_tool("web_search", {"query": "test", "max_results": 3})
            call_body = mock_post.call_args[1]["json"]
            assert call_body["max_results"] == 3

    def test_no_key_falls_back_to_ddg(self):
        from franki.agent.tools import _ddg_search
        mock_instance = MagicMock()
        mock_instance.__enter__ = MagicMock(return_value=mock_instance)
        mock_instance.__exit__ = MagicMock(return_value=False)
        mock_instance.text.return_value = [
            {"title": "DDG result", "href": "https://example.com", "body": "some content"}
        ]
        with patch("franki.agent.tools.DDGS", new=MagicMock(return_value=mock_instance)):
            result = _ddg_search("python", 3)
        assert "DDG result" in result
        assert "example.com" in result

    def test_invalid_key_returns_error(self):
        from franki.agent.tools import execute_tool
        mock = MagicMock()
        mock.status_code = 401
        with patch("httpx.post", return_value=mock):
            result = execute_tool("web_search", {"query": "test"})
        assert "invalid" in result.lower() or "401" in result

    def test_rate_limit_returns_error(self):
        from franki.agent.tools import execute_tool
        mock = MagicMock()
        mock.status_code = 429
        with patch("httpx.post", return_value=mock):
            result = execute_tool("web_search", {"query": "test"})
        assert "rate limit" in result.lower()

    def test_connection_error_returns_error(self):
        from franki.agent.tools import execute_tool
        with patch("httpx.post", side_effect=Exception("connection refused")):
            result = execute_tool("web_search", {"query": "test"})
        assert "error" in result.lower()

    def test_no_results_returns_message(self):
        from franki.agent.tools import execute_tool
        mock = MagicMock()
        mock.status_code = 200
        mock.json.return_value = {"answer": "", "results": []}
        with patch("httpx.post", return_value=mock):
            result = execute_tool("web_search", {"query": "xyzzy obscure thing"})
        assert "no" in result.lower()

    def test_snippet_truncated_at_350_chars(self):
        from franki.agent.tools import execute_tool
        long_content = "x" * 500
        mock = MagicMock()
        mock.status_code = 200
        mock.json.return_value = {
            "answer": "",
            "results": [{"title": "Big page", "url": "https://big.com", "content": long_content}],
        }
        with patch("httpx.post", return_value=mock):
            result = execute_tool("web_search", {"query": "test"})
        assert "…" in result

    def test_max_results_capped_at_10(self):
        from franki.agent.tools import execute_tool
        with patch("httpx.post") as mock_post:
            mock_post.return_value = self._mock_response()
            execute_tool("web_search", {"query": "test", "max_results": 99})
            call_body = mock_post.call_args[1]["json"]
            assert call_body["max_results"] <= 10


# ── READ_ONLY_TOOLS membership ────────────────────────────────────────────────

class TestWebSearchReadOnly:
    def test_web_search_in_read_only_tools(self):
        from franki.agent.tools import READ_ONLY_TOOLS
        assert "web_search" in READ_ONLY_TOOLS

    def test_web_search_not_in_needs_confirm(self):
        from franki.agent.tools import NEEDS_CONFIRM
        assert "web_search" not in NEEDS_CONFIRM
