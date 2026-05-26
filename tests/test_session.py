"""Comprehensive tests for session.py."""
import pytest
from franki.session import Session


class TestInit:
    def test_default_skill_is_coding(self):
        s = Session()
        assert s.skill == "coding"

    def test_system_message_inserted(self):
        s = Session()
        msgs = s.get_messages()
        assert msgs[0]["role"] == "system"
        assert len(msgs[0]["content"]) > 20

    def test_custom_skill(self):
        s = Session(skill="pentest")
        assert s.skill == "pentest"

    def test_memory_context_in_system(self):
        s = Session(memory_context="user prefers Python")
        assert "user prefers Python" in s.get_messages()[0]["content"]

    def test_no_memory_context(self):
        s = Session(memory_context="")
        prompt = s.get_messages()[0]["content"]
        assert isinstance(prompt, str)

    def test_trackers_initially_none(self):
        s = Session()
        assert s.routing_tracker is None
        assert s.cost_tracker is None


class TestAddMessages:
    def test_add_user(self):
        s = Session()
        s.add_user("hello")
        display = s.history_display()
        assert display[-1] == {"role": "user", "content": "hello"}

    def test_add_assistant(self):
        s = Session()
        s.add_assistant("hi there")
        display = s.history_display()
        assert display[-1] == {"role": "assistant", "content": "hi there"}

    def test_system_excluded_from_history(self):
        s = Session()
        s.add_user("q")
        s.add_assistant("a")
        for m in s.history_display():
            assert m["role"] != "system"

    def test_get_messages_includes_system(self):
        s = Session()
        roles = [m["role"] for m in s.get_messages()]
        assert "system" in roles

    def test_get_messages_returns_copy(self):
        s = Session()
        m1 = s.get_messages()
        m1.append({"role": "user", "content": "injected"})
        assert len(s.get_messages()) == len(m1) - 1


class TestSetSkill:
    def test_set_skill_updates_attribute(self):
        s = Session(skill="coding")
        s.set_skill("soc")
        assert s.skill == "soc"

    def test_set_skill_updates_system_prompt(self):
        s = Session(skill="coding")
        prompt_before = s.get_messages()[0]["content"]
        s.set_skill("pentest")
        prompt_after = s.get_messages()[0]["content"]
        assert prompt_before != prompt_after

    def test_set_skill_keeps_existing_messages(self):
        s = Session()
        s.add_user("test")
        s.set_skill("soc")
        assert any(m["content"] == "test" for m in s.get_messages())

    def test_system_still_first_after_skill_change(self):
        s = Session()
        s.add_user("msg1")
        s.set_skill("pentest")
        assert s.get_messages()[0]["role"] == "system"


class TestScope:
    def test_scope_appended_for_pentest(self):
        s = Session(skill="pentest")
        s.set_scope("192.168.1.0/24")
        prompt = s.get_messages()[0]["content"]
        assert "192.168.1.0/24" in prompt

    def test_scope_not_appended_for_non_pentest(self):
        s = Session(skill="coding")
        s.set_scope("192.168.1.1")
        prompt = s.get_messages()[0]["content"]
        assert "192.168.1.1" not in prompt

    def test_clear_scope(self):
        s = Session(skill="pentest")
        s.set_scope("10.0.0.1")
        s.set_scope(None)
        assert s.scope is None
        prompt = s.get_messages()[0]["content"]
        assert "10.0.0.1" not in prompt


class TestRewind:
    def test_rewind_removes_last_pair(self):
        s = Session()
        s.add_user("q1")
        s.add_assistant("a1")
        removed = s.rewind()
        assert removed == 2
        assert s.history_display() == []

    def test_rewind_only_user(self):
        s = Session()
        s.add_user("q1")
        removed = s.rewind()
        assert removed == 1
        assert s.history_display() == []

    def test_rewind_empty_returns_zero(self):
        s = Session()
        assert s.rewind() == 0

    def test_rewind_preserves_earlier_messages(self):
        s = Session()
        s.add_user("q1")
        s.add_assistant("a1")
        s.add_user("q2")
        s.add_assistant("a2")
        s.rewind()
        history = s.history_display()
        assert len(history) == 2
        assert history[0]["content"] == "q1"

    def test_rewind_assistant_only_at_end(self):
        # Manually construct unusual state — assistant without user
        s = Session()
        s._messages.append({"role": "assistant", "content": "orphan"})
        removed = s.rewind()
        assert removed == 1


class TestClear:
    def test_clear_removes_all_non_system(self):
        s = Session()
        s.add_user("a")
        s.add_assistant("b")
        s.clear()
        assert s.history_display() == []

    def test_clear_keeps_system_prompt(self):
        s = Session()
        s.add_user("msg")
        s.clear()
        msgs = s.get_messages()
        assert msgs[0]["role"] == "system"
        assert len(msgs) == 1


class TestCompact:
    def test_compact_replaces_history(self):
        s = Session()
        s.add_user("long conversation")
        s.add_assistant("long response")
        s.compact("brief summary")
        assert len(s.history_display()) == 1

    def test_compact_content_contains_summary(self):
        s = Session()
        s.compact("key points here")
        assert "key points here" in s.history_display()[0]["content"]

    def test_compact_preserves_system_first(self):
        s = Session()
        s.compact("summary")
        assert s.get_messages()[0]["role"] == "system"


class TestLastResponse:
    def test_none_when_empty(self):
        s = Session()
        assert s.last_response is None

    def test_returns_last_assistant(self):
        s = Session()
        s.add_assistant("first")
        s.add_user("question")
        s.add_assistant("second")
        assert s.last_response == "second"

    def test_none_when_only_user_messages(self):
        s = Session()
        s.add_user("question")
        assert s.last_response is None


class TestMessageStats:
    def test_empty_stats(self):
        s = Session()
        stats = s.message_stats()
        assert stats["user"] == 0
        assert stats["assistant"] == 0
        assert stats["total"] == 0

    def test_counts(self):
        s = Session()
        s.add_user("q1")
        s.add_assistant("a1")
        s.add_user("q2")
        stats = s.message_stats()
        assert stats["user"] == 2
        assert stats["assistant"] == 1
        assert stats["total"] == 3

    def test_approx_tokens_positive(self):
        s = Session()
        s.add_user("a" * 400)
        stats = s.message_stats()
        assert stats["approx_tokens"] > 0


class TestMemoryContext:
    def test_set_memory_context_updates_prompt(self):
        s = Session()
        s.set_memory_context("remember: use typescript")
        assert "remember: use typescript" in s.get_messages()[0]["content"]

    def test_clear_memory_context(self):
        s = Session(memory_context="old context")
        s.set_memory_context("")
        prompt = s.get_messages()[0]["content"]
        assert "old context" not in prompt


class TestProjectContext:
    def test_set_project_context_updates_prompt(self):
        s = Session()
        s.set_project_context("# My Project\nuse FastAPI")
        assert "My Project" in s.get_messages()[0]["content"]

    def test_clear_project_context_with_none(self):
        s = Session(project_context="old project")
        s.set_project_context(None)
        assert "old project" not in s.get_messages()[0]["content"]

    def test_clear_project_context_with_empty_string(self):
        s = Session(project_context="old project")
        s.set_project_context("")
        assert "old project" not in s.get_messages()[0]["content"]
