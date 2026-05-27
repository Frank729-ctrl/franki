"""
Response cache — in-memory LRU cache for non-streaming AI calls.
Keyed by SHA-256(provider + model + messages JSON) with a TTL.
All providers benefit automatically.
"""
from __future__ import annotations
import hashlib
import json
import time
from collections import OrderedDict


class ResponseCache:
    def __init__(self, max_size: int = 128, ttl_seconds: int = 3600) -> None:
        self._store: OrderedDict[str, tuple[str, float]] = OrderedDict()
        self._max_size   = max_size
        self._ttl        = ttl_seconds
        self.hits        = 0
        self.misses      = 0

    def _key(self, provider: str, model: str, messages: list[dict]) -> str:
        payload = json.dumps([provider, model, messages], sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(payload.encode()).hexdigest()[:20]

    def get(self, provider: str, model: str, messages: list[dict]) -> str | None:
        k = self._key(provider, model, messages)
        if k not in self._store:
            self.misses += 1
            return None
        value, ts = self._store[k]
        if time.monotonic() - ts > self._ttl:
            del self._store[k]
            self.misses += 1
            return None
        self._store.move_to_end(k)
        self.hits += 1
        return value

    def put(self, provider: str, model: str, messages: list[dict], response: str) -> None:
        k = self._key(provider, model, messages)
        self._store[k] = (response, time.monotonic())
        self._store.move_to_end(k)
        while len(self._store) > self._max_size:
            self._store.popitem(last=False)

    def clear(self) -> None:
        self._store.clear()
        self.hits = 0
        self.misses = 0

    @property
    def size(self) -> int:
        return len(self._store)

    @property
    def hit_rate(self) -> float:
        total = self.hits + self.misses
        return self.hits / total if total else 0.0


# Module-level singleton — shared across all callers in the same process
response_cache = ResponseCache()
