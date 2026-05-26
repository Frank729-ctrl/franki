"""Tests for @clipboard injection, auto-copy, and agent cost recording."""
from unittest.mock import patch, MagicMock
import pytest


# ── @clipboard injection ──────────────────────────────────────────────────────

class TestClipboardInjection:
    def test_injects_clipboard_text(self):
        from franki.utils.files import resolve_content
        with patch("pyperclip.paste", return_value="some copied text"):
            result, errors = resolve_content("@clipboard")
        assert errors == []
        assert "some copied text" in result

    def test_clipboard_header_in_block(self):
        from franki.utils.files import resolve_content
        with patch("pyperclip.paste", return_value="hello"):
            result, errors = resolve_content("@clipboard")
        assert "[clipboard]" in result

    def test_empty_clipboard_returns_error(self):
        from franki.utils.files import resolve_content
        with patch("pyperclip.paste", return_value=""):
            result, errors = resolve_content("@clipboard")
        assert len(errors) == 1
        assert "empty" in errors[0]

    def test_whitespace_only_clipboard_returns_error(self):
        from franki.utils.files import resolve_content
        with patch("pyperclip.paste", return_value="   \n  "):
            result, errors = resolve_content("@clipboard")
        assert len(errors) == 1

    def test_large_clipboard_truncated(self):
        from franki.utils.files import resolve_content, _CLIPBOARD_MAX
        with patch("pyperclip.paste", return_value="x" * (_CLIPBOARD_MAX + 500)):
            result, errors = resolve_content("@clipboard")
        assert errors == []
        assert "truncated" in result

    def test_token_removed_from_message(self):
        from franki.utils.files import resolve_content
        with patch("pyperclip.paste", return_value="copied content"):
            result, errors = resolve_content("check this @clipboard for me")
        assert "@clipboard" not in result
        assert "check this" in result or "for me" in result

    def test_case_insensitive(self):
        from franki.utils.files import resolve_content
        with patch("pyperclip.paste", return_value="data"):
            result, errors = resolve_content("@CLIPBOARD")
        assert errors == []
        assert "data" in result

    def test_pyperclip_error_returns_error(self):
        from franki.utils.files import resolve_content
        with patch("pyperclip.paste", side_effect=Exception("no display")):
            result, errors = resolve_content("@clipboard")
        assert len(errors) == 1
        assert "clipboard" in errors[0].lower()

    def test_missing_pyperclip_returns_error(self):
        from franki.utils.files import _inject_clipboard
        import sys
        with patch.dict(sys.modules, {"pyperclip": None}):
            block, err = _inject_clipboard()
        assert err  # some error message


# ── Auto-copy + cost hint ─────────────────────────────────────────────────────

class TestAutoCopy:
    def test_copies_when_auto_copy_on(self):
        from franki.agent.loop import _auto_copy
        from io import StringIO
        from rich.console import Console
        c = Console(file=StringIO(), highlight=False, width=80)
        copied = []
        with patch("pyperclip.copy", side_effect=lambda t: copied.append(t)):
            _auto_copy(c, "hello world", None, auto_copy=True)
        assert len(copied) == 1
        assert "hello world" in copied[0]

    def test_does_not_copy_when_auto_copy_off(self):
        from franki.agent.loop import _auto_copy
        from io import StringIO
        from rich.console import Console
        c = Console(file=StringIO(), highlight=False, width=80)
        copied = []
        with patch("pyperclip.copy", side_effect=lambda t: copied.append(t)):
            _auto_copy(c, "response text", None, auto_copy=False)
        assert len(copied) == 0

    def test_shows_copied_hint_only_when_on(self):
        from franki.agent.loop import _auto_copy
        from io import StringIO
        from rich.console import Console
        c = Console(file=StringIO(), highlight=False, width=80)
        with patch("pyperclip.copy"):
            _auto_copy(c, "response text", None, auto_copy=True)
        assert "copied" in c.file.getvalue()

    def test_no_copied_hint_when_off(self):
        from franki.agent.loop import _auto_copy
        from io import StringIO
        from rich.console import Console
        c = Console(file=StringIO(), highlight=False, width=80)
        with patch("pyperclip.copy"):
            _auto_copy(c, "response text", None, auto_copy=False)
        assert "copied" not in c.file.getvalue()

    def test_shows_token_count_when_cost_tracker_has_data(self):
        from franki.agent.loop import _auto_copy
        from franki.cost_tracker import CostTracker
        from io import StringIO
        from rich.console import Console
        ct = CostTracker()
        ct.record("groq", "llama", 100, 50, {"cost_per_1m_input": 0.05, "cost_per_1m_output": 0.08}, 1.0)
        c = Console(file=StringIO(), highlight=False, width=80)
        with patch("pyperclip.copy"):
            _auto_copy(c, "test", ct)
        out = c.file.getvalue()
        assert "t" in out  # token count

    def test_pyperclip_failure_still_shows_tokens(self):
        from franki.agent.loop import _auto_copy
        from franki.cost_tracker import CostTracker
        from io import StringIO
        from rich.console import Console
        ct = CostTracker()
        ct.record("groq", "llama", 200, 100, {"cost_per_1m_input": 0.0, "cost_per_1m_output": 0.0}, 1.0)
        c = Console(file=StringIO(), highlight=False, width=80)
        with patch("pyperclip.copy", side_effect=Exception("no clipboard")):
            _auto_copy(c, "test", ct, auto_copy=True)
        out = c.file.getvalue()
        assert "t" in out  # token count still shown

    def test_no_output_when_no_data(self):
        from franki.agent.loop import _auto_copy
        from io import StringIO
        from rich.console import Console
        c = Console(file=StringIO(), highlight=False, width=80)
        with patch("pyperclip.copy", side_effect=Exception("no clipboard")):
            _auto_copy(c, "test", None, auto_copy=False)
        assert c.file.getvalue().strip() == ""


# ── Cost recording in agent loop ─────────────────────────────────────────────

class TestAgentCostRecording:
    def test_cost_recorded_after_agent_call(self):
        import asyncio
        from franki.agent.loop import _stream_and_assemble
        from franki.cost_tracker import CostTracker

        ct = CostTracker()
        msgs = [{"role": "user", "content": "hello"}]

        async def _fake_stream(*args, **kwargs):
            yield "text", "hi there"
            yield "done", "[]"

        with patch("franki.agent.loop.stream_chat_with_tools", side_effect=_fake_stream):
            asyncio.run(_stream_and_assemble(
                "key", "model", msgs, "https://api.example.com", "groq",
                console=None, cost_tracker=ct,
                pdata={"cost_per_1m_input": 0.05, "cost_per_1m_output": 0.08},
            ))

        assert ct.total_calls() == 1
        assert ct.total_tokens() > 0

    def test_no_cost_tracker_doesnt_crash(self):
        import asyncio
        from franki.agent.loop import _stream_and_assemble

        msgs = [{"role": "user", "content": "hello"}]

        async def _fake_stream(*args, **kwargs):
            yield "text", "hi"
            yield "done", "[]"

        with patch("franki.agent.loop.stream_chat_with_tools", side_effect=_fake_stream):
            result = asyncio.run(_stream_and_assemble(
                "key", "model", msgs, "https://api.example.com", "groq",
                console=None, cost_tracker=None,
            ))
        assert result["content"] == "hi"


# ── MCP tool schemas ──────────────────────────────────────────────────────────

class TestMCPToolSchemas:
    def setup_method(self):
        from franki.agent.tools import register_mcp_clients
        register_mcp_clients({})

    def teardown_method(self):
        from franki.agent.tools import register_mcp_clients
        register_mcp_clients({})

    def test_no_mcp_clients_no_extra_schemas(self):
        from franki.agent.tools import get_mcp_tool_schemas
        assert get_mcp_tool_schemas() == []

    def test_registered_client_adds_schemas(self):
        from franki.agent.tools import register_mcp_clients, get_mcp_tool_schemas
        mock_client = MagicMock()
        mock_client.get_tools.return_value = [
            {"name": "read_db", "description": "Read from DB", "inputSchema": {
                "type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]
            }}
        ]
        register_mcp_clients({"myserver": mock_client})
        schemas = get_mcp_tool_schemas()
        assert len(schemas) == 1
        assert schemas[0]["function"]["name"] == "mcp_myserver__read_db"

    def test_schema_name_prefixed_with_server(self):
        from franki.agent.tools import register_mcp_clients, get_mcp_tool_schemas
        mock_client = MagicMock()
        mock_client.get_tools.return_value = [
            {"name": "search", "description": "Search", "inputSchema": {"type": "object", "properties": {}, "required": []}}
        ]
        register_mcp_clients({"db": mock_client})
        schemas = get_mcp_tool_schemas()
        assert schemas[0]["function"]["name"] == "mcp_db__search"

    def test_description_includes_server_name(self):
        from franki.agent.tools import register_mcp_clients, get_mcp_tool_schemas
        mock_client = MagicMock()
        mock_client.get_tools.return_value = [
            {"name": "tool", "description": "Does something", "inputSchema": {"type": "object", "properties": {}, "required": []}}
        ]
        register_mcp_clients({"mysvr": mock_client})
        schemas = get_mcp_tool_schemas()
        assert "mysvr" in schemas[0]["function"]["description"]

    def test_execute_mcp_tool_dispatches_correctly(self):
        from franki.agent.tools import register_mcp_clients, execute_tool
        mock_client = MagicMock()
        mock_client.call_tool.return_value = "result from mcp"
        register_mcp_clients({"srv": mock_client})
        result = execute_tool("mcp_srv__mytool", {"param": "value"})
        mock_client.call_tool.assert_called_once_with("mytool", {"param": "value"})
        assert result == "result from mcp"

    def test_missing_mcp_server_returns_error(self):
        from franki.agent.tools import execute_tool
        result = execute_tool("mcp_nonexistent__tool", {})
        assert "not running" in result or "error" in result.lower()
