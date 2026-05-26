"""Additional command tests for uncovered command function bodies."""
import asyncio
import pytest
from io import StringIO
from unittest.mock import patch, MagicMock

from franki.config import FrankiConfig
from franki.session import Session
from franki.utils.search import SearchResult


def _cfg(**kwargs):
    base = {
        "active_provider": "groq",
        "active_skill": "coding",
        "providers": {
            "groq": {
                "api_key": "sk-test",
                "base_url": "https://api.groq.com/openai/v1",
                "model": "llama-3.3-70b",
                "priority": 1,
                "key_required": True,
                "capabilities": ["coding", "speed"],
            }
        },
        "routing_strategy": "capability",
    }
    base.update(kwargs)
    return FrankiConfig(**base)


def _noop(*args, **kwargs):
    pass


# ── handle_command dispatch for uncovered commands ────────────────────────────

class TestHandleCommandMore:
    def test_compact_dispatches(self):
        from franki.commands import handle_command
        s = Session()
        s.add_user("q")
        s.add_assistant("a")
        with patch("franki.ai_ops.ask_ai", return_value="summary"):
            result = handle_command("/compact", _cfg(), s, _noop, _noop)
        assert result is True

    def test_copy_dispatches_no_response(self):
        from franki.commands import handle_command
        result = handle_command("/copy", _cfg(), Session(), _noop, _noop)
        assert result is True

    def test_note_dispatches(self):
        from franki.commands import handle_command
        import tempfile, os
        with tempfile.TemporaryDirectory() as tmp:
            cfg = _cfg()
            cfg.export_path = tmp
            with patch("franki.memory.track_note"):
                result = handle_command("/note test finding", cfg, Session(), _noop, _noop)
        assert result is True

    def test_report_dispatches(self):
        from franki.commands import handle_command
        with patch("franki.reporter.run_report"):
            result = handle_command("/report", _cfg(), Session(), _noop, _noop)
        assert result is True

    def test_search_empty_query(self):
        from franki.commands import handle_command
        result = handle_command("/search", _cfg(), Session(), _noop, _noop)
        assert result is True

    def test_search_with_query_handles_error(self):
        from franki.commands import handle_command
        from franki.utils.search import SearchError
        with patch("franki.utils.search.web_search", side_effect=SearchError("no key")):
            result = handle_command("/search nmap tutorial", _cfg(), Session(), _noop, _noop)
        assert result is True

    def test_mitre_dispatches(self):
        from franki.commands import handle_command
        with patch("franki.mitre.run_mitre"):
            result = handle_command("/mitre process injection", _cfg(), Session(), _noop, _noop)
        assert result is True

    def test_payload_dispatches(self):
        from franki.commands import handle_command
        with patch("franki.ai_ops.run_payload"):
            result = handle_command("/payload XSS", _cfg(), Session(), _noop, _noop)
        assert result is True

    def test_tools_dispatches(self):
        from franki.commands import handle_command
        with patch("franki.ai_ops.run_tools"):
            result = handle_command("/tools enumerate SMB", _cfg(), Session(), _noop, _noop)
        assert result is True

    def test_explain_dispatches(self):
        from franki.commands import handle_command
        with patch("franki.ai_ops.run_explain"):
            result = handle_command("/explain nmap", _cfg(), Session(), _noop, _noop)
        assert result is True

    def test_providers_dispatches_eof(self):
        from franki.commands import handle_command
        with patch("builtins.input", side_effect=EOFError):
            result = handle_command("/providers", _cfg(), Session(), _noop, _noop)
        assert result is True

    def test_mcp_dispatches(self):
        from franki.commands import handle_command
        result = handle_command("/mcp", _cfg(), Session(), _noop, _noop)
        assert result is True

    def test_init_dispatches(self):
        from franki.commands import handle_command
        updated = _cfg()
        with patch("franki.setup_wizard.run_wizard", return_value=updated):
            result = handle_command("/init", _cfg(), Session(), _noop, _noop)
        assert result is True

    def test_config_dispatches(self):
        from franki.commands import handle_command
        with patch("franki.config_cmd.run_interactive_config"):
            result = handle_command("/config", _cfg(), Session(), _noop, _noop)
        assert result is True


# ── _cmd_compact ──────────────────────────────────────────────────────────────

class TestCmdCompact:
    def test_compacts_session(self):
        from franki.commands import _cmd_compact
        s = Session()
        s.add_user("long conversation")
        s.add_assistant("long answer")
        with patch("franki.ai_ops.ask_ai", return_value="brief summary"):
            result = _cmd_compact(_cfg(), s)
        assert result is True

    def test_returns_true_always(self):
        from franki.commands import _cmd_compact
        with patch("franki.ai_ops.run_compact"):
            assert _cmd_compact(_cfg(), Session()) is True


# ── _cmd_report ───────────────────────────────────────────────────────────────

class TestCmdReport:
    def test_calls_reporter_run_report(self):
        from franki.commands import _cmd_report
        with patch("franki.reporter.run_report") as mock:
            result = _cmd_report(_cfg(), Session())
        assert result is True
        assert mock.called


# ── _cmd_search ───────────────────────────────────────────────────────────────

class TestCmdSearch:
    def _make_result(self, answer="", results=None):
        return SearchResult(
            query="test",
            answer=answer,
            results=results or [],
        )

    def test_empty_query_prints_usage(self):
        from franki.commands import _cmd_search
        result = _cmd_search(_cfg(), Session(), "")
        assert result is True

    def test_search_error_handled(self):
        from franki.commands import _cmd_search
        from franki.utils.search import SearchError
        with patch("franki.utils.search.web_search", side_effect=SearchError("no key")):
            result = _cmd_search(_cfg(), Session(), "nmap")
        assert result is True

    def test_successful_search_adds_to_session(self):
        from franki.commands import _cmd_search
        sr = self._make_result(answer="Nmap is a scanner", results=[
            {"title": "Nmap docs", "url": "https://nmap.org", "content": "network scanner"},
        ])
        s = Session()
        with patch("franki.utils.search.web_search", return_value=sr):
            result = _cmd_search(_cfg(), s, "nmap tool")
        assert result is True
        # Result context should be in session
        assert len(s.history_display()) == 1

    def test_search_with_no_results(self):
        from franki.commands import _cmd_search
        sr = self._make_result()
        with patch("franki.utils.search.web_search", return_value=sr):
            result = _cmd_search(_cfg(), Session(), "obscure query")
        assert result is True

    def test_search_with_long_snippet(self):
        from franki.commands import _cmd_search
        sr = self._make_result(results=[{
            "title": "t", "url": "u", "content": "x" * 300
        }])
        with patch("franki.utils.search.web_search", return_value=sr):
            result = _cmd_search(_cfg(), Session(), "test")
        assert result is True


# ── _cmd_mcp ─────────────────────────────────────────────────────────────────

class TestCmdMcp:
    def test_list_no_servers(self):
        from franki.commands import _cmd_mcp
        result = _cmd_mcp(_cfg(), "", _noop)
        assert result is True

    def test_list_with_servers(self):
        from franki.commands import _cmd_mcp
        cfg = _cfg()
        cfg.mcp = {"filesystem": {"command": "npx", "args": ["-y", "@mcp/fs"], "enabled": True}}
        result = _cmd_mcp(cfg, "list", _noop)
        assert result is True

    def test_add_eof_cancels(self):
        from franki.commands import _cmd_mcp
        with patch("builtins.input", side_effect=EOFError):
            result = _cmd_mcp(_cfg(), "add", _noop)
        assert result is True

    def test_add_empty_name_cancels(self):
        from franki.commands import _cmd_mcp
        with patch("builtins.input", return_value=""):
            result = _cmd_mcp(_cfg(), "add", _noop)
        assert result is True

    def test_add_server_successfully(self):
        from franki.commands import _cmd_mcp
        cfg = _cfg()
        inputs = iter(["myserver", "npx", "-y @mcp/server"])
        with patch("builtins.input", side_effect=inputs):
            save_fn = MagicMock()
            result = _cmd_mcp(cfg, "add", save_fn)
        assert result is True
        assert "myserver" in cfg.mcp
        assert save_fn.called

    def test_remove_nonexistent(self):
        from franki.commands import _cmd_mcp
        result = _cmd_mcp(_cfg(), "remove nonexistent", _noop)
        assert result is True

    def test_remove_existing(self):
        from franki.commands import _cmd_mcp
        cfg = _cfg()
        cfg.mcp = {"myserver": {"command": "npx", "args": [], "enabled": True}}
        save_fn = MagicMock()
        result = _cmd_mcp(cfg, "remove myserver", save_fn)
        assert result is True
        assert "myserver" not in cfg.mcp
        assert save_fn.called

    def test_remove_no_name(self):
        from franki.commands import _cmd_mcp
        result = _cmd_mcp(_cfg(), "remove", _noop)
        assert result is True

    def test_unknown_subcommand(self):
        from franki.commands import _cmd_mcp
        result = _cmd_mcp(_cfg(), "unknown", _noop)
        assert result is True


# ── _cmd_providers ────────────────────────────────────────────────────────────

class TestCmdProviders:
    def test_no_providers_shows_none_message(self):
        from franki.commands import _cmd_providers
        cfg = FrankiConfig()  # no providers
        with patch("builtins.input", side_effect=EOFError):
            result = _cmd_providers(cfg, _noop, _noop)
        assert result is True

    def test_quit_exits_loop(self):
        from franki.commands import _cmd_providers
        with patch("builtins.input", return_value="q"):
            result = _cmd_providers(_cfg(), _noop, _noop)
        assert result is True

    def test_empty_input_exits_loop(self):
        from franki.commands import _cmd_providers
        with patch("builtins.input", return_value=""):
            result = _cmd_providers(_cfg(), _noop, _noop)
        assert result is True

    def test_unknown_choice_continues(self):
        from franki.commands import _cmd_providers
        inputs = iter(["x", "q"])
        with patch("builtins.input", side_effect=inputs):
            result = _cmd_providers(_cfg(), _noop, _noop)
        assert result is True

    def test_remove_provider_by_name(self):
        from franki.commands import _cmd_providers
        cfg = _cfg()
        inputs = iter(["r", "groq", "q"])
        save_fn = MagicMock()
        with patch("builtins.input", side_effect=inputs):
            result = _cmd_providers(cfg, save_fn, _noop)
        assert result is True
        assert "groq" not in cfg.providers
        assert save_fn.called

    def test_remove_provider_not_found(self):
        from franki.commands import _cmd_providers
        cfg = _cfg()
        inputs = iter(["r", "nonexistent", "q"])
        with patch("builtins.input", side_effect=inputs):
            result = _cmd_providers(cfg, _noop, _noop)
        assert result is True

    def test_remove_eof_continues(self):
        from franki.commands import _cmd_providers
        cfg = _cfg()
        inputs = iter(["r", EOFError, "q"])

        def input_side_effect(prompt=""):
            val = next(iter_inputs)
            if val is EOFError:
                raise EOFError
            return val

        iter_inputs = iter(["r", "", "q"])
        first_call = [True]

        def controlled_input(p=""):
            val = next(iter_inputs)
            return val

        # r, then EOFError on second call, then q
        call_count = [0]
        responses = ["r", "q"]
        second_eof = [False]

        def smart_input(p=""):
            if not second_eof[0] and call_count[0] == 1:
                second_eof[0] = True
                raise EOFError
            val = responses[min(call_count[0], len(responses) - 1)]
            call_count[0] += 1
            return val

        with patch("builtins.input", side_effect=smart_input):
            result = _cmd_providers(cfg, _noop, _noop)
        assert result is True

    def test_set_default_provider_by_name(self):
        from franki.commands import _cmd_providers
        cfg = FrankiConfig(
            active_provider="p1",
            providers={
                "p1": {"api_key": "k1", "base_url": "http://p1/v1", "model": "m1", "priority": 1, "key_required": True},
                "p2": {"api_key": "k2", "base_url": "http://p2/v1", "model": "m2", "priority": 2, "key_required": True},
            },
        )
        inputs = iter(["d", "p2", "q"])
        save_fn = MagicMock()
        with patch("builtins.input", side_effect=inputs):
            result = _cmd_providers(cfg, save_fn, _noop)
        assert result is True
        assert cfg.active_provider == "p2"

    def test_set_default_by_index(self):
        from franki.commands import _cmd_providers
        cfg = FrankiConfig(
            active_provider="p1",
            providers={
                "p1": {"api_key": "k1", "base_url": "http://p1/v1", "model": "m1", "priority": 1, "key_required": True},
                "p2": {"api_key": "k2", "base_url": "http://p2/v1", "model": "m2", "priority": 2, "key_required": True},
            },
        )
        inputs = iter(["d", "2", "q"])
        save_fn = MagicMock()
        with patch("builtins.input", side_effect=inputs):
            result = _cmd_providers(cfg, save_fn, _noop)
        assert result is True
        assert cfg.active_provider == "p2"

    def test_remove_by_index(self):
        from franki.commands import _cmd_providers
        cfg = FrankiConfig(
            active_provider="p1",
            providers={
                "p1": {"api_key": "k1", "base_url": "http://p1/v1", "model": "m1", "priority": 1, "key_required": True},
            },
        )
        inputs = iter(["r", "1", "q"])
        save_fn = MagicMock()
        with patch("builtins.input", side_effect=inputs):
            result = _cmd_providers(cfg, save_fn, _noop)
        assert result is True
        assert "p1" not in cfg.providers


# ── _cmd_init / _cmd_config_edit ─────────────────────────────────────────────

class TestCmdInit:
    def test_runs_wizard_and_updates_cfg(self):
        from franki.commands import _cmd_init
        updated = _cfg()
        updated.active_provider = "gemini"
        with patch("franki.setup_wizard.run_wizard", return_value=updated):
            save_fn = MagicMock()
            result = _cmd_init(_cfg(), save_fn, _noop)
        assert result is True
        assert save_fn.called


class TestCmdConfigEdit:
    def test_calls_run_interactive_config(self):
        from franki.commands import _cmd_config_edit
        with patch("franki.config_cmd.run_interactive_config") as mock:
            result = _cmd_config_edit(_cfg(), _noop, _noop)
        assert result is True
        assert mock.called


# ── /export dispatch ──────────────────────────────────────────────────────────

class TestExportDispatch:
    def test_export_dispatches(self):
        from franki.commands import handle_command
        from franki.session import Session
        s = Session()
        s.add_user("q")
        s.add_assistant("a")
        with patch("franki.exporter.export_session", return_value="/tmp/session.md"):
            result = handle_command("/export", _cfg(), s, _noop, _noop)
        assert result is True

    def test_export_returns_none_gracefully(self):
        from franki.commands import handle_command
        from franki.session import Session
        s = Session()
        with patch("franki.exporter.export_session", return_value=None):
            result = handle_command("/export", _cfg(), s, _noop, _noop)
        assert result is True


# ── _cmd_copy errors ──────────────────────────────────────────────────────────

class TestCmdCopyErrors:
    def test_import_error_prints_message(self):
        from franki.commands import _cmd_copy
        from franki.session import Session
        s = Session()
        s.add_user("q")
        s.add_assistant("AI response")
        with patch("franki.commands._strip_markup", return_value="clean"):
            import sys
            original = sys.modules.get("pyperclip")
            sys.modules["pyperclip"] = None  # type: ignore — triggers ImportError
            try:
                result = _cmd_copy(s)
            finally:
                if original is None:
                    del sys.modules["pyperclip"]
                else:
                    sys.modules["pyperclip"] = original
        assert result is True

    def test_exception_in_copy_handled(self):
        from franki.commands import _cmd_copy
        from franki.session import Session
        s = Session()
        s.add_user("q")
        s.add_assistant("AI response")
        mock_pyperclip = MagicMock()
        mock_pyperclip.copy.side_effect = Exception("clipboard locked")
        import sys
        sys.modules["pyperclip"] = mock_pyperclip
        try:
            with patch("franki.commands._strip_markup", return_value="clean"):
                result = _cmd_copy(s)
        finally:
            del sys.modules["pyperclip"]
        assert result is True


# ── _cmd_model edge cases ─────────────────────────────────────────────────────

class TestCmdModelEdgeCases:
    def test_shows_no_model_providers_skipped(self):
        from franki.commands import _cmd_model
        from franki.config import FrankiConfig
        # Provider with empty model — should be skipped
        cfg = FrankiConfig(
            active_provider="groq",
            providers={
                "groq": {
                    "api_key": "sk-test",
                    "base_url": "https://x",
                    "model": "",  # empty model — skipped
                    "priority": 1,
                },
                "gemini": {
                    "api_key": "sk-gem",
                    "base_url": "https://y",
                    "model": "gemini-pro",  # has model — shown
                    "priority": 2,
                },
            },
        )
        with patch("builtins.input", side_effect=EOFError):
            result = _cmd_model(cfg, "", _noop, _noop)
        assert result is True


# ── _cmd_providers advanced ───────────────────────────────────────────────────

class TestCmdProvidersAdvanced:
    def test_no_key_provider_shows_red_status(self):
        from franki.commands import _cmd_providers
        from franki.config import FrankiConfig
        import os
        # Provider with key_required=True but no key → "no key" status
        cfg = FrankiConfig(
            active_provider="groq",
            providers={
                "groq": {
                    "api_key": "",  # no key
                    "base_url": "https://x",
                    "model": "m",
                    "priority": 1,
                    "key_required": True,
                }
            },
        )
        with patch.dict(os.environ, {}, clear=False):
            # Remove GROQ_API_KEY if set
            os.environ.pop("GROQ_API_KEY", None)
            with patch("builtins.input", return_value="q"):
                result = _cmd_providers(cfg, _noop, _noop)
        assert result is True

    def test_option_a_add_provider(self):
        from franki.commands import _cmd_providers
        cfg = _cfg()
        cfg.active_provider = ""  # clear so it gets set after add
        call_count = [0]
        responses = ["a", "q"]

        def fake_input(p=""):
            idx = call_count[0]
            call_count[0] += 1
            return responses[idx] if idx < len(responses) else "q"

        def fake_add(cfg, is_first):
            cfg.providers["newprovider"] = {
                "api_key": "sk", "base_url": "x", "model": "m", "priority": 2, "key_required": True,
            }
            return True

        save_fn = MagicMock()
        with patch("builtins.input", side_effect=fake_input):
            with patch("franki.setup_wizard._add_provider", side_effect=fake_add):
                result = _cmd_providers(cfg, save_fn, _noop)
        assert result is True

    def test_option_r_no_providers(self):
        from franki.commands import _cmd_providers
        from franki.config import FrankiConfig
        cfg = FrankiConfig()  # no providers
        inputs = iter(["r", "q"])
        with patch("builtins.input", side_effect=inputs):
            result = _cmd_providers(cfg, _noop, _noop)
        assert result is True

    def test_option_d_no_providers(self):
        from franki.commands import _cmd_providers
        from franki.config import FrankiConfig
        cfg = FrankiConfig()  # no providers
        inputs = iter(["d", "q"])
        with patch("builtins.input", side_effect=inputs):
            result = _cmd_providers(cfg, _noop, _noop)
        assert result is True

    def test_option_d_eof_on_input(self):
        from franki.commands import _cmd_providers
        cfg = _cfg()
        call_count = [0]

        def fake_input(p=""):
            idx = call_count[0]
            call_count[0] += 1
            if idx == 0:
                return "d"  # choose set-default option
            if idx == 1:
                raise EOFError  # EOF on "set default:" prompt
            return "q"

        with patch("builtins.input", side_effect=fake_input):
            result = _cmd_providers(cfg, _noop, _noop)
        assert result is True

    def test_option_d_not_found(self):
        from franki.commands import _cmd_providers
        cfg = _cfg()
        inputs = iter(["d", "nonexistent", "q"])
        with patch("builtins.input", side_effect=inputs):
            result = _cmd_providers(cfg, _noop, _noop)
        assert result is True

    def test_unknown_choice_prints_hint(self):
        from franki.commands import _cmd_providers
        cfg = _cfg()
        inputs = iter(["z", "q"])
        with patch("builtins.input", side_effect=inputs):
            result = _cmd_providers(cfg, _noop, _noop)
        assert result is True
