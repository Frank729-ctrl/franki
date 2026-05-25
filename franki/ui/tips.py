import random

TIPS: list[str] = [
    "Use [bold]/skill pentest[/bold] + [bold]/scope <ip>[/bold] before starting an engagement — scope is injected into every AI call.",
    "[bold]!command[/bold] runs shell commands and feeds stdout/stderr directly to the AI for analysis.",
    "[bold]/compact[/bold] summarises your conversation history into a single message — use it when tokens run low.",
    "[bold]/remember[/bold] saves facts across sessions. Your next franki launch already knows your environment.",
    "Prefix a message with [bold]@filename[/bold] to inject file contents — works with configs, code, and logs.",
    "CVE IDs (CVE-XXXX-XXXXX) and keywords like 'latest' or 'today' automatically trigger a web search for fresh context.",
    "[bold]/mitre <behaviour>[/bold] maps any technique description to MITRE ATT\\&CK TTPs and returns a rich table.",
    "[bold]/quiz[/bold] launches CEH v13 flashcard mode — adaptive scoring, 19 domains covered.",
    "[bold]/report[/bold] at the end of an engagement auto-generates a structured pentest or SOC report and saves it.",
    "[bold]/connect delkaai[/bold] routes requests through your own DelkaAI backend — all fallback logic still applies.",
]


def get_random_tip() -> str:
    return random.choice(TIPS)
