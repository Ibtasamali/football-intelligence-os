"""Key-value store with TTL backing CAG, the shared insight cache and the LLM response cache.

Redis when REDIS_URL is reachable (Azure Cache for Redis in production), otherwise an in-process
TTL map. Both expose the same async interface so the rest of the system is unaware of the backend.
"""
from __future__ import annotations

import json
import time
from typing import Any

from app.core.logging import get_logger

log = get_logger("cag.store")


class MemoryKV:
    backend = "memory"

    def __init__(self) -> None:
        self._d: dict[str, tuple[float, str]] = {}

    async def get(self, key: str) -> str | None:
        item = self._d.get(key)
        if not item:
            return None
        exp, val = item
        if exp and exp < time.time():
            self._d.pop(key, None)
            return None
        return val

    async def set(self, key: str, value: str, ttl: int | None = None) -> None:
        self._d[key] = ((time.time() + ttl) if ttl else 0.0, value)
        if len(self._d) > 50_000:  # crude bound
            for k in list(self._d)[:5_000]:
                self._d.pop(k, None)

    async def delete(self, key: str) -> None:
        self._d.pop(key, None)

    async def incr(self, key: str) -> int:
        v = int(await self.get(key) or 0) + 1
        await self.set(key, str(v))
        return v

    async def close(self) -> None:
        return None


class RedisKV:
    """All keys are namespaced `fios:` so a shared Redis can be cleared safely (`fios:*`)."""
    backend = "redis"
    PREFIX = "fios:"

    def __init__(self, client) -> None:
        self.r = client

    async def get(self, key: str) -> str | None:
        return await self.r.get(self.PREFIX + key)

    async def set(self, key: str, value: str, ttl: int | None = None) -> None:
        await self.r.set(self.PREFIX + key, value, ex=ttl)

    async def delete(self, key: str) -> None:
        await self.r.delete(self.PREFIX + key)

    async def incr(self, key: str) -> int:
        return int(await self.r.incr(self.PREFIX + key))

    async def clear_namespace(self, pattern: str = "*") -> int:
        n = 0
        async for k in self.r.scan_iter(match=self.PREFIX + pattern, count=500):
            await self.r.delete(k)
            n += 1
        return n

    async def close(self) -> None:
        await self.r.aclose()


async def create_kv(redis_url: str):
    if redis_url:
        try:
            import redis.asyncio as aioredis
            client = aioredis.from_url(redis_url, decode_responses=True, socket_connect_timeout=1.5)
            await client.ping()
            log.info("kv_backend", backend="redis")
            return RedisKV(client)
        except Exception as exc:  # noqa: BLE001
            log.warning("redis_unavailable_fallback_memory", error=str(exc))
    return MemoryKV()


class JsonKV:
    """Typed JSON helpers over any KV backend."""

    def __init__(self, kv) -> None:
        self.kv = kv

    async def get_json(self, key: str) -> Any | None:
        raw = await self.kv.get(key)
        return json.loads(raw) if raw else None

    async def set_json(self, key: str, value: Any, ttl: int | None = None) -> None:
        await self.kv.set(key, json.dumps(value, default=str), ttl)
