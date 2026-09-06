from __future__ import annotations

from fastapi.testclient import TestClient

from sniper_data.api import create_app
from sniper_data.bus.redis_store import InMemoryStateStore
from sniper_data.bus.timescaledb import InMemoryOHLCVStore
from sniper_data.config import Settings
from sniper_data.history import generate_history, seed_ohlcv_history
from sniper_data.models import Timeframe
from sniper_data.universe import DEFAULT_UNIVERSE_CSV, parse_universe


def test_generate_history_is_deterministic():
    a = generate_history("ES", Timeframe.M15, 24, now_ms=1_717_502_400_000, seed=7)
    b = generate_history("ES", "15m", 24, now_ms=1_717_502_400_000, seed=7)
    assert len(a) == 24
    assert [x.close for x in a] == [x.close for x in b]
    assert a[0].symbol == "ES"
    assert a[0].asset_class.value == "futures"


async def test_seed_covers_mixed_universe():
    store = InMemoryOHLCVStore()
    symbols = parse_universe(DEFAULT_UNIVERSE_CSV)
    stats = await seed_ohlcv_history(store, symbols, now_ms=1_717_502_400_000)
    assert stats["symbols"] == len(symbols)
    for symbol in ("BTCUSDT", "AAPL", "ES", "CL", "GC", "NQ"):
        for tf in ("1m", "5m", "15m", "1h", "4h"):
            rows = await store.fetch(symbol, tf, limit=200)
            assert len(rows) >= 24, (symbol, tf)


def test_ohlcv_http_returns_bars_for_futures_and_equities():
    store = InMemoryStateStore()
    bars = InMemoryOHLCVStore()
    settings = Settings(USE_INMEMORY=True, DASHBOARD_SYMBOLS="ES,CL,GC,NQ,AAPL,BTCUSDT")
    import asyncio

    asyncio.run(seed_ohlcv_history(bars, settings.symbols, now_ms=1_717_502_400_000))
    http = TestClient(create_app(store=store, settings=settings, bars=bars))
    for symbol in settings.symbols:
        body = http.get(f"/v1/ohlcv/{symbol}?timeframe=15m&limit=50").json()
        assert body["symbol"] == symbol
        assert len(body["bars"]) >= 24
        assert body["bars"][0]["asset_class"] in {"crypto", "equity", "futures"}
