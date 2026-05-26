from __future__ import annotations
import asyncio
import os
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
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.history import FileHistory
from prompt_toolkit.completion import Completer, Completion

from franki import __version__
from franki.config import load_config, save_config, CONFIG_FILE, FrankiConfig, needs_setup
from franki.session import Session
from franki.commands import handle_command
from franki.router import stream_with_fallback
from franki.routing import RoutingTracker
from franki.cost_tracker import CostTracker
from franki.ui.logo import render_logo
from franki.ui.theme import GOLD, TEXT_BODY, TEXT_USER, TEXT_DIM, BORDER
from franki.ui.tips import get_random_tip
from franki.ui.token_warning import warning_text
from franki.ui.version_check import start_version_check
from franki.utils.highlight import render_response
from franki.ui.phrases import pick_phrase, phrase_for_elapsed
from franki.utils.files import resolve_content

# Aliases kept so existing test patches continue to work
_resolve_content = resolve_content
from franki.utils.shell import run_command, build_ai_prompt
from franki.agent import run_agent
from franki.project_context import load_project_context

console = Console(highlight=False)


# ── Splash / skill bar ────────────────────────────────────────────────────────

def _render_splash(cfg: FrankiConfig, project_context: str | None = None) -> None:
    cwd = str(Path.cwd())
    console.print()
    render_logo(console)
    console.print(Text(f"  {cwd}", style=TEXT_DIM))
    if project_context:
        console.print(Text("  ◦ .franki.md loaded", style=TEXT_DIM))
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

    if token_warn:
        right = Text(f"  {token_warn}", style="yellow")
    elif cfg.active_skill == "pentest" and not scope:
        right = Text("  /scope to set target hosts", style=TEXT_DIM)
    elif cfg.active_skill == "pentest":
        right = Text("  /report when done  ·  /cost for usage", style=TEXT_DIM)
    else:
        right = Text("  /help for commands", style=TEXT_DIM)

    width = console.width or 80
    pad = max(2, width - len(left.plain) - len(right.plain) - 2)
    left.append(" " * pad)
    left.append_text(right)

    console.print(left)
    console.print(Rule(style=BORDER))


def _print_fallback_notice(from_model: str, to_model: str, reason: str = "") -> None:
    msg = f"  rate limit on {from_model} — switching to {to_model}"
    if reason and reason not in ("rate-limited", "priority order"):
        msg += f"  ({reason})"
    console.print(Text(msg, style=TEXT_DIM))


# ── Streaming ─────────────────────────────────────────────────────────────────

def _count_tokens_approx(text: str) -> int:
    return max(1, len(text) // 4)


async def _stream_response(
    cfg: FrankiConfig,
    session: Session,
    routing_tracker: RoutingTracker | None = None,
    cost_tracker: CostTracker | None = None,
) -> str:
    import time as _time
    import sys as _sys

    full_response: list[str] = []
    fallback_notice: list = [None]
    _active_provider: list[str] = [cfg.active_provider]

    def on_fallback(from_m: str, to_m: str, reason: str = "") -> None:
        fallback_notice[0] = (from_m, to_m, reason)
        _active_provider[0] = to_m.split("/")[0] if "/" in to_m else to_m

    spinner  = Spinner("dots", style=GOLD)
    t_start  = _time.perf_counter()
    _opening = pick_phrase()
    streaming_started = False

    live = Live(console=console, refresh_per_second=12, transient=True)
    live.start()
    live.update(Columns([spinner, Text(f"  {_opening}  ·  0.0s", style=TEXT_DIM)]))

    try:
        async for chunk in stream_with_fallback(
            cfg,
            session.get_messages(),
            skill=session.skill,
            tracker=routing_tracker,
            on_fallback=on_fallback,
        ):
            if fallback_notice[0]:
                from_m, to_m, reason = fallback_notice[0]
                fallback_notice[0] = None
                if streaming_started:
                    _sys.stdout.write("\n")
                    _sys.stdout.flush()
                    streaming_started = False
                else:
                    live.stop()
                _print_fallback_notice(from_m, to_m, reason)
                if not streaming_started:
                    live.start()

            if not streaming_started:
                live.stop()
                console.print()
                console.print(Text("  ● ", style=f"bold {GOLD}"), end="")
                streaming_started = True

            full_response.append(chunk)
            _sys.stdout.write(chunk)
            _sys.stdout.flush()

    finally:
        if not streaming_started:
            live.stop()

    _sys.stdout.write("\n")
    _sys.stdout.flush()

    elapsed = _time.perf_counter() - t_start
    response_text = "".join(full_response)

    if cost_tracker is not None:
        provider_name = _active_provider[0]
        pdata = cfg.providers.get(provider_name, {})
        input_tokens = _count_tokens_approx(
            " ".join(str(m.get("content", "")) for m in session.get_messages())
        )
        output_tokens = _count_tokens_approx(response_text)
        cost_tracker.record(
            provider=provider_name,
            model=cfg.providers.get(provider_name, {}).get("model", ""),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            pdata=pdata if isinstance(pdata, dict) else {},
            latency_s=elapsed,
        )

    _auto_copy_hint(response_text, cost_tracker, auto_copy=cfg.auto_copy)
    return response_text


# ── MCP server lifecycle ─────────────────────────────────────────────────────

def _start_mcp_servers(cfg: FrankiConfig) -> dict:
    """Start all enabled MCP servers from config. Returns {name: MCPClient}."""
    from franki.mcp_client import MCPClient, MCPError
    clients: dict = {}
    for name, mdata in cfg.mcp.items():
        if not isinstance(mdata, dict) or not mdata.get("enabled", True):
            continue
        command = mdata.get("command", "")
        args    = mdata.get("args", [])
        env     = mdata.get("env")
        if not command:
            continue
        try:
            client = MCPClient(name, command, args, env)
            clients[name] = client
            tool_count = len(client.get_tools())
            console.print(Text(
                f"  ◦ MCP [{name}]  {tool_count} tool(s) available",
                style=TEXT_DIM,
            ))
        except MCPError as exc:
            console.print(Text(f"  ⚠ MCP [{name}] failed to start: {exc}", style="yellow"))
        except Exception as exc:
            console.print(Text(f"  ⚠ MCP [{name}] error: {exc}", style="yellow"))
    return clients


def _stop_mcp_servers(clients: dict) -> None:
    for client in clients.values():
        try:
            client.stop()
        except Exception:
            pass


# ── Auto-copy + inline cost hint ─────────────────────────────────────────────

def _auto_copy_hint(text: str, cost_tracker: CostTracker | None = None, auto_copy: bool = False) -> None:
    """Show a dim token/cost line. Copy to clipboard only if auto_copy is on."""
    copied = False
    if auto_copy:
        try:
            import pyperclip
            clean = re.sub(r'\[/?[^\]\s][^\]]*\]', '', text)
            pyperclip.copy(clean)
            copied = True
        except Exception:
            pass

    parts: list[str] = []
    if cost_tracker and cost_tracker.total_calls() > 0:
        tokens = cost_tracker.total_tokens()
        cost   = cost_tracker.total_cost()
        parts.append(f"~{tokens:,}t")
        if cost > 0:
            parts.append(f"${cost:.4f}")
    if copied:
        parts.append("copied ↑")

    if parts:
        console.print(Text("  " + "  ·  ".join(parts), style=TEXT_DIM))


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
    msgs = session.history_display()
    if not msgs:
        console.print(Text("  bye.", style=TEXT_DIM))
        return

    # Always auto-save session for resume capability
    try:
        from franki.session_store import save_session as _save_sess
        _save_sess(session, cfg)
    except Exception:
        pass

    try:
        console.print()
        console.print(Text("  save session as markdown before exiting? [y/N] ", style=TEXT_DIM), end="")
        choice = input("").strip().lower()
    except (KeyboardInterrupt, EOFError):
        console.print()
        console.print(Text("  bye.", style=TEXT_DIM))
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


def _maybe_auto_compact(cfg: FrankiConfig, session: Session) -> bool:
    """Compact history if auto_compact is on and a threshold is exceeded.
    Returns True if compaction ran."""
    if not cfg.auto_compact:
        return False
    stats = session.message_stats()

    # Message-count trigger
    if cfg.auto_compact_messages > 0 and stats["user"] >= cfg.auto_compact_messages:
        reason = f"reached {stats['user']} messages"
        _do_compact(cfg, session, reason)
        return True

    # Token-window trigger
    from franki.ui.token_warning import token_usage_pct
    pct = token_usage_pct(stats["approx_tokens"], cfg.get_active_model())
    if pct >= cfg.auto_compact_threshold:
        reason = f"context {pct:.0%} full"
        _do_compact(cfg, session, reason)
        return True

    return False


def _do_compact(cfg: FrankiConfig, session: Session, reason: str) -> None:
    console.print()
    console.print(Text(
        f"  auto-compact: {reason} — summarising history...",
        style=TEXT_DIM,
    ))
    from franki.ai_ops import run_compact
    run_compact(cfg, session)


# ── Input helpers ─────────────────────────────────────────────────────────────

_SLASH_COMMANDS = [
    "/clear", "/compact", "/rewind", "/retry", "/history", "/context",
    "/pin", "/template", "/export", "/copy", "/note", "/report", "/search",
    "/cd", "/skill", "/model", "/scope", "/mitre", "/payload", "/tools",
    "/explain", "/remember", "/memories", "/forget", "/cost", "/routing",
    "/providers", "/ollama", "/mcp", "/test", "/sessions", "/undo", "/diff", "/profile",
    "/auto", "/sandbox", "/branch", "/audit", "/init", "/config", "/help",
    "/feedback", "/exit", "/quit",
]

_HISTORY_FILE = Path.home() / ".config" / "franki" / "history"


def _get_pt_session() -> PromptSession:
    style = PTStyle.from_dict({
        "prompt": f"bold {GOLD}",
        "": TEXT_USER,
        "bottom-toolbar": f"noreverse bg:#0d0d0d fg:{TEXT_DIM}",
    })

    kb = KeyBindings()

    @kb.add("escape", "enter")
    def _alt_enter(event):
        """Alt/Escape+Enter inserts a newline without submitting."""
        event.current_buffer.insert_text("\n")

    @kb.add("enter")
    def _enter(event):
        """Plain Enter submits the prompt."""
        event.current_buffer.validate_and_handle()

    class _SlashCompleter(Completer):
        def get_completions(self, document, complete_event):
            line = document.text_before_cursor.split("\n")[-1]
            if not line.startswith("/"):
                return
            for cmd in _SLASH_COMMANDS:
                if cmd.startswith(line):
                    yield Completion(cmd, start_position=-len(line))

    _HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    history = FileHistory(str(_HISTORY_FILE))

    return PromptSession(
        style=style,
        key_bindings=kb,
        multiline=True,
        completer=_SlashCompleter(),
        complete_while_typing=True,
        history=history,
    )


_EXIT_WORDS = {"exit", "quit", "q", "/exit", "/quit", "/q"}


# ── REPL ──────────────────────────────────────────────────────────────────────

def _end_session(session: Session, cfg: FrankiConfig) -> None:
    """Save prompt + optional periodic feedback prompt."""
    _prompt_save_exit(session, cfg)
    from franki.feedback import should_ask, ask_feedback
    stats = session.message_stats()
    if should_ask(cfg.session_count, stats["user"]):
        ask_feedback(console, skill=session.skill, msgs=stats["user"])


def _load_dotenv() -> None:
    """Auto-load .env from CWD or parent dirs (up to home dir)."""
    try:
        from dotenv import load_dotenv
        p = Path.cwd()
        home = Path.home()
        for _ in range(6):
            candidate = p / ".env"
            if candidate.exists():
                load_dotenv(candidate, override=False)
                break
            if p == home or p.parent == p:
                break
            p = p.parent
    except ImportError:
        pass


def _run_repl(cfg: FrankiConfig, resume_data: dict | None = None) -> None:
    from franki.memory import get_context_string

    _load_dotenv()

    _loop = asyncio.new_event_loop()
    asyncio.set_event_loop(_loop)

    cfg.session_count = (cfg.session_count or 0) + 1
    save_config(cfg)

    project_context = load_project_context()
    mem_context     = get_context_string()

    if resume_data is not None:
        session = Session.from_dict(
            resume_data,
            memory_context=mem_context,
            project_context=project_context,
        )
    else:
        session = Session(
            skill=cfg.active_skill,
            memory_context=mem_context,
            project_context=project_context,
        )
    from franki.change_tracker import ChangeTracker
    from franki.custom_tools import parse_custom_tools
    from franki.agent.tools import register_custom_tools, set_tavily_key, register_mcp_clients
    routing_tracker        = RoutingTracker()
    cost_tracker           = CostTracker()
    change_tracker         = ChangeTracker()
    session.routing_tracker = routing_tracker
    session.cost_tracker    = cost_tracker
    session.change_tracker  = change_tracker
    register_custom_tools(parse_custom_tools(project_context or ""))
    set_tavily_key(os.environ.get("TAVILY_API_KEY", "") or cfg.tavily_api_key)

    # Start enabled MCP servers and register cleanup on exit
    _mcp_clients = _start_mcp_servers(cfg)
    register_mcp_clients(_mcp_clients)
    if _mcp_clients:
        import atexit
        atexit.register(_stop_mcp_servers, _mcp_clients)

    # Inject full self-awareness block into system prompt
    from franki.environment import build_environment_block
    session.set_env_context(build_environment_block(cfg))

    _render_splash(cfg, project_context=project_context)
    if resume_data is not None:
        msgs = session.history_display()
        console.print(Text(
            f"  resumed  [{session.skill}]  {len(msgs)} messages",
            style=GOLD,
        ))

    def _on_update(current: str, latest: str) -> None:
        console.print(Text(
            f"  update available: franki {current} -> {latest}  "
            "(pip install -U franki-cli)",
            style="yellow",
        ))

    start_version_check(__version__, _on_update)

    def _redraw_bar() -> None:
        model = cfg.get_active_model()
        label = (f"{cfg.active_provider}/{model}" if model
                 else cfg.active_provider or "no provider")
        scope_part = f"  ·  scope:{session.scope}" if session.scope else ""
        t = Text()
        t.append("  ● ", style=GOLD)
        t.append(f"[{cfg.active_skill}]{scope_part}  ·  {label}", style=TEXT_DIM)
        console.print(t)

    _check_providers(cfg)

    pt = _get_pt_session()

    def _toolbar() -> HTML:
        model = cfg.get_active_model()
        model_short = model[:26] + ".." if len(model) > 28 else model
        label = f"{cfg.active_provider}/{model_short}" if model_short else cfg.active_provider or "no provider"
        scope_part = f"  ·  scope:{session.scope}" if session.scope else ""
        stats = session.message_stats()
        warn = warning_text(stats["approx_tokens"], cfg.get_active_model())
        hint = f"  ·  ⚠ {warn}" if warn else "  ·  /help for commands"
        return HTML(
            f'<style fg="{TEXT_DIM}" bg="#0d0d0d">'
            f"  [{cfg.active_skill}]{scope_part}  ·  {label}{hint}"
            "</style>"
        )

    while True:
        try:
            raw = pt.prompt(
                [("class:prompt", ">  ")],
                bottom_toolbar=_toolbar,
            ).strip()
        except (KeyboardInterrupt, EOFError):
            console.print()
            _end_session(session, cfg)
            break

        if not raw:
            continue

        # ── Plain exit/quit (no slash required) ──────────────────────────────
        if raw.lower() in _EXIT_WORDS:
            console.print()
            _end_session(session, cfg)
            break

        # ── Slash commands ────────────────────────────────────────────────────
        if raw.startswith("/"):
            result = handle_command(
                raw, cfg, session, save_config,
                lambda: _redraw_bar(),
            )
            if result == "retry":
                removed, last_content = session.rewind_full()
                if last_content is None:
                    console.print(Text("  nothing to retry.", style=TEXT_DIM))
                    continue
                console.print(Text("  retrying...", style=TEXT_DIM))
                try:
                    _loop.run_until_complete(
                        run_agent(cfg, session, console, last_content)
                    )
                    if not _maybe_auto_compact(cfg, session):
                        _maybe_warn_tokens(session, cfg)
                except Exception as exc:
                    console.print(Text(f"  error: {exc}", style="red"))
            elif isinstance(result, str) and result.startswith("template:"):
                template_prompt = result[len("template:"):]
                try:
                    _loop.run_until_complete(
                        run_agent(cfg, session, console, template_prompt)
                    )
                    if not _maybe_auto_compact(cfg, session):
                        _maybe_warn_tokens(session, cfg)
                except Exception as exc:
                    console.print(Text(f"  error: {exc}", style="red"))
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
                response = _loop.run_until_complete(
                    _stream_response(cfg, session, routing_tracker, cost_tracker)
                )
                session.add_assistant(response)
                if not _maybe_auto_compact(cfg, session):
                    _maybe_warn_tokens(session, cfg)
            except Exception as exc:
                console.print(Text(f"  error: {exc}", style="red"))
            continue

        # ── @file / @image context injection (vision-aware) ──────────────────
        content: str | list = raw
        if "@" in raw:
            content, errors = resolve_content(raw)
            for err in errors:
                console.print(Text(f"  warning: {err}", style="yellow"))
            # If content is a string and empty after injection, skip
            if isinstance(content, str) and not content.strip():
                continue

        # For auto-skill and auto-search, use the text portion only
        text_content = (
            content if isinstance(content, str)
            else " ".join(p.get("text", "") for p in content if isinstance(p, dict))
        )

        # ── Auto-skill detection ──────────────────────────────────────────────
        _maybe_auto_switch_skill(text_content, cfg, session, save_config, _redraw_bar)

        # ── Auto-search trigger ───────────────────────────────────────────────
        sq = _auto_search_query(text_content)
        if sq:
            from franki.utils.search import is_search_available
            if is_search_available(cfg):
                _run_auto_search(cfg, session, sq)

        # ── Agent loop (tool use + streaming final response) ──────────────────
        try:
            response = _loop.run_until_complete(
                run_agent(cfg, session, console, content)
            )
            if not _maybe_auto_compact(cfg, session):
                _maybe_warn_tokens(session, cfg)
        except RuntimeError as exc:
            console.print(Text(f"  error: {exc}", style="red"))
        except Exception as exc:
            console.print(Text(f"  error: {exc}", style="red"))


# ── CLI sub-commands ──────────────────────────────────────────────────────────

def _cmd_resume(args: list[str]) -> None:
    """franki resume [n] — interactively restore a saved session."""
    from franki.session_store import list_sessions, load_session_data

    sessions = list_sessions()
    if not sessions:
        console.print(Text("  no saved sessions found.", style=TEXT_DIM))
        return

    # If number given directly, skip the interactive list
    if args and args[0].isdigit():
        idx = int(args[0])
    else:
        console.print()
        for i, s in enumerate(sessions, 1):
            date_str = s["saved_at"][:16].replace("T", " ") if s["saved_at"] else "?"
            console.print(Text(
                f"  {i}.  [{s['skill']}]  {date_str}  ·  {s['message_count']}msg"
                f"  —  {s['preview'][:50] if s['preview'] else '(no preview)'}",
                style=TEXT_BODY,
            ))
        console.print()
        console.print(Text("  resume session #: ", style=TEXT_DIM), end="")
        try:
            choice = input("").strip()
        except (KeyboardInterrupt, EOFError):
            console.print()
            return
        if not choice.isdigit():
            return
        idx = int(choice)

    data = load_session_data(idx)
    if data is None:
        console.print(Text(f"  session #{idx} not found.", style="red"))
        return

    cfg = load_config()

    # Restore provider from saved session if still configured
    saved_provider = data.get("provider", "")
    if saved_provider and saved_provider in cfg.providers:
        cfg.active_provider = saved_provider

    cfg.active_skill = data.get("skill", cfg.active_skill)
    save_config(cfg)

    _run_repl(cfg, resume_data=data)


def _cmd_profile_cli(args: list[str]) -> None:
    """franki profile <save|load|list|delete> [name]"""
    from franki.profiles import save_profile, load_profile, list_profiles, delete_profile, _valid_name

    sub  = args[0].lower() if args else "list"
    name = args[1] if len(args) > 1 else ""

    if sub == "list":
        profiles = list_profiles()
        if not profiles:
            console.print(Text("  no profiles saved.", style=TEXT_DIM))
        else:
            for p in profiles:
                console.print(Text(f"  {p}", style=TEXT_BODY))
        return

    if sub == "save":
        if not name:
            console.print(Text("  usage: franki profile save <name>", style=TEXT_DIM))
            return
        if not _valid_name(name):
            console.print(Text("  invalid name — use alphanumeric/dash/underscore, max 32 chars.", style="red"))
            return
        cfg = load_config()
        save_profile(name, cfg)
        console.print(Text(f"  profile '{name}' saved.", style=GOLD))
        return

    if sub == "load":
        if not name:
            console.print(Text("  usage: franki profile load <name>", style=TEXT_DIM))
            return
        loaded = load_profile(name)
        if loaded is None:
            console.print(Text(f"  profile '{name}' not found.", style="red"))
            return
        cfg = load_config()
        count = cfg.session_count
        cfg.__dict__.update(loaded.__dict__)
        cfg.session_count = count
        save_config(cfg)
        console.print(Text(f"  profile '{name}' loaded.", style=GOLD))
        return

    if sub == "delete":
        if not name:
            console.print(Text("  usage: franki profile delete <name>", style=TEXT_DIM))
            return
        if delete_profile(name):
            console.print(Text(f"  profile '{name}' deleted.", style=GOLD))
        else:
            console.print(Text(f"  profile '{name}' not found.", style="red"))
        return

    console.print(Text(
        "  usage: franki profile list|save|load|delete [name]",
        style=TEXT_DIM,
    ))


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

    # Purpose-built one-shot commands
    if args and args[0] == "fix":
        from franki.oneshot import run_fix
        run_fix(args[1:])
        return

    if args and args[0] == "review":
        from franki.oneshot import run_review
        run_review(args[1:])
        return

    if args and args[0] == "commit":
        from franki.oneshot import run_commit
        run_commit(args[1:])
        return

    if args and args[0] == "explain":
        from franki.oneshot import run_explain
        run_explain(args[1:])
        return

    if args and args[0] == "resume":
        _cmd_resume(args[1:])
        return

    if args and args[0] == "profile":
        _cmd_profile_cli(args[1:])
        return

    # First-run or legacy config migration → run setup wizard then start REPL
    if needs_setup():
        if CONFIG_FILE.exists():
            backup = CONFIG_FILE.parent / "config.json.bak"
            backup.write_text(CONFIG_FILE.read_text(encoding="utf-8"), encoding="utf-8")
            CONFIG_FILE.unlink()
            console.print()
            console.print(Text(
                "  config format updated — please re-enter your providers",
                style="yellow",
            ))
        from franki.setup_wizard import run_wizard
        cfg = run_wizard()
        _run_repl(cfg)
        return

    cfg = load_config()
    _run_repl(cfg)


if __name__ == "__main__":
    main()
