import random

TIPS: list[str] = [
    "[bold]/skill pentest[/bold] + [bold]/scope <ip>[/bold] before starting an engagement — scope is injected into every AI call.",
    "[bold]!command[/bold] runs shell commands and feeds stdout/stderr directly to the AI for analysis.",
    "[bold]/compact[/bold] summarises your conversation history — use it when the context window is filling up.",
    "[bold]/remember[/bold] saves facts across sessions. Your next franki launch already knows your environment.",
    "Prefix a message with [bold]@filename[/bold] to inject file contents — works with configs, code, and logs.",
    "CVE IDs (CVE-XXXX-XXXXX) and keywords like 'latest' or 'today' automatically trigger a web search.",
    "[bold]/mitre <behaviour>[/bold] maps any technique description to MITRE ATT&CK TTPs and returns a rich table.",
    "[bold]/report[/bold] at the end of a session auto-generates a structured pentest or SOC report.",
    "[bold]/routing[/bold] shows which provider franki will pick and why — useful for debugging slow responses.",
    "[bold]/cost[/bold] shows token usage and estimated spend for the current session.",
    "Add custom skills by dropping a [bold].md[/bold] file into [bold]~/.config/franki/skills/[/bold] — loaded automatically.",
    "[bold]franki commit[/bold] reads your git diff and writes a conventional commit message.",
    "[bold]franki review <file>[/bold] runs a thorough code review without opening the REPL.",
    "[bold]/providers[/bold] lets you add, remove, or set a default provider without restarting.",
    "Franki auto-detects your skill from message keywords — type [bold]/skill[/bold] to override manually.",
]


def get_random_tip() -> str:
    return random.choice(TIPS)
