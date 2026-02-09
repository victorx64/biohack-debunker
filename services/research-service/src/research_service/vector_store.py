from __future__ import annotations

import time
from typing import Dict, Tuple

from .schemas import ResearchResponse


class CacheStore:
    def __init__(self, ttl_seconds: int) -> None:
        self._ttl_seconds = ttl_seconds
        self._store: Dict[str, Tuple[float, ResearchResponse]] = {}

    @property
    def ttl_seconds(self) -> int:
        return self._ttl_seconds

    def get(self, key: str) -> ResearchResponse | None:
        entry = self._store.get(key)
        if not entry:
            return None
        expires_at, value = entry
        if time.time() > expires_at:
            self._store.pop(key, None)
            return None
        return value

    def set(self, key: str, value: ResearchResponse) -> None:
        expires_at = time.time() + self._ttl_seconds
        self._store[key] = (expires_at, value)

    def size(self) -> int:
        return len(self._store)
