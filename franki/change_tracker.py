"""
Track file changes made by the agent so they can be undone or diffed.
An instance is attached to each Session as .change_tracker.
"""
from __future__ import annotations
import difflib
from pathlib import Path


class ChangeTracker:
    def __init__(self) -> None:
        self._changes: list[dict] = []

    # ── Recording ─────────────────────────────────────────────────────────────

    def record(self, path: str, before: str | None, after: str, tool: str) -> None:
        """
        Snapshot a file change.
        before=None means the file was created (didn't exist before).
        """
        self._changes.append({
            "path":   path,
            "before": before,
            "after":  after,
            "tool":   tool,
        })

    # ── Undo ──────────────────────────────────────────────────────────────────

    def revert_last(self) -> str | None:
        """
        Revert the most recent change.
        Returns the path that was reverted, or None if nothing to revert.
        """
        if not self._changes:
            return None
        change = self._changes.pop()
        p = Path(change["path"])
        try:
            if change["before"] is None:
                if p.exists():
                    p.unlink()
            else:
                p.write_text(change["before"], encoding="utf-8")
        except OSError:
            return None
        return change["path"]

    def revert_all(self) -> list[str]:
        """Revert all changes in reverse order. Returns list of reverted paths."""
        reverted: list[str] = []
        while self._changes:
            r = self.revert_last()
            if r:
                reverted.append(r)
        return reverted

    # ── Diff ──────────────────────────────────────────────────────────────────

    def diff_summary(self) -> list[dict]:
        """Return a list of dicts with unified diff info for each change."""
        result = []
        for change in self._changes:
            before_lines = (change["before"] or "").splitlines(keepends=True)
            after_lines  = change["after"].splitlines(keepends=True)
            diff = list(difflib.unified_diff(
                before_lines, after_lines,
                fromfile=f"a/{change['path']}",
                tofile=f"b/{change['path']}",
                lineterm="",
            ))
            result.append({
                "path":          change["path"],
                "tool":          change["tool"],
                "diff":          diff,
                "lines_added":   sum(1 for l in diff if l.startswith("+") and not l.startswith("+++")),
                "lines_removed": sum(1 for l in diff if l.startswith("-") and not l.startswith("---")),
                "is_new_file":   change["before"] is None,
            })
        return result

    # ── Properties ────────────────────────────────────────────────────────────

    @property
    def count(self) -> int:
        return len(self._changes)

    @property
    def changed_paths(self) -> list[str]:
        seen: dict[str, None] = {}
        for c in self._changes:
            seen[c["path"]] = None
        return list(seen)
