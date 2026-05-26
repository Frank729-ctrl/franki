"""
Persist and restore REPL sessions to/from JSON.
Sessions are saved to ~/.config/franki/sessions/ and kept up to _MAX_SESSIONS.
"""
from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from franki.session import Session
    from franki.config import FrankiConfig

SESSIONS_DIR = Path.home() / ".config" / "franki" / "sessions"
_MAX_SESSIONS = 20
_VERSION = 1


def save_session(session: "Session", cfg: "FrankiConfig") -> Path | None:
    """Persist the current session to disk. Returns the path written or None."""
    msgs = session.history_display()
    if not msgs:
        return None

    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)

    now = datetime.now(timezone.utc)
    ts = now.strftime("%Y%m%d_%H%M%S")
    path = SESSIONS_DIR / f"{ts}_{session.skill}.json"

    preview = _make_preview(msgs)

    data = {
        "version":       _VERSION,
        "saved_at":      now.isoformat(),
        "skill":         session.skill,
        "scope":         session.scope,
        "provider":      cfg.active_provider,
        "model":         cfg.get_active_model(),
        "preview":       preview,
        "message_count": len(msgs),
        "messages":      session.get_messages(),
    }

    try:
        path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
    except OSError:
        return None

    _prune(SESSIONS_DIR, _MAX_SESSIONS)
    return path


def list_sessions() -> list[dict]:
    """Return metadata for all saved sessions, newest first."""
    if not SESSIONS_DIR.exists():
        return []

    sessions = []
    for p in sorted(SESSIONS_DIR.glob("*.json"), reverse=True):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            sessions.append({
                "path":          p,
                "saved_at":      data.get("saved_at", ""),
                "skill":         data.get("skill", "coding"),
                "scope":         data.get("scope"),
                "provider":      data.get("provider", ""),
                "model":         data.get("model", ""),
                "preview":       data.get("preview", ""),
                "message_count": data.get("message_count", 0),
            })
        except (OSError, json.JSONDecodeError):
            continue

    return sessions


def load_session_data(index_or_path: int | str) -> dict | None:
    """
    Load raw session data by 1-based index (from list_sessions()) or file path.
    Returns the parsed dict or None on error.
    """
    if isinstance(index_or_path, int):
        sessions = list_sessions()
        idx = index_or_path - 1
        if idx < 0 or idx >= len(sessions):
            return None
        p = sessions[idx]["path"]
    else:
        p = Path(index_or_path)

    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def delete_session(index: int) -> bool:
    """Delete a session by 1-based index. Returns True on success."""
    sessions = list_sessions()
    idx = index - 1
    if idx < 0 or idx >= len(sessions):
        return False
    try:
        sessions[idx]["path"].unlink()
        return True
    except OSError:
        return False


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_preview(msgs: list[dict]) -> str:
    for m in msgs:
        if m["role"] == "user":
            c = m.get("content", "")
            if isinstance(c, str):
                return c[:80].replace("\n", " ")
            if isinstance(c, list):
                for part in c:
                    if isinstance(part, dict) and part.get("type") == "text":
                        return part.get("text", "")[:80].replace("\n", " ")
    return ""


def _prune(directory: Path, keep: int) -> None:
    files = sorted(directory.glob("*.json"), reverse=True)
    for old in files[keep:]:
        try:
            old.unlink()
        except OSError:
            pass
