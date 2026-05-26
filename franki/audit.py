"""Append-only audit log for all agent tool executions."""
from __future__ import annotations
import json
from datetime import datetime
from pathlib import Path

AUDIT_LOG = Path.home() / ".config" / "franki" / "audit.log"
_MAX_BYTES = 5 * 1024 * 1024  # 5 MB — rotate when exceeded


def log_tool(tool_name: str, args: dict, result: str) -> None:
    """Write one tool-execution record to the audit log."""
    entry = {
        "ts":     datetime.now().isoformat(timespec="seconds"),
        "tool":   tool_name,
        "args":   {k: str(v)[:200] for k, v in args.items()},
        "result": result[:300],
    }
    try:
        AUDIT_LOG.parent.mkdir(parents=True, exist_ok=True)
        _maybe_rotate()
        with AUDIT_LOG.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
    except OSError:
        pass


def _maybe_rotate() -> None:
    if AUDIT_LOG.exists() and AUDIT_LOG.stat().st_size > _MAX_BYTES:
        rotated = AUDIT_LOG.with_suffix(".log.1")
        try:
            AUDIT_LOG.rename(rotated)
        except OSError:
            AUDIT_LOG.unlink(missing_ok=True)


def tail(n: int = 50) -> list[dict]:
    """Return the last n audit entries."""
    if not AUDIT_LOG.exists():
        return []
    lines = AUDIT_LOG.read_text(encoding="utf-8", errors="replace").splitlines()
    entries = []
    for line in reversed(lines[-n * 2:]):
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            continue
        if len(entries) >= n:
            break
    entries.reverse()
    return entries
