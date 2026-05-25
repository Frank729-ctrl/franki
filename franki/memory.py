"""
memory.py — persistent long-term memory across sessions.

Stored at ~/.config/franki/memory.json as four independent buckets:
  facts        — user-defined /remember entries
  scope_history — last 5 pentest scopes used
  skill_usage  — cumulative usage count per skill
  note_history — last 10 /note entries

Public API used by the session/command layer:
  save_fact(content)          → add a user-defined fact
  remove_fact(id)             → delete by id
  get_facts()                 → list all facts
  build_memory_prompt()       → formatted system message (500-token cap)
"""
from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path

_MEMORY_FILE = Path.home() / ".config" / "franki" / "memory.json"
_MAX_SCOPES = 5
_MAX_NOTES  = 10


# ── I/O ───────────────────────────────────────────────────────────────────────

def _load() -> dict:
    if not _MEMORY_FILE.exists():
        return _empty()
    try:
        data = json.loads(_MEMORY_FILE.read_text(encoding="utf-8"))
        return {**_empty(), **data}
    except Exception:
        return _empty()


def _save(data: dict) -> None:
    _MEMORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    _MEMORY_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _empty() -> dict:
    return {
        "facts": [],
        "scope_history": [],
        "skill_usage": {},
        "note_history": [],
    }


# ── Facts ─────────────────────────────────────────────────────────────────────

def add(content: str) -> dict:
    """Save a user-defined fact. Returns the new entry."""
    data = _load()
    facts = data["facts"]
    next_id = max((f["id"] for f in facts), default=0) + 1
    entry = {
        "id": next_id,
        "content": content.strip(),
        "created": datetime.now(timezone.utc).isoformat(),
    }
    facts.append(entry)
    _save(data)
    return entry


def list_facts() -> list[dict]:
    return _load()["facts"]


def remove(item_id: int) -> bool:
    data = _load()
    facts = data["facts"]
    new_facts = [f for f in facts if f["id"] != item_id]
    if len(new_facts) == len(facts):
        return False
    data["facts"] = new_facts
    _save(data)
    return True


def clear_facts() -> int:
    data = _load()
    count = len(data["facts"])
    data["facts"] = []
    _save(data)
    return count


# ── Named aliases (preferred public API) ─────────────────────────────────────

save_fact   = add
remove_fact = remove
get_facts   = list_facts


# ── Scope history ─────────────────────────────────────────────────────────────

def track_scope(scope: str) -> None:
    """Record a pentest scope; keeps the last _MAX_SCOPES unique entries."""
    if not scope or not scope.strip():
        return
    data = _load()
    history: list[str] = data["scope_history"]
    scope = scope.strip()
    if scope in history:
        history.remove(scope)
    history.insert(0, scope)
    data["scope_history"] = history[:_MAX_SCOPES]
    _save(data)


def list_scopes() -> list[str]:
    return _load()["scope_history"]


# ── Skill usage ───────────────────────────────────────────────────────────────

def track_skill(skill: str) -> None:
    """Increment usage counter for a skill."""
    data = _load()
    usage: dict = data["skill_usage"]
    usage[skill] = usage.get(skill, 0) + 1
    _save(data)


def most_used_skill() -> str | None:
    usage = _load()["skill_usage"]
    if not usage:
        return None
    return max(usage, key=lambda k: usage[k])


def skill_usage_counts() -> dict[str, int]:
    return _load()["skill_usage"]


# ── Note history ──────────────────────────────────────────────────────────────

def track_note(text: str) -> None:
    """Record a /note entry; keeps the last _MAX_NOTES entries."""
    data = _load()
    notes: list[dict] = data["note_history"]
    notes.append({
        "text": text.strip(),
        "created": datetime.now(timezone.utc).isoformat(),
    })
    data["note_history"] = notes[-_MAX_NOTES:]
    _save(data)


def list_notes() -> list[dict]:
    return _load()["note_history"]


# ── Full clear ────────────────────────────────────────────────────────────────

def clear_all() -> None:
    _save(_empty())


# ── Memory prompt builders ────────────────────────────────────────────────────

_TOKEN_BUDGET  = 500          # hard cap for build_memory_prompt
_CHARS_PER_TOK = 4            # rough approximation


def build_memory_prompt() -> str:
    """
    Return a system-message string containing the user's saved facts,
    capped at ~500 tokens. Most-recent facts are prioritised.
    Returns an empty string when no facts exist.
    """
    facts = list_facts()
    if not facts:
        return ""

    header = (
        "The user has shared the following facts about themselves "
        "and their environment:\n"
    )
    budget = _TOKEN_BUDGET * _CHARS_PER_TOK - len(header)

    lines: list[str] = []
    for fact in reversed(facts):          # newest first
        line = f"- {fact['content']}\n"
        if len(line) > budget:
            break
        lines.append(line)
        budget -= len(line)

    if not lines:
        return ""

    lines.reverse()                        # restore chronological order
    return header + "".join(lines)


# ── System prompt context ─────────────────────────────────────────────────────

def get_context_string() -> str:
    """
    Return a compact block injected into the system prompt so the AI has
    persistent user context. Only includes non-empty buckets.
    """
    data = _load()
    parts: list[str] = []

    mem_prompt = build_memory_prompt()
    if mem_prompt:
        parts.append(mem_prompt.rstrip())

    scopes = data["scope_history"]
    if scopes:
        parts.append(f"Recent pentest scopes: {', '.join(scopes)}")

    top_skill = most_used_skill()
    if top_skill:
        parts.append(f"Preferred skill: {top_skill}")

    notes = data["note_history"][-5:]
    if notes:
        lines = "\n".join(f"- {n['text']}" for n in notes)
        parts.append(f"Recent notes:\n{lines}")

    if not parts:
        return ""
    return "Remembered context:\n" + "\n\n".join(parts)
