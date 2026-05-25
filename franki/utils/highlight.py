import re
from rich.console import Console
from rich.syntax import Syntax
from rich.panel import Panel
from rich.text import Text

GOLD      = "#d4a853"
BG_CODE   = "#141414"
TEXT_BODY = "#a8a8a8"
TEXT_CODE = "#c0bab0"
TEXT_DIM  = "#555555"

# Matches ``` optionally followed by a language tag, then a newline, content, closing ```
_FENCE_SPLIT = re.compile(r'(```\w*[ \t]*\n.*?```)', re.DOTALL)
_FENCE_PARSE = re.compile(r'```(\w*)[ \t]*\n(.*?)```', re.DOTALL)

# Normalise common aliases to Pygments lexer names
_LANG_ALIASES: dict[str, str] = {
    "js": "javascript",
    "ts": "typescript",
    "py": "python",
    "sh": "bash",
    "shell": "bash",
    "zsh": "bash",
    "yml": "yaml",
    "md": "markdown",
    "dockerfile": "docker",
}


def _resolve_lang(lang: str) -> str:
    return _LANG_ALIASES.get(lang.lower(), lang.lower())


def render_response(console: Console, text: str) -> None:
    """
    Render an AI response with syntax-highlighted code blocks.
    Non-code text is printed in muted grey; code blocks get a gold border.
    """
    parts = _FENCE_SPLIT.split(text)

    for part in parts:
        if not part:
            continue

        m = _FENCE_PARSE.match(part)
        if m:
            _render_code_block(console, m.group(1), m.group(2))
        else:
            stripped = part.strip("\n")
            if stripped:
                console.print(Text(stripped, style=TEXT_BODY))
    console.print()


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
        # Unknown / unsupported lexer — fall back to plain
        console.print(Panel(
            Text(code.rstrip(), style=TEXT_CODE),
            border_style=GOLD,
            title=title,
            title_align="left",
            padding=(0, 1),
        ))
