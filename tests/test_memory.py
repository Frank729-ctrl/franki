"""Comprehensive tests for memory.py — uses tmp_path to avoid touching real disk."""
import json
import pytest
from pathlib import Path
from unittest.mock import patch


def _patch_memory(tmp_path):
    """Return a context manager that redirects memory I/O to tmp_path."""
    mem_file = tmp_path / "memory.json"
    return patch("franki.memory._MEMORY_FILE", mem_file)


class TestFacts:
    def test_add_and_list(self, tmp_path):
        with _patch_memory(tmp_path):
            import franki.memory as m
            entry = m.add("I use vim")
            assert entry["content"] == "I use vim"
            assert entry["id"] == 1
            facts = m.list_facts()
            assert len(facts) == 1
            assert facts[0]["content"] == "I use vim"

    def test_ids_auto_increment(self, tmp_path):
        with _patch_memory(tmp_path):
            import franki.memory as m
            m.add("fact one")
            m.add("fact two")
            ids = [f["id"] for f in m.list_facts()]
            assert ids == [1, 2]

    def test_remove_existing(self, tmp_path):
        with _patch_memory(tmp_path):
            import franki.memory as m
            entry = m.add("to remove")
            removed = m.remove(entry["id"])
            assert removed is True
            assert m.list_facts() == []

    def test_remove_nonexistent(self, tmp_path):
        with _patch_memory(tmp_path):
            import franki.memory as m
            assert m.remove(999) is False

    def test_clear_facts(self, tmp_path):
        with _patch_memory(tmp_path):
            import franki.memory as m
            m.add("a")
            m.add("b")
            count = m.clear_facts()
            assert count == 2
            assert m.list_facts() == []

    def test_aliases(self, tmp_path):
        with _patch_memory(tmp_path):
            import franki.memory as m
            assert m.save_fact is m.add
            assert m.remove_fact is m.remove
            assert m.get_facts is m.list_facts

    def test_content_stripped(self, tmp_path):
        with _patch_memory(tmp_path):
            import franki.memory as m
            m.add("  spaces  ")
            assert m.list_facts()[0]["content"] == "spaces"


class TestScopeHistory:
    def test_track_and_list(self, tmp_path):
        with _patch_memory(tmp_path):
            import franki.memory as m
            m.track_scope("192.168.1.0/24")
            assert "192.168.1.0/24" in m.list_scopes()

    def test_most_recent_first(self, tmp_path):
        with _patch_memory(tmp_path):
            import franki.memory as m
            m.track_scope("10.0.0.1")
            m.track_scope("10.0.0.2")
            scopes = m.list_scopes()
            assert scopes[0] == "10.0.0.2"

    def test_deduplication(self, tmp_path):
        with _patch_memory(tmp_path):
            import franki.memory as m
            m.track_scope("10.0.0.1")
            m.track_scope("10.0.0.2")
            m.track_scope("10.0.0.1")  # re-add
            scopes = m.list_scopes()
            assert scopes.count("10.0.0.1") == 1
            assert scopes[0] == "10.0.0.1"

    def test_max_scopes_cap(self, tmp_path):
        with _patch_memory(tmp_path):
            import franki.memory as m
            for i in range(10):
                m.track_scope(f"10.0.0.{i}")
            assert len(m.list_scopes()) <= 5

    def test_empty_scope_ignored(self, tmp_path):
        with _patch_memory(tmp_path):
            import franki.memory as m
            m.track_scope("")
            m.track_scope("   ")
            assert m.list_scopes() == []


class TestSkillUsage:
    def test_track_and_count(self, tmp_path):
        with _patch_memory(tmp_path):
            import franki.memory as m
            m.track_skill("coding")
            m.track_skill("coding")
            m.track_skill("pentest")
            counts = m.skill_usage_counts()
            assert counts["coding"] == 2
            assert counts["pentest"] == 1

    def test_most_used_skill(self, tmp_path):
        with _patch_memory(tmp_path):
            import franki.memory as m
            m.track_skill("soc")
            m.track_skill("soc")
            m.track_skill("coding")
            assert m.most_used_skill() == "soc"

    def test_most_used_returns_none_when_empty(self, tmp_path):
        with _patch_memory(tmp_path):
            import franki.memory as m
            assert m.most_used_skill() is None


class TestNoteHistory:
    def test_track_and_list(self, tmp_path):
        with _patch_memory(tmp_path):
            import franki.memory as m
            m.track_note("remember this")
            notes = m.list_notes()
            assert len(notes) == 1
            assert notes[0]["text"] == "remember this"

    def test_max_notes_cap(self, tmp_path):
        with _patch_memory(tmp_path):
            import franki.memory as m
            for i in range(15):
                m.track_note(f"note {i}")
            assert len(m.list_notes()) <= 10

    def test_newest_at_end(self, tmp_path):
        with _patch_memory(tmp_path):
            import franki.memory as m
            m.track_note("first")
            m.track_note("last")
            notes = m.list_notes()
            assert notes[-1]["text"] == "last"


class TestBuildMemoryPrompt:
    def test_empty_when_no_facts(self, tmp_path):
        with _patch_memory(tmp_path):
            import franki.memory as m
            assert m.build_memory_prompt() == ""

    def test_contains_facts(self, tmp_path):
        with _patch_memory(tmp_path):
            import franki.memory as m
            m.add("user is a pentester")
            prompt = m.build_memory_prompt()
            assert "pentester" in prompt

    def test_token_budget_respected(self, tmp_path):
        with _patch_memory(tmp_path):
            import franki.memory as m
            # Add many large facts
            for i in range(50):
                m.add("x" * 200)
            prompt = m.build_memory_prompt()
            # Should be under ~2000 chars (500 token budget × 4 chars/token)
            assert len(prompt) < 2500


class TestGetContextString:
    def test_empty_when_nothing_stored(self, tmp_path):
        with _patch_memory(tmp_path):
            import franki.memory as m
            assert m.get_context_string() == ""

    def test_includes_facts_when_present(self, tmp_path):
        with _patch_memory(tmp_path):
            import franki.memory as m
            m.add("I use arch linux")
            ctx = m.get_context_string()
            assert "arch linux" in ctx

    def test_includes_scopes_when_present(self, tmp_path):
        with _patch_memory(tmp_path):
            import franki.memory as m
            m.track_scope("10.10.10.0/24")
            ctx = m.get_context_string()
            assert "10.10.10.0/24" in ctx


class TestClearAll:
    def test_clears_everything(self, tmp_path):
        with _patch_memory(tmp_path):
            import franki.memory as m
            m.add("fact")
            m.track_scope("192.168.1.1")
            m.track_skill("coding")
            m.clear_all()
            assert m.list_facts() == []
            assert m.list_scopes() == []
            assert m.skill_usage_counts() == {}


class TestBuildMemoryPromptExtra:
    def test_single_huge_fact_returns_empty(self, tmp_path):
        """A fact larger than the token budget produces an empty string."""
        with _patch_memory(tmp_path):
            import franki.memory as m
            # Single fact exceeds budget (500 tokens * 4 chars = 2000 chars)
            m.add("x" * 2100)
            prompt = m.build_memory_prompt()
        assert prompt == ""


class TestGetContextStringExtra:
    def test_includes_skill_when_used(self, tmp_path):
        with _patch_memory(tmp_path):
            import franki.memory as m
            m.track_skill("pentest")
            m.track_skill("pentest")  # use twice so it's the top
            ctx = m.get_context_string()
        assert "pentest" in ctx

    def test_includes_notes_when_present(self, tmp_path):
        with _patch_memory(tmp_path):
            import franki.memory as m
            m.track_note("found open ports on 10.0.0.1")
            ctx = m.get_context_string()
        assert "10.0.0.1" in ctx


class TestCorruptFile:
    def test_corrupt_file_returns_empty(self, tmp_path):
        mem_file = tmp_path / "memory.json"
        mem_file.write_text("not json at all {{{{")
        with patch("franki.memory._MEMORY_FILE", mem_file):
            import franki.memory as m
            assert m.list_facts() == []

    def test_missing_keys_filled_in(self, tmp_path):
        mem_file = tmp_path / "memory.json"
        mem_file.write_text('{"facts": []}')  # missing other keys
        with patch("franki.memory._MEMORY_FILE", mem_file):
            import franki.memory as m
            data = m._load()
            assert "scope_history" in data
            assert "skill_usage" in data
            assert "note_history" in data
