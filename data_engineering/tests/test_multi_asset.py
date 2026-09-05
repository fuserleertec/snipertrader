from __future__ import annotations

from datetime import datetime, timezone

import pytest

from sniper_data.bus.kafka import InMemoryBus
from sniper_data.bus.redis_store import InMemoryStateStore
from sniper_data.bus.timescaledb import InMemoryOHLCVStore
from sniper_data.connectors.futures import FuturesConnector
from sniper_data.connectors.mock import MockConnector
from sniper_data.connectors.base import ConnectorNotConfigured
from sniper_data.models import AssetClass
from sniper_data.pipeline import Runtime
from sniper_data.symbols import infer_asset_class, normalize_symbol, normalize_tick


def test_futures_dated_contract_normalization():
    assert normalize_symbol("es-z-2024") == "ESZ2024"
    assert infer_asset_class("ES") is AssetClass.FUTURES
    assert infer_asset_class("ESZ2024") is AssetClass.FUTURES
    assert infer_asset_class("ESZ24") is AssetClass.FUTURES
    assert infer_asset_class("NQH2025") is AssetClass.FUTURES
    assert infer_asset_class("AAPL") is AssetClass.EQUITY
    assert infer_asset_class("BTCUSDT") is AssetClass.CRYPTO


@pytest.mark.asyncio
async def test_mock_emits_crypto_equity_and_futures():
    conn = MockConnector(symbols=["BTCUSDT", "AAPL", "ES"], interval_ms=1, seed=3)
    seen: dict[str, AssetClass] = {}
    n = 0
    async for tick in conn.stream():
        seen[tick.symbol] = tick.asset_class
        n += 1
        if n >= 6:
            break
    await conn.close()
    assert seen["BTCUSDT"] is AssetClass.CRYPTO
    assert seen["AAPL"] is AssetClass.EQUITY
    assert seen["ES"] is AssetClass.FUTURES


@pytest.mark.asyncio
async def test_pipeline_multi_asset_end_to_end():
    """Crypto + equity + futures ticks share Phase 1 topics, differentiated by asset_class."""
    bus = InMemoryBus()
    store = InMemoryStateStore()
    rt = Runtime(inmemory=True, bus=bus, store=store, bars=InMemoryOHLCVStore())
    await rt.start()
    # 2024-06-04 14:00 UTC: crypto NY AM, AAPL/ES RTH
    t0 = int(datetime(2024, 6, 4, 14, 0, tzinfo=timezone.utc).timestamp() * 1000)
    universe = (
        ("BTCUSDT", 65000.0, AssetClass.CRYPTO),
        ("AAPL", 228.4, AssetClass.EQUITY),
        ("ES", 5812.25, AssetClass.FUTURES),
    )
    for i, (sym, px, _klass) in enumerate(universe):
        await rt.handle_tick(
            normalize_tick(symbol=sym, price=px, volume=10.0, ts=t0 + i * 1000)
        )
        await rt.handle_tick(
            normalize_tick(symbol=sym, price=px + 1, volume=5.0, ts=t0 + i * 1000 + 10)
        )
    await rt.stop()

    ticks = [rec["value"] for rec in bus.topics["raw_ticks"]]
    classes = {t["symbol"]: t["asset_class"] for t in ticks}
    assert classes == {"BTCUSDT": "crypto", "AAPL": "equity", "ES": "futures"}
    assert rt.ticks_by_class["crypto"] >= 2
    assert rt.ticks_by_class["equity"] >= 2
    assert rt.ticks_by_class["futures"] >= 2

    assert await store.get("vwap:BTCUSDT:weekly") is not None
    assert await store.get("vwap:AAPL:weekly") is not None
    assert await store.get("vwap:ES:weekly") is not None

    btc_vp = await store.get("volume_profile:BTCUSDT:ny_am")
    assert btc_vp is not None
    assert btc_vp["session_type"] == "ny_am"
    assert btc_vp["poc"] is not None
    aapl_vp = await store.get("volume_profile:AAPL:rth")
    assert aapl_vp["session_type"] == "rth"
    es_vp = await store.get("volume_profile:ES:rth")
    assert es_vp["session_type"] == "rth"


@pytest.mark.asyncio
async def test_futures_stub_refuses_live_stream():
    fut = FuturesConnector(symbols=["ESZ2024"])
    parsed = fut.parse_trade(
        {"symbol": "es-z-2024", "price": 5800, "volume": 2, "ts_ms": 1_717_500_000_000}
    )
    assert parsed.symbol == "ESZ2024"
    assert parsed.asset_class is AssetClass.FUTURES
    with pytest.raises(ConnectorNotConfigured):
        await anext(fut.stream())
