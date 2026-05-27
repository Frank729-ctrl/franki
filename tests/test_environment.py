"""Tests for the dynamic self-awareness environment block."""
from franki.config import FrankiConfig
import datetime


def _cfg(**kwargs) -> FrankiConfig:
    base = {
        "active_provider": "groq",
        "providers": {"groq": {
            "api_key": "sk-test",
            "base_url": "https://api.groq.com/openai/v1",
            "model": "llama-3.3-70b-versatile",
            "priority": 1,
        }},
    }
    base.update(kwargs)
    return FrankiConfig(**base)


class TestBuildEnvironmentBlock:
    def test_includes_version(self):
        from franki.environment import build_environment_block
        from franki import __version__
        block = build_environment_block(_cfg())
        assert __version__ in block

    def test_includes_today_date(self):
        from franki.environment import build_environment_block
        block = build_environment_block(_cfg())
        assert datetime.date.today().isoformat() in block

    def test_includes_working_directory(self):
        from franki.environment import build_environment_block
        import os
        block = build_environment_block(_cfg())
        assert os.getcwd() in block

    def test_includes_active_provider(self):
        from franki.environment import build_environment_block
        block = build_environment_block(_cfg())
        assert "groq" in block
        assert "llama-3.3-70b-versatile" in block

    def test_marks_active_provider(self):
        from franki.environment import build_environment_block
        block = build_environment_block(_cfg())
        # Active provider and model appear in the compact model: field
        assert "groq" in block
        assert "llama-3.3-70b-versatile" in block

    def test_includes_web_search(self):
        from franki.environment import build_environment_block
        block = build_environment_block(_cfg())
        assert "web_search" in block

    def test_includes_skills(self):
        from franki.environment import build_environment_block
        block = build_environment_block(_cfg())
        assert "coding" in block
        assert "pentest" in block
        assert "soc" in block

    def test_includes_auto_accept_when_on(self):
        from franki.environment import build_environment_block
        block = build_environment_block(_cfg(auto_accept=True))
        assert "auto-accept" in block
        # Not shown when off (saves tokens)
        block_off = build_environment_block(_cfg(auto_accept=False))
        assert "auto-accept" not in block_off

    def test_includes_mcp_tools_when_registered(self):
        from franki.environment import build_environment_block
        from franki.agent.tools import register_mcp_clients
        from unittest.mock import MagicMock
        mock = MagicMock()
        mock.get_tools.return_value = [
            {"name": "read_db", "description": "Query the database"}
        ]
        register_mcp_clients({"mydb": mock})
        try:
            block = build_environment_block(_cfg())
            assert "mydb" in block
            assert "read_db" in block
        finally:
            register_mcp_clients({})

    def test_includes_custom_tools_when_registered(self):
        from franki.environment import build_environment_block
        from franki.agent.tools import register_custom_tools
        register_custom_tools([{
            "name": "deploy", "description": "Deploy to production",
            "command": "make deploy", "params": {},
        }])
        try:
            block = build_environment_block(_cfg())
            assert "deploy" in block
        finally:
            register_custom_tools([])

    def test_no_mcp_section_when_none_registered(self):
        from franki.environment import build_environment_block
        from franki.agent.tools import register_mcp_clients
        register_mcp_clients({})
        block = build_environment_block(_cfg())
        assert "### MCP servers" not in block

    def test_compact_format_low_token_count(self):
        from franki.environment import build_environment_block
        from franki.main import _count_tokens_approx
        block = build_environment_block(_cfg())
        # Lean format should stay well under 100 tokens
        assert _count_tokens_approx(block) < 100


class TestSessionEnvContext:
    def test_env_context_injected_into_system_prompt(self):
        from franki.session import Session
        s = Session()
        s.set_env_context("## Test Environment\nActive model: test/model")
        system = s.get_messages()[0]["content"]
        assert "Test Environment" in system
        assert "Active model: test/model" in system

    def test_env_context_updates_on_set(self):
        from franki.session import Session
        s = Session()
        s.set_env_context("first block")
        s.set_env_context("second block")
        system = s.get_messages()[0]["content"]
        assert "second block" in system
        assert "first block" not in system

    def test_env_context_empty_by_default(self):
        from franki.session import Session
        s = Session()
        assert s._env_context == ""

    def test_from_dict_initialises_env_context(self):
        from franki.session import Session
        s = Session.from_dict({"skill": "coding", "messages": []})
        assert s._env_context == ""
        # Can be set after restore
        s.set_env_context("env block")
        assert "env block" in s.get_messages()[0]["content"]
