import json
import re
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from franki.config import FrankiConfig
from franki.utils.ai import ask_ai

GOLD      = "#d4a853"
TEXT_BODY = "#a8a8a8"
TEXT_DIM  = "#555555"

_SYSTEM = """\
You are a MITRE ATT&CK framework expert. Map the described behaviour to ATT&CK.

Respond ONLY with valid JSON — no markdown, no explanation, no extra text:
{
  "tactic": "<tactic name>",
  "technique_id": "<T1234 or T1234.001>",
  "technique_name": "<technique name>",
  "description": "<one sentence describing what the attacker is doing>",
  "detection": "<how defenders can detect this>",
  "mitigation": "<recommended mitigation>"
}\
"""


def _extract_json(text: str) -> dict | None:
    text = re.sub(r'```(?:json)?\s*', '', text).strip().rstrip('`').strip()
    match = re.search(r'\{[\s\S]*\}', text)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def run_mitre(cfg: FrankiConfig, behaviour: str) -> None:
    console = Console(highlight=False)

    if not behaviour.strip():
        console.print(Text("  usage: /mitre <behaviour description>", style=TEXT_DIM))
        console.print(Text('  example: /mitre "process injected into lsass.exe"', style=TEXT_DIM))
        return

    messages = [
        {"role": "system", "content": _SYSTEM},
        {"role": "user", "content": f"Map this behaviour: {behaviour}"},
    ]

    try:
        raw = ask_ai(cfg, messages, console=console, status_text="mapping to MITRE ATT&CK...")
    except Exception as exc:
        console.print(Text(f"  error: {exc}", style="red"))
        return

    data = _extract_json(raw)
    if not data:
        console.print(Text(raw, style=TEXT_BODY))
        return

    table = Table(show_header=False, box=None, padding=(0, 2), expand=True)
    table.add_column(style=GOLD, no_wrap=True, width=18)
    table.add_column(style=TEXT_BODY, overflow="fold")

    for label, key in [
        ("Tactic",        "tactic"),
        ("Technique ID",  "technique_id"),
        ("Technique",     "technique_name"),
        ("Description",   "description"),
        ("Detection",     "detection"),
        ("Mitigation",    "mitigation"),
    ]:
        table.add_row(label, data.get(key, "—"))

    console.print()
    console.print(Panel(
        table,
        title=f"[bold {GOLD}]MITRE ATT&CK[/]",
        title_align="left",
        border_style=GOLD,
        padding=(0, 1),
    ))
    console.print()
