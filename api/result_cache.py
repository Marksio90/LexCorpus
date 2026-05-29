"""
result_cache.py — In-process LRU cache for RAG query results.

Caches full (retrieval + LLM) responses for identical queries to reduce
OpenAI API costs at scale. TTL=24h, max 1000 entries, LRU eviction.

Not used for streaming (/ask/stream) — streaming is always real-time.
"""
from __future__ import annotations

import hashlib
import logging
import re
import time
from collections import OrderedDict
from typing import Any

log = logging.getLogger(__name__)

_TTL_SECONDS = 86_400        # 24 hours
_MAX_ENTRIES = 1_000
_TIME_SENSITIVE = re.compile(
    r"\b(dzisiaj|dziś|teraz|aktualnie|ostatnio|wczoraj|w tym roku|"
    r"od kiedy|do kiedy|kiedy|current|now|today)\b",
    re.IGNORECASE,
)


class ResultCache:
    def __init__(self, ttl: int = _TTL_SECONDS, max_size: int = _MAX_ENTRIES) -> None:
        self._cache: OrderedDict[str, tuple[float, Any]] = OrderedDict()
        self._ttl = ttl
        self._max_size = max_size
        self._hits = 0
        self._misses = 0

    def _make_key(self, question: str, source_type_filter: str | None, top_k: int) -> str:
        raw = f"{question.strip().lower()}|{source_type_filter or ''}|{top_k}"
        return hashlib.md5(raw.encode()).hexdigest()

    def _is_cacheable(self, question: str) -> bool:
        if len(question.strip()) < 20:
            return False
        if _TIME_SENSITIVE.search(question):
            return False
        return True

    def get(self, question: str, source_type_filter: str | None, top_k: int) -> Any | None:
        if not self._is_cacheable(question):
            return None
        key = self._make_key(question, source_type_filter, top_k)
        entry = self._cache.get(key)
        if entry is None:
            self._misses += 1
            return None
        ts, value = entry
        if time.time() - ts > self._ttl:
            del self._cache[key]
            self._misses += 1
            return None
        # Move to end (LRU)
        self._cache.move_to_end(key)
        self._hits += 1
        log.debug("Cache HIT (hits=%d, misses=%d)", self._hits, self._misses)
        return value

    def set(self, question: str, source_type_filter: str | None, top_k: int, value: Any) -> None:
        if not self._is_cacheable(question):
            return
        key = self._make_key(question, source_type_filter, top_k)
        self._cache[key] = (time.time(), value)
        self._cache.move_to_end(key)
        # Evict oldest if over limit
        while len(self._cache) > self._max_size:
            self._cache.popitem(last=False)

    def stats(self) -> dict:
        return {
            "entries": len(self._cache),
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": round(self._hits / max(1, self._hits + self._misses), 3),
        }


# Module-level singleton
_cache = ResultCache()


def get_cache() -> ResultCache:
    return _cache
