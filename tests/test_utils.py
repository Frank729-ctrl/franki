"""Tests for utils/shell.py, utils/files.py, utils/highlight.py, ui/tips.py, ui/logo.py."""
import pytest
from pathlib import Path
from unittest.mock import patch
from io import StringIO


# ── shell.py ──────────────────────────────────────────────────────────────────

class TestRunCommand:
    def test_simple_command(self):
        from franki.utils.shell import run_command
        stdout, stderr, rc = run_command("echo hello")
        assert "hello" in stdout
        assert rc == 0

    def test_failing_command(self):
        from franki.utils.shell import run_command
        _, _, rc = run_command("exit 1")
        assert rc == 1

    def test_stderr_captured(self):
        from franki.utils.shell import run_command
        stdout, stderr, rc = run_command("echo err >&2")
        assert "err" in stderr or "err" in stdout  # shell-dependent

    def test_nonexistent_command(self):
        from franki.utils.shell import run_command
        stdout, stderr, rc = run_command("this_command_does_not_exist_xyz")
        assert rc != 0

    def test_returns_three_tuple(self):
        from franki.utils.shell import run_command
        result = run_command("echo x")
        assert len(result) == 3

    def test_timeout_returns_error(self):
        from franki.utils.shell import run_command
        import franki.utils.shell as shell_mod
        with patch.object(shell_mod, "_TIMEOUT", 0):
            stdout, stderr, rc = run_command("sleep 10")
            assert rc == 1
            assert "timed out" in stderr or rc == 1


class TestBuildAiPrompt:
    def test_includes_command(self):
        from franki.utils.shell import build_ai_prompt
        msg = build_ai_prompt("ls -la", "total 10", "", 0)
        assert "`ls -la`" in msg

    def test_includes_stdout(self):
        from franki.utils.shell import build_ai_prompt
        msg = build_ai_prompt("cat file", "file content here", "", 0)
        assert "file content here" in msg

    def test_includes_stderr(self):
        from franki.utils.shell import build_ai_prompt
        msg = build_ai_prompt("bad cmd", "", "error: not found", 1)
        assert "error: not found" in msg

    def test_includes_exit_code_when_nonzero(self):
        from franki.utils.shell import build_ai_prompt
        msg = build_ai_prompt("cmd", "", "", 2)
        assert "2" in msg

    def test_no_exit_code_when_zero(self):
        from franki.utils.shell import build_ai_prompt
        msg = build_ai_prompt("cmd", "ok", "", 0)
        assert "Exit code: 0" not in msg

    def test_ends_with_analysis_request(self):
        from franki.utils.shell import build_ai_prompt
        msg = build_ai_prompt("cmd", "", "", 0)
        assert "analyse" in msg.lower()


# ── files.py ─────────────────────────────────────────────────────────────────

class TestResolveFiles:
    def test_no_refs_unchanged(self):
        from franki.utils.files import resolve_files
        msg, errors = resolve_files("just a plain message")
        assert msg == "just a plain message"
        assert errors == []

    def test_injects_file_content(self, tmp_path):
        from franki.utils.files import resolve_files
        f = tmp_path / "test.py"
        f.write_text("print('hello')")
        msg, errors = resolve_files(f"review @{f}")
        assert "print('hello')" in msg
        assert errors == []

    def test_missing_file_gives_error(self):
        from franki.utils.files import resolve_files
        msg, errors = resolve_files("read @/nonexistent_file_xyz.txt")
        assert len(errors) == 1
        assert "not found" in errors[0]

    def test_ref_token_stripped_from_message(self, tmp_path):
        from franki.utils.files import resolve_files
        f = tmp_path / "code.py"
        f.write_text("x = 1")
        msg, _ = resolve_files(f"explain @{f} please")
        assert f"@{f}" not in msg

    def test_text_preserved_after_injection(self, tmp_path):
        from franki.utils.files import resolve_files
        f = tmp_path / "a.py"
        f.write_text("code")
        msg, _ = resolve_files(f"@{f} explain this")
        assert "explain this" in msg

    def test_multiple_refs(self, tmp_path):
        from franki.utils.files import resolve_files
        f1 = tmp_path / "a.py"
        f2 = tmp_path / "b.py"
        f1.write_text("file_a_content")
        f2.write_text("file_b_content")
        msg, errors = resolve_files(f"diff @{f1} @{f2}")
        assert "file_a_content" in msg
        assert "file_b_content" in msg
        assert errors == []

    def test_language_in_code_fence(self, tmp_path):
        from franki.utils.files import resolve_files
        f = tmp_path / "script.py"
        f.write_text("pass")
        msg, _ = resolve_files(f"@{f}")
        assert "```py" in msg


# ── highlight.py ─────────────────────────────────────────────────────────────

class TestRenderResponse:
    def _make_console(self):
        from rich.console import Console
        return Console(file=StringIO(), highlight=False, width=100)

    def test_plain_text_renders(self):
        from franki.utils.highlight import render_response
        c = self._make_console()
        render_response(c, "Hello world")
        output = c.file.getvalue()
        assert "Hello world" in output

    def test_code_block_renders(self):
        from franki.utils.highlight import render_response
        c = self._make_console()
        render_response(c, "Here:\n```python\nx = 1\n```")
        output = c.file.getvalue()
        assert "x = 1" in output

    def test_unknown_lang_doesnt_crash(self):
        from franki.utils.highlight import render_response
        c = self._make_console()
        render_response(c, "```xyzfakelang\nsome code\n```")
        output = c.file.getvalue()
        assert "some code" in output

    def test_empty_text_no_crash(self):
        from franki.utils.highlight import render_response
        c = self._make_console()
        render_response(c, "")  # should not raise

    def test_multiple_code_blocks(self):
        from franki.utils.highlight import render_response
        c = self._make_console()
        render_response(c, "First:\n```py\na=1\n```\nThen:\n```js\nb=2\n```")
        output = c.file.getvalue()
        assert "a=1" in output
        assert "b=2" in output

    def test_lang_alias_resolution(self):
        from franki.utils.highlight import _resolve_lang
        assert _resolve_lang("js") == "javascript"
        assert _resolve_lang("ts") == "typescript"
        assert _resolve_lang("py") == "python"
        assert _resolve_lang("sh") == "bash"
        assert _resolve_lang("yml") == "yaml"

    def test_unknown_lang_returned_unchanged(self):
        from franki.utils.highlight import _resolve_lang
        assert _resolve_lang("RUST") == "rust"
        assert _resolve_lang("UNKNOWN_LANG") == "unknown_lang"

    def test_prefix_inlined_with_first_text_chunk(self):
        from franki.utils.highlight import render_response
        c = self._make_console()
        render_response(c, "Hello world", prefix="  ● ")
        output = c.file.getvalue()
        assert "●" in output
        assert "Hello world" in output

    def test_prefix_on_own_line_when_first_chunk_is_code(self):
        from franki.utils.highlight import render_response
        c = self._make_console()
        render_response(c, "```python\nx = 1\n```", prefix="  ● ")
        output = c.file.getvalue()
        assert "●" in output
        assert "x = 1" in output

    def test_empty_prefix_unchanged(self):
        from franki.utils.highlight import render_response
        c = self._make_console()
        render_response(c, "Hello world", prefix="")
        output = c.file.getvalue()
        assert "Hello world" in output


# ── tips.py ───────────────────────────────────────────────────────────────────

class TestTips:
    def test_get_random_tip_returns_string(self):
        from franki.ui.tips import get_random_tip, TIPS
        tip = get_random_tip()
        assert isinstance(tip, str)
        assert len(tip) > 10

    def test_all_tips_are_strings(self):
        from franki.ui.tips import TIPS
        for tip in TIPS:
            assert isinstance(tip, str)

    def test_no_stale_references(self):
        from franki.ui.tips import TIPS
        stale = ["/quiz", "/connect delkaai", "CEH", "DelkaAI"]
        for tip in TIPS:
            for word in stale:
                assert word not in tip, f"Stale ref '{word}' in tip: {tip}"

    def test_tips_list_non_empty(self):
        from franki.ui.tips import TIPS
        assert len(TIPS) >= 5


# ── logo.py ───────────────────────────────────────────────────────────────────

class TestLogo:
    def test_render_logo_no_crash(self):
        from rich.console import Console
        from franki.ui.logo import render_logo, _ART
        c = Console(file=StringIO(), highlight=False, width=100)
        render_logo(c)
        output = c.file.getvalue()
        assert len(output) > 0

    def test_art_has_five_rows(self):
        from franki.ui.logo import _ART
        assert len(_ART) == 5

    def test_art_rows_contain_blocks(self):
        from franki.ui.logo import _ART
        for row in _ART:
            assert "█" in row

    def test_all_rows_same_length(self):
        from franki.ui.logo import _ART
        lengths = [len(row) for row in _ART]
        assert max(lengths) - min(lengths) <= 1  # allow ±1 for trailing space

    def test_narrow_terminal_shows_text_fallback(self):
        from rich.console import Console
        from franki.ui.logo import render_logo
        c = Console(file=StringIO(), highlight=False, width=40)
        render_logo(c)
        output = c.file.getvalue()
        assert "franki" in output
        # Should NOT render block art on a 40-col terminal
        assert "█" not in output


# ── version_check.py ─────────────────────────────────────────────────────────

class TestVersionCheck:
    def test_is_newer_true(self):
        from franki.ui.version_check import _is_newer
        assert _is_newer("0.2.0", "0.1.9") is True
        assert _is_newer("1.0.0", "0.9.9") is True
        assert _is_newer("0.1.3", "0.1.2") is True

    def test_is_newer_false(self):
        from franki.ui.version_check import _is_newer
        assert _is_newer("0.1.2", "0.1.2") is False
        assert _is_newer("0.1.1", "0.1.2") is False

    def test_parse_valid(self):
        from franki.ui.version_check import _parse
        assert _parse("1.2.3") == (1, 2, 3)
        assert _parse("0.1.9") == (0, 1, 9)

    def test_parse_invalid_returns_zero(self):
        from franki.ui.version_check import _parse
        assert _parse("not.a.version") == (0,)

    def test_pypi_url_correct_package(self):
        from franki.ui.version_check import _PYPI_URL
        assert "franki-cli" in _PYPI_URL

    def test_start_version_check_no_crash(self):
        from franki.ui.version_check import start_version_check
        called = []
        # Should not raise even if httpx fails
        start_version_check("0.1.2", lambda c, l: called.append((c, l)))
        # Thread is daemon — just verify it doesn't throw
