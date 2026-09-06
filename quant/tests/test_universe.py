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
    load_paper_universe,
    load_universe_file,
    ranking_source,
    resolve_ranking_universe,
)
from tests.conftest import make_settings

REQUIRED_FUTURES = {"ES", "CL", "GC", "NQ"}


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
