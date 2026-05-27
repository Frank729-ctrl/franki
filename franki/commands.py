from __future__ import annotations
from pathlib import Path
from typing import TYPE_CHECKING

from rich.console import Console
from rich.text import Text
from rich.table import Table
from rich.rule import Rule

from franki.skills import get_all_skill_names
from franki.ui.theme import GOLD, TEXT_DIM, TEXT_BODY, BORDER

if TYPE_CHECKING:
    from franki.config import FrankiConfig
    from franki.session import Session

console = Console(highlight=False)


def handle_command(
    raw: str,
    cfg: "FrankiConfig",
    session: "Session",
    save_cfg_fn,
    redraw_bar_fn,
) -> bool:
    parts = raw.strip().split(maxsplit=1)
    cmd = parts[0].lower()
    arg = parts[1].strip() if len(parts) > 1 else ""

    # ── Conversation ──────────────────────────────────────────────────────────
    if cmd == "/clear":
        return _cmd_clear(session)
    if cmd == "/compact":
        return _cmd_compact(cfg, session)
    if cmd == "/rewind":
        return _cmd_rewind(session)
    if cmd == "/history":
        return _cmd_history(session)
    if cmd == "/context":
        return _cmd_context(cfg, session)
    if cmd == "/pin":
        return _cmd_pin(session, arg)
    if cmd == "/retry":
        return "retry"

    # ── Output ────────────────────────────────────────────────────────────────
    if cmd == "/export":
        return _cmd_export(cfg, session)
    if cmd == "/copy":
        return _cmd_copy(session)
    if cmd == "/note":
        return _cmd_note(cfg, arg)
    if cmd == "/report":
        return _cmd_report(cfg, session)
    if cmd == "/search":
        return _cmd_search(cfg, session, arg)

    # ── Navigation ────────────────────────────────────────────────────────────
    if cmd == "/cd":
        return _cmd_cd(arg, cfg, session, redraw_bar_fn)
    if cmd == "/skill":
        return _cmd_skill(cfg, session, arg, save_cfg_fn, redraw_bar_fn)
    if cmd == "/model":
        return _cmd_model(cfg, arg, save_cfg_fn, redraw_bar_fn, session=session)
    if cmd == "/scope":
        return _cmd_scope(session, arg, redraw_bar_fn)

    # ── Security tools ────────────────────────────────────────────────────────
    if cmd == "/mitre":
        return _cmd_mitre(cfg, arg)
    if cmd == "/payload":
        return _cmd_payload(cfg, arg)
    if cmd == "/tools":
        return _cmd_tools(cfg, arg, session.skill)
    if cmd == "/explain":
        return _cmd_explain(cfg, arg)

    # ── Memory ────────────────────────────────────────────────────────────────
    if cmd == "/remember":
        return _cmd_remember(arg, session)
    if cmd in ("/memory", "/memories"):
        return _cmd_memory()
    if cmd == "/forget":
        return _cmd_forget(arg, session)

    # ── Cost / routing transparency ───────────────────────────────────────────
    if cmd == "/cost":
        return _cmd_cost(session)
    if cmd in ("/routing", "/route"):
        return _cmd_routing(cfg, session)

    # ── Providers / MCP ───────────────────────────────────────────────────────
    if cmd == "/providers":
        # /providers is now an alias for /model — keep it working for muscle memory
        return _cmd_model(cfg, arg, save_cfg_fn, redraw_bar_fn, session)
    if cmd == "/ollama":
        return _cmd_ollama(cfg, arg, save_cfg_fn, redraw_bar_fn)
    if cmd == "/mcp":
        return _cmd_mcp(cfg, arg, save_cfg_fn)

    # ── Test runner ───────────────────────────────────────────────────────────
    if cmd == "/test":
        return _cmd_test(cfg, session, arg)

    # ── Session management ────────────────────────────────────────────────────
    if cmd == "/sessions":
        return _cmd_sessions(cfg, session, arg, save_cfg_fn, redraw_bar_fn)

    # ── Agent undo / diff ─────────────────────────────────────────────────────
    if cmd == "/undo":
        return _cmd_undo(session)
    if cmd == "/diff":
        return _cmd_diff(session)

    # ── Config profiles ───────────────────────────────────────────────────────
    if cmd == "/profile":
        return _cmd_profile(cfg, arg, save_cfg_fn, redraw_bar_fn)

    # ── Templates / sandbox / branching ─────────────────────────────────────
    if cmd == "/template":
        return _cmd_template(session, arg)
    if cmd == "/sandbox":
        return _cmd_sandbox(session, arg)
    if cmd == "/branch":
        return _cmd_branch(session, arg)
    if cmd == "/audit":
        return _cmd_audit()

    # ── System ────────────────────────────────────────────────────────────────
    if cmd == "/toolperms":
        return _cmd_toolperms(cfg, arg, save_cfg_fn)
    if cmd == "/autocommit":
        return _cmd_autocommit(cfg, arg, save_cfg_fn)
    if cmd == "/hooks":
        return _cmd_hooks(cfg, arg, save_cfg_fn)
    if cmd == "/think":
        return _cmd_think(cfg, arg, save_cfg_fn)
    if cmd == "/auto":
        return _cmd_auto(cfg, arg, save_cfg_fn)
    if cmd == "/init":
        return _cmd_init(cfg, save_cfg_fn, redraw_bar_fn)
    if cmd == "/config":
        return _cmd_config_edit(cfg, save_cfg_fn, redraw_bar_fn)
    if cmd == "/help":
        return _cmd_help()
    if cmd == "/feedback":
        return _cmd_feedback(arg, session)
    if cmd in ("/connect", "/connect delkaai", "/connect direct"):
        # Legacy — guide user to /providers
        console.print(Text(
            "  /connect is no longer used — manage providers with /providers",
            style=TEXT_DIM,
        ))
        return True

    # Exit handled upstream in main.py
    if cmd in ("/exit", "/quit", "/q"):
        raise SystemExit(0)

    console.print(Text(f"  unknown command '{cmd}' — type /help for the full list", style=TEXT_DIM))
    return True


# ── Conversation ──────────────────────────────────────────────────────────────

def _cmd_clear(session: "Session") -> bool:
    session.clear()
    console.print(Text("  conversation cleared.", style=TEXT_DIM))
    return True


def _cmd_compact(cfg: "FrankiConfig", session: "Session") -> bool:
    from franki.ai_ops import run_compact
    run_compact(cfg, session)
    return True


def _cmd_rewind(session: "Session") -> bool:
    removed = session.rewind()
    if removed == 0:
        console.print(Text("  nothing to rewind.", style=TEXT_DIM))
    else:
        console.print(Text(f"  rewound {removed} message(s).", style=GOLD))
    return True


def _cmd_pin(session: "Session", arg: str) -> bool:
    parts = arg.strip().split(maxsplit=1)
    sub = parts[0].lower() if parts else ""

    if not arg.strip():
        pins = session.list_pins()
        if not pins:
            console.print(Text("  no pins set.  /pin <message>  to add one.", style=TEXT_DIM))
            return True
        console.print()
        t = Table(show_header=False, box=None, padding=(0, 2))
        t.add_column(style=TEXT_DIM, no_wrap=True, width=4)
        t.add_column(style=TEXT_BODY)
        for i, p in enumerate(pins, 1):
            t.add_row(f"[{i}]", p)
        console.print(t)
        console.print(Text("  /pin clear [n]  to remove", style=TEXT_DIM))
        console.print()
        return True

    if sub == "clear":
        idx_str = parts[1].strip() if len(parts) > 1 else ""
        if not idx_str:
            session.clear_pins()
            console.print(Text("  all pins cleared.", style=GOLD))
        elif idx_str.isdigit():
            if session.remove_pin(int(idx_str)):
                console.print(Text(f"  pin [{idx_str}] removed.", style=GOLD))
            else:
                console.print(Text(f"  no pin [{idx_str}].", style=TEXT_DIM))
        else:
            console.print(Text("  usage: /pin clear [n]", style=TEXT_DIM))
        return True

    idx = session.add_pin(arg.strip())
    console.print(Text(f"  pinned [{idx}]: {arg.strip()}", style=GOLD))
    console.print(Text("  this reminder is included in every request.", style=TEXT_DIM))
    return True


def _cmd_history(session: "Session") -> bool:
    msgs = session.history_display()
    if not msgs:
        console.print(Text("  no messages yet.", style=TEXT_DIM))
        return True
    console.print()
    for m in msgs:
        style = GOLD if m["role"] == "user" else TEXT_BODY
        preview = m["content"][:140].replace("\n", " ")
        console.print(Text(f"  [{m['role']}] {preview}", style=style))
    console.print()
    return True


def _cmd_context(cfg: "FrankiConfig", session: "Session") -> bool:
    from franki import __version__
    from franki.memory import list_facts, skill_usage_counts, list_scopes
    from franki.utils.search import is_search_available

    stats   = session.message_stats()
    facts   = list_facts()
    usage   = skill_usage_counts()
    scopes  = list_scopes()
    search  = is_search_available(cfg)
    top_skill = max(usage, key=usage.__getitem__) if usage else None

    active_model = cfg.get_active_model()
    active_label = f"{cfg.active_provider} / {active_model}" if active_model else cfg.active_provider or "(none)"

    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column(style=TEXT_DIM, no_wrap=True, width=18)
    table.add_column(style=TEXT_BODY)

    table.add_row("Provider / Model", active_label)
    table.add_row("Skill",            session.skill)
    table.add_row("Scope",            session.scope or "(not set)")
    table.add_row("Auto-skill",       "on" if cfg.auto_skill else "off")
    table.add_row("", "")
    table.add_row("Messages",         f"user: {stats['user']}  assistant: {stats['assistant']}  total: {stats['total']}")
    table.add_row("Tokens (approx)", f"~{stats['approx_tokens']:,}")
    table.add_row("", "")
    ct = getattr(session, "change_tracker", None)
    changes_str = f"{ct.count} file change(s) this session" if ct and ct.count else "none"
    table.add_row("Agent changes",    changes_str)
    table.add_row("Memory",           f"{len(facts)} fact(s)" + (f"  preferred: {top_skill}" if top_skill else ""))
    if scopes:
        table.add_row("Scopes", ", ".join(scopes[:3]) + ("..." if len(scopes) > 3 else ""))
    table.add_row("", "")
    table.add_row("Search",           "available" if search else "not configured")
    table.add_row("Export path",      cfg.export_path)
    auto_str = "on" if cfg.auto_accept else "off"
    if cfg.auto_accept:
        notify_str = "  (notify: on)" if cfg.notify_on_done else "  (notify: off)"
        auto_str += notify_str
    table.add_row("Auto-accept",      auto_str)
    table.add_row("MCP servers",      str(len(cfg.mcp)) or "none")
    table.add_row("Version",          f"franki v{__version__}")

    console.print()
    console.print(table)
    console.print()
    return True


# ── Cost / routing transparency ──────────────────────────────────────────────

def _cmd_cost(session: "Session") -> bool:
    ct = session.cost_tracker
    if ct is None or ct.total_calls() == 0:
        console.print(Text("  no calls recorded yet in this session.", style=TEXT_DIM))
        return True

    console.print()
    console.print(Text("  Session cost estimate", style=f"bold {GOLD}"))
    console.print(Rule(style=BORDER))
    for line in ct.summary_lines():
        console.print(Text(line, style=TEXT_BODY))
    console.print()
    console.print(Text(
        "  Note: costs are estimates based on configured rates. "
        "Set cost_per_1m_input/output per provider for accurate figures.",
        style=TEXT_DIM,
    ))
    console.print()
    return True


def _cmd_routing(cfg: "FrankiConfig", session: "Session") -> bool:
    from franki.routing import RoutingTracker, build_routing_order, _get_capabilities

    tracker = session.routing_tracker or RoutingTracker()
    ordered = build_routing_order(cfg, session.skill, tracker)

    if not ordered:
        console.print(Text("  no configured providers to show.", style="yellow"))
        return True

    console.print()
    console.print(Text(
        f"  Routing order for skill [{session.skill}]  "
        f"(local-first: {'on' if cfg.local_first else 'off'}  "
        f"strategy: {cfg.routing_strategy})",
        style=f"bold {GOLD}",
    ))
    console.print(Rule(style=BORDER))

    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column(style=TEXT_DIM, no_wrap=True, width=3)
    table.add_column(style=TEXT_BODY, no_wrap=True, width=18)
    table.add_column(style=TEXT_DIM, no_wrap=True, width=30)
    table.add_column(style=TEXT_DIM)

    for i, (name, pdata, reason) in enumerate(ordered, 1):
        caps = _get_capabilities(name, pdata)
        model = pdata.get("model", "")
        cap_str = ", ".join(caps) if caps else "—"
        rl_note = "  [rate-limited]" if tracker.is_rate_limited(name) else ""
        avg = tracker.avg_latency(name)
        lat_note = f"  avg {avg:.1f}s" if avg else ""
        table.add_row(
            str(i),
            f"{name}/{model}"[:28],
            reason + rl_note + lat_note,
            f"caps: {cap_str}",
        )

    console.print(table)
    console.print()
    return True


# ── Output ────────────────────────────────────────────────────────────────────

def _cmd_export(cfg: "FrankiConfig", session: "Session") -> bool:
    from franki.exporter import export_session
    path = export_session(session, cfg)
    if path:
        console.print(Text(f"  saved → {path}", style=GOLD))
    else:
        console.print(Text("  export cancelled.", style=TEXT_DIM))
    return True


def _cmd_copy(session: "Session") -> bool:
    lr = session.last_response
    if not lr:
        console.print(Text("  no AI response to copy.", style=TEXT_DIM))
        return True
    clean = _strip_markup(lr)
    try:
        import pyperclip
        pyperclip.copy(clean)
        console.print(Text("  copied to clipboard.", style=GOLD))
    except ImportError:
        console.print(Text("  clipboard not available (pyperclip not installed)", style="red"))
    except Exception as exc:
        console.print(Text(f"  clipboard error: {exc}", style="red"))
    return True


def _strip_markup(text: str) -> str:
    import re
    return re.sub(r'\[/?[^\]\s][^\]]*\]', '', text)


def _cmd_note(cfg: "FrankiConfig", text: str) -> bool:
    if not text:
        console.print(Text("  usage: /note <text>", style=TEXT_DIM))
        return True
    from franki.exporter import save_note
    from franki.memory import track_note
    path = save_note(text, cfg)
    if path:
        track_note(text)
        console.print(Text("  note saved.", style=GOLD))
    else:
        console.print(Text("  could not save note.", style="red"))
    return True


def _cmd_report(cfg: "FrankiConfig", session: "Session") -> bool:
    from franki.reporter import run_report
    run_report(cfg, session)
    return True


def _cmd_search(cfg: "FrankiConfig", session: "Session", query: str) -> bool:
    import asyncio
    from rich.status import Status
    from franki.utils.search import web_search, SearchError

    if not query.strip():
        console.print(Text("  usage: /search <query>", style=TEXT_DIM))
        return True

    try:
        with Status(f"[{TEXT_DIM}]searching...[/]", spinner="dots", spinner_style=GOLD, console=console):
            result = asyncio.run(web_search(cfg, query))
    except SearchError as exc:
        console.print(Text(f"  search error: {exc}", style="red"))
        return True

    console.print()
    console.print(Text(f"  web search — {len(result.results)} results", style=TEXT_DIM))
    console.print(Rule(style=BORDER))

    if result.answer:
        console.print(Text(f"  {result.answer}", style=TEXT_BODY))
        console.print()

    for i, r in enumerate(result.results, 1):
        title   = r.get("title", "(no title)")
        url     = r.get("url", "")
        snippet = (r.get("content") or "").strip()[:200]
        if len(r.get("content", "")) > 200:
            snippet += "..."
        console.print(Text(f"  {i}. {title}", style=GOLD))
        console.print(Text(f"     {url}", style=TEXT_DIM))
        if snippet:
            console.print(Text(f"     {snippet}", style=TEXT_BODY))
        console.print()

    session.add_user(result.as_context())
    console.print(Text("  results added to context — ask me about them.", style=TEXT_DIM))
    console.print()
    return True


# ── Navigation ────────────────────────────────────────────────────────────────

def _cmd_skill(
    cfg: "FrankiConfig",
    session: "Session",
    arg: str,
    save_cfg_fn,
    redraw_bar_fn,
) -> bool:
    valid = get_all_skill_names()
    if not arg:
        console.print()
        for skill in valid:
            marker = ">" if skill == session.skill else " "
            style = GOLD if skill == session.skill else TEXT_BODY
            console.print(Text(f"  {marker} {skill}", style=style))
        console.print(Text(f"\n  Add custom skills: ~/.config/franki/skills/<name>.md", style=TEXT_DIM))
        console.print()
        return True

    if arg not in valid:
        console.print(Text(f"  unknown skill '{arg}' — valid: {', '.join(valid)}", style="red"))
        return True

    session.set_skill(arg)
    cfg.active_skill = arg
    save_cfg_fn(cfg)
    redraw_bar_fn()
    from franki.memory import track_skill
    track_skill(arg)
    console.print(Text(f"  skill → {arg}", style=GOLD))
    return True


def _cmd_model(
    cfg: "FrankiConfig",
    arg: str,
    save_cfg_fn,
    redraw_bar_fn,
    session: "Session | None" = None,
) -> bool:

    def _switch(provider_name: str, model_name: str) -> None:
        cfg.active_provider = provider_name
        if isinstance(cfg.providers.get(provider_name), dict):
            cfg.providers[provider_name]["model"] = model_name
        save_cfg_fn(cfg)
        redraw_bar_fn()
        if session is not None:
            from franki.environment import build_environment_block
            session.set_env_context(build_environment_block(cfg))
        console.print(Text(f"  switched to {provider_name} / {model_name}", style=GOLD))

    def _show_table(interactive: bool = False) -> None:
        console.print()
        if not cfg.providers:
            console.print(Text("  no providers configured.", style=TEXT_DIM))
        else:
            for i, (name, pdata) in enumerate(cfg.providers.items(), 1):
                if not isinstance(pdata, dict):
                    continue
                model    = pdata.get("model", "(no model)")
                is_active = name == cfg.active_provider
                marker   = ">" if is_active else " "
                style    = GOLD if is_active else TEXT_BODY
                console.print(Text(f"  {marker} {i}. {name}  ·  {model}", style=style))
        if interactive:
            console.print()
            console.print(Text(
                "  Type a name, number, or model to switch.\n"
                "  Commands: add  remove <name>  q",
                style=TEXT_DIM,
            ))
        console.print()

    # ── No arg → interactive menu ─────────────────────────────────────────────
    if not arg:
        _show_table(interactive=True)
        while True:
            console.print(Text("  > ", style=GOLD), end="")
            try:
                raw = input("").strip()
            except (KeyboardInterrupt, EOFError, OSError):
                console.print()
                break
            if not raw or raw.lower() == "q":
                break
            if raw.lower() == "add":
                from franki.setup_wizard import _add_provider
                _add_provider(cfg, is_first=False)
                save_cfg_fn(cfg)
                if not cfg.active_provider:
                    cfg.active_provider = cfg.first_configured_provider() or ""
                    save_cfg_fn(cfg)
                redraw_bar_fn()
                _show_table(interactive=True)
                continue
            if raw.lower().startswith("remove "):
                target = raw[7:].strip()
                if target in cfg.providers:
                    del cfg.providers[target]
                    if cfg.active_provider == target:
                        cfg.active_provider = cfg.first_configured_provider() or ""
                    save_cfg_fn(cfg)
                    redraw_bar_fn()
                    console.print(Text(f"  removed {target}", style=GOLD))
                    _show_table(interactive=True)
                else:
                    console.print(Text(f"  '{target}' not found", style="red"))
                continue
            # Try as number
            names = list(cfg.providers.keys())
            if raw.isdigit():
                idx = int(raw) - 1
                if 0 <= idx < len(names):
                    raw = names[idx]
            _do_switch(cfg, raw, save_cfg_fn, redraw_bar_fn, session, _switch, _show_table)
        return True

    # ── arg given → smart switch ──────────────────────────────────────────────
    _do_switch(cfg, arg, save_cfg_fn, redraw_bar_fn, session, _switch, _show_table)
    return True


def _do_switch(cfg, raw, save_cfg_fn, redraw_bar_fn, session, _switch, _show_table):
    """Resolve a name/model string and switch, with interactive pick if ambiguous."""
    # Exact provider match
    if raw in cfg.providers:
        model = cfg.providers[raw].get("model", "")
        _switch(raw, model)
        return

    # provider/model format (handles models with slashes like openai/gpt-4o)
    if "/" in raw:
        parts = raw.split("/", 1)
        pname, mname = parts[0].strip(), parts[1].strip()
        if pname in cfg.providers:
            _switch(pname, mname)
            return

    # Exact model name match across providers
    matches = [
        (pname, pdata.get("model", ""))
        for pname, pdata in cfg.providers.items()
        if isinstance(pdata, dict) and pdata.get("model", "").lower() == raw.lower()
    ]
    if len(matches) == 1:
        _switch(matches[0][0], matches[0][1])
        return

    # Partial model name match
    partial = [
        (pname, pdata.get("model", ""))
        for pname, pdata in cfg.providers.items()
        if isinstance(pdata, dict) and raw.lower() in pdata.get("model", "").lower()
    ]
    if len(partial) == 1:
        _switch(partial[0][0], partial[0][1])
        return
    if len(partial) > 1:
        console.print(Text(f"  multiple matches for '{raw}':", style=TEXT_DIM))
        for i, (p, m) in enumerate(partial, 1):
            console.print(Text(f"    {i}. {p} / {m}", style=TEXT_BODY))
        console.print(Text("  pick a number: ", style=TEXT_DIM), end="")
        try:
            sel = input("").strip()
            if sel.isdigit():
                idx = int(sel) - 1
                if 0 <= idx < len(partial):
                    _switch(partial[idx][0], partial[idx][1])
                    return
        except (KeyboardInterrupt, EOFError):
            console.print()
        return

    # Nothing matched — set as model name on active provider
    if cfg.active_provider and cfg.active_provider in cfg.providers:
        cfg.providers[cfg.active_provider]["model"] = raw
        save_cfg_fn(cfg)
        redraw_bar_fn()
        console.print(Text(f"  model → {raw}  (provider: {cfg.active_provider})", style=GOLD))
        return

    console.print(Text(f"  '{raw}' not found — type 'add' to add a provider", style="red"))


def _cmd_scope(session: "Session", arg: str, redraw_bar_fn) -> bool:
    if not arg or arg.lower() == "clear":
        session.set_scope(None)
        redraw_bar_fn()
        console.print(Text("  scope cleared.", style=TEXT_DIM))
    else:
        session.set_scope(arg)
        redraw_bar_fn()
        from franki.memory import track_scope
        track_scope(arg)
        console.print(Text(f"  scope → {arg}", style=GOLD))
    return True


def _cmd_cd(path: str, cfg: "FrankiConfig", session: "Session", redraw_bar_fn) -> bool:
    import os
    from franki.project_context import load_project_context
    from franki.custom_tools import parse_custom_tools
    from franki.agent.tools import register_custom_tools
    from franki.environment import build_environment_block
    if not path:
        console.print(Text(f"  {os.getcwd()}", style=TEXT_DIM))
        return True
    target = Path(path).expanduser().resolve()
    if not target.exists():
        console.print(Text(f"  not found: {path}", style="red"))
        return True
    if not target.is_dir():
        console.print(Text(f"  not a directory: {path}", style="red"))
        return True
    os.chdir(target)
    console.print(Text(f"  → {target}", style=GOLD))
    new_ctx = load_project_context(target)
    session.set_project_context(new_ctx)
    register_custom_tools(parse_custom_tools(new_ctx or ""))
    session.set_env_context(build_environment_block(cfg))
    redraw_bar_fn()
    if new_ctx:
        console.print(Text("  ◦ .franki.md loaded", style=TEXT_DIM))
    return True


# ── Security tools ────────────────────────────────────────────────────────────

def _cmd_mitre(cfg: "FrankiConfig", arg: str) -> bool:
    from franki.mitre import run_mitre
    run_mitre(cfg, arg)
    return True


def _cmd_payload(cfg: "FrankiConfig", arg: str) -> bool:
    from franki.ai_ops import run_payload
    run_payload(cfg, arg)
    return True


def _cmd_tools(cfg: "FrankiConfig", arg: str, skill: str) -> bool:
    from franki.ai_ops import run_tools
    run_tools(cfg, arg, skill)
    return True


def _cmd_explain(cfg: "FrankiConfig", arg: str) -> bool:
    from franki.ai_ops import run_explain
    run_explain(cfg, arg)
    return True


# ── Memory ────────────────────────────────────────────────────────────────────

def _cmd_remember(text: str, session: "Session") -> bool:
    if not text:
        console.print(Text("  usage: /remember <fact>", style=TEXT_DIM))
        return True
    from franki import memory
    entry = memory.add(text)
    session.set_memory_context(memory.get_context_string())
    console.print(Text(f"  remembered [#{entry['id']}]: {text}", style=GOLD))
    return True


def _cmd_memory() -> bool:
    from franki import memory

    facts  = memory.list_facts()
    scopes = memory.list_scopes()
    usage  = memory.skill_usage_counts()
    notes  = memory.list_notes()

    if not any([facts, scopes, usage, notes]):
        console.print(Text("  no memory yet. Use /remember, /note, or /scope.", style=TEXT_DIM))
        return True

    console.print()

    if facts:
        console.print(Text("  Facts", style=f"bold {GOLD}"))
        t = Table(show_header=False, box=None, padding=(0, 2))
        t.add_column(style=TEXT_DIM, no_wrap=True, width=6)
        t.add_column(style=TEXT_BODY)
        for f in facts:
            t.add_row(f"[{f['id']}]", f["content"])
        console.print(t)
        console.print()

    if scopes:
        console.print(Text("  Scope History", style=f"bold {GOLD}"))
        t = Table(show_header=False, box=None, padding=(0, 2))
        t.add_column(style=TEXT_DIM, no_wrap=True, width=4)
        t.add_column(style=TEXT_BODY)
        for i, s in enumerate(scopes, 1):
            t.add_row(f"{i}.", s)
        console.print(t)
        console.print()

    if usage:
        console.print(Text("  Skill Usage", style=f"bold {GOLD}"))
        t = Table(show_header=False, box=None, padding=(0, 2))
        t.add_column(style=TEXT_DIM, no_wrap=True, width=12)
        t.add_column(style=TEXT_BODY)
        for skill, count in sorted(usage.items(), key=lambda x: -x[1]):
            t.add_row(skill, f"{count}x")
        console.print(t)
        console.print()

    if notes:
        console.print(Text("  Recent Notes", style=f"bold {GOLD}"))
        t = Table(show_header=False, box=None, padding=(0, 2))
        t.add_column(style=TEXT_BODY)
        for n in notes[-5:]:
            t.add_row(n["text"])
        console.print(t)
        console.print()

    return True


def _cmd_forget(arg: str, session: "Session") -> bool:
    from franki import memory
    if not arg:
        console.print(Text("  usage: /forget <id>  or  /forget all", style=TEXT_DIM))
        return True
    if arg.lower() == "all":
        memory.clear_all()
        session.set_memory_context("")
        console.print(Text("  all memory cleared.", style=GOLD))
    else:
        try:
            item_id = int(arg)
        except ValueError:
            console.print(Text(f"  invalid id '{arg}' — use a number or 'all'", style="red"))
            return True
        if memory.remove(item_id):
            session.set_memory_context(memory.get_context_string())
            console.print(Text(f"  removed fact #{item_id}.", style=GOLD))
        else:
            console.print(Text(f"  no fact with id #{item_id}.", style=TEXT_DIM))
    return True


# ── Ollama ───────────────────────────────────────────────────────────────────

def _cmd_ollama(cfg, arg, save_cfg_fn, redraw_bar_fn) -> bool:
    import httpx
    base_url = "http://localhost:11434"
    # Allow override if user configured a different Ollama URL
    ollama_pdata = cfg.providers.get("ollama", {})
    if ollama_pdata.get("base_url"):
        base_url = ollama_pdata["base_url"].rstrip("/v1").rstrip("/")

    try:
        resp = httpx.get(f"{base_url}/api/tags", timeout=4)
        resp.raise_for_status()
        models = [m["name"] for m in resp.json().get("models", [])]
    except Exception as e:
        console.print(Text(f"  cannot reach Ollama at {base_url} — is it running?", style="red"))
        console.print(Text(f"  start it with: ollama serve", style=TEXT_DIM))
        return True

    if not models:
        console.print(Text("  Ollama is running but no models are installed.", style=TEXT_DIM))
        console.print(Text("  install one with: ollama pull llama3", style=TEXT_DIM))
        return True

    console.print()
    for i, name in enumerate(models, 1):
        marker = "●" if name == ollama_pdata.get("model") else " "
        console.print(Text(f"  {i}. {marker} {name}", style=GOLD if marker == "●" else TEXT_BODY))
    console.print()

    # If arg is a model name or number, switch directly
    if arg:
        target = arg
        if arg.isdigit():
            idx = int(arg) - 1
            if 0 <= idx < len(models):
                target = models[idx]
        if target in models:
            if "ollama" not in cfg.providers:
                cfg.providers["ollama"] = {
                    "base_url": "http://localhost:11434/v1",
                    "api_key": "ollama",
                    "model": target,
                    "key_required": False,
                    "local": True,
                    "priority": 1,
                }
            else:
                cfg.providers["ollama"]["model"] = target
            cfg.active_provider = "ollama"
            save_cfg_fn(cfg)
            redraw_bar_fn()
            console.print(Text(f"  switched to ollama / {target}", style=GOLD))
        else:
            console.print(Text(f"  model '{arg}' not in list", style="red"))
        return True

    # Interactive pick
    console.print(Text("  pick a model (number or name, Enter to cancel): ", style=TEXT_DIM), end="")
    try:
        sel = input("").strip()
    except (KeyboardInterrupt, EOFError):
        console.print()
        return True

    if not sel:
        return True

    target = sel
    if sel.isdigit():
        idx = int(sel) - 1
        if 0 <= idx < len(models):
            target = models[idx]

    if target not in models:
        console.print(Text(f"  '{target}' not found", style="red"))
        return True

    if "ollama" not in cfg.providers:
        cfg.providers["ollama"] = {
            "base_url": "http://localhost:11434/v1",
            "api_key": "ollama",
            "model": target,
            "key_required": False,
            "local": True,
            "priority": 1,
        }
    else:
        cfg.providers["ollama"]["model"] = target
    cfg.active_provider = "ollama"
    save_cfg_fn(cfg)
    redraw_bar_fn()
    console.print(Text(f"  switched to ollama / {target}", style=GOLD))
    return True


# ── Providers ────────────────────────────────────────────────────────────────

def _cmd_providers(
    cfg: "FrankiConfig",
    save_cfg_fn,
    redraw_bar_fn,
) -> bool:
    console.print()

    if cfg.providers:
        table = Table(show_header=False, box=None, padding=(0, 2))
        table.add_column(style=GOLD, no_wrap=True, width=14)
        table.add_column(style=TEXT_BODY, no_wrap=True, width=36)
        table.add_column(style=TEXT_DIM)

        for name, pdata in cfg.providers.items():
            if not isinstance(pdata, dict):
                continue
            model    = pdata.get("model", "(no model)")
            key      = cfg.get_provider_key(name)
            is_active = name == cfg.active_provider
            priority = pdata.get("priority", "—")

            if is_active:
                status = Text("active", style=GOLD)
            elif key or not pdata.get("key_required", True):
                status = Text("ready", style=TEXT_BODY)
            else:
                status = Text("no key", style="red")

            table.add_row(name, f"{name} / {model}", status)

        console.print(table)
    else:
        console.print(Text("  no providers configured.", style=TEXT_DIM))

    console.print()
    console.print(Text(
        "  Options:\n"
        "    a — add a provider\n"
        "    r — remove a provider\n"
        "    d — set default provider\n"
        "    q — done",
        style=TEXT_DIM,
    ))
    console.print()

    while True:
        console.print(Text("  choice: ", style=TEXT_DIM), end="")
        try:
            choice = input("").strip().lower()
        except (KeyboardInterrupt, EOFError):
            console.print()
            break

        if choice in ("q", ""):
            break
        elif choice == "a":
            from franki.setup_wizard import _add_provider
            _add_provider(cfg, is_first=False)
            save_cfg_fn(cfg)
            if not cfg.active_provider:
                cfg.active_provider = list(cfg.providers.keys())[0]
                save_cfg_fn(cfg)
            redraw_bar_fn()
        elif choice == "r":
            if not cfg.providers:
                console.print(Text("  no providers to remove.", style=TEXT_DIM))
                continue
            names = list(cfg.providers.keys())
            for i, name in enumerate(names, 1):
                console.print(Text(f"  {i}. {name}", style=TEXT_BODY))
            console.print(Text("  provider to remove: ", style=TEXT_DIM), end="")
            try:
                sel = input("").strip()
            except (KeyboardInterrupt, EOFError):
                console.print()
                continue
            target = ""
            if sel.isdigit():
                idx = int(sel) - 1
                if 0 <= idx < len(names):
                    target = names[idx]
            elif sel in names:
                target = sel
            if target:
                del cfg.providers[target]
                if cfg.active_provider == target:
                    first = cfg.first_configured_provider()
                    cfg.active_provider = first or ""
                save_cfg_fn(cfg)
                redraw_bar_fn()
                console.print(Text(f"  removed {target}.", style=GOLD))
            else:
                console.print(Text("  not found.", style="red"))
        elif choice == "d":
            if not cfg.providers:
                console.print(Text("  no providers configured.", style=TEXT_DIM))
                continue
            names = list(cfg.providers.keys())
            for i, name in enumerate(names, 1):
                marker = ">" if name == cfg.active_provider else " "
                console.print(Text(f"  {i}. {marker} {name}", style=TEXT_BODY))
            console.print(Text("  set default: ", style=TEXT_DIM), end="")
            try:
                sel = input("").strip()
            except (KeyboardInterrupt, EOFError):
                console.print()
                continue
            target = ""
            if sel.isdigit():
                idx = int(sel) - 1
                if 0 <= idx < len(names):
                    target = names[idx]
            elif sel in names:
                target = sel
            if target:
                cfg.active_provider = target
                save_cfg_fn(cfg)
                redraw_bar_fn()
                console.print(Text(f"  default → {target}", style=GOLD))
            else:
                console.print(Text("  not found.", style="red"))
        else:
            console.print(Text("  type a, r, d, or q", style=TEXT_DIM))

    return True


# ── MCP ───────────────────────────────────────────────────────────────────────

def _cmd_mcp(cfg: "FrankiConfig", arg: str, save_cfg_fn) -> bool:
    parts = arg.split(maxsplit=1)
    sub = parts[0].lower() if parts else ""

    if not sub or sub == "list":
        console.print()
        if not cfg.mcp:
            console.print(Text("  no MCP servers configured.", style=TEXT_DIM))
            console.print(Text(
                "  Add one with: /mcp add",
                style=TEXT_DIM,
            ))
        else:
            table = Table(show_header=False, box=None, padding=(0, 2))
            table.add_column(style=GOLD, no_wrap=True, width=16)
            table.add_column(style=TEXT_BODY)
            table.add_column(style=TEXT_DIM)
            for name, mdata in cfg.mcp.items():
                cmd = mdata.get("command", "")
                args = " ".join(mdata.get("args", []))
                enabled = "enabled" if mdata.get("enabled", True) else "disabled"
                table.add_row(name, f"{cmd} {args}".strip(), enabled)
            console.print(table)
        console.print()
        return True

    if sub == "add":
        console.print()
        console.print(Text("  Add MCP server", style=f"bold {GOLD}"))
        console.print(Text(
            "  MCP (Model Context Protocol) servers provide tools to the AI.\n"
            "  Example: filesystem server, GitHub, databases, etc.",
            style=TEXT_DIM,
        ))
        console.print()
        try:
            console.print(Text("  name (e.g. filesystem): ", style=TEXT_DIM), end="")
            name = input("").strip()
            if not name:
                console.print(Text("  cancelled.", style=TEXT_DIM))
                return True
            console.print(Text("  command (e.g. npx): ", style=TEXT_DIM), end="")
            command = input("").strip()
            console.print(Text("  args (space-separated, e.g. -y @modelcontextprotocol/server-filesystem /path): ", style=TEXT_DIM), end="")
            args_raw = input("").strip()
            args = args_raw.split() if args_raw else []
        except (KeyboardInterrupt, EOFError):
            console.print()
            console.print(Text("  cancelled.", style=TEXT_DIM))
            return True

        cfg.mcp[name] = {
            "command": command,
            "args": args,
            "enabled": True,
        }
        save_cfg_fn(cfg)
        console.print(Text(f"  MCP server '{name}' added.", style=GOLD))
        return True

    if sub == "remove":
        name = parts[1] if len(parts) > 1 else ""
        if not name:
            console.print(Text("  usage: /mcp remove <name>", style=TEXT_DIM))
            return True
        if name in cfg.mcp:
            del cfg.mcp[name]
            save_cfg_fn(cfg)
            console.print(Text(f"  removed MCP server '{name}'.", style=GOLD))
        else:
            console.print(Text(f"  MCP server '{name}' not found.", style="red"))
        return True

    console.print(Text("  usage: /mcp  |  /mcp add  |  /mcp remove <name>", style=TEXT_DIM))
    return True


# ── Templates ─────────────────────────────────────────────────────────────────

def _cmd_template(session: "Session", arg: str) -> "bool | str":
    from franki.templates import save_template, get_template, delete_template, list_templates, valid_name

    parts = arg.strip().split(maxsplit=1)
    sub   = parts[0].lower() if parts else ""

    if not arg.strip() or sub == "list":
        templates = list_templates()
        if not templates:
            console.print(Text("  no templates saved.  /template save <name>  to add one.", style=TEXT_DIM))
            return True
        console.print()
        t = Table(show_header=False, box=None, padding=(0, 2))
        t.add_column(style=GOLD, no_wrap=True, width=20)
        t.add_column(style=TEXT_BODY)
        for name, prompt in templates.items():
            t.add_row(name, prompt[:70] + ("…" if len(prompt) > 70 else ""))
        console.print(t)
        console.print(Text("  /template run <name>  to use one", style=TEXT_DIM))
        console.print()
        return True

    if sub == "save":
        rest = parts[1].strip() if len(parts) > 1 else ""
        name_parts = rest.split(maxsplit=1)
        if len(name_parts) < 2:
            console.print(Text("  usage: /template save <name> <prompt text>", style=TEXT_DIM))
            return True
        tname, prompt = name_parts[0], name_parts[1]
        if not valid_name(tname):
            console.print(Text("  name must be alphanumeric/dash/underscore, max 40 chars.", style="red"))
            return True
        save_template(tname, prompt)
        console.print(Text(f"  template '{tname}' saved.", style=GOLD))
        return True

    if sub == "delete":
        tname = parts[1].strip() if len(parts) > 1 else ""
        if not tname:
            console.print(Text("  usage: /template delete <name>", style=TEXT_DIM))
            return True
        if delete_template(tname):
            console.print(Text(f"  template '{tname}' deleted.", style=GOLD))
        else:
            console.print(Text(f"  template '{tname}' not found.", style="red"))
        return True

    if sub == "run":
        tname = parts[1].strip() if len(parts) > 1 else ""
        prompt = get_template(tname) if tname else None
        if not prompt:
            console.print(Text(f"  template '{tname}' not found — use /template to list.", style="red"))
            return True
        console.print(Text(f"  running template: {tname}", style=TEXT_DIM))
        return f"template:{prompt}"

    # Shorthand: /template <name> → run it
    prompt = get_template(sub)
    if prompt:
        console.print(Text(f"  running template: {sub}", style=TEXT_DIM))
        return f"template:{prompt}"

    console.print(Text(
        "  usage: /template  |  /template save <name> <prompt>  |  "
        "/template run <name>  |  /template delete <name>",
        style=TEXT_DIM,
    ))
    return True


def _cmd_toolperms(cfg: "FrankiConfig", arg: str, save_cfg_fn) -> bool:
    """Manage per-tool permissions: always | ask | never."""
    from rich.table import Table
    parts = arg.strip().split(None, 1)
    sub   = parts[0].lower() if parts else "list"
    tool  = parts[1].strip() if len(parts) > 1 else ""

    if sub == "list" or not sub:
        perms = getattr(cfg, "tool_permissions", {}) or {}
        if not perms:
            console.print(Text(
                "  no overrides set — all tools use default (ask) behaviour",
                style=TEXT_DIM,
            ))
        else:
            t = Table(show_header=False, box=None, padding=(0, 2))
            t.add_column(style=GOLD, no_wrap=True)
            t.add_column(style=TEXT_BODY)
            for tname, perm in sorted(perms.items()):
                t.add_row(tname, perm)
            console.print(t)
        console.print(Text(
            "  /toolperms allow|block|reset <tool_name>",
            style=TEXT_DIM,
        ))
        return True

    if sub in ("allow", "block", "reset") and not tool:
        console.print(Text(f"  usage: /toolperms {sub} <tool_name>", style=TEXT_DIM))
        return True

    perms = dict(getattr(cfg, "tool_permissions", {}) or {})
    if sub == "allow":
        perms[tool] = "always"
        cfg.tool_permissions = perms
        save_cfg_fn(cfg)
        console.print(Text(f"  {tool}: always allowed (no confirmation)", style=GOLD))
    elif sub == "block":
        perms[tool] = "never"
        cfg.tool_permissions = perms
        save_cfg_fn(cfg)
        console.print(Text(f"  {tool}: blocked", style="red"))
    elif sub == "reset":
        perms.pop(tool, None)
        cfg.tool_permissions = perms
        save_cfg_fn(cfg)
        console.print(Text(f"  {tool}: reset to default (ask)", style=TEXT_DIM))
    else:
        console.print(Text(
            "  usage: /toolperms list | allow <tool> | block <tool> | reset <tool>",
            style=TEXT_DIM,
        ))
    return True


# ── Sandbox ───────────────────────────────────────────────────────────────────

def _cmd_autocommit(cfg: "FrankiConfig", arg: str, save_cfg_fn) -> bool:
    """Toggle auto-commit after each agent turn that writes files."""
    arg = arg.strip().lower()
    if arg == "on":
        cfg.auto_commit = True
        save_cfg_fn(cfg)
        console.print(Text(
            "  auto-commit on — git commits will be created after each agent file edit",
            style=GOLD,
        ))
    elif arg == "off":
        cfg.auto_commit = False
        save_cfg_fn(cfg)
        console.print(Text("  auto-commit off.", style=TEXT_DIM))
    else:
        state = "on" if getattr(cfg, "auto_commit", False) else "off"
        console.print(Text(
            f"  auto-commit: {state}  ·  /autocommit on|off",
            style=TEXT_DIM,
        ))
    return True


def _cmd_sandbox(session: "Session", arg: str) -> bool:
    sub = arg.strip().lower()
    if sub == "on":
        session.sandbox = True
        console.print(Text(
            "  sandbox on — write_file, edit_file, apply_patch, run_command blocked.",
            style=GOLD,
        ))
    elif sub == "off":
        session.sandbox = False
        console.print(Text("  sandbox off — all tools enabled.", style=GOLD))
    else:
        state = "on" if session.sandbox else "off"
        console.print(Text(f"  sandbox: {state}  ·  /sandbox on|off", style=TEXT_DIM))
    return True


# ── Session branching ─────────────────────────────────────────────────────────

def _cmd_branch(session: "Session", arg: str) -> bool:
    from datetime import datetime
    parts = arg.strip().split(maxsplit=1)
    sub   = parts[0].lower() if parts else ""

    if not arg.strip() or sub == "list":
        branches = session.list_branches()
        if not branches:
            console.print(Text("  no branches saved.  /branch save [name]  to checkpoint.", style=TEXT_DIM))
            return True
        console.print()
        t = Table(show_header=False, box=None, padding=(0, 2))
        t.add_column(style=TEXT_DIM, no_wrap=True, width=4)
        t.add_column(style=GOLD)
        for i, name in enumerate(branches, 1):
            t.add_row(str(i), name)
        console.print(t)
        console.print(Text("  /branch restore <name>  to revert to a checkpoint", style=TEXT_DIM))
        console.print()
        return True

    if sub == "save":
        name = parts[1].strip() if len(parts) > 1 else datetime.now().strftime("branch-%H%M%S")
        session.create_branch(name)
        console.print(Text(f"  checkpoint '{name}' saved — {len(session._messages)} messages.", style=GOLD))
        return True

    if sub == "restore":
        name = parts[1].strip() if len(parts) > 1 else ""
        if not name:
            console.print(Text("  usage: /branch restore <name>", style=TEXT_DIM))
            return True
        if session.restore_branch(name):
            console.print(Text(f"  restored to checkpoint '{name}'.", style=GOLD))
        else:
            console.print(Text(f"  checkpoint '{name}' not found.", style="red"))
        return True

    if sub == "delete":
        name = parts[1].strip() if len(parts) > 1 else ""
        if name in session._branches:
            del session._branches[name]
            console.print(Text(f"  checkpoint '{name}' deleted.", style=GOLD))
        else:
            console.print(Text(f"  checkpoint '{name}' not found.", style="red"))
        return True

    # Shorthand: /branch <name> → save with that name
    session.create_branch(sub)
    console.print(Text(f"  checkpoint '{sub}' saved.", style=GOLD))
    return True


# ── Audit log ─────────────────────────────────────────────────────────────────

def _cmd_audit() -> bool:
    from franki.audit import tail, AUDIT_LOG
    entries = tail(30)
    if not entries:
        console.print(Text(f"  no audit entries yet.  log: {AUDIT_LOG}", style=TEXT_DIM))
        return True

    console.print()
    console.print(Text("  Recent tool executions (last 30)", style=f"bold {GOLD}"))
    t = Table(show_header=False, box=None, padding=(0, 2))
    t.add_column(style=TEXT_DIM, no_wrap=True, width=10)
    t.add_column(style=GOLD, no_wrap=True, width=18)
    t.add_column(style=TEXT_BODY)
    for e in entries:
        ts    = e.get("ts", "")[-8:]  # HH:MM:SS
        tool  = e.get("tool", "")
        args  = e.get("args", {})
        brief = next(iter(args.values()), "") if args else ""
        t.add_row(ts, tool, str(brief)[:60])
    console.print(t)
    console.print(Text(f"\n  full log: {AUDIT_LOG}", style=TEXT_DIM))
    console.print()
    return True


# ── System ────────────────────────────────────────────────────────────────────

def _cmd_auto(cfg: "FrankiConfig", arg: str, save_cfg_fn) -> bool:
    parts = arg.lower().split()

    if not parts:
        # Show current state without changing anything
        state   = "on" if cfg.auto_accept else "off"
        notify  = "on" if cfg.notify_on_done else "off"
        copy    = "on" if getattr(cfg, "auto_copy", False) else "off"
        console.print()
        t = Table(show_header=False, box=None, padding=(0, 2))
        t.add_column(style=TEXT_DIM, no_wrap=True, width=18)
        t.add_column(style=GOLD)
        t.add_row("Auto-accept",      state)
        t.add_row("Notify on done",   notify)
        t.add_row("Auto-copy",        copy)
        console.print(t)
        console.print(Text(
            "  /auto on|off  ·  /auto notify on|off  ·  /auto copy on|off",
            style=TEXT_DIM,
        ))
        console.print()
        return True

    if parts[0] == "on":
        cfg.auto_accept = True
        save_cfg_fn(cfg)
        note = "  (notifications on)" if cfg.notify_on_done else ""
        console.print(Text(f"  auto-accept → on{note}", style=GOLD))
        return True

    if parts[0] == "off":
        cfg.auto_accept = False
        save_cfg_fn(cfg)
        console.print(Text("  auto-accept → off", style=GOLD))
        return True

    if parts[0] == "notify" and len(parts) > 1:
        if parts[1] == "on":
            cfg.notify_on_done = True
            save_cfg_fn(cfg)
            console.print(Text("  notify on done → on", style=GOLD))
        elif parts[1] == "off":
            cfg.notify_on_done = False
            save_cfg_fn(cfg)
            console.print(Text("  notify on done → off", style=GOLD))
        else:
            console.print(Text("  usage: /auto notify on|off", style=TEXT_DIM))
        return True

    if parts[0] == "copy" and len(parts) > 1:
        if parts[1] == "on":
            cfg.auto_copy = True
            save_cfg_fn(cfg)
            console.print(Text("  auto-copy → on  (responses copied to clipboard automatically)", style=GOLD))
        elif parts[1] == "off":
            cfg.auto_copy = False
            save_cfg_fn(cfg)
            console.print(Text("  auto-copy → off", style=GOLD))
        else:
            console.print(Text("  usage: /auto copy on|off", style=TEXT_DIM))
        return True

    console.print(Text(
        "  usage: /auto  |  /auto on|off  |  /auto notify on|off  |  /auto copy on|off",
        style=TEXT_DIM,
    ))
    return True


def _cmd_test(cfg: "FrankiConfig", session: "Session", arg: str) -> bool:
    from franki.utils.test_runner import detect_test_cmd, run_tests

    cmd = arg.strip() if arg.strip() else detect_test_cmd()
    if not cmd:
        console.print(Text(
            "  no test runner detected. specify one: /test <command>\n"
            "  e.g. /test python3 -m pytest --tb=short -q",
            style=TEXT_DIM,
        ))
        return True

    console.print()
    console.print(Text(f"  ◦ running  {cmd}", style=TEXT_DIM))
    output, rc = run_tests(cmd)

    status_style = GOLD if rc == 0 else "red"
    status_word  = "passed" if rc == 0 else f"failed (exit {rc})"
    console.print(Text(f"  tests {status_word}", style=status_style))
    console.print()

    # Show a preview
    lines   = output.splitlines()
    preview = "\n".join(f"  {l}" for l in lines[:40])
    if len(lines) > 40:
        preview += f"\n  ... ({len(lines) - 40} more lines — full output in context)"
    console.print(Text(preview, style=TEXT_BODY))
    console.print()

    # Inject full output into the session so the AI can analyse it
    context_msg = (
        f"Test run: `{cmd}`  —  {status_word}\n\n"
        f"```\n{output}\n```\n\n"
        + ("All tests passed." if rc == 0
           else "Please analyse these test failures and fix them.")
    )
    session.add_user(context_msg)
    console.print(Text(
        "  test output added to context — type a question or just send a message to get analysis.",
        style=TEXT_DIM,
    ))
    console.print()
    return True


def _cmd_sessions(
    cfg: "FrankiConfig",
    session: "Session",
    arg: str,
    save_cfg_fn,
    redraw_bar_fn,
) -> bool:
    from franki.session_store import list_sessions, load_session_data, delete_session, save_session
    from franki.session import Session as Sess

    parts = arg.strip().split(maxsplit=1)
    sub = parts[0].lower() if parts else ""

    if not sub or sub == "list":
        sessions = list_sessions()
        if not sessions:
            console.print(Text("  no saved sessions.", style=TEXT_DIM))
            return True
        console.print()
        t = Table(show_header=False, box=None, padding=(0, 2))
        t.add_column(style=TEXT_DIM, no_wrap=True, width=4)
        t.add_column(style=GOLD, no_wrap=True, width=10)
        t.add_column(style=TEXT_DIM, no_wrap=True, width=22)
        t.add_column(style=TEXT_BODY)
        for i, s in enumerate(sessions, 1):
            date_str = s["saved_at"][:16].replace("T", " ") if s["saved_at"] else "?"
            t.add_row(
                str(i),
                s["skill"],
                f"{date_str}  ·  {s['message_count']}msg",
                s["preview"][:50] if s["preview"] else "(no preview)",
            )
        console.print(t)
        console.print(Text(
            "\n  /sessions resume <n>  ·  /sessions delete <n>  ·  /sessions save",
            style=TEXT_DIM,
        ))
        console.print()
        return True

    if sub == "save":
        from franki.session_store import save_session as _save
        path = _save(session, cfg)
        if path:
            console.print(Text(f"  session saved → {path.name}", style=GOLD))
        else:
            console.print(Text("  nothing to save (empty session).", style=TEXT_DIM))
        return True

    if sub == "resume":
        idx_str = parts[1].strip() if len(parts) > 1 else ""
        if not idx_str.isdigit():
            console.print(Text("  usage: /sessions resume <number>", style=TEXT_DIM))
            return True
        data = load_session_data(int(idx_str))
        if data is None:
            console.print(Text(f"  session #{idx_str} not found.", style="red"))
            return True

        from franki.memory import get_context_string
        from franki.project_context import load_project_context
        from franki.routing import RoutingTracker
        from franki.cost_tracker import CostTracker
        from franki.change_tracker import ChangeTracker

        mem = get_context_string()
        proj = load_project_context()
        restored = Sess.from_dict(data, memory_context=mem, project_context=proj)
        restored.routing_tracker = RoutingTracker()
        restored.cost_tracker    = CostTracker()
        restored.change_tracker  = ChangeTracker()

        # Swap current session contents in-place so the REPL keeps its references
        session.__dict__.update(restored.__dict__)

        cfg.active_skill = session.skill
        cfg.active_provider = data.get("provider", cfg.active_provider) or cfg.active_provider
        save_cfg_fn(cfg)
        redraw_bar_fn()

        msgs = session.history_display()
        console.print(Text(
            f"  resumed  [{session.skill}]  {len(msgs)} messages",
            style=GOLD,
        ))
        return True

    if sub == "delete":
        idx_str = parts[1].strip() if len(parts) > 1 else ""
        if not idx_str.isdigit():
            console.print(Text("  usage: /sessions delete <number>", style=TEXT_DIM))
            return True
        if delete_session(int(idx_str)):
            console.print(Text(f"  session #{idx_str} deleted.", style=GOLD))
        else:
            console.print(Text(f"  session #{idx_str} not found.", style="red"))
        return True

    console.print(Text(
        "  usage: /sessions  |  /sessions resume <n>  |  /sessions delete <n>  |  /sessions save",
        style=TEXT_DIM,
    ))
    return True


def _cmd_undo(session: "Session") -> bool:
    ct = getattr(session, "change_tracker", None)
    if ct is None or ct.count == 0:
        console.print(Text("  nothing to undo.", style=TEXT_DIM))
        return True
    path = ct.revert_last()
    if path:
        console.print(Text(f"  reverted → {path}", style=GOLD))
        if ct.count > 0:
            console.print(Text(f"  {ct.count} change(s) remaining  (/undo again to revert more)", style=TEXT_DIM))
    else:
        console.print(Text("  revert failed.", style="red"))
    return True


def _cmd_diff(session: "Session") -> bool:
    from franki.utils.highlight import render_response as _render
    ct = getattr(session, "change_tracker", None)
    if ct is None or ct.count == 0:
        console.print(Text("  no changes recorded in this session.", style=TEXT_DIM))
        return True

    diffs = ct.diff_summary()
    console.print()
    for entry in diffs:
        action = "created" if entry["is_new_file"] else f"+{entry['lines_added']} -{entry['lines_removed']}"
        console.print(Text(f"  {entry['path']}  [{action}]", style=f"bold {GOLD}"))
        if entry["diff"]:
            diff_text = "\n".join(entry["diff"][:40])
            if len(entry["diff"]) > 40:
                diff_text += f"\n... ({len(entry['diff']) - 40} more lines)"
            from rich.syntax import Syntax
            console.print(Syntax(diff_text, "diff", theme="monokai", background_color="default"))
        console.print()
    console.print(Text(
        f"  {len(diffs)} file(s) changed  ·  /undo to revert the last change",
        style=TEXT_DIM,
    ))
    console.print()
    return True


def _cmd_profile(
    cfg: "FrankiConfig",
    arg: str,
    save_cfg_fn,
    redraw_bar_fn,
) -> bool:
    from franki.profiles import save_profile, load_profile, list_profiles, delete_profile, _valid_name

    parts = arg.strip().split(maxsplit=1)
    sub  = parts[0].lower() if parts else ""
    name = parts[1].strip() if len(parts) > 1 else ""

    if not sub or sub == "list":
        profiles = list_profiles()
        console.print()
        if not profiles:
            console.print(Text("  no profiles saved yet.", style=TEXT_DIM))
        else:
            t = Table(show_header=False, box=None, padding=(0, 2))
            t.add_column(style=GOLD, no_wrap=True)
            for p in profiles:
                t.add_row(p)
            console.print(t)
        console.print(Text(
            "\n  /profile save <name>  ·  /profile load <name>  ·  /profile delete <name>",
            style=TEXT_DIM,
        ))
        console.print()
        return True

    if sub == "save":
        if not name:
            console.print(Text("  usage: /profile save <name>", style=TEXT_DIM))
            return True
        if not _valid_name(name):
            console.print(Text("  profile name must be 1-32 alphanumeric/dash/underscore chars.", style="red"))
            return True
        path = save_profile(name, cfg)
        console.print(Text(f"  profile '{name}' saved.", style=GOLD))
        return True

    if sub == "load":
        if not name:
            console.print(Text("  usage: /profile load <name>", style=TEXT_DIM))
            return True
        loaded = load_profile(name)
        if loaded is None:
            console.print(Text(f"  profile '{name}' not found.", style="red"))
            return True
        # Apply profile fields (keep session_count)
        count = cfg.session_count
        cfg.__dict__.update(loaded.__dict__)
        cfg.session_count = count
        save_cfg_fn(cfg)
        redraw_bar_fn()
        console.print(Text(f"  profile '{name}' loaded.", style=GOLD))
        return True

    if sub == "delete":
        if not name:
            console.print(Text("  usage: /profile delete <name>", style=TEXT_DIM))
            return True
        if delete_profile(name):
            console.print(Text(f"  profile '{name}' deleted.", style=GOLD))
        else:
            console.print(Text(f"  profile '{name}' not found.", style="red"))
        return True

    console.print(Text(
        "  usage: /profile  |  /profile save <name>  |  /profile load <name>  |  /profile delete <name>",
        style=TEXT_DIM,
    ))
    return True


def _cmd_init(cfg: "FrankiConfig", save_cfg_fn, redraw_bar_fn) -> bool:
    from franki.setup_wizard import run_wizard
    updated = run_wizard(existing_cfg=cfg)
    # Update in-place so the running session uses new provider immediately
    cfg.providers = updated.providers
    cfg.active_provider = updated.active_provider
    cfg.auto_skill = updated.auto_skill
    cfg.export_path = updated.export_path
    save_cfg_fn(cfg)
    redraw_bar_fn()
    return True


def _cmd_config_edit(cfg: "FrankiConfig", save_cfg_fn, redraw_bar_fn) -> bool:
    from franki.config_cmd import run_interactive_config
    run_interactive_config(cfg, save_cfg_fn, redraw_bar_fn)
    return True


def _cmd_help() -> bool:
    console.print()

    sections = [
        ("Conversation", [
            ("/clear",                  "clear conversation history"),
            ("/compact",                "summarise history to save context"),
            ("/rewind",                 "undo the last exchange"),
            ("/retry",                  "re-run the last message (fresh call)"),
            ("/history",                "show conversation log for this session"),
            ("/context",                "session dashboard: model, memory, tokens"),
            ("/pin <message>",          "pin a persistent reminder into every request"),
            ("/pin",                    "list pinned reminders"),
            ("/pin clear [n]",          "remove one pin or all pins"),
        ]),
        ("Testing", [
            ("/test",                   "run project tests and inject output into context"),
            ("/test <command>",         "run a specific test command"),
        ]),
        ("Sessions", [
            ("/sessions",               "list saved sessions"),
            ("/sessions resume <n>",    "restore a previous session by number"),
            ("/sessions save",          "save current session now"),
            ("/sessions delete <n>",    "delete a saved session"),
        ]),
        ("Agent changes", [
            ("/undo",                   "revert the last file change made by the agent"),
            ("/diff",                   "show a diff of all files changed this session"),
        ]),
        ("Output", [
            ("/export",                 "save session as markdown"),
            ("/copy",                   "copy last AI response to clipboard"),
            ("/note <text>",            "save a timestamped note"),
            ("/report",                 "generate a report from the session"),
            ("/search <query>",         "web search — injects results into context"),
        ]),
        ("Navigation", [
            ("/cd [path]",              "change working directory  (reloads .franki.md)"),
            ("/skill [name]",           "switch skill  (coding / pentest / soc / security + custom)"),
            ("/model [name]",           "switch model  (format: provider/model-name)"),
            ("/scope [ip/cidr]",        "set pentest target scope"),
            ("/scope clear",            "clear active scope"),
        ]),
        ("Routing & cost", [
            ("/routing",                "show provider ranking and routing reasons for current skill"),
            ("/cost",                   "show token usage and estimated cost for this session"),
        ]),
        ("Security tools", [
            ("/mitre <behaviour>",      "map a behaviour to MITRE ATT&CK"),
            ("/payload <type>",         "suggest payloads for an attack type"),
            ("/tools <task>",           "suggest the right tools for a task"),
            ("/explain <tool>",         "explain a tool and its usage"),
        ]),
        ("Memory", [
            ("/remember <fact>",        "save a fact to long-term memory"),
            ("/memories",               "list all saved memory, scopes, notes"),
            ("/forget <id|all>",        "remove a fact by id, or clear all memory"),
        ]),
        ("Profiles", [
            ("/profile",                "list saved config profiles"),
            ("/profile save <name>",    "snapshot current config as a named profile"),
            ("/profile load <name>",    "restore a named profile"),
            ("/profile delete <name>",  "delete a profile"),
        ]),
        ("Providers / MCP", [
            ("/providers",              "add, remove, or set default provider"),
            ("/providers add",          "jump straight to adding a provider"),
            ("/ollama",                 "list installed Ollama models and pick one"),
            ("/ollama <model>",         "switch directly to an Ollama model"),
            ("/mcp",                    "list MCP server connections"),
            ("/mcp add",                "add an MCP server"),
            ("/mcp remove <name>",      "remove an MCP server"),
        ]),
        ("Templates", [
            ("/template",               "list saved prompt templates"),
            ("/template save <n> <p>",  "save prompt p as template n"),
            ("/template run <name>",    "run a saved template  (or just /template <name>)"),
            ("/template delete <name>", "delete a template"),
        ]),
        ("Branching", [
            ("/branch save [name]",     "checkpoint the current conversation"),
            ("/branch restore <name>",  "revert to a saved checkpoint"),
            ("/branch",                 "list checkpoints"),
        ]),
        ("System", [
            ("/auto",                   "show auto-accept status"),
            ("/auto on|off",            "enable or disable auto-accept mode"),
            ("/auto notify on|off",     "toggle task-done notifications"),
            ("/autocommit on|off",      "auto git-commit after each agent file edit"),
            ("/toolperms list",              "show per-tool permission overrides"),
            ("/toolperms allow|block <tool>","set a tool to always-allow or always-block"),
            ("/hooks list",                  "show configured pre/post tool hooks"),
            ("/hooks set <event> <cmd>",     "run a shell command before/after a tool"),
            ("/think on|off|<N>",            "enable extended thinking with token budget"),
            ("/sandbox on|off",         "block all destructive tools (write, run, patch)"),
            ("/audit",                  "show recent tool execution log"),
            ("/init",                   "re-run the provider setup wizard"),
            ("/config",                 "open the interactive config editor"),
            ("/feedback <thoughts>",    "send feedback — saved locally"),
            ("/help",                   "show this command list"),
            ("exit  or  quit",          "exit (prompts to save session)"),
        ]),
        ("Input", [
            ("Alt+Enter  (or Esc→Enter)", "insert a newline without submitting"),
            ("Enter",                    "submit the message"),
        ]),
        ("Context injection  (in messages)", [
            ("@file.py",                "inject a file into the message"),
            ("@src/",                   "inject a directory tree + files"),
            ("@https://...",            "fetch a URL and inject its text"),
            ("@git",                    "inject branch, status, diff, and recent commits"),
            ("@clipboard",              "inject current clipboard contents"),
        ]),
        ("Custom tools  (.franki.md)", [
            ("```franki-tools",         "define project-specific agent tools"),
            ("[tool_name]",             "tool section — description, command, params"),
        ]),
        ("One-shot CLI  (outside REPL)", [
            ("franki fix <file>",       "analyse and fix bugs in a file"),
            ("franki review <file>",    "code review a file"),
            ("franki commit",           "generate a commit message from git diff"),
            ("franki explain <file>",   "explain what a file does"),
            ("franki resume [n]",       "resume a saved session"),
            ("franki profile <cmd>",    "manage config profiles from the shell"),
        ]),
    ]

    for section_name, rows in sections:
        t = Table(show_header=False, box=None, padding=(0, 2))
        t.add_column(style=GOLD, no_wrap=True, width=28)
        t.add_column(style=TEXT_BODY)
        console.print(Text(f"  {section_name}", style=f"bold {GOLD}"))
        for cmd, desc in rows:
            t.add_row(cmd, desc)
        console.print(t)
        console.print()

    return True


def _cmd_feedback(arg: str, session: "Session") -> bool:
    if not arg.strip():
        console.print(Text(
            "  usage: /feedback <your thoughts>  e.g. /feedback the pentest mode is great",
            style=TEXT_DIM,
        ))
        return True
    from franki.feedback import save_feedback
    stats = session.message_stats()
    save_feedback(arg.strip(), skill=session.skill, msgs=stats["user"])
    console.print(Text("  thanks — noted.", style=GOLD))
    return True


def _cmd_hooks(cfg: "FrankiConfig", arg: str, save_cfg_fn) -> bool:
    """Manage pre/post tool hooks.

    /hooks               — list configured hooks
    /hooks set <event> <cmd>  — set a hook command
    /hooks unset <event>      — remove a hook
    /hooks clear         — remove all hooks

    Events: pre_tool, post_tool, pre_tool.<name>, post_tool.<name>,
            pre_session, post_session
    """
    parts = arg.strip().split(maxsplit=1)
    sub = parts[0].lower() if parts else "list"

    if sub in ("list", ""):
        console.print()
        if not cfg.hooks:
            console.print(Text("  no hooks configured", style=TEXT_DIM))
            console.print(Text(
                "  /hooks set <event> <command>  e.g.  /hooks set post_tool.write_file black {FRANKI_TOOL}",
                style=TEXT_DIM,
            ))
        else:
            t = Table(show_header=False, box=None, padding=(0, 2))
            t.add_column(style=GOLD, no_wrap=True, width=28)
            t.add_column(style=TEXT_BODY)
            for event, cmd in cfg.hooks.items():
                t.add_row(event, cmd)
            console.print(t)
        console.print()
        return True

    rest = parts[1] if len(parts) > 1 else ""

    if sub == "set":
        kv = rest.split(maxsplit=1)
        if len(kv) < 2:
            console.print(Text("  usage: /hooks set <event> <shell command>", style=TEXT_DIM))
            return True
        event, cmd = kv[0], kv[1]
        cfg.hooks[event] = cmd
        save_cfg_fn(cfg)
        console.print(Text(f"  hook set: {event} → {cmd}", style=GOLD))
        return True

    if sub == "unset":
        event = rest.strip()
        if not event:
            console.print(Text("  usage: /hooks unset <event>", style=TEXT_DIM))
            return True
        removed = cfg.hooks.pop(event, None)
        if removed:
            save_cfg_fn(cfg)
            console.print(Text(f"  hook removed: {event}", style=GOLD))
        else:
            console.print(Text(f"  no hook named '{event}'", style=TEXT_DIM))
        return True

    if sub == "clear":
        cfg.hooks.clear()
        save_cfg_fn(cfg)
        console.print(Text("  all hooks cleared", style=GOLD))
        return True

    console.print(Text("  usage: /hooks list | set <event> <cmd> | unset <event> | clear", style=TEXT_DIM))
    return True


def _cmd_think(cfg: "FrankiConfig", arg: str, save_cfg_fn) -> bool:
    """Toggle extended thinking.

    /think          — show current status
    /think on       — enable with default budget (8000 tokens)
    /think <N>      — enable with N token budget
    /think off      — disable extended thinking
    """
    DEFAULT_BUDGET = 8000
    part = arg.strip().lower()

    if not part or part == "status":
        budget = getattr(cfg, "thinking_budget", 0) or 0
        state = f"on  (budget: {budget:,} tokens)" if budget > 0 else "off"
        console.print()
        console.print(Text(f"  extended thinking: {state}", style=GOLD))
        console.print(Text(
            "  /think on | /think <N> | /think off",
            style=TEXT_DIM,
        ))
        console.print()
        return True

    if part == "off":
        cfg.thinking_budget = 0
        save_cfg_fn(cfg)
        console.print(Text("  extended thinking → off", style=GOLD))
        return True

    if part == "on":
        cfg.thinking_budget = DEFAULT_BUDGET
        save_cfg_fn(cfg)
        console.print(Text(f"  extended thinking → on  ({DEFAULT_BUDGET:,} token budget)", style=GOLD))
        return True

    try:
        budget = int(part)
        if budget < 1024:
            console.print(Text("  minimum budget is 1024 tokens", style="yellow"))
            return True
        cfg.thinking_budget = budget
        save_cfg_fn(cfg)
        console.print(Text(f"  extended thinking → on  ({budget:,} token budget)", style=GOLD))
    except ValueError:
        console.print(Text("  usage: /think on | off | <token_budget>", style=TEXT_DIM))
    return True
