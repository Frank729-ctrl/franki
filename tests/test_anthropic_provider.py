"""Tests for the Anthropic native API adapter."""
from __future__ import annotations
import json
import pytest


# ── Message conversion ────────────────────────────────────────────────────────

class TestConvertMessages:
    def _convert(self, messages):
        from franki.providers.anthropic import _convert_messages
        return _convert_messages(messages)

    def test_system_extracted(self):
        system, out = self._convert([
            {"role": "system", "content": "You are helpful."},
            {"role": "user", "content": "hello"},
        ])
        assert system == "You are helpful."
        assert len(out) == 1
        assert out[0]["role"] == "user"

    def test_multiple_system_joined(self):
        system, _ = self._convert([
            {"role": "system", "content": "Part A."},
            {"role": "system", "content": "Part B."},
            {"role": "user", "content": "hi"},
        ])
        assert "Part A." in system
        assert "Part B." in system

    def test_tool_result_becomes_user_block(self):
        _, out = self._convert([
            {"role": "user", "content": "do something"},
            {"role": "assistant", "content": "", "tool_calls": [
                {"id": "c1", "type": "function",
                 "function": {"name": "read_file", "arguments": '{"path":"f.py"}'}},
            ]},
            {"role": "tool", "tool_call_id": "c1", "content": "file content"},
        ])
        # Last message is user with tool_result block
        last = out[-1]
        assert last["role"] == "user"
        assert isinstance(last["content"], list)
        assert last["content"][0]["type"] == "tool_result"
        assert last["content"][0]["tool_use_id"] == "c1"

    def test_consecutive_tool_results_merged(self):
        _, out = self._convert([
            {"role": "user", "content": "go"},
            {"role": "assistant", "content": "", "tool_calls": [
                {"id": "c1", "type": "function",
                 "function": {"name": "read_file", "arguments": '{"path":"a"}'}},
                {"id": "c2", "type": "function",
                 "function": {"name": "read_file", "arguments": '{"path":"b"}'}},
            ]},
            {"role": "tool", "tool_call_id": "c1", "content": "content a"},
            {"role": "tool", "tool_call_id": "c2", "content": "content b"},
        ])
        # The two tool results should be in the same user message
        tool_msgs = [m for m in out if m["role"] == "user" and isinstance(m.get("content"), list)]
        assert len(tool_msgs) == 1
        assert len(tool_msgs[0]["content"]) == 2

    def test_assistant_tool_calls_converted(self):
        _, out = self._convert([
            {"role": "user", "content": "go"},
            {"role": "assistant", "content": "ok", "tool_calls": [
                {"id": "t1", "type": "function",
                 "function": {"name": "run_command", "arguments": '{"command":"ls"}'}},
            ]},
        ])
        asst = out[-1]
        assert asst["role"] == "assistant"
        assert isinstance(asst["content"], list)
        tool_use = next(b for b in asst["content"] if b["type"] == "tool_use")
        assert tool_use["id"] == "t1"
        assert tool_use["name"] == "run_command"
        assert tool_use["input"] == {"command": "ls"}

    def test_text_alongside_tool_calls_preserved(self):
        _, out = self._convert([
            {"role": "user", "content": "go"},
            {"role": "assistant", "content": "I will read the file", "tool_calls": [
                {"id": "t1", "type": "function",
                 "function": {"name": "read_file", "arguments": '{"path":"x"}'}},
            ]},
        ])
        asst = out[-1]
        text_blocks = [b for b in asst["content"] if b["type"] == "text"]
        assert any("I will" in b["text"] for b in text_blocks)

    def test_plain_user_message_passthrough(self):
        _, out = self._convert([{"role": "user", "content": "hello"}])
        assert out[0] == {"role": "user", "content": "hello"}

    def test_plain_assistant_message_passthrough(self):
        _, out = self._convert([
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "hello back"},
        ])
        assert out[-1] == {"role": "assistant", "content": "hello back"}


# ── Tool schema conversion ────────────────────────────────────────────────────

class TestConvertTools:
    def _convert(self, tools):
        from franki.providers.anthropic import _convert_tools
        return _convert_tools(tools)

    def test_function_tool_converted(self):
        tools = [{
            "type": "function",
            "function": {
                "name": "read_file",
                "description": "Read a file",
                "parameters": {
                    "type": "object",
                    "properties": {"path": {"type": "string"}},
                    "required": ["path"],
                },
            },
        }]
        result = self._convert(tools)
        assert len(result) == 1
        t = result[0]
        assert t["name"] == "read_file"
        assert t["description"] == "Read a file"
        assert "input_schema" in t
        assert t["input_schema"]["type"] == "object"

    def test_non_function_tools_skipped(self):
        result = self._convert([{"type": "other", "function": {}}])
        assert result == []

    def test_empty_list(self):
        assert self._convert([]) == []


# ── api_type routing ──────────────────────────────────────────────────────────

class TestApiTypeRouting:
    def test_openai_pdata_returns_generic(self):
        from franki.agent.loop import _get_stream_with_tools_fn
        from franki.providers.generic import stream_chat_with_tools
        fn = _get_stream_with_tools_fn({"api_type": "openai"})
        assert fn is stream_chat_with_tools

    def test_default_pdata_returns_generic(self):
        from franki.agent.loop import _get_stream_with_tools_fn
        from franki.providers.generic import stream_chat_with_tools
        fn = _get_stream_with_tools_fn({})
        assert fn is stream_chat_with_tools

    def test_anthropic_pdata_returns_anthropic(self):
        from franki.agent.loop import _get_stream_with_tools_fn
        from franki.providers.anthropic import stream_chat_with_tools as ant
        fn = _get_stream_with_tools_fn({"api_type": "anthropic"})
        assert fn is ant

    def test_router_openai_returns_generic(self):
        from franki.router import _get_stream_fn
        from franki.providers.generic import stream_chat
        fn = _get_stream_fn({})
        assert fn is stream_chat

    def test_router_anthropic_returns_anthropic(self):
        from franki.router import _get_stream_fn
        from franki.providers.anthropic import stream_chat as ant
        fn = _get_stream_fn({"api_type": "anthropic"})
        assert fn is ant


# ── Known providers ───────────────────────────────────────────────────────────

class TestKnownProviders:
    def test_anthropic_in_known_providers(self):
        from franki.config import KNOWN_PROVIDERS
        assert "anthropic" in KNOWN_PROVIDERS

    def test_anthropic_has_api_type(self):
        from franki.config import KNOWN_PROVIDERS
        assert KNOWN_PROVIDERS["anthropic"]["api_type"] == "anthropic"

    def test_anthropic_has_models(self):
        from franki.config import KNOWN_PROVIDERS
        models = KNOWN_PROVIDERS["anthropic"]["suggested_models"]
        assert any("claude" in m for m in models)
