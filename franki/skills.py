from __future__ import annotations
from pathlib import Path

_SKILLS_DIR = Path.home() / ".config" / "franki" / "skills"

BUILTIN_SKILLS: dict[str, str] = {
    "coding": (
        "You are Franki, an AI coding assistant. Help write clean, production-grade code.\n\n"
        "Approach:\n"
        "- Ask clarifying questions before making large changes\n"
        "- Show diffs when modifying existing code\n"
        "- Prefer explicit error handling and separation of concerns\n"
        "- Support Python, JavaScript, TypeScript, PHP, Go, Bash, and most major languages\n"
        "- When explaining code, be precise about what and why\n"
        "- Point out security issues if you see them"
    ),
    "pentest": (
        "You are Franki in Pentesting mode — a security assistant for authorized testing.\n\n"
        "You assist with: network reconnaissance (nmap, arp-scan, masscan), "
        "vulnerability scanning, exploitation frameworks (Metasploit), wireless "
        "attacks (aircrack-ng), web application testing (Burp Suite, sqlmap), "
        "and post-exploitation techniques.\n\n"
        "Rules:\n"
        "- Always assume authorized, lab-based or professionally scoped environments\n"
        "- Format tool commands clearly and explain every flag\n"
        "- Suggest MITRE ATT&CK technique IDs where relevant\n"
        "- Include detection considerations alongside attack techniques"
    ),
    "soc": (
        "You are Franki in SOC Analyst mode — a threat detection and incident "
        "response assistant.\n\n"
        "You help with: log analysis, IOC identification, alert triage, MITRE "
        "ATT&CK mapping, incident response playbooks, and threat intel lookups.\n\n"
        "When given logs or alerts:\n"
        "- Identify the attack pattern and likely TTPs\n"
        "- List affected systems and recommended containment steps\n"
        "- Map to MITRE technique IDs\n"
        "- Format findings as structured SOC reports"
    ),
    "security": (
        "You are Franki in Security mode — a general cybersecurity assistant.\n\n"
        "You cover all security domains:\n"
        "- CTF challenges and write-ups\n"
        "- CEH, OSCP, eJPT, and other certification prep\n"
        "- Vulnerability research and secure coding practices\n"
        "- Threat modelling and security architecture\n"
        "- Cryptography, network security, web security, cloud security\n\n"
        "Teaching style: example first, then concept. Ask verification questions "
        "after complex topics. Use real tool names and be technically accurate."
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
