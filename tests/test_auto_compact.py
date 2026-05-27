"""Tests for auto-compact: config fields, session.compact(), threshold logic."""
import pytest
from franki.config import FrankiConfig
from franki.session import Session


class TestAutoCompactConfig:
    def test_defaults(self):
        cfg = FrankiConfig()
        assert cfg.auto_compact is True
        assert cfg.auto_compact_threshold == 0.70

    def test_can_disable(self):
        cfg = FrankiConfig(auto_compact=False)
        assert cfg.auto_compact is False

    def test_threshold_serialises_round_trip(self):
        cfg = FrankiConfig(auto_compact_threshold=0.90)
        import json
        restored = FrankiConfig(**json.loads(cfg.model_dump_json()))
        assert restored.auto_compact_threshold == pytest.approx(0.90)


class TestSessionCompact:
    def _session_with_history(self) -> Session:
        s = Session(skill="coding")
        s.add_user("explain async/await")
        s.add_assistant("Async/await lets you write non-blocking code.")
        s.add_user("show me an example")
        s.add_assistant("Here is an example: async def fetch(): ...")
        return s

    def test_compact_reduces_to_one_non_system_message(self):
        s = self._session_with_history()
        assert len(s.history_display()) == 4
        s.compact("Summary: discussed async/await and saw an example.")
        assert len(s.history_display()) == 1

    def test_compact_preserves_system_prompt(self):
        s = self._session_with_history()
        s.compact("brief summary")
        msgs = s.get_messages()
        assert msgs[0]["role"] == "system"

    def test_compact_message_contains_summary(self):
        s = self._session_with_history()
        s.compact("key finding: async/await rocks")
        display = s.history_display()
        assert "key finding" in display[0]["content"]

    def test_conversation_continues_after_compact(self):
        s = self._session_with_history()
        s.compact("prior context summary")
        s.add_user("what was the example again?")
        s.add_assistant("The example used async def fetch().")
        assert len(s.history_display()) == 3   # summary + new exchange


class TestThresholdLogic:
    def test_token_usage_pct_below_threshold(self):
        from franki.ui.token_warning import token_usage_pct
        pct = token_usage_pct(1000, "llama-3.3-70b-versatile")  # 128k window
        assert pct < 0.85

    def test_token_usage_pct_above_threshold(self):
        from franki.ui.token_warning import token_usage_pct
        # 120 000 tokens on a 128k model ≈ 93.75%
        pct = token_usage_pct(120_000, "llama-3.3-70b-versatile")
        assert pct > 0.85

    def test_warning_text_none_below_threshold(self):
        from franki.ui.token_warning import warning_text
        result = warning_text(1000, "llama-3.3-70b-versatile")
        assert result is None

    def test_warning_text_no_emoji(self):
        from franki.ui.token_warning import warning_text
        result = warning_text(120_000, "llama-3.3-70b-versatile")
        assert result is not None
        assert "context" in result
        assert "compact" in result
        # No emoji characters (emoji codepoints are >= U+1F000)
        for ch in result:
            assert ord(ch) < 0x1F000, f"unexpected emoji/symbol: {ch!r}"
