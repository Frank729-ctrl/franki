"""Tests for franki/feedback.py."""
import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from io import StringIO

from rich.console import Console


# ── save_feedback ─────────────────────────────────────────────────────────────

class TestSaveFeedback:
    def test_creates_jsonl_entry(self, tmp_path):
        from franki.feedback import save_feedback
        fb_file = tmp_path / "feedback.jsonl"
        with patch("franki.feedback.FEEDBACK_FILE", fb_file), \
             patch("franki.feedback.FEEDBACK_DIR", tmp_path):
            save_feedback("this tool is great", skill="pentest", msgs=5)
        lines = fb_file.read_text().strip().splitlines()
        assert len(lines) == 1
        entry = json.loads(lines[0])
        assert entry["text"] == "this tool is great"
        assert entry["skill"] == "pentest"
        assert entry["msgs"] == 5
        assert "ts" in entry
        assert "version" in entry

    def test_appends_multiple_entries(self, tmp_path):
        from franki.feedback import save_feedback
        fb_file = tmp_path / "feedback.jsonl"
        with patch("franki.feedback.FEEDBACK_FILE", fb_file), \
             patch("franki.feedback.FEEDBACK_DIR", tmp_path):
            save_feedback("first", skill="coding", msgs=2)
            save_feedback("second", skill="pentest", msgs=7)
        lines = fb_file.read_text().strip().splitlines()
        assert len(lines) == 2
        assert json.loads(lines[1])["text"] == "second"

    def test_strips_whitespace(self, tmp_path):
        from franki.feedback import save_feedback
        fb_file = tmp_path / "feedback.jsonl"
        with patch("franki.feedback.FEEDBACK_FILE", fb_file), \
             patch("franki.feedback.FEEDBACK_DIR", tmp_path):
            save_feedback("  needs more docs  ")
        entry = json.loads(fb_file.read_text())
        assert entry["text"] == "needs more docs"

    def test_creates_dir_if_missing(self, tmp_path):
        from franki.feedback import save_feedback
        nested = tmp_path / "new" / "dir"
        fb_file = nested / "feedback.jsonl"
        with patch("franki.feedback.FEEDBACK_FILE", fb_file), \
             patch("franki.feedback.FEEDBACK_DIR", nested):
            save_feedback("hello")
        assert fb_file.exists()


# ── should_ask ────────────────────────────────────────────────────────────────

class TestShouldAsk:
    def test_false_when_session_zero(self):
        from franki.feedback import should_ask
        assert should_ask(0, 10) is False

    def test_false_when_not_multiple_of_five(self):
        from franki.feedback import should_ask
        assert should_ask(1, 5) is False
        assert should_ask(3, 5) is False
        assert should_ask(7, 5) is False

    def test_false_when_too_few_messages(self):
        from franki.feedback import should_ask
        assert should_ask(5, 0) is False
        assert should_ask(5, 2) is False

    def test_true_on_fifth_session_with_enough_messages(self):
        from franki.feedback import should_ask
        assert should_ask(5, 3) is True
        assert should_ask(10, 5) is True
        assert should_ask(15, 10) is True

    def test_false_on_non_multiple(self):
        from franki.feedback import should_ask
        assert should_ask(6, 10) is False
        assert should_ask(11, 10) is False


# ── ask_feedback ──────────────────────────────────────────────────────────────

class TestAskFeedback:
    def _make_console(self):
        return Console(file=StringIO(), highlight=False, width=100)

    def test_saves_when_user_types_text(self, tmp_path):
        from franki.feedback import ask_feedback
        fb_file = tmp_path / "feedback.jsonl"
        c = self._make_console()
        with patch("builtins.input", return_value="needs a dark mode"), \
             patch("franki.feedback.FEEDBACK_FILE", fb_file), \
             patch("franki.feedback.FEEDBACK_DIR", tmp_path):
            ask_feedback(c, skill="coding", msgs=4)
        entry = json.loads(fb_file.read_text())
        assert entry["text"] == "needs a dark mode"

    def test_skips_silently_on_empty_enter(self, tmp_path):
        from franki.feedback import ask_feedback
        fb_file = tmp_path / "feedback.jsonl"
        c = self._make_console()
        with patch("builtins.input", return_value=""), \
             patch("franki.feedback.FEEDBACK_FILE", fb_file), \
             patch("franki.feedback.FEEDBACK_DIR", tmp_path):
            ask_feedback(c)
        assert not fb_file.exists()

    def test_skips_on_eof(self, tmp_path):
        from franki.feedback import ask_feedback
        fb_file = tmp_path / "feedback.jsonl"
        c = self._make_console()
        with patch("builtins.input", side_effect=EOFError), \
             patch("franki.feedback.FEEDBACK_FILE", fb_file), \
             patch("franki.feedback.FEEDBACK_DIR", tmp_path):
            ask_feedback(c)
        assert not fb_file.exists()

    def test_skips_on_keyboard_interrupt(self, tmp_path):
        from franki.feedback import ask_feedback
        fb_file = tmp_path / "feedback.jsonl"
        c = self._make_console()
        with patch("builtins.input", side_effect=KeyboardInterrupt), \
             patch("franki.feedback.FEEDBACK_FILE", fb_file), \
             patch("franki.feedback.FEEDBACK_DIR", tmp_path):
            ask_feedback(c)
        assert not fb_file.exists()

    def test_prints_thanks_after_input(self):
        from franki.feedback import ask_feedback
        c = self._make_console()
        with patch("builtins.input", return_value="great tool"), \
             patch("franki.feedback.save_feedback"):
            ask_feedback(c, skill="soc", msgs=3)
        out = c.file.getvalue()
        assert "noted" in out.lower()


# ── /feedback command ─────────────────────────────────────────────────────────

class TestCmdFeedback:
    def _session(self):
        from franki.session import Session
        s = Session()
        s.add_user("hello")
        s.add_assistant("hi")
        s.add_user("another")
        return s

    def test_no_arg_prints_usage(self, capsys):
        from franki.commands import handle_command
        from franki.config import FrankiConfig
        cfg = FrankiConfig()
        s = self._session()
        handle_command("/feedback", cfg, s, lambda c: None, lambda: None)
        # Should print usage without crashing

    def test_with_text_saves_and_confirms(self, tmp_path):
        from franki.commands import handle_command
        from franki.config import FrankiConfig
        fb_file = tmp_path / "feedback.jsonl"
        cfg = FrankiConfig()
        s = self._session()
        with patch("franki.feedback.FEEDBACK_FILE", fb_file), \
             patch("franki.feedback.FEEDBACK_DIR", tmp_path):
            handle_command("/feedback the routing UI is confusing", cfg, s, lambda c: None, lambda: None)
        entry = json.loads(fb_file.read_text())
        assert "routing" in entry["text"]

    def test_feedback_in_help_output(self, capsys):
        from franki.commands import handle_command
        from franki.config import FrankiConfig
        from franki.session import Session
        handle_command("/help", FrankiConfig(), Session(), lambda c: None, lambda: None)
        # /feedback should appear in help — just verify no crash


# ── _end_session wires feedback ───────────────────────────────────────────────

class TestEndSession:
    def test_feedback_asked_on_fifth_session(self):
        from franki.main import _end_session
        from franki.config import FrankiConfig
        from franki.session import Session

        s = Session()
        for _ in range(4):
            s.add_user("msg")
            s.add_assistant("ok")

        cfg = FrankiConfig(session_count=5)  # 5th session — should trigger

        with patch("franki.main._prompt_save_exit"), \
             patch("franki.feedback.save_feedback") as mock_save, \
             patch("builtins.input", return_value="works great"):
            _end_session(s, cfg)

        assert mock_save.called

    def test_feedback_not_asked_on_non_multiple(self):
        from franki.main import _end_session
        from franki.config import FrankiConfig
        from franki.session import Session

        s = Session()
        for _ in range(4):
            s.add_user("msg")
            s.add_assistant("ok")

        cfg = FrankiConfig(session_count=3)  # 3rd session — no trigger

        with patch("franki.main._prompt_save_exit"), \
             patch("franki.feedback.save_feedback") as mock_save, \
             patch("builtins.input", return_value="feedback"):
            _end_session(s, cfg)

        assert not mock_save.called

    def test_feedback_not_asked_when_too_few_messages(self):
        from franki.main import _end_session
        from franki.config import FrankiConfig
        from franki.session import Session

        s = Session()  # no messages → 0 user msgs

        cfg = FrankiConfig(session_count=5)

        with patch("franki.main._prompt_save_exit"), \
             patch("franki.feedback.save_feedback") as mock_save:
            _end_session(s, cfg)

        assert not mock_save.called


# ── session_count incremented in _run_repl ────────────────────────────────────

class TestSessionCountIncrement:
    def test_session_count_incremented_and_saved(self):
        from franki.main import _run_repl
        from franki.config import FrankiConfig

        cfg = FrankiConfig(
            session_count=2,
            active_provider="groq",
            providers={"groq": {
                "api_key": "sk", "base_url": "https://x",
                "model": "m", "priority": 1, "key_required": True,
            }},
        )
        saved = []

        mock_pt = MagicMock()
        mock_pt.prompt.side_effect = EOFError

        with patch("franki.main._get_pt_session", return_value=mock_pt), \
             patch("franki.main.start_version_check"), \
             patch("franki.main._end_session"), \
             patch("franki.main.save_config", side_effect=lambda c: saved.append(c.session_count)), \
             patch("franki.memory.get_context_string", return_value=""):
            _run_repl(cfg)

        assert cfg.session_count == 3
        assert 3 in saved
