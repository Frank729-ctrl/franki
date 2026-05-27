"""Per-project context — loads .franki.md or CLAUDE.md walking up from cwd."""
from __future__ import annotations
from pathlib import Path

CONTEXT_FILE = ".franki.md"
# Also recognised as project memory, same as Claude Code's convention.
_CLAUDE_FILES = ("CLAUDE.md", ".claude/CLAUDE.md")


def load_project_context(start: Path | None = None) -> str | None:
    """
    Walk from start (default: cwd) up to home looking for .franki.md or CLAUDE.md.
    .franki.md takes precedence; CLAUDE.md is a drop-in alternative so projects
    that already use Claude Code's convention work without any extra setup.
    Returns the file contents or None if no file is found.
    """
    current = (start or Path.cwd()).resolve()
    home = Path.home().resolve()

    while True:
        for name in (CONTEXT_FILE, *_CLAUDE_FILES):
            candidate = current / name
            if candidate.is_file():
                try:
                    content = candidate.read_text(encoding="utf-8").strip()
                    if content:
                        return content
                except OSError:
                    pass

        if current == home or current == current.parent:
            break
        current = current.parent

    return None
