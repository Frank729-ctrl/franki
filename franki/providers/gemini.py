import httpx
import json
from typing import AsyncIterator


GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta/models"

RATE_LIMIT_SIGNALS = [
    "429", "rate limit", "quota exceeded", "resource_exhausted",
    "too many requests", "overloaded", "503",
]


class GeminiRateLimitError(Exception):
    pass


class GeminiError(Exception):
    pass


def _messages_to_gemini(messages: list[dict]) -> tuple[str, list[dict]]:
    system_parts = []
    contents = []
    for m in messages:
        role = m["role"]
        content = m["content"]
        if role == "system":
            system_parts.append({"text": content})
        elif role == "user":
            contents.append({"role": "user", "parts": [{"text": content}]})
        elif role == "assistant":
            contents.append({"role": "model", "parts": [{"text": content}]})
    system_instruction = system_parts[0]["text"] if system_parts else ""
    return system_instruction, contents


async def stream_chat(
    api_key: str,
    model: str,
    messages: list[dict],
    temperature: float = 0.7,
) -> AsyncIterator[str]:
    system_instruction, contents = _messages_to_gemini(messages)
    url = f"{GEMINI_BASE}/{model}:streamGenerateContent?alt=sse&key={api_key}"
    payload: dict = {
        "contents": contents,
        "generationConfig": {"temperature": temperature},
    }
    if system_instruction:
        payload["systemInstruction"] = {"parts": [{"text": system_instruction}]}

    async with httpx.AsyncClient(timeout=60.0) as client:
        async with client.stream("POST", url, json=payload) as resp:
            if resp.status_code == 429:
                body = await resp.aread()
                raise GeminiRateLimitError(body.decode())
            if resp.status_code >= 400:
                body = await resp.aread()
                text = body.decode()
                if any(s in text.lower() for s in RATE_LIMIT_SIGNALS):
                    raise GeminiRateLimitError(text)
                raise GeminiError(f"HTTP {resp.status_code}: {text}")

            async for line in resp.aiter_lines():
                if not line.startswith("data: "):
                    continue
                data = line[6:]
                if data.strip() == "[DONE]":
                    return
                try:
                    chunk = json.loads(data)
                    text = chunk["candidates"][0]["content"]["parts"][0]["text"]
                    if text:
                        yield text
                except (KeyError, json.JSONDecodeError):
                    continue
