from __future__ import annotations
import re
from dataclasses import dataclass, field
from typing import Optional

from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from prompt_toolkit import prompt as pt_prompt
from prompt_toolkit.styles import Style as PTStyle

from franki.config import FrankiConfig
from franki.utils.ai import ask_ai

GOLD      = "#d4a853"
TEXT_BODY = "#a8a8a8"
TEXT_DIM  = "#555555"

CEH_DOMAINS = [
    "Footprinting and Reconnaissance",
    "Scanning Networks",
    "Enumeration",
    "Vulnerability Analysis",
    "System Hacking",
    "Malware Threats",
    "Sniffing",
    "Social Engineering",
    "Denial-of-Service",
    "Session Hijacking",
    "Evading IDS, Firewalls, and Honeypots",
    "Hacking Web Servers",
    "Hacking Web Applications",
    "SQL Injection",
    "Hacking Wireless Networks",
    "Hacking Mobile Platforms",
    "IoT and OT Hacking",
    "Cloud Computing",
    "Cryptography",
]

_QUIZ_SYSTEM = """\
You are a CEH v13 exam question generator. Respond in EXACTLY this format — no other text before or after:

QUESTION: <the question>
A) <option A>
B) <option B>
C) <option C>
D) <option D>
ANSWER: <single uppercase letter A, B, C, or D>
EXPLANATION: <one or two sentences explaining the correct answer>\
"""

_PT_STYLE = PTStyle.from_dict({"prompt": f"{GOLD} bold", "": "#c8c0b0"})


@dataclass
class _QuizState:
    domain: str
    correct: int = 0
    total: int = 0


@dataclass
class _Question:
    text: str
    options: dict[str, str]
    answer: str
    explanation: str


def _parse(raw: str) -> Optional[_Question]:
    q = re.search(r'QUESTION:\s*(.+?)(?=\nA\))', raw, re.DOTALL)
    opts: dict[str, str] = {}
    for letter in "ABCD":
        m = re.search(rf'{letter}\)\s*(.+?)(?=\n[A-D]\)|\nANSWER:|$)', raw, re.DOTALL)
        if m:
            opts[letter] = m.group(1).strip()
    ans = re.search(r'ANSWER:\s*([A-Da-d])', raw)
    exp = re.search(r'EXPLANATION:\s*(.+?)$', raw, re.DOTALL)

    if not (q and len(opts) >= 2 and ans):
        return None
    return _Question(
        text=q.group(1).strip(),
        options=opts,
        answer=ans.group(1).upper(),
        explanation=exp.group(1).strip() if exp else "",
    )


def _render_question(console: Console, state: _QuizState, q: _Question) -> None:
    body = Text()
    body.append(f"Domain: {state.domain}\n\n", style=TEXT_DIM)
    body.append(f"{q.text}\n\n", style=TEXT_BODY)
    for letter, opt in q.options.items():
        body.append(f"  {letter})  {opt}\n", style=TEXT_BODY)
    body.append(f"\nScore: {state.correct}/{state.total}", style=GOLD)
    console.print(Panel(body, border_style=GOLD, title="[bold #d4a853]CEH Quiz[/]", title_align="left"))


def _select_domain(console: Console) -> str:
    console.print()
    console.print(Text("  Select a domain to quiz on:", style=f"bold {GOLD}"))
    console.print()
    for i, d in enumerate(CEH_DOMAINS, 1):
        console.print(Text(f"  {i:2}. {d}", style=TEXT_BODY))
    console.print(Text("   0. All domains (random)", style=TEXT_DIM))
    console.print()

    while True:
        try:
            raw = pt_prompt([("class:prompt", "  choice ›  ")], style=_PT_STYLE).strip()
        except (KeyboardInterrupt, EOFError):
            return ""
        if raw == "0":
            import random
            return random.choice(CEH_DOMAINS)
        if raw.isdigit():
            idx = int(raw) - 1
            if 0 <= idx < len(CEH_DOMAINS):
                return CEH_DOMAINS[idx]
        console.print(Text(f"  enter 0–{len(CEH_DOMAINS)}", style="yellow"))


def run_quiz(cfg: FrankiConfig, _session=None) -> None:
    console = Console(highlight=False)
    console.print()
    console.print(Panel(
        Text.from_markup(
            f"[bold {GOLD}]CEH v13 Quiz Mode[/]\n"
            f"[{TEXT_DIM}]Type A / B / C / D to answer · /quit to exit quiz[/]"
        ),
        border_style=GOLD,
        padding=(0, 2),
    ))

    domain = _select_domain(console)
    if not domain:
        console.print(Text("  quiz cancelled.", style=TEXT_DIM))
        return

    state = _QuizState(domain=domain)

    while True:
        messages = [
            {"role": "system", "content": _QUIZ_SYSTEM},
            {"role": "user", "content": f"Generate one CEH v13 question about: {domain}"},
        ]
        try:
            raw = ask_ai(cfg, messages, console=console, status_text="generating question...")
        except Exception as exc:
            console.print(Text(f"  error: {exc}", style="red"))
            break

        q = _parse(raw)
        if not q:
            # Parser failed — show raw and let user decide
            console.print(Text("  (could not parse structured question)", style=TEXT_DIM))
            console.print(Text(raw, style=TEXT_BODY))
            state.total += 1
        else:
            state.total += 1
            _render_question(console, state, q)

        try:
            ans = pt_prompt([("class:prompt", "  answer ›  ")], style=_PT_STYLE).strip()
        except (KeyboardInterrupt, EOFError):
            break

        if ans.lower() in ("/quit", "/q", "quit", "exit"):
            break

        if q:
            if ans.upper() == q.answer:
                state.correct += 1
                console.print(Text(f"  ✓ Correct!  ({state.correct}/{state.total})", style=GOLD))
            else:
                opt_text = q.options.get(q.answer, "")
                console.print(Text(f"  ✗ Incorrect.  Correct: {q.answer}) {opt_text}", style="red"))
            if q.explanation:
                console.print(Text(f"  {q.explanation}", style=TEXT_BODY))
        console.print()

        try:
            cont = pt_prompt([("class:prompt", "  next question? [Enter] or /quit ›  ")], style=_PT_STYLE).strip()
        except (KeyboardInterrupt, EOFError):
            break
        if cont.lower() in ("/quit", "/q", "quit", "exit"):
            break

    # Final score
    console.print()
    if state.total > 0:
        pct = int(state.correct / state.total * 100)
        color = GOLD if pct >= 70 else "red"
        console.print(Text(f"  Quiz complete — {state.correct}/{state.total} ({pct}%)", style=color))
    console.print(Text("  back in main REPL.", style=TEXT_DIM))
    console.print()
