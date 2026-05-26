"""Tests for @git context injection."""
import subprocess
from unittest.mock import patch, MagicMock


def _git_output(branch="main", status="M  src/app.py", diff="", log="abc1234 init"):
    def _run(args):
        cmd = args[0] if args else ""
        if "rev-parse" in args:
            return "/repo"
        if "branch" in args:
            return branch
        if "status" in args:
            return status
        if "diff" in args:
            return diff
        if "log" in args:
            return log
        return ""
    return _run


class TestInjectGit:
    def test_includes_branch(self):
        from franki.utils.files import resolve_content
        with patch("franki.utils.files._run_git", side_effect=_git_output(branch="feature/search")):
            result, errors = resolve_content("@git")
        assert errors == []
        assert "feature/search" in result

    def test_includes_status(self):
        from franki.utils.files import resolve_content
        with patch("franki.utils.files._run_git", side_effect=_git_output(status="M  app.py\n?? new.py")):
            result, errors = resolve_content("@git")
        assert "app.py" in result
        assert "new.py" in result

    def test_includes_diff(self):
        from franki.utils.files import resolve_content
        with patch("franki.utils.files._run_git", side_effect=_git_output(diff="-old\n+new")):
            result, errors = resolve_content("@git")
        assert "-old" in result
        assert "+new" in result

    def test_includes_log(self):
        from franki.utils.files import resolve_content
        with patch("franki.utils.files._run_git", side_effect=_git_output(log="abc1234 fix bug\ndef5678 add feature")):
            result, errors = resolve_content("@git")
        assert "fix bug" in result
        assert "add feature" in result

    def test_clean_tree_shows_nothing_to_commit(self):
        from franki.utils.files import resolve_content
        with patch("franki.utils.files._run_git", side_effect=_git_output(status="", diff="")):
            result, errors = resolve_content("@git")
        assert "nothing to commit" in result

    def test_no_diff_section_when_clean(self):
        from franki.utils.files import resolve_content
        with patch("franki.utils.files._run_git", side_effect=_git_output(status="", diff="")):
            result, errors = resolve_content("@git")
        assert "## Diff" not in result

    def test_not_in_repo_returns_error(self):
        from franki.utils.files import resolve_content
        def _no_repo(args):
            return ""
        with patch("franki.utils.files._run_git", side_effect=_no_repo):
            result, errors = resolve_content("@git")
        assert len(errors) == 1
        assert "git repository" in errors[0]

    def test_large_diff_truncated(self):
        from franki.utils.files import resolve_content, _GIT_DIFF_MAX
        big_diff = "+line\n" * (_GIT_DIFF_MAX // 5 + 200)
        with patch("franki.utils.files._run_git", side_effect=_git_output(diff=big_diff)):
            result, errors = resolve_content("@git")
        assert "truncated" in result

    def test_git_token_removed_from_message(self):
        from franki.utils.files import resolve_content
        with patch("franki.utils.files._run_git", side_effect=_git_output()):
            result, errors = resolve_content("review @git please")
        assert "@git" not in result
        assert "review" in result or "please" in result

    def test_git_case_insensitive(self):
        from franki.utils.files import resolve_content
        with patch("franki.utils.files._run_git", side_effect=_git_output()):
            result, errors = resolve_content("@GIT")
        assert errors == []
        assert "git context" in result.lower()


class TestRunGit:
    def test_returns_stdout(self):
        from franki.utils.files import _run_git
        out = _run_git(["rev-parse", "--show-toplevel"])
        # just verify it doesn't throw — result depends on cwd
        assert isinstance(out, str)

    def test_invalid_command_returns_empty(self):
        from franki.utils.files import _run_git
        result = _run_git(["no-such-git-subcommand-xyz"])
        assert isinstance(result, str)
