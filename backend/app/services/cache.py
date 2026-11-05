"""快取與分散式鎖。正式環境使用 Redis；未設定 REDIS_URL 時退回行程內記憶體實作。"""

import logging
import secrets
import time
from typing import Protocol

from redis.asyncio import Redis
from redis.exceptions import RedisError

log = logging.getLogger(__name__)

# 只有持有者（token 相符）才能釋放鎖，避免誤刪他人的鎖
_RELEASE_SCRIPT = """
if redis.call('get', KEYS[1]) == ARGV[1] then
  return redis.call('del', KEYS[1])
end
return 0
"""


class Cache(Protocol):
    backend: str

    async def get(self, key: str) -> str | None: ...
    async def set(self, key: str, value: str, ttl_s: int) -> None: ...
    async def acquire_lock(self, name: str, ttl_s: int) -> str | None: ...
    async def release_lock(self, name: str, token: str) -> None: ...
    async def close(self) -> None: ...


class MemoryCache:
    backend = "memory"

    def __init__(self) -> None:
        self._data: dict[str, tuple[str, float]] = {}

    def _alive(self, key: str) -> str | None:
        item = self._data.get(key)
        if item is None:
            return None
        value, expires_at = item
        if expires_at <= time.monotonic():
            self._data.pop(key, None)
            return None
        return value

    async def get(self, key: str) -> str | None:
        return self._alive(key)

    async def set(self, key: str, value: str, ttl_s: int) -> None:
        self._data[key] = (value, time.monotonic() + ttl_s)

    async def acquire_lock(self, name: str, ttl_s: int) -> str | None:
        if self._alive(name) is not None:
            return None
        token = secrets.token_hex(8)
        await self.set(name, token, ttl_s)
        return token

    async def release_lock(self, name: str, token: str) -> None:
        if self._alive(name) == token:
            self._data.pop(name, None)

    async def close(self) -> None:
        self._data.clear()


class RedisCache:
    backend = "redis"

    def __init__(self, client: Redis) -> None:
        self._redis = client

    async def get(self, key: str) -> str | None:
        try:
            value = await self._redis.get(key)
        except RedisError as exc:  # 快取故障不應讓搜尋失敗
            log.error("Redis GET 失敗，視為未命中：%s", exc)
            return None
        return value.decode() if isinstance(value, bytes) else value

    async def set(self, key: str, value: str, ttl_s: int) -> None:
        try:
            await self._redis.set(key, value, ex=ttl_s)
        except RedisError as exc:
            log.error("Redis SET 失敗：%s", exc)

    async def acquire_lock(self, name: str, ttl_s: int) -> str | None:
        token = secrets.token_hex(8)
        acquired = await self._redis.set(name, token, nx=True, ex=ttl_s)
        return token if acquired else None

    async def release_lock(self, name: str, token: str) -> None:
        await self._redis.eval(_RELEASE_SCRIPT, 1, name, token)

    async def close(self) -> None:
        await self._redis.aclose()


def create_cache(redis_url: str | None) -> Cache:
    if not redis_url:
        log.warning("未設定 REDIS_URL，使用行程內記憶體快取（僅適合單機開發）")
        return MemoryCache()
    return RedisCache(Redis.from_url(redis_url))
