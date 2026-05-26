"""
Interactive config editor — used by /config inside the REPL and by `franki config` CLI.
Presents a menu-driven form instead of raw key=value arguments.
"""
from __future__ import annotations

from rich.console import Console
from rich.rule import Rule
from rich.table import Table
from rich.text import Text

from franki.config import FrankiConfig, load_config, save_config
from franki.ui.theme import GOLD, TEXT_BODY, TEXT_DIM, BORDER

console = Console()


def _mask(value: str) -> str:
    if not value:
        return "(not set)"
    if len(value) <= 8:
        return "****"
    return value[:4] + "****" + value[-4:]


def _ask(prompt: str, default: str = "") -> str:
    console.print(Text(f"  {prompt}", style=TEXT_DIM), end="")
    if default:
        console.print(Text(f" [{default}]", style=TEXT_DIM), end="")
    console.print(Text(": ", style=TEXT_DIM), end="")
    try:
        val = input("").strip()
        return val if val else default
    except (KeyboardInterrupt, EOFError):
        console.print()
        return default


def _yn(prompt: str, current: bool) -> bool:
    hint = "Y/n" if current else "y/N"
    console.print(Text(f"  {prompt} [{hint}]: ", style=TEXT_DIM), end="")
    try:
        val = input("").strip().lower()
    except (KeyboardInterrupt, EOFError):
        console.print()
        return current
    if not val:
        return current
    return val.startswith("y")


def _print_summary(cfg: FrankiConfig) -> None:
    console.print()
    console.print(Text("  Current config", style=f"bold {GOLD}"))
    console.print(Rule(style=BORDER))

    t = Table(show_header=False, box=None, padding=(0, 2))
    t.add_column(style=TEXT_DIM, no_wrap=True, width=22)
    t.add_column(style=TEXT_BODY)

    model = cfg.get_active_model()
    compact_note = ""
    if cfg.auto_compact:
        parts = [f"at {cfg.auto_compact_threshold:.0%}"]
        if cfg.auto_compact_messages > 0:
            parts.append(f"or {cfg.auto_compact_messages} msgs")
        compact_note = "on  (" + ", ".join(parts) + ")"
    else:
        compact_note = "off"

    t.add_row("active provider",  cfg.active_provider or "(none)")
    t.add_row("active model",     model or "(none)")
    t.add_row("active skill",     cfg.active_skill)
    t.add_row("auto-skill",       "on" if cfg.auto_skill else "off")
    t.add_row("auto-accept",      "on" if cfg.auto_accept else "off")
    t.add_row("auto-compact",     compact_note)
    t.add_row("routing strategy", cfg.routing_strategy)
    t.add_row("local-first",      "on" if cfg.local_first else "off")
    t.add_row("export path",      cfg.export_path)
    t.add_row("web search key",   _mask(cfg.tavily_api_key))
    t.add_row("providers",        ", ".join(cfg.providers.keys()) or "(none)")
    t.add_row("MCP servers",      ", ".join(cfg.mcp.keys()) or "(none)")

    console.print(t)
    console.print()


def run_interactive_config(
    cfg: FrankiConfig,
    save_cfg_fn=None,
    redraw_bar_fn=None,
) -> None:
    """
    Full interactive config editor. Accepts a live cfg object so changes
    take effect immediately inside the REPL.
    """
    _save = save_cfg_fn or (lambda c: save_config(c))
    _redraw = redraw_bar_fn or (lambda: None)

    while True:
        _print_summary(cfg)

        console.print(Text(
            "  1  Active provider\n"
            "  2  Active model\n"
            "  3  Active skill\n"
            "  4  Auto-detect skill\n"
            "  5  Auto-accept shell commands\n"
            "  6  Auto-compact (summarise when context fills)\n"
            "  7  Routing strategy  (capability / speed / cost / priority)\n"
            "  8  Local-first mode  (prefer Ollama / local providers)\n"
            "  9  Export / notes path\n"
            "  10 Web search key (Tavily)\n"
            "  11 Edit provider key\n"
            "  0  Done",
            style=TEXT_BODY,
        ))
        console.print()

        console.print(Text("  choice: ", style=TEXT_DIM), end="")
        try:
            choice = input("").strip()
        except (KeyboardInterrupt, EOFError):
            console.print()
            break

        if choice in ("0", ""):
            break

        elif choice == "1":
            names = list(cfg.providers.keys())
            if not names:
                console.print(Text("  no providers configured — add one with /providers", style="yellow"))
                continue
            for i, n in enumerate(names, 1):
                marker = ">" if n == cfg.active_provider else " "
                console.print(Text(f"  {i}. {marker} {n}", style=TEXT_BODY))
            sel = _ask("Set default provider", cfg.active_provider)
            if sel.isdigit():
                idx = int(sel) - 1
                sel = names[idx] if 0 <= idx < len(names) else sel
            if sel in cfg.providers:
                cfg.active_provider = sel
                _save(cfg)
                _redraw()
                console.print(Text(f"  active provider → {sel}", style=GOLD))
            else:
                console.print(Text(f"  provider '{sel}' not found", style="red"))

        elif choice == "2":
            pdata = cfg.providers.get(cfg.active_provider, {})
            current_model = pdata.get("model", "") if isinstance(pdata, dict) else ""
            new_model = _ask(
                f"Model for {cfg.active_provider or 'provider'}",
                current_model,
            )
            if new_model and isinstance(cfg.providers.get(cfg.active_provider), dict):
                cfg.providers[cfg.active_provider]["model"] = new_model
                _save(cfg)
                _redraw()
                console.print(Text(f"  model → {new_model}", style=GOLD))

        elif choice == "3":
            from franki.skills import get_all_skill_names
            skills = get_all_skill_names()
            for i, s in enumerate(skills, 1):
                marker = ">" if s == cfg.active_skill else " "
                console.print(Text(f"  {i}. {marker} {s}", style=TEXT_BODY))
            sel = _ask("Active skill", cfg.active_skill)
            if sel.isdigit():
                idx = int(sel) - 1
                sel = skills[idx] if 0 <= idx < len(skills) else sel
            if sel in skills:
                cfg.active_skill = sel
                _save(cfg)
                _redraw()
                console.print(Text(f"  skill → {sel}", style=GOLD))
            else:
                console.print(Text(f"  skill '{sel}' not found", style="red"))

        elif choice == "4":
            cfg.auto_skill = _yn("Enable auto-skill detection", cfg.auto_skill)
            _save(cfg)
            console.print(Text(f"  auto-skill → {'on' if cfg.auto_skill else 'off'}", style=GOLD))

        elif choice == "5":
            cfg.auto_accept = _yn(
                "Auto-accept shell commands (no confirmation prompt for !cmd)",
                cfg.auto_accept,
            )
            _save(cfg)
            console.print(Text(f"  auto-accept → {'on' if cfg.auto_accept else 'off'}", style=GOLD))

        elif choice == "6":
            cfg.auto_compact = _yn(
                "Enable auto-compact (summarise history when context window fills)",
                cfg.auto_compact,
            )
            _save(cfg)
            if cfg.auto_compact:
                raw_pct = _ask(
                    f"Compact threshold % (e.g. 85)",
                    str(int(cfg.auto_compact_threshold * 100)),
                )
                try:
                    val = float(raw_pct.strip().rstrip("%"))
                    val = max(50.0, min(99.0, val))
                    cfg.auto_compact_threshold = val / 100.0
                    _save(cfg)
                except ValueError:
                    pass
            console.print(Text(
                f"  auto-compact → {'on at ' + str(int(cfg.auto_compact_threshold * 100)) + '%' if cfg.auto_compact else 'off'}",
                style=GOLD,
            ))

        elif choice == "7":
            strategies = ["capability", "speed", "cost", "priority"]
            for i, s in enumerate(strategies, 1):
                marker = ">" if s == cfg.routing_strategy else " "
                console.print(Text(f"  {i}. {marker} {s}", style=TEXT_BODY))
            sel = _ask("Routing strategy", cfg.routing_strategy)
            if sel.isdigit():
                idx = int(sel) - 1
                sel = strategies[idx] if 0 <= idx < len(strategies) else sel
            if sel in strategies:
                cfg.routing_strategy = sel
                _save(cfg)
                console.print(Text(f"  routing strategy → {sel}", style=GOLD))
            else:
                console.print(Text(f"  unknown strategy '{sel}'", style="red"))

        elif choice == "8":
            cfg.local_first = _yn(
                "Local-first mode (boost Ollama/local providers in routing)",
                cfg.local_first,
            )
            _save(cfg)
            console.print(Text(f"  local-first → {'on' if cfg.local_first else 'off'}", style=GOLD))

        elif choice == "9":
            new_path = _ask("Export / notes path", cfg.export_path)
            if new_path:
                cfg.export_path = new_path
                _save(cfg)
                console.print(Text(f"  export path → {new_path}", style=GOLD))

        elif choice == "10":
            import getpass
            console.print(Text("  Tavily API key (hidden, Enter to clear): ", style=TEXT_DIM), end="")
            try:
                key = getpass.getpass("").strip()
            except (KeyboardInterrupt, EOFError):
                console.print()
                continue
            cfg.tavily_api_key = key
            _save(cfg)
            console.print(Text("  web search key updated.", style=GOLD))

        elif choice == "11":
            import getpass
            names = list(cfg.providers.keys())
            if not names:
                console.print(Text("  no providers configured.", style="yellow"))
                continue
            for i, n in enumerate(names, 1):
                console.print(Text(f"  {i}. {n}", style=TEXT_BODY))
            sel = _ask("Provider to update key for", "")
            if sel.isdigit():
                idx = int(sel) - 1
                sel = names[idx] if 0 <= idx < len(names) else sel
            if sel not in cfg.providers:
                console.print(Text(f"  provider '{sel}' not found", style="red"))
                continue
            console.print(Text(f"  New API key for {sel} (hidden): ", style=TEXT_DIM), end="")
            try:
                key = getpass.getpass("").strip()
            except (KeyboardInterrupt, EOFError):
                console.print()
                continue
            if key and isinstance(cfg.providers[sel], dict):
                cfg.providers[sel]["api_key"] = key
                _save(cfg)
                console.print(Text(f"  key updated for {sel}.", style=GOLD))
        else:
            console.print(Text("  enter a number from the list above", style=TEXT_DIM))


def run_config_cli(args: list[str]) -> None:
    """Fallback for `franki config` from the command line (non-REPL)."""
    cfg = load_config()

    if not args:
        run_interactive_config(cfg)
        return

    # Legacy positional commands for scripting / CI
    if args[0] == "list":
        _print_summary(cfg)
        return

    if args[0] == "set" and len(args) >= 3:
        key, value = args[1], args[2]
        if key == "active_provider":
            cfg.active_provider = value
        elif key == "active_skill":
            cfg.active_skill = value
        elif key == "export_path":
            cfg.export_path = value
        elif key == "auto_skill":
            cfg.auto_skill = value.lower() in ("true", "1", "yes")
        elif key == "auto_accept":
            cfg.auto_accept = value.lower() in ("true", "1", "yes")
        elif key == "auto_compact":
            cfg.auto_compact = value.lower() in ("true", "1", "yes")
        elif key == "auto_compact_threshold":
            try:
                v = float(value.rstrip("%"))
                cfg.auto_compact_threshold = v / 100.0 if v > 1 else v
            except ValueError:
                print(f"  invalid threshold '{value}'")
                return
        elif key == "auto_compact_messages":
            try:
                cfg.auto_compact_messages = int(value)
            except ValueError:
                print(f"  invalid message count '{value}'")
                return
        elif key == "local_first":
            cfg.local_first = value.lower() in ("true", "1", "yes")
        elif key == "routing_strategy":
            if value in ("capability", "speed", "cost", "priority"):
                cfg.routing_strategy = value
            else:
                print(f"  unknown strategy '{value}' — valid: capability, speed, cost, priority")
                return
        elif "." in key:
            # e.g. groq.api_key  or  groq.model
            parts = key.split(".", 1)
            provider_name, field = parts
            if provider_name in cfg.providers and isinstance(cfg.providers[provider_name], dict):
                cfg.providers[provider_name][field] = value
            else:
                print(f"  provider '{provider_name}' not found")
                return
        else:
            print(f"  unknown key '{key}'")
            return
        save_config(cfg)
        print(f"  {key} = {value}")
        return

    if args[0] == "get" and len(args) >= 2:
        key = args[1]
        simple = {
            "active_provider", "active_skill", "export_path",
            "auto_skill", "auto_accept",
            "auto_compact", "auto_compact_threshold", "auto_compact_messages",
            "local_first", "routing_strategy",
        }
        if key in simple:
            print(f"  {key} = {getattr(cfg, key)}")
        elif "." in key:
            parts = key.split(".", 1)
            pname, field = parts
            pdata = cfg.providers.get(pname, {})
            val = pdata.get(field, "(not found)") if isinstance(pdata, dict) else "(not found)"
            display = _mask(str(val)) if field == "api_key" else str(val)
            print(f"  {key} = {display}")
        return

    print(f"  usage: franki config  (interactive)  or  franki config set <key> <value>")
