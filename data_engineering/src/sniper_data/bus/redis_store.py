from __future__ import annotations

import json
import logging
from typing import Any, Protocol

from pydantic import BaseModel

from sniper_data.bus.resilience import Backoff, retry_async
from sniper_data.config import FVG_TTL_MAX_SECONDS
from sniper_data.metrics import record_redis_error, set_redis_memory_bytes

log = logging.getLogger(__name__)

ZONE_KEY_PREFIXES = ("fvg:", "sweep:", "mss:", "ob:")


def encode(value: Any) -> str:
    if isinstance(value, BaseModel):
        return value.model_dump_json()
    if isinstance(value, (dict, list)):
        return json.dumps(value)
    return str(value)


def decode(raw: str | bytes | None) -> Any:
    if raw is None:
        return None
    if isinstance(raw, bytes):
        raw = raw.decode()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return raw


class StateStore(Protocol):
    async def set(self, key: str, value: Any, ttl: int | None = None) -> None: ...
    async def get(self, key: str) -> Any: ...
    async def expire(self, key: str, ttl: int) -> bool: ...
    async def ttl(self, key: str) -> int: ...
    async def delete(self, key: str) -> None: ...
    async def scan(self, match: str) -> list[str]: ...
    async def publish(self, channel: str, value: Any) -> None: ...
    async def ping(self) -> bool: ...
    async def close(self) -> None: ...


class InMemoryStateStore:
    def __init__(self) -> None:
        self.data: dict[str, str] = {}
        self.ttls: dict[str, int] = {}
        self.channels: dict[str, list[Any]] = {}

    async def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        if key.startswith(ZONE_KEY_PREFIXES) and ttl is None:
            raise ValueError(f"zone key {key} must be written with a TTL")
        self.data[key] = encode(value)
        if ttl is not None:
            if key.startswith(ZONE_KEY_PREFIXES):
                ttl = max(1, min(int(ttl), FVG_TTL_MAX_SECONDS))
            self.ttls[key] = int(ttl)
        else:
            self.ttls.pop(key, None)

    async def get(self, key: str) -> Any:
        return decode(self.data.get(key))

    async def expire(self, key: str, ttl: int) -> bool:
        if key not in self.data:
            return False
        self.ttls[key] = int(ttl)
        return True

    async def ttl(self, key: str) -> int:
        if key not in self.data:
            return -2
        return self.ttls.get(key, -1)

    async def delete(self, key: str) -> None:
        self.data.pop(key, None)
        self.ttls.pop(key, None)

    async def scan(self, match: str) -> list[str]:
        prefix = match.rstrip("*")
        return [k for k in self.data if k.startswith(prefix)]

    async def publish(self, channel: str, value: Any) -> None:
        self.channels.setdefault(channel, []).append(
            json.loads(encode(value)) if not isinstance(value, str) else value
        )

    async def ping(self) -> bool:
        return True

    async def info_memory(self) -> int:
        return sum(len(k) + len(v) for k, v in self.data.items())

    async def close(self) -> None:
        return None


class RedisStateStore:
    """Pooled Redis client with retry/backoff. Shared state for stateless workers."""

    def __init__(
        self,
        url: str,
        *,
        max_connections: int = 32,
        retries: int = 4,
    ) -> None:
        import redis.asyncio as redis

        self._url = url
        self._retries = max(1, int(retries))
        self._pool = redis.ConnectionPool.from_url(
            url,
            decode_responses=True,
            max_connections=max(1, int(max_connections)),
            socket_timeout=5.0,
            socket_connect_timeout=5.0,
            retry_on_timeout=True,
            health_check_interval=30,
        )
        self._client = redis.Redis(connection_pool=self._pool)

    async def _call(self, op: str, fn):
        def _on_retry(exc: BaseException, attempt: int, delay: float) -> None:
            record_redis_error(op)
            log.warning("redis %s retry %s after %s (sleep %.3fs)", op, attempt, exc, delay)

        return await retry_async(
            fn,
            attempts=self._retries,
            backoff=Backoff(base_s=0.05, max_s=2.0),
            on_retry=_on_retry,
        )

    async def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        payload = encode(value)

        async def _once() -> None:
            if key.startswith(ZONE_KEY_PREFIXES):
                if ttl is None:
                    raise ValueError(f"zone key {key} must be written with a TTL")
                clamped = max(1, min(int(ttl), FVG_TTL_MAX_SECONDS))
                await self._client.set(key, payload, ex=clamped)
                return
            if ttl is None:
                await self._client.set(key, payload)
            else:
                await self._client.set(key, payload, ex=int(ttl))

        await self._call("set", _once)

    async def get(self, key: str) -> Any:
        async def _once() -> Any:
            return decode(await self._client.get(key))

        return await self._call("get", _once)

    async def expire(self, key: str, ttl: int) -> bool:
        async def _once() -> bool:
            return bool(await self._client.expire(key, int(ttl)))

        return await self._call("expire", _once)

    async def ttl(self, key: str) -> int:
        async def _once() -> int:
            return int(await self._client.ttl(key))

        return await self._call("ttl", _once)

    async def delete(self, key: str) -> None:
        async def _once() -> None:
            await self._client.delete(key)

        await self._call("delete", _once)

    async def scan(self, match: str) -> list[str]:
        async def _once() -> list[str]:
            keys: list[str] = []
            async for key in self._client.scan_iter(match=match, count=200):
                keys.append(key)
            return keys

        return await self._call("scan", _once)

    async def publish(self, channel: str, value: Any) -> None:
        async def _once() -> None:
            await self._client.publish(channel, encode(value))

        await self._call("publish", _once)

    async def ping(self) -> bool:
        async def _once() -> bool:
            return bool(await self._client.ping())

        try:
            return await self._call("ping", _once)
        except Exception as exc:  # noqa: BLE001
            record_redis_error("ping")
            log.warning("redis ping failed: %s", exc)
            return False

    async def info_memory(self) -> int:
        async def _once() -> int:
            info = await self._client.info("memory")
            used = int(info.get("used_memory") or 0)
            set_redis_memory_bytes(used)
            return used

        try:
            return await self._call("info", _once)
        except Exception as exc:  # noqa: BLE001
            record_redis_error("info")
            log.warning("redis INFO memory failed: %s", exc)
            return 0

    async def close(self) -> None:
        await self._client.aclose()
        await self._pool.aclose()
