"""
Terminal logo based on the franki_logo.svg mark.

The SVG shows:
  - A solid gold square (the main cursor-block mark)
  - Fading vertical bars extending right
  - Fading horizontal rows extending below
  - A cursor bar indicator (far right, rows 4-5)
  - Wordmark "franki" and a rule to the right
"""
from rich.console import Console
from rich.text import Text

# Colour palette from the SVG
_GOLD      = "#d4a853"   # solid block — 100%
_G60       = "#7a5218"   # vertical bars — ~60%
_G30       = "#3d2a0d"   # vertical bars — ~30%
_G35       = "#4d3414"   # fading rows below — ~35%
_G15       = "#261a0a"   # fading rows below — ~15%
_G20       = "#2a1d0b"   # right extension — ~20%
_G10       = "#160f06"   # right extension — ~10%
_CURSOR    = "#c49444"   # cursor indicator — ~90%
_WORDMARK  = "#e8e0d0"
_RULE      = "#2d2d2d"

# Each tuple: (left mark columns, right text column)
_ROWS: list[tuple[str, str]] = [
    (
        f"[bold {_GOLD}]████[/]  [{_G60}]██[/]  [{_G30}]██[/]",
        f"  [bold {_WORDMARK}]franki[/]",
    ),
    (
        f"[bold {_GOLD}]████[/]  [{_G60}]██[/]  [{_G30}]██[/]",
        f"  [{_RULE}]──────────────────────[/]",
    ),
    (
        f"[bold {_GOLD}]████[/]  [{_G60}]██[/]  [{_G30}]██[/]",
        "",
    ),
    (
        f"[{_G35}]████[/]  [{_G20}]████████████[/]",
        f"     [{_CURSOR}]▌[/]",
    ),
    (
        f"[{_G15}]████[/]  [{_G10}]████████[/]    ",
        f"     [{_CURSOR}]▌[/]",
    ),
]


def render_logo(console: Console) -> None:
    for left, right in _ROWS:
        line = Text.from_markup(f"  {left}{right}")
        console.print(line)
