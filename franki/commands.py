from __future__ import annotations
from typing import TYPE_CHECKING

from rich.console import Console
from rich.text import Text
from rich.table import Table
from rich.rule import Rule
from rich.panel import Panel
from franki.skills import VALID_SKILLS, get_skill_icon

if TYPE_CHECKING:
    from franki.config import FrankiConfig
    from franki.session import Session

console = Console(highlight=False)

GOLD      = "#d4a853"
TEXT_DIM  = "#555555"
TEXT_BODY = "#a8a8a8"
BORDER    = "#2d2d2d"


# ── Dispatch ──────────────────────────────────────────────────────────────────

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

    # ── Output ────────────────────────────────────────────────────────────────
    if cmd == "/export":
        return _cmd_export(cfg, session)
    if cmd == "/copy":
        return _cmd_copy(session)
    if cmd == "/note":
        return _cmd_note(cfg, arg)
    if cmd == "/report":
        return _cmd_report(cfg, session)

    # ── Navigation ────────────────────────────────────────────────────────────
    if cmd == "/skill":
        return _cmd_skill(cfg, session, arg, save_cfg_fn, redraw_bar_fn)
    if cmd == "/model":
        return _cmd_model(cfg, arg, save_cfg_fn, redraw_bar_fn)
    if cmd == "/scope":
        return _cmd_scope(session, arg, redraw_bar_fn)

    # ── CEH / Security ────────────────────────────────────────────────────────
    if cmd == "/quiz":
        return _cmd_quiz(cfg, session)
    if cmd == "/mitre":
        return _cmd_mitre(cfg, arg)
    if cmd == "/payload":
        return _cmd_payload(cfg, arg)
    if cmd == "/tools":
        return _cmd_tools(cfg, arg, session.skill)
    if cmd == "/explain":
        return _cmd_explain(cfg, arg)

    # ── Search ───────────────────────────────────────────────────────────────
    if cmd == "/search":
        return _cmd_search(cfg, session, arg)

    # ── Memory ────────────────────────────────────────────────────────────────
    if cmd == "/remember":
        return _cmd_remember(arg, session)
    if cmd in ("/memory", "/memories"):
        return _cmd_memory()
    if cmd == "/forget":
        return _cmd_forget(arg, session)

    # ── System ────────────────────────────────────────────────────────────────
    if cmd == "/connect":
        return _cmd_connect(cfg, arg, save_cfg_fn, redraw_bar_fn)
    if cmd == "/init":
        return _cmd_init()
    if cmd == "/config":
        return _cmd_config()
    if cmd == "/providers":
        return _cmd_providers(cfg)
    if cmd == "/help":
        return _cmd_help()

    # ── Exit aliases — handled upstream in main.py before reaching here ──────
    if cmd in ("/exit", "/quit", "/q"):
        raise SystemExit(0)  # fallback only if called outside the REPL

    console.print(Text(f"  unknown command '{cmd}' — /help for the full list", style=TEXT_DIM))
    return True


# ── Conversation commands ─────────────────────────────────────────────────────

def _cmd_clear(session: "Session") -> bool:
    session.clear()
    console.print(Text("  conversation cleared.", style=TEXT_DIM))
    return True


def _cmd_compact(cfg: "FrankiConfig", session: "Session") -> bool:
    from franki.report import run_compact
    run_compact(cfg, session)
    return True


def _cmd_rewind(session: "Session") -> bool:
    removed = session.rewind()
    if removed == 0:
        console.print(Text("  nothing to rewind.", style=TEXT_DIM))
    else:
        console.print(Text(f"  rewound {removed} message(s).", style=GOLD))
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
    icon    = get_skill_icon(session.skill)
    facts   = list_facts()
    usage   = skill_usage_counts()
    scopes  = list_scopes()

    delkaai_data = cfg.providers.get("delkaai", {})
    delkaai_on   = isinstance(delkaai_data, dict) and delkaai_data.get("enabled", False)
    conn_mode    = "delkaai" if delkaai_on else "direct"
    search_avail = is_search_available(cfg)

    top_skill = max(usage, key=lambda k: usage[k]) if usage else None

    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column(style=TEXT_DIM, no_wrap=True, width=16)
    table.add_column(style=TEXT_BODY)

    # ── Model / skill / scope ─────────────────────────────────────────────────
    table.add_row("Model",      f"{cfg.get_active_provider()} / {cfg.get_active_model_name()}")
    table.add_row("Skill",      f"{icon} {session.skill}")
    table.add_row("Scope",      session.scope or "(not set)")
    table.add_row("Connection", conn_mode)
    table.add_row("",           "")

    # ── Session stats ─────────────────────────────────────────────────────────
    table.add_row("Messages",   f"user: {stats['user']}  ·  ai: {stats['assistant']}  ·  total: {stats['total']}")
    table.add_row("Tokens",     f"~{stats['approx_tokens']:,} (approx)")
    table.add_row("",           "")

    # ── Memory ────────────────────────────────────────────────────────────────
    table.add_row("Memory",     f"{len(facts)} fact(s)" + (f"  ·  preferred: {top_skill}" if top_skill else ""))
    if scopes:
        table.add_row("Scopes",  ", ".join(scopes[:3]) + ("…" if len(scopes) > 3 else ""))
    table.add_row("",           "")

    # ── System ────────────────────────────────────────────────────────────────
    table.add_row("Search",     "available" if search_avail else "not configured")
    table.add_row("Export",     cfg.export_path)
    table.add_row("Version",    f"franki v{__version__}")

    console.print()
    console.print(table)
    console.print()
    return True


# ── Output commands ───────────────────────────────────────────────────────────

def _cmd_export(cfg: "FrankiConfig", session: "Session") -> bool:
    from franki.exporter import export_session
    path = export_session(session, cfg)
    if path:
        console.print(Text(f"  session saved → {path}", style=GOLD))
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
        console.print(Text("  Copied to clipboard.", style=GOLD))
    except ImportError:
        console.print(Text("  clipboard unavailable: pyperclip not installed", style="red"))
    except Exception as exc:
        console.print(Text(f"  clipboard error: {exc}  (headless system?)", style="red"))
    return True


def _strip_markup(text: str) -> str:
    """Remove Rich markup tags like [bold], [#d4a853], [/bold] from text."""
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


# ── Navigation commands ───────────────────────────────────────────────────────

def _cmd_skill(
    cfg: "FrankiConfig",
    session: "Session",
    arg: str,
    save_cfg_fn,
    redraw_bar_fn,
) -> bool:
    if not arg:
        _show_skills(session)
        return True
    if arg not in VALID_SKILLS:
        console.print(Text(f"  unknown skill '{arg}' — valid: {', '.join(VALID_SKILLS)}", style="red"))
        return True
    session.set_skill(arg)
    cfg.active_skill = arg
    save_cfg_fn(cfg)
    redraw_bar_fn()
    from franki.memory import track_skill
    track_skill(arg)
    console.print(Text(f"  skill → {get_skill_icon(arg)} {arg}", style=GOLD))
    return True


def _cmd_model(cfg: "FrankiConfig", arg: str, save_cfg_fn, redraw_bar_fn) -> bool:
    if not arg:
        _show_models(cfg)
        return True
    cfg.active_model = arg
    save_cfg_fn(cfg)
    redraw_bar_fn()
    console.print(Text(f"  model → {arg}", style=GOLD))
    return True


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


# ── CEH / Security commands ───────────────────────────────────────────────────

def _cmd_quiz(cfg: "FrankiConfig", session: "Session") -> bool:
    from franki.quiz import run_quiz
    run_quiz(cfg, session)
    return True


def _cmd_mitre(cfg: "FrankiConfig", arg: str) -> bool:
    from franki.mitre import run_mitre
    run_mitre(cfg, arg)
    return True


def _cmd_payload(cfg: "FrankiConfig", arg: str) -> bool:
    from franki.report import run_payload
    run_payload(cfg, arg)
    return True


def _cmd_tools(cfg: "FrankiConfig", arg: str, skill: str) -> bool:
    from franki.report import run_tools
    run_tools(cfg, arg, skill)
    return True


def _cmd_explain(cfg: "FrankiConfig", arg: str) -> bool:
    from franki.report import run_explain
    run_explain(cfg, arg)
    return True


# ── Search command ────────────────────────────────────────────────────────────

def _cmd_search(cfg: "FrankiConfig", session: "Session", query: str) -> bool:
    import asyncio
    from rich.table import Table
    from rich.rule import Rule
    from rich.status import Status
    from franki.utils.search import web_search, SearchError

    if not query.strip():
        console.print(Text("  usage: /search <query>", style=TEXT_DIM))
        return True

    try:
        with Status(
            f"[{TEXT_DIM}] searching...[/]",
            spinner="dots",
            spinner_style=GOLD,
            console=console,
        ):
            result = asyncio.run(web_search(cfg, query))
    except SearchError as exc:
        console.print(Text(f"  search error: {exc}", style="red"))
        return True

    console.print()
    console.print(Text(f"  Web search  ·  {result.mode}  ·  {len(result.results)} results", style=TEXT_DIM))
    console.print(Rule(style=BORDER))

    if result.answer:
        console.print(Text(f"  {result.answer}", style=TEXT_BODY))
        console.print()

    for i, r in enumerate(result.results, 1):
        title = r.get("title", "(no title)")
        url   = r.get("url", "")
        snippet = (r.get("content") or "").strip()[:200]
        if len(r.get("content", "")) > 200:
            snippet += "…"

        console.print(Text(f"  {i}. {title}", style=GOLD))
        console.print(Text(f"     {url}", style=TEXT_DIM))
        if snippet:
            console.print(Text(f"     {snippet}", style=TEXT_BODY))
        console.print()

    # Inject results into session so the AI can reference them immediately
    session.add_user(result.as_context())
    console.print(Text("  results injected into context — ask me about them.", style=TEXT_DIM))
    console.print()
    return True


# ── Memory commands ───────────────────────────────────────────────────────────

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
    from rich.table import Table

    facts  = memory.list_facts()
    scopes = memory.list_scopes()
    usage  = memory.skill_usage_counts()
    notes  = memory.list_notes()

    if not any([facts, scopes, usage, notes]):
        console.print(Text("  no memory yet. Use /remember, /skill, /scope, or /note.", style=TEXT_DIM))
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
            t.add_row(skill, f"{count}×")
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


# ── System commands ───────────────────────────────────────────────────────────

def _cmd_connect(
    cfg: "FrankiConfig",
    arg: str,
    save_cfg_fn,
    redraw_bar_fn,
) -> bool:
    arg = arg.lower().strip()

    if not arg:
        _show_connection(cfg)
        return True

    if arg == "delkaai":
        return _connect_delkaai(cfg, save_cfg_fn, redraw_bar_fn)

    if arg == "direct":
        return _connect_direct(cfg, save_cfg_fn, redraw_bar_fn)

    console.print(Text(f"  unknown connection mode '{arg}' — try 'delkaai' or 'direct'", style="red"))
    return True


def _show_connection(cfg: "FrankiConfig") -> None:
    delkaai_data = cfg.providers.get("delkaai", {})
    enabled = isinstance(delkaai_data, dict) and delkaai_data.get("enabled", False)
    mode_label = "delkaai" if enabled else "direct"
    style = GOLD if enabled else TEXT_BODY
    console.print()
    console.print(Text(f"  connection mode: {mode_label}", style=style))
    if enabled:
        url = delkaai_data.get("url", "https://api.delkaai.com")
        console.print(Text(f"  endpoint: {url}", style=TEXT_DIM))
    console.print()


def _connect_delkaai(cfg: "FrankiConfig", save_cfg_fn, redraw_bar_fn) -> bool:
    import getpass
    key = cfg.get_provider_key("delkaai")
    if not key:
        console.print(Text("  Enter your DelkaAI API key (hidden):", style=TEXT_DIM))
        try:
            key = getpass.getpass("  key: ").strip()
        except (KeyboardInterrupt, EOFError):
            console.print(Text("  cancelled.", style=TEXT_DIM))
            return True
        if not key:
            console.print(Text("  no key entered — aborted.", style=TEXT_DIM))
            return True
        if not isinstance(cfg.providers.get("delkaai"), dict):
            cfg.providers["delkaai"] = {}
        cfg.providers["delkaai"]["api_key"] = key

    if not isinstance(cfg.providers.get("delkaai"), dict):
        cfg.providers["delkaai"] = {}
    cfg.providers["delkaai"]["enabled"] = True
    cfg.mode = "delkaai"
    cfg.active_model = "delkaai/auto"
    save_cfg_fn(cfg)
    redraw_bar_fn()
    console.print(Text("  connected to DelkaAI. Falling back to direct providers if unavailable.", style=GOLD))
    return True


def _connect_direct(cfg: "FrankiConfig", save_cfg_fn, redraw_bar_fn) -> bool:
    if isinstance(cfg.providers.get("delkaai"), dict):
        cfg.providers["delkaai"]["enabled"] = False
    cfg.mode = "direct"

    # Restore to first configured direct provider
    for name, pdata in cfg.providers.items():
        if name == "delkaai" or not isinstance(pdata, dict):
            continue
        if cfg.get_provider_key(name) and pdata.get("models"):
            cfg.active_model = f"{name}/{pdata['models'][0]}"
            break

    save_cfg_fn(cfg)
    redraw_bar_fn()
    console.print(Text("  switched to direct providers.", style=GOLD))
    return True


def _cmd_init() -> bool:
    from franki.setup_wizard import run_wizard
    run_wizard()
    return True


def _cmd_config() -> bool:
    from franki.config_cmd import run_config
    run_config([])
    return True


def _cmd_providers(cfg: "FrankiConfig") -> bool:
    active_provider = cfg.get_active_provider()
    console.print()

    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column(style=GOLD, no_wrap=True, width=14)
    table.add_column(style=TEXT_BODY, no_wrap=True, width=16)
    table.add_column(style=TEXT_DIM)

    for name, pdata in cfg.providers.items():
        if not isinstance(pdata, dict):
            continue
        key = cfg.get_provider_key(name)
        priority = pdata.get("priority", "—")
        is_active = name == active_provider and key

        if name == "delkaai":
            enabled = pdata.get("enabled", False)
            status = Text("● enabled", style=GOLD) if enabled else Text("○ disabled", style=TEXT_DIM)
            table.add_row(name, status, f"priority {priority}  ·  Phase 4")
            continue

        if key:
            status_str = "● configured"
            suffix = "  [active]" if is_active else f"  priority {priority}"
            style = GOLD if is_active else TEXT_BODY
        else:
            status_str = "○ not configured"
            suffix = f"  priority {priority}  ·  franki config set {name}.api_key <key>"
            style = TEXT_DIM

        table.add_row(name, Text(status_str, style=style), suffix)

    console.print(table)
    console.print()
    return True


def _cmd_help() -> bool:
    console.print()

    sections = [
        ("Conversation", [
            ("/clear",             "clear conversation history"),
            ("/compact",           "summarise history to save context, keep going"),
            ("/rewind",            "undo the last exchange"),
            ("/history",           "show current session conversation log"),
            ("/context",           "show full session dashboard: model, memory, search, tokens"),
        ]),
        ("Output", [
            ("/export",            "save session to Obsidian vault as markdown"),
            ("/copy",              "copy the last AI response to clipboard"),
            ("/note <text>",       "save a timestamped finding note"),
            ("/report",            "generate a pentest or SOC report from the session"),
            ("/search <query>",    "web search via Tavily — injects results into context"),
        ]),
        ("Navigation", [
            ("/skill <name>",      "switch skill: coding / pentest / soc / ceh"),
            ("/model <name>",      "switch AI model"),
            ("/scope <ip/cidr>",   "set pentest target scope"),
            ("/scope clear",       "remove active scope"),
        ]),
        ("CEH / Security", [
            ("/quiz",              "CEH v13 flashcard quiz mode"),
            ("/mitre <behaviour>", "map a behaviour to MITRE ATT&CK"),
            ("/payload <type>",    "suggest payloads for an attack type"),
            ("/tools <task>",      "suggest the right tools for a task"),
            ("/explain <tool>",    "explain a tool, its flags, and usage"),
        ]),
        ("Memory", [
            ("/remember <fact>",   "save a fact to long-term memory"),
            ("/memories",          "list all saved memory, scopes, skill usage, notes"),
            ("/forget <id|all>",   "remove a fact by id, or clear all memory"),
        ]),
        ("System", [
            ("/connect",           "show connection mode (delkaai / direct)"),
            ("/connect delkaai",   "switch to DelkaAI backend"),
            ("/connect direct",    "switch back to direct providers"),
            ("/init",              "re-run the API key setup wizard"),
            ("/config",            "open the config editor"),
            ("/providers",         "show provider status and configuration"),
            ("/help",              "show this command table"),
            ("/quit",              "exit (prompts to save session)"),
        ]),
    ]

    for section_name, rows in sections:
        table = Table(show_header=False, box=None, padding=(0, 2))
        table.add_column(style=GOLD, no_wrap=True, width=26)
        table.add_column(style=TEXT_BODY)

        console.print(Text(f"  {section_name}", style=f"bold {GOLD}"))
        for cmd, desc in rows:
            table.add_row(cmd, desc)
        console.print(table)
        console.print()

    return True


# ── Display helpers ───────────────────────────────────────────────────────────

def _show_skills(session: "Session") -> None:
    console.print()
    for skill in VALID_SKILLS:
        icon = get_skill_icon(skill)
        marker = "●" if skill == session.skill else " "
        style = GOLD if skill == session.skill else TEXT_BODY
        console.print(Text(f"  {marker} {icon} {skill}", style=style))
    console.print()


def _show_models(cfg: "FrankiConfig") -> None:
    console.print()
    for name, pdata in cfg.providers.items():
        if not isinstance(pdata, dict) or name == "delkaai":
            continue
        for m in pdata.get("models", []):
            full = f"{name}/{m}"
            marker = "●" if full == cfg.active_model else " "
            style = GOLD if full == cfg.active_model else TEXT_BODY
            console.print(Text(f"  {marker} {full}", style=style))
    console.print()
