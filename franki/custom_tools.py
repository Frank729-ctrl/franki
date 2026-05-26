"""
Parse custom agent tool definitions from .franki.md.

Tools are declared in a ```franki-tools code fence inside .franki.md:

    ```franki-tools
    [query_db]
    description = Run a read-only SQL query against the local dev database
    command = psql -U dev mydb -c "{query}"
    param.query = The SQL query to execute

    [restart_server]
    description = Restart the development server
    command = systemctl restart myapp
    ```

Each [section] defines one tool.  `command` supports {param_name} substitution.
`param.<name> = description` declares a parameter the AI can supply.
"""
from __future__ import annotations
import re

_FENCE_RE  = re.compile(r'```franki-tools\s*\n(.*?)```', re.DOTALL | re.IGNORECASE)
_SECTION_RE = re.compile(r'^\[([^\]]+)\]$')


def parse_custom_tools(project_context: str) -> list[dict]:
    """
    Return a list of tool dicts parsed from the ```franki-tools fence.
    Each dict: {name, description, command, params: {param_name: description}}.
    Only tools with a non-empty command are returned.
    """
    if not project_context:
        return []

    m = _FENCE_RE.search(project_context)
    if not m:
        return []

    tools: list[dict] = []
    current: dict | None = None

    for raw_line in m.group(1).splitlines():
        line = raw_line.rstrip()

        # Skip blank lines and comments
        if not line or line.lstrip().startswith("#"):
            continue

        section_m = _SECTION_RE.match(line.strip())
        if section_m:
            if current:
                tools.append(current)
            current = {
                "name":        section_m.group(1).strip(),
                "description": "",
                "command":     "",
                "params":      {},
            }
            continue

        if current is None or "=" not in line:
            continue

        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip()

        if key == "description":
            current["description"] = val
        elif key == "command":
            current["command"] = val
        elif key.startswith("param."):
            param_name = key[6:].strip()
            if param_name:
                current["params"][param_name] = val

    if current:
        tools.append(current)

    return [t for t in tools if t["name"] and t["command"]]
