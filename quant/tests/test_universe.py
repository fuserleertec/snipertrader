"""File-backed ranking allow-list (paper only, no hardcoded lists)."""

from __future__ import annotations

from pathlib import Path

import pytest

from sniper_quant.backtest.detectors import detect_setup
from sniper_quant.backtest.params import DEFAULT_PARAMS
from sniper_quant.config import get_settings
from sniper_quant.models import AssetClass, OHLCVBar
from sniper_quant.universe import (
    DEFAULT_UNIVERSE_PATH,
    REQUIRED_FUTURES,
    clear_de_top_cache,
    load_paper_universe,
    load_universe_file,
    parse_universe_top,
    ranking_source,
    resolve_ranking_universe,
    universe_dump,
)
from tests.conftest import make_settings


def _paper_symbols() -> set[str]:
    return {s for s, _ in load_paper_universe(make_settings())}


def test_default_paper_universe_file_has_mix():
    assert DEFAULT_UNIVERSE_PATH.is_file()
    pairs = load_paper_universe(make_settings())
    assert len(pairs) >= 20
    classes = {ac for _, ac in pairs}
    assert classes == {AssetClass.CRYPTO, AssetClass.EQUITY, AssetClass.FUTURES}
    assert ("BTCUSDT", AssetClass.CRYPTO) in pairs
    assert ("AAPL", AssetClass.EQUITY) in pairs
    assert REQUIRED_FUTURES <= {s for s, _ in pairs}
    for root in REQUIRED_FUTURES:
        assert (root, AssetClass.FUTURES) in pairs


def test_default_ranking_is_the_paper_file_not_a_hardcoded_list():
    ranked = resolve_ranking_universe(make_settings())
    paper = load_paper_universe(make_settings())
    assert ranked == paper
    assert ranking_source(make_settings()) == "paper_universe"
    assert REQUIRED_FUTURES <= {s for s, _ in ranked}
    assert "IBM" not in {s for s, _ in ranked}


def test_setup_universe_can_only_narrow_file():
    settings = make_settings(SETUP_UNIVERSE="BTCUSDT,ES,FAKECOIN,NVDA")
    ranked = resolve_ranking_universe(settings)
    assert {s for s, _ in ranked} == {"BTCUSDT", "ES", "NVDA"}

    csv = make_settings(PAPER_UNIVERSE="SOLUSDT:crypto,NVDA:equity,NQ:futures")
    assert load_paper_universe(csv) == [
        ("SOLUSDT", AssetClass.CRYPTO),
        ("NVDA", AssetClass.EQUITY),
        ("NQ", AssetClass.FUTURES),
    ]
    # Paper override does not expand (or shrink) the ensemble allow-list.
    assert {s for s, _ in resolve_ranking_universe(csv)} == _paper_symbols()


def test_demo_symbols_override_replaces_file():
    settings = make_settings(DEMO_SYMBOLS="ETHUSDT,MSFT")
    assert ranking_source(settings) == "demo_symbols"
    assert {s for s, _ in resolve_ranking_universe(settings)} == {"ETHUSDT", "MSFT"}


def test_de_universe_top_limit_10_and_20(monkeypatch: pytest.MonkeyPatch):
    clear_de_top_cache()
    ten = [
        ("ES", AssetClass.FUTURES),
        ("CL", AssetClass.FUTURES),
        ("GC", AssetClass.FUTURES),
        ("NQ", AssetClass.FUTURES),
        ("BTCUSDT", AssetClass.CRYPTO),
        ("ETHUSDT", AssetClass.CRYPTO),
        ("AAPL", AssetClass.EQUITY),
        ("MSFT", AssetClass.EQUITY),
        ("NVDA", AssetClass.EQUITY),
        ("SPY", AssetClass.EQUITY),
    ]
    twenty = ten + [
        ("SOLUSDT", AssetClass.CRYPTO),
        ("AMZN", AssetClass.EQUITY),
        ("META", AssetClass.EQUITY),
        ("GOOGL", AssetClass.EQUITY),
        ("TSLA", AssetClass.EQUITY),
        ("BNBUSDT", AssetClass.CRYPTO),
        ("XRPUSDT", AssetClass.CRYPTO),
        ("ADAUSDT", AssetClass.CRYPTO),
        ("AVAXUSDT", AssetClass.CRYPTO),
        ("LINKUSDT", AssetClass.CRYPTO),
    ]

    def fake_fetch(_settings, limit: int):
        return list(ten if limit == 10 else twenty)

    settings = make_settings(DE_API_BASE="http://de.test")
    assert ranking_source(settings, limit=10, fetcher=fake_fetch) == "de_top"
    assert resolve_ranking_universe(settings, limit=10, fetcher=fake_fetch) == ten
    assert resolve_ranking_universe(settings, limit=20, fetcher=fake_fetch) == twenty
    dump = universe_dump(settings, fetcher=fake_fetch)
    assert dump["handoff"] == "de_top"
    assert dump["live_trading"] is False
    assert {r["symbol"] for r in dump["ensemble_universe"]} == {s for s, _ in ten}
    assert {r["symbol"] for r in dump["history_universe"]} == {s for s, _ in twenty}
    assert REQUIRED_FUTURES <= {r["symbol"] for r in dump["ensemble_universe"]}


def test_parse_universe_top_and_http_handoff(monkeypatch: pytest.MonkeyPatch):
    clear_de_top_cache()
    payload = {
        "as_of_ts_ms": 1_700_000_400_000,
        "limit": 10,
        "symbols": [
            {"symbol": "ES", "asset_class": "futures", "rank": 1, "score": 0.9},
            {"symbol": "CL", "asset_class": "futures", "rank": 2, "score": 0.8},
            {"symbol": "GC", "asset_class": "futures", "rank": 3, "score": 0.7},
            {"symbol": "NQ", "asset_class": "futures", "rank": 4, "score": 0.6},
        ],
    }
    parsed = parse_universe_top(payload, limit=10)
    assert [s for s, _ in parsed] == ["ES", "CL", "GC", "NQ"]

    class _Resp:
        def raise_for_status(self) -> None:
            return None

        def json(self):
            return payload

    def fake_get(url, params=None, timeout=None):
        assert url.endswith("/v1/universe/top")
        assert params["limit"] in (10, 20)
        return _Resp()

    monkeypatch.setattr("httpx.get", fake_get)
    settings = make_settings(DE_API_BASE="http://de.test")
    from sniper_quant.universe import fetch_de_universe_top

    got = fetch_de_universe_top(settings, 10)
    assert [s for s, _ in got] == ["ES", "CL", "GC", "NQ"]
    assert ranking_source(settings, limit=10) == "de_top"
    clear_de_top_cache()


def test_de_top_failure_keeps_provisional_futures(monkeypatch: pytest.MonkeyPatch):
    clear_de_top_cache()

    def boom(url, params=None, timeout=None):
        raise ConnectionError("de down")

    monkeypatch.setattr("httpx.get", boom)
    settings = make_settings(DE_API_BASE="http://de.test")
    ranked = resolve_ranking_universe(settings, limit=10)
    assert REQUIRED_FUTURES <= {s for s, _ in ranked}
    assert ranking_source(settings) == "paper_universe"


def test_de_universe_handoff_replaces_demo_symbols(tmp_path: Path):
    feed = tmp_path / "de.json"
    feed.write_text(
        '{"symbols":[{"symbol":"ETHUSDT","asset_class":"crypto"},'
        '{"symbol":"MSFT","asset_class":"equity"}]}',
        encoding="utf-8",
    )
    settings = make_settings(DE_UNIVERSE=str(feed), SETUP_UNIVERSE="ETHUSDT,NVDA")
    assert ranking_source(settings) == "de_feed"
    assert resolve_ranking_universe(settings) == [("ETHUSDT", AssetClass.CRYPTO)]


def test_missing_universe_file_raises(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    missing = tmp_path / "missing_universe.json"
    monkeypatch.setattr("sniper_quant.universe.DEFAULT_UNIVERSE_PATH", missing)
    with pytest.raises(FileNotFoundError, match="no hardcoded fallback"):
        load_universe_file()
    with pytest.raises(FileNotFoundError, match="no hardcoded fallback"):
        load_paper_universe(make_settings())
    with pytest.raises(FileNotFoundError, match="no hardcoded fallback"):
        resolve_ranking_universe(make_settings())


def test_setup_universe_filters_detectors():
    bars = [
        OHLCVBar(
            symbol="BTCUSDT",
            asset_class=AssetClass.CRYPTO,
            timeframe="5m",
            open_ts_ms=1_700_000_000_000 + i * 300_000,
            close_ts_ms=1_700_000_000_000 + (i + 1) * 300_000,
            open=100.0,
            high=101.0,
            low=99.0,
            close=100.5,
            volume=10.0,
        )
        for i in range(5)
    ]
    assert detect_setup("sweep_reclaim", bars, DEFAULT_PARAMS, setup_universe={"ETHUSDT"}) == []
    detect_setup("sweep_reclaim", bars, DEFAULT_PARAMS, setup_universe=None)
    get_settings.cache_clear()
