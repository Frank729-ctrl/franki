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
    pass


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
                        raise ProviderRateLimitError(friendly)
                    raise ProviderError(friendly)

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

    except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
        raise ProviderError(
            f"{provider_name}: connection failed — check your network or the provider URL"
        ) from exc
    except httpx.ReadTimeout:
        raise ProviderError(
            f"{provider_name}: response timed out — the model may be slow, try again"
        )


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
