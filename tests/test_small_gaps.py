"""Targeted tests for specific uncovered lines in smaller modules."""
import pytest
from pathlib import Path
from io import StringIO
from unittest.mock import patch, MagicMock

from franki.config import FrankiConfig


# ── utils/files.py — missing lines 25, 33-34, 42-43 ─────────────────────────

class TestResolveFilesEdgeCases:
    def test_relative_ref_resolved_from_cwd(self, tmp_path, monkeypatch):
        from franki.utils.files import resolve_files
        monkeypatch.chdir(tmp_path)
        f = tmp_path / "relative.py"
        f.write_text("x = 1")
        msg, errors = resolve_files("@relative.py explain")
        assert "x = 1" in msg
        assert errors == []

    def test_ref_to_directory_gives_error(self, tmp_path):
        from franki.utils.files import resolve_files
        # tmp_path itself is a directory
        msg, errors = resolve_files(f"@{tmp_path}")
        assert len(errors) == 1
        assert "not a file" in errors[0]

    def test_unreadable_file_gives_error(self, tmp_path):
        from franki.utils.files import resolve_files
        f = tmp_path / "unreadable.py"
        f.write_text("code")
        # Mock read_text to raise
        with patch.object(Path, "read_text", side_effect=PermissionError("denied")):
            # Use a file that exists but can't be read
            msg, errors = resolve_files(f"@{f}")
        assert len(errors) == 1
        assert "denied" in errors[0]


# ── utils/highlight.py — missing lines 75-77 ─────────────────────────────────

class TestHighlightFallback:
    def test_unsupported_lexer_falls_back_to_plain(self):
        from franki.utils.highlight import _render_code_block
        from rich.console import Console
        from rich.syntax import Syntax

        buf = StringIO()
        console = Console(file=buf, highlight=False, width=100)

        # Patch Syntax to raise for any lexer
        with patch("franki.utils.highlight.Syntax", side_effect=Exception("unsupported lexer")):
            _render_code_block(console, "weird_lang", "some code here")

        output = buf.getvalue()
        assert "some code here" in output


# ── utils/shell.py — missing lines 23-24 ─────────────────────────────────────

class TestRunCommandException:
    def test_subprocess_exception_returns_error(self):
        from franki.utils.shell import run_command
        import subprocess

        with patch("subprocess.run", side_effect=OSError("exec failed")):
            stdout, stderr, rc = run_command("some_command")
        assert rc == 1
        assert "exec failed" in stderr


# ── exporter.py — missing lines 33-56, 62, 88 ────────────────────────────────

class TestExporterInteractiveFallback:
    def _make_bad_path(self, tmp_path):
        """A path that doesn't exist and can't be mkdir'd."""
        return "/proc/nonexistent_franki_test_dir/cannot_create"

    def test_export_returns_none_when_dir_fails_and_no_input(self, tmp_path):
        from franki.exporter import _resolve_export_dir
        cfg = FrankiConfig(export_path=self._make_bad_path(tmp_path))

        with patch("franki.exporter.input", return_value="", create=True):
            # EOF — input returns empty → returns None
            result = _resolve_export_dir(cfg)
        assert result is None

    def test_export_returns_none_on_eof(self, tmp_path):
        from franki.exporter import _resolve_export_dir
        cfg = FrankiConfig(export_path=self._make_bad_path(tmp_path))

        with patch("builtins.input", side_effect=EOFError):
            result = _resolve_export_dir(cfg)
        assert result is None

    def test_export_returns_none_on_keyboard_interrupt(self, tmp_path):
        from franki.exporter import _resolve_export_dir
        cfg = FrankiConfig(export_path=self._make_bad_path(tmp_path))

        with patch("builtins.input", side_effect=KeyboardInterrupt):
            result = _resolve_export_dir(cfg)
        assert result is None

    def test_export_custom_path_created(self, tmp_path):
        from franki.exporter import _resolve_export_dir
        custom_dir = tmp_path / "custom"
        cfg = FrankiConfig(export_path=self._make_bad_path(tmp_path))

        with patch("builtins.input", return_value=str(custom_dir)):
            with patch("franki.config.save_config"):
                result = _resolve_export_dir(cfg)
        assert result == custom_dir
        assert custom_dir.exists()

    def test_export_custom_path_bad_mkdir_returns_none(self, tmp_path):
        from franki.exporter import _resolve_export_dir
        cfg = FrankiConfig(export_path=self._make_bad_path(tmp_path))

        with patch("builtins.input", return_value="/proc/cannot_create_this"):
            result = _resolve_export_dir(cfg)
        assert result is None

    def test_export_session_returns_none_when_no_dir(self, tmp_path):
        from franki.exporter import export_session
        from franki.session import Session
        s = Session()
        cfg = FrankiConfig(export_path=self._make_bad_path(tmp_path))

        with patch("builtins.input", return_value=""):
            result = export_session(s, cfg)
        assert result is None

    def test_save_note_returns_none_when_no_dir(self, tmp_path):
        from franki.exporter import save_note
        cfg = FrankiConfig(export_path=self._make_bad_path(tmp_path))

        with patch("builtins.input", return_value=""):
            result = save_note("test note", cfg)
        assert result is None

    def test_export_session_with_scope_in_content(self, tmp_path):
        """Covers the session.scope branch in export_session."""
        from franki.exporter import export_session
        from franki.session import Session
        s = Session(skill="pentest")
        s.set_scope("10.0.0.1")
        cfg = FrankiConfig(export_path=str(tmp_path))
        path = export_session(s, cfg)
        assert path is not None
        content = Path(path).read_text()
        assert "10.0.0.1" in content


# ── ui/version_check.py — missing lines 25-31 ────────────────────────────────

class TestVersionCheckThread:
    def test_check_fires_on_update_when_newer(self):
        from franki.ui.version_check import start_version_check
        import threading
        import time

        called = []
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"info": {"version": "9.9.9"}}

        threads_started = []
        original_thread = threading.Thread

        def patched_thread(**kwargs):
            t = original_thread(**kwargs)
            threads_started.append(t)
            return t

        with patch("threading.Thread", side_effect=patched_thread):
            with patch("httpx.get", return_value=mock_resp):
                start_version_check("0.1.0", lambda c, l: called.append((c, l)))

        if threads_started:
            threads_started[-1].join(timeout=1.0)
        assert len(called) == 1
        assert called[0][1] == "9.9.9"

    def test_check_no_update_when_same_version(self):
        from franki.ui.version_check import start_version_check
        import threading
        import time

        called = []
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"info": {"version": "0.1.0"}}

        threads_started = []

        original_thread = threading.Thread

        def patched_thread(**kwargs):
            t = original_thread(**kwargs)
            threads_started.append(t)
            return t

        with patch("threading.Thread", side_effect=patched_thread):
            with patch("httpx.get", return_value=mock_resp):
                start_version_check("0.1.0", lambda c, l: called.append((c, l)))

        if threads_started:
            threads_started[-1].join(timeout=1.0)
        assert called == []  # not newer, so no callback

    def test_check_handles_network_error(self):
        from franki.ui.version_check import start_version_check
        import threading
        import time

        threads_started = []
        original_thread = threading.Thread

        def patched_thread(**kwargs):
            t = original_thread(**kwargs)
            threads_started.append(t)
            return t

        with patch("threading.Thread", side_effect=patched_thread):
            with patch("httpx.get", side_effect=Exception("network down")):
                start_version_check("0.1.0", lambda c, l: None)

        if threads_started:
            threads_started[-1].join(timeout=1.0)
        # Should not raise

    def test_check_handles_non_200_response(self):
        from franki.ui.version_check import start_version_check
        import threading
        import time

        threads_started = []
        original_thread = threading.Thread

        def patched_thread(**kwargs):
            t = original_thread(**kwargs)
            threads_started.append(t)
            return t

        called = []
        mock_resp = MagicMock()
        mock_resp.status_code = 404

        with patch("threading.Thread", side_effect=patched_thread):
            with patch("httpx.get", return_value=mock_resp):
                start_version_check("0.1.0", lambda c, l: called.append((c, l)))

        if threads_started:
            threads_started[-1].join(timeout=1.0)
        assert called == []


# ── franki/__init__.py — version fallback ────────────────────────────────────

class TestSkillsEmptyStem:
    def test_file_with_empty_stem_skipped(self, tmp_path):
        """A .md file whose stem becomes empty after normalization is skipped."""
        from franki.skills import _load_user_skills
        # Create a regular file and one that would have empty stem
        # A file named ".md" has empty stem in pathlib (stem="", suffix=".md")
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        (skills_dir / "valid.md").write_text("valid skill content")
        hidden = skills_dir / ".md"
        hidden.write_text("hidden content")
        with patch("franki.skills._SKILLS_DIR", skills_dir):
            result = _load_user_skills()
        # "valid" skill should be loaded; hidden file should be skipped
        assert "valid" in result
        assert "" not in result

    def test_empty_stem_via_mocked_glob(self):
        """Mock glob to return a path with an empty stem — hits the `if not name: continue` branch."""
        from franki.skills import _load_user_skills
        mock_path = MagicMock()
        mock_path.stem = ""  # empty stem → name becomes "" → skipped
        mock_dir = MagicMock()
        mock_dir.exists.return_value = True
        mock_dir.glob.return_value = [mock_path]  # single item — sorted needs no comparisons
        with patch("franki.skills._SKILLS_DIR", mock_dir):
            result = _load_user_skills()
        assert result == {}


class TestFrankiInit:
    def test_version_available(self):
        import franki
        assert hasattr(franki, "__version__")
        assert isinstance(franki.__version__, str)

    def test_version_fallback_on_package_not_found(self):
        import sys
        import importlib
        from importlib.metadata import PackageNotFoundError

        # Remove franki from sys.modules so we can reload it with patched metadata
        keys_to_remove = [k for k in sys.modules if k == "franki"]
        saved = {k: sys.modules.pop(k) for k in keys_to_remove}
        try:
            with patch("importlib.metadata.version", side_effect=PackageNotFoundError("franki")):
                import franki as franki_fresh
                version = franki_fresh.__version__
        finally:
            sys.modules.update(saved)
            # Force re-import of original
            import franki  # noqa

        assert version == "0.1.3"
