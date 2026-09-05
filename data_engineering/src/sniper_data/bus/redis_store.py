from __future__ import annotations

import json
import logging
from typing import Any, Protocol

from pydantic import BaseModel

from sniper_data.config import FVG_TTL_MAX_SECONDS

log = logging.getLogger(__name__)

ZONE_KEY_PREFIXES = ("fvg:", "sweep:")


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

    async def close(self) -> None:
        return None


class RedisStateStore:
    def __init__(self, url: str) -> None:
        import redis.asyncio as redis

        self._client = redis.from_url(url, decode_responses=True)

    async def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        payload = encode(value)
        if key.startswith(ZONE_KEY_PREFIXES):
            if ttl is None:
                raise ValueError(f"zone key {key} must be written with a TTL")
            ttl = max(1, min(int(ttl), FVG_TTL_MAX_SECONDS))
            await self._client.set(key, payload, ex=ttl)
            return
        if ttl is None:
            await self._client.set(key, payload)
        else:
            await self._client.set(key, payload, ex=int(ttl))

    async def get(self, key: str) -> Any:
        return decode(await self._client.get(key))

    async def expire(self, key: str, ttl: int) -> bool:
        return bool(await self._client.expire(key, int(ttl)))

    async def ttl(self, key: str) -> int:
        return int(await self._client.ttl(key))

    async def delete(self, key: str) -> None:
        await self._client.delete(key)

    async def scan(self, match: str) -> list[str]:
        keys: list[str] = []
        async for key in self._client.scan_iter(match=match, count=200):
            keys.append(key)
        return keys

    async def publish(self, channel: str, value: Any) -> None:
        await self._client.publish(channel, encode(value))

    async def ping(self) -> bool:
        return bool(await self._client.ping())

    async def close(self) -> None:
        await self._client.aclose()
