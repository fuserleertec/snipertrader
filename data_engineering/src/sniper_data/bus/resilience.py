"""Exponential backoff + retry helpers for Redis and Kafka reconnects."""

from __future__ import annotations

import asyncio
import logging
import random
from collections.abc import Awaitable, Callable
from typing import TypeVar

log = logging.getLogger(__name__)

T = TypeVar("T")


class Backoff:
    """Jittered exponential backoff. Call ``reset()`` after a successful op."""

    def __init__(
        self,
        base_s: float = 0.05,
        factor: float = 2.0,
        max_s: float = 8.0,
        jitter: float = 0.2,
    ) -> None:
        if base_s <= 0:
            raise ValueError("base_s must be > 0")
        self.base_s = float(base_s)
        self.factor = float(factor)
        self.max_s = float(max_s)
        self.jitter = float(jitter)
        self._delay = float(base_s)
        self.attempts = 0

    def next(self) -> float:
        self.attempts += 1
        delay = min(self._delay, self.max_s)
        self._delay = min(self._delay * self.factor, self.max_s)
        if self.jitter:
            delay = delay * (1.0 + random.uniform(-self.jitter, self.jitter))
        return max(0.0, delay)

    def reset(self) -> None:
        self._delay = self.base_s
        self.attempts = 0


async def retry_async(
    fn: Callable[[], Awaitable[T]],
    *,
    attempts: int = 5,
    backoff: Backoff | None = None,
    retry_on: tuple[type[BaseException], ...] = (Exception,),
    on_retry: Callable[[BaseException, int, float], None] | None = None,
    sleep: Callable[[float], Awaitable[None]] | None = None,
) -> T:
    """Run ``fn`` up to ``attempts`` times with backoff between failures."""
    clock = sleep or asyncio.sleep
    policy = backoff or Backoff()
    last: BaseException | None = None
    for i in range(1, max(1, attempts) + 1):
        try:
            result = await fn()
            policy.reset()
            return result
        except retry_on as exc:  # type: ignore[misc]
            last = exc
            if i >= attempts:
                break
            delay = policy.next()
            if on_retry is not None:
                on_retry(exc, i, delay)
            else:
                log.warning("retry %s/%s after %s (sleep %.3fs)", i, attempts, exc, delay)
            await clock(delay)
    assert last is not None
    raise last
