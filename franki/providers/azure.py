"""
Azure OpenAI adapter.

Azure uses the same JSON schema as OpenAI but differs in:
  - Auth: `api-key` header instead of `Authorization: Bearer`
  - URL:  deployment-based endpoint with `api-version` query parameter
  - The base_url in config should be the full deployment endpoint, e.g.
    https://{resource}.openai.azure.com/openai/deployments/{deployment}

api-version defaults to "2024-02-01" but can be overridden via
pdata["api_version"] in the provider config.
"""
from __future__ import annotations
import json
from typing import AsyncIterator

import httpx

from franki.providers.generic import ProviderError, ProviderRateLimitError, RATE_LIMIT_SIGNALS

_DEFAULT_API_VERSION = "2024-02-01"


def _build_url(base_url: str, api_version: str) -> str:
    base = base_url.rstrip("/")
    return f"{base}/chat/completions?api-version={api_version}"


def _build_headers(api_key: str) -> dict:
    return {
        "api-key":      api_key,
        "Content-Type": "application/json",
    }


def _raise_for_status(status: int, body: str, provider: str, model: str) -> None:
    b = body.lower()
    if status == 401:
        raise ProviderError(f"{provider}: invalid API key — update with /config")
    if status == 404:
        raise ProviderError(
            f"{provider}: deployment '{model}' not found — "
            "check the deployment name in your Azure portal"
        )
    if status == 429 or any(s in b for s in RATE_LIMIT_SIGNALS):
        raise ProviderRateLimitError(f"{provider}: rate limit hit")
    if status == 500:
        raise ProviderError(f"{provider}: server error — try again")
    try:
        data = json.loads(body)
        msg = (data.get("error") or {}).get("message", "")
        if msg:
            raise ProviderError(f"{provider}: {msg}")
    except (json.JSONDecodeError, AttributeError):
        pass
    raise ProviderError(f"{provider}: HTTP {status}")


async def stream_chat(
    api_key: str,
    model: str,
    messages: list[dict],
    base_url: str,
    provider_name: str = "azure",
    temperature: float = 0.7,
    api_version: str = _DEFAULT_API_VERSION,
) -> AsyncIterator[str]:
    url = _build_url(base_url, api_version)
    payload = {
        "messages":    messages,
        "stream":      True,
        "temperature": temperature,
    }
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
                    data = line[6:]
                    if data.strip() == "[DONE]":
                        break
                    try:
                        chunk  = json.loads(data)
                        choice = chunk["choices"][0]
                        finish_reason = choice.get("finish_reason") or finish_reason
                        content = (choice.get("delta") or {}).get("content", "")
                        if content:
                            yield content
                    except (KeyError, IndexError, json.JSONDecodeError):
                        continue

    except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
        raise ProviderError(f"{provider_name}: connection failed") from exc
    except httpx.ReadTimeout:
        raise ProviderError(f"{provider_name}: response timed out")

    if finish_reason == "length":
        yield "\n\n*(response truncated — context limit reached)*"


async def stream_chat_with_tools(
    api_key: str,
    model: str,
    messages: list[dict],
    base_url: str,
    tools: list[dict],
    provider_name: str = "azure",
    temperature: float = 0.7,
    api_version: str = _DEFAULT_API_VERSION,
):
    """
    Streaming tool-capable chat via Azure OpenAI.
    Yields ("text", chunk) and ("done", json_str).
    """
    url = _build_url(base_url, api_version)
    payload = {
        "messages":    messages,
        "tools":       tools,
        "tool_choice": "auto",
        "stream":      True,
        "temperature": temperature,
    }

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
                                    "id":   tc.get("id", ""),
                                    "type": "function",
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

    except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
        raise ProviderError(f"{provider_name}: connection failed") from exc
    except httpx.ReadTimeout:
        raise ProviderError(f"{provider_name}: response timed out")

    tool_calls = [tool_calls_acc[i] for i in sorted(tool_calls_acc)]
    if finish_reason == "length" and not tool_calls:
        yield ("text", "\n\n*(response truncated — context limit reached)*")
    yield ("done", json.dumps(tool_calls))
