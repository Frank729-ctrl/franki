"""
Anthropic native Messages API adapter.

Converts between the internal OpenAI-compatible message format used by
the agent loop and Anthropic's distinct request/response/SSE format, so
the rest of Franki needs no changes to support Anthropic models.
"""
from __future__ import annotations
import json
from typing import AsyncIterator

import httpx

from franki.providers.generic import ProviderError, ProviderRateLimitError, RATE_LIMIT_SIGNALS

_DEFAULT_URL     = "https://api.anthropic.com"
_API_VERSION     = "2023-06-01"
_DEFAULT_MAX_TOK = 8192


# ── Message conversion ────────────────────────────────────────────────────────

def _convert_messages(messages: list[dict]) -> tuple[str, list[dict]]:
    """
    Split OpenAI-format messages into (system_prompt, anthropic_messages).

    - system  → joined into a top-level `system` string
    - tool    → merged into preceding or new user messages as tool_result blocks
    - assistant with tool_calls → converted to tool_use content blocks
    """
    system_parts: list[str] = []
    out: list[dict] = []

    for m in messages:
        role    = m.get("role", "")
        content = m.get("content", "") or ""

        if role == "system":
            if content:
                system_parts.append(content)
            continue

        if role == "tool":
            block = {
                "type":        "tool_result",
                "tool_use_id": m.get("tool_call_id", ""),
                "content":     content if isinstance(content, str) else json.dumps(content),
            }
            # Merge consecutive tool results into one user message
            if out and out[-1]["role"] == "user" and isinstance(out[-1]["content"], list):
                out[-1]["content"].append(block)
            else:
                out.append({"role": "user", "content": [block]})
            continue

        if role == "assistant":
            tool_calls = m.get("tool_calls")
            if tool_calls:
                ant_content: list[dict] = []
                if content:
                    ant_content.append({"type": "text", "text": content})
                for tc in tool_calls:
                    fn = tc.get("function", {})
                    try:
                        args = json.loads(fn.get("arguments", "{}") or "{}")
                    except json.JSONDecodeError:
                        args = {}
                    ant_content.append({
                        "type":  "tool_use",
                        "id":    tc.get("id", ""),
                        "name":  fn.get("name", ""),
                        "input": args,
                    })
                out.append({"role": "assistant", "content": ant_content})
            else:
                out.append({"role": "assistant", "content": content})
            continue

        if role == "user":
            if isinstance(content, list):
                # Multimodal: convert OpenAI image_url blocks → Anthropic image blocks
                ant: list[dict] = []
                for part in content:
                    if not isinstance(part, dict):
                        continue
                    if part.get("type") == "text":
                        ant.append({"type": "text", "text": part.get("text", "")})
                    elif part.get("type") == "image_url":
                        url = (part.get("image_url") or {}).get("url", "")
                        if url.startswith("data:"):
                            media_type, b64 = url.split(",", 1)
                            media_type = media_type.split(";")[0].replace("data:", "")
                            ant.append({
                                "type": "image",
                                "source": {"type": "base64", "media_type": media_type, "data": b64},
                            })
                        else:
                            ant.append({
                                "type": "image",
                                "source": {"type": "url", "url": url},
                            })
                out.append({"role": "user", "content": ant or content})
            else:
                out.append({"role": "user", "content": content})

    return "\n\n".join(system_parts), out


def _convert_tools(tools: list[dict]) -> list[dict]:
    """Convert OpenAI tool schema list to Anthropic format."""
    result = []
    for t in tools:
        if t.get("type") != "function":
            continue
        fn = t.get("function", {})
        result.append({
            "name":         fn.get("name", ""),
            "description":  fn.get("description", ""),
            "input_schema": fn.get("parameters") or {"type": "object", "properties": {}},
        })
    return result


def _build_headers(api_key: str) -> dict:
    return {
        "x-api-key":         api_key,
        "anthropic-version": _API_VERSION,
        "anthropic-beta":    "prompt-caching-2024-07-31",
        "content-type":      "application/json",
    }


def _raise_for_status(status: int, body: str, provider: str, model: str, retry_after: float | None = None) -> None:
    b = body.lower()
    if status == 401:
        raise ProviderError(f"{provider}: invalid API key — update with /config")
    if status == 403:
        raise ProviderError(f"{provider}: access denied for model '{model}'")
    if status == 404:
        raise ProviderError(f"{provider}: model '{model}' not found")
    if status == 429 or any(s in b for s in RATE_LIMIT_SIGNALS):
        raise ProviderRateLimitError(f"{provider}: rate limit hit", retry_after=retry_after)
    if status == 500:
        raise ProviderError(f"{provider}: server error — try again")
    if status == 529 or status == 503:
        raise ProviderRateLimitError(f"{provider}: overloaded — try again shortly", retry_after=retry_after)
    try:
        data = json.loads(body)
        msg = (data.get("error") or {}).get("message", "")
        if msg:
            raise ProviderError(f"{provider}: {msg}")
    except (json.JSONDecodeError, AttributeError):
        pass
    raise ProviderError(f"{provider}: HTTP {status}")


# ── stream_chat (plain text streaming) ───────────────────────────────────────

async def stream_chat(
    api_key: str,
    model: str,
    messages: list[dict],
    base_url: str,
    provider_name: str = "anthropic",
    temperature: float = 0.7,
) -> AsyncIterator[str]:
    system_prompt, ant_messages = _convert_messages(messages)
    base = (base_url or _DEFAULT_URL).rstrip("/")
    url = f"{base}/v1/messages"

    payload: dict = {
        "model":      model,
        "max_tokens": _DEFAULT_MAX_TOK,
        "messages":   ant_messages,
        "stream":     True,
        "temperature": temperature,
    }
    if system_prompt:
        payload["system"] = [
            {
                "type": "text",
                "text": system_prompt,
                "cache_control": {"type": "ephemeral"},
            }
        ]

    finish_reason: str | None = None

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            async with client.stream(
                "POST", url, headers=_build_headers(api_key), json=payload
            ) as resp:
                if resp.status_code >= 400:
                    body = await resp.aread()
                    ra_raw = resp.headers.get("retry-after") or resp.headers.get("x-ratelimit-reset-after")
                    ra: float | None = None
                    if ra_raw:
                        try:
                            ra = float(ra_raw)
                        except ValueError:
                            pass
                    _raise_for_status(resp.status_code, body.decode(), provider_name, model, retry_after=ra)

                async for line in resp.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    raw = line[6:]
                    if raw.strip() == "[DONE]":
                        break
                    try:
                        evt = json.loads(raw)
                        t = evt.get("type", "")
                        if t == "content_block_delta":
                            d = evt.get("delta", {})
                            if d.get("type") == "text_delta":
                                yield d.get("text", "")
                        elif t == "message_delta":
                            finish_reason = (evt.get("delta") or {}).get("stop_reason")
                    except (json.JSONDecodeError, KeyError):
                        continue

    except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
        raise ProviderError(
            f"{provider_name}: connection failed — check your network or the base URL"
        ) from exc
    except httpx.ReadTimeout:
        raise ProviderError(f"{provider_name}: response timed out — try again")

    if finish_reason == "max_tokens":
        yield "\n\n*(response truncated — context limit reached)*"


# ── stream_chat_with_tools ────────────────────────────────────────────────────

async def stream_chat_with_tools(
    api_key: str,
    model: str,
    messages: list[dict],
    base_url: str,
    tools: list[dict],
    provider_name: str = "anthropic",
    temperature: float = 0.7,
    thinking_budget: int = 0,
):
    """
    Streaming tool-capable chat via Anthropic Messages API.
    Yields ("text", chunk) and ("done", json_str) — same interface as generic.py.
    Tool calls are returned in OpenAI format so the agent loop needs no changes.
    When thinking_budget > 0 extended thinking is enabled (budget_tokens = thinking_budget).
    """
    system_prompt, ant_messages = _convert_messages(messages)
    ant_tools = _convert_tools(tools)

    base = (base_url or _DEFAULT_URL).rstrip("/")
    url = f"{base}/v1/messages"

    payload: dict = {
        "model":      model,
        "max_tokens": _DEFAULT_MAX_TOK,
        "messages":   ant_messages,
        "stream":     True,
    }
    if thinking_budget > 0:
        # Extended thinking requires budget >= 1024 and temperature must be 1
        payload["thinking"] = {"type": "enabled", "budget_tokens": max(thinking_budget, 1024)}
        payload["temperature"] = 1
    else:
        payload["temperature"] = temperature
    if system_prompt:
        payload["system"] = [
            {
                "type": "text",
                "text": system_prompt,
                "cache_control": {"type": "ephemeral"},
            }
        ]
    if ant_tools:
        payload["tools"] = ant_tools

    # Streaming accumulators
    tool_blocks: dict[int, dict] = {}  # index → {id, name, input_json}
    finish_reason: str | None    = None

    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            async with client.stream(
                "POST", url, headers=_build_headers(api_key), json=payload
            ) as resp:
                if resp.status_code >= 400:
                    body = await resp.aread()
                    ra_raw = resp.headers.get("retry-after") or resp.headers.get("x-ratelimit-reset-after")
                    ra: float | None = None
                    if ra_raw:
                        try:
                            ra = float(ra_raw)
                        except ValueError:
                            pass
                    _raise_for_status(resp.status_code, body.decode(), provider_name, model, retry_after=ra)

                async for line in resp.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    raw = line[6:]
                    if raw.strip() == "[DONE]":
                        break
                    try:
                        evt = json.loads(raw)
                        t   = evt.get("type", "")

                        if t == "content_block_start":
                            idx   = evt.get("index", 0)
                            block = evt.get("content_block", {})
                            if block.get("type") == "tool_use":
                                tool_blocks[idx] = {
                                    "id":         block.get("id", ""),
                                    "name":       block.get("name", ""),
                                    "input_json": "",
                                }

                        elif t == "content_block_delta":
                            idx   = evt.get("index", 0)
                            delta = evt.get("delta", {})
                            dt    = delta.get("type", "")
                            if dt == "text_delta":
                                yield ("text", delta.get("text", ""))
                            elif dt == "input_json_delta" and idx in tool_blocks:
                                tool_blocks[idx]["input_json"] += delta.get("partial_json", "")

                        elif t == "message_delta":
                            finish_reason = (evt.get("delta") or {}).get("stop_reason")

                    except (json.JSONDecodeError, KeyError):
                        continue

    except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
        raise ProviderError(
            f"{provider_name}: connection failed — check your network or the base URL"
        ) from exc
    except httpx.ReadTimeout:
        raise ProviderError(f"{provider_name}: response timed out")

    # Convert accumulated Anthropic tool_use blocks → OpenAI tool_calls format
    tool_calls = []
    for idx in sorted(tool_blocks):
        b = tool_blocks[idx]
        try:
            args_str = json.dumps(json.loads(b["input_json"])) if b["input_json"] else "{}"
        except json.JSONDecodeError:
            args_str = b["input_json"] or "{}"
        tool_calls.append({
            "id":   b["id"],
            "type": "function",
            "function": {"name": b["name"], "arguments": args_str},
        })

    if finish_reason == "max_tokens" and not tool_calls:
        yield ("text", "\n\n*(response truncated — context limit reached)*")

    yield ("done", json.dumps(tool_calls))
