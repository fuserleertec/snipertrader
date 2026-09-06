from __future__ import annotations

from fastapi.testclient import TestClient

from sniper_data.api import create_app
from sniper_data.bus.kafka import InMemoryBus
from sniper_data.bus.redis_store import InMemoryStateStore
from sniper_data.config import Settings
from sniper_data.models import SetupSignal
from sniper_data.patterns import fixtures_for, seed_patterns
from sniper_data.setups import SETUP_KEYS
from sniper_data.universe import parse_universe


FUTURES = ["ES", "CL", "GC", "NQ"]


def test_fixtures_emit_trigger_ids_for_futures_roots():
    for symbol in FUTURES + ["BTCUSDT", "AAPL"]:
        bundle = fixtures_for(symbol, now_ms=1_717_502_400_000)
        assert bundle["sweep"].symbol == symbol
        assert bundle["fvg"].symbol == symbol
        signals: list[SetupSignal] = bundle["signals"]
        types = {s.setup_type for s in signals}
        assert SETUP_KEYS[0] in types
        assert SETUP_KEYS[1] in types
        assert SETUP_KEYS[4] in types  # pullback
        for sig in signals:
            assert sig.trigger_event_ids
            assert bundle["sweep"].id in sig.trigger_event_ids or bundle["fvg"].id in sig.trigger_event_ids


async def test_seed_patterns_writes_every_configured_symbol():
    store = InMemoryStateStore()
    bus = InMemoryBus()
    symbols = parse_universe("BTCUSDT,ETHUSDT,AAPL,MSFT,ES,NQ,CL,GC,SPY,NVDA")
    stats = await seed_patterns(store, symbols, bus=bus, now_ms=1_717_502_400_000)
    assert stats["symbols"] == len(symbols)
    for symbol in symbols:
        assert await store.get(f"sweep:{symbol}:sw-{symbol}-1") is not None
        assert await store.get(f"fvg:{symbol}:fvg-{symbol}-1") is not None
        assert await store.get(f"mss:{symbol}:mss-{symbol}-1") is not None
        assert await store.get(f"ob:{symbol}:ob-{symbol}-1") is not None
        ids = await store.get(f"setup:index:{symbol}")
        assert len(ids) == 3
        pull = await store.get(f"setup:{symbol}:sig-{symbol}-pullback")
        assert pull["setup_type"] == SETUP_KEYS[4]
        assert "sw-" in "".join(pull["trigger_event_ids"])
    assert bus.topics["setup_signals"]
    assert {r["value"]["symbol"] for r in bus.topics["setup_signals"]} == set(symbols)


def test_signals_http_lists_up_to_twenty_symbols():
    store = InMemoryStateStore()
    settings = Settings(USE_INMEMORY=True, DASHBOARD_SYMBOLS=",".join(FUTURES + ["AAPL", "BTCUSDT"]))
    import asyncio

    asyncio.run(seed_patterns(store, settings.symbols, now_ms=1_717_502_400_000))
    http = TestClient(create_app(store=store, settings=settings))
    all_rows = http.get("/v1/signals?limit=50").json()
    assert all_rows["live_trading"] is False
    assert set(all_rows["symbols"]) == set(settings.symbols)
    assert all_rows["count"] >= 3 * len(settings.symbols)
    one = http.get("/v1/signals?symbol=ES").json()
    assert one["symbols"] == ["ES"]
    assert all(row["symbol"] == "ES" for row in one["signals"])
    many = http.get("/v1/signals?symbols=ES,CL,GC,NQ&limit=40").json()
    assert set(many["symbols"]) == set(FUTURES)
