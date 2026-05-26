"""
environment.py — builds a dynamic self-awareness block injected into the
system prompt so the AI knows exactly what it is, what tools it has,
what providers and MCP servers are connected, and what's configured.
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
    Call this AFTER tools, MCP clients, and Tavily key are all registered,
    so the snapshot is accurate.
    """
    from franki import __version__
    from franki.agent.tools import (
        TOOL_SCHEMAS, get_custom_tool_schemas, get_mcp_tool_schemas,
        _TAVILY_KEY, DDGS, _MCP_CLIENTS, _CUSTOM_TOOLS,
    )
    from franki.skills import get_all_skill_names

    lines: list[str] = [
        f"## Franki v{__version__} — Runtime Environment",
        "",
        f"Today's date: {datetime.date.today().isoformat()}",
        f"Working directory: {Path.cwd()}",
        "",
    ]

    # ── Active model ──────────────────────────────────────────────────────────
    model = cfg.get_active_model()
    if cfg.active_provider and model:
        lines += [f"Active model: {cfg.active_provider} / {model}", ""]

    # ── All configured providers ──────────────────────────────────────────────
    usable = [
        (name, pdata)
        for name, pdata in cfg.providers.items()
        if isinstance(pdata, dict) and pdata.get("model") and pdata.get("base_url")
    ]
    if usable:
        lines.append("### Providers")
        for name, pdata in usable:
            m       = pdata.get("model", "")
            active  = " ← active" if name == cfg.active_provider else ""
            local   = "  (local)" if pdata.get("local") else ""
            lines.append(f"  {name} / {m}{active}{local}")
        lines.append("")

    # ── Built-in tools ────────────────────────────────────────────────────────
    lines.append("### Built-in tools")
    for schema in TOOL_SCHEMAS:
        fn   = schema["function"]
        desc = fn["description"].split(".")[0].split("\n")[0][:90]
        lines.append(f"  {fn['name']} — {desc}")

    # ── Web search ────────────────────────────────────────────────────────────
    if _TAVILY_KEY:
        lines.append("  web_search — search the web (Tavily — enhanced results + AI answer)")
    elif DDGS is not None:
        lines.append("  web_search — search the web (DuckDuckGo — no key required)")
    lines.append("")

    # ── MCP servers and their tools ───────────────────────────────────────────
    if _MCP_CLIENTS:
        lines.append("### MCP servers (connected)")
        for server_name, client in _MCP_CLIENTS.items():
            tools = client.get_tools()
            tool_names = ", ".join(t.get("name", "") for t in tools[:8])
            suffix = f"  +{len(tools) - 8} more" if len(tools) > 8 else ""
            lines.append(f"  [{server_name}]  {len(tools)} tools: {tool_names}{suffix}")
            for tool in tools:
                tname = f"mcp_{server_name}__{tool.get('name', '')}"
                tdesc = tool.get("description", "")[:80]
                lines.append(f"    {tname} — {tdesc}")
        lines.append("")

    # ── Custom tools from .franki.md ──────────────────────────────────────────
    if _CUSTOM_TOOLS:
        lines.append("### Custom tools (from .franki.md)")
        for name, tool in _CUSTOM_TOOLS.items():
            desc = tool.get("description", "")[:80]
            lines.append(f"  {name} — {desc}")
        lines.append("")

    # ── Skills ────────────────────────────────────────────────────────────────
    skills = get_all_skill_names()
    lines.append(f"### Available skills: {', '.join(skills)}")
    lines.append("")

    # ── Settings ─────────────────────────────────────────────────────────────
    lines.append("### Settings")
    lines.append(f"  auto_accept: {'on' if cfg.auto_accept else 'off'}")
    lines.append(f"  auto_copy:   {'on' if getattr(cfg, 'auto_copy', False) else 'off'}")
    lines.append(f"  routing:     {cfg.routing_strategy}")
    if cfg.tavily_api_key or _TAVILY_KEY:
        lines.append("  tavily:      configured")
    lines.append("")

    lines += [
        "You have complete knowledge of your own capabilities as listed above.",
        "When asked what tools, providers, models, or MCP servers you have,",
        "answer directly from this environment block rather than guessing.",
    ]

    return "\n".join(lines)
