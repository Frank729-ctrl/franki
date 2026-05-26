"""Lightweight feedback collection — local storage, periodic prompts."""
from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path

from franki import __version__

FEEDBACK_DIR  = Path.home() / ".config" / "franki"
FEEDBACK_FILE = FEEDBACK_DIR / "feedback.jsonl"


def save_feedback(text: str, skill: str = "", msgs: int = 0) -> None:
    FEEDBACK_DIR.mkdir(parents=True, exist_ok=True)
    entry = {
        "ts":      datetime.now(timezone.utc).isoformat(),
        "text":    text.strip(),
        "skill":   skill,
        "version": __version__,
        "msgs":    msgs,
    }
    with FEEDBACK_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def should_ask(session_count: int, msg_count: int) -> bool:
    """Ask for feedback every 5th session that had at least 3 messages."""
    return session_count > 0 and session_count % 5 == 0 and msg_count >= 3


def ask_feedback(console, skill: str = "", msgs: int = 0) -> None:
    """Print a brief optional feedback prompt; save the response if non-empty."""
    from rich.text import Text
    from franki.ui.theme import GOLD, TEXT_DIM
    console.print()
    console.print(Text("  what could franki do better? (Enter to skip)  ", style=TEXT_DIM), end="")
    try:
        text = input("").strip()
    except (KeyboardInterrupt, EOFError):
        console.print()
        return
    if text:
        save_feedback(text, skill=skill, msgs=msgs)
        console.print(Text("  noted, thanks.", style=GOLD))
