import sys
from rich.console import Console
from rich.table import Table
from rich.text import Text
from rich.rule import Rule

from franki.config import load_config, save_config, FrankiConfig

console = Console()

GOLD = "#d4a853"
TEXT_BODY = "#a8a8a8"
TEXT_DIM = "#555555"
BORDER = "#2d2d2d"

_MASKED_KEYS = {"api_key"}


def _mask(value: str) -> str:
    if not value:
        return "(not set)"
    if len(value) <= 8:
        return "****"
    return value[:4] + "****" + value[-4:]


def _print_config(cfg: FrankiConfig) -> None:
    table = Table(show_header=True, box=None, padding=(0, 2))
    table.add_column("Key", style=GOLD, no_wrap=True)
    table.add_column("Value", style=TEXT_BODY)

    table.add_row("mode", cfg.mode)
    table.add_row("active_skill", cfg.active_skill)
    table.add_row("active_model", cfg.active_model)
    table.add_row("stream", str(cfg.stream))
    table.add_row("theme", cfg.theme)
    table.add_row("export_path", cfg.export_path)
    table.add_row("", "")

    for pname, pdata in cfg.providers.items():
        if not isinstance(pdata, dict):
            continue
        for k, v in pdata.items():
            display = _mask(str(v)) if k in _MASKED_KEYS else str(v)
            table.add_row(f"providers.{pname}.{k}", display)

    console.print()
    console.print(table)
    console.print()


def _set_value(cfg: FrankiConfig, dotpath: str, value: str) -> bool:
    """Set a dotted config path, e.g. groq.api_key or active_model."""
    parts = dotpath.split(".", 1)

    # Top-level fields
    top_fields = {"mode", "active_skill", "active_model", "stream", "theme", "export_path"}
    if parts[0] in top_fields:
        field = parts[0]
        if field == "stream":
            setattr(cfg, field, value.lower() in ("true", "1", "yes"))
        else:
            setattr(cfg, field, value)
        return True

    # Provider fields: groq.api_key, gemini.models, etc.
    if parts[0] == "providers" and len(parts) == 2:
        sub = parts[1].split(".", 1)
        if len(sub) == 2:
            pname, key = sub
            if pname in cfg.providers and isinstance(cfg.providers[pname], dict):
                cfg.providers[pname][key] = value
                return True

    # Shorthand: groq.api_key → providers.groq.api_key
    provider_names = list(cfg.providers.keys())
    if parts[0] in provider_names and len(parts) == 2:
        pname, key = parts[0], parts[1]
        if isinstance(cfg.providers[pname], dict):
            cfg.providers[pname][key] = value
            return True

    return False


def run_config(args: list[str]) -> None:
    cfg = load_config()

    if not args or args[0] == "list":
        _print_config(cfg)
        return

    if args[0] == "get":
        if len(args) < 2:
            console.print(Text("  usage: franki config get <key>", style="red"))
            return
        dotpath = args[1]
        parts = dotpath.split(".", 1)
        pnames = list(cfg.providers.keys())

        if parts[0] in {"mode", "active_skill", "active_model", "stream", "theme", "export_path"}:
            val = str(getattr(cfg, parts[0]))
            console.print(Text(f"  {dotpath} = {val}", style=GOLD))
        elif (parts[0] in pnames or (parts[0] == "providers" and len(parts) == 2)):
            if parts[0] == "providers":
                sub = parts[1].split(".", 1)
                pname, key = sub[0], sub[1] if len(sub) > 1 else ""
            else:
                pname = parts[0]
                key = parts[1] if len(parts) > 1 else ""
            pdata = cfg.providers.get(pname, {})
            val = pdata.get(key, "(not found)") if isinstance(pdata, dict) else "(not found)"
            display = _mask(str(val)) if key in _MASKED_KEYS else str(val)
            console.print(Text(f"  {dotpath} = {display}", style=GOLD))
        else:
            console.print(Text(f"  key '{dotpath}' not found", style="red"))
        return

    if args[0] == "set":
        if len(args) < 3:
            console.print(Text("  usage: franki config set <key> <value>", style="red"))
            return
        dotpath, value = args[1], args[2]
        ok = _set_value(cfg, dotpath, value)
        if ok:
            save_config(cfg)
            console.print(Text(f"  {dotpath} = {value}", style=GOLD))
        else:
            console.print(Text(f"  unknown key '{dotpath}'", style="red"))
        return

    if args[0] == "reset":
        console.print(Text("  Reset config to defaults? All API keys will be cleared. [y/N]: ", style="yellow"), end="")
        try:
            answer = input("").strip().lower()
        except (KeyboardInterrupt, EOFError):
            answer = ""
        if answer == "y":
            from franki.config import DEFAULT_CONFIG, FrankiConfig
            import copy
            cfg = FrankiConfig(**copy.deepcopy(DEFAULT_CONFIG))
            save_config(cfg)
            console.print(Text("  config reset to defaults.", style=GOLD))
        else:
            console.print(Text("  cancelled.", style=TEXT_DIM))
        return

    console.print(Text(f"  unknown config command '{args[0]}'. Use: list, get, set, reset", style="red"))
