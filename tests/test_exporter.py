"""Tests for exporter.py — file I/O using tmp_path."""
import pytest
from pathlib import Path
from unittest.mock import patch
from franki.config import FrankiConfig
from franki.session import Session


def _cfg(tmp_path) -> FrankiConfig:
    return FrankiConfig(export_path=str(tmp_path))


class TestExportSession:
    def test_creates_file(self, tmp_path):
        from franki.exporter import export_session
        s = Session()
        s.add_user("hello")
        s.add_assistant("hi")
        cfg = _cfg(tmp_path)
        path = export_session(s, cfg)
        assert path is not None
        assert Path(path).exists()

    def test_file_contains_messages(self, tmp_path):
        from franki.exporter import export_session
        s = Session()
        s.add_user("my question")
        s.add_assistant("my answer")
        cfg = _cfg(tmp_path)
        path = export_session(s, cfg)
        content = Path(path).read_text()
        assert "my question" in content
        assert "my answer" in content

    def test_file_contains_skill(self, tmp_path):
        from franki.exporter import export_session
        s = Session(skill="pentest")
        cfg = _cfg(tmp_path)
        path = export_session(s, cfg)
        content = Path(path).read_text()
        assert "pentest" in content

    def test_file_contains_scope(self, tmp_path):
        from franki.exporter import export_session
        s = Session(skill="pentest")
        s.set_scope("10.0.0.1")
        cfg = _cfg(tmp_path)
        path = export_session(s, cfg)
        content = Path(path).read_text()
        assert "10.0.0.1" in content

    def test_markdown_extension(self, tmp_path):
        from franki.exporter import export_session
        s = Session()
        cfg = _cfg(tmp_path)
        path = export_session(s, cfg)
        assert path.endswith(".md")

    def test_creates_export_dir_if_missing(self, tmp_path):
        from franki.exporter import export_session
        new_dir = tmp_path / "new" / "subdir"
        cfg = FrankiConfig(export_path=str(new_dir))
        s = Session()
        path = export_session(s, cfg)
        assert path is not None
        assert new_dir.exists()

    def test_empty_session_still_exports(self, tmp_path):
        from franki.exporter import export_session
        s = Session()
        cfg = _cfg(tmp_path)
        path = export_session(s, cfg)
        assert path is not None


class TestSaveNote:
    def test_creates_note_file(self, tmp_path):
        from franki.exporter import save_note
        cfg = _cfg(tmp_path)
        path = save_note("important finding", cfg)
        assert path is not None
        assert Path(path).exists()

    def test_note_content_saved(self, tmp_path):
        from franki.exporter import save_note
        cfg = _cfg(tmp_path)
        save_note("SQL injection found", cfg)
        files = list(tmp_path.glob("notes_*.md"))
        assert len(files) == 1
        content = files[0].read_text()
        assert "SQL injection found" in content

    def test_multiple_notes_appended(self, tmp_path):
        from franki.exporter import save_note
        cfg = _cfg(tmp_path)
        save_note("first note", cfg)
        save_note("second note", cfg)
        files = list(tmp_path.glob("notes_*.md"))
        assert len(files) == 1
        content = files[0].read_text()
        assert "first note" in content
        assert "second note" in content

    def test_note_filename_format(self, tmp_path):
        from franki.exporter import save_note
        cfg = _cfg(tmp_path)
        path = save_note("test", cfg)
        name = Path(path).name
        assert name.startswith("notes_")
        assert name.endswith(".md")


class TestResolveExportDir:
    def test_existing_path_returned(self, tmp_path):
        from franki.exporter import _resolve_export_dir
        cfg = _cfg(tmp_path)
        result = _resolve_export_dir(cfg)
        assert result == tmp_path

    def test_nonexistent_path_created(self, tmp_path):
        from franki.exporter import _resolve_export_dir
        new = tmp_path / "auto_created"
        cfg = FrankiConfig(export_path=str(new))
        result = _resolve_export_dir(cfg)
        assert result == new
        assert new.exists()
