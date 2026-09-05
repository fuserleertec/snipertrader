"""5m session-aware tape with injected Setups 1–3 (DE crypto session clocks)."""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

from sniper_quant.models import AssetClass, OHLCVBar

UTC = timezone.utc
BAR_MS = 300_000  # 5m
# 2024-06-03 Monday 00:00 UTC
START = datetime(2024, 6, 3, 0, 0, tzinfo=UTC)


def _ms(dt: datetime) -> int:
    return int(dt.timestamp() * 1000)


def _bar(
    symbol: str,
    ts: int,
    o: float,
    h: float,
    l: float,
    c: float,
    volume: float = 100.0,
    timeframe: str = "5m",
) -> OHLCVBar:
    return OHLCVBar(
        symbol=symbol,
        asset_class=AssetClass.CRYPTO,
        timeframe=timeframe,
        open_ts_ms=ts,
        close_ts_ms=ts + BAR_MS - 1,
        open=o,
        high=max(o, h, l, c),
        low=min(o, h, l, c),
        close=c,
        volume=volume,
        n_ticks=12,
    )


def _range(
    symbol: str,
    start: datetime,
    n: int,
    mid: float,
    half: float,
    timeframe: str,
) -> list[OHLCVBar]:
    bars: list[OHLCVBar] = []
    px = mid
    for i in range(n):
        wobble = half * 0.35 * math.sin(i * 0.55)
        o = px
        c = mid + wobble
        h = max(o, c) + half * 0.2
        l = min(o, c) - half * 0.2
        ts = _ms(start + timedelta(minutes=5 * i))
        bars.append(_bar(symbol, ts, o, h, l, c, volume=110 + (i % 7), timeframe=timeframe))
        px = c
    return bars


def _day_start(day_offset: int) -> datetime:
    return START + timedelta(days=day_offset)


def _sweep_reclaim_day(symbol: str, day: datetime, mid: float, timeframe: str) -> list[OHLCVBar]:
    """London sweep + MSS reclaim with VWAP bands still in front of entry."""
    # Volatile Asia so session σ on the next window is independent; London starts fresh.
    asia = _range(symbol, day, 84, mid, 0.8, timeframe)
    london_start = day + timedelta(hours=7)
    # Wide early London builds session σ; last 8 bars tighten so the sweep is shallow.
    # Fat session residual so VWAP ±2σ can clear min_rr=2.0 after a shallow sweep.
    fat: list[OHLCVBar] = []
    for k, (h, l, c) in enumerate(((mid + 3.2, mid - 0.2, mid + 1.4), (mid + 0.3, mid - 3.2, mid - 1.2), (mid + 2.8, mid - 0.4, mid + 0.4))):
        fat.append(
            _bar(
                symbol,
                _ms(london_start + timedelta(minutes=5 * k)),
                mid,
                h,
                l,
                c,
                volume=90,
                timeframe=timeframe,
            )
        )
    wide = _range(symbol, london_start + timedelta(minutes=15), 17, mid, 0.8, timeframe)
    tight_start = london_start + timedelta(minutes=5 * 20)
    tight = _range(symbol, tight_start, 8, mid, 0.10, timeframe)
    pre = fat + wide + tight
    ts = _ms(london_start + timedelta(minutes=5 * 28))
    swing_floor = min(b.low for b in tight[-5:])
    sweep = _bar(
        symbol,
        ts,
        mid,
        mid + 0.06,
        swing_floor - 0.14,
        mid + 0.01,
        volume=420,
        timeframe=timeframe,
    )
    follow: list[OHLCVBar] = []
    t = ts + BAR_MS
    swing_high = max(b.high for b in pre[-5:])
    follow.append(_bar(symbol, t, mid + 0.04, mid + 0.18, mid - 0.04, mid + 0.08, volume=160, timeframe=timeframe))
    t += BAR_MS
    # MSS: close just through the swing high (stay below 1σ so bands remain targets).
    mss_close = swing_high + 0.04
    follow.append(_bar(symbol, t, mid + 0.08, mss_close + 0.06, mid + 0.04, mss_close, volume=300, timeframe=timeframe))
    # Path out to ~2σ+ so the backtest can hit the band.
    for close in (mid + 0.9, mid + 1.5, mid + 2.1, mid + 2.7):
        t += BAR_MS
        follow.append(
            _bar(symbol, t, follow[-1].close, close + 0.1, follow[-1].close - 0.08, close, volume=150, timeframe=timeframe)
        )
    used = 28 + 1 + len(follow)
    rest = _range(symbol, london_start + timedelta(minutes=5 * used), max(78 - used, 4), follow[-1].close, 0.3, timeframe)
    ny = _range(symbol, day + timedelta(hours=13, minutes=30), 18, rest[-1].close, 0.25, timeframe)
    return asia + pre + [sweep] + follow + rest + ny


def _fvg_day(symbol: str, day: datetime, mid: float, timeframe: str, *, pin: bool) -> list[OHLCVBar]:
    asia = _range(symbol, day, 84, mid, 0.45, timeframe)
    london_start = day + timedelta(hours=7)
    pre = _range(symbol, london_start, 16, mid, 0.35, timeframe)
    ts = _ms(london_start + timedelta(minutes=5 * 16))
    # Bullish FVG whose zone contains session VWAP (~mid).
    left = _bar(symbol, ts, mid - 0.12, mid - 0.08, mid - 0.28, mid - 0.14, volume=140, timeframe=timeframe)
    midb = _bar(symbol, ts + BAR_MS, mid - 0.1, mid + 0.7, mid - 0.16, mid + 0.55, volume=380, timeframe=timeframe)
    right = _bar(symbol, ts + 2 * BAR_MS, mid + 0.5, mid + 0.65, mid + 0.12, mid + 0.32, volume=190, timeframe=timeframe)
    t = ts + 3 * BAR_MS
    if pin:
        # Lower wick / body >= 2.5; close is the confirm_close entry.
        confirm = _bar(symbol, t, mid + 0.38, mid + 0.48, mid + 0.08, mid + 0.42, volume=250, timeframe=timeframe)
    else:
        confirm = _bar(symbol, t, right.low - 0.03, right.high + 0.08, right.low - 0.03, right.high + 0.05, volume=270, timeframe=timeframe)
    follow = []
    px = confirm.close
    t = confirm.open_ts_ms + BAR_MS
    for close in (mid + 0.9, mid + 1.4, mid + 1.9, mid + 2.3):
        follow.append(_bar(symbol, t, px, close + 0.1, px - 0.08, close, volume=150, timeframe=timeframe))
        px = close
        t += BAR_MS
    used = 16 + 4 + len(follow)
    rest = _range(symbol, london_start + timedelta(minutes=5 * used), max(78 - used, 4), px, 0.2, timeframe)
    ny = _range(symbol, day + timedelta(hours=13, minutes=30), 18, rest[-1].close, 0.2, timeframe)
    return asia + pre + [left, midb, right, confirm] + follow + rest + ny


def _po3_day(symbol: str, day: datetime, mid: float, timeframe: str) -> list[OHLCVBar]:
    # Tight Asia range so opposite extreme is ≥ 2R from a low-side displacement entry.
    asia = _range(symbol, day, 84, mid, 0.95, timeframe)
    london = _range(symbol, day + timedelta(hours=7), 78, mid, 0.25, timeframe)
    ny_start = day + timedelta(hours=13, minutes=30)
    asia_lo = min(b.low for b in asia)
    t0 = _ms(ny_start)
    sweep = _bar(symbol, t0, mid - 0.2, mid + 0.04, asia_lo - 0.2, mid - 0.55, volume=480, timeframe=timeframe)
    # Displacement stays in the lower half so opposite Asia extreme is ≥ 2R.
    disp = _bar(
        symbol,
        t0 + BAR_MS,
        mid - 0.70,
        mid - 0.20,
        mid - 0.75,
        mid - 0.38,
        volume=520,
        timeframe=timeframe,
    )
    follow = []
    t = t0 + 2 * BAR_MS
    px = disp.close
    # Continue toward Asia high (target).
    asia_hi = max(b.high for b in asia)
    for step in (0.4, 0.7, 1.1, 1.5):
        close = min(mid + step, asia_hi + 0.05)
        follow.append(_bar(symbol, t, px, close + 0.08, px - 0.08, close, volume=170, timeframe=timeframe))
        px = close
        t += BAR_MS
    rest_n = max(18 - 2 - len(follow), 2)
    rest = _range(symbol, ny_start + timedelta(minutes=5 * (2 + len(follow))), rest_n, px, 0.2, timeframe)
    return asia + london + [sweep, disp] + follow + rest


def _sd_fade_day(symbol: str, day: datetime, mid: float, timeframe: str) -> list[OHLCVBar]:
    """Low-volume ≥2σ extension + pin confirm, then grind back to session VWAP."""
    asia = _range(symbol, day, 84, mid, 0.25, timeframe)
    london_start = day + timedelta(hours=7)
    tight = _range(symbol, london_start, 24, mid, 0.10, timeframe)
    ts = _ms(london_start + timedelta(minutes=5 * 24))
    # Established σ from tight tape is small; wick ~0.45 below mid ≈ ≥2σ.
    ext = _bar(symbol, ts, mid, mid + 0.04, mid - 0.48, mid - 0.22, volume=22, timeframe=timeframe)
    pin = _bar(
        symbol,
        ts + BAR_MS,
        mid - 0.28,
        mid - 0.18,
        mid - 0.46,
        mid - 0.26,
        volume=90,
        timeframe=timeframe,
    )
    follow: list[OHLCVBar] = []
    t = pin.open_ts_ms + BAR_MS
    px = pin.close
    for close in (mid - 0.10, mid + 0.02, mid + 0.08, mid + 0.12):
        follow.append(_bar(symbol, t, px, close + 0.06, px - 0.04, close, volume=140, timeframe=timeframe))
        px = close
        t += BAR_MS
    used = 24 + 2 + len(follow)
    rest = _range(symbol, london_start + timedelta(minutes=5 * used), max(78 - used, 4), px, 0.15, timeframe)
    ny = _range(symbol, day + timedelta(hours=13, minutes=30), 18, rest[-1].close, 0.12, timeframe)
    return asia + tight + [ext, pin] + follow + rest + ny


def _vwap_pb_day(symbol: str, day: datetime, mid: float, timeframe: str) -> list[OHLCVBar]:
    """Uptrend, first-touch VWAP pullback, bullish FVG, strong-body continuation."""
    asia = _range(symbol, day, 84, mid - 0.4, 0.12, timeframe)
    london_start = day + timedelta(hours=7)
    climb: list[OHLCVBar] = []
    px = mid - 0.2
    for i in range(20):
        nxt = px + 0.10
        ts = _ms(london_start + timedelta(minutes=5 * i))
        climb.append(_bar(symbol, ts, px, nxt + 0.03, px - 0.02, nxt, volume=160, timeframe=timeframe))
        px = nxt
    # Bullish FVG, then a shallow pullback that tags VWAP near `mid`.
    ts = _ms(london_start + timedelta(minutes=5 * 20))
    left = _bar(symbol, ts, px, px + 0.03, px - 0.05, px - 0.01, volume=120, timeframe=timeframe)
    midb = _bar(symbol, ts + BAR_MS, px, px + 0.45, px - 0.03, px + 0.36, volume=260, timeframe=timeframe)
    right = _bar(symbol, ts + 2 * BAR_MS, px + 0.30, px + 0.40, px + 0.22, px + 0.28, volume=150, timeframe=timeframe)
    # Pull back to the live session VWAP (~ last climb VWAP ≈ mid+0.8), not `mid`.
    pb1 = _bar(symbol, ts + 3 * BAR_MS, px + 0.20, px + 0.22, mid + 0.90, mid + 0.95, volume=130, timeframe=timeframe)
    pb2 = _bar(symbol, ts + 4 * BAR_MS, mid + 0.95, mid + 1.00, mid + 0.72, mid + 0.82, volume=120, timeframe=timeframe)
    confirm = _bar(
        symbol,
        ts + 5 * BAR_MS,
        mid + 0.80,
        mid + 1.05,
        mid + 0.78,
        mid + 0.98,
        volume=240,
        timeframe=timeframe,
    )
    follow: list[OHLCVBar] = []
    t = confirm.open_ts_ms + BAR_MS
    cur = confirm.close
    for close in (px + 0.35, px + 0.55, px + 0.75, px + 0.95):
        follow.append(_bar(symbol, t, cur, close + 0.06, cur - 0.04, close, volume=150, timeframe=timeframe))
        cur = close
        t += BAR_MS
    used = 22 + 6 + len(follow)
    rest = _range(symbol, london_start + timedelta(minutes=5 * used), max(78 - used, 4), cur, 0.12, timeframe)
    ny = _range(symbol, day + timedelta(hours=13, minutes=30), 18, rest[-1].close, 0.10, timeframe)
    return asia + climb + [left, midb, right, pb1, pb2, confirm] + follow + rest + ny


def _avwap_ob_day(symbol: str, day: datetime, mid: float, timeframe: str) -> list[OHLCVBar]:
    """4h down-bar then 4h displacement (bullish OB), later pin rejection at the zone."""
    # 48 × 5m = 4h bearish HTF candle (Asia 00:00–04:00).
    down = _range(symbol, day, 48, mid + 0.6, 0.25, timeframe)
    # Force the merged 4h close below open by ending lower.
    last_down_ts = _ms(day + timedelta(minutes=5 * 47))
    down[-1] = _bar(symbol, last_down_ts, mid, mid + 0.1, mid - 1.4, mid - 1.2, volume=180, timeframe=timeframe)
    # Next 48 bars: bullish displacement (04:00–08:00, spans Asia→London).
    up_start = day + timedelta(hours=4)
    up = _range(symbol, up_start, 47, mid - 1.0, 0.20, timeframe)
    last_up_ts = _ms(up_start + timedelta(minutes=5 * 47))
    up.append(_bar(symbol, last_up_ts, mid - 0.4, mid + 2.2, mid - 0.5, mid + 2.0, volume=400, timeframe=timeframe))
    # Pullback into the bullish OB (prior 4h body around mid-1.2 … mid) with a pin.
    pb_start = day + timedelta(hours=8)
    approach = _range(symbol, pb_start, 10, mid - 0.2, 0.15, timeframe)
    pin_ts = _ms(pb_start + timedelta(minutes=5 * 10))
    pin = _bar(symbol, pin_ts, mid - 0.15, mid + 0.10, mid - 0.85, mid - 0.05, volume=220, timeframe=timeframe)
    follow: list[OHLCVBar] = []
    t = pin.open_ts_ms + BAR_MS
    px = pin.close
    for close in (mid + 0.4, mid + 0.9, mid + 1.4, mid + 2.1):
        follow.append(_bar(symbol, t, px, close + 0.08, px - 0.05, close, volume=160, timeframe=timeframe))
        px = close
        t += BAR_MS
    rest = _range(symbol, pb_start + timedelta(minutes=5 * (11 + len(follow))), 40, px, 0.15, timeframe)
    ny = _range(symbol, day + timedelta(hours=13, minutes=30), 18, rest[-1].close, 0.12, timeframe)
    return down + up + approach + [pin] + follow + rest + ny


_CYCLE = ("sweep", "fvg_pin", "po3", "s4_fade", "s5_pb", "s6_ob")


def synthetic_setup_tape(
    symbol: str = "BTCUSDT",
    *,
    cycles: int = 12,
    start_ms: int | None = None,
    start_price: float = 100.0,
    timeframe: str = "5m",
) -> list[OHLCVBar]:
    """One patterned crypto day per cycle (Asia + London + NY AM). Default TF: 5m."""
    _ = start_ms  # session clock is fixed to START so kill zones line up
    bars: list[OHLCVBar] = []
    px = start_price
    n_days = max(cycles, 6)
    for d in range(n_days):
        kind = _CYCLE[d % len(_CYCLE)]
        day = _day_start(d)
        if kind == "sweep":
            chunk = _sweep_reclaim_day(symbol, day, px, timeframe)
        elif kind == "fvg_pin":
            chunk = _fvg_day(symbol, day, px, timeframe, pin=True)
        elif kind == "fvg_engulf":
            chunk = _fvg_day(symbol, day, px, timeframe, pin=False)
        elif kind == "s4_fade":
            chunk = _sd_fade_day(symbol, day, px, timeframe)
        elif kind == "s5_pb":
            chunk = _vwap_pb_day(symbol, day, px, timeframe)
        elif kind == "s6_ob":
            chunk = _avwap_ob_day(symbol, day, px, timeframe)
        else:
            chunk = _po3_day(symbol, day, px, timeframe)
        bars.extend(chunk)
        px = chunk[-1].close
    return bars
