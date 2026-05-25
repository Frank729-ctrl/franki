import httpx
import json
from typing import AsyncIterator


OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"

RATE_LIMIT_SIGNALS = [
    "429", "rate limit", "quota exceeded", "too many requests",
    "overloaded", "503", "service unavailable",
]


class OpenRouterRateLimitError(Exception):
    pass


class OpenRouterError(Exception):
    pass


async def stream_chat(
    api_key: str,
    model: str,
    messages: list[dict],
    temperature: float = 0.7,
) -> AsyncIterator[str]:
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/Frank729-ctrl/franki",
        "X-Title": "Franki CLI",
    }
    payload = {
        "model": model,
        "messages": messages,
        "stream": True,
        "temperature": temperature,
    }

    async with httpx.AsyncClient(timeout=60.0) as client:
        async with client.stream("POST", OPENROUTER_API_URL, headers=headers, json=payload) as resp:
            if resp.status_code == 429:
                body = await resp.aread()
                raise OpenRouterRateLimitError(body.decode())
            if resp.status_code >= 400:
                body = await resp.aread()
                text = body.decode()
                if any(s in text.lower() for s in RATE_LIMIT_SIGNALS):
                    raise OpenRouterRateLimitError(text)
                raise OpenRouterError(f"HTTP {resp.status_code}: {text}")

            async for line in resp.aiter_lines():
                if not line.startswith("data: "):
                    continue
                data = line[6:]
                if data.strip() == "[DONE]":
                    return
                try:
                    chunk = json.loads(data)
                    delta = chunk["choices"][0]["delta"]
                    content = delta.get("content", "")
                    if content:
                        yield content
                except (KeyError, json.JSONDecodeError):
                    continue
