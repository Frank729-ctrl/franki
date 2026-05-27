"""
Agentic execution loop — tool use, plan display, permission prompts, verification.
"""
from __future__ import annotations
import json
import asyncio
import time
from pathlib import Path
from typing import TYPE_CHECKING

from rich.text import Text
from rich.rule import Rule
from rich.live import Live
from rich.spinner import Spinner
from rich.columns import Columns

from franki.agent.tools import (
    get_all_tool_schemas, NEEDS_CONFIRM, execute_tool,
    WRITE_TOOLS, READ_ONLY_TOOLS, _CUSTOM_TOOLS,
)
from franki.hooks import run_pre_tool, run_post_tool
from franki.audit import log_tool
from franki.cost_tracker import CostTracker
import sys

from franki.providers.generic import (
    stream_chat_with_tools,  # module-level name keeps test patches working
    ProviderRateLimitError,
    ProviderError,
)


def _get_stream_with_tools_fn(pdata: dict):
    """Return the right stream_chat_with_tools for this provider's api_type."""
    api_type = (pdata or {}).get("api_type", "openai")
    if api_type == "anthropic":
        from franki.providers.anthropic import stream_chat_with_tools as _fn
        return _fn
    if api_type == "cohere":
        from franki.providers.cohere import stream_chat_with_tools as _fn
        return _fn
    if api_type == "azure":
        from franki.providers.azure import stream_chat_with_tools as _fn
        return _fn
    # Look up via sys.modules so test patches on this name are respected
    return sys.modules[__name__].stream_chat_with_tools
from franki.routing import build_routing_order, RoutingTracker
from franki.ui.theme import GOLD, TEXT_DIM, TEXT_BODY
from franki.ui.phrases import pick_phrase, phrase_for_elapsed
from franki.utils.highlight import render_response

if TYPE_CHECKING:
    from franki.config import FrankiConfig
    from franki.session import Session
    from rich.console import Console

_MAX_STEPS = 15  # safety cap on tool-call iterations

import re as _re
_SEEKING_PERMISSION = _re.compile(
    r"\b(should i|shall i|do you want( me to)?|would you like( me to)?|want me to|may i)\b",
    _re.IGNORECASE,
)
_PREMATURE_STOP = _re.compile(
    r"\b(i(?:'ll| will| am going to)| let me |i need to |now i(?:'ll| will))\b",
    _re.IGNORECASE,
)
_TASK_COMPLETE = _re.compile(
    r"\b(done|complete[d]?|finish(?:ed)?|here(?:'s| is)|i(?:'ve| have) (?:updated|created|fixed|written|added|removed|refactored))\b",
    _re.IGNORECASE,
)


# ── Provider routing for tool calls ──────────────────────────────────────────

async def _call_with_tools(
    cfg: "FrankiConfig",
    messages: list[dict],
    skill: str,
    tracker: "RoutingTracker | None" = None,
    console: "Console | None" = None,
    cost_tracker: "CostTracker | None" = None,
    thinking_budget: int = 0,
) -> dict:
    """
    Route through providers using streaming tool calls.
    Shows a Live spinner with elapsed time and token count if *console* is
    provided.  Returns the assembled assistant message dict.
    """
    ordered = build_routing_order(cfg, skill, tracker or RoutingTracker())
    if not ordered:
        raise ProviderError("No providers configured — run 'franki init' or use /providers.")

    last_err: Exception | None = None
    for name, pdata, _reason in ordered:
        api_key  = cfg.get_provider_key(name)
        base_url = pdata.get("base_url", "")
        model    = pdata.get("model", "")
        if not base_url or not model:
            continue
        if not api_key and pdata.get("key_required", True):
            continue
        for attempt in range(3):
            try:
                return await _stream_and_assemble(
                    api_key, model, messages, base_url, name, console,
                    cost_tracker=cost_tracker,
                    pdata=pdata if isinstance(pdata, dict) else {},
                    thinking_budget=thinking_budget,
                )
            except ProviderRateLimitError as exc:
                last_err = exc
                if attempt < 2:
                    wait = exc.retry_after if exc.retry_after is not None else 2 ** attempt
                    await asyncio.sleep(min(wait, 60.0))
                    continue
                break
            except ProviderError:
                raise

    raise ProviderError(str(last_err) if last_err else "All providers unavailable.")


async def _stream_and_assemble(
    api_key: str,
    model: str,
    messages: list[dict],
    base_url: str,
    provider_name: str,
    console: "Console | None",
    cost_tracker: "CostTracker | None" = None,
    pdata: dict | None = None,
    thinking_budget: int = 0,
) -> dict:
    """Stream a tool-capable call, show spinner, return assembled message dict."""
    text_parts: list[str] = []
    tool_calls_json = "[]"
    t_start  = time.monotonic()
    spinner  = Spinner("dots", style=GOLD)
    _opening = pick_phrase()

    _stream_fn = _get_stream_with_tools_fn(pdata)

    async def _consume(live=None):
        nonlocal tool_calls_json
        async for event_type, value in _stream_fn(
            api_key, model, messages, base_url, get_all_tool_schemas(),
            provider_name=provider_name,
            thinking_budget=thinking_budget,
        ):
            if event_type == "text":
                text_parts.append(value)
                if live is not None:
                    elapsed = time.monotonic() - t_start
                    chars   = len("".join(text_parts))
                    phrase  = phrase_for_elapsed(elapsed, _opening)
                    t = Text()
                    t.append(f"  {phrase}  ·  {elapsed:.1f}s", style=TEXT_DIM)
                    if chars > 8:
                        t.append(f"  ·  ~{chars // 4}t", style=TEXT_DIM)
                    live.update(Columns([spinner, t]))
            elif event_type == "done":
                tool_calls_json = value

    if console is not None:
        with Live(console=console, refresh_per_second=12, transient=True) as live:
            live.update(Columns([spinner, Text(f"  {_opening}  ·  0.0s", style=TEXT_DIM)]))
            await _consume(live)
    else:
        await _consume()

    elapsed = time.monotonic() - t_start
    text = "".join(text_parts)
    tool_calls = json.loads(tool_calls_json)

    if cost_tracker is not None:
        input_tokens  = max(1, sum(len(m.get("content") or "") for m in messages) // 4)
        output_tokens = max(1, len(text) // 4)
        cost_tracker.record(
            provider=provider_name,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            pdata=pdata or {},
            latency_s=elapsed,
        )

    msg: dict = {"role": "assistant", "content": text}
    if tool_calls:
        msg["tool_calls"] = tool_calls
    return msg


# ── Permission prompts ────────────────────────────────────────────────────────

def _confirm_tool(
    console: "Console",
    tool_name: str,
    args: dict,
    auto_accept: bool,
    tool_permissions: "dict[str, str] | None" = None,
) -> bool:
    perm = (tool_permissions or {}).get(tool_name)
    if perm == "always" or auto_accept:
        return True
    if perm == "never":
        console.print(Text(
            f"  blocked: '{tool_name}' is in your deny list  (/tools allow {tool_name} to unblock)",
            style="red",
        ))
        return False

    console.print()
    if tool_name == "write_file":
        console.print(Text(f"  write  →  {args['path']}", style=GOLD))
        lines = args.get("content", "").count("\n") + 1
        console.print(Text(f"           {lines} lines", style=TEXT_DIM))
    elif tool_name == "edit_file":
        console.print(Text(f"  edit   →  {args['path']}", style=GOLD))
        old = args.get("old_str", "")[:80].replace("\n", "↵")
        console.print(Text(f"           replace: {old!r}", style=TEXT_DIM))
    elif tool_name == "run_command":
        console.print(Text(f"  run    →  {args['command']}", style=GOLD))

    console.print(Text("  proceed? [y/N] ", style=TEXT_DIM), end="")
    try:
        choice = input("").strip().lower()
        console.print()
        return choice in ("y", "yes")
    except (KeyboardInterrupt, EOFError):
        console.print()
        return False


# ── Tool display ──────────────────────────────────────────────────────────────

def _show_tool_call(
    console: "Console",
    tool_name: str,
    args: dict,
    step: int | None = None,
    total: int | None = None,
) -> None:
    icons = {
        "read_file":        "◦ reading",
        "list_directory":   "◦ listing",
        "search_files":     "◦ searching",
        "grep_files":       "◦ grep",
        "write_file":       "◦ writing",
        "edit_file":        "◦ editing",
        "run_command":      "◦ running",
        "run_background":   "◦ background",
        "check_background": "◦ checking",
        "stop_background":  "◦ stopping",
        "list_backgrounds": "◦ processes",
        "web_search":       "◦ web search",
    }
    label = icons.get(tool_name, f"◦ {tool_name}")
    if tool_name in ("read_file", "write_file", "edit_file"):
        detail = args.get("path", "")
    elif tool_name in ("run_command", "run_background"):
        detail = args.get("command", "")
    elif tool_name in ("list_directory",):
        detail = args.get("path", ".")
    elif tool_name == "search_files":
        detail = f"{args.get('pattern', '')} in {args.get('directory', '.')}"
    elif tool_name == "grep_files":
        detail = f"{args.get('query', '')} in {args.get('directory', '.')}"
    elif tool_name == "web_search":
        detail = args.get("query", "")
    elif tool_name in ("check_background", "stop_background"):
        detail = args.get("process_id", "")
    elif tool_name in _CUSTOM_TOOLS:
        detail = next(iter(args.values()), "") if args else ""
    else:
        detail = ""
    step_str = f"[{step}/{total}]  " if step is not None and total else ""
    console.print(Text(f"  {step_str}{label}  {detail}", style=TEXT_DIM))


def _show_write_diff(console: "Console", path: str, before: str, after: str) -> None:
    """Show a compact colored unified diff immediately after a file write/edit."""
    import difflib
    from rich.syntax import Syntax
    before_lines = before.splitlines(keepends=True)
    after_lines  = after.splitlines(keepends=True)
    diff = list(difflib.unified_diff(
        before_lines, after_lines,
        fromfile=f"a/{path}", tofile=f"b/{path}",
        n=2,
    ))
    if not diff:
        return
    shown = diff[:50]
    extra = len(diff) - 50
    diff_text = "".join(shown)
    if extra > 0:
        diff_text += f"\n    ... ({extra} more lines)"
    console.print(Syntax(diff_text, "diff", theme="monokai", background_color="default"))


def _show_tool_result(console: "Console", tool_name: str, result: str) -> None:
    if tool_name in WRITE_TOOLS:
        console.print(Text(f"    ✓  {result}", style=GOLD))
    elif tool_name == "run_command":
        # Show first few lines of output
        lines = result.splitlines()
        preview = "\n".join(lines[:6])
        if len(lines) > 6:
            preview += f"\n    … ({len(lines) - 6} more lines)"
        if preview:
            console.print(Text(f"    {preview}", style=TEXT_BODY))


# ── Verification ──────────────────────────────────────────────────────────────

def _read_snapshot(path: str) -> str | None:
    """Read the current content of a file for undo snapshots. Returns None if it doesn't exist."""
    p = Path(path)
    if not p.exists():
        return None
    try:
        return p.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def _maybe_verify(console: "Console", cfg: "FrankiConfig", files_written: list[str]) -> None:
    """After file edits, offer to run tests if a test suite is detectable."""
    if not files_written:
        return
    cwd = Path.cwd()

    # Detect test runner
    test_cmd: str | None = None
    if (cwd / "pytest.ini").exists() or (cwd / "pyproject.toml").exists():
        test_cmd = "python3 -m pytest --tb=short -q"
    elif (cwd / "package.json").exists():
        test_cmd = "npm test"
    elif (cwd / "Makefile").exists():
        # Look for a 'test' target
        try:
            content = (cwd / "Makefile").read_text()
            if "test:" in content or "test :" in content:
                test_cmd = "make test"
        except OSError:
            pass

    if not test_cmd:
        return

    console.print()
    console.print(Text(f"  run tests to verify? ({test_cmd})  [y/N] ", style=TEXT_DIM), end="")
    try:
        choice = input("").strip().lower()
        console.print()
    except (KeyboardInterrupt, EOFError):
        console.print()
        return

    if choice not in ("y", "yes"):
        return

    console.print(Text(f"  ◦ running  {test_cmd}", style=TEXT_DIM))
    result = execute_tool("run_command", {"command": test_cmd})
    console.print(Text(result, style=TEXT_BODY))


# ── Auto-copy + inline cost hint ─────────────────────────────────────────────

def _auto_copy(
    console: "Console",
    text: str,
    cost_tracker: "CostTracker | None",
    auto_copy: bool = False,
) -> None:
    """Show a dim hint with token/cost info. Copy to clipboard only if auto_copy is on."""
    copied = False
    if auto_copy:
        try:
            import pyperclip
            import re as _re
            clean = _re.sub(r'\[/?[^\]\s][^\]]*\]', '', text)
            pyperclip.copy(clean)
            copied = True
        except Exception:
            pass

    parts: list[str] = []
    if cost_tracker and cost_tracker.total_calls() > 0:
        tokens = cost_tracker.total_tokens()
        cost   = cost_tracker.total_cost()
        parts.append(f"~{tokens:,}t")
        if cost > 0:
            parts.append(f"${cost:.4f}")
    if copied:
        parts.append("copied ↑")

    if parts:
        console.print(Text("  " + "  ·  ".join(parts), style=TEXT_DIM))


# ── Main agent entry point ────────────────────────────────────────────────────

async def run_agent(
    cfg: "FrankiConfig",
    session: "Session",
    console: "Console",
    message: str | list,
) -> str:
    """
    Run the agentic loop for one user turn.

    1. Adds the user message to the session.
    2. Calls the AI with tool schemas.
    3. If the AI requests tools: confirms destructive ones, executes, feeds results back.
    4. Repeats until the AI returns a plain text response.
    5. Renders the final response and returns the text.
    """
    session.add_user(message)
    files_written: list[str] = []
<<<<<<< HEAD
    auto_accept    = getattr(cfg, "auto_accept", False)
    tool_permissions = getattr(cfg, "tool_permissions", {}) or {}
    notify_on_done = getattr(cfg, "notify_on_done", True)
=======
    auto_accept      = getattr(cfg, "auto_accept", False)
    tool_permissions = getattr(cfg, "tool_permissions", {}) or {}
    hooks            = getattr(cfg, "hooks", {}) or {}
    thinking_budget  = int(getattr(cfg, "thinking_budget", 0) or 0)
    notify_on_done   = getattr(cfg, "notify_on_done", True)
>>>>>>> 6d328d19bdc04b514c9b57d089213f4a73ac7c46
    sandbox        = getattr(session, "sandbox", False)
    _tracker       = getattr(session, "routing_tracker", None)
    _ct            = getattr(session, "change_tracker", None)
    _cost          = getattr(session, "cost_tracker", None)
    _start_time    = time.monotonic()
    _tool_steps    = 0

    for _step in range(_MAX_STEPS):
        # ── Call the AI with tools (streaming) ───────────────────────────────
        _max_tool_chars = getattr(cfg, "tool_result_max_chars", 2000)
        _max_turns      = getattr(cfg, "max_history_turns", 0)
        msg = await _call_with_tools(
            cfg,
            session.get_messages_for_api(
                tool_result_max_chars=int(_max_tool_chars) if isinstance(_max_tool_chars, int) else 2000,
                max_history_turns=int(_max_turns) if isinstance(_max_turns, int) else 0,
            ),
            session.skill, _tracker, console,
            cost_tracker=_cost,
            thinking_budget=thinking_budget,
        )

        tool_calls = msg.get("tool_calls") or []
        text       = (msg.get("content") or "").strip()

        # ── No tool calls → check for premature stop then finalize ───────────
        if not tool_calls:
            if not text:
                text = "Done."

            # If model is seeking confirmation and auto_accept is on, nudge it once
            if (
                auto_accept
                and _step < _MAX_STEPS - 2
                and _SEEKING_PERMISSION.search(text)
                and not _TASK_COMPLETE.search(text)
            ):
                session.add_tool_call_message({"role": "assistant", "content": text})
                session.add_user("Yes, go ahead.")
                continue

            # If model announced intent but took no action on the very first step, nudge once
            if (
                _step == 0
                and _tool_steps == 0
                and _PREMATURE_STOP.search(text)
                and not _TASK_COMPLETE.search(text)
            ):
                session.add_tool_call_message({"role": "assistant", "content": text})
                session.add_user("Please proceed.")
                continue

            session.add_assistant(text)
            console.print()
            render_response(console, text, prefix="  ● ")
            _auto_copy(console, text, _cost, auto_copy=getattr(cfg, "auto_copy", False))
            _maybe_verify(console, cfg, files_written)
            if auto_accept and notify_on_done and _tool_steps > 0:
                from franki.notifications import notify_done
                notify_done(
                    console,
                    steps=_tool_steps,
                    files_written=len(files_written),
                    elapsed_s=time.monotonic() - _start_time,
                    skill=session.skill,
                )
            return text

        # ── Show AI reasoning / plan before tools ─────────────────────────────
        if text:
            console.print()
            render_response(console, text, prefix="  ● ")

        # ── Store the assistant tool-call message ─────────────────────────────
        session.add_tool_call_message(msg)

        # ── Parse all tool call args up-front ────────────────────────────────
        parsed: list[tuple] = []  # (tc, fn_name, fn_args)
        for tc in tool_calls:
            fn_name = tc["function"]["name"]
            try:
                fn_args = json.loads(tc["function"]["arguments"])
            except (json.JSONDecodeError, KeyError):
                fn_args = {}
            parsed.append((tc, fn_name, fn_args))

        # ── Split: read-only (parallelisable) vs write/exec (sequential) ─────
        read_batch  = [(tc, n, a) for tc, n, a in parsed if n in READ_ONLY_TOOLS]
        other_batch = [(tc, n, a) for tc, n, a in parsed if n not in READ_ONLY_TOOLS]

        results: dict[str, str] = {}
        batch_total = len(parsed)

        # Run all read-only tools concurrently
        if read_batch:
            for i, (tc, fn_name, fn_args) in enumerate(read_batch, 1):
                _show_tool_call(console, fn_name, fn_args, step=i, total=batch_total)
            loop = asyncio.get_event_loop()
            from concurrent.futures import ThreadPoolExecutor
            with ThreadPoolExecutor() as pool:
                futures = {
                    tc["id"]: loop.run_in_executor(pool, execute_tool, fn_name, fn_args)
                    for tc, fn_name, fn_args in read_batch
                }
                gathered = await asyncio.gather(*futures.values(), return_exceptions=True)
            for (tc, fn_name, _fn_args), res in zip(read_batch, gathered):
                r = str(res) if isinstance(res, Exception) else res
                log_tool(fn_name, _fn_args, r)
                _show_tool_result(console, fn_name, r)
                results[tc["id"]] = r

        # When auto-accepting, parallelize writes to non-conflicting paths
        if auto_accept and len(other_batch) > 1:
            seen_paths: set[str] = set()
            parallel_writes: list[tuple] = []
            remaining_other: list[tuple] = []
            for item in other_batch:
                tc2, fn2, fa2 = item
                path2 = fa2.get("path", "")
                if fn2 in WRITE_TOOLS and path2 and path2 not in seen_paths:
                    seen_paths.add(path2)
                    parallel_writes.append(item)
                else:
                    remaining_other.append(item)
            if len(parallel_writes) > 1:
                from concurrent.futures import ThreadPoolExecutor
                _pw_loop = asyncio.get_event_loop()
                with ThreadPoolExecutor() as _pw_pool:
                    _pw_futures = {
                        tc2["id"]: _pw_loop.run_in_executor(
                            _pw_pool, execute_tool, fn2, fa2
                        )
                        for tc2, fn2, fa2 in parallel_writes
                    }
                    _pw_results = await asyncio.gather(*_pw_futures.values(), return_exceptions=True)
                for (tc2, fn2, fa2), res2 in zip(parallel_writes, _pw_results):
                    r2 = str(res2) if isinstance(res2, Exception) else res2
                    path2 = fa2.get("path", "")
                    files_written.append(path2)
                    _before2 = _read_snapshot(path2)
                    after2   = fa2.get("content", "")
                    if not after2 and Path(path2).exists():
                        try:
                            after2 = Path(path2).read_text(encoding="utf-8", errors="replace")
                        except OSError:
                            after2 = ""
                    if _ct is not None:
                        _ct.record(path2, _before2, after2, fn2)
                    _show_write_diff(console, path2, _before2 or "", after2)
                    _show_tool_result(console, fn2, r2)
                    log_tool(fn2, fa2, r2)
                    results[tc2["id"]] = r2
                other_batch = remaining_other

        # Run write/exec tools sequentially with confirmation
        cancelled = False
        read_count = len(read_batch)
        for i, (tc, fn_name, fn_args) in enumerate(other_batch, read_count + 1):
            _show_tool_call(console, fn_name, fn_args, step=i, total=batch_total)
            # Sandbox: block destructive tools entirely
            if sandbox and fn_name in NEEDS_CONFIRM:
                console.print(Text(
                    f"  sandbox: '{fn_name}' blocked — disable with /sandbox off",
                    style="yellow",
                ))
                results[tc["id"]] = f"blocked by sandbox mode: {fn_name}"
                cancelled = True
                continue
            if fn_name in NEEDS_CONFIRM or fn_name in _CUSTOM_TOOLS:
                if not _confirm_tool(console, fn_name, fn_args, auto_accept, tool_permissions):
                    results[tc["id"]] = "user declined — skipped"
                    cancelled = True
                    continue

            # Snapshot before write for /undo and inline diff
            _before: str | None = None
            if fn_name in WRITE_TOOLS:
                path = fn_args.get("path", "")
                _before = _read_snapshot(path)

            pre_out = run_pre_tool(hooks, fn_name, fn_args)
            if pre_out:
                console.print(Text(f"  [hook] {pre_out}", style=TEXT_DIM))

            result = execute_tool(fn_name, fn_args)
            log_tool(fn_name, fn_args, result)

            post_out = run_post_tool(hooks, fn_name, result)
            if post_out:
                console.print(Text(f"  [hook] {post_out}", style=TEXT_DIM))

            if fn_name in WRITE_TOOLS:
                path = fn_args.get("path", "")
                files_written.append(path)
                after_content = fn_args.get("content", "")
                if not after_content and Path(path).exists():
                    try:
                        after_content = Path(path).read_text(encoding="utf-8", errors="replace")
                    except OSError:
                        after_content = ""
                if _ct is not None:
                    _ct.record(path, _before, after_content, fn_name)
                _show_write_diff(console, path, _before or "", after_content)

            _show_tool_result(console, fn_name, result)
            results[tc["id"]] = result

        # Feed results back to session in original order
        for tc, _fn_name, _fn_args in parsed:
            session.add_tool_result(tc["id"], results.get(tc["id"], "(no result)"))

        _tool_steps += 1

        if cancelled and not read_batch and all(
            n in NEEDS_CONFIRM for _, n, _ in other_batch
        ):
            break

    # Hit max steps or all cancelled
    final = "I've completed the available steps. Let me know if you'd like me to continue."
    session.add_assistant(final)
    console.print()
    render_response(console, final, prefix="  ● ")
    _auto_copy(console, final, _cost, auto_copy=getattr(cfg, "auto_copy", False))
    if auto_accept and notify_on_done and _tool_steps > 0:
        from franki.notifications import notify_done
        notify_done(
            console,
            steps=_tool_steps,
            files_written=len(files_written),
            elapsed_s=time.monotonic() - _start_time,
            skill=session.skill,
        )
    return final
