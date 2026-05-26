"""
Cohere Chat v2 API adapter.

Cohere's v2 API uses a streaming format different from OpenAI's SSE,
but the message schema is compatible enough to adapt with a thin layer.
"""
from __future__ import annotations
import json
from typing import AsyncIterator

import httpx

from franki.providers.generic import ProviderError, ProviderRateLimitError, RATE_LIMIT_SIGNALS

_DEFAULT_URL = "https://api.cohere.com"


def _convert_tool_results(messages: list[dict]) -> list[dict]:
    """
    Cohere v2 expects tool results as content arrays in user messages.
    OpenAI uses role=tool with tool_call_id.  Merge them.
    """
    out: list[dict] = []
    for m in messages:
        role = m.get("role", "")
        if role == "system":
            out.append(m)
            continue
        if role == "tool":
            block = {
                "type":         "tool_result",
                "tool_use_id":  m.get("tool_call_id", ""),
                "content":      [{"type": "text", "text": m.get("content", "")}],
            }
            if out and out[-1]["role"] == "user" and isinstance(out[-1].get("content"), list):
                out[-1]["content"].append(block)
            else:
                out.append({"role": "user", "content": [block]})
            continue
        out.append(m)
    return out


def _build_headers(api_key: str) -> dict:
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type":  "application/json",
        "Accept":        "application/json",
    }


def _raise_for_status(status: int, body: str, provider: str, model: str) -> None:
    b = body.lower()
    if status == 401:
        raise ProviderError(f"{provider}: invalid API key — update with /config")
    if status == 404:
        raise ProviderError(f"{provider}: model '{model}' not found")
    if status == 429 or any(s in b for s in RATE_LIMIT_SIGNALS):
        raise ProviderRateLimitError(f"{provider}: rate limit hit")
    raise ProviderError(f"{provider}: HTTP {status}")


async def stream_chat(
    api_key: str,
    model: str,
    messages: list[dict],
    base_url: str,
    provider_name: str = "cohere",
    temperature: float = 0.7,
) -> AsyncIterator[str]:
    """Stream chat via Cohere's v2 /chat endpoint."""
    msgs = _convert_tool_results(messages)
    # Extract system message into preamble
    preamble = ""
    chat_msgs = []
    for m in msgs:
        if m.get("role") == "system":
            preamble = m.get("content", "")
        else:
            chat_msgs.append(m)

    base = (base_url or _DEFAULT_URL).rstrip("/")
    url = f"{base}/v2/chat"

    payload: dict = {
        "model":       model,
        "messages":    chat_msgs,
        "stream":      True,
        "temperature": temperature,
    }
    if preamble:
        payload["preamble"] = preamble

    finish_reason: str | None = None

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            async with client.stream(
                "POST", url, headers=_build_headers(api_key), json=payload
            ) as resp:
                if resp.status_code >= 400:
                    body = await resp.aread()
                    _raise_for_status(resp.status_code, body.decode(), provider_name, model)

                async for line in resp.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    raw = line[6:]
                    if raw.strip() == "[DONE]":
                        break
                    try:
                        evt = json.loads(raw)
                        t = evt.get("type", "")
                        if t == "content-delta":
                            text = (
                                (evt.get("delta") or {})
                                .get("message", {})
                                .get("content", {})
                                .get("text", "")
                            )
                            if text:
                                yield text
                        elif t == "message-end":
                            finish_reason = (evt.get("delta") or {}).get("finish_reason", "")
                    except (json.JSONDecodeError, KeyError):
                        continue

    except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
        raise ProviderError(f"{provider_name}: connection failed") from exc
    except httpx.ReadTimeout:
        raise ProviderError(f"{provider_name}: response timed out")

    if finish_reason and finish_reason.upper() in ("MAX_TOKENS", "LENGTH"):
        yield "\n\n*(response truncated — context limit reached)*"


async def stream_chat_with_tools(
    api_key: str,
    model: str,
    messages: list[dict],
    base_url: str,
    tools: list[dict],
    provider_name: str = "cohere",
    temperature: float = 0.7,
):
    """
    Streaming tool-capable chat via Cohere v2.
    Yields ("text", chunk) and ("done", json_str) matching the OpenAI adapter interface.
    """
    msgs = _convert_tool_results(messages)
    preamble = ""
    chat_msgs = []
    for m in msgs:
        if m.get("role") == "system":
            preamble = m.get("content", "")
        else:
            chat_msgs.append(m)

    # Cohere uses OpenAI-compatible tool schemas for v2
    base = (base_url or _DEFAULT_URL).rstrip("/")
    url = f"{base}/v2/chat"

    payload: dict = {
        "model":       model,
        "messages":    chat_msgs,
        "stream":      True,
        "temperature": temperature,
    }
    if preamble:
        payload["preamble"] = preamble
    if tools:
        payload["tools"] = [t for t in tools if t.get("type") == "function"]

    tool_calls_acc: dict[int, dict] = {}
    finish_reason: str | None = None

    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            async with client.stream(
                "POST", url, headers=_build_headers(api_key), json=payload
            ) as resp:
                if resp.status_code >= 400:
                    body = await resp.aread()
                    _raise_for_status(resp.status_code, body.decode(), provider_name, model)

                async for line in resp.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    raw = line[6:]
                    if raw.strip() == "[DONE]":
                        break
                    try:
                        evt = json.loads(raw)
                        t = evt.get("type", "")

                        if t == "content-delta":
                            text = (
                                (evt.get("delta") or {})
                                .get("message", {})
                                .get("content", {})
                                .get("text", "")
                            )
                            if text:
                                yield ("text", text)

                        elif t == "tool-call-start":
                            idx  = evt.get("index", 0)
                            tcs  = (evt.get("delta", {}).get("message", {}).get("tool_calls") or [{}])
                            tc   = tcs[0] if tcs else {}
                            fn   = tc.get("function", {})
                            tool_calls_acc[idx] = {
                                "id":   tc.get("id", ""),
                                "type": "function",
                                "function": {
                                    "name":      fn.get("name", ""),
                                    "arguments": fn.get("arguments", ""),
                                },
                            }

                        elif t == "tool-call-delta":
                            idx  = evt.get("index", 0)
                            tcs  = (evt.get("delta", {}).get("message", {}).get("tool_calls") or [{}])
                            fn   = (tcs[0] if tcs else {}).get("function", {})
                            if idx in tool_calls_acc:
                                tool_calls_acc[idx]["function"]["arguments"] += fn.get("arguments", "")

                        elif t == "message-end":
                            finish_reason = (evt.get("delta") or {}).get("finish_reason", "")

                    except (json.JSONDecodeError, KeyError):
                        continue

    except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
        raise ProviderError(f"{provider_name}: connection failed") from exc
    except httpx.ReadTimeout:
        raise ProviderError(f"{provider_name}: response timed out")

    tool_calls = [tool_calls_acc[i] for i in sorted(tool_calls_acc)]

    if not tool_calls and finish_reason and finish_reason.upper() in ("MAX_TOKENS", "LENGTH"):
        yield ("text", "\n\n*(response truncated — context limit reached)*")

    yield ("done", json.dumps(tool_calls))
