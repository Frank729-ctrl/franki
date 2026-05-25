"""
First-run and re-run setup wizard.

Lets users add as many OpenAI-compatible providers as they want.
After the wizard completes, franki starts immediately — no need to restart.
"""
from __future__ import annotations
import asyncio
import getpass
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.rule import Rule
from rich.text import Text

from franki.config import (
    FrankiConfig,
    KNOWN_PROVIDERS,
    CONFIG_FILE,
    save_config,
    load_config,
)

console = Console()

GOLD     = "#d4a853"
TEXT_DIM = "#555555"
TEXT_BODY = "#a8a8a8"
BORDER   = "#2d2d2d"


# ── Known-provider display list ───────────────────────────────────────────────

_PRESET_DISPLAY = [
    ("groq",       "Groq          — fast, free tier, great for everyday use"),
    ("gemini",     "Google Gemini — generous free tier via Google AI Studio"),
    ("openrouter", "OpenRouter    — access many models, some free"),
    ("ollama",     "Ollama        — run models locally, no API key needed"),
    ("together",   "Together AI   — competitive models, free credits on signup"),
    ("cerebras",   "Cerebras      — extremely fast inference"),
    ("mistral",    "Mistral       — strong European models"),
    ("custom",     "Custom        — any OpenAI-compatible endpoint"),
]


# ── Key validation ────────────────────────────────────────────────────────────

async def _validate_key(api_key: str, base_url: str, model: str) -> tuple[bool, str]:
    """Make a minimal test call. Returns (ok, error_message)."""
    from franki.providers.generic import chat_once, ProviderError, ProviderRateLimitError
    try:
        await chat_once(
            api_key=api_key,
            model=model,
            messages=[{"role": "user", "content": "hi"}],
            base_url=base_url,
            provider_name="test",
        )
        return True, ""
    except (ProviderError, ProviderRateLimitError) as exc:
        return False, str(exc)
    except Exception as exc:
        return False, str(exc)


# ── Prompt helpers ────────────────────────────────────────────────────────────

def _ask(prompt: str, default: str = "") -> str:
    """Show a styled input prompt. Returns default on empty input."""
    suffix = f" [{default}]" if default else ""
    console.print(Text(f"  {prompt}{suffix}: ", style=TEXT_DIM), end="")
    try:
        val = input("").strip()
        return val if val else default
    except (KeyboardInterrupt, EOFError):
        console.print()
        raise


def _ask_key(prompt: str) -> str:
    """Hidden input for API keys."""
    console.print(Text(f"  {prompt}: ", style=TEXT_DIM), end="")
    try:
        return getpass.getpass("").strip()
    except (KeyboardInterrupt, EOFError):
        console.print()
        raise


def _yn(prompt: str, default: bool = False) -> bool:
    hint = "Y/n" if default else "y/N"
    console.print(Text(f"  {prompt} [{hint}]: ", style=TEXT_DIM), end="")
    try:
        val = input("").strip().lower()
    except (KeyboardInterrupt, EOFError):
        console.print()
        return default
    if not val:
        return default
    return val.startswith("y")


# ── Add one provider ──────────────────────────────────────────────────────────

def _add_provider(cfg: FrankiConfig, is_first: bool) -> bool:
    """
    Interactively add one provider to cfg.
    Returns True if a provider was successfully added.
    """
    console.print()
    console.print(Text("  Choose a provider:", style=f"bold {GOLD}"))
    for i, (key, label) in enumerate(_PRESET_DISPLAY, 1):
        console.print(Text(f"  {i:2}. {label}", style=TEXT_BODY))
    console.print()

    try:
        choice_raw = _ask("Enter number", "1")
    except (KeyboardInterrupt, EOFError):
        return False

    choice_idx = -1
    if choice_raw.isdigit():
        idx = int(choice_raw) - 1
        if 0 <= idx < len(_PRESET_DISPLAY):
            choice_idx = idx

    if choice_idx < 0:
        console.print(Text("  invalid choice — skipping", style="red"))
        return False

    preset_name, _ = _PRESET_DISPLAY[choice_idx]

    # ── Determine name and base_url ───────────────────────────────────────────
    if preset_name == "custom":
        try:
            name = _ask("Provider name (e.g. myprovider)").lower().replace(" ", "_")
            if not name:
                console.print(Text("  name required — skipping", style="red"))
                return False
            base_url = _ask("Base URL (e.g. https://api.example.com/v1)")
            if not base_url:
                console.print(Text("  base URL required — skipping", style="red"))
                return False
        except (KeyboardInterrupt, EOFError):
            return False
        key_required = True
        suggested_models: list[str] = []
    else:
        name = preset_name
        preset = KNOWN_PROVIDERS.get(preset_name, {})
        base_url = preset.get("base_url", "")
        suggested_models = preset.get("suggested_models", [])
        key_required = preset.get("key_required", True)
        key_url = preset.get("key_url")
        if key_url:
            console.print(Text(f"  Get your API key at: {key_url}", style=TEXT_DIM))

    # ── API key ───────────────────────────────────────────────────────────────
    api_key = ""
    if key_required:
        while True:
            try:
                api_key = _ask_key("API key (hidden, Enter to skip)")
            except (KeyboardInterrupt, EOFError):
                return False

            if not api_key:
                console.print(Text("  skipped — no key entered", style=TEXT_DIM))
                return False
            break
    else:
        console.print(Text("  no API key required", style=TEXT_DIM))
        api_key = "ollama"  # placeholder so provider_list_by_priority includes it

    # ── Model name ────────────────────────────────────────────────────────────
    if suggested_models:
        console.print(Text(f"  Suggested models: {', '.join(suggested_models)}", style=TEXT_DIM))
    try:
        default_model = suggested_models[0] if suggested_models else ""
        model = _ask("Model name", default_model)
    except (KeyboardInterrupt, EOFError):
        return False

    if not model:
        console.print(Text("  model name required — skipping", style="red"))
        return False

    # ── Validate ──────────────────────────────────────────────────────────────
    console.print(Text("  validating...", style=TEXT_DIM), end="\r")
    ok, err = asyncio.run(_validate_key(api_key, base_url, model))
    if ok:
        console.print(Text("  ok — provider works                ", style=GOLD))
    else:
        console.print(Text(f"  validation failed: {err}", style="red"))
        try:
            if not _yn("Add anyway?", default=False):
                return False
        except (KeyboardInterrupt, EOFError):
            return False

    # ── Determine priority ────────────────────────────────────────────────────
    existing_priorities = [
        p.get("priority", 99)
        for p in cfg.providers.values()
        if isinstance(p, dict)
    ]
    next_priority = max(existing_priorities, default=0) + 1

    cfg.providers[name] = {
        "api_key": api_key,
        "base_url": base_url,
        "model": model,
        "priority": next_priority,
        "key_required": key_required,
    }

    console.print(Text(f"  added: {name} / {model}", style=GOLD))
    return True


# ── Main wizard ───────────────────────────────────────────────────────────────

def run_wizard(existing_cfg: FrankiConfig | None = None) -> FrankiConfig:
    """
    Run the setup wizard. If existing_cfg is provided, adds to it.
    Returns the updated config (also saves to disk).
    """
    console.print()
    if existing_cfg is None or not existing_cfg.providers:
        console.print(Panel(
            Text.from_markup(
                f"[bold {GOLD}]Welcome to Franki[/]\n\n"
                f"[{TEXT_BODY}]Add your AI providers below. You can add as many as you want.\n"
                f"Franki will use them in order, falling back when one is rate-limited.\n\n"
                f"All providers must be OpenAI-compatible (most modern APIs are).[/]"
            ),
            border_style=GOLD,
            padding=(1, 2),
        ))
    else:
        console.print(Panel(
            Text.from_markup(
                f"[bold {GOLD}]Add providers[/]\n\n"
                f"[{TEXT_BODY}]Current providers: "
                + ", ".join(existing_cfg.providers.keys())
                + f"\n\nAdd more below or press Ctrl+C to cancel.[/]"
            ),
            border_style=GOLD,
            padding=(1, 2),
        ))

    cfg = existing_cfg or FrankiConfig()

    # ── Provider loop ─────────────────────────────────────────────────────────
    added_any = False
    while True:
        console.print()
        if added_any:
            try:
                if not _yn("Add another provider?", default=False):
                    break
            except (KeyboardInterrupt, EOFError):
                break
        else:
            console.print(Text("  Let's add your first provider.", style=TEXT_DIM))

        try:
            result = _add_provider(cfg, is_first=not added_any)
        except (KeyboardInterrupt, EOFError):
            console.print(Text("  cancelled.", style=TEXT_DIM))
            break

        if result:
            added_any = True

    if not cfg.providers:
        console.print()
        console.print(Panel(
            Text.from_markup(
                f"[red]No providers added.[/]\n\n"
                f"[{TEXT_BODY}]Franki needs at least one AI provider to work.\n"
                f"Run 'franki init' or use /providers inside the CLI to add one.[/]"
            ),
            border_style="red",
            padding=(1, 2),
        ))
        save_config(cfg)
        return cfg

    # ── Default provider ──────────────────────────────────────────────────────
    if len(cfg.providers) > 1:
        console.print()
        console.print(Text("  Default provider:", style=f"bold {GOLD}"))
        provider_names = list(cfg.providers.keys())
        for i, name in enumerate(provider_names, 1):
            console.print(Text(f"  {i}. {name}", style=TEXT_BODY))
        console.print()
        try:
            choice = _ask("Choose default [1]", "1")
            if choice.isdigit():
                idx = int(choice) - 1
                if 0 <= idx < len(provider_names):
                    cfg.active_provider = provider_names[idx]
                else:
                    cfg.active_provider = provider_names[0]
            else:
                cfg.active_provider = provider_names[0]
        except (KeyboardInterrupt, EOFError):
            cfg.active_provider = provider_names[0]
    else:
        cfg.active_provider = list(cfg.providers.keys())[0]

    console.print(Text(f"  default provider: {cfg.active_provider}", style=GOLD))

    # ── Auto-skill detection ──────────────────────────────────────────────────
    console.print()
    console.print(Text(
        "  Auto-detect skill — Franki notices when you switch between coding,",
        style=TEXT_DIM,
    ))
    console.print(Text(
        "  security, or SOC work and gently suggests a skill switch.",
        style=TEXT_DIM,
    ))
    try:
        cfg.auto_skill = _yn("Enable auto-skill detection?", default=True)
    except (KeyboardInterrupt, EOFError):
        cfg.auto_skill = True

    # ── Notes / export path ───────────────────────────────────────────────────
    console.print()
    console.print(Text(
        "  Where should Franki save session exports and notes?",
        style=TEXT_DIM,
    ))
    try:
        path = _ask("Export path", "~/Documents/franki-sessions")
        cfg.export_path = path if path else "~/Documents/franki-sessions"
    except (KeyboardInterrupt, EOFError):
        cfg.export_path = "~/Documents/franki-sessions"

    # ── Create skills dir ─────────────────────────────────────────────────────
    skills_dir = Path.home() / ".config" / "franki" / "skills"
    skills_dir.mkdir(parents=True, exist_ok=True)

    save_config(cfg)

    console.print()
    console.print(Rule(style=BORDER))
    console.print(Text(
        "  Setup complete — Franki is starting...",
        style=TEXT_BODY,
    ))
    console.print()

    return cfg
