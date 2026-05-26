"""Tests for franki/project_context.py."""
import pytest
from pathlib import Path
from unittest.mock import patch


class TestLoadProjectContext:
    def test_finds_file_in_cwd(self, tmp_path):
        from franki.project_context import load_project_context
        (tmp_path / ".franki.md").write_text("# My Project\nsome context")
        result = load_project_context(tmp_path)
        assert result == "# My Project\nsome context"

    def test_finds_file_in_parent(self, tmp_path):
        from franki.project_context import load_project_context
        (tmp_path / ".franki.md").write_text("parent context")
        child = tmp_path / "src" / "module"
        child.mkdir(parents=True)
        result = load_project_context(child)
        assert result == "parent context"

    def test_returns_none_when_not_found(self, tmp_path):
        from franki.project_context import load_project_context
        sub = tmp_path / "deep" / "nested"
        sub.mkdir(parents=True)
        result = load_project_context(sub)
        assert result is None

    def test_empty_file_returns_none(self, tmp_path):
        from franki.project_context import load_project_context
        (tmp_path / ".franki.md").write_text("   \n  ")
        result = load_project_context(tmp_path)
        assert result is None

    def test_oserror_skipped_continues_up(self, tmp_path):
        from franki.project_context import load_project_context
        child = tmp_path / "child"
        child.mkdir()
        child_ctx = child / ".franki.md"
        child_ctx.write_text("child")
        parent_ctx = tmp_path / ".franki.md"
        parent_ctx.write_text("parent")

        orig_read_text = Path.read_text

        def fail_on_child(self, **kwargs):
            if self == child_ctx:
                raise OSError("permission denied")
            return orig_read_text(self, **kwargs)

        with patch.object(Path, "read_text", fail_on_child):
            result = load_project_context(child)
        # child read fails → walk up → find parent
        assert result == "parent"

    def test_stops_at_home(self, tmp_path):
        from franki.project_context import load_project_context
        with patch("franki.project_context.Path.home", return_value=tmp_path):
            result = load_project_context(tmp_path)
        assert result is None

    def test_stops_at_filesystem_root(self, tmp_path):
        from franki.project_context import load_project_context
        # Patch home to something unreachable so it hits the root boundary
        with patch("franki.project_context.Path.home", return_value=Path("/nonexistent_home_xyz")):
            # Just ensure it doesn't loop forever and returns None
            result = load_project_context(Path("/"))
        assert result is None

    def test_strips_whitespace(self, tmp_path):
        from franki.project_context import load_project_context
        (tmp_path / ".franki.md").write_text("\n\n  context content  \n\n")
        result = load_project_context(tmp_path)
        assert result == "context content"

    def test_uses_cwd_when_start_is_none(self, tmp_path):
        from franki.project_context import load_project_context
        (tmp_path / ".franki.md").write_text("cwd context")
        with patch("franki.project_context.Path.cwd", return_value=tmp_path):
            result = load_project_context(None)
        assert result == "cwd context"
