from __future__ import annotations
import json
import httpx
from typing import AsyncIterator


class DelkaAIRateLimitError(Exception):
    """429 from DelkaAI — show rate-limit notice, fall back to direct providers."""


class DelkaAIFallbackError(Exception):
    """Connection error or 401 — silent fallback to direct providers."""


async def stream_chat(
    api_key: str,
    model: str,
    messages: list[dict],
    url: str = "https://api.delkaai.com",
    temperature: float = 0.7,
) -> AsyncIterator[str]:
    endpoint = f"{url.rstrip('/')}/v1/chat"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    body = {
        "messages": messages,
        "stream": True,
        "model": model,
        "temperature": temperature,
    }

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            async with client.stream("POST", endpoint, headers=headers, json=body) as resp:
                if resp.status_code == 401:
                    raise DelkaAIFallbackError("DelkaAI: unauthorized (401)")
                if resp.status_code == 429:
                    raise DelkaAIRateLimitError("DelkaAI: rate limit (429)")
                if resp.status_code >= 400:
                    raise DelkaAIFallbackError(f"DelkaAI: HTTP {resp.status_code}")

                async for line in resp.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        break
                    try:
                        obj = json.loads(data)
                        delta = obj["choices"][0]["delta"]
                        chunk = delta.get("content") or ""
                        if chunk:
                            yield chunk
                    except (KeyError, json.JSONDecodeError):
                        continue

    except (httpx.ConnectError, httpx.TimeoutException, httpx.RemoteProtocolError) as exc:
        raise DelkaAIFallbackError(f"DelkaAI: connection error — {exc}") from exc
