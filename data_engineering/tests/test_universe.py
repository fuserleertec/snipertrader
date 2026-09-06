from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from sniper_data.api import create_app
from sniper_data.bus.redis_store import InMemoryStateStore
from sniper_data.config import Settings
from sniper_data.models import AssetClass
from sniper_data.symbols import infer_asset_class
from sniper_data.universe import (
    DEFAULT_UNIVERSE_CSV,
    MAX_UNIVERSE_SYMBOLS,
    REDIS_UNIVERSE_ACTIVE,
    clamp_top_limit,
    parse_universe,
    rank_rows,
    slice_active,
    top_envelope,
    write_universe_active,
)


FUTURES_REQUIRED = {"ES", "CL", "GC", "NQ"}


def test_default_universe_is_mixed_and_at_least_ten():
    symbols = parse_universe("")
    assert symbols == parse_universe(DEFAULT_UNIVERSE_CSV)
    assert len(symbols) >= 10
    assert len(symbols) <= MAX_UNIVERSE_SYMBOLS
    classes = {infer_asset_class(s) for s in symbols}
    assert classes == {AssetClass.CRYPTO, AssetClass.EQUITY, AssetClass.FUTURES}
    assert FUTURES_REQUIRED <= set(symbols)


def test_dashboard_symbols_beats_universe_and_demo():
    assert parse_universe("ES,CL", "AAPL", "BTCUSDT") == ["ES", "CL"]
    settings = Settings(
        DASHBOARD_SYMBOLS="ES,NQ,CL,GC,AAPL",
        UNIVERSE="BTCUSDT",
        DEMO_SYMBOLS="MSFT",
        LIVE_TRADING=True,
    )
    assert settings.symbols == ["ES", "NQ", "CL", "GC", "AAPL"]
    assert settings.live_trading is False


def test_universe_cap_twenty():
    raw = ",".join(f"SYM{i:02d}" for i in range(25))
    assert len(parse_universe(raw)) == 20
    with pytest.raises(ValueError):
        clamp_top_limit(0)
    with pytest.raises(ValueError):
        clamp_top_limit(21)
    assert clamp_top_limit(10) == 10
    assert clamp_top_limit(20) == 20


def test_ranking_orders_by_score_inputs():
    rows = [
        {
            "symbol": "AAPL",
            "asset_class": "equity",
            "volume": 10,
            "volatility": 0.001,
            "session_active": False,
            "levels_available": 1,
            "pattern_count": 0,
        },
        {
            "symbol": "ES",
            "asset_class": "futures",
            "volume": 9_000,
            "volatility": 0.04,
            "session_active": True,
            "levels_available": 5,
            "pattern_count": 8,
        },
    ]
    ranked = rank_rows(rows, limit=10)
    assert ranked[0].symbol == "ES"
    assert ranked[0].rank == 1
    assert ranked[0].asset_class is AssetClass.FUTURES
    env = top_envelope(rows, limit=10, now_ms=1)
    dumped = env.model_dump(mode="json")
    assert dumped["live_trading"] is False
    assert dumped["limit"] == 10
    assert dumped["score_inputs"] == [
        "volume",
        "volatility",
        "session_active",
        "levels_available",
        "pattern_count",
    ]


@pytest.mark.asyncio
async def test_universe_top_http_is_locked_contract():
    store = InMemoryStateStore()
    settings = Settings(
        USE_INMEMORY=True,
        DASHBOARD_SYMBOLS="BTCUSDT,ETHUSDT,AAPL,MSFT,NVDA,SPY,ES,NQ,CL,GC,SOLUSDT,BNBUSDT",
        LIVE_TRADING=False,
    )
    env = top_envelope(
        [
            {
                "symbol": s,
                "asset_class": infer_asset_class(s).value,
                "volume": 100 + i * 10,
                "volatility": 0.01,
                "session_active": True,
                "levels_available": 4,
                "pattern_count": 3,
            }
            for i, s in enumerate(settings.symbols)
        ],
        limit=20,
        now_ms=1_700_000_000_000,
    )
    await write_universe_active(store, env)
    raw = await store.get(REDIS_UNIVERSE_ACTIVE)
    assert raw["live_trading"] is False
    assert len(raw["symbols"]) == 12

    app = create_app(store=store, settings=settings)
    http = TestClient(app)
    top10 = http.get("/v1/universe/top?limit=10")
    assert top10.status_code == 200
    body = top10.json()
    assert set(body) >= {"as_of_ts_ms", "limit", "symbols", "live_trading"}
    assert body["limit"] == 10
    assert body["live_trading"] is False
    assert len(body["symbols"]) == 10
    assert body["symbols"][0]["rank"] == 1
    for row in body["symbols"]:
        assert set(row) >= {"symbol", "asset_class", "rank", "score"}

    top20 = http.get("/v1/universe/top?limit=20").json()
    assert top20["limit"] == 20
    assert len(top20["symbols"]) == 12
    assert http.get("/v1/universe/top?limit=21").status_code == 400
    helper = http.get("/v1/universe").json()
    assert helper["live_trading"] is False
    assert "ES" in helper["symbols"]
    assert helper.get("contract") == "/v1/universe/top"
    health = http.get("/health").json()
    assert health["live_trading"] is False
    assert health["universe_contract"] == "/v1/universe/top"


def test_slice_active_re_ranks_prefix():
    payload = {
        "as_of_ts_ms": 9,
        "limit": 20,
        "live_trading": False,
        "score_inputs": ["volume"],
        "symbols": [
            {"symbol": "ES", "rank": 1, "score": 1.0, "asset_class": "futures"},
            {"symbol": "CL", "rank": 2, "score": 0.9, "asset_class": "futures"},
            {"symbol": "GC", "rank": 3, "score": 0.8, "asset_class": "futures"},
        ],
    }
    sliced = slice_active(payload, 2)
    assert sliced["limit"] == 2
    assert [r["symbol"] for r in sliced["symbols"]] == ["ES", "CL"]
    assert sliced["live_trading"] is False
