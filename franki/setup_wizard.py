import asyncio
import getpass
import json
from pathlib import Path

import httpx
from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from rich.rule import Rule

from franki.config import load_config, save_config, CONFIG_FILE, DEFAULT_CONFIG, FrankiConfig
from franki.skills import VALID_SKILLS

console = Console()

GOLD = "#d4a853"
TEXT_DIM = "#555555"
TEXT_BODY = "#a8a8a8"
BORDER = "#2d2d2d"

PROVIDERS = [
    {
        "name": "groq",
        "label": "Groq",
        "url": "groq.com/keys",
        "env": "GROQ_API_KEY",
    },
    {
        "name": "gemini",
        "label": "Google Gemini",
        "url": "aistudio.google.com/apikey",
        "env": "GEMINI_API_KEY",
    },
    {
        "name": "openrouter",
        "label": "OpenRouter",
        "url": "openrouter.ai/keys",
        "env": "OPENROUTER_API_KEY",
    },
]


async def _test_groq_key(api_key: str) -> bool:
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={"model": "llama-3.1-8b-instant", "messages": [{"role": "user", "content": "hi"}], "max_tokens": 1},
            )
            return resp.status_code == 200
    except Exception:
        return False


async def _test_gemini_key(api_key: str) -> bool:
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}",
                json={"contents": [{"parts": [{"text": "hi"}]}], "generationConfig": {"maxOutputTokens": 1}},
            )
            return resp.status_code == 200
    except Exception:
        return False


async def _test_openrouter_key(api_key: str) -> bool:
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                "https://openrouter.ai/api/v1/auth/key",
                headers={"Authorization": f"Bearer {api_key}"},
            )
            return resp.status_code == 200
    except Exception:
        return False


_TEST_FNS = {
    "groq": _test_groq_key,
    "gemini": _test_gemini_key,
    "openrouter": _test_openrouter_key,
}


def _validate_key(provider_name: str, api_key: str) -> bool:
    test_fn = _TEST_FNS.get(provider_name)
    if not test_fn:
        return True
    return asyncio.run(test_fn(api_key))


def run_wizard() -> None:
    console.print()
    console.print(Panel(
        Text.from_markup(
            f"[bold {GOLD}]Welcome to Franki[/]\n\n"
            f"[{TEXT_BODY}]Let's get you set up. Add at least one API key.\n"
            f"You can update keys anytime with: [bold]franki config[/][/]"
        ),
        border_style=GOLD,
        padding=(1, 2),
    ))
    console.print()

    collected_keys: dict[str, str] = {}

    for provider in PROVIDERS:
        name = provider["name"]
        label = provider["label"]
        url = provider["url"]

        console.print(Text(f"  {label}", style=f"bold {GOLD}"))
        console.print(Text(f"  Free key at: {url}", style=TEXT_DIM))

        while True:
            try:
                key = getpass.getpass(f"  API key (Enter to skip): ")
            except (KeyboardInterrupt, EOFError):
                console.print()
                console.print(Text("  Setup cancelled.", style=TEXT_DIM))
                raise SystemExit(1)

            if not key.strip():
                console.print(Text(f"  ↷ skipped", style=TEXT_DIM))
                break

            console.print(Text(f"  validating...", style=TEXT_DIM), end="\r")
            valid = _validate_key(name, key.strip())
            if valid:
                console.print(Text(f"  ✓ key accepted", style=f"bold {GOLD}"))
                collected_keys[name] = key.strip()
                break
            else:
                console.print(Text(f"  ✗ key invalid or unreachable — try again or press Enter to skip", style="red"))

        console.print()

    if not collected_keys:
        console.print(Panel(
            Text.from_markup(
                f"[red]No valid API keys provided.[/]\n\n"
                f"[{TEXT_BODY}]Get a free key from any of these:\n"
                f"  • Groq: groq.com/keys\n"
                f"  • Gemini: aistudio.google.com/apikey\n"
                f"  • OpenRouter: openrouter.ai/keys\n\n"
                f"Then run [bold]franki init[/] to try again.[/]"
            ),
            border_style="red",
            padding=(1, 2),
        ))
        raise SystemExit(1)

    # Skill selection
    console.print(Text("  Default skill:", style=f"bold {GOLD}"))
    for i, skill in enumerate(VALID_SKILLS):
        console.print(Text(f"  {i + 1}. {skill}", style=TEXT_BODY))
    console.print()

    default_skill = "coding"
    try:
        choice_raw = input("  Choose [1-4] (default: 1 coding): ").strip()
        if choice_raw.isdigit():
            idx = int(choice_raw) - 1
            if 0 <= idx < len(VALID_SKILLS):
                default_skill = VALID_SKILLS[idx]
    except (KeyboardInterrupt, EOFError):
        pass

    console.print(Text(f"  skill → {default_skill}", style=GOLD))
    console.print()

    # Build and save config
    import copy
    raw = copy.deepcopy(DEFAULT_CONFIG)
    raw["active_skill"] = default_skill

    for provider in PROVIDERS:
        name = provider["name"]
        if name in collected_keys:
            raw["providers"][name]["api_key"] = collected_keys[name]

    cfg = FrankiConfig(**raw)
    save_config(cfg)

    console.print(Rule(style=BORDER))
    console.print(Text(
        f"  You are all set. Run [bold]franki[/] to start.",
        style=TEXT_BODY,
    ))
    console.print()
