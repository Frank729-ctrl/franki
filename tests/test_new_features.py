"""Tests for session_store, change_tracker, profiles, /auto, /sessions, /undo, /diff, /profile."""
import json
import asyncio
from io import StringIO
from pathlib import Path
from unittest.mock import patch, MagicMock, AsyncMock

import pytest
from rich.console import Console

from franki.config import FrankiConfig
from franki.session import Session


def _cfg(**kwargs) -> FrankiConfig:
    base = dict(
        active_provider="groq",
        providers={"groq": {
            "api_key": "sk-test",
            "base_url": "https://api.groq.com/openai/v1",
            "model": "llama",
            "priority": 1,
        }},
    )
    base.update(kwargs)
    return FrankiConfig(**base)


def _console() -> Console:
    return Console(file=StringIO(), highlight=False, width=80)


def _session(skill="coding"):
    s = Session(skill=skill)
    s.add_user("hello")
    s.add_assistant("hi there")
    return s


# ── session_store ─────────────────────────────────────────────────────────────

class TestSessionStore:
    def test_save_returns_path(self, tmp_path):
        from franki.session_store import save_session, SESSIONS_DIR
        session = _session()
        cfg = _cfg()
        with patch("franki.session_store.SESSIONS_DIR", tmp_path):
            result = save_session(session, cfg)
        assert result is not None
        assert result.exists()

    def test_save_empty_session_returns_none(self, tmp_path):
        from franki.session_store import save_session
        session = Session()  # no messages
        with patch("franki.session_store.SESSIONS_DIR", tmp_path):
            result = save_session(session, _cfg())
        assert result is None

    def test_saved_file_contains_skill_and_messages(self, tmp_path):
        from franki.session_store import save_session
        session = _session("pentest")
        with patch("franki.session_store.SESSIONS_DIR", tmp_path):
            path = save_session(session, _cfg())
        data = json.loads(path.read_text())
        assert data["skill"] == "pentest"
        assert len(data["messages"]) > 0

    def test_list_sessions_returns_newest_first(self, tmp_path):
        from franki.session_store import save_session, list_sessions
        with patch("franki.session_store.SESSIONS_DIR", tmp_path):
            save_session(_session("coding"),  _cfg())
            save_session(_session("pentest"), _cfg())
            sessions = list_sessions()
        assert len(sessions) == 2
        assert sessions[0]["skill"] == "pentest"

    def test_list_sessions_empty_dir(self, tmp_path):
        from franki.session_store import list_sessions
        with patch("franki.session_store.SESSIONS_DIR", tmp_path):
            assert list_sessions() == []

    def test_load_session_data_by_index(self, tmp_path):
        from franki.session_store import save_session, load_session_data
        session = _session("soc")
        with patch("franki.session_store.SESSIONS_DIR", tmp_path):
            save_session(session, _cfg())
            data = load_session_data(1)
        assert data is not None
        assert data["skill"] == "soc"

    def test_load_session_data_invalid_index(self, tmp_path):
        from franki.session_store import load_session_data
        with patch("franki.session_store.SESSIONS_DIR", tmp_path):
            assert load_session_data(99) is None

    def test_delete_session(self, tmp_path):
        from franki.session_store import save_session, delete_session, list_sessions
        with patch("franki.session_store.SESSIONS_DIR", tmp_path):
            save_session(_session(), _cfg())
            assert delete_session(1) is True
            assert list_sessions() == []

    def test_delete_nonexistent_session(self, tmp_path):
        from franki.session_store import delete_session
        with patch("franki.session_store.SESSIONS_DIR", tmp_path):
            assert delete_session(5) is False

    def test_prune_keeps_max_sessions(self, tmp_path):
        from franki.session_store import save_session, list_sessions
        import time
        with patch("franki.session_store.SESSIONS_DIR", tmp_path), \
             patch("franki.session_store._MAX_SESSIONS", 3):
            for i in range(5):
                time.sleep(0.01)
                save_session(_session(), _cfg())
            sessions = list_sessions()
        assert len(sessions) <= 3


# ── Session.from_dict ─────────────────────────────────────────────────────────

class TestSessionFromDict:
    def test_restores_skill_and_scope(self):
        s = _session("pentest")
        s.scope = "10.0.0.0/8"
        data = {
            "skill": "pentest",
            "scope": "10.0.0.0/8",
            "messages": s.get_messages(),
        }
        restored = Session.from_dict(data)
        assert restored.skill == "pentest"
        assert restored.scope == "10.0.0.0/8"

    def test_restores_messages_without_system(self):
        s = _session()
        data = {
            "skill": "coding",
            "scope": None,
            "messages": s.get_messages(),
        }
        restored = Session.from_dict(data)
        history = restored.history_display()
        assert any(m["role"] == "user" for m in history)
        assert any(m["role"] == "assistant" for m in history)

    def test_system_message_is_fresh(self):
        data = {"skill": "coding", "scope": None, "messages": [
            {"role": "system", "content": "old stale prompt"},
            {"role": "user", "content": "hello"},
        ]}
        restored = Session.from_dict(data, memory_context="new memory")
        sys_msg = restored._messages[0]
        assert "new memory" in sys_msg["content"]
        assert "old stale prompt" not in sys_msg["content"]

    def test_change_tracker_is_none(self):
        data = {"skill": "coding", "scope": None, "messages": []}
        restored = Session.from_dict(data)
        assert restored.change_tracker is None


# ── change_tracker ────────────────────────────────────────────────────────────

class TestChangeTracker:
    def test_record_and_count(self):
        from franki.change_tracker import ChangeTracker
        ct = ChangeTracker()
        ct.record("/tmp/a.py", None, "new content", "write_file")
        assert ct.count == 1

    def test_revert_last_restores_file(self, tmp_path):
        from franki.change_tracker import ChangeTracker
        f = tmp_path / "test.py"
        original = "original content"
        f.write_text(original)
        ct = ChangeTracker()
        ct.record(str(f), original, "modified content", "edit_file")
        f.write_text("modified content")
        reverted = ct.revert_last()
        assert reverted == str(f)
        assert f.read_text() == original

    def test_revert_last_deletes_new_file(self, tmp_path):
        from franki.change_tracker import ChangeTracker
        f = tmp_path / "newfile.py"
        f.write_text("brand new")
        ct = ChangeTracker()
        ct.record(str(f), None, "brand new", "write_file")
        ct.revert_last()
        assert not f.exists()

    def test_revert_last_empty_returns_none(self):
        from franki.change_tracker import ChangeTracker
        ct = ChangeTracker()
        assert ct.revert_last() is None

    def test_revert_all_clears_stack(self, tmp_path):
        from franki.change_tracker import ChangeTracker
        f1 = tmp_path / "a.py"
        f2 = tmp_path / "b.py"
        f1.write_text("a"); f2.write_text("b")
        ct = ChangeTracker()
        ct.record(str(f1), "a", "a2", "write_file")
        ct.record(str(f2), "b", "b2", "write_file")
        f1.write_text("a2"); f2.write_text("b2")
        reverted = ct.revert_all()
        assert len(reverted) == 2
        assert ct.count == 0

    def test_diff_summary_shows_added_removed(self, tmp_path):
        from franki.change_tracker import ChangeTracker
        ct = ChangeTracker()
        ct.record("/tmp/x.py", "line1\n", "line1\nline2\n", "edit_file")
        diffs = ct.diff_summary()
        assert diffs[0]["lines_added"] >= 1
        assert diffs[0]["is_new_file"] is False

    def test_diff_summary_new_file(self):
        from franki.change_tracker import ChangeTracker
        ct = ChangeTracker()
        ct.record("/tmp/new.py", None, "content\n", "write_file")
        diffs = ct.diff_summary()
        assert diffs[0]["is_new_file"] is True

    def test_changed_paths_deduplicates(self):
        from franki.change_tracker import ChangeTracker
        ct = ChangeTracker()
        ct.record("/tmp/a.py", "x", "y", "edit_file")
        ct.record("/tmp/a.py", "y", "z", "edit_file")
        assert ct.changed_paths == ["/tmp/a.py"]


# ── profiles ──────────────────────────────────────────────────────────────────

class TestProfiles:
    def test_save_and_load(self, tmp_path):
        from franki.profiles import save_profile, load_profile
        cfg = _cfg()
        with patch("franki.profiles.PROFILES_DIR", tmp_path):
            save_profile("work", cfg)
            loaded = load_profile("work")
        assert loaded is not None
        assert loaded.active_provider == "groq"

    def test_load_nonexistent_returns_none(self, tmp_path):
        from franki.profiles import load_profile
        with patch("franki.profiles.PROFILES_DIR", tmp_path):
            assert load_profile("nope") is None

    def test_list_profiles(self, tmp_path):
        from franki.profiles import save_profile, list_profiles
        cfg = _cfg()
        with patch("franki.profiles.PROFILES_DIR", tmp_path):
            save_profile("alpha", cfg)
            save_profile("beta", cfg)
            names = list_profiles()
        assert names == ["alpha", "beta"]

    def test_delete_profile(self, tmp_path):
        from franki.profiles import save_profile, delete_profile, list_profiles
        cfg = _cfg()
        with patch("franki.profiles.PROFILES_DIR", tmp_path):
            save_profile("tmp", cfg)
            assert delete_profile("tmp") is True
            assert list_profiles() == []

    def test_delete_nonexistent_returns_false(self, tmp_path):
        from franki.profiles import delete_profile
        with patch("franki.profiles.PROFILES_DIR", tmp_path):
            assert delete_profile("ghost") is False

    def test_valid_name(self):
        from franki.profiles import _valid_name
        assert _valid_name("my-profile") is True
        assert _valid_name("work_2024") is True
        assert _valid_name("a" * 32) is True
        assert _valid_name("") is False
        assert _valid_name("a" * 33) is False
        assert _valid_name("bad name!") is False


# ── /auto command ─────────────────────────────────────────────────────────────

class TestCmdAuto:
    def _run(self, arg, cfg=None):
        from franki.commands import _cmd_auto
        if cfg is None:
            cfg = _cfg()
        saved = []
        _cmd_auto(cfg, arg, saved.append)
        return cfg, saved

    def test_no_arg_shows_state(self):
        from franki.commands import _cmd_auto
        cfg = _cfg(auto_accept=False, notify_on_done=True)
        c = _console()
        # Patch console inside commands
        with patch("franki.commands.console", c):
            _cmd_auto(cfg, "", lambda _: None)
        assert "off" in c.file.getvalue()

    def test_on_enables_auto_accept(self):
        cfg, saved = self._run("on", _cfg(auto_accept=False))
        assert cfg.auto_accept is True
        assert len(saved) == 1

    def test_off_disables_auto_accept(self):
        cfg, saved = self._run("off", _cfg(auto_accept=True))
        assert cfg.auto_accept is False
        assert len(saved) == 1

    def test_notify_on(self):
        cfg, saved = self._run("notify on", _cfg(notify_on_done=False))
        assert cfg.notify_on_done is True
        assert len(saved) == 1

    def test_notify_off(self):
        cfg, saved = self._run("notify off", _cfg(notify_on_done=True))
        assert cfg.notify_on_done is False

    def test_unknown_arg_no_crash(self):
        cfg, saved = self._run("blah")
        assert len(saved) == 0  # no save on unknown arg


# ── /undo command ─────────────────────────────────────────────────────────────

class TestCmdUndo:
    def test_nothing_to_undo(self):
        from franki.commands import _cmd_undo
        session = _session()
        with patch("franki.commands.console", _console()):
            _cmd_undo(session)  # no crash, no change_tracker

    def test_undo_reverts_last_change(self, tmp_path):
        from franki.commands import _cmd_undo
        from franki.change_tracker import ChangeTracker
        f = tmp_path / "f.py"
        f.write_text("original")
        session = _session()
        ct = ChangeTracker()
        ct.record(str(f), "original", "modified", "edit_file")
        f.write_text("modified")
        session.change_tracker = ct
        with patch("franki.commands.console", _console()):
            _cmd_undo(session)
        assert f.read_text() == "original"
        assert ct.count == 0

    def test_undo_with_no_changes(self):
        from franki.commands import _cmd_undo
        from franki.change_tracker import ChangeTracker
        session = _session()
        session.change_tracker = ChangeTracker()
        with patch("franki.commands.console", _console()):
            _cmd_undo(session)  # should print "nothing to undo"


# ── /diff command ─────────────────────────────────────────────────────────────

class TestCmdDiff:
    def test_diff_no_changes(self):
        from franki.commands import _cmd_diff
        session = _session()
        with patch("franki.commands.console", _console()):
            _cmd_diff(session)  # no crash

    def test_diff_shows_changed_file(self):
        from franki.commands import _cmd_diff
        from franki.change_tracker import ChangeTracker
        session = _session()
        ct = ChangeTracker()
        ct.record("/tmp/x.py", "old\n", "new\n", "edit_file")
        session.change_tracker = ct
        c = _console()
        with patch("franki.commands.console", c):
            _cmd_diff(session)
        assert "/tmp/x.py" in c.file.getvalue()


# ── /sessions command ─────────────────────────────────────────────────────────

class TestCmdSessions:
    def _make_redraw(self):
        return lambda: None

    def test_sessions_list_empty(self, tmp_path):
        from franki.commands import _cmd_sessions
        cfg = _cfg()
        session = _session()
        c = _console()
        with patch("franki.session_store.SESSIONS_DIR", tmp_path), \
             patch("franki.commands.console", c):
            _cmd_sessions(cfg, session, "", lambda _: None, self._make_redraw())
        assert "no saved sessions" in c.file.getvalue()

    def test_sessions_save(self, tmp_path):
        from franki.commands import _cmd_sessions
        cfg = _cfg()
        session = _session()
        with patch("franki.session_store.SESSIONS_DIR", tmp_path), \
             patch("franki.commands.console", _console()):
            _cmd_sessions(cfg, session, "save", lambda _: None, self._make_redraw())
        assert len(list(tmp_path.glob("*.json"))) == 1

    def test_sessions_delete(self, tmp_path):
        from franki.commands import _cmd_sessions
        from franki.session_store import save_session
        cfg = _cfg()
        session = _session()
        with patch("franki.session_store.SESSIONS_DIR", tmp_path):
            save_session(session, cfg)
        with patch("franki.session_store.SESSIONS_DIR", tmp_path), \
             patch("franki.commands.console", _console()):
            _cmd_sessions(cfg, session, "delete 1", lambda _: None, self._make_redraw())
        assert list(tmp_path.glob("*.json")) == []

    def test_sessions_resume(self, tmp_path):
        from franki.commands import _cmd_sessions
        from franki.session_store import save_session
        cfg = _cfg()
        session = _session("pentest")
        with patch("franki.session_store.SESSIONS_DIR", tmp_path):
            save_session(session, cfg)
        target = _session("coding")
        with patch("franki.session_store.SESSIONS_DIR", tmp_path), \
             patch("franki.commands.console", _console()):
            _cmd_sessions(cfg, target, "resume 1", lambda _: None, self._make_redraw())
        assert target.skill == "pentest"


# ── /profile command ─────────────────────────────────────────────────────────

class TestCmdProfile:
    def _run(self, arg, cfg=None, tmp_path=None):
        from franki.commands import _cmd_profile
        if cfg is None:
            cfg = _cfg()
        saved = []
        ctx = patch("franki.profiles.PROFILES_DIR", tmp_path) if tmp_path else patch("franki.profiles.PROFILES_DIR", Path("/tmp/franki_test_profiles"))
        with ctx, patch("franki.commands.console", _console()):
            _cmd_profile(cfg, arg, saved.append, lambda: None)
        return cfg, saved

    def test_save_profile(self, tmp_path):
        _cfg2, _saved = self._run("save myprofile", tmp_path=tmp_path)
        assert (tmp_path / "myprofile.json").exists()

    def test_load_profile(self, tmp_path):
        from franki.profiles import save_profile
        cfg = _cfg()
        save_profile("test", cfg)
        loaded_cfg, saved = self._run("load test", tmp_path=tmp_path)
        # Profile file doesn't exist in tmp_path, expect "not found"
        # (load looks in PROFILES_DIR which we patch to tmp_path)

    def test_invalid_profile_name(self, tmp_path):
        cfg = _cfg()
        saved = []
        from franki.commands import _cmd_profile
        with patch("franki.profiles.PROFILES_DIR", tmp_path), \
             patch("franki.commands.console", _console()):
            _cmd_profile(cfg, "save bad name!", saved.append, lambda: None)
        assert len(saved) == 0

    def test_list_profiles(self, tmp_path):
        from franki.profiles import save_profile
        with patch("franki.profiles.PROFILES_DIR", tmp_path):
            save_profile("alpha", _cfg())
        c = _console()
        from franki.commands import _cmd_profile
        with patch("franki.profiles.PROFILES_DIR", tmp_path), \
             patch("franki.commands.console", c):
            _cmd_profile(_cfg(), "", lambda _: None, lambda: None)
        assert "alpha" in c.file.getvalue()


# ── stream_chat_with_tools ────────────────────────────────────────────────────

class TestStreamChatWithTools:
    @pytest.mark.asyncio
    async def test_yields_text_and_done(self):
        from franki.providers.generic import stream_chat_with_tools

        sse_lines = [
            'data: {"choices":[{"delta":{"content":"hello"},"finish_reason":null}]}',
            'data: {"choices":[{"delta":{"content":" world"},"finish_reason":null}]}',
            'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}',
            "data: [DONE]",
        ]

        async def _mock_stream(*args, **kwargs):
            for line in sse_lines:
                yield line

        with patch("httpx.AsyncClient") as mock_client:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.aiter_lines = _mock_stream
            mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
            mock_resp.__aexit__ = AsyncMock(return_value=False)
            mock_client.return_value.__aenter__ = AsyncMock(return_value=mock_client.return_value)
            mock_client.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_client.return_value.stream.return_value = mock_resp

            events = []
            async for ev in stream_chat_with_tools("key", "model", [], "http://x", []):
                events.append(ev)

        text_events = [v for t, v in events if t == "text"]
        done_events = [v for t, v in events if t == "done"]
        assert "".join(text_events) == "hello world"
        assert len(done_events) == 1
        assert json.loads(done_events[0]) == []

    @pytest.mark.asyncio
    async def test_accumulates_tool_calls(self):
        from franki.providers.generic import stream_chat_with_tools

        sse_lines = [
            'data: {"choices":[{"delta":{"tool_calls":[{"index":0,"id":"c1","type":"function","function":{"name":"read_file","arguments":""}}]},"finish_reason":null}]}',
            'data: {"choices":[{"delta":{"tool_calls":[{"index":0,"function":{"arguments":"{\\"path\\":\\"/tmp/x\\"}"}}]},"finish_reason":null}]}',
            'data: {"choices":[{"delta":{},"finish_reason":"tool_calls"}]}',
            "data: [DONE]",
        ]

        async def _mock_stream(*args, **kwargs):
            for line in sse_lines:
                yield line

        with patch("httpx.AsyncClient") as mock_client:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.aiter_lines = _mock_stream
            mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
            mock_resp.__aexit__ = AsyncMock(return_value=False)
            mock_client.return_value.__aenter__ = AsyncMock(return_value=mock_client.return_value)
            mock_client.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_client.return_value.stream.return_value = mock_resp

            events = []
            async for ev in stream_chat_with_tools("key", "model", [], "http://x", []):
                events.append(ev)

        done_events = [v for t, v in events if t == "done"]
        tcs = json.loads(done_events[0])
        assert len(tcs) == 1
        assert tcs[0]["function"]["name"] == "read_file"
        assert "/tmp/x" in tcs[0]["function"]["arguments"]
