"""Tool definitions and execution for the agentic loop."""
from __future__ import annotations
import re
import subprocess
import threading
import uuid
from pathlib import Path
from typing import Any

try:
    from ddgs import DDGS
except ImportError:
    DDGS = None  # type: ignore[assignment,misc]

# ── Tool schemas (OpenAI function-calling format) ─────────────────────────────

TOOL_SCHEMAS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": (
                "Read the contents of a file. Always call this before editing "
                "to see the current state."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File path (relative to cwd or absolute)"},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Create a new file or completely overwrite an existing one.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path":    {"type": "string", "description": "File path to write"},
                    "content": {"type": "string", "description": "Full content to write"},
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "edit_file",
            "description": (
                "Replace an exact string in a file with new content. "
                "Use read_file first. old_str must match exactly — "
                "if it appears more than once, make it more specific."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path":    {"type": "string"},
                    "old_str": {"type": "string", "description": "Exact string to replace"},
                    "new_str": {"type": "string", "description": "Replacement string"},
                },
                "required": ["path", "old_str", "new_str"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_command",
            "description": "Run a shell command and return stdout + stderr. Use for tests, linting, builds.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "Shell command to execute"},
                },
                "required": ["command"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_directory",
            "description": "List the files and subdirectories at a path.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Directory path (default: .)", "default": "."},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_files",
            "description": "Find files by name pattern (glob). Returns matching paths.",
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern":   {"type": "string", "description": "Glob pattern e.g. '*.py' or 'test_*.py'"},
                    "directory": {"type": "string", "description": "Root directory (default: .)", "default": "."},
                },
                "required": ["pattern"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "grep_files",
            "description": "Search for a string or regex inside files. Returns file:line matches.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query":        {"type": "string", "description": "String or regex to search for"},
                    "directory":    {"type": "string", "description": "Directory to search (default: .)", "default": "."},
                    "file_pattern": {"type": "string", "description": "Filter to file extension e.g. '*.py' (default: all)", "default": "*"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_background",
            "description": (
                "Start a long-running shell command in the background (e.g. a dev server, "
                "watcher, or test runner). Returns immediately with a process ID. "
                "Use check_background to read its output."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "Shell command to run in background"},
                },
                "required": ["command"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "check_background",
            "description": "Read new output from a background process started with run_background.",
            "parameters": {
                "type": "object",
                "properties": {
                    "process_id": {"type": "string", "description": "Process ID returned by run_background"},
                },
                "required": ["process_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "stop_background",
            "description": "Terminate a background process.",
            "parameters": {
                "type": "object",
                "properties": {
                    "process_id": {"type": "string", "description": "Process ID to stop"},
                },
                "required": ["process_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_backgrounds",
            "description": "List all background processes and their status.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "apply_patch",
            "description": (
                "Apply a unified diff (patch) to a file. "
                "The diff must be in standard unified format (diff -u). "
                "Useful for applying AI-generated patches directly."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path":  {"type": "string", "description": "File to patch"},
                    "patch": {"type": "string", "description": "Unified diff content"},
                },
                "required": ["path", "patch"],
            },
        },
    },
]

# Which tools need user confirmation (they modify state)
WRITE_TOOLS   = {"write_file", "edit_file", "apply_patch"}
EXEC_TOOLS    = {"run_command", "run_background"}
NEEDS_CONFIRM = WRITE_TOOLS | EXEC_TOOLS

# Read-only tools that are safe to run in parallel
READ_ONLY_TOOLS = {"read_file", "list_directory", "search_files", "grep_files", "web_search"}

# ── Web search tool ───────────────────────────────────────────────────────────

_TAVILY_KEY: str = ""

_WEB_SEARCH_SCHEMA: dict = {
    "type": "function",
    "function": {
        "name": "web_search",
        "description": (
            "Search the web for current information — documentation, error messages, "
            "API references, changelogs, or anything that may have changed since training. "
            "Returns titles, URLs, and text snippets."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query",
                },
                "max_results": {
                    "type": "integer",
                    "description": "Number of results to return (1–10, default 5)",
                    "default": 5,
                },
            },
            "required": ["query"],
        },
    },
}


def set_tavily_key(key: str) -> None:
    """Set the Tavily API key used by the web_search agent tool."""
    global _TAVILY_KEY
    _TAVILY_KEY = key.strip()


# ── MCP tool registry ────────────────────────────────────────────────────────

_MCP_CLIENTS: dict[str, Any] = {}   # server_name → MCPClient


def register_mcp_clients(clients: dict) -> None:
    """Register active MCPClient instances keyed by server name."""
    _MCP_CLIENTS.clear()
    _MCP_CLIENTS.update(clients)


def get_mcp_tool_schemas() -> list[dict]:
    """Convert registered MCP tool definitions to OpenAI function-calling format."""
    schemas: list[dict] = []
    for server_name, client in _MCP_CLIENTS.items():
        for tool in client.get_tools():
            name = f"mcp_{server_name}__{tool.get('name', '')}"
            schemas.append({
                "type": "function",
                "function": {
                    "name":        name,
                    "description": f"[{server_name}] {tool.get('description', '')}",
                    "parameters":  tool.get("inputSchema") or {"type": "object", "properties": {}, "required": []},
                },
            })
    return schemas


# ── Custom tool registry ──────────────────────────────────────────────────────

_CUSTOM_TOOLS: dict[str, dict] = {}


def register_custom_tools(tools: list[dict]) -> None:
    """Populate the registry from .franki.md parsed definitions."""
    _CUSTOM_TOOLS.clear()
    for t in tools:
        _CUSTOM_TOOLS[t["name"]] = t


def get_custom_tool_schemas() -> list[dict]:
    """Return OpenAI function-calling schemas for all registered custom tools."""
    schemas = []
    for name, tool in _CUSTOM_TOOLS.items():
        params = tool.get("params", {})
        props  = {p: {"type": "string", "description": d} for p, d in params.items()}
        schemas.append({
            "type": "function",
            "function": {
                "name":        name,
                "description": tool.get("description", f"Custom tool: {name}"),
                "parameters":  {
                    "type":       "object",
                    "properties": props,
                    "required":   list(params.keys()),
                },
            },
        })
    return schemas


def get_all_tool_schemas() -> list[dict]:
    """Return built-in TOOL_SCHEMAS, web_search, MCP, plus custom tool schemas."""
    return TOOL_SCHEMAS + [_WEB_SEARCH_SCHEMA] + get_mcp_tool_schemas() + get_custom_tool_schemas()

# Directories skipped by list/search/grep
_SKIP_DIRS = {".git", "__pycache__", "node_modules", ".venv", "venv", ".tox", "dist", "build"}

# ── Background process registry ───────────────────────────────────────────────

_BACKGROUNDS: dict[str, dict] = {}


def list_background_ids() -> list[str]:
    return list(_BACKGROUNDS.keys())


# ── Execution ─────────────────────────────────────────────────────────────────

def execute_tool(name: str, args: dict[str, Any]) -> str:
    try:
        if name == "read_file":
            path = args.get("path") or args.get("file")
            if not path:
                return "error: missing required argument 'path'"
            return _read_file(path)
        if name == "write_file":
            path = args.get("path") or args.get("file")
            content = args.get("content") or args.get("text", "")
            if not path:
                return "error: missing required argument 'path'"
            return _write_file(path, content)
        if name == "edit_file":
            path = args.get("path") or args.get("file")
            if not path:
                return "error: missing required argument 'path'"
            return _edit_file(path, args.get("old_str", ""), args.get("new_str", ""))
        if name == "run_command":
            cmd = args.get("command") or args.get("cmd") or args.get("shell")
            if not cmd:
                return "error: missing required argument 'command'"
            return _run_command(cmd)
        if name == "list_directory":
            return _list_directory(args.get("path", "."))
        if name == "search_files":
            return _search_files(args["pattern"], args.get("directory", "."))
        if name == "grep_files":
            return _grep_files(
                args["query"],
                args.get("directory", "."),
                args.get("file_pattern", "*"),
            )
        if name == "run_background":
            cmd = args.get("command") or args.get("cmd") or args.get("shell")
            if not cmd:
                return "error: missing required argument 'command'"
            return _run_background(cmd)
        if name == "check_background":
            return _check_background(args["process_id"])
        if name == "stop_background":
            return _stop_background(args["process_id"])
        if name == "list_backgrounds":
            return _list_backgrounds()
        if name == "web_search":
            return _web_search(args["query"], int(args.get("max_results", 5)))
        if name == "apply_patch":
            return _apply_patch(args["path"], args["patch"])
        if name.startswith("mcp_") and "__" in name:
            return _execute_mcp_tool(name, args)
        if name in _CUSTOM_TOOLS:
            return _execute_custom_tool(name, args)
        return f"unknown tool: {name}"
    except Exception as exc:
        return f"error: {exc}"


# ── Individual tool implementations ──────────────────────────────────────────

def _read_file(path: str) -> str:
    p = Path(path)
    if not p.exists():
        return f"file not found: {path}"
    if not p.is_file():
        return f"not a file: {path}"
    content = p.read_text(encoding="utf-8", errors="replace")
    lines = content.splitlines()
    if len(lines) > 60:
        numbered = "\n".join(f"{i+1:4}: {line}" for i, line in enumerate(lines))
        return f"```\n{numbered}\n```"
    return content


def _write_file(path: str, content: str) -> str:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return f"wrote {content.count(chr(10)) + 1} lines → {path}"


def _edit_file(path: str, old_str: str, new_str: str) -> str:
    p = Path(path)
    if not p.exists():
        return f"file not found: {path}"
    current = p.read_text(encoding="utf-8")
    if old_str not in current:
        return f"string not found in {path} — use read_file to check current content"
    count = current.count(old_str)
    if count > 1:
        return f"string appears {count} times in {path} — make old_str more specific"
    p.write_text(current.replace(old_str, new_str, 1), encoding="utf-8")
    return f"edited {path}"


def _apply_patch(path: str, patch: str) -> str:
    """Apply a unified diff to a file using Python's difflib."""
    import difflib
    p = Path(path)
    if not p.exists():
        return f"file not found: {path}"
    original = p.read_text(encoding="utf-8").splitlines(keepends=True)
    try:
        patched = list(difflib.restore(
            [l if l.endswith("\n") else l + "\n" for l in patch.splitlines()],
            which=2,
        ))
    except Exception:
        patched = None

    # difflib.restore is limited — try subprocess `patch` as a reliable fallback
    if not patched:
        import tempfile, os
        with tempfile.NamedTemporaryFile(mode="w", suffix=".patch", delete=False, encoding="utf-8") as f:
            f.write(patch)
            tmp = f.name
        try:
            result = subprocess.run(
                ["patch", "--quiet", path, tmp],
                capture_output=True, text=True, timeout=30,
            )
            os.unlink(tmp)
            if result.returncode != 0:
                return f"patch failed: {result.stderr.strip() or result.stdout.strip()}"
            return f"patched {path}"
        except FileNotFoundError:
            os.unlink(tmp)
            return "patch command not found — install GNU patch or use edit_file"
        except Exception as exc:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            return f"patch error: {exc}"

    p.write_text("".join(patched), encoding="utf-8")
    return f"patched {path}"


def _run_command(command: str) -> str:
    try:
        result = subprocess.run(
            command, shell=True, capture_output=True, text=True, timeout=60
        )
    except subprocess.TimeoutExpired:
        return "command timed out after 60s"
    out = result.stdout
    if result.stderr:
        out += f"\n[stderr]\n{result.stderr}"
    if result.returncode != 0:
        out += f"\n[exit {result.returncode}]"
    return out.strip() or "(no output)"


def _list_directory(path: str) -> str:
    p = Path(path)
    if not p.exists():
        return f"path not found: {path}"
    if not p.is_dir():
        return f"not a directory: {path}"
    items = sorted(p.iterdir(), key=lambda x: (x.is_file(), x.name.lower()))
    lines = [
        f"{item.name}{'/' if item.is_dir() else ''}"
        for item in items
        if item.name not in _SKIP_DIRS and not item.name.startswith(".")
    ]
    return "\n".join(lines) if lines else "(empty)"


def _search_files(pattern: str, directory: str) -> str:
    p = Path(directory).resolve()
    root_depth = len(p.parts)
    matches = [
        str(m) for m in sorted(p.rglob(pattern))
        if m.is_file() and not any(
            part in _SKIP_DIRS or part.startswith(".")
            for part in m.parts[root_depth:]
        )
    ]
    if not matches:
        return f"no files matching '{pattern}' in {directory}"
    return "\n".join(matches[:100])


def _grep_files(query: str, directory: str, file_pattern: str) -> str:
    p = Path(directory).resolve()
    root_depth = len(p.parts)
    glob = f"**/{file_pattern}" if file_pattern != "*" else "**/*"
    results: list[str] = []
    try:
        for f in sorted(p.glob(glob)):
            if not f.is_file():
                continue
            if any(part in _SKIP_DIRS or part.startswith(".") for part in f.parts[root_depth:]):
                continue
            try:
                for i, line in enumerate(
                    f.read_text(encoding="utf-8", errors="replace").splitlines(), 1
                ):
                    if re.search(query, line, re.IGNORECASE):
                        results.append(f"{f}:{i}: {line.strip()}")
                        if len(results) >= 60:
                            break
            except OSError:
                continue
            if len(results) >= 60:
                break
    except Exception as exc:
        return f"error: {exc}"
    return "\n".join(results) if results else f"no matches for '{query}'"


# ── Background process tools ──────────────────────────────────────────────────

def _run_background(command: str) -> str:
    proc_id = uuid.uuid4().hex[:8]
    buf: list[str] = []
    lock = threading.Lock()

    proc = subprocess.Popen(
        command, shell=True,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, bufsize=1,
    )

    def _reader():
        assert proc.stdout is not None
        for line in proc.stdout:
            with lock:
                buf.append(line)

    thread = threading.Thread(target=_reader, daemon=True)
    thread.start()
    _BACKGROUNDS[proc_id] = {
        "proc": proc, "buf": buf, "lock": lock,
        "read_pos": 0, "cmd": command,
    }
    return f"started [{proc_id}]  {command}\nuse check_background('{proc_id}') to read output"


def _check_background(process_id: str) -> str:
    if process_id not in _BACKGROUNDS:
        return f"no background process '{process_id}' — use list_backgrounds to see running processes"
    entry = _BACKGROUNDS[process_id]
    with entry["lock"]:
        new_lines = entry["buf"][entry["read_pos"]:]
        entry["read_pos"] = len(entry["buf"])
    rc = entry["proc"].poll()
    status = "[running]" if rc is None else f"[exited {rc}]"
    output = "".join(new_lines).strip()
    return f"{status}\n{output}" if output else f"{status}\n(no new output)"


def _stop_background(process_id: str) -> str:
    if process_id not in _BACKGROUNDS:
        return f"no background process '{process_id}'"
    entry = _BACKGROUNDS.pop(process_id)
    entry["proc"].terminate()
    try:
        entry["proc"].wait(timeout=5)
    except subprocess.TimeoutExpired:
        entry["proc"].kill()
    return f"stopped [{process_id}]  {entry['cmd']}"


def _list_backgrounds() -> str:
    if not _BACKGROUNDS:
        return "no background processes running"
    lines = []
    for pid, entry in _BACKGROUNDS.items():
        rc = entry["proc"].poll()
        status = "running" if rc is None else f"exited {rc}"
        lines.append(f"[{pid}]  {status}  {entry['cmd']}")
    return "\n".join(lines)


# ── Web search execution ─────────────────────────────────────────────────────

def _web_search(query: str, max_results: int = 5) -> str:
    max_results = max(1, min(int(max_results), 10))
    if _TAVILY_KEY:
        return _tavily_search(query, max_results)
    return _ddg_search(query, max_results)


def _format_results(query: str, results: list[dict], answer: str = "") -> str:
    if not results:
        return f'no web results for: "{query}"'
    lines = [f'[web search: "{query}"]', ""]
    if answer:
        lines += [f"Summary: {answer}", ""]
    for i, r in enumerate(results, 1):
        title   = r.get("title", "").strip()
        url     = r.get("url", "")
        content = r.get("content", "").strip()
        snippet = content[:350] + ("…" if len(content) > 350 else "")
        lines.append(f"{i}. {title}")
        lines.append(f"   {url}")
        if snippet:
            lines.append(f"   {snippet}")
        lines.append("")
    return "\n".join(lines).rstrip()


def _tavily_search(query: str, max_results: int) -> str:
    import httpx
    try:
        resp = httpx.post(
            "https://api.tavily.com/search",
            json={
                "api_key": _TAVILY_KEY,
                "query": query,
                "search_depth": "basic",
                "max_results": max_results,
                "include_answer": True,
            },
            timeout=20.0,
        )
        if resp.status_code == 401:
            return "web_search error: invalid Tavily API key"
        if resp.status_code == 429:
            return "web_search error: Tavily rate limit exceeded"
        if resp.status_code >= 400:
            return f"web_search error: HTTP {resp.status_code}"
        data = resp.json()
    except Exception as exc:
        return f"web_search error: {exc}"
    results = [
        {"title": r.get("title", ""), "url": r.get("url", ""), "content": r.get("content", "")}
        for r in data.get("results", [])
    ]
    return _format_results(query, results, answer=data.get("answer", ""))


def _ddg_search(query: str, max_results: int) -> str:
    if DDGS is None:
        return (
            "web_search unavailable — install 'ddgs' (pip install ddgs) "
            "or add a Tavily API key via /config"
        )
    try:
        with DDGS() as ddgs:
            raw = list(ddgs.text(query, max_results=max_results))
    except Exception as exc:
        return f"web_search error: {exc}"
    results = [
        {"title": r.get("title", ""), "url": r.get("href", ""), "content": r.get("body", "")}
        for r in raw
    ]
    return _format_results(query, results)


# ── MCP tool execution ───────────────────────────────────────────────────────

def _execute_mcp_tool(name: str, args: dict[str, Any]) -> str:
    # name format: mcp_<server>__<tool>
    _, rest = name.split("_", 1)          # strip "mcp"
    server_name, tool_name = rest.lstrip("_").split("__", 1)
    client = _MCP_CLIENTS.get(server_name)
    if client is None:
        return f"MCP server '{server_name}' is not running"
    try:
        return client.call_tool(tool_name, args)
    except Exception as exc:
        return f"MCP tool error: {exc}"


# ── Custom tool execution ─────────────────────────────────────────────────────

def _execute_custom_tool(name: str, args: dict[str, Any]) -> str:
    tool = _CUSTOM_TOOLS[name]
    cmd_template = tool.get("command", "")
    if not cmd_template:
        return f"custom tool '{name}' has no command defined"
    try:
        cmd = cmd_template
        for k, v in args.items():
            cmd = cmd.replace(f"{{{k}}}", str(v))
        result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, timeout=60
        )
        out = result.stdout
        if result.stderr:
            out += f"\n[stderr]\n{result.stderr}"
        if result.returncode != 0:
            out += f"\n[exit {result.returncode}]"
        return out.strip() or "(no output)"
    except subprocess.TimeoutExpired:
        return f"custom tool '{name}' timed out after 60s"
    except Exception as exc:
        return f"error running '{name}': {exc}"
