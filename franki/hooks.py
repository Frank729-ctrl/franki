"""Pre/post tool hooks — run shell commands around tool calls."""
from __future__ import annotations
import json
import os
import shlex
import subprocess


def _run(cmd: str, extra_env: dict[str, str] | None = None) -> str:
    env = {**os.environ, **(extra_env or {})}
    try:
        r = subprocess.run(
            shlex.split(cmd), capture_output=True, text=True, timeout=30, env=env
        )
        return (r.stdout + r.stderr).strip()
    except Exception:
        return ""


def run_pre_tool(hooks: dict[str, str], tool_name: str, args: dict) -> str | None:
    """Run pre_tool.<name> or pre_tool hook before a tool call. Returns output or None."""
    cmd = hooks.get(f"pre_tool.{tool_name}") or hooks.get("pre_tool")
    if not cmd:
        return None
    out = _run(cmd, {"FRANKI_TOOL": tool_name, "FRANKI_ARGS": json.dumps(args)})
    return out or None


def run_post_tool(hooks: dict[str, str], tool_name: str, result: str) -> str | None:
    """Run post_tool.<name> or post_tool hook after a tool call. Returns output or None."""
    cmd = hooks.get(f"post_tool.{tool_name}") or hooks.get("post_tool")
    if not cmd:
        return None
    out = _run(cmd, {"FRANKI_TOOL": tool_name, "FRANKI_RESULT": result[:500]})
    return out or None


def run_session_hook(hooks: dict[str, str], event: str) -> str | None:
    """Run a session-level hook (pre_session or post_session). Returns output or None."""
    cmd = hooks.get(event)
    if not cmd:
        return None
    out = _run(cmd)
    return out or None
