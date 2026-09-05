from __future__ import annotations

from sniper_data.models import AnchorSource, AssetClass
from sniper_data.swings import SwingDetector, earnings_anchor, news_anchor


def test_fractal_swing_high_and_low():
    det = SwingDetector(left=2, right=2)
    # prices: 10, 11, 15, 12, 11 → pivot high at 15 once the right side confirms
    series = [10.0, 11.0, 15.0, 12.0, 11.0]
    found = []
    for i, px in enumerate(series):
        found.extend(det.on_tick("BTCUSDT", px, 1.0, 1_000 + i, AssetClass.CRYPTO))
    highs = [r for r in found if r.source is AnchorSource.SWING_HIGH]
    assert len(highs) == 1
    assert highs[0].anchor_price == 15.0
    assert highs[0].anchor_time == 1_002

    # continue into a swing low: 11, 8, 9, 10
    more = []
    for i, px in enumerate([8.0, 9.0, 10.0], start=5):
        more.extend(det.on_tick("BTCUSDT", px, 1.0, 1_000 + i, AssetClass.CRYPTO))
    lows = [r for r in more if r.source is AnchorSource.SWING_LOW]
    assert lows
    assert lows[0].anchor_price == 8.0


def test_placeholder_earnings_and_news_hooks():
    e = earnings_anchor("aapl", 1_700_000_000_000, 228.5)
    assert e.source is AnchorSource.EARNINGS
    assert e.symbol == "AAPL"
    assert e.asset_class is AssetClass.EQUITY
    n = news_anchor("BTCUSDT", 1_700_000_000_000, 64000.0)
    assert n.source is AnchorSource.NEWS
    assert n.asset_class is AssetClass.CRYPTO
