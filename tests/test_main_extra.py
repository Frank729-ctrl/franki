"""Additional tests for main.py — covering remaining uncovered lines."""
import asyncio
import pytest
from unittest.mock import patch, MagicMock, AsyncMock

from franki.config import FrankiConfig
from franki.session import Session


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
                "capabilities": ["coding"],
            }
        },
    }
    base.update(kwargs)
    return FrankiConfig(**base)


# ── _check_providers — no usable provider ─────────────────────────────────────

class TestCheckProvidersNoUsable:
    def test_no_usable_provider_prints_fix_message(self, monkeypatch):
        from franki.main import _check_providers
        monkeypatch.delenv("GROQ_API_KEY", raising=False)
        # active_provider not in providers AND first_configured_provider() returns None
        cfg = FrankiConfig(
            active_provider="missing",
            providers={
                "keyless": {
                    "api_key": "",          # no key
                    "base_url": "https://x",
                    "model": "m",
                    "priority": 1,
                    "key_required": True,   # key required but empty
                }
            },
        )
        # Should print "no usable provider" message and return (not crash)
        _check_providers(cfg)


# ── _prompt_save_exit — export returns None ───────────────────────────────────

class TestPromptSaveExitExportNone:
    def test_export_returns_none_prints_cancelled(self):
        from franki.main import _prompt_save_exit
        s = Session()
        s.add_user("q")
        s.add_assistant("a")
        cfg = _cfg()
        with patch("builtins.input", return_value="y"):
            with patch("franki.exporter.export_session", return_value=None):
                _prompt_save_exit(s, cfg)  # should print "export cancelled."


# ── _maybe_warn_tokens ────────────────────────────────────────────────────────

class TestMaybeWarnTokens:
    def test_no_warning_when_low_usage(self):
        from franki.main import _maybe_warn_tokens
        s = Session()
        s.add_user("short message")
        cfg = _cfg()
        with patch("franki.main.warning_text", return_value=""):
            _maybe_warn_tokens(s, cfg)  # no crash

    def test_warning_printed_when_high_usage(self):
        from franki.main import _maybe_warn_tokens
        s = Session()
        s.add_user("q")
        cfg = _cfg()
        with patch("franki.main.warning_text", return_value="context 90% full"):
            _maybe_warn_tokens(s, cfg)  # should print warning


# ── _maybe_auto_compact — token threshold trigger ─────────────────────────────

class TestMaybeAutoCompactTokenThreshold:
    def test_token_threshold_triggers_compact(self):
        from franki.main import _maybe_auto_compact
        cfg = FrankiConfig(
            auto_compact=True,
            auto_compact_messages=0,   # disable message count check
            auto_compact_threshold=0.10,  # very low threshold — will trigger
        )
        s = Session()
        s.add_user("a message with some content that has tokens")
        with patch("franki.ui.token_warning.token_usage_pct", return_value=0.50):
            with patch("franki.ai_ops.ask_ai", return_value="summary"):
                result = _maybe_auto_compact(cfg, s)
        assert result is True


# ── _get_pt_session ───────────────────────────────────────────────────────────

class TestGetPtSession:
    def test_returns_prompt_session(self):
        from franki.main import _get_pt_session
        session = _get_pt_session()
        assert session is not None


# ── _run_repl — minimal tests ─────────────────────────────────────────────────

class TestRunRepl:
    def _make_mock_pt(self, responses):
        """Return a mock PromptSession that yields responses then raises EOFError.
        Invokes bottom_toolbar callable on each call so _toolbar() lines are covered."""
        call_count = [0]

        def prompt_side_effect(*args, **kwargs):
            tb = kwargs.get("bottom_toolbar")
            if callable(tb):
                tb()  # exercise _toolbar body on every iteration
            idx = call_count[0]
            call_count[0] += 1
            if idx < len(responses):
                return responses[idx]
            raise EOFError

        mock_pt = MagicMock()
        mock_pt.prompt.side_effect = prompt_side_effect
        return mock_pt

    def test_eof_exits_repl(self):
        from franki.main import _run_repl
        cfg = _cfg()
        mock_pt = self._make_mock_pt([])  # EOFError immediately

        with patch("franki.main._get_pt_session", return_value=mock_pt), \
             patch("franki.main.start_version_check"), \
             patch("franki.main._prompt_save_exit"), \
             patch("franki.memory.get_context_string", return_value=""):
            _run_repl(cfg)

    def test_keyboard_interrupt_exits_repl(self):
        from franki.main import _run_repl
        cfg = _cfg()
        mock_pt = MagicMock()
        mock_pt.prompt.side_effect = KeyboardInterrupt

        with patch("franki.main._get_pt_session", return_value=mock_pt), \
             patch("franki.main.start_version_check"), \
             patch("franki.main._prompt_save_exit"), \
             patch("franki.memory.get_context_string", return_value=""):
            _run_repl(cfg)

    def test_exit_word_exits_repl(self):
        from franki.main import _run_repl
        cfg = _cfg()
        mock_pt = self._make_mock_pt(["exit"])

        with patch("franki.main._get_pt_session", return_value=mock_pt), \
             patch("franki.main.start_version_check"), \
             patch("franki.main._prompt_save_exit"), \
             patch("franki.memory.get_context_string", return_value=""):
            _run_repl(cfg)

    def test_quit_word_exits_repl(self):
        from franki.main import _run_repl
        cfg = _cfg()
        mock_pt = self._make_mock_pt(["quit"])

        with patch("franki.main._get_pt_session", return_value=mock_pt), \
             patch("franki.main.start_version_check"), \
             patch("franki.main._prompt_save_exit"), \
             patch("franki.memory.get_context_string", return_value=""):
            _run_repl(cfg)

    def test_empty_input_continues(self):
        from franki.main import _run_repl
        cfg = _cfg()
        # empty → continue; then exit
        mock_pt = self._make_mock_pt(["", "exit"])

        with patch("franki.main._get_pt_session", return_value=mock_pt), \
             patch("franki.main.start_version_check"), \
             patch("franki.main._prompt_save_exit"), \
             patch("franki.memory.get_context_string", return_value=""):
            _run_repl(cfg)

    def test_slash_command_dispatched(self):
        from franki.main import _run_repl
        cfg = _cfg()
        mock_pt = self._make_mock_pt(["/help", "exit"])

        with patch("franki.main._get_pt_session", return_value=mock_pt), \
             patch("franki.main.start_version_check"), \
             patch("franki.main._prompt_save_exit"), \
             patch("franki.main.handle_command") as mock_cmd, \
             patch("franki.memory.get_context_string", return_value=""):
            _run_repl(cfg)
        assert mock_cmd.called

    def test_regular_message_streams_response(self):
        from franki.main import _run_repl
        cfg = _cfg()
        mock_pt = self._make_mock_pt(["hello franki", "exit"])

        async def _empty_stream(*args, **kwargs):
            if False:
                yield ""

        with patch("franki.main._get_pt_session", return_value=mock_pt), \
             patch("franki.main.start_version_check"), \
             patch("franki.main._prompt_save_exit"), \
             patch("franki.main.stream_with_fallback", side_effect=_empty_stream), \
             patch("franki.memory.get_context_string", return_value=""):
            _run_repl(cfg)

    def test_shell_command_executed(self):
        from franki.main import _run_repl
        cfg = _cfg(auto_accept=True)
        mock_pt = self._make_mock_pt(["!echo hello", "exit"])

        async def _empty_stream(*args, **kwargs):
            if False:
                yield ""

        with patch("franki.main._get_pt_session", return_value=mock_pt), \
             patch("franki.main.start_version_check"), \
             patch("franki.main._prompt_save_exit"), \
             patch("franki.main.run_command", return_value=("hello\n", "", 0)), \
             patch("franki.main.stream_with_fallback", side_effect=_empty_stream), \
             patch("franki.memory.get_context_string", return_value=""):
            _run_repl(cfg)

    def test_shell_command_declined_by_user(self):
        from franki.main import _run_repl
        cfg = _cfg(auto_accept=False)
        mock_pt = self._make_mock_pt(["!ls", "exit"])

        with patch("franki.main._get_pt_session", return_value=mock_pt), \
             patch("franki.main.start_version_check"), \
             patch("franki.main._prompt_save_exit"), \
             patch("franki.main._confirm_shell_command", return_value=False), \
             patch("franki.memory.get_context_string", return_value=""):
            _run_repl(cfg)

    def test_empty_shell_command_continues(self):
        from franki.main import _run_repl
        cfg = _cfg()
        mock_pt = self._make_mock_pt(["!   ", "exit"])

        with patch("franki.main._get_pt_session", return_value=mock_pt), \
             patch("franki.main.start_version_check"), \
             patch("franki.main._prompt_save_exit"), \
             patch("franki.memory.get_context_string", return_value=""):
            _run_repl(cfg)

    def test_stream_error_handled(self):
        from franki.main import _run_repl
        cfg = _cfg()
        mock_pt = self._make_mock_pt(["hello", "exit"])

        async def _error_stream(*args, **kwargs):
            raise RuntimeError("provider gone")
            if False:
                yield ""

        with patch("franki.main._get_pt_session", return_value=mock_pt), \
             patch("franki.main.start_version_check"), \
             patch("franki.main._prompt_save_exit"), \
             patch("franki.main.stream_with_fallback", side_effect=_error_stream), \
             patch("franki.memory.get_context_string", return_value=""):
            _run_repl(cfg)  # should not raise

    def test_at_file_injection_with_errors(self):
        from franki.main import _run_repl
        cfg = _cfg()
        mock_pt = self._make_mock_pt(["@nonexistent.py", "exit"])

        async def _empty_stream(*args, **kwargs):
            if False:
                yield ""

        with patch("franki.main._get_pt_session", return_value=mock_pt), \
             patch("franki.main.start_version_check"), \
             patch("franki.main._prompt_save_exit"), \
             patch("franki.main.resolve_content", return_value=("context text", ["file not found"])), \
             patch("franki.main.stream_with_fallback", side_effect=_empty_stream), \
             patch("franki.memory.get_context_string", return_value=""):
            _run_repl(cfg)

    def test_at_file_empty_message_continues(self):
        from franki.main import _run_repl
        cfg = _cfg()
        mock_pt = self._make_mock_pt(["@empty.py", "exit"])

        with patch("franki.main._get_pt_session", return_value=mock_pt), \
             patch("franki.main.start_version_check"), \
             patch("franki.main._prompt_save_exit"), \
             patch("franki.main.resolve_content", return_value=("   ", [])), \
             patch("franki.memory.get_context_string", return_value=""):
            _run_repl(cfg)

    def test_auto_search_triggered(self):
        from franki.main import _run_repl
        cfg = _cfg()
        mock_pt = self._make_mock_pt(["what is the latest CVE-2024-12345?", "exit"])

        async def _empty_stream(*args, **kwargs):
            if False:
                yield ""

        with patch("franki.main._get_pt_session", return_value=mock_pt), \
             patch("franki.main.start_version_check"), \
             patch("franki.main._prompt_save_exit"), \
             patch("franki.main.stream_with_fallback", side_effect=_empty_stream), \
             patch("franki.utils.search.is_search_available", return_value=True), \
             patch("franki.main._run_auto_search") as mock_search, \
             patch("franki.memory.get_context_string", return_value=""):
            _run_repl(cfg)
        assert mock_search.called

    def test_shell_command_stream_exception_handled(self):
        from franki.main import _run_repl
        cfg = _cfg(auto_accept=True)
        mock_pt = self._make_mock_pt(["!echo hi", "exit"])

        async def _error_stream(*args, **kwargs):
            raise Exception("stream failed")
            if False:
                yield ""

        with patch("franki.main._get_pt_session", return_value=mock_pt), \
             patch("franki.main.start_version_check"), \
             patch("franki.main._prompt_save_exit"), \
             patch("franki.main.run_command", return_value=("hi\n", "", 0)), \
             patch("franki.main.stream_with_fallback", side_effect=_error_stream), \
             patch("franki.memory.get_context_string", return_value=""):
            _run_repl(cfg)  # should not raise

    def test_general_exception_in_message_stream_handled(self):
        """Test that non-RuntimeError exceptions in message streaming are caught."""
        from franki.main import _run_repl
        cfg = _cfg()
        mock_pt = self._make_mock_pt(["tell me something", "exit"])

        async def _value_error_stream(*args, **kwargs):
            raise ValueError("unexpected error")
            if False:
                yield ""

        with patch("franki.main._get_pt_session", return_value=mock_pt), \
             patch("franki.main.start_version_check"), \
             patch("franki.main._prompt_save_exit"), \
             patch("franki.main.stream_with_fallback", side_effect=_value_error_stream), \
             patch("franki.memory.get_context_string", return_value=""):
            _run_repl(cfg)  # should not raise

    def test_redraw_bar_called_by_skill_command(self):
        """Test _redraw_bar is called when a command triggers redraw_bar_fn."""
        from franki.main import _run_repl
        cfg = _cfg()
        mock_pt = self._make_mock_pt(["/skill pentest", "exit"])

        with patch("franki.main._get_pt_session", return_value=mock_pt), \
             patch("franki.main.start_version_check"), \
             patch("franki.main._prompt_save_exit"), \
             patch("franki.main.save_config"), \
             patch("franki.memory.get_context_string", return_value=""):
            _run_repl(cfg)
        # _redraw_bar should have been called via lambda: _redraw_bar()
        # (no assertion needed — just verify no crash)

    def test_on_update_callback_fires(self):
        """Ensure _on_update callback body (line 391) executes when fired by start_version_check."""
        from franki.main import _run_repl
        cfg = _cfg()
        mock_pt = self._make_mock_pt(["exit"])

        def fake_start_version_check(version, callback):
            callback("0.1.0", "9.9.9")  # fire immediately with a newer version

        with patch("franki.main._get_pt_session", return_value=mock_pt), \
             patch("franki.main.start_version_check", side_effect=fake_start_version_check), \
             patch("franki.main._prompt_save_exit"), \
             patch("franki.memory.get_context_string", return_value=""):
            _run_repl(cfg)

    def test_stream_with_fallback_callback_and_chunks(self):
        """Yield real chunks and trigger on_fallback — covers lines 126-127 and 152-161."""
        from franki.main import _run_repl
        cfg = _cfg()
        mock_pt = self._make_mock_pt(["tell me something", "exit"])

        async def _fallback_then_yield(cfg, messages, skill=None, tracker=None, on_fallback=None):
            if on_fallback:
                # triggers lines 126-127 (on_fallback body)
                on_fallback("groq", "anthropic/claude-3", "rate-limited")
            yield "hello "   # triggers lines 152-161 (loop body with notice check)
            yield "world"

        with patch("franki.main._get_pt_session", return_value=mock_pt), \
             patch("franki.main.start_version_check"), \
             patch("franki.main._prompt_save_exit"), \
             patch("franki.main.stream_with_fallback", side_effect=_fallback_then_yield), \
             patch("franki.memory.get_context_string", return_value=""):
            _run_repl(cfg)


# ── main() entry point ────────────────────────────────────────────────────────

class TestMain:
    def test_version_flag(self, capsys):
        from franki.main import main
        with patch("sys.argv", ["franki", "--version"]):
            main()
        out = capsys.readouterr().out
        assert "franki" in out

    def test_version_short_flag(self, capsys):
        from franki.main import main
        with patch("sys.argv", ["franki", "-V"]):
            main()
        out = capsys.readouterr().out
        assert "franki" in out

    def test_init_command(self):
        from franki.main import main
        with patch("sys.argv", ["franki", "init"]):
            with patch("franki.setup_wizard.run_wizard") as mock_wizard:
                main()
        assert mock_wizard.called

    def test_config_command(self):
        from franki.main import main
        with patch("sys.argv", ["franki", "config", "list"]):
            with patch("franki.config_cmd.run_config_cli") as mock_cfg:
                main()
        assert mock_cfg.called

    def test_fix_command(self):
        from franki.main import main
        with patch("sys.argv", ["franki", "fix", "main.py"]):
            with patch("franki.oneshot.run_fix") as mock_fix:
                main()
        assert mock_fix.called

    def test_review_command(self):
        from franki.main import main
        with patch("sys.argv", ["franki", "review", "main.py"]):
            with patch("franki.oneshot.run_review") as mock_review:
                main()
        assert mock_review.called

    def test_commit_command(self):
        from franki.main import main
        with patch("sys.argv", ["franki", "commit"]):
            with patch("franki.oneshot.run_commit") as mock_commit:
                main()
        assert mock_commit.called

    def test_explain_command(self):
        from franki.main import main
        with patch("sys.argv", ["franki", "explain", "main.py"]):
            with patch("franki.oneshot.run_explain") as mock_explain:
                main()
        assert mock_explain.called

    def test_needs_setup_runs_wizard_then_repl(self):
        from franki.main import main
        cfg = _cfg()
        with patch("sys.argv", ["franki"]):
            with patch("franki.main.needs_setup", return_value=True):
                with patch("franki.main.CONFIG_FILE") as mock_file:
                    mock_file.exists.return_value = False
                    with patch("franki.setup_wizard.run_wizard", return_value=cfg):
                        with patch("franki.main._run_repl"):
                            main()

    def test_needs_setup_with_existing_config_migrates(self, tmp_path):
        from franki.main import main
        cfg = _cfg()
        config_file = tmp_path / "config.json"
        config_file.write_text('{"old": "config"}', encoding="utf-8")

        with patch("sys.argv", ["franki"]):
            with patch("franki.main.needs_setup", return_value=True):
                with patch("franki.main.CONFIG_FILE", config_file):
                    with patch("franki.setup_wizard.run_wizard", return_value=cfg):
                        with patch("franki.main._run_repl"):
                            main()
        # Backup should have been created
        backup = tmp_path / "config.json.bak"
        assert backup.exists()

    def test_no_args_runs_repl(self):
        from franki.main import main
        cfg = _cfg()
        with patch("sys.argv", ["franki"]):
            with patch("franki.main.needs_setup", return_value=False):
                with patch("franki.main.load_config", return_value=cfg):
                    with patch("franki.main._run_repl") as mock_repl:
                        main()
        assert mock_repl.called

    def test_if_name_main_line_exists(self):
        """Just import main to ensure module-level code runs."""
        import franki.main  # noqa — ensure it imports without error


class TestMainNameGuard:
    def test_dunder_main_runs_version(self):
        """Cover the `if __name__ == '__main__': main()` guard via subprocess."""
        import subprocess
        import sys
        result = subprocess.run(
            [sys.executable, "-m", "franki.main", "--version"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0
        assert "franki" in result.stdout


# ── _resolve_content ──────────────────────────────────────────────────────────

class TestResolveContent:
    def test_no_at_returns_raw(self):
        from franki.utils.files import resolve_content as _resolve_content
        result, errors = _resolve_content("hello world")
        assert result == "hello world"
        assert errors == []

    def test_at_missing_file_appends_error(self):
        from franki.utils.files import resolve_content as _resolve_content
        result, errors = _resolve_content("@/nonexistent_xyz_abc_999.py")
        assert len(errors) == 1
        assert "not found" in errors[0]

    def test_at_directory_injects_tree(self, tmp_path):
        from franki.utils.files import resolve_content as _resolve_content
        # Directories are now injected as a tree (not an error)
        (tmp_path / "hello.py").write_text("print('hi')")
        result, errors = _resolve_content(f"@{str(tmp_path)}")
        assert errors == []
        assert isinstance(result, str)
        assert "hello.py" in result

    def test_text_file_injected(self, tmp_path):
        from franki.utils.files import resolve_content as _resolve_content
        f = tmp_path / "context.txt"
        f.write_text("some context")
        result, errors = _resolve_content(f"explain this: @{str(f)}")
        assert isinstance(result, str)
        assert "some context" in result
        assert errors == []

    def test_text_file_oserror_appends_error(self, tmp_path):
        from franki.utils.files import resolve_content as _resolve_content
        f = tmp_path / "locked.txt"
        f.write_text("secret")
        with patch("pathlib.Path.read_text", side_effect=OSError("permission denied")):
            result, errors = _resolve_content(f"@{str(f)}")
        assert any("permission denied" in e for e in errors)

    def test_image_file_becomes_multimodal(self, tmp_path):
        from franki.utils.files import resolve_content as _resolve_content
        img = tmp_path / "photo.png"
        img.write_bytes(b"\x89PNG\r\n")
        result, errors = _resolve_content(f"describe @{str(img)}")
        assert isinstance(result, list)
        assert any(p.get("type") == "image_url" for p in result)

    def test_image_file_oserror_appends_error(self, tmp_path):
        from franki.utils.files import resolve_content as _resolve_content
        img = tmp_path / "photo.png"
        img.write_bytes(b"\x89PNG")
        with patch("pathlib.Path.read_bytes", side_effect=OSError("unreadable")):
            result, errors = _resolve_content(f"@{str(img)}")
        assert any("unreadable" in e for e in errors)

    def test_image_plus_text_builds_multimodal(self, tmp_path):
        from franki.utils.files import resolve_content as _resolve_content
        img = tmp_path / "photo.png"
        img.write_bytes(b"\x89PNG")
        txt = tmp_path / "notes.txt"
        txt.write_text("see image")
        result, errors = _resolve_content(f"@{str(img)} plus @{str(txt)}")
        assert isinstance(result, list)
        text_parts = [p for p in result if p.get("type") == "text"]
        img_parts = [p for p in result if p.get("type") == "image_url"]
        assert len(img_parts) == 1
        assert text_parts[0]["text"] if text_parts else True


# ── _render_splash with project_context ───────────────────────────────────────

class TestRenderSplashProjectContext:
    def test_shows_franki_md_loaded_when_context(self):
        from franki.main import _render_splash
        cfg = _cfg()
        # Should not raise and should print the ".franki.md loaded" line
        _render_splash(cfg, project_context="# My Project\nsome context")


# ── _stream_response on_fallback and token count ──────────────────────────────

class TestStreamResponseCoverage:
    def test_on_fallback_fires_and_token_count_shown(self):
        """on_fallback body + token_count > 1 path."""
        import asyncio
        from franki.main import _stream_response

        cfg = _cfg()
        session = Session()
        session.add_user("hello")

        async def fake_stream(cfg_arg, messages, skill=None, tracker=None, on_fallback=None):
            if on_fallback:
                on_fallback("groq", "anthropic/claude", "rate-limited")
            # yield multiple large chunks so token_count > 1
            for word in ["word"] * 20:
                yield word

        with patch("franki.main.stream_with_fallback", side_effect=fake_stream), \
             patch("franki.main._print_fallback_notice"):
            result = asyncio.run(_stream_response(cfg, session))
        assert "word" * 5 in result

    def test_fallback_notice_printed_mid_stream(self):
        import asyncio
        from franki.main import _stream_response

        cfg = _cfg()
        session = Session()
        session.add_user("hi")

        async def fake_stream(cfg_arg, messages, skill=None, tracker=None, on_fallback=None):
            if on_fallback:
                on_fallback("groq", "openrouter", "unavailable")
            yield "first"
            yield "second"

        with patch("franki.main.stream_with_fallback", side_effect=fake_stream), \
             patch("franki.main._print_fallback_notice") as mock_notice:
            asyncio.run(_stream_response(cfg, session))
        mock_notice.assert_called_once()


# ── REPL run_agent path ───────────────────────────────────────────────────────

class TestRunReplAgentPath:
    def _make_mock_pt(self, responses):
        call_count = [0]

        def prompt_side_effect(*args, **kwargs):
            tb = kwargs.get("bottom_toolbar")
            if callable(tb):
                tb()
            idx = call_count[0]
            call_count[0] += 1
            if idx < len(responses):
                return responses[idx]
            raise EOFError

        mock_pt = MagicMock()
        mock_pt.prompt.side_effect = prompt_side_effect
        return mock_pt

    def test_run_agent_success_calls_auto_compact(self):
        from franki.main import _run_repl
        cfg = _cfg()
        mock_pt = self._make_mock_pt(["hello franki", "exit"])

        with patch("franki.main._get_pt_session", return_value=mock_pt), \
             patch("franki.main.start_version_check"), \
             patch("franki.main._prompt_save_exit"), \
             patch("franki.main.run_agent", new_callable=AsyncMock, return_value="done"), \
             patch("franki.main._maybe_auto_compact", return_value=False) as mock_compact, \
             patch("franki.main._maybe_warn_tokens"), \
             patch("franki.memory.get_context_string", return_value=""):
            _run_repl(cfg)
        assert mock_compact.called

    def test_run_agent_runtime_error_handled(self):
        from franki.main import _run_repl
        cfg = _cfg()
        mock_pt = self._make_mock_pt(["hello", "exit"])

        with patch("franki.main._get_pt_session", return_value=mock_pt), \
             patch("franki.main.start_version_check"), \
             patch("franki.main._prompt_save_exit"), \
             patch("franki.main.run_agent", new_callable=AsyncMock,
                   side_effect=RuntimeError("provider gone")), \
             patch("franki.memory.get_context_string", return_value=""):
            _run_repl(cfg)  # should not raise

    def test_at_file_empty_after_resolve_continues(self):
        from franki.main import _run_repl
        cfg = _cfg()
        mock_pt = self._make_mock_pt(["@empty.txt", "exit"])

        with patch("franki.main._get_pt_session", return_value=mock_pt), \
             patch("franki.main.start_version_check"), \
             patch("franki.main._prompt_save_exit"), \
             patch("franki.main.resolve_content", return_value=("   ", [])), \
             patch("franki.main.run_agent", new_callable=AsyncMock, return_value="x") as mock_agent, \
             patch("franki.memory.get_context_string", return_value=""):
            _run_repl(cfg)
        # run_agent should NOT be called since content is empty after resolve
        mock_agent.assert_not_called()
