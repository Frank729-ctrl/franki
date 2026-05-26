"""Tests for oneshot.py — _load_file, run_fix, run_review, run_commit, run_explain."""
import subprocess
import sys
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock


# ── _load_file ────────────────────────────────────────────────────────────────

class TestLoadFile:
    def test_returns_content_and_lang(self, tmp_path):
        from franki.oneshot import _load_file
        f = tmp_path / "main.py"
        f.write_text("print('hello')")
        content, lang = _load_file(str(f))
        assert "print('hello')" in content
        assert lang == "python"

    def test_js_extension_mapped(self, tmp_path):
        from franki.oneshot import _load_file
        f = tmp_path / "app.js"
        f.write_text("console.log(1)")
        _, lang = _load_file(str(f))
        assert lang == "javascript"

    def test_ts_extension_mapped(self, tmp_path):
        from franki.oneshot import _load_file
        f = tmp_path / "app.ts"
        f.write_text("const x: number = 1")
        _, lang = _load_file(str(f))
        assert lang == "typescript"

    def test_sh_extension_mapped(self, tmp_path):
        from franki.oneshot import _load_file
        f = tmp_path / "run.sh"
        f.write_text("#!/bin/bash")
        _, lang = _load_file(str(f))
        assert lang == "bash"

    def test_yml_extension_mapped(self, tmp_path):
        from franki.oneshot import _load_file
        f = tmp_path / "config.yml"
        f.write_text("key: value")
        _, lang = _load_file(str(f))
        assert lang == "yaml"

    def test_unknown_extension_uses_suffix(self, tmp_path):
        from franki.oneshot import _load_file
        f = tmp_path / "data.xyz"
        f.write_text("stuff")
        _, lang = _load_file(str(f))
        assert lang == "xyz"

    def test_no_extension_returns_text(self, tmp_path):
        from franki.oneshot import _load_file
        f = tmp_path / "Makefile"
        f.write_text("all: build")
        _, lang = _load_file(str(f))
        assert lang == "text"

    def test_missing_file_exits(self, tmp_path):
        from franki.oneshot import _load_file
        with pytest.raises(SystemExit):
            _load_file(str(tmp_path / "nonexistent.py"))

    def test_go_extension_mapped(self, tmp_path):
        from franki.oneshot import _load_file
        f = tmp_path / "main.go"
        f.write_text("package main")
        _, lang = _load_file(str(f))
        assert lang == "go"

    def test_rust_extension_mapped(self, tmp_path):
        from franki.oneshot import _load_file
        f = tmp_path / "lib.rs"
        f.write_text("fn main() {}")
        _, lang = _load_file(str(f))
        assert lang == "rust"


# ── run_fix / run_review / run_explain — usage errors ────────────────────────

class TestRunFixUsage:
    def test_no_args_exits(self):
        from franki.oneshot import run_fix
        with pytest.raises(SystemExit):
            run_fix([])

    def test_with_file_calls_run_oneshot(self, tmp_path):
        from franki.oneshot import run_fix
        f = tmp_path / "bug.py"
        f.write_text("x = 1/0")
        with patch("franki.oneshot._run_oneshot") as mock:
            run_fix([str(f)])
        assert mock.called

    def test_description_appended_to_message(self, tmp_path):
        from franki.oneshot import run_fix
        f = tmp_path / "app.py"
        f.write_text("code")
        captured = []
        with patch("franki.oneshot._run_oneshot", side_effect=lambda msgs, **kw: captured.extend(msgs)):
            run_fix([str(f), "divide", "by", "zero"])
        assert any("divide by zero" in m.get("content", "") for m in captured)

    def test_default_description_when_no_extra_args(self, tmp_path):
        from franki.oneshot import run_fix
        f = tmp_path / "app.py"
        f.write_text("code")
        captured = []
        with patch("franki.oneshot._run_oneshot", side_effect=lambda msgs, **kw: captured.extend(msgs)):
            run_fix([str(f)])
        # Default description "look for bugs and issues" should appear
        assert any("look for bugs" in m.get("content", "") for m in captured)


class TestRunReviewUsage:
    def test_no_args_exits(self):
        from franki.oneshot import run_review
        with pytest.raises(SystemExit):
            run_review([])

    def test_with_file_calls_run_oneshot(self, tmp_path):
        from franki.oneshot import run_review
        f = tmp_path / "auth.py"
        f.write_text("def login(): pass")
        with patch("franki.oneshot._run_oneshot") as mock:
            run_review([str(f)])
        assert mock.called


class TestRunExplainUsage:
    def test_no_args_exits(self):
        from franki.oneshot import run_explain
        with pytest.raises(SystemExit):
            run_explain([])

    def test_with_file_calls_run_oneshot(self, tmp_path):
        from franki.oneshot import run_explain
        f = tmp_path / "router.py"
        f.write_text("def route(): pass")
        with patch("franki.oneshot._run_oneshot") as mock:
            run_explain([str(f)])
        assert mock.called

    def test_message_contains_filename(self, tmp_path):
        from franki.oneshot import run_explain
        f = tmp_path / "complex_module.py"
        f.write_text("# code")
        captured = []
        with patch("franki.oneshot._run_oneshot", side_effect=lambda msgs, **kw: captured.extend(msgs)):
            run_explain([str(f)])
        assert any("complex_module.py" in m.get("content", "") for m in captured)


# ── run_commit ────────────────────────────────────────────────────────────────

class TestRunCommit:
    def test_no_diff_prints_message(self, capsys):
        from franki.oneshot import run_commit
        with patch("subprocess.check_output", return_value=b""):
            run_commit([])
        # Should print a "no git diff" message — no SystemExit
        # (it returns, not raises)

    def test_with_diff_calls_run_oneshot(self):
        from franki.oneshot import run_commit
        diff = b"diff --git a/f b/f\n+added line"
        with patch("subprocess.check_output", return_value=diff):
            with patch("franki.oneshot._run_oneshot") as mock:
                run_commit([])
        assert mock.called

    def test_large_diff_truncated(self):
        from franki.oneshot import run_commit
        large_diff = b"+" + b"x" * 15_000
        captured = []
        with patch("subprocess.check_output", return_value=large_diff):
            with patch("franki.oneshot._run_oneshot", side_effect=lambda msgs, **kw: captured.extend(msgs)):
                run_commit([])
        content = " ".join(m.get("content", "") for m in captured)
        assert "truncated" in content

    def test_git_not_found_falls_back_gracefully(self):
        from franki.oneshot import run_commit
        with patch("subprocess.check_output", side_effect=FileNotFoundError):
            # Should not raise — just print "no diff" message
            run_commit([])

    def test_staged_diff_preferred(self):
        from franki.oneshot import run_commit
        calls = []

        def check_output(cmd, **kwargs):
            calls.append(cmd)
            if "--cached" in cmd:
                return b"staged diff content"
            return b""

        with patch("subprocess.check_output", side_effect=check_output):
            with patch("franki.oneshot._run_oneshot"):
                run_commit([])

        # --cached should be tried first
        assert any("--cached" in c for c in calls)

    def test_falls_back_to_unstaged_when_no_staged(self):
        from franki.oneshot import run_commit
        calls = []

        def check_output(cmd, **kwargs):
            calls.append(cmd)
            if "--cached" in cmd:
                return b""  # nothing staged
            return b"unstaged diff"

        with patch("subprocess.check_output", side_effect=check_output):
            with patch("franki.oneshot._run_oneshot"):
                run_commit([])

        assert len(calls) == 2


# ── _run_oneshot setup guard ──────────────────────────────────────────────────

class TestRunOneshotGuard:
    def test_exits_when_no_providers(self):
        from franki.oneshot import _run_oneshot
        from franki.config import FrankiConfig

        with patch("franki.oneshot.load_config", return_value=FrankiConfig()):
            with patch("franki.oneshot.needs_setup", return_value=False):
                with pytest.raises(SystemExit):
                    _run_oneshot([{"role": "user", "content": "test"}])

    def test_exits_when_needs_setup(self):
        from franki.oneshot import _run_oneshot

        with patch("franki.oneshot.needs_setup", return_value=True):
            with pytest.raises(SystemExit):
                _run_oneshot([{"role": "user", "content": "test"}])

    def test_success_renders_response(self):
        from franki.oneshot import _run_oneshot
        from franki.config import FrankiConfig

        cfg = FrankiConfig(
            active_provider="groq",
            providers={"groq": {
                "api_key": "sk-test",
                "base_url": "https://x",
                "model": "m",
                "priority": 1,
                "key_required": True,
            }},
        )
        with patch("franki.oneshot.load_config", return_value=cfg), \
             patch("franki.oneshot.needs_setup", return_value=False), \
             patch("franki.utils.ai.ask_ai", return_value="AI response text"), \
             patch("franki.oneshot.render_response") as mock_render:
            _run_oneshot([{"role": "user", "content": "q"}])
        assert mock_render.called

    def test_ask_ai_error_exits(self):
        from franki.oneshot import _run_oneshot
        from franki.config import FrankiConfig

        cfg = FrankiConfig(
            active_provider="groq",
            providers={"groq": {
                "api_key": "sk-test",
                "base_url": "https://x",
                "model": "m",
                "priority": 1,
                "key_required": True,
            }},
        )
        with patch("franki.oneshot.load_config", return_value=cfg), \
             patch("franki.oneshot.needs_setup", return_value=False), \
             patch("franki.utils.ai.ask_ai", side_effect=Exception("no providers")):
            with pytest.raises(SystemExit):
                _run_oneshot([{"role": "user", "content": "q"}])


class TestLoadFileReadError:
    def test_read_text_exception_exits(self, tmp_path):
        from franki.oneshot import _load_file
        f = tmp_path / "locked.py"
        f.write_text("code")
        with patch.object(Path, "read_text", side_effect=PermissionError("access denied")):
            with pytest.raises(SystemExit):
                _load_file(str(f))
