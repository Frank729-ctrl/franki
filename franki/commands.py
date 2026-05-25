from __future__ import annotations
from typing import TYPE_CHECKING

from rich.console import Console
from rich.text import Text
from rich.table import Table
from rich.rule import Rule

from franki.skills import get_all_skill_names

if TYPE_CHECKING:
    from franki.config import FrankiConfig
    from franki.session import Session

console = Console(highlight=False)

GOLD      = "#d4a853"
TEXT_DIM  = "#555555"
TEXT_BODY = "#a8a8a8"
BORDER    = "#2d2d2d"


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
    if cmd == "/search":
        return _cmd_search(cfg, session, arg)

    # ── Navigation ────────────────────────────────────────────────────────────
    if cmd == "/skill":
        return _cmd_skill(cfg, session, arg, save_cfg_fn, redraw_bar_fn)
    if cmd == "/model":
        return _cmd_model(cfg, arg, save_cfg_fn, redraw_bar_fn)
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

    # ── Providers / MCP ───────────────────────────────────────────────────────
    if cmd == "/providers":
        return _cmd_providers(cfg, save_cfg_fn, redraw_bar_fn)
    if cmd == "/mcp":
        return _cmd_mcp(cfg, arg, save_cfg_fn)

    # ── System ────────────────────────────────────────────────────────────────
    if cmd == "/init":
        return _cmd_init(cfg, save_cfg_fn, redraw_bar_fn)
    if cmd == "/config":
        return _cmd_config_edit(cfg, save_cfg_fn, redraw_bar_fn)
    if cmd == "/help":
        return _cmd_help()
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
    table.add_row("Memory",           f"{len(facts)} fact(s)" + (f"  preferred: {top_skill}" if top_skill else ""))
    if scopes:
        table.add_row("Scopes", ", ".join(scopes[:3]) + ("..." if len(scopes) > 3 else ""))
    table.add_row("", "")
    table.add_row("Search",           "available" if search else "not configured")
    table.add_row("Export path",      cfg.export_path)
    table.add_row("Auto-accept",      "on" if cfg.auto_accept else "off")
    table.add_row("MCP servers",      str(len(cfg.mcp)) or "none")
    table.add_row("Version",          f"franki v{__version__}")

    console.print()
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
    console.print(Text(f"  search: {result.mode}  {len(result.results)} results", style=TEXT_DIM))
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
) -> bool:
    if not arg:
        # Show current provider/model combos
        console.print()
        for name, pdata in cfg.providers.items():
            if not isinstance(pdata, dict):
                continue
            model = pdata.get("model", "")
            if not model:
                continue
            is_active = name == cfg.active_provider
            marker = ">" if is_active else " "
            style = GOLD if is_active else TEXT_BODY
            console.print(Text(f"  {marker} {name} / {model}", style=style))
        console.print(Text(
            "\n  To switch: /model <provider>/<model>\n"
            "  To add a provider: /providers",
            style=TEXT_DIM,
        ))
        console.print()
        return True

    # Expect "provider/model" format
    if "/" not in arg:
        console.print(Text(
            f"  format: /model <provider>/<model>  (e.g. /model groq/llama-3.3-70b-versatile)\n"
            f"  use /model to see configured providers",
            style="red",
        ))
        return True

    parts = arg.split("/", 1)
    provider_name = parts[0].strip()
    model_name = parts[1].strip()

    if provider_name not in cfg.providers:
        console.print(Text(
            f"  provider '{provider_name}' not configured — add it with /providers",
            style="red",
        ))
        return True

    cfg.active_provider = provider_name
    if isinstance(cfg.providers[provider_name], dict):
        cfg.providers[provider_name]["model"] = model_name

    save_cfg_fn(cfg)
    redraw_bar_fn()
    console.print(Text(f"  switched to {provider_name} / {model_name}", style=GOLD))
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


# ── Security tools ────────────────────────────────────────────────────────────

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


# ── System ────────────────────────────────────────────────────────────────────

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
            ("/clear",             "clear conversation history"),
            ("/compact",           "summarise history to save context"),
            ("/rewind",            "undo the last exchange"),
            ("/history",           "show conversation log for this session"),
            ("/context",           "session dashboard: model, memory, tokens"),
        ]),
        ("Output", [
            ("/export",            "save session as markdown"),
            ("/copy",              "copy last AI response to clipboard"),
            ("/note <text>",       "save a timestamped note"),
            ("/report",            "generate a report from the session"),
            ("/search <query>",    "web search — injects results into context"),
        ]),
        ("Navigation", [
            ("/skill [name]",      "switch skill  (coding / pentest / soc / security + custom)"),
            ("/model [name]",      "switch model  (format: provider/model-name)"),
            ("/scope [ip/cidr]",   "set pentest target scope"),
            ("/scope clear",       "clear active scope"),
        ]),
        ("Security tools", [
            ("/mitre <behaviour>", "map a behaviour to MITRE ATT&CK"),
            ("/payload <type>",    "suggest payloads for an attack type"),
            ("/tools <task>",      "suggest the right tools for a task"),
            ("/explain <tool>",    "explain a tool and its usage"),
        ]),
        ("Memory", [
            ("/remember <fact>",   "save a fact to long-term memory"),
            ("/memories",          "list all saved memory, scopes, notes"),
            ("/forget <id|all>",   "remove a fact by id, or clear all memory"),
        ]),
        ("Providers / MCP", [
            ("/providers",         "add, remove, or set default provider"),
            ("/mcp",               "list MCP server connections"),
            ("/mcp add",           "add an MCP server"),
            ("/mcp remove <name>", "remove an MCP server"),
        ]),
        ("System", [
            ("/init",              "re-run the provider setup wizard"),
            ("/config",            "open the interactive config editor"),
            ("/help",              "show this command list"),
            ("exit  or  quit",     "exit (prompts to save session)"),
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
