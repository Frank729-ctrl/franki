"""ASCII block art logo for the franki CLI."""
from rich.console import Console
from rich.text import Text

from franki.ui.theme import GOLD as _GOLD

_DIM = "#3a3a3a"

# 5-row block art spelling FRANKI, each letter 6 chars wide (I: 4), 2-space gaps
_ART = [
    "██████  █████    ████   ██  ██  ██  ██  ████",
    "██      ██  ██  ██  ██  ███ ██  ██ ██    ██ ",
    "████    █████   ██████  ██████  ████     ██ ",
    "██      ██ ██   ██  ██  ██ ███  ██ ██    ██ ",
    "██      ██  ██  ██  ██  ██  ██  ██  ██  ████",
]


def render_logo(console: Console) -> None:
    if (console.width or 80) < 55:
        console.print(Text("  franki", style=f"bold {_GOLD}"))
        return
    console.print()
    for row in _ART:
        console.print(Text(f"  {row}", style=f"bold {_GOLD}"))
    console.print()
