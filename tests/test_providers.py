"""Tests for providers/generic.py — _parse_friendly_error and async streaming."""
import json
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from franki.providers.generic import (
    _parse_friendly_error,
    stream_chat,
    chat_once,
    ProviderError,
    ProviderRateLimitError,
)


# ── _parse_friendly_error ─────────────────────────────────────────────────────

class TestParseFriendlyError:
    def test_401_invalid_key(self):
        msg = _parse_friendly_error(401, "", "groq", "llama")
        assert "groq" in msg
        assert "invalid API key" in msg or "invalid" in msg.lower()

    def test_403_access_denied(self):
        msg = _parse_friendly_error(403, "", "groq", "my-model")
        assert "groq" in msg
        assert "my-model" in msg
        assert "access denied" in msg or "permission" in msg.lower()

    def test_404_model_not_found(self):
        msg = _parse_friendly_error(404, "", "groq", "bad-model")
        assert "groq" in msg
        assert "bad-model" in msg
        assert "not found" in msg.lower()

    def test_429_rate_limit(self):
        msg = _parse_friendly_error(429, "", "groq", "m")
        assert "rate limit" in msg.lower() or "429" in msg

    def test_500_server_error(self):
        msg = _parse_friendly_error(500, "", "groq", "m")
        assert "groq" in msg
        assert "server error" in msg.lower() or "500" in msg

    def test_503_unavailable(self):
        msg = _parse_friendly_error(503, "", "groq", "m")
        assert "groq" in msg
        assert "unavailable" in msg.lower() or "503" in msg

    def test_body_contains_rate_limit_signal(self):
        # 400 but body says "rate_limit"
        msg = _parse_friendly_error(400, "rate_limit exceeded", "groq", "m")
        assert "rate limit" in msg.lower() or "groq" in msg

    def test_json_error_message_extracted(self):
        body = json.dumps({"error": {"message": "context length exceeded"}})
        msg = _parse_friendly_error(400, body, "groq", "m")
        assert "context length exceeded" in msg

    def test_json_error_string(self):
        body = json.dumps({"error": "invalid request format"})
        msg = _parse_friendly_error(400, body, "groq", "m")
        assert "invalid request format" in msg

    def test_fallback_http_status(self):
        msg = _parse_friendly_error(418, "{}", "myprovider", "m")
        assert "418" in msg or "myprovider" in msg

    def test_invalid_json_body_fallback(self):
        msg = _parse_friendly_error(400, "not json {{", "groq", "m")
        assert "400" in msg or "groq" in msg


# ── Async helpers ─────────────────────────────────────────────────────────────

async def _collect_stream(gen):
    chunks = []
    async for chunk in gen:
        chunks.append(chunk)
    return chunks


class _MockStreamResp:
    """Simulates httpx streaming response as an async context manager."""

    def __init__(self, status_code=200, body=b"", lines=None, headers=None):
        self.status_code = status_code
        self._body = body
        self._lines = lines or []
        self.text = body.decode() if body else ""
        self.headers = headers or {}

    async def aread(self):
        return self._body

    async def aiter_lines(self):
        for line in self._lines:
            yield line

    def json(self):
        import json
        return json.loads(self._body)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass


class _MockClient:
    def __init__(self, resp):
        self._resp = resp

    def stream(self, *args, **kwargs):
        return self._resp

    async def post(self, *args, **kwargs):
        return self._resp

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass


def _sse_lines(chunks: list[str]) -> list[str]:
    """Build SSE lines from a list of content strings."""
    lines = []
    for c in chunks:
        data = {"choices": [{"delta": {"content": c}}]}
        lines.append(f"data: {json.dumps(data)}")
    lines.append("data: [DONE]")
    return lines


# ── stream_chat ───────────────────────────────────────────────────────────────

class TestStreamChat:
    def _patch_client(self, resp):
        mock = _MockClient(resp)
        return patch("httpx.AsyncClient", return_value=mock)

    def test_streams_content_chunks(self):
        lines = _sse_lines(["hello", " world"])
        resp = _MockStreamResp(200, lines=lines)
        with self._patch_client(resp):
            chunks = asyncio.run(_collect_stream(
                stream_chat("key", "model", [], "http://test/v1")
            ))
        assert "hello" in chunks
        assert " world" in chunks

    def test_done_sentinel_stops_iteration(self):
        lines = _sse_lines(["data"])
        resp = _MockStreamResp(200, lines=lines)
        with self._patch_client(resp):
            chunks = asyncio.run(_collect_stream(
                stream_chat("key", "model", [], "http://test/v1")
            ))
        assert len(chunks) == 1

    def test_non_data_lines_ignored(self):
        lines = ["", ": heartbeat", _sse_lines(["hi"])[0], "data: [DONE]"]
        resp = _MockStreamResp(200, lines=lines)
        with self._patch_client(resp):
            chunks = asyncio.run(_collect_stream(
                stream_chat("key", "model", [], "http://test/v1")
            ))
        assert chunks == ["hi"]

    def test_empty_delta_content_skipped(self):
        empty_data = {"choices": [{"delta": {}}]}
        lines = [f"data: {json.dumps(empty_data)}", "data: [DONE]"]
        resp = _MockStreamResp(200, lines=lines)
        with self._patch_client(resp):
            chunks = asyncio.run(_collect_stream(
                stream_chat("key", "model", [], "http://test/v1")
            ))
        assert chunks == []

    def test_401_raises_provider_error(self):
        resp = _MockStreamResp(401, body=b"Unauthorized")
        with self._patch_client(resp):
            with pytest.raises(ProviderError):
                asyncio.run(_collect_stream(
                    stream_chat("key", "model", [], "http://test/v1")
                ))

    def test_429_raises_rate_limit_error(self):
        resp = _MockStreamResp(429, body=b"rate_limit exceeded")
        with self._patch_client(resp):
            with pytest.raises(ProviderRateLimitError):
                asyncio.run(_collect_stream(
                    stream_chat("key", "model", [], "http://test/v1")
                ))

    def test_503_rate_limit_signal_raises_rate_limit_error(self):
        resp = _MockStreamResp(503, body=b"service unavailable")
        with self._patch_client(resp):
            with pytest.raises((ProviderRateLimitError, ProviderError)):
                asyncio.run(_collect_stream(
                    stream_chat("key", "model", [], "http://test/v1")
                ))

    def test_body_rate_limit_signal_raises_rate_limit_error(self):
        resp = _MockStreamResp(400, body=b'{"error": "quota_exceeded for model"}')
        with self._patch_client(resp):
            with pytest.raises((ProviderRateLimitError, ProviderError)):
                asyncio.run(_collect_stream(
                    stream_chat("key", "model", [], "http://test/v1")
                ))

    def test_connect_error_raises_provider_error(self):
        import httpx

        class BadClient:
            def stream(self, *args, **kwargs):
                raise httpx.ConnectError("connection refused")

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                pass

        with patch("httpx.AsyncClient", return_value=BadClient()):
            with pytest.raises(ProviderError, match="connection failed"):
                asyncio.run(_collect_stream(
                    stream_chat("key", "model", [], "http://test/v1")
                ))

    def test_read_timeout_raises_provider_error(self):
        import httpx

        class TimeoutClient:
            def stream(self, *args, **kwargs):
                raise httpx.ReadTimeout("timed out")

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                pass

        with patch("httpx.AsyncClient", return_value=TimeoutClient()):
            with pytest.raises(ProviderError, match="timed out"):
                asyncio.run(_collect_stream(
                    stream_chat("key", "model", [], "http://test/v1")
                ))

    def test_url_constructed_correctly(self):
        """Verify trailing slash on base_url is stripped."""
        called_urls = []

        class CapturingStreamResp:
            status_code = 200
            _lines = ["data: [DONE]"]

            async def aread(self):
                return b""

            async def aiter_lines(self):
                for line in self._lines:
                    yield line

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                pass

        class CapturingClient:
            def stream(self, method, url, **kwargs):
                called_urls.append(url)
                return CapturingStreamResp()

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                pass

        with patch("httpx.AsyncClient", return_value=CapturingClient()):
            asyncio.run(_collect_stream(
                stream_chat("key", "model", [], "http://test/v1/")
            ))
        assert called_urls[0] == "http://test/v1/chat/completions"

    def test_malformed_json_chunk_skipped(self):
        lines = ["data: {bad json}", "data: [DONE]"]
        resp = _MockStreamResp(200, lines=lines)
        with self._patch_client(resp):
            chunks = asyncio.run(_collect_stream(
                stream_chat("key", "model", [], "http://test/v1")
            ))
        assert chunks == []


# ── chat_once ─────────────────────────────────────────────────────────────────

class TestChatOnce:
    def _patch_client(self, resp):
        mock = _MockClient(resp)
        return patch("httpx.AsyncClient", return_value=mock)

    def test_returns_content_string(self):
        body = json.dumps({"choices": [{"message": {"content": "hello!"}}]}).encode()
        resp = _MockStreamResp(200, body=body)
        with self._patch_client(resp):
            result = asyncio.run(chat_once("key", "model", [], "http://test/v1"))
        assert result == "hello!"

    def test_401_raises_provider_error(self):
        resp = _MockStreamResp(401, body=b"Unauthorized")
        with self._patch_client(resp):
            with pytest.raises(ProviderError):
                asyncio.run(chat_once("key", "model", [], "http://test/v1"))

    def test_429_raises_rate_limit_error(self):
        resp = _MockStreamResp(429, body=b"rate_limit")
        with self._patch_client(resp):
            with pytest.raises(ProviderRateLimitError):
                asyncio.run(chat_once("key", "model", [], "http://test/v1"))

    def test_connect_error_raises_provider_error(self):
        import httpx

        class BadClient:
            async def post(self, *args, **kwargs):
                raise httpx.ConnectError("refused")

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                pass

        with patch("httpx.AsyncClient", return_value=BadClient()):
            with pytest.raises(ProviderError, match="connection failed"):
                asyncio.run(chat_once("key", "model", [], "http://test/v1"))
