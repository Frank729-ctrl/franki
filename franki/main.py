from __future__ import annotations
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
from franki.router import stream_with_fallback
from franki.ui.logo import render_logo
from franki.ui.tips import get_random_tip
from franki.ui.token_warning import warning_text
from franki.ui.version_check import start_version_check
from franki.utils.highlight import render_response
from franki.utils.files import resolve_files
from franki.utils.shell import run_command, build_ai_prompt

GOLD      = "#d4a853"
TEXT_BODY = "#a8a8a8"
TEXT_USER = "#c8c0b0"
TEXT_DIM  = "#555555"
BORDER    = "#2d2d2d"

console = Console(highlight=False)


# ── Splash / skill bar ────────────────────────────────────────────────────────

def _render_splash(cfg: FrankiConfig) -> None:
    model = cfg.get_active_model()
    provider = cfg.active_provider
    skill = cfg.active_skill
    cwd = str(Path.cwd())

    console.print()
    render_logo(console)
    console.print()
    label = f"{provider} / {model}" if model else provider or "(no provider configured)"
    console.print(Text(f"    {label}  ·  {skill}", style=TEXT_BODY))
    console.print(Text(f"    {cwd}", style=TEXT_DIM))
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
    provider = cfg.active_provider
    model = cfg.get_active_model()
    model_label = model if len(model) <= 30 else model[:28] + "..."
    full_label = f"{provider} / {model_label}" if model_label else provider or "no provider"

    left = Text()
    left.append("  skill: [", style=TEXT_DIM)
    left.append(cfg.active_skill, style=GOLD)
    left.append("]", style=TEXT_DIM)

    if scope:
        left.append("  scope: [", style=TEXT_DIM)
        left.append(scope, style=GOLD)
        left.append("]", style=TEXT_DIM)

    left.append("  ·  model: [", style=TEXT_DIM)
    left.append(full_label, style=GOLD)
    left.append("]", style=TEXT_DIM)

    right = Text(f"  {token_warn}", style="yellow") if token_warn else Text(
        "use /skill or /model to change", style=TEXT_DIM
    )

    width = console.width or 80
    pad = max(2, width - len(left.plain) - len(right.plain) - 2)
    left.append(" " * pad)
    left.append_text(right)

    console.print(left)
    console.print(Rule(style=BORDER))


def _print_fallback_notice(from_model: str, to_model: str) -> None:
    console.print(Text(
        f"  rate limit on {from_model} — switching to {to_model}",
        style=TEXT_DIM,
    ))


# ── Streaming ─────────────────────────────────────────────────────────────────

def _count_tokens_approx(text: str) -> int:
    return max(1, len(text) // 4)


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
            t.append("  thinking...", style=TEXT_DIM)
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


# ── Auto-search trigger ────────────────────────────────────────────────────────

_SEARCH_TRIGGERS = re.compile(
    r'\b(latest|current|today|news)\b|CVE-\d{4}-\d{4,7}',
    re.IGNORECASE,
)


def _auto_search_query(message: str) -> str | None:
    m = _SEARCH_TRIGGERS.search(message)
    if not m:
        return None
    cve = re.search(r'CVE-\d{4}-\d{4,7}', message, re.IGNORECASE)
    if cve:
        return cve.group(0)
    return message[:200].strip()


def _run_auto_search(cfg: FrankiConfig, session: Session, query: str) -> None:
    from franki.utils.search import web_search, SearchError
    console.print(Text("  searching the web for context...", style=TEXT_DIM))
    try:
        result = asyncio.run(web_search(cfg, query))
        session.add_user(result.as_context())
    except SearchError:
        pass


# ── Auto-skill detection ───────────────────────────────────────────────────────

def _maybe_auto_switch_skill(
    message: str,
    cfg: FrankiConfig,
    session: Session,
    save_cfg_fn,
    redraw_bar_fn,
) -> None:
    """
    If auto_skill is enabled, detect the best skill for the message.
    Silently switch if it's different from the current skill.
    Shows a one-line notice so the user can override with /skill.
    """
    if not cfg.auto_skill:
        return
    from franki.skills import detect_skill
    suggested = detect_skill(message)
    if suggested and suggested != session.skill:
        session.set_skill(suggested)
        cfg.active_skill = suggested
        save_cfg_fn(cfg)
        redraw_bar_fn()
        console.print(Text(
            f"  auto-skill: switched to [{suggested}] — type /skill to change",
            style=TEXT_DIM,
        ))


# ── Shell execution with auto-accept ──────────────────────────────────────────

def _confirm_shell_command(cmd: str, cfg: FrankiConfig) -> bool:
    """Return True if the command should be run."""
    if cfg.auto_accept:
        return True
    console.print(Text(f"  run: {cmd}", style=TEXT_DIM))
    console.print(Text("  execute? [y/N] ", style=TEXT_DIM), end="")
    try:
        choice = input("").strip().lower()
        return choice in ("y", "yes")
    except (KeyboardInterrupt, EOFError):
        console.print()
        return False


# ── Startup checks ────────────────────────────────────────────────────────────

def _check_providers(cfg: FrankiConfig) -> None:
    if not cfg.providers:
        console.print()
        console.print(Text(
            "  no providers configured — type /providers to add one",
            style="yellow",
        ))
        console.print()
        return

    if not cfg.active_provider or cfg.active_provider not in cfg.providers:
        first = cfg.first_configured_provider()
        if first:
            cfg.active_provider = first
            save_config(cfg)
        else:
            console.print()
            console.print(Text(
                "  no usable provider found — type /providers to fix",
                style="yellow",
            ))
            console.print()
            return

    key = cfg.get_provider_key(cfg.active_provider)
    pdata = cfg.providers.get(cfg.active_provider, {})
    needs_key = pdata.get("key_required", True) if isinstance(pdata, dict) else True
    if not key and needs_key:
        console.print()
        console.print(Text(
            f"  no API key for '{cfg.active_provider}' — type /config to add it",
            style="yellow",
        ))
        console.print()


def _prompt_save_exit(session: Session, cfg: FrankiConfig) -> None:
    if not session.history_display():
        console.print(Text("  bye.", style=TEXT_DIM))
        return
    try:
        console.print()
        console.print(Text("  save session before exiting? [y/N] ", style=TEXT_DIM), end="")
        choice = input("").strip().lower()
    except (KeyboardInterrupt, EOFError):
        console.print()
        return
    if choice in ("y", "yes"):
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


def _maybe_warn_tokens(session: Session, cfg: FrankiConfig) -> None:
    stats = session.message_stats()
    warn = warning_text(stats["approx_tokens"], cfg.get_active_model())
    if warn:
        console.print(Text(f"  {warn}", style="yellow"))


# ── Input helpers ─────────────────────────────────────────────────────────────

def _get_pt_session() -> PromptSession:
    style = PTStyle.from_dict({
        "prompt": f"{GOLD} bold",
        "": TEXT_USER,
    })
    return PromptSession(style=style)


_EXIT_WORDS = {"exit", "quit", "q", "/exit", "/quit", "/q"}


# ── REPL ──────────────────────────────────────────────────────────────────────

def _run_repl(cfg: FrankiConfig) -> None:
    from franki.memory import get_context_string
    session = Session(skill=cfg.active_skill, memory_context=get_context_string())

    _render_splash(cfg)

    def _on_update(current: str, latest: str) -> None:
        console.print(Text(
            f"  update available: franki {current} -> {latest}  "
            "(pip install -U franki-cli)",
            style="yellow",
        ))

    start_version_check(__version__, _on_update)

    def _redraw_bar() -> None:
        scope = session.scope
        stats = session.message_stats()
        warn = warning_text(stats["approx_tokens"], cfg.get_active_model())
        _print_skill_bar(cfg, scope=scope, token_warn=warn)

    _print_skill_bar(cfg)
    _check_providers(cfg)

    pt = _get_pt_session()
    bottom_toolbar = HTML(
        f'<style fg="{TEXT_DIM}">'
        "/help  /skill  /model  /providers  /scope  /mitre  /report  /export  /note  /clear  exit"
        "</style>"
    )

    while True:
        try:
            raw = pt.prompt(
                [("class:prompt", ">  ")],
                bottom_toolbar=bottom_toolbar,
            ).strip()
        except (KeyboardInterrupt, EOFError):
            console.print()
            _prompt_save_exit(session, cfg)
            break

        if not raw:
            continue

        # ── Plain exit/quit (no slash required) ──────────────────────────────
        if raw.lower() in _EXIT_WORDS:
            console.print()
            _prompt_save_exit(session, cfg)
            break

        # ── Slash commands ────────────────────────────────────────────────────
        if raw.startswith("/"):
            handle_command(
                raw, cfg, session, save_config,
                lambda: _redraw_bar(),
            )
            continue

        # ── Shell execution: !command ─────────────────────────────────────────
        if raw.startswith("!"):
            cmd = raw[1:].strip()
            if not cmd:
                continue
            if not _confirm_shell_command(cmd, cfg):
                console.print(Text("  cancelled.", style=TEXT_DIM))
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
            except Exception as exc:
                console.print(Text(f"  error: {exc}", style="red"))
            continue

        # ── @file context injection ───────────────────────────────────────────
        message = raw
        if "@" in raw:
            message, errors = resolve_files(raw)
            for err in errors:
                console.print(Text(f"  warning: {err}", style="yellow"))
            if not message.strip():
                continue

        # ── Auto-skill detection ──────────────────────────────────────────────
        _maybe_auto_switch_skill(message, cfg, session, save_config, _redraw_bar)

        # ── Auto-search trigger ───────────────────────────────────────────────
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
            console.print(Text(f"  error: {exc}", style="red"))


# ── Entry point ────────────────────────────────────────────────────────────────

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
        from franki.config_cmd import run_config_cli
        run_config_cli(args[1:])
        return

    # First-run: no config file → run wizard inline then start REPL
    if not CONFIG_FILE.exists():
        from franki.setup_wizard import run_wizard
        cfg = run_wizard()
        _run_repl(cfg)
        return

    cfg = load_config()
    _run_repl(cfg)


if __name__ == "__main__":
    main()
