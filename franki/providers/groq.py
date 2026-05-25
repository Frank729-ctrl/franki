import httpx
from typing import AsyncIterator, Optional


GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"

RATE_LIMIT_SIGNALS = [
    "429", "rate limit", "quota exceeded", "usage limit",
    "too many requests", "overloaded", "capacity exceeded",
    "503", "service unavailable",
]


class GroqRateLimitError(Exception):
    pass


class GroqError(Exception):
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
    }
    payload = {
        "model": model,
        "messages": messages,
        "stream": True,
        "temperature": temperature,
    }

    async with httpx.AsyncClient(timeout=60.0) as client:
        async with client.stream("POST", GROQ_API_URL, headers=headers, json=payload) as resp:
            if resp.status_code == 429:
                body = await resp.aread()
                raise GroqRateLimitError(body.decode())
            if resp.status_code >= 400:
                body = await resp.aread()
                text = body.decode()
                if any(s in text.lower() for s in RATE_LIMIT_SIGNALS):
                    raise GroqRateLimitError(text)
                raise GroqError(f"HTTP {resp.status_code}: {text}")

            async for line in resp.aiter_lines():
                if not line.startswith("data: "):
                    continue
                data = line[6:]
                if data.strip() == "[DONE]":
                    return
                try:
                    import json
                    chunk = json.loads(data)
                    delta = chunk["choices"][0]["delta"]
                    content = delta.get("content", "")
                    if content:
                        yield content
                except (KeyError, json.JSONDecodeError):
                    continue


async def chat_once(
    api_key: str,
    model: str,
    messages: list[dict],
    temperature: float = 0.7,
) -> str:
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": messages,
        "stream": False,
        "temperature": temperature,
    }
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(GROQ_API_URL, headers=headers, json=payload)
        if resp.status_code == 429:
            raise GroqRateLimitError(resp.text)
        if resp.status_code >= 400:
            if any(s in resp.text.lower() for s in RATE_LIMIT_SIGNALS):
                raise GroqRateLimitError(resp.text)
            raise GroqError(f"HTTP {resp.status_code}: {resp.text}")
        data = resp.json()
        return data["choices"][0]["message"]["content"]
