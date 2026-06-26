"""Cache client utility with Redis support and in-memory fallback.

Provides a unified ``CacheClient`` interface for key-value storage.
If Redis is unavailable or fails to connect, transparently falls back to
an in-memory dictionary.
"""

import asyncio
import contextlib
import json
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol, cast

import redis.asyncio as aioredis
from redis.exceptions import RedisError

from src.core.settings import get_settings
from src.shared.logger import get_logger

logger = get_logger(__name__)


class _AsyncRedis(Protocol):
    """Typed view of the ``redis.asyncio`` client methods this module uses.

    redis-py's async client is under-typed: its commands inherit
    ``Union[Awaitable[T], T]`` signatures from the sync core, so pyright's
    strict mode reports their members as partially unknown (see
    https://github.com/redis/redis-py/issues/3169). Pinning exact async
    signatures here restores real type checking at every call site, so the
    only unavoidable suppression is the untyped ``from_url`` constructor.
    """

    async def ping(self) -> bool: ...
    async def get(self, name: str) -> str | None: ...
    async def set(self, name: str, value: str, *, ex: int | None = None) -> bool | None: ...
    async def delete(self, *names: str) -> int: ...
    async def aclose(self) -> None: ...


class CacheClient:
    """Unified cache client wrapping Redis with an in-memory fallback."""

    def __init__(self) -> None:
        self.settings = get_settings()
        self._redis: _AsyncRedis | None = None
        self._fallback_store: dict[str, tuple[str, datetime | None]] = {}
        self._fallback_active = False
        self._initialized = False
        self._loop: asyncio.AbstractEventLoop | None = None

    async def _init_redis(self) -> None:
        current_loop = asyncio.get_running_loop()

        if self._initialized and self._loop is current_loop:
            return

        # Event loop changed (e.g. between tests) — tear down stale connection.
        if self._redis is not None:
            with contextlib.suppress(Exception):
                await self._redis.aclose()
            self._redis = None

        self._loop = current_loop
        self._initialized = False
        self._fallback_active = False

        try:
            self._redis = cast(
                "_AsyncRedis",
                aioredis.from_url(  # pyright: ignore[reportUnknownMemberType]  # redis/redis-py#3169
                    self.settings.REDIS_URL,
                    decode_responses=True,
                    socket_timeout=2.0,
                    socket_connect_timeout=2.0,
                ),
            )
            # Ping to verify connection
            await self._redis.ping()
            self._fallback_active = False
            logger.info("Connected to Redis cache")
        except (RedisError, OSError) as exc:
            self._fallback_active = True
            self._redis = None
            logger.warning(
                "Redis connection failed, falling back to in-memory cache store",
                error=str(exc),
            )
        finally:
            self._initialized = True

    async def get(self, key: str) -> str | None:
        """Retrieve value from cache by key. Returns ``None`` if expired or missing."""
        await self._init_redis()

        if self._fallback_active or not self._redis:
            if key not in self._fallback_store:
                return None
            val, expiry = self._fallback_store[key]
            if expiry and datetime.now(UTC) > expiry:
                del self._fallback_store[key]
                return None
            return val

        try:
            return await self._redis.get(key)
        except RedisError as exc:
            logger.warning("Redis GET error, using in-memory store", key=key, error=str(exc))
            self._fallback_active = True
            return await self.get(key)

    async def set(self, key: str, value: str, ttl: int | None = None) -> None:
        """Set key-value pair in cache with optional TTL in seconds."""
        await self._init_redis()

        if self._fallback_active or not self._redis:
            expiry = datetime.now(UTC) + timedelta(seconds=ttl) if ttl else None
            self._fallback_store[key] = (value, expiry)
            return

        try:
            await self._redis.set(key, value, ex=ttl)
        except RedisError as exc:
            logger.warning("Redis SET error, using in-memory store", key=key, error=str(exc))
            self._fallback_active = True
            await self.set(key, value, ttl)

    async def delete(self, key: str) -> None:
        """Remove key from cache."""
        await self._init_redis()

        if self._fallback_active or not self._redis:
            self._fallback_store.pop(key, None)
            return

        try:
            await self._redis.delete(key)
        except RedisError as exc:
            logger.warning("Redis DELETE error, using in-memory store", key=key, error=str(exc))
            self._fallback_active = True
            await self.delete(key)

    async def get_json(self, key: str) -> Any | None:  # noqa: ANN401
        """Retrieve key and deserialize from JSON."""
        val = await self.get(key)
        return json.loads(val) if val else None

    async def set_json(self, key: str, value: Any, ttl: int | None = None) -> None:  # noqa: ANN401
        """Serialize value to JSON and store in cache."""
        await self.set(key, json.dumps(value), ttl)

    async def close(self) -> None:
        """Close connection to Redis."""
        if self._redis:
            await self._redis.aclose()
            logger.info("Closed Redis connection")


# Module-level singleton
_cache_client = CacheClient()


def get_cache_client() -> CacheClient:
    """Return the cached ``CacheClient`` singleton."""
    return _cache_client
