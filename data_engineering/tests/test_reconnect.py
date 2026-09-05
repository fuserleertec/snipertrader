from __future__ import annotations

import pytest

from sniper_data.bus.resilience import Backoff, retry_async
from sniper_data.metrics import KAFKA_ERRORS, REDIS_ERRORS, record_kafka_error, record_redis_error


def test_backoff_grows_and_resets():
    b = Backoff(base_s=0.1, factor=2.0, max_s=0.5, jitter=0.0)
    assert b.next() == pytest.approx(0.1)
    assert b.next() == pytest.approx(0.2)
    assert b.next() == pytest.approx(0.4)
    assert b.next() == pytest.approx(0.5)
    b.reset()
    assert b.next() == pytest.approx(0.1)


@pytest.mark.asyncio
async def test_retry_async_recovers_then_resets():
    hits = {"n": 0}

    async def flaky():
        hits["n"] += 1
        if hits["n"] < 3:
            raise ConnectionError("down")
        return "ok"

    sleeps: list[float] = []

    async def fake_sleep(s: float) -> None:
        sleeps.append(s)

    result = await retry_async(
        flaky,
        attempts=5,
        backoff=Backoff(base_s=0.01, factor=2.0, max_s=1.0, jitter=0.0),
        retry_on=(ConnectionError,),
        sleep=fake_sleep,
    )
    assert result == "ok"
    assert hits["n"] == 3
    assert sleeps == pytest.approx([0.01, 0.02])


@pytest.mark.asyncio
async def test_retry_async_exhausts():
    async def always():
        raise TimeoutError("nope")

    with pytest.raises(TimeoutError):
        await retry_async(
            always,
            attempts=2,
            backoff=Backoff(base_s=0.001, jitter=0.0),
            retry_on=(TimeoutError,),
            sleep=lambda _s: __import__("asyncio").sleep(0),
        )


def test_error_counters_increment():
    before_r = REDIS_ERRORS.labels("set")._value.get()
    before_k = KAFKA_ERRORS.labels("publish")._value.get()
    record_redis_error("set")
    record_kafka_error("publish")
    assert REDIS_ERRORS.labels("set")._value.get() == before_r + 1
    assert KAFKA_ERRORS.labels("publish")._value.get() == before_k + 1
