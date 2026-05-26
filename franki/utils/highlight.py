from __future__ import annotations
import re

import rich.box
from rich.console import Console
from rich.syntax import Syntax
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from franki.ui.theme import GOLD, BG_CODE, TEXT_BODY, TEXT_CODE, TEXT_DIM

# ── Code fence parsing ────────────────────────────────────────────────────────

# Matches ``` optionally followed by a language tag, then a newline, content, closing ```
_FENCE_SPLIT = re.compile(r'(```\w*[ \t]*\n.*?```)', re.DOTALL)
_FENCE_PARSE = re.compile(r'```(\w*)[ \t]*\n(.*?)```', re.DOTALL)

# ── Markdown table parsing ────────────────────────────────────────────────────

# A table block: header row | separator row (|---| pattern) | 0+ data rows
# All lines must start with |.  We require at least header + separator.
_TABLE_SPLIT = re.compile(
    r'(\|[^\n]+\n\|[ :\-|]+\n(?:\|[^\n]+\n?)*)',
    re.MULTILINE,
)

# Normalise common language aliases to Pygments lexer names
_LANG_ALIASES: dict[str, str] = {
    "js":         "javascript",
    "ts":         "typescript",
    "py":         "python",
    "sh":         "bash",
    "shell":      "bash",
    "zsh":        "bash",
    "yml":        "yaml",
    "md":         "markdown",
    "dockerfile": "docker",
}


def _resolve_lang(lang: str) -> str:
    return _LANG_ALIASES.get(lang.lower(), lang.lower())


# ── Renderers ─────────────────────────────────────────────────────────────────

def _render_code_block(console: Console, lang: str, code: str) -> None:
    lexer = _resolve_lang(lang) if lang else "text"
    title = f"[{TEXT_DIM}]{lang}[/{TEXT_DIM}]" if lang else ""

    try:
        syntax = Syntax(
            code.rstrip(),
            lexer=lexer,
            theme="one-dark",
            background_color=BG_CODE,
            word_wrap=True,
        )
        console.print(Panel(
            syntax,
            border_style=GOLD,
            title=title,
            title_align="left",
            padding=(0, 1),
        ))
    except Exception:
        console.print(Panel(
            Text(code.rstrip(), style=TEXT_CODE),
            border_style=GOLD,
            title=title,
            title_align="left",
            padding=(0, 1),
        ))


def _render_table(console: Console, block: str) -> None:
    """Render a markdown table block as a Rich Table with gold borders."""
    lines = [ln.strip() for ln in block.strip().splitlines()]
    if len(lines) < 2:
        console.print(Text(block.strip(), style=TEXT_BODY))
        return

    # Validate separator line
    if not re.match(r'^[\|:\- ]+$', lines[1]):
        console.print(Text(block.strip(), style=TEXT_BODY))
        return

    headers = [c.strip() for c in lines[0].strip('|').split('|')]
    n_cols = len(headers)

    table = Table(
        box=rich.box.ROUNDED,
        border_style=GOLD,
        header_style=f"bold {GOLD}",
        show_header=True,
        padding=(0, 1),
    )
    for h in headers:
        table.add_column(h, style=TEXT_BODY)

    for line in lines[2:]:
        if not line.startswith('|'):
            continue
        cols = [c.strip() for c in line.strip('|').split('|')]
        # Pad or trim to match header count
        while len(cols) < n_cols:
            cols.append('')
        table.add_row(*cols[:n_cols])

    console.print(table)


# ── Main entry point ──────────────────────────────────────────────────────────

def render_response(console: Console, text: str, prefix: str = "") -> None:
    """
    Render an AI response with:
    - Syntax-highlighted fenced code blocks (gold border)
    - Markdown tables rendered as Rich tables (gold border)
    - Body text in muted grey

    If prefix is given it is inlined with the first output chunk (e.g. "  ● ").
    """
    # First split on code fences
    fence_parts = _FENCE_SPLIT.split(text)
    _first = [True]

    def _emit_text(chunk: str) -> None:
        stripped = chunk.strip("\n")
        if not stripped:
            return
        if _first[0] and prefix:
            _first[0] = False
            t = Text()
            t.append(prefix, style=GOLD)
            t.append(stripped, style=TEXT_BODY)
            console.print(t)
        else:
            console.print(Text(stripped, style=TEXT_BODY))

    def _emit_prefix_only() -> None:
        if _first[0] and prefix:
            _first[0] = False
            console.print(Text(prefix, style=GOLD))

    for part in fence_parts:
        if not part:
            continue

        m = _FENCE_PARSE.match(part)
        if m:
            _emit_prefix_only()
            _render_code_block(console, m.group(1), m.group(2))
            continue

        # Further split on markdown tables inside plain text segments
        table_parts = _TABLE_SPLIT.split(part)
        for tp in table_parts:
            if not tp:
                continue
            if _TABLE_SPLIT.match(tp):
                _emit_prefix_only()
                _render_table(console, tp)
            else:
                _emit_text(tp)

    console.print()
