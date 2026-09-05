from __future__ import annotations

from sniper_data.models import AssetClass, Timeframe
from sniper_data.ohlcv import OHLCVAggregator, bar_open_ms
from sniper_data.symbols import normalize_tick


def test_bar_alignment_utc():
    # 12:03:10 UTC → 1m opens 12:03, 5m opens 12:00, 1h opens 12:00, 4h opens 12:00
    ts = 1_717_502_590_000  # not used — compute from known
    from datetime import datetime, timezone

    ts = int(datetime(2024, 6, 4, 12, 3, 10, tzinfo=timezone.utc).timestamp() * 1000)
    assert bar_open_ms(ts, Timeframe.M1) == int(datetime(2024, 6, 4, 12, 3, tzinfo=timezone.utc).timestamp() * 1000)
    assert bar_open_ms(ts, Timeframe.M5) == int(datetime(2024, 6, 4, 12, 0, tzinfo=timezone.utc).timestamp() * 1000)
    assert bar_open_ms(ts, Timeframe.H4) == int(datetime(2024, 6, 4, 12, 0, tzinfo=timezone.utc).timestamp() * 1000)


def test_close_on_boundary():
    agg = OHLCVAggregator((Timeframe.M1,))
    t0 = 1_717_502_400_000  # 2024-06-04 12:00:00Z
    tick_a = normalize_tick(symbol="BTCUSDT", price=100, volume=1, ts=t0)
    tick_b = normalize_tick(symbol="BTCUSDT", price=110, volume=2, ts=t0 + 30_000)
    tick_c = normalize_tick(symbol="BTCUSDT", price=90, volume=3, ts=t0 + 60_000)
    assert agg.on_tick(tick_a) == []
    assert agg.on_tick(tick_b) == []
    closed = agg.on_tick(tick_c)
    assert len(closed) == 1
    bar = closed[0]
    assert bar.open == 100
    assert bar.high == 110
    assert bar.low == 100
    assert bar.close == 110
    assert bar.volume == 3
    assert bar.n_ticks == 2
    assert bar.asset_class is AssetClass.CRYPTO
    assert bar.timeframe is Timeframe.M1
