"""Setup 4 / 5 consume continuous 1m+5m DE bars — never dashboard snapshots."""

from __future__ import annotations

import pytest

from sniper_data.bus.redis_store import InMemoryStateStore
from sniper_data.bus.timescaledb import InMemoryOHLCVStore
from sniper_data.config import Settings
from sniper_data.models import Timeframe
from sniper_data.setup_detection.fixtures import (
    VWAP_SESSION,
    pullback_ob,
    setup4_fade_long_bars,
    setup4_vol_warmup,
    setup5_pullback_bars,
    setup5_rising_vwaps,
    setup5_trend_bars,
)
from sniper_data.setup_detection.ohlcv_source import (
    CONTINUOUS_TIMEFRAMES,
    FORBIDDEN_BAR_TOPICS,
    KAFKA_OHLCV_TOPIC,
    WS_OHLCV_PATH,
    assert_not_dashboard_source,
    clamp_continuous_timeframes,
    fetch_continuous_ohlcv,
    fetch_continuous_ohlcv_http,
    is_continuous_bar,
    is_dashboard_snapshot,
)
from sniper_data.setup_detection.orchestrator import SetupOrchestrator, subscribe_inmemory
from sniper_data.setup_detection.params import load_setup_params
from sniper_data.setup_detection.setup4 import SdExtensionFadeDetector
from sniper_data.setup_detection.setup5 import VwapPullbackContDetector
from sniper_data.zones import store_ob


DASHBOARD_SNAP = {
    "schema_version": "1.1",
    "symbol": "ES",
    "asset_class": "futures",
    "ts_ms": 1,
    "cadence_s": 900,
    "live_trading": False,
    "pointers": {
        "vwap": "vwap:ES:session",
        "session": "session:ES:rth",
        "avwap_latest": "avwap:ES:latest",
        "kill_zone": "kill_zone:ES",
        "volume_profile": "volume_profile:ES:rth",
    },
    "available": {
        "vwap": False,
        "session": False,
        "avwap": False,
        "kill_zone": False,
        "volume_profile": False,
    },
    "topic": "dashboard_snapshots",
}


def test_locked_sources_and_timeframes():
    assert CONTINUOUS_TIMEFRAMES == ("1m", "5m")
    assert KAFKA_OHLCV_TOPIC == "ohlcv_bars"
    assert WS_OHLCV_PATH == "/v1/ws/ohlcv"
    assert "dashboard_snapshots" in FORBIDDEN_BAR_TOPICS
    assert clamp_continuous_timeframes(("15m", "1h")) == ("1m", "5m")
    assert clamp_continuous_timeframes(("15m", "5m", "1m")) == ("5m", "1m")
    with pytest.raises(ValueError):
        assert_not_dashboard_source("dashboard_snapshots")
    assert is_dashboard_snapshot(DASHBOARD_SNAP) is True
    assert is_continuous_bar(DASHBOARD_SNAP) is False


def test_params_strip_15m_from_s4_s5():
    p = load_setup_params(Settings(SETUP4_TIMEFRAMES="1m,5m,15m", SETUP5_TIMEFRAMES="15m,5m"))
    assert p.s4_timeframes == ("1m", "5m")
    assert p.s5_timeframes == ("5m",)
    defaults = load_setup_params(Settings())
    assert defaults.s4_timeframes == ("1m", "5m")
    assert defaults.s5_timeframes == ("1m", "5m")


@pytest.mark.asyncio
async def test_s4_s5_ignore_15m_and_dashboard_payloads():
    store = InMemoryStateStore()
    s4 = SdExtensionFadeDetector(store)
    s5 = VwapPullbackContDetector(store)
    s4.on_vwap(VWAP_SESSION)
    s5.on_vwap(VWAP_SESSION)

    fifteen = setup4_vol_warmup(5, timeframe=Timeframe.M15)[-1]
    assert await s4.on_bar(fifteen) == []
    assert await s5.on_bar(fifteen) == []
    assert not s4._state
    assert not s5._state


@pytest.mark.asyncio
async def test_s4_and_s5_accept_1m_and_5m():
    store = InMemoryStateStore()
    await store.set("vwap:BTCUSDT:session", VWAP_SESSION.model_dump(mode="json"))
    await store_ob(store, pullback_ob())

    for tf in (Timeframe.M1, Timeframe.M5):
        fade = SdExtensionFadeDetector(store)
        fade.on_vwap(VWAP_SESSION)
        for b in setup4_vol_warmup(timeframe=tf):
            await fade.on_bar(b)
        out4 = []
        for b in setup4_fade_long_bars(timeframe=tf):
            out4.extend(await fade.on_bar(b))
        assert out4, f"setup4 should fire on {tf.value}"
        assert out4[0].timeframe == tf.value

        pull = VwapPullbackContDetector(store)
        pull.on_vwap(VWAP_SESSION)
        trend = setup5_trend_bars(timeframe=tf)
        for snap, b in zip(setup5_rising_vwaps(len(trend)), trend, strict=True):
            pull.on_vwap(snap)
            await pull.on_bar(b)
        out5 = []
        for b in setup5_pullback_bars(start=len(trend), timeframe=tf):
            out5.extend(await pull.on_bar(b))
        assert out5, f"setup5 should fire on {tf.value}"
        assert out5[0].timeframe == tf.value


@pytest.mark.asyncio
async def test_fetch_continuous_ohlcv_store_and_http_reject_15m():
    bars = InMemoryOHLCVStore()
    for b in setup4_vol_warmup(3, timeframe=Timeframe.M1):
        await bars.upsert(b)
    for b in setup4_vol_warmup(2, timeframe=Timeframe.M15):
        await bars.upsert(b)
    got = await fetch_continuous_ohlcv(bars, "BTCUSDT", "1m")
    assert got and all(is_continuous_bar(b) for b in got)
    with pytest.raises(ValueError, match="1m or 5m"):
        await fetch_continuous_ohlcv(bars, "BTCUSDT", "15m")

    import httpx

    def handler(request: httpx.Request) -> httpx.Response:
        assert "/v1/ohlcv/ES" in str(request.url)
        assert "timeframe=5m" in str(request.url)
        assert "dashboard" not in str(request.url)
        return httpx.Response(
            200,
            json={
                "symbol": "ES",
                "timeframe": "5m",
                "bars": [setup4_vol_warmup(1, timeframe=Timeframe.M5)[0].model_dump(mode="json")],
            },
        )

    rows = await fetch_continuous_ohlcv_http(
        "http://de.example",
        "ES",
        "5m",
        transport=httpx.MockTransport(handler),
    )
    assert len(rows) == 1
    assert rows[0].timeframe == Timeframe.M5
    with pytest.raises(ValueError):
        await fetch_continuous_ohlcv_http("http://de.example", "ES", "15m")


@pytest.mark.asyncio
async def test_orchestrator_hydrates_1m_5m_not_dashboard():
    store = InMemoryStateStore()
    bars = InMemoryOHLCVStore()
    for b in setup4_vol_warmup(4, timeframe=Timeframe.M1):
        await bars.upsert(b)
    for b in setup4_vol_warmup(4, timeframe=Timeframe.M15):
        await bars.upsert(b)
    from sniper_data.bus.kafka import InMemoryBus
    from sniper_data.setup_detection.risk_client import StaticRiskClient

    orch = SetupOrchestrator(store, InMemoryBus(), StaticRiskClient(approved=True))
    n = await orch.hydrate_continuous_ohlcv(bars, ["BTCUSDT"])
    assert n == 4
    keyed = list(orch.setup4._state)
    assert all(tf == "1m" for _, tf in keyed)


@pytest.mark.asyncio
async def test_subscribe_skips_dashboard_snapshots():
    from sniper_data.bus.kafka import InMemoryBus
    from sniper_data.setup_detection.risk_client import StaticRiskClient

    bus = InMemoryBus()
    store = InMemoryStateStore()
    orch = SetupOrchestrator(store, bus, StaticRiskClient(approved=True))
    subscribe_inmemory(bus, orch)
    assert "ohlcv_bars" in bus._subs
    assert "dashboard_snapshots" not in bus._subs
    await bus.publish("ohlcv_bars", DASHBOARD_SNAP, key="ES")
    # Must not crash / must not treat snapshot as a bar.
    assert not orch.setup4._state
