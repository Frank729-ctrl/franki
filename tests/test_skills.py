"""Tests for skills.py — built-in skills, auto-detect, user-defined loading."""
import pytest
from pathlib import Path
from franki.skills import (
    BUILTIN_SKILLS,
    VALID_SKILLS,
    get_all_skill_names,
    get_system_prompt,
    detect_skill,
)


class TestBuiltinSkills:
    def test_expected_skills_present(self):
        for skill in ("coding", "pentest", "soc", "security"):
            assert skill in BUILTIN_SKILLS

    def test_ceh_removed(self):
        assert "ceh" not in BUILTIN_SKILLS

    def test_valid_skills_is_list_of_builtins(self):
        assert set(VALID_SKILLS) == set(BUILTIN_SKILLS.keys())

    def test_get_system_prompt_returns_string(self):
        for skill in BUILTIN_SKILLS:
            prompt = get_system_prompt(skill)
            assert isinstance(prompt, str)
            assert len(prompt) > 50

    def test_get_system_prompt_unknown_falls_back_to_coding(self):
        prompt = get_system_prompt("nonexistent_skill_xyz")
        coding_prompt = get_system_prompt("coding")
        assert prompt == coding_prompt

    def test_get_all_skill_names_includes_builtins(self):
        names = get_all_skill_names()
        for skill in BUILTIN_SKILLS:
            assert skill in names


class TestAutoDetect:
    @pytest.mark.parametrize("message,expected", [
        ("run nmap scan then exploit it with metasploit", "security"),
        ("do a ctf challenge with privilege escalation payload", "security"),
        ("analyze the splunk log for ioc indicators of compromise", "soc"),
        ("write an async fastapi route that returns json from a database schema", "coding"),
        ("lateral movement via pass the hash through active directory domain controller", "pentest"),
        ("how do I make coffee", None),
        ("what is 2+2", None),
        ("hello", None),
    ])
    def test_detect_skill(self, message, expected):
        result = detect_skill(message)
        assert result == expected, f"message={message!r}: expected {expected!r}, got {result!r}"

    def test_detect_requires_at_least_two_keywords(self):
        # One keyword alone should not trigger a switch
        result = detect_skill("nmap is a great tool")
        assert result is None  # only 1 security keyword

    def test_detect_returns_none_for_empty(self):
        assert detect_skill("") is None


class TestUserDefinedSkills:
    def test_user_skills_loaded_from_dir(self, tmp_path, monkeypatch):
        # Patch the skills dir to a temp location
        import franki.skills as skills_mod
        monkeypatch.setattr(skills_mod, "_SKILLS_DIR", tmp_path)

        skill_file = tmp_path / "devops.md"
        skill_file.write_text("You are a DevOps expert. Help with CI/CD and infrastructure.")

        names = get_all_skill_names()
        assert "devops" in names
        prompt = get_system_prompt("devops")
        assert "DevOps" in prompt

    def test_user_skill_filename_normalized(self, tmp_path, monkeypatch):
        import franki.skills as skills_mod
        monkeypatch.setattr(skills_mod, "_SKILLS_DIR", tmp_path)

        (tmp_path / "my skill.md").write_text("You are a custom skill assistant.")
        names = get_all_skill_names()
        assert "my_skill" in names

    def test_empty_md_file_ignored(self, tmp_path, monkeypatch):
        import franki.skills as skills_mod
        monkeypatch.setattr(skills_mod, "_SKILLS_DIR", tmp_path)

        (tmp_path / "empty.md").write_text("   ")
        names = get_all_skill_names()
        assert "empty" not in names

    def test_no_skills_dir_doesnt_crash(self, tmp_path, monkeypatch):
        import franki.skills as skills_mod
        nonexistent = tmp_path / "skills_that_dont_exist"
        monkeypatch.setattr(skills_mod, "_SKILLS_DIR", nonexistent)
        names = get_all_skill_names()
        # Should still have all builtins
        assert set(BUILTIN_SKILLS.keys()).issubset(set(names))
