"""
environment.py — builds a lean self-awareness block injected into the system
prompt so the AI knows the date, cwd, active model, and what's available.

Kept deliberately short: tool schemas are already sent as the API `tools`
parameter on every call, so repeating them here wastes tokens.
"""
from __future__ import annotations
import datetime
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from franki.config import FrankiConfig


def build_environment_block(cfg: "FrankiConfig") -> str:
    """
    Generate a concise runtime-environment section for the system prompt.
    Call this AFTER tools, MCP clients, and Tavily key are all registered.

    Design goal: ≤ 60 tokens on a typical install.  Tool names/descriptions
    are intentionally omitted here because they are already included verbatim
    in the `tools` array of every API request.
    """
    from franki import __version__
    from franki.agent.tools import (
        TOOL_SCHEMAS, _TAVILY_KEY, DDGS, _MCP_CLIENTS, _CUSTOM_TOOLS,
    )
    from franki.skills import get_all_skill_names

    model   = cfg.get_active_model()
    active  = f"{cfg.active_provider}/{model}" if cfg.active_provider and model else "none"
    skills  = ", ".join(get_all_skill_names())
    cwd     = Path.cwd()
    today   = datetime.date.today().isoformat()

    # Compact single-line summary ─────────────────────────────────────────────
    lines = [
        f"[Franki v{__version__}  date:{today}  cwd:{cwd}  model:{active}  skills:{skills}]",
    ]

    # Only add extra lines when non-default things are active ─────────────────
    if cfg.auto_accept:
        lines.append("[auto-accept: ON — tool calls proceed without confirmation]")

    if _MCP_CLIENTS:
        for server_name, client in _MCP_CLIENTS.items():
            tools     = client.get_tools()
            names_str = ", ".join(t.get("name", "") for t in tools[:6])
            suffix    = f" +{len(tools)-6} more" if len(tools) > 6 else ""
            lines.append(
                f"[MCP:{server_name}  {len(tools)} tools: {names_str}{suffix}]"
            )

    if _CUSTOM_TOOLS:
        cnames = ", ".join(_CUSTOM_TOOLS.keys())
        lines.append(f"[custom tools from .franki.md: {cnames}]")

    if _TAVILY_KEY:
        lines.append("[web_search: Tavily]")
    elif DDGS is not None:
        lines.append("[web_search: DuckDuckGo]")

    return "\n".join(lines)
