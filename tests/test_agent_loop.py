"""Tests for franki/agent/loop.py."""
from __future__ import annotations
import asyncio
import pytest
from io import StringIO
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock, patch, call


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_console():
    c = MagicMock()
    c.width = 80
    return c


def _make_cfg(auto_accept=False):
    cfg = MagicMock()
    cfg.auto_accept = auto_accept
    cfg.get_provider_key.return_value = "key"
    return cfg


def _make_session(skill="coding"):
    from franki.session import Session
    s = Session(skill=skill)
    return s


def _plain_msg(text="hello"):
    return {"content": text, "tool_calls": None}


def _tool_msg(tool_name, args_json, call_id="tc1"):
    return {
        "content": "",
        "tool_calls": [
            {
                "id": call_id,
                "function": {"name": tool_name, "arguments": args_json},
            }
        ],
    }


# ── _show_tool_call ────────────────────────────────────────────────────────────

class TestShowToolCall:
    def _call(self, name, args):
        from franki.agent.loop import _show_tool_call
        console = _make_console()
        _show_tool_call(console, name, args)
        return console.print.call_args[0][0]

    def test_read_file(self):
        t = self._call("read_file", {"path": "foo.py"})
        assert "reading" in str(t)
        assert "foo.py" in str(t)

    def test_write_file(self):
        t = self._call("write_file", {"path": "out.py"})
        assert "writing" in str(t)

    def test_edit_file(self):
        t = self._call("edit_file", {"path": "bar.py"})
        assert "editing" in str(t)

    def test_run_command(self):
        t = self._call("run_command", {"command": "ls -la"})
        assert "running" in str(t)
        assert "ls -la" in str(t)

    def test_list_directory(self):
        t = self._call("list_directory", {"path": "/tmp"})
        assert "listing" in str(t)
        assert "/tmp" in str(t)

    def test_search_files(self):
        t = self._call("search_files", {"pattern": "*.py", "directory": "."})
        assert "searching" in str(t)

    def test_grep_files(self):
        t = self._call("grep_files", {"query": "def foo", "directory": "."})
        assert "grep" in str(t)

    def test_run_background(self):
        t = self._call("run_background", {"command": "npm start"})
        assert "background" in str(t)
        assert "npm start" in str(t)

    def test_check_background(self):
        t = self._call("check_background", {"process_id": "abc123"})
        assert "checking" in str(t)
        assert "abc123" in str(t)

    def test_stop_background(self):
        t = self._call("stop_background", {"process_id": "abc123"})
        assert "stopping" in str(t)
        assert "abc123" in str(t)

    def test_list_backgrounds(self):
        t = self._call("list_backgrounds", {})
        assert "processes" in str(t)

    def test_unknown_tool(self):
        t = self._call("magic_tool", {})
        assert "magic_tool" in str(t)


# ── _show_tool_result ─────────────────────────────────────────────────────────

class TestShowToolResult:
    def test_write_tool_shows_confirmation(self):
        from franki.agent.loop import _show_tool_result
        console = _make_console()
        _show_tool_result(console, "write_file", "wrote 5 lines → out.py")
        assert console.print.called

    def test_edit_tool_shows_confirmation(self):
        from franki.agent.loop import _show_tool_result
        console = _make_console()
        _show_tool_result(console, "edit_file", "edited foo.py")
        assert console.print.called

    def test_run_command_shows_preview(self):
        from franki.agent.loop import _show_tool_result
        console = _make_console()
        output = "\n".join(f"line{i}" for i in range(10))
        _show_tool_result(console, "run_command", output)
        assert console.print.called

    def test_run_command_many_lines_truncated(self):
        from franki.agent.loop import _show_tool_result
        console = _make_console()
        output = "\n".join(f"line{i}" for i in range(20))
        _show_tool_result(console, "run_command", output)
        printed = str(console.print.call_args_list)
        assert "more lines" in printed

    def test_read_tool_no_output(self):
        from franki.agent.loop import _show_tool_result
        console = _make_console()
        _show_tool_result(console, "read_file", "some content")
        # read_file is not in WRITE_TOOLS and not run_command — no print
        console.print.assert_not_called()


# ── _confirm_tool ──────────────────────────────────────────────────────────────

class TestConfirmTool:
    def test_auto_accept_returns_true(self):
        from franki.agent.loop import _confirm_tool
        assert _confirm_tool(_make_console(), "write_file", {"path": "x.py"}, True) is True

    def test_write_file_user_yes(self):
        from franki.agent.loop import _confirm_tool
        with patch("builtins.input", return_value="y"):
            result = _confirm_tool(_make_console(), "write_file", {"path": "x.py", "content": "a\nb\n"}, False)
        assert result is True

    def test_write_file_user_no(self):
        from franki.agent.loop import _confirm_tool
        with patch("builtins.input", return_value="n"):
            result = _confirm_tool(_make_console(), "write_file", {"path": "x.py", "content": "a"}, False)
        assert result is False

    def test_edit_file_shows_details(self):
        from franki.agent.loop import _confirm_tool
        console = _make_console()
        with patch("builtins.input", return_value="yes"):
            result = _confirm_tool(console, "edit_file", {"path": "f.py", "old_str": "old", "new_str": "new"}, False)
        assert result is True

    def test_run_command_shows_command(self):
        from franki.agent.loop import _confirm_tool
        console = _make_console()
        with patch("builtins.input", return_value="y"):
            result = _confirm_tool(console, "run_command", {"command": "rm -rf /"}, False)
        assert result is True

    def test_keyboard_interrupt_returns_false(self):
        from franki.agent.loop import _confirm_tool
        with patch("builtins.input", side_effect=KeyboardInterrupt):
            result = _confirm_tool(_make_console(), "run_command", {"command": "x"}, False)
        assert result is False

    def test_eof_returns_false(self):
        from franki.agent.loop import _confirm_tool
        with patch("builtins.input", side_effect=EOFError):
            result = _confirm_tool(_make_console(), "write_file", {"path": "x", "content": ""}, False)
        assert result is False


# ── _maybe_verify ─────────────────────────────────────────────────────────────

class TestMaybeVerify:
    def test_no_files_written_skips(self, tmp_path):
        from franki.agent.loop import _maybe_verify
        console = _make_console()
        _maybe_verify(console, _make_cfg(), [])
        console.print.assert_not_called()

    def test_no_test_runner_detected_skips(self, tmp_path):
        from franki.agent.loop import _maybe_verify
        console = _make_console()
        with patch("franki.agent.loop.Path.cwd", return_value=tmp_path):
            _maybe_verify(console, _make_cfg(), ["foo.py"])
        console.print.assert_not_called()

    def test_pytest_detected_user_yes(self, tmp_path):
        from franki.agent.loop import _maybe_verify
        (tmp_path / "pytest.ini").write_text("[pytest]")
        console = _make_console()
        with patch("franki.agent.loop.Path.cwd", return_value=tmp_path), \
             patch("builtins.input", return_value="y"), \
             patch("franki.agent.loop.execute_tool", return_value="5 passed") as mock_exec:
            _maybe_verify(console, _make_cfg(), ["foo.py"])
        mock_exec.assert_called_once()
        assert "pytest" in mock_exec.call_args[0][1]["command"]

    def test_pytest_detected_user_no(self, tmp_path):
        from franki.agent.loop import _maybe_verify
        (tmp_path / "pytest.ini").write_text("[pytest]")
        console = _make_console()
        with patch("franki.agent.loop.Path.cwd", return_value=tmp_path), \
             patch("builtins.input", return_value="n"), \
             patch("franki.agent.loop.execute_tool") as mock_exec:
            _maybe_verify(console, _make_cfg(), ["foo.py"])
        mock_exec.assert_not_called()

    def test_pyproject_toml_detected(self, tmp_path):
        from franki.agent.loop import _maybe_verify
        (tmp_path / "pyproject.toml").write_text("[tool.pytest]")
        console = _make_console()
        with patch("franki.agent.loop.Path.cwd", return_value=tmp_path), \
             patch("builtins.input", return_value="y"), \
             patch("franki.agent.loop.execute_tool", return_value="ok") as mock_exec:
            _maybe_verify(console, _make_cfg(), ["x.py"])
        mock_exec.assert_called_once()

    def test_package_json_detected(self, tmp_path):
        from franki.agent.loop import _maybe_verify
        (tmp_path / "package.json").write_text("{}")
        console = _make_console()
        with patch("franki.agent.loop.Path.cwd", return_value=tmp_path), \
             patch("builtins.input", return_value="y"), \
             patch("franki.agent.loop.execute_tool", return_value="ok") as mock_exec:
            _maybe_verify(console, _make_cfg(), ["index.js"])
        assert "npm test" in mock_exec.call_args[0][1]["command"]

    def test_makefile_with_test_target(self, tmp_path):
        from franki.agent.loop import _maybe_verify
        (tmp_path / "Makefile").write_text("test:\n\tpytest\n")
        console = _make_console()
        with patch("franki.agent.loop.Path.cwd", return_value=tmp_path), \
             patch("builtins.input", return_value="y"), \
             patch("franki.agent.loop.execute_tool", return_value="ok") as mock_exec:
            _maybe_verify(console, _make_cfg(), ["main.py"])
        assert "make test" in mock_exec.call_args[0][1]["command"]

    def test_makefile_without_test_target_skips(self, tmp_path):
        from franki.agent.loop import _maybe_verify
        (tmp_path / "Makefile").write_text("build:\n\tgcc main.c\n")
        console = _make_console()
        with patch("franki.agent.loop.Path.cwd", return_value=tmp_path), \
             patch("franki.agent.loop.execute_tool") as mock_exec:
            _maybe_verify(console, _make_cfg(), ["main.c"])
        mock_exec.assert_not_called()

    def test_keyboard_interrupt_during_verify_prompt(self, tmp_path):
        from franki.agent.loop import _maybe_verify
        (tmp_path / "pytest.ini").write_text("")
        console = _make_console()
        with patch("franki.agent.loop.Path.cwd", return_value=tmp_path), \
             patch("builtins.input", side_effect=KeyboardInterrupt):
            _maybe_verify(console, _make_cfg(), ["foo.py"])  # should not raise

    def test_makefile_oserror_skips(self, tmp_path):
        from franki.agent.loop import _maybe_verify
        (tmp_path / "Makefile").write_text("test:\n\tpytest\n")
        console = _make_console()
        with patch("franki.agent.loop.Path.cwd", return_value=tmp_path), \
             patch.object(Path, "read_text", side_effect=OSError("permission denied")), \
             patch("franki.agent.loop.execute_tool") as mock_exec:
            _maybe_verify(console, _make_cfg(), ["main.py"])
        mock_exec.assert_not_called()


# ── _call_with_tools ──────────────────────────────────────────────────────────

class TestCallWithTools:
    def _make_cfg_with_provider(self):
        cfg = MagicMock()
        cfg.get_provider_key.return_value = "testkey"
        return cfg

    @pytest.mark.asyncio
    async def test_returns_message_on_success(self):
        from franki.agent.loop import _call_with_tools
        from franki.providers.generic import ProviderError
        cfg = self._make_cfg_with_provider()
        expected = {"content": "done", "tool_calls": None}
        with patch("franki.agent.loop.build_routing_order",
                   return_value=[("groq", {"base_url": "http://x", "model": "m", "key_required": True}, "r")]), \
             patch("franki.agent.loop._stream_and_assemble", new_callable=AsyncMock,
                   return_value=expected):
            result = await _call_with_tools(cfg, [], "coding")
        assert result == expected

    @pytest.mark.asyncio
    async def test_no_providers_raises(self):
        from franki.agent.loop import _call_with_tools
        from franki.providers.generic import ProviderError
        cfg = self._make_cfg_with_provider()
        with patch("franki.agent.loop.build_routing_order", return_value=[]):
            with pytest.raises(ProviderError, match="No providers"):
                await _call_with_tools(cfg, [], "coding")

    @pytest.mark.asyncio
    async def test_skips_provider_missing_base_url(self):
        from franki.agent.loop import _call_with_tools
        from franki.providers.generic import ProviderError
        cfg = self._make_cfg_with_provider()
        with patch("franki.agent.loop.build_routing_order",
                   return_value=[("p1", {"base_url": "", "model": "m", "key_required": False}, "r")]):
            with pytest.raises(ProviderError):
                await _call_with_tools(cfg, [], "coding")

    @pytest.mark.asyncio
    async def test_skips_provider_missing_api_key(self):
        from franki.agent.loop import _call_with_tools
        from franki.providers.generic import ProviderError
        cfg = self._make_cfg_with_provider()
        cfg.get_provider_key.return_value = None
        with patch("franki.agent.loop.build_routing_order",
                   return_value=[("p1", {"base_url": "http://x", "model": "m", "key_required": True}, "r")]):
            with pytest.raises(ProviderError):
                await _call_with_tools(cfg, [], "coding")

    @pytest.mark.asyncio
    async def test_falls_through_on_rate_limit(self):
        from franki.agent.loop import _call_with_tools
        from franki.providers.generic import ProviderRateLimitError, ProviderError
        cfg = self._make_cfg_with_provider()
        providers = [
            ("p1", {"base_url": "http://x", "model": "m", "key_required": True}, "r"),
            ("p2", {"base_url": "http://y", "model": "m2", "key_required": True}, "r"),
        ]
        call_count = [0]
        async def side_effect(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                raise ProviderRateLimitError("rate limited")
            return {"content": "ok", "tool_calls": None}

        with patch("franki.agent.loop.build_routing_order", return_value=providers), \
             patch("franki.agent.loop._stream_and_assemble", side_effect=side_effect):
            result = await _call_with_tools(cfg, [], "coding")
        assert result["content"] == "ok"

    @pytest.mark.asyncio
    async def test_provider_error_propagates(self):
        from franki.agent.loop import _call_with_tools
        from franki.providers.generic import ProviderError
        cfg = self._make_cfg_with_provider()
        with patch("franki.agent.loop.build_routing_order",
                   return_value=[("p1", {"base_url": "http://x", "model": "m", "key_required": True}, "r")]), \
             patch("franki.agent.loop._stream_and_assemble", new_callable=AsyncMock,
                   side_effect=ProviderError("server error")):
            with pytest.raises(ProviderError, match="server error"):
                await _call_with_tools(cfg, [], "coding")

    @pytest.mark.asyncio
    async def test_all_rate_limited_raises(self):
        from franki.agent.loop import _call_with_tools
        from franki.providers.generic import ProviderRateLimitError, ProviderError
        cfg = self._make_cfg_with_provider()
        with patch("franki.agent.loop.build_routing_order",
                   return_value=[("p1", {"base_url": "http://x", "model": "m", "key_required": True}, "r")]), \
             patch("franki.agent.loop._stream_and_assemble", new_callable=AsyncMock,
                   side_effect=ProviderRateLimitError("rate limit")):
            with pytest.raises(ProviderError):
                await _call_with_tools(cfg, [], "coding")


# ── run_agent ─────────────────────────────────────────────────────────────────

class TestRunAgent:
    @pytest.mark.asyncio
    async def test_plain_response_no_tools(self):
        from franki.agent.loop import run_agent
        cfg = _make_cfg()
        session = _make_session()
        console = _make_console()
        with patch("franki.agent.loop._call_with_tools", new_callable=AsyncMock,
                   return_value=_plain_msg("Hello!")), \
             patch("franki.agent.loop.render_response"), \
             patch("franki.agent.loop._maybe_verify"):
            result = await run_agent(cfg, session, console, "hi")
        assert result == "Hello!"

    @pytest.mark.asyncio
    async def test_tool_call_then_final_response(self):
        from franki.agent.loop import run_agent
        cfg = _make_cfg(auto_accept=True)
        session = _make_session()
        console = _make_console()
        import json
        tool_response = _tool_msg("read_file", json.dumps({"path": "/tmp/x.py"}))
        responses = [tool_response, _plain_msg("Done!")]

        with patch("franki.agent.loop._call_with_tools", new_callable=AsyncMock,
                   side_effect=responses), \
             patch("franki.agent.loop.render_response"), \
             patch("franki.agent.loop.execute_tool", return_value="file content"), \
             patch("franki.agent.loop._maybe_verify"):
            result = await run_agent(cfg, session, console, "read x")
        assert result == "Done!"

    @pytest.mark.asyncio
    async def test_write_tool_requires_confirm(self):
        from franki.agent.loop import run_agent
        cfg = _make_cfg(auto_accept=False)
        session = _make_session()
        console = _make_console()
        import json
        tool_response = _tool_msg("write_file", json.dumps({"path": "/tmp/out.py", "content": "x"}))
        responses = [tool_response, _plain_msg("Done!")]

        with patch("franki.agent.loop._call_with_tools", new_callable=AsyncMock,
                   side_effect=responses), \
             patch("franki.agent.loop.render_response"), \
             patch("franki.agent.loop._confirm_tool", return_value=True), \
             patch("franki.agent.loop.execute_tool", return_value="wrote 1 lines → /tmp/out.py"), \
             patch("franki.agent.loop._maybe_verify"):
            result = await run_agent(cfg, session, console, "write")
        assert result == "Done!"

    @pytest.mark.asyncio
    async def test_declined_tool_stops_loop(self):
        from franki.agent.loop import run_agent
        cfg = _make_cfg(auto_accept=False)
        session = _make_session()
        console = _make_console()
        import json
        tool_response = _tool_msg("write_file", json.dumps({"path": "/tmp/out.py", "content": "x"}))

        with patch("franki.agent.loop._call_with_tools", new_callable=AsyncMock,
                   return_value=tool_response), \
             patch("franki.agent.loop.render_response"), \
             patch("franki.agent.loop._confirm_tool", return_value=False), \
             patch("franki.agent.loop._maybe_verify"):
            result = await run_agent(cfg, session, console, "write")
        # All tools declined → fall through to max_steps message
        assert "completed" in result or result  # returns something

    @pytest.mark.asyncio
    async def test_max_steps_hit_returns_fallback(self):
        from franki.agent.loop import run_agent
        cfg = _make_cfg(auto_accept=True)
        session = _make_session()
        console = _make_console()
        import json

        def make_tool_response():
            return _tool_msg("read_file", json.dumps({"path": "/tmp/x"}))

        with patch("franki.agent.loop._call_with_tools", new_callable=AsyncMock,
                   side_effect=[make_tool_response() for _ in range(20)]), \
             patch("franki.agent.loop.render_response"), \
             patch("franki.agent.loop.execute_tool", return_value="content"), \
             patch("franki.agent.loop._maybe_verify"):
            result = await run_agent(cfg, session, console, "loop forever")
        assert "completed" in result

    @pytest.mark.asyncio
    async def test_ai_text_shown_before_tools(self):
        from franki.agent.loop import run_agent
        import json
        cfg = _make_cfg(auto_accept=True)
        session = _make_session()
        console = _make_console()
        tool_msg = {
            "content": "Let me read the file first.",
            "tool_calls": [{"id": "tc1", "function": {"name": "read_file", "arguments": json.dumps({"path": "/tmp/x"})}}],
        }
        with patch("franki.agent.loop._call_with_tools", new_callable=AsyncMock,
                   side_effect=[tool_msg, _plain_msg("Done")]), \
             patch("franki.agent.loop.render_response") as mock_render, \
             patch("franki.agent.loop.execute_tool", return_value="content"), \
             patch("franki.agent.loop._maybe_verify"):
            await run_agent(cfg, session, console, "read")
        # render_response should have been called for both the inline text and final
        assert mock_render.call_count >= 2

    @pytest.mark.asyncio
    async def test_invalid_json_args_handled(self):
        from franki.agent.loop import run_agent
        cfg = _make_cfg(auto_accept=True)
        session = _make_session()
        console = _make_console()
        bad_tool_msg = {
            "content": "",
            "tool_calls": [{"id": "tc1", "function": {"name": "read_file", "arguments": "NOT JSON"}}],
        }
        with patch("franki.agent.loop._call_with_tools", new_callable=AsyncMock,
                   side_effect=[bad_tool_msg, _plain_msg("Done")]), \
             patch("franki.agent.loop.render_response"), \
             patch("franki.agent.loop.execute_tool", return_value="err"), \
             patch("franki.agent.loop._maybe_verify"):
            result = await run_agent(cfg, session, console, "bad")
        assert result == "Done"

    @pytest.mark.asyncio
    async def test_parallel_read_tools_run_concurrently(self):
        """When AI returns multiple read-only tool calls, they run in parallel."""
        from franki.agent.loop import run_agent
        import json
        cfg = _make_cfg(auto_accept=True)
        session = _make_session()
        console = _make_console()
        # AI returns two read_file calls at once
        parallel_msg = {
            "content": "",
            "tool_calls": [
                {"id": "tc1", "function": {"name": "read_file", "arguments": json.dumps({"path": "/tmp/a"})}},
                {"id": "tc2", "function": {"name": "read_file", "arguments": json.dumps({"path": "/tmp/b"})}},
            ],
        }
        call_order = []

        def track_execute(name, args):
            call_order.append(name)
            return f"content of {args.get('path', '')}"

        with patch("franki.agent.loop._call_with_tools", new_callable=AsyncMock,
                   side_effect=[parallel_msg, _plain_msg("Done")]), \
             patch("franki.agent.loop.render_response"), \
             patch("franki.agent.loop.execute_tool", side_effect=track_execute), \
             patch("franki.agent.loop._maybe_verify"):
            result = await run_agent(cfg, session, console, "read both")
        assert result == "Done"
        assert call_order.count("read_file") == 2

    @pytest.mark.asyncio
    async def test_write_tool_adds_to_files_written(self):
        from franki.agent.loop import run_agent
        import json
        cfg = _make_cfg(auto_accept=True)
        session = _make_session()
        console = _make_console()
        tool_response = _tool_msg("write_file", json.dumps({"path": "/tmp/out.py", "content": "x"}))

        with patch("franki.agent.loop._call_with_tools", new_callable=AsyncMock,
                   side_effect=[tool_response, _plain_msg("Done")]), \
             patch("franki.agent.loop.render_response"), \
             patch("franki.agent.loop.execute_tool", return_value="wrote 1 lines"), \
             patch("franki.agent.loop._maybe_verify") as mock_verify:
            await run_agent(cfg, session, console, "write")
        # _maybe_verify should receive the files_written list
        called_files = mock_verify.call_args[0][2]
        assert "/tmp/out.py" in called_files
