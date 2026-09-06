"""Continuous DE 1m/5m bar feed — not 15m universe/dashboard."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from sniper_quant.api import create_app
from sniper_quant.bus import InMemoryBus, OHLCV_BARS_TOPIC
from sniper_quant.lifecycle import LifecycleMonitor
from sniper_quant.live import SignalHub
from sniper_quant.models import AssetClass, OHLCVBar, Side, SignalStatus, StoredSignal
from sniper_quant.ohlcv_feed import (
    OhlcvBarService,
    de_ohlcv_http_url,
    de_ohlcv_ws_url,
    parse_de_ohlcv_response,
    parse_ohlcv_bar,
    reject_non_bar_envelope,
    run_inmemory_ohlcv_consumer,
)
from sniper_quant.risk.engine import RiskEngine, RiskState
from sniper_quant.store.ohlcv import InMemoryOHLCVLoader, assert_bar_feed_timeframe
from sniper_quant.store.signals import InMemorySignalStore
from tests.conftest import make_settings


def _bar_payload(tf: str = "1m", **over) -> dict:
    body = {
        "schema_version": "1.1",
        "symbol": "ES",
        "asset_class": "futures",
        "timeframe": tf,
        "open_ts_ms": 1_700_000_000_000,
        "close_ts_ms": 1_700_000_059_999,
        "open": 100.0,
        "high": 101.0,
        "low": 99.0,
        "close": 100.5,
        "volume": 10.0,
        "n_ticks": 4,
    }
    body.update(over)
    return body


def test_bar_feed_timeframe_lock():
    assert assert_bar_feed_timeframe("1m") == "1m"
    assert assert_bar_feed_timeframe("5m") == "5m"
    with pytest.raises(ValueError, match="universe/top"):
        assert_bar_feed_timeframe("15m")
    with pytest.raises(ValueError, match="1m or 5m"):
        assert_bar_feed_timeframe("1h")


def test_parse_de_get_ohlcv_1m_and_5m():
    ten = [_bar_payload("1m"), _bar_payload("1m", open_ts_ms=1_700_000_060_000, close_ts_ms=1_700_000_119_999)]
    parsed = parse_de_ohlcv_response(
        {"symbol": "ES", "timeframe": "1m", "bars": ten},
        timeframe="1m",
    )
    assert [b.symbol for b in parsed] == ["ES", "ES"]
    assert parsed[0].timeframe == "1m"

    five = parse_de_ohlcv_response(
        {"symbol": "BTCUSDT", "timeframe": "5m", "bars": [_bar_payload("5m", symbol="BTCUSDT", asset_class="crypto")]},
        timeframe="5m",
    )
    assert five[0].timeframe == "5m"


def test_reject_universe_top_and_dashboard_as_bars():
    top = {
        "as_of_ts_ms": 1,
        "limit": 10,
        "symbols": [{"symbol": "ES", "asset_class": "futures", "rank": 1, "score": 0.9}],
    }
    with pytest.raises(ValueError, match="ranking book"):
        reject_non_bar_envelope(top)
    with pytest.raises(ValueError, match="ranking book"):
        parse_ohlcv_bar(top)
    with pytest.raises(ValueError, match="dashboard"):
        reject_non_bar_envelope({"kind": "dashboard_snapshot", "symbol": "ES"})
    with pytest.raises(ValueError, match="15m"):
        parse_de_ohlcv_response(
            {"symbol": "ES", "timeframe": "15m", "bars": [_bar_payload("15m")]},
            timeframe="15m",
        )


def test_de_urls_are_ohlcv_not_universe():
    settings = make_settings(DE_API_BASE="http://localhost:8000")
    assert de_ohlcv_http_url(settings, "ES") == "http://localhost:8000/v1/ohlcv/ES"
    assert de_ohlcv_ws_url(settings, "ES", "5m") == "ws://localhost:8000/v1/ws/ohlcv?symbol=ES&timeframe=5m"
    with pytest.raises(ValueError, match="1m or 5m"):
        de_ohlcv_ws_url(settings, "ES", "15m")


async def test_http_loader_fetches_locked_envelope(monkeypatch):
    from sniper_quant.ohlcv_feed import DeHttpOHLCVLoader

    payload = {
        "symbol": "NQ",
        "timeframe": "5m",
        "bars": [_bar_payload("5m", symbol="NQ")],
    }

    class _Resp:
        def raise_for_status(self):
            return None

        def json(self):
            return payload

    def fake_get(url, params=None, timeout=None):
        assert url.endswith("/v1/ohlcv/NQ")
        assert params["timeframe"] == "5m"
        assert "/universe/top" not in url
        assert "dashboard" not in url
        return _Resp()

    monkeypatch.setattr("httpx.get", fake_get)
    loader = DeHttpOHLCVLoader(make_settings(DE_API_BASE="http://de.test"))
    rows = await loader.fetch("NQ", "5m")
    assert len(rows) == 1
    assert rows[0].symbol == "NQ"


async def test_kafka_1m_marks_and_skips_15m():
    store = InMemorySignalStore()
    await store.insert(
        StoredSignal.model_validate(
            {
                "id": "live-es",
                "symbol": "ES",
                "asset_class": AssetClass.FUTURES,
                "setup_type": "sweep_reclaim",
                "side": Side.LONG,
                "ts_ms": 1_000,
                "entry": 100.0,
                "stop": 96.0,
                "target": 108.0,
                "position_size": 1.0,
                "status": SignalStatus.ACTIVE,
            }
        )
    )
    loader = InMemoryOHLCVLoader()
    monitor = LifecycleMonitor(store, SignalHub(), loader)
    closed: list = []

    async def on_bar(bar: OHLCVBar) -> None:
        closed.extend(await monitor.apply_bar(bar))

    service = OhlcvBarService(loader, on_bar=on_bar)
    bus = InMemoryBus()
    await run_inmemory_ohlcv_consumer(bus, service)
    skipped = await service.handle(
        {
            "as_of_ts_ms": 1,
            "limit": 10,
            "symbols": [{"symbol": "ES", "asset_class": "futures", "rank": 1, "score": 0.1}],
        }
    )
    assert skipped is None
    skipped_tf = await service.handle(_bar_payload("15m"))
    assert skipped_tf is None
    await bus.publish(
        OHLCV_BARS_TOPIC,
        _bar_payload("1m", high=109.0, low=99.0, close=108.5),
        key="ES",
    )
    assert len(closed) == 1
    assert closed[0].status is SignalStatus.TP_HIT
    tape = await loader.fetch("ES", "1m")
    assert len(tape) == 1


def test_lifecycle_bar_rejects_15m_and_universe_docs():
    settings = make_settings()
    engine = RiskEngine(settings=settings, state=RiskState(equity=100_000))
    http = TestClient(create_app(settings=settings, signals=InMemorySignalStore(), engine=engine))
    bad = http.post("/v1/lifecycle/bar", json=_bar_payload("15m"))
    assert bad.status_code == 422
    setups = http.get("/v1/setups").json()
    assert setups["bar_feed"] == "de_ohlcv_1m_5m"
    assert setups["bar_feed_timeframes"] == ["1m", "5m"]
    assert setups["universe_top_role"] == "15m_ranking_book_only"
    assert "/v1/universe/top" in setups["bar_feed_not"]
    dump = http.get("/paper/universe").json()
    assert dump["bar_feed"]["timeframes"] == ["1m", "5m"]
    assert dump["bar_feed"]["live_trading"] is False
    assert dump["handoff"] in {"fallback", "de_top"}
    spec = http.get("/openapi.json").json()
    assert "1m / 5m" in spec["info"]["description"] or "1m/5m" in spec["info"]["description"]
    assert "universe/top" in spec["info"]["description"]
