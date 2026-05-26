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
        assert "active" in block

    def test_includes_builtin_tools(self):
        from franki.environment import build_environment_block
        block = build_environment_block(_cfg())
        assert "read_file" in block
        assert "write_file" in block
        assert "run_command" in block

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

    def test_includes_settings(self):
        from franki.environment import build_environment_block
        block = build_environment_block(_cfg())
        assert "auto_accept" in block
        assert "auto_copy" in block

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

    def test_includes_self_knowledge_instruction(self):
        from franki.environment import build_environment_block
        block = build_environment_block(_cfg())
        assert "knowledge" in block.lower() or "capabilities" in block.lower()


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
