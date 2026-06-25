"""Cache client utility with Redis support and in-memory fallback.

Provides a unified ``CacheClient`` interface for key-value storage.
If Redis is unavailable or fails to connect, transparently falls back to
an in-memory dictionary.
"""

import json
from datetime import UTC, datetime, timedelta
from typing import Any

from redis.asyncio import Redis

from src.core.settings import get_settings
from src.shared.logger import get_logger

logger = get_logger(__name__)


class CacheClient:
    """Unified cache client wrapping Redis with an in-memory fallback."""

    def __init__(self) -> None:
        self.settings = get_settings()
        self._redis: Redis | None = None
        self._fallback_store: dict[str, tuple[str, datetime | None]] = {}
        self._fallback_active = False
        self._initialized = False

    async def _init_redis(self) -> None:
        if self._initialized:
            return

        try:
            self._redis = Redis.from_url(  # type: ignore
                self.settings.REDIS_URL,
                decode_responses=True,
                socket_timeout=2.0,
                socket_connect_timeout=2.0,
            )
            # Ping to verify connection
            await self._redis.ping()  # type: ignore
            self._fallback_active = False
            logger.info("Connected to Redis cache")
        except Exception as exc:
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
            val = await self._redis.get(key)
            if isinstance(val, bytes):
                return val.decode("utf-8")
            return val
        except Exception as exc:
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
        except Exception as exc:
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
        except Exception as exc:
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
