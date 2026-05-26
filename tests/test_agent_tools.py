"""Tests for franki/agent/tools.py — tool execution."""
import subprocess
import pytest
from pathlib import Path
from unittest.mock import patch


# ── read_file ─────────────────────────────────────────────────────────────────

class TestReadFile:
    def test_reads_small_file(self, tmp_path):
        from franki.agent.tools import execute_tool
        f = tmp_path / "hello.py"
        f.write_text("print('hi')")
        result = execute_tool("read_file", {"path": str(f)})
        assert "print('hi')" in result

    def test_adds_line_numbers_for_large_file(self, tmp_path):
        from franki.agent.tools import execute_tool
        f = tmp_path / "big.py"
        f.write_text("\n".join(f"line{i}" for i in range(70)))
        result = execute_tool("read_file", {"path": str(f)})
        assert "   1:" in result  # line numbers present

    def test_missing_file_returns_error(self, tmp_path):
        from franki.agent.tools import execute_tool
        result = execute_tool("read_file", {"path": str(tmp_path / "nope.py")})
        assert "not found" in result

    def test_directory_returns_error(self, tmp_path):
        from franki.agent.tools import execute_tool
        result = execute_tool("read_file", {"path": str(tmp_path)})
        assert "not a file" in result


# ── write_file ────────────────────────────────────────────────────────────────

class TestWriteFile:
    def test_creates_file(self, tmp_path):
        from franki.agent.tools import execute_tool
        p = tmp_path / "new.py"
        execute_tool("write_file", {"path": str(p), "content": "x = 1\ny = 2\n"})
        assert p.read_text() == "x = 1\ny = 2\n"

    def test_creates_parent_dirs(self, tmp_path):
        from franki.agent.tools import execute_tool
        p = tmp_path / "a" / "b" / "file.py"
        execute_tool("write_file", {"path": str(p), "content": "pass"})
        assert p.exists()

    def test_returns_confirmation(self, tmp_path):
        from franki.agent.tools import execute_tool
        p = tmp_path / "f.py"
        result = execute_tool("write_file", {"path": str(p), "content": "x\ny\nz"})
        assert "wrote" in result
        assert str(p) in result


# ── edit_file ─────────────────────────────────────────────────────────────────

class TestEditFile:
    def test_replaces_string(self, tmp_path):
        from franki.agent.tools import execute_tool
        f = tmp_path / "code.py"
        f.write_text("def foo():\n    return 1\n")
        execute_tool("edit_file", {"path": str(f), "old_str": "return 1", "new_str": "return 42"})
        assert "return 42" in f.read_text()

    def test_missing_file_returns_error(self, tmp_path):
        from franki.agent.tools import execute_tool
        result = execute_tool("edit_file", {
            "path": str(tmp_path / "x.py"), "old_str": "a", "new_str": "b"
        })
        assert "not found" in result

    def test_string_not_found_returns_error(self, tmp_path):
        from franki.agent.tools import execute_tool
        f = tmp_path / "code.py"
        f.write_text("hello world")
        result = execute_tool("edit_file", {
            "path": str(f), "old_str": "not here", "new_str": "x"
        })
        assert "not found" in result

    def test_ambiguous_string_returns_error(self, tmp_path):
        from franki.agent.tools import execute_tool
        f = tmp_path / "code.py"
        f.write_text("foo\nfoo\nfoo\n")
        result = execute_tool("edit_file", {
            "path": str(f), "old_str": "foo", "new_str": "bar"
        })
        assert "3 times" in result


# ── run_command ───────────────────────────────────────────────────────────────

class TestRunCommand:
    def test_captures_stdout(self):
        from franki.agent.tools import execute_tool
        result = execute_tool("run_command", {"command": "echo hello_world"})
        assert "hello_world" in result

    def test_captures_stderr(self):
        from franki.agent.tools import execute_tool
        result = execute_tool("run_command", {"command": "echo errline >&2"})
        assert "errline" in result

    def test_nonzero_exit_shown(self):
        from franki.agent.tools import execute_tool
        result = execute_tool("run_command", {"command": "exit 1"})
        assert "exit 1" in result

    def test_timeout_handled(self):
        from franki.agent.tools import execute_tool
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("cmd", 60)):
            result = execute_tool("run_command", {"command": "sleep 999"})
        assert "timed out" in result

    def test_no_output_returns_placeholder(self):
        from franki.agent.tools import execute_tool
        result = execute_tool("run_command", {"command": "true"})
        assert result  # not empty


# ── list_directory ────────────────────────────────────────────────────────────

class TestListDirectory:
    def test_lists_files(self, tmp_path):
        from franki.agent.tools import execute_tool
        (tmp_path / "a.py").write_text("")
        (tmp_path / "b.txt").write_text("")
        result = execute_tool("list_directory", {"path": str(tmp_path)})
        assert "a.py" in result
        assert "b.txt" in result

    def test_directories_have_slash(self, tmp_path):
        from franki.agent.tools import execute_tool
        (tmp_path / "subdir").mkdir()
        result = execute_tool("list_directory", {"path": str(tmp_path)})
        assert "subdir/" in result

    def test_missing_path_returns_error(self, tmp_path):
        from franki.agent.tools import execute_tool
        result = execute_tool("list_directory", {"path": str(tmp_path / "nope")})
        assert "not found" in result

    def test_hidden_files_excluded(self, tmp_path):
        from franki.agent.tools import execute_tool
        (tmp_path / ".hidden").write_text("")
        (tmp_path / "visible.py").write_text("")
        result = execute_tool("list_directory", {"path": str(tmp_path)})
        assert ".hidden" not in result
        assert "visible.py" in result


# ── search_files ──────────────────────────────────────────────────────────────

class TestSearchFiles:
    def test_finds_matching_files(self, tmp_path):
        from franki.agent.tools import execute_tool
        (tmp_path / "test_foo.py").write_text("")
        (tmp_path / "main.py").write_text("")
        result = execute_tool("search_files", {"pattern": "test_*.py", "directory": str(tmp_path)})
        assert "test_foo.py" in result
        assert "main.py" not in result

    def test_no_match_returns_message(self, tmp_path):
        from franki.agent.tools import execute_tool
        result = execute_tool("search_files", {"pattern": "*.go", "directory": str(tmp_path)})
        assert "no files" in result


# ── grep_files ────────────────────────────────────────────────────────────────

class TestGrepFiles:
    def test_finds_matches(self, tmp_path):
        from franki.agent.tools import execute_tool
        f = tmp_path / "code.py"
        f.write_text("def hello():\n    return 'world'\n")
        result = execute_tool("grep_files", {"query": "def hello", "directory": str(tmp_path)})
        assert "def hello" in result

    def test_no_match_returns_message(self, tmp_path):
        from franki.agent.tools import execute_tool
        (tmp_path / "empty.py").write_text("pass")
        result = execute_tool("grep_files", {"query": "nonexistent_xyz", "directory": str(tmp_path)})
        assert "no matches" in result

    def test_file_pattern_filters(self, tmp_path):
        from franki.agent.tools import execute_tool
        (tmp_path / "a.py").write_text("needle")
        (tmp_path / "b.txt").write_text("needle")
        result = execute_tool("grep_files", {
            "query": "needle", "directory": str(tmp_path), "file_pattern": "*.py"
        })
        assert "a.py" in result
        assert "b.txt" not in result


# ── unknown tool ──────────────────────────────────────────────────────────────

class TestUnknownTool:
    def test_unknown_tool_returns_error(self):
        from franki.agent.tools import execute_tool
        result = execute_tool("fly_to_moon", {})
        assert "unknown tool" in result

    def test_exception_in_tool_returns_error(self):
        from franki.agent.tools import execute_tool
        # missing required key triggers KeyError → caught by outer except
        result = execute_tool("read_file", {})
        assert "error" in result


# ── run_background / check_background / stop_background / list_backgrounds ────

class TestBackgroundTools:
    def test_run_background_returns_process_id(self):
        from franki.agent.tools import execute_tool, _BACKGROUNDS
        result = execute_tool("run_background", {"command": "echo bg_done"})
        assert "started" in result
        # extract id and clean up
        pid = result.split("[")[1].split("]")[0]
        import time; time.sleep(0.1)
        execute_tool("stop_background", {"process_id": pid})

    def test_check_background_gets_output(self):
        from franki.agent.tools import execute_tool
        import time
        start = execute_tool("run_background", {"command": "echo hello_bg"})
        pid = start.split("[")[1].split("]")[0]
        time.sleep(0.2)
        result = execute_tool("check_background", {"process_id": pid})
        assert "hello_bg" in result or "exited" in result
        execute_tool("stop_background", {"process_id": pid})

    def test_check_background_unknown_id(self):
        from franki.agent.tools import execute_tool
        result = execute_tool("check_background", {"process_id": "deadbeef"})
        assert "no background process" in result

    def test_stop_background_terminates(self):
        from franki.agent.tools import execute_tool, _BACKGROUNDS
        start = execute_tool("run_background", {"command": "sleep 60"})
        pid = start.split("[")[1].split("]")[0]
        assert pid in _BACKGROUNDS
        result = execute_tool("stop_background", {"process_id": pid})
        assert "stopped" in result
        assert pid not in _BACKGROUNDS

    def test_stop_background_unknown_id(self):
        from franki.agent.tools import execute_tool
        result = execute_tool("stop_background", {"process_id": "nope"})
        assert "no background process" in result

    def test_list_backgrounds_empty(self):
        from franki.agent.tools import execute_tool, _BACKGROUNDS
        _BACKGROUNDS.clear()
        result = execute_tool("list_backgrounds", {})
        assert "no background" in result

    def test_list_backgrounds_shows_running(self):
        from franki.agent.tools import execute_tool, _BACKGROUNDS
        _BACKGROUNDS.clear()
        start = execute_tool("run_background", {"command": "sleep 60"})
        pid = start.split("[")[1].split("]")[0]
        result = execute_tool("list_backgrounds", {})
        assert pid in result
        assert "sleep 60" in result
        execute_tool("stop_background", {"process_id": pid})

    def test_check_background_exited_process(self):
        from franki.agent.tools import execute_tool
        import time
        start = execute_tool("run_background", {"command": "true"})
        pid = start.split("[")[1].split("]")[0]
        time.sleep(0.2)
        result = execute_tool("check_background", {"process_id": pid})
        assert "exited" in result
        execute_tool("stop_background", {"process_id": pid})

    def test_list_background_ids_helper(self):
        from franki.agent.tools import execute_tool, _BACKGROUNDS, list_background_ids
        _BACKGROUNDS.clear()
        start = execute_tool("run_background", {"command": "sleep 1"})
        pid = start.split("[")[1].split("]")[0]
        assert pid in list_background_ids()
        execute_tool("stop_background", {"process_id": pid})


# ── list_directory edge cases ─────────────────────────────────────────────────

class TestListDirectoryExtra:
    def test_file_path_returns_not_a_directory(self, tmp_path):
        from franki.agent.tools import execute_tool
        f = tmp_path / "file.txt"
        f.write_text("x")
        result = execute_tool("list_directory", {"path": str(f)})
        assert "not a directory" in result

    def test_empty_directory_returns_placeholder(self, tmp_path):
        from franki.agent.tools import execute_tool
        result = execute_tool("list_directory", {"path": str(tmp_path)})
        assert "(empty)" in result


# ── grep_files edge cases ─────────────────────────────────────────────────────

class TestGrepFilesExtra:
    def test_skips_non_file_entries(self, tmp_path):
        from franki.agent.tools import execute_tool
        # subdir shouldn't match as a file
        (tmp_path / "subdir").mkdir()
        (tmp_path / "real.py").write_text("needle")
        result = execute_tool("grep_files", {"query": "needle", "directory": str(tmp_path)})
        assert "real.py" in result

    def test_caps_at_60_results(self, tmp_path):
        from franki.agent.tools import execute_tool
        # single file with 80 matching lines — result should be capped
        content = "\n".join("needle" for _ in range(80))
        (tmp_path / "big.py").write_text(content)
        result = execute_tool("grep_files", {"query": "needle", "directory": str(tmp_path)})
        lines = result.splitlines()
        assert len(lines) == 60

    def test_oserror_on_file_skipped(self, tmp_path):
        from franki.agent.tools import execute_tool
        from unittest.mock import patch
        (tmp_path / "a.py").write_text("needle")
        orig_read = Path.read_text
        def bad_read(self, **kw):
            raise OSError("permission denied")
        with patch.object(Path, "read_text", bad_read):
            result = execute_tool("grep_files", {"query": "needle", "directory": str(tmp_path)})
        assert "no matches" in result

    def test_skips_skip_dirs(self, tmp_path):
        from franki.agent.tools import execute_tool
        skip = tmp_path / "__pycache__"
        skip.mkdir()
        (skip / "cached.py").write_text("needle")
        (tmp_path / "normal.py").write_text("needle")
        result = execute_tool("grep_files", {"query": "needle", "directory": str(tmp_path)})
        assert "__pycache__" not in result
        assert "normal.py" in result

    def test_outer_exception_returns_error(self, tmp_path):
        from franki.agent.tools import execute_tool
        from unittest.mock import patch
        with patch("franki.agent.tools.Path.glob", side_effect=Exception("disk error")):
            result = execute_tool("grep_files", {"query": "x", "directory": str(tmp_path)})
        assert "error" in result
