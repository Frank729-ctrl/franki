import asyncio
import re
import sys
from pathlib import Path

from rich.console import Console
from rich.text import Text
from rich.rule import Rule
from rich.live import Live
from rich.spinner import Spinner
from rich.columns import Columns
from prompt_toolkit import PromptSession
from prompt_toolkit.styles import Style as PTStyle
from prompt_toolkit.formatted_text import HTML

from franki import __version__
from franki.config import load_config, save_config, CONFIG_FILE, FrankiConfig
from franki.session import Session
from franki.commands import handle_command
from franki.skills import get_skill_icon
from franki.router import stream_with_fallback
from franki.ui.logo import render_logo
from franki.ui.tips import get_random_tip
from franki.ui.token_warning import warning_text
from franki.ui.version_check import start_version_check
from franki.utils.highlight import render_response
from franki.utils.files import resolve_files
from franki.utils.shell import run_command, build_ai_prompt

# ── Colour palette ─────────────────────────────────────────────────────────────
GOLD      = "#d4a853"
TEXT_BODY = "#a8a8a8"
TEXT_USER = "#c8c0b0"
TEXT_DIM  = "#555555"
BORDER    = "#2d2d2d"

console = Console(highlight=False)


def _render_splash(cfg: FrankiConfig) -> None:
    provider = cfg.get_active_provider()
    model = cfg.get_active_model_name()
    skill = cfg.active_skill
    cwd = str(Path.cwd())

    console.print()
    render_logo(console)
    console.print()
    console.print(Text(f"    {provider} / {model}  ·  {skill.capitalize()}", style=TEXT_BODY))
    console.print(Text(f"    {cwd}", style=TEXT_DIM))
    console.print(Text("    ● ● ●", style=GOLD))
    console.print(Rule(style=BORDER))

    tip = get_random_tip()
    console.print(Text("  tip  ", style=f"bold {GOLD}"), end="")
    console.print(tip)
    console.print()


def _print_skill_bar(
    cfg: FrankiConfig,
    scope: str | None = None,
    token_warn: str | None = None,
) -> None:
    icon = get_skill_icon(cfg.active_skill)
    provider = cfg.get_active_provider()
    model_name = cfg.get_active_model_name()
    short_model = model_name if len(model_name) <= 28 else model_name[:26] + "…"

    left = Text()
    left.append("  skill: [", style=TEXT_DIM)
    left.append(f"{icon} {cfg.active_skill}", style=GOLD)
    left.append("]", style=TEXT_DIM)

    if scope and cfg.active_skill == "pentest":
        left.append("  scope: [", style=TEXT_DIM)
        left.append(scope, style=GOLD)
        left.append("]", style=TEXT_DIM)

    left.append("  ·  model: [", style=TEXT_DIM)
    left.append(f"{provider} / {short_model}", style=GOLD)
    left.append("]", style=TEXT_DIM)

    if token_warn:
        right = Text(f"  {token_warn}", style="yellow")
    else:
        right = Text("use /skill or /model to change", style=TEXT_DIM)

    width = console.width or 80
    pad = max(2, width - len(left.plain) - len(right.plain) - 2)
    left.append(" " * pad)
    left.append_text(right)

    console.print(left)
    console.print(Rule(style=BORDER))


def _print_fallback_notice(from_model: str, to_model: str) -> None:
    console.print(Text(f"  ⇄ {from_model} rate limit — switching to {to_model}", style=TEXT_DIM))


def _count_tokens_approx(text: str) -> int:
    return max(1, len(text) // 4)


_SEARCH_KEYWORDS = re.compile(
    r'\b(latest|current|today|news)\b|CVE-\d{4}-\d{4,7}',
    re.IGNORECASE,
)


def _auto_search_query(message: str) -> str | None:
    """Return a search query if the message contains trigger keywords or a CVE ID."""
    m = _SEARCH_KEYWORDS.search(message)
    if not m:
        return None
    cve = re.search(r'CVE-\d{4}-\d{4,7}', message, re.IGNORECASE)
    if cve:
        return cve.group(0)
    return message[:200].strip()


def _run_auto_search(cfg: FrankiConfig, session: Session, query: str) -> None:
    """Silently inject web search results before the AI call. Fails silently."""
    from franki.utils.search import web_search, SearchError
    console.print(Text("  ⌕ searching the web for context...", style=TEXT_DIM))
    try:
        result = asyncio.run(web_search(cfg, query))
        session.add_user(result.as_context())
    except SearchError:
        pass


async def _stream_response(cfg: FrankiConfig, session: Session) -> str:
    full_response: list[str] = []
    token_count = [0]
    fallback_notice: list = [None]

    def on_fallback(from_m: str, to_m: str) -> None:
        fallback_notice[0] = (from_m, to_m)

    spinner = Spinner("dots", style=GOLD)

    with Live(console=console, refresh_per_second=12, transient=True) as live:
        def _update_spinner() -> None:
            t = Text()
            t.append(" franki is thinking...", style=TEXT_DIM)
            tc = f"{token_count[0]} tokens"
            width = console.width or 80
            pad = max(1, width - len(t.plain) - len(tc) - 2)
            t.append(" " * pad)
            t.append(tc, style=TEXT_DIM)
            live.update(Columns([spinner, t]))

        _update_spinner()

        async for chunk in stream_with_fallback(cfg, session.get_messages(), on_fallback=on_fallback):
            if fallback_notice[0]:
                from_m, to_m = fallback_notice[0]
                fallback_notice[0] = None
                live.stop()
                _print_fallback_notice(from_m, to_m)
                live.start()

            full_response.append(chunk)
            token_count[0] = _count_tokens_approx("".join(full_response))
            _update_spinner()

    response_text = "".join(full_response)
    console.print()
    render_response(console, response_text)
    return response_text


def _get_pt_session() -> PromptSession:
    style = PTStyle.from_dict({
        "prompt": f"{GOLD} bold",
        "": TEXT_USER,
    })
    return PromptSession(style=style)


def _check_api_keys(cfg: FrankiConfig) -> None:
    provider = cfg.get_active_provider()
    key = cfg.get_provider_key(provider)
    if not key:
        console.print()
        console.print(Text(
            f"  ⚠  No API key for '{provider}'. Run franki config to add keys.",
            style="yellow",
        ))
        console.print()


def _prompt_save_exit(session: Session, cfg: FrankiConfig) -> None:
    """Ask user whether to save session before exit. Never raises."""
    if not session.history_display():
        console.print(Text("  bye.", style=TEXT_DIM))
        return
    try:
        console.print()
        console.print(Text("  Save session before exiting? (y/n) ", style=TEXT_DIM), end="")
        choice = input("").strip().lower()
    except (KeyboardInterrupt, EOFError):
        console.print()
        return
    if choice == "y":
        try:
            from franki.exporter import export_session
            path = export_session(session, cfg)
            if path:
                console.print(Text(f"  saved → {path}", style=GOLD))
            else:
                console.print(Text("  export cancelled.", style=TEXT_DIM))
        except Exception as exc:
            console.print(Text(f"  could not save: {exc}", style="red"))
    console.print(Text("  bye.", style=TEXT_DIM))


def _run_repl(cfg: FrankiConfig) -> None:
    from franki.memory import get_context_string
    session = Session(skill=cfg.active_skill, memory_context=get_context_string())

    _render_splash(cfg)

    # Non-blocking version check — prints below splash if update found
    def _on_update(current: str, latest: str) -> None:
        console.print(Text(
            f"  update available: franki {current} → {latest}"
            "  ·  pip install -U franki",
            style="yellow",
        ))

    start_version_check(__version__, _on_update)

    _print_skill_bar(cfg)
    _check_api_keys(cfg)

    pt = _get_pt_session()
    bottom_toolbar = HTML(
        f'<style fg="{TEXT_DIM}">'
        "? /help · /skill · /model · /scope · /quiz · /mitre · /report · /export · /note · /clear · /exit"
        "</style>"
    )

    def _redraw_bar() -> None:
        scope = session.scope if cfg.active_skill == "pentest" else None
        stats = session.message_stats()
        warn = warning_text(stats["approx_tokens"], cfg.get_active_model_name())
        _print_skill_bar(cfg, scope=scope, token_warn=warn)

    while True:
        try:
            raw = pt.prompt(
                [("class:prompt", "›  ")],
                bottom_toolbar=bottom_toolbar,
            ).strip()
        except (KeyboardInterrupt, EOFError):
            console.print()
            _prompt_save_exit(session, cfg)
            break

        if not raw:
            continue

        # ── Slash commands ──────────────────────────────────────────────────
        if raw.startswith("/"):
            if raw.strip().lower() in ("/exit", "/quit", "/q"):
                console.print()
                _prompt_save_exit(session, cfg)
                break
            handle_command(raw, cfg, session, save_config, _redraw_bar)
            continue

        # ── Shell execution: !command ───────────────────────────────────────
        if raw.startswith("!"):
            cmd = raw[1:].strip()
            if not cmd:
                continue
            console.print(Text(f"  $ {cmd}", style=TEXT_DIM))
            stdout, stderr, rc = run_command(cmd)
            output_display = (stdout + stderr).rstrip()
            if output_display:
                console.print(Text(output_display, style=TEXT_BODY))
            console.print()
            ai_message = build_ai_prompt(cmd, stdout, stderr, rc)
            session.add_user(ai_message)
            try:
                response = asyncio.run(_stream_response(cfg, session))
                session.add_assistant(response)
                _maybe_warn_tokens(session, cfg)
            except RuntimeError as exc:
                console.print(Text(f"  error: {exc}", style="red"))
            except Exception as exc:
                console.print(Text(f"  unexpected error: {exc}", style="red"))
            continue

        # ── @file context injection ─────────────────────────────────────────
        message = raw
        if "@" in raw:
            message, errors = resolve_files(raw)
            for err in errors:
                console.print(Text(f"  ⚠  {err}", style="yellow"))
            if not message.strip():
                continue

        # ── Auto-search trigger ─────────────────────────────────────────────
        sq = _auto_search_query(message)
        if sq:
            from franki.utils.search import is_search_available
            if is_search_available(cfg):
                _run_auto_search(cfg, session, sq)

        session.add_user(message)

        try:
            response = asyncio.run(_stream_response(cfg, session))
            session.add_assistant(response)
            _maybe_warn_tokens(session, cfg)
        except RuntimeError as exc:
            console.print(Text(f"  error: {exc}", style="red"))
        except Exception as exc:
            console.print(Text(f"  unexpected error: {exc}", style="red"))


def _maybe_warn_tokens(session: Session, cfg: FrankiConfig) -> None:
    """Print a one-line token warning after an AI response if threshold exceeded."""
    stats = session.message_stats()
    warn = warning_text(stats["approx_tokens"], cfg.get_active_model_name())
    if warn:
        console.print(Text(f"  {warn}", style="yellow"))


def main() -> None:
    args = sys.argv[1:]

    if args and args[0] in ("--version", "-V"):
        print(f"franki {__version__}")
        return

    if args and args[0] == "init":
        from franki.setup_wizard import run_wizard
        run_wizard()
        return

    if args and args[0] == "config":
        from franki.config_cmd import run_config
        run_config(args[1:])
        return

    if not CONFIG_FILE.exists():
        from franki.setup_wizard import run_wizard
        run_wizard()
        cfg = load_config()
        _run_repl(cfg)
        return

    cfg = load_config()
    _run_repl(cfg)


if __name__ == "__main__":
    main()
