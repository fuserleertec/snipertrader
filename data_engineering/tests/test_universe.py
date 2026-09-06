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
    REDIS_UNIVERSE_TOP,
    clamp_top_limit,
    parse_universe,
    rank_rows,
    slice_top,
    top_envelope,
    write_universe_active,
    write_universe_top,
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
        clamp_top_limit(1)
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
    assert set(dumped) == {"as_of_ts_ms", "limit", "symbols"}
    assert dumped["limit"] == 10
    assert set(dumped["symbols"][0]) == {"symbol", "asset_class", "rank", "score"}


@pytest.mark.asyncio
async def test_universe_top_http_is_locked_contract():
    store = InMemoryStateStore()
    settings = Settings(
        USE_INMEMORY=True,
        DASHBOARD_SYMBOLS="BTCUSDT,ETHUSDT,AAPL,MSFT,NVDA,SPY,ES,NQ,CL,GC,SOLUSDT,BNBUSDT",
        LIVE_TRADING=False,
    )
    await write_universe_active(store, settings.symbols, now_ms=1_700_000_000_000)
    raw = await store.get(REDIS_UNIVERSE_ACTIVE)
    assert raw["as_of_ts_ms"] == 1_700_000_000_000
    assert raw["live_trading"] is False
    assert {row["symbol"] for row in raw["symbols"]} == set(settings.symbols)
    assert all(set(row) == {"symbol", "asset_class"} for row in raw["symbols"])
    assert {"ES", "CL", "GC", "NQ"} <= {row["symbol"] for row in raw["symbols"]}

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
    await write_universe_top(store, env)
    ranked = await store.get(REDIS_UNIVERSE_TOP)
    assert ranked["limit"] == 20
    assert len(ranked["symbols"]) == 12

    app = create_app(store=store, settings=settings)
    http = TestClient(app)
    full = http.get("/v1/universe")
    assert full.status_code == 200
    listed = full.json()
    assert set(listed) >= {"as_of_ts_ms", "symbols"}
    assert [row["symbol"] for row in listed["symbols"]] == settings.symbols
    assert all("asset_class" in row for row in listed["symbols"])

    top10 = http.get("/v1/universe/top?limit=10")
    assert top10.status_code == 200
    body = top10.json()
    assert set(body) == {"as_of_ts_ms", "limit", "symbols"}
    assert body["limit"] == 10
    assert len(body["symbols"]) == 10
    assert body["symbols"][0]["rank"] == 1
    for row in body["symbols"]:
        assert set(row) == {"symbol", "asset_class", "rank", "score"}

    top20 = http.get("/v1/universe/top?limit=20").json()
    assert set(top20) == {"as_of_ts_ms", "limit", "symbols"}
    assert top20["limit"] == 20
    assert len(top20["symbols"]) == 12
    assert http.get("/v1/universe/top?limit=21").status_code == 400
    assert http.get("/v1/universe/top?limit=1").status_code == 400
    health = http.get("/health").json()
    assert health["live_trading"] is False
    assert health["universe_contract"] == "/v1/universe"
    assert health["universe_redis"] == "universe:active"


def test_slice_top_re_ranks_prefix():
    payload = {
        "as_of_ts_ms": 9,
        "limit": 20,
        "symbols": [
            {"symbol": "ES", "rank": 1, "score": 1.0, "asset_class": "futures", "volume": 99},
            {"symbol": "CL", "rank": 2, "score": 0.9, "asset_class": "futures"},
        ]
        + [
            {"symbol": f"X{i}", "rank": i + 2, "score": 0.1, "asset_class": "crypto"}
            for i in range(10)
        ],
    }
    sliced = slice_top(payload, 10)
    assert set(sliced) == {"as_of_ts_ms", "limit", "symbols"}
    assert sliced["limit"] == 10
    assert [r["symbol"] for r in sliced["symbols"][:2]] == ["ES", "CL"]
    assert set(sliced["symbols"][0]) == {"symbol", "asset_class", "rank", "score"}


def _top_wire(symbols: list[str], *, limit: int = 20, as_of: int = 42) -> dict:
    return {
        "as_of_ts_ms": as_of,
        "limit": limit,
        "symbols": [
            {"symbol": s, "asset_class": infer_asset_class(s).value, "rank": i + 1, "score": 1.0 - i * 0.01}
            for i, s in enumerate(symbols)
        ],
    }


def test_symbols_from_payload_reads_frozen_object_rows():
    from sniper_data.universe import symbols_from_payload

    names, as_of, members = symbols_from_payload(_top_wire(["ES", "CL", "GC", "NQ"], limit=10))
    assert names == ["ES", "CL", "GC", "NQ"]
    assert as_of == 42
    assert members[0]["symbol"] == "ES"
    assert members[0]["asset_class"] == "futures"
    assert members[0]["rank"] == 1


@pytest.mark.asyncio
async def test_scan_uses_http_top_object_rows_not_setup_universe(monkeypatch):
    """SWAP: SETUP_UNIVERSE must not win when GET /v1/universe/top is up."""
    import httpx

    from sniper_data.universe import (
        EnvUniverseProvider,
        FallbackUniverseProvider,
        HttpUniverseProvider,
        RedisUniverseProvider,
        resolve_scan_universe,
    )

    monkeypatch.setenv("SETUP_UNIVERSE", "BTCUSDT,AAPL")
    store = InMemoryStateStore()
    await write_universe_active(store, ["AAPL", "MSFT"], now_ms=1)
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        assert "/v1/universe/top" in str(request.url)
        assert "limit=20" in str(request.url)
        return httpx.Response(200, json=_top_wire(["ES", "CL", "GC", "NQ"], limit=20))

    env = EnvUniverseProvider(Settings(SETUP_UNIVERSE="BTCUSDT,AAPL"))
    http = HttpUniverseProvider("http://de.example", env, transport=httpx.MockTransport(handler))
    auto = FallbackUniverseProvider(
        env=env,
        redis=RedisUniverseProvider(store, env),
        http=http,
    )
    scan = await resolve_scan_universe(auto, limit=20)
    assert list(scan.symbols) == ["ES", "CL", "GC", "NQ"]
    assert scan.backend == "http"
    assert "/v1/universe/top" in scan.source
    assert scan.ranked is True
    assert scan.members[0]["rank"] == 1
    assert seen and "/v1/universe/top" in seen[0]
    full = await auto.snapshot(ranked=False)
    assert [row["symbol"] if isinstance(row, dict) else row for row in (await store.get(REDIS_UNIVERSE_ACTIVE))["symbols"]] == ["AAPL", "MSFT"]
    assert list(full.symbols) == ["AAPL", "MSFT"]
    assert full.backend == "redis"


@pytest.mark.asyncio
async def test_scan_uses_redis_top_cache_not_setup_universe(monkeypatch):
    from sniper_data.universe import build_universe_provider, resolve_scan_universe

    monkeypatch.setenv("SETUP_UNIVERSE", "AAPL,MSFT")
    store = InMemoryStateStore()
    await write_universe_top(store, _top_wire(["ES", "NQ", "CL", "GC"], limit=10, as_of=7))
    provider = build_universe_provider(Settings(SETUP_UNIVERSE="AAPL,MSFT"), store=store)
    scan = await resolve_scan_universe(provider, limit=10)
    assert list(scan.symbols) == ["ES", "NQ", "CL", "GC"]
    assert scan.source == REDIS_UNIVERSE_TOP
    assert scan.backend == "redis"


@pytest.mark.asyncio
async def test_setup_universe_only_when_de_unreachable():
    from sniper_data.universe import EnvUniverseProvider, HttpUniverseProvider, resolve_scan_universe

    env = EnvUniverseProvider(Settings(SETUP_UNIVERSE="ES,CL,GC,NQ"))
    http = HttpUniverseProvider("http://127.0.0.1:9", env, timeout_s=0.05)
    scan = await resolve_scan_universe(http, limit=20)
    assert list(scan.symbols) == ["ES", "CL", "GC", "NQ"]
    assert scan.backend == "env"
    assert scan.source == "SETUP_UNIVERSE"
