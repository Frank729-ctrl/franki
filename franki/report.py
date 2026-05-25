from __future__ import annotations
from typing import TYPE_CHECKING

from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from franki.config import FrankiConfig
from franki.utils.ai import ask_ai, stream_to_terminal
from franki.utils.highlight import render_response

if TYPE_CHECKING:
    from franki.session import Session

GOLD     = "#d4a853"
TEXT_DIM = "#555555"

_PENTEST_SYS = """\
You are a professional penetration test report writer.
Generate a structured report from the conversation. Use markdown with these sections:
# Penetration Test Report
## Executive Summary
## Scope
## Methodology
## Findings
(list each finding with a Severity: Critical/High/Medium/Low/Info label)
## Recommendations
## Conclusion
Be specific. Extract real data from the conversation. Keep it professional.\
"""

_SOC_SYS = """\
You are a SOC analyst report writer.
Generate a structured incident report from the conversation. Use markdown with:
# Incident Response Report
## Incident Summary
## Timeline
## Indicators of Compromise (IOCs)
## MITRE ATT&CK TTPs
## Affected Systems
## Containment Actions Taken
## Recommendations
## Lessons Learned\
"""

_DEFAULT_SYS = """\
Generate a structured session summary report.
Use markdown headings. Include key findings, decisions, code produced, and next steps.\
"""

_PAYLOAD_SYS = """\
You are a penetration testing payload specialist assisting with authorized security testing.
For the requested attack type, provide:
1. Common payloads with explanations (use fenced code blocks per payload)
2. Context: when each variant is effective (reflected, stored, DOM for XSS; error-based, blind for SQLi; etc.)
3. Detection considerations
Begin your response with the line: "For authorized testing only."
Never omit that line.\
"""

_TOOLS_SYS = """\
You are a security tooling expert. For the described task, recommend the best tools.
For each tool: name, one-sentence description, and a practical command example.
Organize by use case. Be specific about flags.\
"""

_EXPLAIN_SYS = """\
You are a security tool documentation expert.
Explain the requested tool with:
1. What it does
2. Key flags and what they do (as a table or list)
3. A practical usage example with annotated flags
4. Common use cases in penetration testing or SOC work\
"""

_COMPACT_SYS = """\
Summarize this conversation compactly.
Preserve: all technical details, commands used, findings, decisions, and action items.
Be concise but complete. Use bullet points.\
"""


def _history_text(session: Session, max_chars: int = 500) -> str:
    return "\n\n".join(
        f"[{m['role'].upper()}]: {m['content'][:max_chars]}"
        for m in session.history_display()
    )


def run_report(cfg: FrankiConfig, session: Session) -> None:
    console = Console(highlight=False)
    if not session.history_display():
        console.print(Text("  no conversation to report on.", style=TEXT_DIM))
        return

    sys_map = {
        "pentest": (_PENTEST_SYS, "Penetration Test Report"),
        "soc":     (_SOC_SYS,     "Incident Response Report"),
    }
    sys_prompt, title = sys_map.get(session.skill, (_DEFAULT_SYS, "Session Report"))

    messages = [
        {"role": "system", "content": sys_prompt},
        {"role": "user", "content": f"Generate report from this session:\n\n{_history_text(session)}"},
    ]

    try:
        raw = ask_ai(cfg, messages, console=console, status_text="generating report...")
    except Exception as exc:
        console.print(Text(f"  error: {exc}", style="red"))
        return

    console.print()
    console.print(Panel(Text(title, style=f"bold {GOLD}"), border_style=GOLD, padding=(0, 1)))
    render_response(console, raw)


def run_payload(cfg: FrankiConfig, attack_type: str) -> None:
    console = Console(highlight=False)
    if not attack_type.strip():
        console.print(Text("  usage: /payload <type>  (e.g. XSS, SQLi, reverse shell)", style=TEXT_DIM))
        return

    messages = [
        {"role": "system", "content": _PAYLOAD_SYS},
        {"role": "user", "content": f"Payloads for: {attack_type}"},
    ]

    console.print()
    console.print(Text("  For authorized testing only.", style=f"bold {GOLD}"))
    console.print()
    try:
        stream_to_terminal(cfg, messages)
    except Exception as exc:
        console.print(Text(f"  error: {exc}", style="red"))


def run_tools(cfg: FrankiConfig, task: str, skill: str = "pentest") -> None:
    console = Console(highlight=False)
    if not task.strip():
        console.print(Text("  usage: /tools <task>  (e.g. enumerate SMB shares)", style=TEXT_DIM))
        return

    messages = [
        {"role": "system", "content": _TOOLS_SYS},
        {"role": "user", "content": f"Tools for: {task}"},
    ]

    console.print()
    try:
        stream_to_terminal(cfg, messages)
    except Exception as exc:
        console.print(Text(f"  error: {exc}", style="red"))


def run_explain(cfg: FrankiConfig, tool: str) -> None:
    console = Console(highlight=False)
    if not tool.strip():
        console.print(Text("  usage: /explain <tool>  (e.g. nmap, burpsuite, metasploit)", style=TEXT_DIM))
        return

    messages = [
        {"role": "system", "content": _EXPLAIN_SYS},
        {"role": "user", "content": f"Explain: {tool}"},
    ]

    console.print()
    try:
        stream_to_terminal(cfg, messages)
    except Exception as exc:
        console.print(Text(f"  error: {exc}", style="red"))


def run_compact(cfg: FrankiConfig, session: Session) -> None:
    console = Console(highlight=False)
    history = session.history_display()
    if not history:
        console.print(Text("  nothing to compact.", style=TEXT_DIM))
        return

    messages = [
        {"role": "system", "content": _COMPACT_SYS},
        {"role": "user", "content": f"Summarize:\n\n{_history_text(session, max_chars=800)}"},
    ]

    try:
        summary = ask_ai(cfg, messages, console=console, status_text="compacting history...")
    except Exception as exc:
        console.print(Text(f"  error: {exc}", style="red"))
        return

    original = len(history)
    session.compact(summary)
    console.print(Text(f"  History compacted. Context reduced from {original} to 1 messages.", style=GOLD))
