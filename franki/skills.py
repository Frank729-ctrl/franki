from __future__ import annotations
from pathlib import Path

_SKILLS_DIR = Path.home() / ".config" / "franki" / "skills"

# Behavioral directives only — tool names/descriptions are already in the API
# `tools` parameter on every call, so repeating them here wastes tokens.
_AGENT_RULES = (
    "Use your tools directly and proactively — never ask the user to read files "
    "or run commands themselves. Read a file before editing it. After making "
    "changes run tests or the linter automatically. Act; don't describe."
)

BUILTIN_SKILLS: dict[str, str] = {
    "coding": (
        "You are Franki, a coding assistant. "
        "Write clean, production-grade code in any language. "
        "Flag security issues when you see them. "
        + _AGENT_RULES
    ),
    "pentest": (
        "You are Franki in Pentesting mode — a security assistant for authorized testing. "
        "Help with recon, scanning, exploitation, web app testing, and wireless attacks. "
        "Explain every flag. Reference MITRE ATT&CK IDs. Assume authorized scope only. "
        + _AGENT_RULES
    ),
    "soc": (
        "You are Franki in SOC Analyst mode. "
        "Analyze logs, triage alerts, map TTPs to MITRE ATT&CK, write incident reports. "
        "Identify affected systems and containment steps. "
        + _AGENT_RULES
    ),
    "security": (
        "You are Franki in Security mode. "
        "Cover CTF, certifications (CEH/OSCP/eJPT), vuln research, secure coding, "
        "threat modeling, cryptography, web/network/cloud security. "
        "Lead with examples, then theory. "
        + _AGENT_RULES
    ),
}

# Keywords used for auto-detecting skill from message content.
# A skill needs >= 2 keyword matches to trigger a suggestion.
_AUTO_DETECT: dict[str, list[str]] = {
    "security": [
        "nmap", "exploit", "metasploit", "payload", "reverse shell", "burp",
        "vulnerability", "cve-", "sqlmap", "aircrack", "privilege escalation",
        "pentest", "penetration test", "ctf", "poc", "zero day", "0day",
        "ceh", "oscp", "ecppt", "hackthebox", "tryhackme", "kali", "parrot",
    ],
    "soc": [
        "siem", "ioc", "indicators of compromise", "log analysis", "alert triage",
        "incident response", "mitre att&ck", "threat hunt", "forensic",
        "splunk", "elastic", "qradar", "wazuh", "malware analysis",
        "intrusion detection", "ids alert", "firewall log",
    ],
    "coding": [
        "implement this function", "refactor", "debug this", "write a class",
        "fix this error", "unit test", "api endpoint", "database schema",
        "typescript", "react component", "dockerfile", "fastapi", "django route",
        "async function", "sql query", "regex",
    ],
    "pentest": [
        "scan the network", "enumerate", "smb share", "rdp", "ldap",
        "active directory", "domain controller", "pass the hash", "kerberoast",
        "lateral movement", "pivoting", "meterpreter",
    ],
}


def _load_user_skills() -> dict[str, str]:
    """Load user-defined skills from ~/.config/franki/skills/*.md"""
    if not _SKILLS_DIR.exists():
        return {}
    result: dict[str, str] = {}
    for f in sorted(_SKILLS_DIR.glob("*.md")):
        name = f.stem.lower().replace(" ", "_").replace("-", "_")
        if not name:
            continue
        content = f.read_text(encoding="utf-8").strip()
        if content:
            result[name] = content
    return result


def get_all_skills() -> dict[str, str]:
    combined = dict(BUILTIN_SKILLS)
    combined.update(_load_user_skills())
    return combined


def get_all_skill_names() -> list[str]:
    return list(get_all_skills().keys())


# Kept for backward compat — use get_all_skill_names() for dynamic list
VALID_SKILLS: list[str] = list(BUILTIN_SKILLS.keys())


def get_system_prompt(skill: str) -> str:
    return get_all_skills().get(skill, BUILTIN_SKILLS["coding"])


def detect_skill(message: str) -> str | None:
    """
    Analyze message content and return a suggested skill, or None.
    Requires >= 2 keyword matches to avoid false positives.
    """
    msg = message.lower()
    scores: dict[str, int] = {}
    for skill, keywords in _AUTO_DETECT.items():
        count = sum(1 for kw in keywords if kw in msg)
        if count:
            scores[skill] = count
    if not scores:
        return None
    best = max(scores, key=scores.__getitem__)
    return best if scores[best] >= 2 else None
