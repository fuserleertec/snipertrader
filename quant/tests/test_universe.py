"""Paper universe + SETUP_UNIVERSE intersection (paper only)."""

from __future__ import annotations

from pathlib import Path

from sniper_quant.backtest.detectors import detect_setup
from sniper_quant.backtest.params import DEFAULT_PARAMS
from sniper_quant.config import get_settings
from sniper_quant.models import AssetClass, OHLCVBar
from sniper_quant.universe import (
    DEFAULT_UNIVERSE_PATH,
    load_paper_universe,
    resolve_ranking_universe,
)
from tests.conftest import make_settings


def test_default_paper_universe_file_has_mix():
    assert DEFAULT_UNIVERSE_PATH.is_file()
    pairs = load_paper_universe(make_settings())
    assert len(pairs) >= 20
    classes = {ac for _, ac in pairs}
    assert classes == {AssetClass.CRYPTO, AssetClass.EQUITY, AssetClass.FUTURES}
    assert ("BTCUSDT", AssetClass.CRYPTO) in pairs
    assert ("AAPL", AssetClass.EQUITY) in pairs
    assert ("ES", AssetClass.FUTURES) in pairs


def test_setup_universe_intersection_and_csv_override(tmp_path: Path):
    settings = make_settings(SETUP_UNIVERSE="BTCUSDT,ES,FAKECOIN")
    ranked = resolve_ranking_universe(settings)
    assert {s for s, _ in ranked} == {"BTCUSDT", "ES"}

    alt = tmp_path / "uni.json"
    alt.write_text(
        '{"symbols":[{"symbol":"MSFT","asset_class":"equity"},'
        '{"symbol":"CL","asset_class":"futures"}]}',
        encoding="utf-8",
    )
    custom = make_settings(PAPER_UNIVERSE=str(alt), SETUP_UNIVERSE="MSFT")
    assert resolve_ranking_universe(custom) == [("MSFT", AssetClass.EQUITY)]

    csv = make_settings(PAPER_UNIVERSE="SOLUSDT:crypto,NVDA:equity,NQ:futures")
    assert load_paper_universe(csv) == [
        ("SOLUSDT", AssetClass.CRYPTO),
        ("NVDA", AssetClass.EQUITY),
        ("NQ", AssetClass.FUTURES),
    ]


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
    # Unset allow-list does not drop the tape (may still find no pattern).
    detect_setup("sweep_reclaim", bars, DEFAULT_PARAMS, setup_universe=None)
    get_settings.cache_clear()
