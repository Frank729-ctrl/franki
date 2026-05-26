"""Per-project context — loads .franki.md walking up from the working directory."""
from __future__ import annotations
from pathlib import Path

CONTEXT_FILE = ".franki.md"


def load_project_context(start: Path | None = None) -> str | None:
    """
    Walk from start (default: cwd) up to home looking for .franki.md.
    Returns its contents or None if not found.
    """
    current = (start or Path.cwd()).resolve()
    home = Path.home().resolve()

    while True:
        candidate = current / CONTEXT_FILE
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
