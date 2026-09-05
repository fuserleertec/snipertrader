from __future__ import annotations

from datetime import datetime, timezone

import pytest

from sniper_data.bus.kafka import InMemoryBus
from sniper_data.bus.redis_store import InMemoryStateStore
from sniper_data.bus.timescaledb import InMemoryOHLCVStore
from sniper_data.connectors.binance import BinanceConnector
from sniper_data.connectors.mock import MockConnector
from sniper_data.connectors.us_equities import USEquitiesConnector
from sniper_data.connectors.base import ConnectorNotConfigured
from sniper_data.models import AssetClass, Timeframe
from sniper_data.ohlcv import OHLCVAggregator
from sniper_data.pipeline import Runtime
from sniper_data.symbols import normalize_tick


@pytest.mark.asyncio
async def test_mock_tick_to_ohlcv_session_vwap():
    bus = InMemoryBus()
    store = InMemoryStateStore()
    bars = InMemoryOHLCVStore()
    rt = Runtime(inmemory=True, bus=bus, store=store, bars=bars)
    await rt.start()
    ts = int(datetime(2024, 6, 4, 10, 0, tzinfo=timezone.utc).timestamp() * 1000)
    for i, (px, vol) in enumerate([(100.0, 10.0), (102.0, 20.0), (98.0, 30.0)]):
        tick = normalize_tick(
            symbol="BTCUSDT",
            price=px,
            volume=vol,
            ts=ts + i * 1000,
            bid=px - 0.5,
            ask=px + 0.5,
        )
        await rt.handle_tick(tick)
    assert rt.ticks_processed == 3
    assert bus.latest("raw_ticks")["symbol"] == "BTCUSDT"
    vwap = await store.get("vwap:BTCUSDT:session")
    assert vwap is not None
    assert vwap["vwap"] == pytest.approx(5980 / 60)
    sess = await store.get("session:BTCUSDT:london")
    assert sess["open"] == 100.0
    assert sess["high"] == 102.0
    assert sess["low"] == 98.0
    await rt.stop()


@pytest.mark.asyncio
async def test_mock_connector_emits_normalized_book():
    conn = MockConnector(symbols=["btc-usdt"], interval_ms=1, seed=1)
    tick = await conn.snapshot("btc-usdt")
    assert tick.symbol == "BTCUSDT"
    assert tick.asset_class is AssetClass.CRYPTO
    assert tick.book is not None
    assert len(tick.book.bids) == 5
    assert tick.ts_ms > 1_000_000_000_000
    await conn.close()


@pytest.mark.asyncio
async def test_binance_and_equity_stubs():
    bn = BinanceConnector()
    with pytest.raises(ConnectorNotConfigured):
        await anext(bn.stream())
    parsed = bn.parse_trade({"s": "btc-usdt", "p": "100", "q": "2", "T": 1_717_500_000_000})
    assert parsed.symbol == "BTCUSDT"
    assert parsed.ts_ms == 1_717_500_000_000

    eq = USEquitiesConnector()
    with pytest.raises(ConnectorNotConfigured):
        await anext(eq.stream())


@pytest.mark.asyncio
async def test_multi_timeframe_flush():
    agg = OHLCVAggregator()
    t0 = int(datetime(2024, 6, 4, 12, 0, tzinfo=timezone.utc).timestamp() * 1000)
    agg.on_tick(normalize_tick(symbol="ES", price=5000, volume=1, ts=t0))
    flushed = agg.flush()
    tfs = {b.timeframe for b in flushed}
    assert tfs == {Timeframe.M1, Timeframe.M5, Timeframe.M15, Timeframe.H1, Timeframe.H4}
