from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from sniper_data.models import AssetClass, SessionType
from sniper_data.sessions import (
    SessionTracker,
    primary_session,
    sessions_at,
    weekly_anchor_start,
)

NY = ZoneInfo("America/New_York")
UTC = timezone.utc


def _utc(y, m, d, hh, mm, ss=0) -> datetime:
    return datetime(y, m, d, hh, mm, ss, tzinfo=UTC)


def test_crypto_windows_are_utc_not_midnight_everywhere():
    assert primary_session(AssetClass.CRYPTO, _utc(2024, 6, 4, 3, 0)).session_type is SessionType.ASIA
    assert primary_session(AssetClass.CRYPTO, _utc(2024, 6, 4, 7, 0)).session_type is SessionType.LONDON
    assert primary_session(AssetClass.CRYPTO, _utc(2024, 6, 4, 13, 30)).session_type is SessionType.NY_AM
    assert primary_session(AssetClass.CRYPTO, _utc(2024, 6, 4, 14, 59)).session_type is SessionType.NY_AM
    assert primary_session(AssetClass.CRYPTO, _utc(2024, 6, 4, 15, 0)) is None
    assert primary_session(AssetClass.CRYPTO, _utc(2024, 6, 4, 18, 0)).session_type is SessionType.NY_PM
    assert primary_session(AssetClass.CRYPTO, _utc(2024, 6, 4, 20, 0)) is None


def test_crypto_boundaries_exclusive_end():
    london_end = primary_session(AssetClass.CRYPTO, _utc(2024, 6, 4, 13, 29, 59))
    assert london_end is not None and london_end.session_type is SessionType.LONDON
    ny_pm_end = primary_session(AssetClass.CRYPTO, _utc(2024, 6, 4, 19, 59, 59))
    assert ny_pm_end is not None and ny_pm_end.session_type is SessionType.NY_PM


def test_equity_rth_dst_winter_est():
    # 09:30 EST = 14:30 UTC; 16:00 EST = 21:00 UTC; 20:00 EST = 01:00 UTC next day
    before = _utc(2024, 1, 16, 14, 29)
    open_ = _utc(2024, 1, 16, 14, 30)
    rth_close = _utc(2024, 1, 16, 21, 0)
    eth_close = _utc(2024, 1, 17, 1, 0)
    assert before.astimezone(NY).hour == 9
    assert primary_session(AssetClass.EQUITY, before).session_type is SessionType.ETH
    assert primary_session(AssetClass.EQUITY, open_).session_type is SessionType.RTH
    assert primary_session(AssetClass.EQUITY, rth_close).session_type is SessionType.ETH
    assert primary_session(AssetClass.EQUITY, eth_close) is None


def test_equity_rth_dst_summer_edt():
    # 09:30 EDT = 13:30 UTC; 16:00 EDT = 20:00 UTC; 20:00 EDT = 00:00 UTC next day
    before = _utc(2024, 7, 16, 13, 29)
    open_ = _utc(2024, 7, 16, 13, 30)
    rth_close = _utc(2024, 7, 16, 20, 0)
    eth_close = _utc(2024, 7, 17, 0, 0)
    assert open_.astimezone(NY).hour == 9 and open_.astimezone(NY).minute == 30
    assert primary_session(AssetClass.EQUITY, before).session_type is SessionType.ETH
    assert primary_session(AssetClass.EQUITY, open_).session_type is SessionType.RTH
    assert primary_session(AssetClass.EQUITY, rth_close).session_type is SessionType.ETH
    assert primary_session(AssetClass.EQUITY, eth_close) is None


def test_equity_eth_contains_rth_but_primary_is_rth():
    during_rth = _utc(2024, 7, 16, 15, 0)  # 11:00 EDT
    windows = sessions_at(AssetClass.EQUITY, during_rth)
    types = {w.session_type for w in windows}
    assert types == {SessionType.ETH, SessionType.RTH}
    assert primary_session(AssetClass.EQUITY, during_rth).session_type is SessionType.RTH


def test_equity_weekend_dark():
    saturday = _utc(2024, 7, 13, 15, 0)
    assert sessions_at(AssetClass.EQUITY, saturday) == []


def test_futures_globex_wraps_midnight_winter():
    # Friday 18:00 EST = 23:00 UTC on 2024-01-19
    start = _utc(2024, 1, 19, 23, 0)
    # Saturday 09:29 EST = 14:29 UTC 2024-01-20
    late = _utc(2024, 1, 20, 14, 29)
    after = _utc(2024, 1, 20, 14, 30)
    win = primary_session(AssetClass.FUTURES, start)
    assert win is not None and win.session_type is SessionType.GLOBEX
    assert primary_session(AssetClass.FUTURES, late).session_type is SessionType.GLOBEX
    # Saturday 09:30 is not a weekday RTH; globex has ended.
    assert primary_session(AssetClass.FUTURES, after) is None


def test_futures_rth_and_globex_dst_summer():
    # Monday 18:00 EDT = 22:00 UTC
    globex = _utc(2024, 7, 15, 22, 0)
    assert globex.astimezone(NY).hour == 18
    assert primary_session(AssetClass.FUTURES, globex).session_type is SessionType.GLOBEX
    # Tuesday 09:30 EDT = 13:30 UTC
    rth = _utc(2024, 7, 16, 13, 30)
    assert primary_session(AssetClass.FUTURES, rth).session_type is SessionType.RTH


def test_weekly_anchor_crypto_monday_utc():
    wed = _utc(2024, 6, 5, 15, 0)  # Wednesday
    anchor = weekly_anchor_start(AssetClass.CRYPTO, wed)
    assert anchor == datetime(2024, 6, 3, 0, 0, tzinfo=UTC)


def test_weekly_anchor_equity_monday_rth_open_ny():
    wed = datetime(2024, 7, 17, 16, 0, tzinfo=NY)
    anchor = weekly_anchor_start(AssetClass.EQUITY, wed)
    assert anchor == datetime(2024, 7, 15, 9, 30, tzinfo=NY)
    # Monday 08:00 ET is before this week's RTH open → previous Monday.
    monday_pre = datetime(2024, 7, 15, 8, 0, tzinfo=NY)
    prev = weekly_anchor_start(AssetClass.EQUITY, monday_pre)
    assert prev == datetime(2024, 7, 8, 9, 30, tzinfo=NY)


def test_session_tracker_publishes_ohlc():
    tracker = SessionTracker()
    t0 = int(_utc(2024, 6, 4, 8, 0).timestamp() * 1000)
    a = tracker.on_tick("BTCUSDT", 100.0, 1.0, t0, AssetClass.CRYPTO)
    b = tracker.on_tick("BTCUSDT", 110.0, 1.0, t0 + 1000, AssetClass.CRYPTO)
    c = tracker.on_tick("BTCUSDT", 90.0, 2.0, t0 + 2000, AssetClass.CRYPTO)
    assert a is not None and a.session_type is SessionType.LONDON
    assert c.open == 100.0
    assert c.high == 110.0
    assert c.low == 90.0
    assert c.close == 90.0
    assert c.volume == 4.0
