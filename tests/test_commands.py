"""Tests for commands.py — individual _cmd_* functions."""
import pytest
from io import StringIO
from pathlib import Path
from unittest.mock import patch, MagicMock

from franki.config import FrankiConfig
from franki.session import Session


# ── Helpers ───────────────────────────────────────────────────────────────────

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


def _session(**kwargs):
    return Session(**kwargs)


def _noop(*args, **kwargs):
    pass


# ── handle_command dispatch ───────────────────────────────────────────────────

class TestHandleCommand:
    def test_unknown_command_returns_true(self):
        from franki.commands import handle_command
        cfg = _cfg()
        s = _session()
        result = handle_command("/unknowncmd", cfg, s, _noop, _noop)
        assert result is True

    def test_clear_dispatches(self):
        from franki.commands import handle_command
        s = _session()
        s.add_user("hello")
        handle_command("/clear", _cfg(), s, _noop, _noop)
        assert s.history_display() == []

    def test_rewind_dispatches(self):
        from franki.commands import handle_command
        s = _session()
        s.add_user("q")
        s.add_assistant("a")
        handle_command("/rewind", _cfg(), s, _noop, _noop)
        assert s.history_display() == []

    def test_history_dispatches(self):
        from franki.commands import handle_command
        s = _session()
        result = handle_command("/history", _cfg(), s, _noop, _noop)
        assert result is True

    def test_context_dispatches(self):
        from franki.commands import handle_command
        with patch("franki.memory.list_facts", return_value=[]), \
             patch("franki.memory.skill_usage_counts", return_value={}), \
             patch("franki.memory.list_scopes", return_value=[]):
            result = handle_command("/context", _cfg(), _session(), _noop, _noop)
        assert result is True

    def test_skill_no_arg_lists_skills(self):
        from franki.commands import handle_command
        result = handle_command("/skill", _cfg(), _session(), _noop, _noop)
        assert result is True

    def test_model_no_arg_lists_providers(self):
        from franki.commands import handle_command
        result = handle_command("/model", _cfg(), _session(), _noop, _noop)
        assert result is True

    def test_scope_dispatches(self):
        from franki.commands import handle_command
        s = _session(skill="pentest")
        handle_command("/scope 10.0.0.1", _cfg(), s, _noop, _noop)
        assert s.scope == "10.0.0.1"

    def test_remember_dispatches(self):
        from franki.commands import handle_command
        with patch("franki.memory.add", return_value={"id": 1, "content": "test"}) as mock_add, \
             patch("franki.memory.get_context_string", return_value=""):
            result = handle_command("/remember I use vim", _cfg(), _session(), _noop, _noop)
        assert result is True
        mock_add.assert_called_once()

    def test_memory_dispatches(self):
        from franki.commands import handle_command
        with patch("franki.memory.list_facts", return_value=[]), \
             patch("franki.memory.list_scopes", return_value=[]), \
             patch("franki.memory.skill_usage_counts", return_value={}), \
             patch("franki.memory.list_notes", return_value=[]):
            result = handle_command("/memory", _cfg(), _session(), _noop, _noop)
        assert result is True

    def test_forget_dispatches(self):
        from franki.commands import handle_command
        with patch("franki.memory.remove", return_value=False):
            result = handle_command("/forget 999", _cfg(), _session(), _noop, _noop)
        assert result is True

    def test_cost_dispatches(self):
        from franki.commands import handle_command
        result = handle_command("/cost", _cfg(), _session(), _noop, _noop)
        assert result is True

    def test_routing_dispatches(self):
        from franki.commands import handle_command
        result = handle_command("/routing", _cfg(), _session(), _noop, _noop)
        assert result is True

    def test_help_dispatches(self):
        from franki.commands import handle_command
        result = handle_command("/help", _cfg(), _session(), _noop, _noop)
        assert result is True

    def test_connect_legacy_handled(self):
        from franki.commands import handle_command
        result = handle_command("/connect", _cfg(), _session(), _noop, _noop)
        assert result is True

    def test_exit_raises(self):
        from franki.commands import handle_command
        with pytest.raises(SystemExit):
            handle_command("/exit", _cfg(), _session(), _noop, _noop)

    def test_quit_raises(self):
        from franki.commands import handle_command
        with pytest.raises(SystemExit):
            handle_command("/quit", _cfg(), _session(), _noop, _noop)

    def test_memories_alias(self):
        from franki.commands import handle_command
        with patch("franki.memory.list_facts", return_value=[]), \
             patch("franki.memory.list_scopes", return_value=[]), \
             patch("franki.memory.skill_usage_counts", return_value={}), \
             patch("franki.memory.list_notes", return_value=[]):
            result = handle_command("/memories", _cfg(), _session(), _noop, _noop)
        assert result is True

    def test_route_alias(self):
        from franki.commands import handle_command
        result = handle_command("/route", _cfg(), _session(), _noop, _noop)
        assert result is True


# ── _cmd_clear ────────────────────────────────────────────────────────────────

class TestCmdClear:
    def test_clears_session(self):
        from franki.commands import _cmd_clear
        s = _session()
        s.add_user("test")
        _cmd_clear(s)
        assert s.history_display() == []

    def test_returns_true(self):
        from franki.commands import _cmd_clear
        assert _cmd_clear(_session()) is True


# ── _cmd_rewind ───────────────────────────────────────────────────────────────

class TestCmdRewind:
    def test_removes_messages(self):
        from franki.commands import _cmd_rewind
        s = _session()
        s.add_user("q")
        s.add_assistant("a")
        _cmd_rewind(s)
        assert s.history_display() == []

    def test_empty_session_prints_notice(self, capsys):
        from franki.commands import _cmd_rewind
        _cmd_rewind(_session())

    def test_returns_true(self):
        from franki.commands import _cmd_rewind
        assert _cmd_rewind(_session()) is True


# ── _cmd_history ──────────────────────────────────────────────────────────────

class TestCmdHistory:
    def test_empty_history(self):
        from franki.commands import _cmd_history
        result = _cmd_history(_session())
        assert result is True

    def test_with_messages(self):
        from franki.commands import _cmd_history
        s = _session()
        s.add_user("what is nmap")
        s.add_assistant("nmap is a scanner")
        result = _cmd_history(s)
        assert result is True


# ── _cmd_cost ─────────────────────────────────────────────────────────────────

class TestCmdCost:
    def test_no_tracker_prints_notice(self):
        from franki.commands import _cmd_cost
        s = _session()
        assert s.cost_tracker is None
        result = _cmd_cost(s)
        assert result is True

    def test_empty_tracker_prints_notice(self):
        from franki.commands import _cmd_cost
        from franki.cost_tracker import CostTracker
        s = _session()
        s.cost_tracker = CostTracker()
        result = _cmd_cost(s)
        assert result is True

    def test_with_data_prints_summary(self):
        from franki.commands import _cmd_cost
        from franki.cost_tracker import CostTracker
        s = _session()
        s.cost_tracker = CostTracker()
        pdata = {"cost_per_1m_input": 0.05, "cost_per_1m_output": 0.08}
        s.cost_tracker.record("groq", "llama", 100, 200, pdata, 1.5)
        result = _cmd_cost(s)
        assert result is True


# ── _cmd_routing ──────────────────────────────────────────────────────────────

class TestCmdRouting:
    def test_no_providers_prints_notice(self):
        from franki.commands import _cmd_routing
        cfg = FrankiConfig()
        s = _session()
        result = _cmd_routing(cfg, s)
        assert result is True

    def test_with_provider_prints_table(self):
        from franki.commands import _cmd_routing
        cfg = _cfg()
        s = _session()
        result = _cmd_routing(cfg, s)
        assert result is True

    def test_uses_session_routing_tracker(self):
        from franki.commands import _cmd_routing
        from franki.routing import RoutingTracker
        cfg = _cfg()
        s = _session()
        s.routing_tracker = RoutingTracker()
        s.routing_tracker.record_latency("groq", 1.2)
        result = _cmd_routing(cfg, s)
        assert result is True


# ── _cmd_skill ────────────────────────────────────────────────────────────────

class TestCmdSkill:
    def test_no_arg_lists_skills(self):
        from franki.commands import _cmd_skill
        result = _cmd_skill(_cfg(), _session(), "", _noop, _noop)
        assert result is True

    def test_invalid_skill_prints_error(self):
        from franki.commands import _cmd_skill
        result = _cmd_skill(_cfg(), _session(), "notaskill_xyz", _noop, _noop)
        assert result is True

    def test_valid_skill_updates_session(self):
        from franki.commands import _cmd_skill
        from franki.skills import get_all_skill_names
        s = _session(skill="coding")
        valid = get_all_skill_names()
        other_skill = next(sk for sk in valid if sk != "coding")
        with patch("franki.memory.track_skill"):
            save_fn = MagicMock()
            _cmd_skill(_cfg(), s, other_skill, save_fn, _noop)
        assert s.skill == other_skill
        assert save_fn.called


# ── _cmd_model ────────────────────────────────────────────────────────────────

class TestCmdModel:
    def test_no_arg_lists_providers(self):
        from franki.commands import _cmd_model
        result = _cmd_model(_cfg(), "", _noop, _noop)
        assert result is True

    def test_no_slash_prints_format_error(self):
        from franki.commands import _cmd_model
        result = _cmd_model(_cfg(), "just-text", _noop, _noop)
        assert result is True

    def test_unknown_provider_prints_error(self):
        from franki.commands import _cmd_model
        result = _cmd_model(_cfg(), "unknown/model", _noop, _noop)
        assert result is True

    def test_valid_switch_updates_config(self):
        from franki.commands import _cmd_model
        cfg = _cfg()
        save_fn = MagicMock()
        _cmd_model(cfg, "groq/llama-3.1-8b", save_fn, _noop)
        assert cfg.active_provider == "groq"
        assert cfg.providers["groq"]["model"] == "llama-3.1-8b"
        assert save_fn.called


# ── _cmd_scope ────────────────────────────────────────────────────────────────

class TestCmdScope:
    def test_sets_scope(self):
        from franki.commands import _cmd_scope
        s = _session(skill="pentest")
        with patch("franki.memory.track_scope"):
            _cmd_scope(s, "10.0.0.0/24", _noop)
        assert s.scope == "10.0.0.0/24"

    def test_clear_clears_scope(self):
        from franki.commands import _cmd_scope
        s = _session(skill="pentest")
        s.set_scope("10.0.0.1")
        _cmd_scope(s, "clear", _noop)
        assert s.scope is None

    def test_empty_arg_clears_scope(self):
        from franki.commands import _cmd_scope
        s = _session(skill="pentest")
        s.set_scope("10.0.0.1")
        _cmd_scope(s, "", _noop)
        assert s.scope is None


# ── _cmd_cd ───────────────────────────────────────────────────────────────────

class TestCmdCd:
    def test_no_arg_prints_cwd(self, tmp_path):
        from franki.commands import _cmd_cd
        s = _session()
        result = _cmd_cd("", _cfg(), s, _noop)
        assert result is True

    def test_changes_to_valid_dir(self, tmp_path):
        from franki.commands import _cmd_cd
        import os
        original = os.getcwd()
        s = _session()
        try:
            _cmd_cd(str(tmp_path), _cfg(), s, _noop)
            assert os.getcwd() == str(tmp_path)
        finally:
            os.chdir(original)

    def test_reloads_franki_md(self, tmp_path):
        from franki.commands import _cmd_cd
        import os
        original = os.getcwd()
        (tmp_path / ".franki.md").write_text("new project context")
        s = _session()
        try:
            _cmd_cd(str(tmp_path), _cfg(), s, _noop)
            assert "new project context" in s.get_messages()[0]["content"]
        finally:
            os.chdir(original)

    def test_clears_project_context_when_no_franki_md(self, tmp_path):
        from franki.commands import _cmd_cd
        import os
        original = os.getcwd()
        s = _session()
        s.set_project_context("old context")
        try:
            _cmd_cd(str(tmp_path), _cfg(), s, _noop)
            assert "old context" not in s.get_messages()[0]["content"]
        finally:
            os.chdir(original)

    def test_missing_path_returns_error(self, tmp_path):
        from franki.commands import _cmd_cd
        s = _session()
        result = _cmd_cd(str(tmp_path / "nonexistent"), _cfg(), s, _noop)
        assert result is True

    def test_file_path_returns_error(self, tmp_path):
        from franki.commands import _cmd_cd
        f = tmp_path / "file.txt"
        f.write_text("x")
        s = _session()
        result = _cmd_cd(str(f), _cfg(), s, _noop)
        assert result is True

    def test_tilde_expansion(self, tmp_path):
        from franki.commands import _cmd_cd
        import os
        original = os.getcwd()
        home = Path.home()
        s = _session()
        try:
            _cmd_cd("~", _cfg(), s, _noop)
            assert os.getcwd() == str(home)
        finally:
            os.chdir(original)

    def test_handle_command_dispatches_cd(self, tmp_path):
        from franki.commands import handle_command
        s = _session()
        import os
        original = os.getcwd()
        try:
            result = handle_command(f"/cd {tmp_path}", _cfg(), s, _noop, _noop)
        finally:
            os.chdir(original)
        assert result is True


# ── _cmd_remember / _cmd_forget ───────────────────────────────────────────────

class TestCmdRemember:
    def test_empty_text_prints_usage(self):
        from franki.commands import _cmd_remember
        result = _cmd_remember("", _session())
        assert result is True

    def test_remembers_text(self):
        from franki.commands import _cmd_remember
        with patch("franki.memory.add", return_value={"id": 1, "content": "use vim"}) as mock_add, \
             patch("franki.memory.get_context_string", return_value="use vim"):
            result = _cmd_remember("use vim", _session())
        assert result is True
        mock_add.assert_called_once_with("use vim")


class TestCmdForget:
    def test_empty_arg_prints_usage(self):
        from franki.commands import _cmd_forget
        result = _cmd_forget("", _session())
        assert result is True

    def test_forget_all_clears_memory(self):
        from franki.commands import _cmd_forget
        with patch("franki.memory.clear_all") as mock_clear, \
             patch("franki.memory.get_context_string", return_value=""):
            _cmd_forget("all", _session())
        mock_clear.assert_called_once()

    def test_forget_by_id_existing(self):
        from franki.commands import _cmd_forget
        s = _session()
        with patch("franki.memory.remove", return_value=True) as mock_remove, \
             patch("franki.memory.get_context_string", return_value=""):
            _cmd_forget("5", s)
        mock_remove.assert_called_once_with(5)

    def test_forget_by_id_not_found(self):
        from franki.commands import _cmd_forget
        with patch("franki.memory.remove", return_value=False):
            result = _cmd_forget("999", _session())
        assert result is True

    def test_invalid_id_prints_error(self):
        from franki.commands import _cmd_forget
        result = _cmd_forget("not-a-number", _session())
        assert result is True


# ── _cmd_memory ───────────────────────────────────────────────────────────────

class TestCmdMemory:
    def test_empty_memory_prints_notice(self):
        from franki.commands import _cmd_memory
        with patch("franki.memory.list_facts", return_value=[]), \
             patch("franki.memory.list_scopes", return_value=[]), \
             patch("franki.memory.skill_usage_counts", return_value={}), \
             patch("franki.memory.list_notes", return_value=[]):
            result = _cmd_memory()
        assert result is True

    def test_with_data_shows_tables(self):
        from franki.commands import _cmd_memory
        with patch("franki.memory.list_facts", return_value=[{"id": 1, "content": "use vim"}]), \
             patch("franki.memory.list_scopes", return_value=["10.0.0.1"]), \
             patch("franki.memory.skill_usage_counts", return_value={"coding": 3}), \
             patch("franki.memory.list_notes", return_value=[{"text": "note", "ts": "x"}]):
            result = _cmd_memory()
        assert result is True


# ── _cmd_note ─────────────────────────────────────────────────────────────────

class TestCmdNote:
    def test_empty_text_prints_usage(self):
        from franki.commands import _cmd_note
        result = _cmd_note(_cfg(), "")
        assert result is True

    def test_saves_note(self, tmp_path):
        from franki.commands import _cmd_note
        cfg = FrankiConfig(export_path=str(tmp_path))
        with patch("franki.memory.track_note"):
            result = _cmd_note(cfg, "SQL injection found")
        assert result is True

    def test_failed_save_prints_error(self):
        from franki.commands import _cmd_note
        with patch("franki.exporter.save_note", return_value=None):
            result = _cmd_note(_cfg(), "some note")
        assert result is True


# ── _cmd_export ───────────────────────────────────────────────────────────────

class TestCmdExport:
    def test_successful_export(self, tmp_path):
        from franki.commands import _cmd_export
        cfg = FrankiConfig(export_path=str(tmp_path))
        s = _session()
        s.add_user("test")
        result = _cmd_export(cfg, s)
        assert result is True

    def test_failed_export_prints_cancelled(self):
        from franki.commands import _cmd_export
        with patch("franki.exporter.export_session", return_value=None):
            result = _cmd_export(_cfg(), _session())
        assert result is True


# ── _cmd_copy ─────────────────────────────────────────────────────────────────

class TestCmdCopy:
    def test_no_response_prints_notice(self):
        from franki.commands import _cmd_copy
        result = _cmd_copy(_session())
        assert result is True

    def test_copies_with_pyperclip(self):
        from franki.commands import _cmd_copy
        s = _session()
        s.add_assistant("some response")
        mock_pyperclip = MagicMock()
        with patch.dict("sys.modules", {"pyperclip": mock_pyperclip}):
            result = _cmd_copy(s)
        assert result is True

    def test_no_pyperclip_handled(self):
        from franki.commands import _cmd_copy
        import sys
        s = _session()
        s.add_assistant("response text")
        with patch.dict("sys.modules", {"pyperclip": None}):
            result = _cmd_copy(s)
        assert result is True


# ── _strip_markup ─────────────────────────────────────────────────────────────

class TestStripMarkup:
    def test_strips_rich_tags(self):
        from franki.commands import _strip_markup
        result = _strip_markup("[bold]hello[/bold] world")
        assert "bold" not in result
        assert "hello" in result
        assert "world" in result

    def test_plain_text_unchanged(self):
        from franki.commands import _strip_markup
        assert _strip_markup("plain text") == "plain text"


# ── _cmd_context ──────────────────────────────────────────────────────────────

class TestCmdContext:
    def test_shows_context_table(self):
        from franki.commands import _cmd_context
        with patch("franki.memory.list_facts", return_value=[{"id": 1, "content": "x"}]), \
             patch("franki.memory.skill_usage_counts", return_value={"coding": 2}), \
             patch("franki.memory.list_scopes", return_value=["10.0.0.1", "192.168.1.1", "172.16.0.0", "10.10.0.0"]), \
             patch("franki.utils.search.is_search_available", return_value=True):
            result = _cmd_context(_cfg(), _session())
        assert result is True

    def test_empty_context(self):
        from franki.commands import _cmd_context
        with patch("franki.memory.list_facts", return_value=[]), \
             patch("franki.memory.skill_usage_counts", return_value={}), \
             patch("franki.memory.list_scopes", return_value=[]):
            result = _cmd_context(_cfg(), _session())
        assert result is True
