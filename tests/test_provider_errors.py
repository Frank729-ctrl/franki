"""Tests for providers/generic.py — friendly error message parsing."""
import json
import pytest
from franki.providers.generic import _parse_friendly_error


def _body(msg: str, code: str | None = None) -> str:
    err: dict = {"message": msg}
    if code:
        err["code"] = code
    return json.dumps({"error": err})


class TestFriendlyErrors:
    def test_401_invalid_key(self):
        msg = _parse_friendly_error(401, _body("Unauthorized"), "groq", "llama")
        assert "invalid API key" in msg
        assert "groq" in msg

    def test_403_access_denied(self):
        msg = _parse_friendly_error(403, _body("Forbidden"), "openrouter", "gpt-4")
        assert "access denied" in msg
        assert "gpt-4" in msg

    def test_404_model_not_found(self):
        msg = _parse_friendly_error(404, _body("model not found"), "gemini", "gemini-bad")
        assert "not found" in msg
        assert "gemini-bad" in msg
        assert "/model" in msg or "/config" in msg

    def test_429_rate_limit(self):
        msg = _parse_friendly_error(429, _body("rate limit exceeded"), "groq", "llama")
        assert "rate limit" in msg

    def test_500_server_error(self):
        msg = _parse_friendly_error(500, "", "groq", "llama")
        assert "server error" in msg

    def test_503_unavailable(self):
        msg = _parse_friendly_error(503, "", "groq", "llama")
        assert "unavailable" in msg

    def test_unknown_status_falls_back_to_json_message(self):
        body = _body("custom provider error message")
        msg = _parse_friendly_error(422, body, "myprovider", "mymodel")
        assert "custom provider error message" in msg

    def test_unknown_status_with_invalid_json(self):
        msg = _parse_friendly_error(418, "not json at all", "myprovider", "mymodel")
        assert "418" in msg

    def test_provider_name_included_in_most_messages(self):
        for status in (401, 403, 404, 500, 503):
            msg = _parse_friendly_error(status, "{}", "myprovider", "mymodel")
            assert "myprovider" in msg


class TestRateLimitSignalDetection:
    """Test that rate-limit body strings are caught by 400-level status codes."""

    def test_rate_limit_signal_in_body_triggers_rate_limit_message(self):
        # "quota_exceeded" is a RATE_LIMIT_SIGNAL, so even a 400 body containing
        # it gets normalized to the standard "rate limit hit" message.
        body = json.dumps({"error": {"message": "quota_exceeded for today"}})
        msg = _parse_friendly_error(400, body, "groq", "llama")
        assert "rate limit" in msg.lower()
