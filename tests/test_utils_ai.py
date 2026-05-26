"""Tests for utils/ai.py — ask_ai and stream_to_terminal with mocked routing."""
import asyncio
import pytest
from unittest.mock import patch, MagicMock

from franki.config import FrankiConfig
from franki.providers.generic import ProviderError


def _cfg():
    return FrankiConfig(
        active_provider="groq",
        providers={"groq": {
            "api_key": "sk-test",
            "base_url": "https://api.groq.com/openai/v1",
            "model": "llama",
            "priority": 1,
        }},
    )


async def _good_stream(*args, **kwargs):
    yield "hello"
    yield " world"


async def _empty_stream(*args, **kwargs):
    return
    yield


# ── ask_ai ────────────────────────────────────────────────────────────────────

class TestAskAi:
    def test_returns_collected_text(self):
        from franki.utils.ai import ask_ai
        with patch("franki.router.stream_chat", side_effect=_good_stream):
            result = ask_ai(_cfg(), [{"role": "user", "content": "hi"}])
        assert result == "hello world"

    def test_empty_stream_returns_empty_string(self):
        from franki.utils.ai import ask_ai
        with patch("franki.router.stream_chat", side_effect=_empty_stream):
            result = ask_ai(_cfg(), [{"role": "user", "content": "hi"}])
        assert result == ""

    def test_with_console_runs_with_status(self):
        from franki.utils.ai import ask_ai
        from rich.console import Console
        console = Console(file=MagicMock(), highlight=False)
        with patch("franki.router.stream_chat", side_effect=_good_stream):
            result = ask_ai(_cfg(), [], console=console, status_text="working...")
        assert result == "hello world"

    def test_custom_status_text(self):
        from franki.utils.ai import ask_ai
        from rich.console import Console
        console = Console(file=MagicMock(), highlight=False)
        with patch("franki.router.stream_chat", side_effect=_good_stream):
            result = ask_ai(_cfg(), [], console=console, status_text="custom status")
        assert result == "hello world"

    def test_no_providers_raises(self):
        from franki.utils.ai import ask_ai
        cfg = FrankiConfig()  # no providers
        with pytest.raises(ProviderError):
            ask_ai(cfg, [])


# ── stream_to_terminal ────────────────────────────────────────────────────────

class TestStreamToTerminal:
    def test_returns_full_text(self):
        from franki.utils.ai import stream_to_terminal
        with patch("franki.router.stream_chat", side_effect=_good_stream):
            with patch("sys.stdout") as mock_stdout:
                result = stream_to_terminal(_cfg(), [])
        assert result == "hello world"

    def test_writes_chunks_to_stdout(self):
        from franki.utils.ai import stream_to_terminal
        written = []
        with patch("franki.router.stream_chat", side_effect=_good_stream):
            with patch("sys.stdout") as mock_stdout:
                mock_stdout.write = lambda s: written.append(s)
                mock_stdout.flush = lambda: None
                result = stream_to_terminal(_cfg(), [])
        assert "hello" in written
        assert " world" in written

    def test_empty_stream_returns_empty(self):
        from franki.utils.ai import stream_to_terminal
        with patch("franki.router.stream_chat", side_effect=_empty_stream):
            with patch("sys.stdout") as mock_stdout:
                mock_stdout.write = lambda s: None
                mock_stdout.flush = lambda: None
                result = stream_to_terminal(_cfg(), [])
        assert result == ""
