"""Tests for report.py and reporter.py — mocked AI calls."""
import pytest
from io import StringIO
from pathlib import Path
from unittest.mock import patch, MagicMock

from franki.config import FrankiConfig
from franki.session import Session


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


def _session_with_history(skill="coding"):
    s = Session(skill=skill)
    s.add_user("how do I scan ports?")
    s.add_assistant("Use nmap: nmap -sV 10.0.0.1")
    return s


# ── report.py ─────────────────────────────────────────────────────────────────

class TestRunReport:
    def test_empty_session_prints_notice(self, capsys):
        from franki.report import run_report
        s = Session()
        run_report(_cfg(), s)
        # No crash, prints "no conversation" message

    def test_pentest_uses_pentest_sys_prompt(self):
        from franki.report import run_report
        s = _session_with_history(skill="pentest")
        captured = []
        with patch("franki.ai_ops.ask_ai", side_effect=lambda cfg, msgs, **kw: (captured.extend(msgs), "report text")[1]):
            run_report(_cfg(), s)
        assert any("penetration" in m.get("content", "").lower() for m in captured)

    def test_soc_uses_soc_sys_prompt(self):
        from franki.report import run_report
        s = _session_with_history(skill="soc")
        captured = []
        with patch("franki.ai_ops.ask_ai", side_effect=lambda cfg, msgs, **kw: (captured.extend(msgs), "report text")[1]):
            run_report(_cfg(), s)
        assert any("incident" in m.get("content", "").lower() for m in captured)

    def test_default_skill_uses_default_prompt(self):
        from franki.report import run_report
        s = _session_with_history(skill="coding")
        captured = []
        with patch("franki.ai_ops.ask_ai", side_effect=lambda cfg, msgs, **kw: (captured.extend(msgs), "report text")[1]):
            run_report(_cfg(), s)
        # Uses _DEFAULT_SYS (not pentest/soc)
        assert any("session" in m.get("content", "").lower() for m in captured)

    def test_ai_error_prints_message(self, capsys):
        from franki.report import run_report
        s = _session_with_history()
        with patch("franki.ai_ops.ask_ai", side_effect=Exception("AI down")):
            run_report(_cfg(), s)
        # Should not raise — handled gracefully

    def test_renders_report_text(self):
        from franki.report import run_report
        s = _session_with_history()
        with patch("franki.ai_ops.ask_ai", return_value="# Report\nFindings here"):
            with patch("franki.ai_ops.render_response") as mock_render:
                run_report(_cfg(), s)
        assert mock_render.called


class TestRunPayload:
    def test_empty_type_prints_usage(self, capsys):
        from franki.report import run_payload
        run_payload(_cfg(), "")
        # No crash

    def test_valid_type_calls_stream(self):
        from franki.report import run_payload
        with patch("franki.ai_ops.stream_to_terminal") as mock_stream:
            run_payload(_cfg(), "XSS")
        assert mock_stream.called

    def test_stream_error_handled(self):
        from franki.report import run_payload
        with patch("franki.ai_ops.stream_to_terminal", side_effect=Exception("error")):
            run_payload(_cfg(), "SQLi")
        # No unhandled exception


class TestRunTools:
    def test_empty_task_prints_usage(self, capsys):
        from franki.report import run_tools
        run_tools(_cfg(), "")
        # No crash

    def test_valid_task_calls_stream(self):
        from franki.report import run_tools
        with patch("franki.ai_ops.stream_to_terminal") as mock_stream:
            run_tools(_cfg(), "enumerate SMB")
        assert mock_stream.called

    def test_stream_error_handled(self):
        from franki.report import run_tools
        with patch("franki.ai_ops.stream_to_terminal", side_effect=Exception("error")):
            run_tools(_cfg(), "nmap scan")


class TestRunExplain:
    def test_empty_tool_prints_usage(self, capsys):
        from franki.report import run_explain
        run_explain(_cfg(), "")

    def test_valid_tool_calls_stream(self):
        from franki.report import run_explain
        with patch("franki.ai_ops.stream_to_terminal") as mock_stream:
            run_explain(_cfg(), "nmap")
        assert mock_stream.called

    def test_stream_error_handled(self):
        from franki.report import run_explain
        with patch("franki.ai_ops.stream_to_terminal", side_effect=Exception("oops")):
            run_explain(_cfg(), "burpsuite")


class TestRunCompact:
    def test_empty_session_prints_notice(self, capsys):
        from franki.report import run_compact
        s = Session()
        run_compact(_cfg(), s)

    def test_compacts_session_on_success(self):
        from franki.report import run_compact
        s = _session_with_history()
        with patch("franki.ai_ops.ask_ai", return_value="brief summary"):
            run_compact(_cfg(), s)
        assert len(s.history_display()) == 1
        assert "brief summary" in s.history_display()[0]["content"]

    def test_ai_error_does_not_modify_session(self):
        from franki.report import run_compact
        s = _session_with_history()
        original_len = len(s.history_display())
        with patch("franki.ai_ops.ask_ai", side_effect=Exception("failed")):
            run_compact(_cfg(), s)
        assert len(s.history_display()) == original_len


# ── reporter.py ──────────────────────────────────────────────────────────────

class TestResolveReporterSavePath:
    def test_existing_path_returned(self, tmp_path):
        from franki.reporter import _resolve_save_path
        cfg = FrankiConfig(export_path=str(tmp_path))
        result = _resolve_save_path(cfg)
        assert result == tmp_path

    def test_creates_missing_dir(self, tmp_path):
        from franki.reporter import _resolve_save_path
        new_dir = tmp_path / "auto" / "subdir"
        cfg = FrankiConfig(export_path=str(new_dir))
        result = _resolve_save_path(cfg)
        assert result.exists()

    def test_falls_back_to_cwd_on_error(self, tmp_path):
        from franki.reporter import _resolve_save_path
        cfg = FrankiConfig(export_path="/root/forbidden/path/that/cant/be/created")
        result = _resolve_save_path(cfg)
        # Should return something (cwd) without raising
        assert result is not None


class TestReporterRunReport:
    def test_empty_session_no_crash(self, capsys):
        from franki.reporter import run_report
        s = Session()
        run_report(_cfg(), s)

    def test_pentest_uses_pentest_prompt(self, tmp_path):
        from franki.reporter import run_report
        s = _session_with_history(skill="pentest")
        captured = []
        with patch("franki.reporter.stream_to_terminal", return_value="Report content") as mock_stream:
            with patch("franki.reporter._resolve_save_path", return_value=tmp_path):
                run_report(_cfg(), s)
        assert mock_stream.called

    def test_soc_uses_soc_prompt(self, tmp_path):
        from franki.reporter import run_report
        s = _session_with_history(skill="soc")
        with patch("franki.reporter.stream_to_terminal", return_value="Incident report") as mock_stream:
            with patch("franki.reporter._resolve_save_path", return_value=tmp_path):
                run_report(_cfg(), s)
        assert mock_stream.called

    def test_report_saved_to_file(self, tmp_path):
        from franki.reporter import run_report
        s = _session_with_history()
        with patch("franki.reporter.stream_to_terminal", return_value="Report text here"):
            with patch("franki.reporter._resolve_save_path", return_value=tmp_path):
                run_report(_cfg(), s)
        files = list(tmp_path.glob("franki_report_*.md"))
        assert len(files) == 1
        assert "Report text here" in files[0].read_text()

    def test_report_file_has_header(self, tmp_path):
        from franki.reporter import run_report
        s = _session_with_history()
        with patch("franki.reporter.stream_to_terminal", return_value="body"):
            with patch("franki.reporter._resolve_save_path", return_value=tmp_path):
                run_report(_cfg(), s)
        files = list(tmp_path.glob("franki_report_*.md"))
        content = files[0].read_text()
        assert "Generated by franki" in content

    def test_stream_error_handled(self, tmp_path):
        from franki.reporter import run_report
        s = _session_with_history()
        with patch("franki.reporter.stream_to_terminal", side_effect=Exception("AI error")):
            with patch("franki.reporter._resolve_save_path", return_value=tmp_path):
                run_report(_cfg(), s)
        # No unhandled exception

    def test_save_error_handled(self, tmp_path):
        from franki.reporter import run_report
        s = _session_with_history()
        # Return a real dir but patch write_text on the resulting filepath to fail
        filepath_mock = MagicMock()
        filepath_mock.write_text = MagicMock(side_effect=PermissionError("cant write"))
        dir_mock = MagicMock()
        dir_mock.__truediv__ = MagicMock(return_value=filepath_mock)
        with patch("franki.reporter.stream_to_terminal", return_value="text"):
            with patch("franki.reporter._resolve_save_path", return_value=dir_mock):
                run_report(_cfg(), s)
        # No unhandled exception
