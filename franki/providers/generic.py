"""
Universal OpenAI-compatible streaming provider.
Works with Groq, Gemini (via OpenAI-compat endpoint), OpenRouter, Ollama,
Together AI, Mistral, Cerebras, and any other OpenAI-compatible API.
"""
from __future__ import annotations
import json
from typing import AsyncIterator

import httpx

RATE_LIMIT_SIGNALS = [
    "429", "rate_limit", "rate limit", "quota_exceeded", "quota exceeded",
    "usage limit", "too many requests", "overloaded", "capacity exceeded",
    "503", "service unavailable",
]


class ProviderRateLimitError(Exception):
    """Raised on HTTP 429 / rate-limit responses.

    ``retry_after`` carries the server-suggested wait in seconds when the
    response includes a ``Retry-After`` header; otherwise it is ``None``.
    """
    def __init__(self, message: str, retry_after: float | None = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after


class ProviderError(Exception):
    pass


def _parse_friendly_error(status: int, body: str, provider: str, model: str) -> str:
    b = body.lower()
    if status == 401:
        return (
            f"{provider}: invalid API key — update it with /config or 'franki config'"
        )
    if status == 403:
        return f"{provider}: access denied — your key may not have permission for '{model}'"
    if status == 404:
        return (
            f"{provider}: model '{model}' not found — "
            "check the model name with /model or /config"
        )
    if status == 429 or any(s in b for s in RATE_LIMIT_SIGNALS):
        return f"{provider}: rate limit hit"
    if status == 500:
        return f"{provider}: server error — try again in a moment"
    if status == 503:
        return f"{provider}: service unavailable — try again or add a fallback provider"

    try:
        data = json.loads(body)
        err = data.get("error", {})
        msg = ""
        if isinstance(err, dict):
            msg = err.get("message", "")
        elif isinstance(err, str):
            msg = err
        if msg:
            return f"{provider}: {msg}"
    except Exception:
        pass

    return f"{provider}: HTTP {status}"


async def stream_chat(
    api_key: str,
    model: str,
    messages: list[dict],
    base_url: str,
    provider_name: str = "provider",
    temperature: float = 0.7,
) -> AsyncIterator[str]:
    url = f"{base_url.rstrip('/')}/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": messages,
        "stream": True,
        "temperature": temperature,
    }

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            async with client.stream("POST", url, headers=headers, json=payload) as resp:
                if resp.status_code >= 400:
                    body = await resp.aread()
                    text = body.decode()
                    friendly = _parse_friendly_error(
                        resp.status_code, text, provider_name, model
                    )
                    if resp.status_code == 429 or any(
                        s in text.lower() for s in RATE_LIMIT_SIGNALS
                    ):
                        ra_raw = resp.headers.get("retry-after") or resp.headers.get("x-ratelimit-reset-after")
                        retry_after: float | None = None
                        if ra_raw:
                            try:
                                retry_after = float(ra_raw)
                            except ValueError:
                                pass
                        raise ProviderRateLimitError(friendly, retry_after=retry_after)
                    raise ProviderError(friendly)

                finish_reason: str | None = None
                async for line in resp.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    data = line[6:]
                    if data.strip() == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data)
                        choice = chunk["choices"][0]
                        finish_reason = choice.get("finish_reason") or finish_reason
                        content = (choice.get("delta") or {}).get("content", "")
                        if content:
                            yield content
                    except (KeyError, IndexError, json.JSONDecodeError):
                        continue

                if finish_reason == "length":
                    yield "\n\n*(response truncated — context limit reached)*"

    except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
        raise ProviderError(
            f"{provider_name}: connection failed — check your network or the provider URL"
        ) from exc
    except httpx.ReadTimeout:
        raise ProviderError(
            f"{provider_name}: response timed out — the model may be slow, try again"
        )


async def chat_with_tools(
    api_key: str,
    model: str,
    messages: list[dict],
    base_url: str,
    tools: list[dict],
    provider_name: str = "provider",
    temperature: float = 0.7,
) -> dict:
    """
    Non-streaming call with tool/function-calling support.
    Returns the full assistant message dict, which may contain:
      - 'content': text  (finish_reason == 'stop')
      - 'tool_calls': [...]  (finish_reason == 'tool_calls')
    """
    url = f"{base_url.rstrip('/')}/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": messages,
        "tools": tools,
        "tool_choice": "auto",
        "stream": False,
        "temperature": temperature,
    }
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(url, headers=headers, json=payload)
            if resp.status_code >= 400:
                friendly = _parse_friendly_error(
                    resp.status_code, resp.text, provider_name, model
                )
                if resp.status_code == 429 or any(
                    s in resp.text.lower() for s in RATE_LIMIT_SIGNALS
                ):
                    ra_raw = resp.headers.get("retry-after") or resp.headers.get("x-ratelimit-reset-after")
                    retry_after: float | None = None
                    if ra_raw:
                        try:
                            retry_after = float(ra_raw)
                        except ValueError:
                            pass
                    raise ProviderRateLimitError(friendly, retry_after=retry_after)
                raise ProviderError(friendly)
            data = resp.json()
            return data["choices"][0]["message"]
    except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
        raise ProviderError(
            f"{provider_name}: connection failed — check your network or the provider URL"
        ) from exc
    except httpx.ReadTimeout:
        raise ProviderError(
            f"{provider_name}: response timed out"
        )


async def stream_chat_with_tools(
    api_key: str,
    model: str,
    messages: list[dict],
    base_url: str,
    tools: list[dict],
    provider_name: str = "provider",
    temperature: float = 0.7,
):
    """
    Streaming tool-capable chat call.

    Yields ``("text", chunk)`` for each content delta as it arrives, then a
    single ``("done", json_str)`` where *json_str* is the assembled tool_calls
    list (JSON array string).  Yields ``("done", "[]")`` for a plain-text
    response with no tool calls.

    Use instead of ``chat_with_tools`` when you want live token feedback.
    """
    url = f"{base_url.rstrip('/')}/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model":        model,
        "messages":     messages,
        "tools":        tools,
        "tool_choice":  "auto",
        "stream":       True,
        "temperature":  temperature,
    }

    tool_calls_acc: dict[int, dict] = {}

    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            async with client.stream("POST", url, headers=headers, json=payload) as resp:
                if resp.status_code >= 400:
                    body = await resp.aread()
                    text = body.decode()
                    friendly = _parse_friendly_error(
                        resp.status_code, text, provider_name, model
                    )
                    if resp.status_code == 429 or any(
                        s in text.lower() for s in RATE_LIMIT_SIGNALS
                    ):
                        ra_raw = resp.headers.get("retry-after") or resp.headers.get("x-ratelimit-reset-after")
                        retry_after: float | None = None
                        if ra_raw:
                            try:
                                retry_after = float(ra_raw)
                            except ValueError:
                                pass
                        raise ProviderRateLimitError(friendly, retry_after=retry_after)
                    raise ProviderError(friendly)

                finish_reason: str | None = None
                async for line in resp.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    raw = line[6:]
                    if raw.strip() == "[DONE]":
                        break
                    try:
                        chunk  = json.loads(raw)
                        choice = chunk["choices"][0]
                        delta  = choice.get("delta", {})
                        finish_reason = choice.get("finish_reason") or finish_reason

                        content = delta.get("content") or ""
                        if content:
                            yield ("text", content)

                        for tc in delta.get("tool_calls") or []:
                            idx = tc.get("index", 0)
                            if idx not in tool_calls_acc:
                                tool_calls_acc[idx] = {
                                    "id":       tc.get("id", ""),
                                    "type":     "function",
                                    "function": {
                                        "name":      (tc.get("function") or {}).get("name", ""),
                                        "arguments": "",
                                    },
                                }
                            else:
                                if tc.get("id"):
                                    tool_calls_acc[idx]["id"] = tc["id"]
                                fn = tc.get("function") or {}
                                if fn.get("name"):
                                    tool_calls_acc[idx]["function"]["name"] += fn["name"]
                                if fn.get("arguments"):
                                    tool_calls_acc[idx]["function"]["arguments"] += fn["arguments"]

                    except (KeyError, IndexError, json.JSONDecodeError):
                        continue

                if finish_reason == "length" and not tool_calls_acc:
                    yield ("text", "\n\n*(response truncated — context limit reached)*")

    except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
        raise ProviderError(
            f"{provider_name}: connection failed — check your network or the provider URL"
        ) from exc
    except httpx.ReadTimeout:
        raise ProviderError(f"{provider_name}: response timed out")

    tool_calls = [tool_calls_acc[i] for i in sorted(tool_calls_acc)]
    yield ("done", json.dumps(tool_calls))


async def chat_once(
    api_key: str,
    model: str,
    messages: list[dict],
    base_url: str,
    provider_name: str = "provider",
    temperature: float = 0.7,
) -> str:
    url = f"{base_url.rstrip('/')}/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": messages,
        "stream": False,
        "temperature": temperature,
        "max_tokens": 8,
    }
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(url, headers=headers, json=payload)
            if resp.status_code >= 400:
                friendly = _parse_friendly_error(
                    resp.status_code, resp.text, provider_name, model
                )
                if resp.status_code == 429 or any(
                    s in resp.text.lower() for s in RATE_LIMIT_SIGNALS
                ):
                    raise ProviderRateLimitError(friendly)
                raise ProviderError(friendly)
            data = resp.json()
            return data["choices"][0]["message"]["content"]
    except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
        raise ProviderError(
            f"{provider_name}: connection failed"
        ) from exc
