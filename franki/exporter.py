from __future__ import annotations
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from rich.console import Console
from rich.text import Text

if TYPE_CHECKING:
    from franki.config import FrankiConfig
    from franki.session import Session

console = Console()
GOLD     = "#d4a853"
TEXT_DIM = "#555555"


def _resolve_export_dir(cfg: "FrankiConfig") -> Path | None:
    """
    Return a writable export directory.
    Falls back to asking the user if the configured path doesn't exist.
    """
    from franki.config import save_config

    export_dir = Path(cfg.export_path).expanduser()
    if export_dir.exists():
        return export_dir

    # Try to create it
    try:
        export_dir.mkdir(parents=True, exist_ok=True)
        return export_dir
    except Exception:
        pass

    console.print(Text(f"  export path not found: {export_dir}", style="yellow"))
    console.print(Text("  enter a path (or press Enter to cancel): ", style=TEXT_DIM), end="")
    try:
        custom = input("").strip()
    except (KeyboardInterrupt, EOFError):
        console.print()
        return None

    if not custom:
        return None

    custom_dir = Path(custom).expanduser()
    try:
        custom_dir.mkdir(parents=True, exist_ok=True)
    except Exception as exc:
        console.print(Text(f"  could not create directory: {exc}", style="red"))
        return None

    cfg.export_path = custom
    save_config(cfg)
    return custom_dir


def export_session(session: "Session", cfg: "FrankiConfig") -> str | None:
    export_dir = _resolve_export_dir(cfg)
    if not export_dir:
        return None

    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M")
    filepath = export_dir / f"franki_{timestamp}.md"

    lines: list[str] = [
        f"# Franki Session — {timestamp}\n",
        f"\n> skill: {session.skill}",
    ]
    if session.scope:
        lines.append(f"  scope: {session.scope}")
    lines.append("\n\n---\n\n")

    for msg in session.history_display():
        if msg["role"] == "user":
            lines.append(f"## User\n\n{msg['content']}\n\n")
        elif msg["role"] == "assistant":
            lines.append(f"## Franki\n\n{msg['content']}\n\n")

    filepath.write_text("".join(lines), encoding="utf-8")
    return str(filepath)


def save_note(text: str, cfg: "FrankiConfig") -> str | None:
    export_dir = _resolve_export_dir(cfg)
    if not export_dir:
        return None

    today    = datetime.now().strftime("%Y-%m-%d")
    time_str = datetime.now().strftime("%H:%M")
    filepath = export_dir / f"notes_{today}.md"

    entry = f"- [{time_str}] {text}\n"

    if not filepath.exists():
        filepath.write_text(f"# Notes — {today}\n\n{entry}", encoding="utf-8")
    else:
        with filepath.open("a", encoding="utf-8") as f:
            f.write(entry)

    return str(filepath)
