"""
Purpose-built one-shot CLI commands:
  franki fix <file> [description]
  franki review <file>
  franki commit
  franki explain <file>

Each loads the file/diff, builds a focused prompt, streams the response,
and exits. No REPL, no session history.
"""
from __future__ import annotations
import subprocess
import sys
from pathlib import Path

from rich.console import Console
from rich.text import Text
from rich.rule import Rule

from franki.config import load_config, needs_setup
from franki.ui.theme import GOLD, TEXT_DIM, BORDER
from franki.utils.highlight import render_response

console = Console(highlight=False)


def _load_file(path_str: str) -> tuple[str, str]:
    """Return (content, language). Raises SystemExit on error."""
    p = Path(path_str).expanduser()
    if not p.exists():
        console.print(Text(f"  file not found: {p}", style="red"))
        sys.exit(1)
    try:
        content = p.read_text(encoding="utf-8", errors="replace")
    except Exception as exc:
        console.print(Text(f"  could not read {p}: {exc}", style="red"))
        sys.exit(1)
    suffix = p.suffix.lstrip(".")
    lang_map = {
        "py": "python", "js": "javascript", "ts": "typescript",
        "go": "go", "rs": "rust", "java": "java", "c": "c",
        "cpp": "cpp", "cs": "csharp", "rb": "ruby", "sh": "bash",
        "yaml": "yaml", "yml": "yaml", "json": "json", "md": "markdown",
    }
    return content, lang_map.get(suffix, suffix or "text")


def _run_oneshot(messages: list[dict], status: str = "working...") -> None:
    """Stream an AI response to the terminal and exit."""
    import asyncio
    from franki.utils.ai import ask_ai

    cfg = load_config()
    if needs_setup() or not cfg.providers:
        console.print(Text(
            "  no providers configured — run 'franki init' first",
            style="yellow",
        ))
        sys.exit(1)

    console.print()
    try:
        response = ask_ai(cfg, messages, console=console, status_text=status)
    except Exception as exc:
        console.print(Text(f"  error: {exc}", style="red"))
        sys.exit(1)

    console.print()
    render_response(console, response)
    console.print()


# ── franki fix ────────────────────────────────────────────────────────────────

def run_fix(args: list[str]) -> None:
    """franki fix <file> [description of the bug]"""
    if not args:
        console.print(Text(
            "  usage: franki fix <file> [description]\n"
            "  example: franki fix app.py 'index out of range in process_items'",
            style=TEXT_DIM,
        ))
        sys.exit(1)

    file_path = args[0]
    description = " ".join(args[1:]) if len(args) > 1 else "look for bugs and issues"

    content, lang = _load_file(file_path)
    console.print(Text(f"  fixing: {file_path}", style=TEXT_DIM))

    messages = [
        {
            "role": "system",
            "content": (
                "You are an expert software debugger. Analyse the code, identify the issue, "
                "and return a fixed version of the full file or the relevant diff. "
                "Explain the root cause briefly before showing the fix."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Issue: {description}\n\n"
                f"File: {file_path}\n"
                f"```{lang}\n{content}\n```\n\n"
                "Provide the fix."
            ),
        },
    ]
    _run_oneshot(messages, status_text="analysing and fixing...")


# ── franki review ─────────────────────────────────────────────────────────────

def run_review(args: list[str]) -> None:
    """franki review <file>"""
    if not args:
        console.print(Text(
            "  usage: franki review <file>\n"
            "  example: franki review auth.py",
            style=TEXT_DIM,
        ))
        sys.exit(1)

    file_path = args[0]
    content, lang = _load_file(file_path)
    console.print(Text(f"  reviewing: {file_path}", style=TEXT_DIM))

    messages = [
        {
            "role": "system",
            "content": (
                "You are a senior engineer doing a thorough code review. "
                "Cover: correctness, security issues, performance, readability, "
                "error handling, and any potential bugs. "
                "Use markdown with clear sections. Be specific and actionable."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Review this file: {file_path}\n\n"
                f"```{lang}\n{content}\n```"
            ),
        },
    ]
    _run_oneshot(messages, status_text="reviewing...")


# ── franki commit ─────────────────────────────────────────────────────────────

def run_commit(args: list[str]) -> None:
    """franki commit — generates a commit message from staged/unstaged diff."""
    try:
        diff = subprocess.check_output(
            ["git", "diff", "--cached"], stderr=subprocess.DEVNULL
        ).decode("utf-8", errors="replace").strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        diff = ""

    if not diff:
        try:
            diff = subprocess.check_output(
                ["git", "diff"], stderr=subprocess.DEVNULL
            ).decode("utf-8", errors="replace").strip()
        except (subprocess.CalledProcessError, FileNotFoundError):
            diff = ""

    if not diff:
        console.print(Text("  no git diff found — nothing to commit", style="yellow"))
        return

    # Truncate very large diffs
    if len(diff) > 12_000:
        diff = diff[:12_000] + "\n... (truncated)"

    console.print(Text("  generating commit message...", style=TEXT_DIM))

    messages = [
        {
            "role": "system",
            "content": (
                "You are an expert at writing git commit messages. "
                "Given a diff, write a concise, conventional commit message. "
                "Format: one subject line (≤72 chars, imperative mood), "
                "a blank line, then 2-4 bullet points explaining what changed and why. "
                "Output only the commit message, nothing else."
            ),
        },
        {
            "role": "user",
            "content": f"Generate a commit message for this diff:\n\n```diff\n{diff}\n```",
        },
    ]
    _run_oneshot(messages, status_text="writing commit message...")


# ── franki explain ────────────────────────────────────────────────────────────

def run_explain(args: list[str]) -> None:
    """franki explain <file> — explains what the file/function does."""
    if not args:
        console.print(Text(
            "  usage: franki explain <file>\n"
            "  example: franki explain router.py",
            style=TEXT_DIM,
        ))
        sys.exit(1)

    file_path = args[0]
    content, lang = _load_file(file_path)
    console.print(Text(f"  explaining: {file_path}", style=TEXT_DIM))

    messages = [
        {
            "role": "system",
            "content": (
                "You are a patient teacher explaining code to a developer. "
                "Explain what this code does, how it works, the key design decisions, "
                "and any non-obvious parts. Use plain language and markdown."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Explain this file: {file_path}\n\n"
                f"```{lang}\n{content}\n```"
            ),
        },
    ]
    _run_oneshot(messages, status_text="explaining...")
