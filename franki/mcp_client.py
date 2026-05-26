"""
Minimal MCP (Model Context Protocol) stdio client.

Connects to an MCP server over stdin/stdout using JSON-RPC 2.0,
discovers its tools, and can invoke them.
"""
from __future__ import annotations
import json
import os
import subprocess
import threading
from typing import Any


class MCPError(Exception):
    pass


_id_lock  = threading.Lock()
_id_count = 0


def _next_id() -> int:
    global _id_count
    with _id_lock:
        _id_count += 1
        return _id_count


class MCPClient:
    def __init__(self, name: str, command: str, args: list[str], env: dict | None = None) -> None:
        self.name   = name
        self._tools: list[dict] = []
        self._lock  = threading.Lock()

        full_env = {**os.environ, **(env or {})}
        self._proc = subprocess.Popen(
            [command] + args,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            env=full_env,
        )
        self._initialized = False
        self._init()

    # ── Low-level JSON-RPC ────────────────────────────────────────────────────

    def _send(self, obj: dict) -> None:
        assert self._proc.stdin
        self._proc.stdin.write(json.dumps(obj) + "\n")
        self._proc.stdin.flush()

    def _recv(self, timeout: float = 15.0) -> dict:
        assert self._proc.stdout
        buf: list[str] = [None]  # type: ignore[list-item]
        exc: list[Exception | None] = [None]

        def _read():
            try:
                buf[0] = self._proc.stdout.readline()
            except Exception as e:
                exc[0] = e

        t = threading.Thread(target=_read, daemon=True)
        t.start()
        t.join(timeout)
        if t.is_alive():
            raise MCPError(f"MCP server '{self.name}' timed out after {timeout}s")
        if exc[0]:
            raise MCPError(f"MCP read error: {exc[0]}")
        line = buf[0]
        if not line:
            raise MCPError(f"MCP server '{self.name}' closed the connection")
        return json.loads(line)

    def _request(self, method: str, params: dict | None = None) -> Any:
        msg_id = _next_id()
        with self._lock:
            self._send({"jsonrpc": "2.0", "id": msg_id, "method": method, "params": params or {}})
            while True:
                resp = self._recv()
                # Skip notifications the server might send unprompted
                if resp.get("id") == msg_id:
                    break
        if "error" in resp:
            raise MCPError(f"MCP error from '{self.name}': {resp['error']}")
        return resp.get("result", {})

    def _notify(self, method: str, params: dict | None = None) -> None:
        with self._lock:
            self._send({"jsonrpc": "2.0", "method": method, "params": params or {}})

    # ── Initialization ────────────────────────────────────────────────────────

    def _init(self) -> None:
        try:
            self._request("initialize", {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "franki", "version": "0.1.0"},
            })
            self._notify("notifications/initialized")
            result      = self._request("tools/list")
            self._tools = result.get("tools", [])
            self._initialized = True
        except Exception as exc:
            self.stop()
            raise MCPError(f"Failed to connect to MCP server '{self.name}': {exc}") from exc

    # ── Public API ────────────────────────────────────────────────────────────

    def get_tools(self) -> list[dict]:
        """Return the raw MCP tool definitions from the server."""
        return self._tools

    def call_tool(self, tool_name: str, arguments: dict) -> str:
        """Invoke a tool and return the text result."""
        result  = self._request("tools/call", {"name": tool_name, "arguments": arguments})
        content = result.get("content", [])
        parts   = [item.get("text", "") for item in content if item.get("type") == "text"]
        text    = "\n".join(parts)
        if result.get("isError"):
            return f"[MCP error] {text}"
        return text or "(no output)"

    def stop(self) -> None:
        try:
            if self._proc.poll() is None:
                self._proc.terminate()
                self._proc.wait(timeout=3)
        except Exception:
            try:
                self._proc.kill()
            except Exception:
                pass
