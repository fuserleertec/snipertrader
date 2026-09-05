from __future__ import annotations

from datetime import datetime, timezone

from sniper_data.models import AssetClass, Timeframe
from sniper_data.ohlcv import OHLCVAggregator, classify_aggressor, signed_volume
from sniper_data.symbols import normalize_tick


def test_bar_alignment_utc():
    from sniper_data.ohlcv import bar_open_ms

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
    assert bar.buy_volume is None
    assert bar.sell_volume is None


def test_classify_aggressor_explicit_and_mid_and_maker():
    buy = normalize_tick(symbol="BTCUSDT", price=100, volume=2, ts=1, aggressor="buy")
    sell = normalize_tick(symbol="BTCUSDT", price=100, volume=3, ts=1, aggressor="sell")
    assert classify_aggressor(buy) == "buy"
    assert signed_volume(buy) == 2
    assert classify_aggressor(sell) == "sell"
    assert signed_volume(sell) == -3

    maker_sell = normalize_tick(
        symbol="BTCUSDT", price=100, volume=1, ts=1, is_buyer_maker=True
    )
    taker_buy = normalize_tick(
        symbol="BTCUSDT", price=100, volume=1, ts=1, is_buyer_maker=False
    )
    assert classify_aggressor(maker_sell) == "sell"
    assert classify_aggressor(taker_buy) == "buy"

    above_mid = normalize_tick(
        symbol="BTCUSDT", price=101, volume=1, ts=1, bid=99, ask=101
    )
    below_mid = normalize_tick(
        symbol="BTCUSDT", price=99, volume=1, ts=1, bid=99, ask=101
    )
    # mid = 100; 101 >= 100 → buy; 99 < 100 → sell
    assert classify_aggressor(above_mid) == "buy"
    assert classify_aggressor(below_mid) == "sell"
    assert classify_aggressor(normalize_tick(symbol="BTCUSDT", price=100, volume=1, ts=1)) is None


def test_bar_buy_sell_from_aggressor():
    agg = OHLCVAggregator((Timeframe.M1,))
    t0 = 1_717_502_400_000
    agg.on_tick(normalize_tick(symbol="BTCUSDT", price=100, volume=10, ts=t0, aggressor="buy"))
    agg.on_tick(normalize_tick(symbol="BTCUSDT", price=101, volume=4, ts=t0 + 1_000, aggressor="sell"))
    closed = agg.on_tick(normalize_tick(symbol="BTCUSDT", price=102, volume=1, ts=t0 + 60_000, aggressor="buy"))
    bar = closed[0]
    assert bar.volume == 14
    assert bar.buy_volume == 10
    assert bar.sell_volume == 4
    assert bar.buy_volume + bar.sell_volume == bar.volume
    assert (bar.buy_volume - bar.sell_volume) == 6


def test_bar_buy_sell_derived_from_mid():
    agg = OHLCVAggregator((Timeframe.M1,))
    t0 = 1_717_502_400_000
    # mid=100; price 100.5 → buy 5; price 99.5 → sell 3
    agg.on_tick(normalize_tick(symbol="ES", price=100.5, volume=5, ts=t0, bid=99.5, ask=100.5))
    agg.on_tick(normalize_tick(symbol="ES", price=99.5, volume=3, ts=t0 + 1_000, bid=99.5, ask=100.5))
    bar = agg.flush()[0]
    assert bar.volume == 8
    assert bar.buy_volume == 5
    assert bar.sell_volume == 3
