"""
rate_limit.py — Redis-backed sliding-window rate limiter with in-process fallback.

Uses a Redis sorted set per IP (key: rl:<ip>) where each member is a unique
request ID and the score is the Unix timestamp. On each request:
  1. Remove members older than the window
  2. Count remaining members
  3. Reject if count >= limit, otherwise add new member with TTL

Falls back silently to in-process token bucket when Redis is unavailable,
so local development without Redis works out of the box.
"""
from __future__ import annotations

import logging
import os
import time
import uuid
from collections import defaultdict

from fastapi import HTTPException

log = logging.getLogger(__name__)

RATE_LIMIT_REQUESTS = int(os.getenv("RATE_LIMIT_REQUESTS", "20"))
RATE_LIMIT_WINDOW = int(os.getenv("RATE_LIMIT_WINDOW", "60"))
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", "")


def _normalize_ip(ip: str) -> str:
    """Collapse IPv6 addresses to /64 subnet to prevent trivial rotation bypasses."""
    import ipaddress
    try:
        addr = ipaddress.ip_address(ip)
        if isinstance(addr, ipaddress.IPv6Address):
            # Rate-limit at /64 prefix (first 4 groups)
            net = ipaddress.ip_network(f"{ip}/64", strict=False)
            return str(net.network_address)
    except ValueError:
        pass
    return ip

_redis_client = None
_redis_available = False
_redis_last_failure: float = 0.0
_REDIS_RETRY_INTERVAL = 30.0  # seconds before retrying a failed Redis connection
_fallback_buckets: dict[str, list[float]] = defaultdict(list)

# Atomic Lua script: remove expired entries, check count, add new entry if under limit.
# Returns 1 if request is allowed, 0 if rate limit exceeded.
_RATE_LIMIT_SCRIPT = """
local key = KEYS[1]
local now = tonumber(ARGV[1])
local window = tonumber(ARGV[2])
local limit = tonumber(ARGV[3])
local member = ARGV[4]
redis.call('ZREMRANGEBYSCORE', key, '-inf', now - window)
local count = redis.call('ZCARD', key)
if count >= limit then
    return 0
end
redis.call('ZADD', key, now, member)
redis.call('EXPIRE', key, window + 1)
return 1
"""


def _get_redis():
    global _redis_client, _redis_available, _redis_last_failure
    if _redis_available and _redis_client is not None:
        return _redis_client
    # Retry connection after cool-down to recover from transient failures
    if not _redis_available and (time.time() - _redis_last_failure) < _REDIS_RETRY_INTERVAL:
        return None
    try:
        import redis
        url = REDIS_URL
        if REDIS_PASSWORD:
            from urllib.parse import urlparse, urlunparse
            p = urlparse(url)
            url = urlunparse(p._replace(netloc=f":{REDIS_PASSWORD}@{p.hostname}:{p.port or 6379}"))
        client = redis.from_url(url, socket_connect_timeout=1, socket_timeout=1)
        client.ping()
        _redis_client = client
        _redis_available = True
        log.info("Rate limiter: połączono z Redis (%s)", REDIS_URL)
    except Exception as exc:
        _redis_client = None
        _redis_available = False
        _redis_last_failure = time.time()
        log.warning("Rate limiter: Redis niedostępny (%s) — używam in-process fallback", exc)
    return _redis_client if _redis_available else None


def _check_redis(ip: str, client) -> None:
    key = f"rl:{ip}"
    now = time.time()
    allowed = client.eval(
        _RATE_LIMIT_SCRIPT,
        1,
        key,
        now,
        RATE_LIMIT_WINDOW,
        RATE_LIMIT_REQUESTS,
        str(uuid.uuid4()),
    )
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail=f"Zbyt wiele zapytań. Limit: {RATE_LIMIT_REQUESTS} na {RATE_LIMIT_WINDOW}s.",
        )


def _check_fallback(ip: str) -> None:
    now = time.time()
    window_start = now - RATE_LIMIT_WINDOW
    _fallback_buckets[ip] = [t for t in _fallback_buckets[ip] if t > window_start]
    if len(_fallback_buckets[ip]) >= RATE_LIMIT_REQUESTS:
        raise HTTPException(
            status_code=429,
            detail=f"Zbyt wiele zapytań. Limit: {RATE_LIMIT_REQUESTS} na {RATE_LIMIT_WINDOW}s.",
        )
    _fallback_buckets[ip].append(now)


def check_rate_limit(ip: str) -> None:
    """Check rate limit for the given IP. Raises HTTP 429 if exceeded."""
    ip = _normalize_ip(ip)
    client = _get_redis()
    if client is not None:
        try:
            _check_redis(ip, client)
            return
        except HTTPException:
            raise
        except Exception as exc:
            log.warning("Rate limiter: błąd Redis, fallback do in-process: %s", exc)
            global _redis_available
            _redis_available = False
    _check_fallback(ip)
