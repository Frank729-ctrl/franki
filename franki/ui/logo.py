from rich.console import Console
from rich.text import Text
from rich.columns import Columns

GOLD = "#d4a853"
TEXT_MAIN = "#e8e0d0"
TEXT_DIM = "#555555"

LOGO_LINES = [
    "[bold #d4a853]█████[/]",
    "[bold #d4a853]█[/]    ",
    "[bold #d4a853]████[/] ",
    "[bold #d4a853]█[/]    ",
    "[bold #d4a853]█[/]    ",
]

WORDMARK = f"[bold {TEXT_MAIN}]franki[/]"
TAGLINE = f"[{GOLD}]AI CLI ASSISTANT[/]"
DIVIDER = f"[{TEXT_DIM}]──────────────────────────────[/]"
SUBLINE = f"[{TEXT_DIM}]coding · pentesting · soc · ceh[/]"

SIDE_LINES = [WORDMARK, TAGLINE, DIVIDER, SUBLINE, ""]


def render_logo(console: Console) -> None:
    for i, logo_line in enumerate(LOGO_LINES):
        side = SIDE_LINES[i] if i < len(SIDE_LINES) else ""
        console.print(f"  {logo_line}  {side}")
