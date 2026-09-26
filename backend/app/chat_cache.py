"""App 1 cache-aside implementations.

The in-memory implementation keeps tests and basic local runs independent of Redis.
Docker Compose uses Redis so separate API replicas can share cached answers and locks.
Redis is disposable: provider output remains computable when the cache is unavailable.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from typing import Callable, Iterator, Protocol

from redis import Redis
from redis.exceptions import RedisError


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CachedChat:
    answer: str


class ChatCache(Protocol):
    def get(self, key: str) -> CachedChat | None: ...
    def set(self, key: str, value: CachedChat, ttl_seconds: int) -> None: ...
    def lock(self, key: str) -> Iterator[bool]: ...


class MemoryChatCache:
    """Process-local TTL cache with per-key locks for deterministic tests."""

    def __init__(self, clock: Callable[[], float] = time.monotonic):
        self._clock = clock
        self._values: dict[str, tuple[float, CachedChat]] = {}
        self._locks: dict[str, threading.Lock] = {}
        self._guard = threading.Lock()

    def get(self, key: str) -> CachedChat | None:
        with self._guard:
            stored = self._values.get(key)
            if stored is None:
                return None
            expires_at, value = stored
            if expires_at <= self._clock():
                self._values.pop(key, None)
                return None
            return value

    def set(self, key: str, value: CachedChat, ttl_seconds: int) -> None:
        with self._guard:
            self._values[key] = (self._clock() + ttl_seconds, value)

    @contextmanager
    def lock(self, key: str) -> Iterator[bool]:
        with self._guard:
            lock = self._locks.setdefault(key, threading.Lock())
        with lock:
            yield True


class RedisChatCache:
    """Shared Redis cache and distributed lock with safe cache-miss degradation."""

    def __init__(self, redis_url: str):
        self._client = Redis.from_url(
            redis_url,
            decode_responses=True,
            socket_connect_timeout=1,
            socket_timeout=1,
        )

    def get(self, key: str) -> CachedChat | None:
        try:
            raw = self._client.get(key)
            if raw is None:
                return None
            return CachedChat(**json.loads(raw))
        except (RedisError, TypeError, ValueError):
            logger.warning("chat cache read failed; continuing as a miss", exc_info=True)
            return None

    def set(self, key: str, value: CachedChat, ttl_seconds: int) -> None:
        try:
            self._client.set(key, json.dumps(asdict(value)), ex=ttl_seconds)
        except RedisError:
            logger.warning("chat cache write failed; returning uncached result", exc_info=True)

    @contextmanager
    def lock(self, key: str) -> Iterator[bool]:
        lock = self._client.lock(f"{key}:lock", timeout=30, blocking_timeout=5)
        acquired = False
        try:
            acquired = bool(lock.acquire(blocking=True))
            yield acquired
        except RedisError:
            logger.warning("chat cache lock failed; continuing without cache lock", exc_info=True)
            yield False
        finally:
            if acquired:
                try:
                    lock.release()
                except RedisError:
                    logger.warning("chat cache lock release failed", exc_info=True)
