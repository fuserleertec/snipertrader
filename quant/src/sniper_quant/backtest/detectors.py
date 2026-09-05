"""Rule-based detectors for locked Setups 1–6."""

from __future__ import annotations

from sniper_quant.backtest.engine import BacktestSignal
from sniper_quant.backtest.params import (
    CONVICTION_WEIGHTS,
    DEFAULT_PARAMS,
    HARD_RR_FLOOR,
    SETUP_INDEX,
    SETUP_NAME_TO_INDEX,
    DetectorParams,
    grid_for,
    parse_setup_ids,
    with_params,
)
from sniper_quant.backtest.sessions import (
    in_kill_zone,
    session_hvn,
    session_of,
    session_range,
    session_vwap_and_dev,
    typical_price,
    utc_dt,
)
from sniper_quant.models import AssetClass, OHLCVBar, Side
from sniper_quant.news import calendar_anchor_events, in_news_window
from sniper_quant.usme import atr_from_bars

__all__ = [
    "DEFAULT_PARAMS",
    "SETUP_INDEX",
    "SETUP_NAME_TO_INDEX",
    "DetectorParams",
    "detect_avwap_ob_confluence",
    "detect_fvg_entry",
    "detect_po3_judas",
    "detect_sd_extension_fade",
    "detect_setup",
    "detect_sweep_reclaim",
    "detect_vwap_pullback_cont",
    "grid_for",
    "parse_setup_ids",
    "resample_htf",
    "with_params",
    "_apply_orchestrator",
    "_conviction",
    "_kz_aligned",
    "_s456_conviction",
    "_s6_avwap",
    "_swing_anchor_index",
]


def _atr_at(bars: list[OHLCVBar], i: int, period: int) -> float:
    end = max(i, 1)
    start = max(0, end - period - 1)
    window = bars[start:end]
    atr = atr_from_bars(
        [b.high for b in window],
        [b.low for b in window],
        [b.close for b in window],
        period=min(period, max(len(window) - 1, 1)),
    )
    if atr is None or atr <= 0:
        return max(abs(bars[i].close) * 0.01, 1e-9)
    return atr


def _avg_volume(bars: list[OHLCVBar], i: int, n: int = 20) -> float:
    window = bars[max(0, i - n) : i]
    if not window:
        return bars[i].volume or 1.0
    return sum(b.volume or 1.0 for b in window) / len(window)


def _stop_buffer(params: DetectorParams, atr: float, asset: AssetClass) -> float:
    if asset is AssetClass.FUTURES:
        return params.stop_buffer_ticks * params.tick_size
    return params.stop_buffer_atr * atr


def _rr(side: Side, entry: float, stop: float, target: float) -> float:
    risk = abs(entry - stop)
    if risk <= 0:
        return 0.0
    if side is Side.LONG:
        if stop >= entry or target <= entry:
            return 0.0
        return (target - entry) / risk
    if stop <= entry or target >= entry:
        return 0.0
    return (entry - target) / risk


def _vwap_target(
    *,
    side: Side,
    entry: float,
    stop: float,
    vwap: float,
    dev: float,
    params: DetectorParams,
) -> float | None:
    if side is Side.LONG:
        bands = [vwap + 1.0 * dev, vwap + 2.0 * dev]
    else:
        bands = [vwap - 1.0 * dev, vwap - 2.0 * dev]
    labeled = [("1", bands[0]), ("2", bands[1])]
    if params.vwap_target_band in {"1", "2"}:
        labeled = [row for row in labeled if row[0] == params.vwap_target_band]
    viable: list[tuple[float, float]] = []  # (distance, target)
    for _name, tgt in labeled:
        rr = _rr(side, entry, stop, tgt)
        if rr + 1e-12 >= params.min_rr:
            viable.append((abs(tgt - entry), tgt))
    if not viable:
        # Auto: 1σ if RR ok else 2σ — already tried; last chance is 2σ if >= 1.2
        fallback = bands[1]
        if _rr(side, entry, stop, fallback) + 1e-12 >= HARD_RR_FLOOR:
            # Still below selected min_rr → discard (1.2 is hard floor only after adjust).
            return None
        return None
    viable.sort(key=lambda row: row[0])  # nearer band that clears min_rr
    target = viable[0][1]
    if _rr(side, entry, stop, target) + 1e-12 < HARD_RR_FLOOR:
        return None
    return target


def _conviction(
    *,
    confluence: float,
    volume_ok: bool,
    kill_ok: bool,
) -> float:
    score = (
        CONVICTION_WEIGHTS["confluence_count"] * max(0.0, min(confluence, 1.0))
        + CONVICTION_WEIGHTS["volume_confirm"] * (1.0 if volume_ok else 0.0)
        + CONVICTION_WEIGHTS["kill_zone_align"] * (1.0 if kill_ok else 0.0)
    )
    return score  # 0–100


def _kz_aligned(bar: OHLCVBar, params: DetectorParams) -> bool:
    """True when the bar sits in the resolved kill zone (S4–S6 bonus)."""
    return in_kill_zone(bar, params.resolved_kill_zone(bar.asset_class))


def _s456_conviction(
    *,
    confluence: float,
    volume_ok: bool,
    bar: OHLCVBar,
    params: DetectorParams,
) -> float:
    """S4–S6 conviction including the kill-zone bonus (not a hard gate here)."""
    return _conviction(
        confluence=confluence,
        volume_ok=volume_ok,
        kill_ok=_kz_aligned(bar, params),
    )


def _apply_orchestrator(
    signals: list[BacktestSignal],
    params: DetectorParams,
) -> list[BacktestSignal]:
    keep: list[BacktestSignal] = []
    last_ts: dict[tuple[str, str], int] = {}
    min_conf = params.min_conviction / 100.0
    window_ms = params.dedupe_window_sec * 1000
    for sig in sorted(signals, key=lambda s: s.ts_ms):
        if sig.confidence is not None and sig.confidence + 1e-12 < min_conf:
            continue
        key = (sig.symbol, sig.setup_type)
        prev = last_ts.get(key)
        if prev is not None and sig.ts_ms - prev < window_ms:
            continue
        last_ts[key] = sig.ts_ms
        keep.append(sig)
    return keep


def _is_engulfing(prev: OHLCVBar, bar: OHLCVBar, *, long: bool) -> bool:
    if long:
        return bar.close > bar.open and bar.close >= prev.high and bar.open <= prev.low
    return bar.close < bar.open and bar.close <= prev.low and bar.open >= prev.high


def _is_pin(bar: OHLCVBar, *, long: bool, ratio: float) -> bool:
    body = abs(bar.close - bar.open)
    if body <= 1e-12:
        body = 1e-12
    if long:
        wick = min(bar.open, bar.close) - bar.low
    else:
        wick = bar.high - max(bar.open, bar.close)
    return wick / body >= ratio


def detect_sweep_reclaim(bars: list[OHLCVBar], params: DetectorParams | None = None) -> list[BacktestSignal]:
    params = params or DEFAULT_PARAMS
    look = params.mss_swing_lookback
    need = look + params.max_bars_sweep_to_mss + params.atr_period + 2
    if len(bars) < need:
        return []
    vwap, dev = session_vwap_and_dev(bars)
    out: list[BacktestSignal] = []
    i = max(look, params.atr_period + 1)
    while i < len(bars) - 1:
        prior = bars[i - look : i]
        swing_low = min(b.low for b in prior)
        swing_high = max(b.high for b in prior)
        bar = bars[i]
        atr_here = _atr_at(bars, i, params.atr_period)
        swept_low = bar.low < swing_low - 0.35 * atr_here
        swept_high = bar.high > swing_high + 0.35 * atr_here
        confirmed_low = swept_low and bar.close > swing_low
        confirmed_high = swept_high and bar.close < swing_high
        if params.require_confirmed_sweep:
            ok_long, ok_short = confirmed_low, confirmed_high
        else:
            ok_long, ok_short = swept_low, swept_high
        side: Side | None = None
        extreme = 0.0
        if ok_long:
            side = Side.LONG
            extreme = bar.low
        elif ok_short:
            side = Side.SHORT
            extreme = bar.high
        if side is None:
            i += 1
            continue
        mss_high = swing_high
        mss_low = swing_low
        mss_i = None
        sweep_sess = session_of(bar)
        end = min(len(bars), i + 1 + params.max_bars_sweep_to_mss)
        for j in range(i + 1, end):
            if session_of(bars[j]) != sweep_sess:
                continue
            if side is Side.LONG and bars[j].close > mss_high:
                mss_i = j
                break
            if side is Side.SHORT and bars[j].close < mss_low:
                mss_i = j
                break
        if mss_i is None:
            i += 1
            continue
        fill = bars[mss_i]
        # Reclaim: MSS close back through the extreme and on the VWAP side.
        if side is Side.LONG and not (fill.close > extreme and fill.close >= vwap[mss_i]):
            i += 1
            continue
        if side is Side.SHORT and not (fill.close < extreme and fill.close <= vwap[mss_i]):
            i += 1
            continue
        atr = _atr_at(bars, mss_i, params.atr_period)
        buf = _stop_buffer(params, atr, fill.asset_class)
        entry = fill.close
        stop = extreme - buf if side is Side.LONG else extreme + buf
        target = _vwap_target(
            side=side,
            entry=entry,
            stop=stop,
            vwap=vwap[mss_i],
            dev=dev[mss_i],
            params=params,
        )
        if target is None:
            i += 1
            continue
        vol_ok = fill.volume >= 1.1 * _avg_volume(bars, mss_i)
        kill = params.resolved_kill_zone(fill.asset_class)
        factors = 0.0
        factors += 1.0  # sweep
        factors += 1.0  # mss
        factors += 1.0 if (side is Side.LONG and fill.close >= vwap[mss_i]) or (
            side is Side.SHORT and fill.close <= vwap[mss_i]
        ) else 0.0
        conv = _conviction(confluence=factors / 3.0, volume_ok=vol_ok, kill_ok=in_kill_zone(fill, kill))
        out.append(
            BacktestSignal(
                ts_ms=fill.close_ts_ms,
                symbol=fill.symbol,
                setup_type="sweep_reclaim",
                side=side,
                entry=entry,
                stop=stop,
                target=target,
                atr=atr,
                signal_id=f"sweep_reclaim-{fill.symbol}-{fill.open_ts_ms}",
                confidence=conv / 100.0,
            )
        )
        i = mss_i + 1
    return _apply_orchestrator(out, params)


def detect_fvg_entry(bars: list[OHLCVBar], params: DetectorParams | None = None) -> list[BacktestSignal]:
    params = params or DEFAULT_PARAMS
    if len(bars) < params.atr_period + 6:
        return []
    vwap, _dev = session_vwap_and_dev(bars)
    out: list[BacktestSignal] = []
    last_i = -10**9
    for i in range(max(2, params.atr_period + 1), len(bars) - 2):
        left, mid, right = bars[i - 2], bars[i - 1], bars[i]
        _ = mid
        confirm = bars[i + 1]
        age_h = (confirm.close_ts_ms - left.open_ts_ms) / 3_600_000.0
        if age_h > params.max_fvg_age_hours:
            continue
        bull = left.high < right.low
        bear = left.low > right.high
        if not bull and not bear:
            continue
        side = Side.LONG if bull else Side.SHORT
        zone_lo, zone_hi = (left.high, right.low) if bull else (right.high, left.low)
        atr = _atr_at(bars, i + 1, params.atr_period)
        tol = params.fvg_overlap_tol_atr * atr
        vwap_hit = (zone_lo - tol) <= vwap[i] <= (zone_hi + tol)
        hvn = session_hvn(bars, i)
        hvn_hit = hvn is not None and (zone_lo - tol) <= hvn <= (zone_hi + tol)
        mode = params.confluence_mode
        if mode == "vwap_touch" and not vwap_hit:
            continue
        if mode == "hvn_overlap" and not hvn_hit:
            continue
        if mode == "vwap_or_hvn" and not (vwap_hit or hvn_hit):
            continue
        if mode == "vwap_and_hvn" and not (vwap_hit and hvn_hit):
            continue
        prev = right
        engulf = _is_engulfing(prev, confirm, long=bull)
        pin = _is_pin(confirm, long=bull, ratio=params.pin_wick_ratio)
        if params.confirmation == "engulfing" and not engulf:
            continue
        if params.confirmation == "pin_bar" and not pin:
            continue
        if params.confirmation == "either" and not (engulf or pin):
            continue
        if params.entry_mode == "zone_boundary":
            entry = zone_hi if bull else zone_lo
        else:
            entry = confirm.close
        buf = params.fvg_stop_buffer_atr * atr
        stop = (zone_lo - buf) if bull else (zone_hi + buf)
        risk = abs(entry - stop)
        if risk <= 0:
            continue
        if params.target_mode == "1.5R":
            target = entry + 1.5 * risk if bull else entry - 1.5 * risk
        elif params.target_mode == "2R":
            target = entry + 2.0 * risk if bull else entry - 2.0 * risk
        else:
            look = bars[max(0, i - 20) : i]
            if bull:
                swing = max(b.high for b in look)
                target = swing
            else:
                swing = min(b.low for b in look)
                target = swing
            if _rr(side, entry, stop, target) + 1e-12 < params.min_rr:
                target = entry + 2.0 * risk if bull else entry - 2.0 * risk
        if _rr(side, entry, stop, target) + 1e-12 < HARD_RR_FLOOR:
            continue
        if _rr(side, entry, stop, target) + 1e-12 < params.min_rr:
            continue
        vol_ok = confirm.volume >= 1.1 * _avg_volume(bars, i + 1)
        kill = params.resolved_kill_zone(confirm.asset_class)
        conf_n = (1.0 if vwap_hit else 0.0) + (1.0 if hvn_hit else 0.0) + 1.0
        conv = _conviction(confluence=conf_n / 3.0, volume_ok=vol_ok, kill_ok=in_kill_zone(confirm, kill))
        if i - last_i < 3:
            continue
        out.append(
            BacktestSignal(
                ts_ms=confirm.close_ts_ms,
                symbol=confirm.symbol,
                setup_type="fvg_entry",
                side=side,
                entry=entry,
                stop=stop,
                target=target,
                atr=atr,
                signal_id=f"fvg_entry-{confirm.symbol}-{confirm.open_ts_ms}",
                confidence=conv / 100.0,
            )
        )
        last_i = i
    return _apply_orchestrator(out, params)


def _band_tagged(bar: OHLCVBar, vwap: float, dev: float, mode: str) -> bool:
    if mode == "none":
        return True
    tag1 = bar.low <= vwap + dev and bar.high >= vwap - dev
    tag2 = bar.low <= vwap + 2 * dev and bar.high >= vwap - 2 * dev
    # "tag" the outer band more strictly: wick reaches vwap±kσ
    reach1 = bar.low <= vwap - dev or bar.high >= vwap + dev
    reach2 = bar.low <= vwap - 2 * dev or bar.high >= vwap + 2 * dev
    if mode == "1s":
        return reach1 or tag1
    if mode == "2s":
        return reach2
    if mode == "either":
        return reach1 or reach2 or tag1
    return True


def detect_po3_judas(bars: list[OHLCVBar], params: DetectorParams | None = None) -> list[BacktestSignal]:
    params = params or DEFAULT_PARAMS
    if len(bars) < params.atr_period + 8:
        return []
    vwap, dev = session_vwap_and_dev(bars)
    out: list[BacktestSignal] = []
    i = params.atr_period + 1
    while i < len(bars):
        bar = bars[i]
        kill = params.resolved_kill_zone(bar.asset_class)
        if not in_kill_zone(bar, kill):
            i += 1
            continue
        accum = params.accumulation_session
        rng = session_range(bars, i, accum)
        if rng is None:
            i += 1
            continue
        acc_lo, acc_hi = rng
        swept_low = bar.low < acc_lo
        swept_high = bar.high > acc_hi
        if not swept_low and not swept_high:
            i += 1
            continue
        side = Side.LONG if swept_low else Side.SHORT
        wick = bar.low if side is Side.LONG else bar.high
        disp_i = None
        end = min(len(bars), i + 1 + params.max_bars_sweep_to_displace)
        for j in range(i, end):
            body = abs(bars[j].close - bars[j].open)
            atr = _atr_at(bars, j, params.atr_period)
            if body + 1e-12 < params.displacement_min_body_atr * atr:
                continue
            if side is Side.LONG and bars[j].close <= bars[j].open:
                continue
            if side is Side.SHORT and bars[j].close >= bars[j].open:
                continue
            if not _band_tagged(bars[j], vwap[j], dev[j], params.require_band_tag):
                continue
            disp_i = j
            break
        if disp_i is None:
            i += 1
            continue
        fill = bars[disp_i]
        atr = _atr_at(bars, disp_i, params.atr_period)
        buf = params.po3_stop_buffer_atr * atr
        entry = fill.close
        stop = wick - buf if side is Side.LONG else wick + buf
        mid = (acc_lo + acc_hi) / 2.0
        if params.partial_mid:
            target = mid
        else:
            target = acc_hi if side is Side.LONG else acc_lo
        if _rr(side, entry, stop, target) + 1e-12 < HARD_RR_FLOOR:
            i = disp_i + 1
            continue
        if _rr(side, entry, stop, target) + 1e-12 < params.min_rr:
            i = disp_i + 1
            continue
        vol_ok = fill.volume >= 1.1 * _avg_volume(bars, disp_i)
        factors = 1.0 + 1.0  # sweep + displace
        factors += 0.0 if params.require_band_tag == "none" else 1.0
        conv = _conviction(confluence=factors / 3.0, volume_ok=vol_ok, kill_ok=True)
        out.append(
            BacktestSignal(
                ts_ms=fill.close_ts_ms,
                symbol=fill.symbol,
                setup_type="po3_judas",
                side=side,
                entry=entry,
                stop=stop,
                target=target,
                atr=atr,
                signal_id=f"po3_judas-{fill.symbol}-{fill.open_ts_ms}",
                confidence=conv / 100.0,
            )
        )
        i = disp_i + 2
    return _apply_orchestrator(out, params)


def _is_strong_body(bar: OHLCVBar, *, long: bool) -> bool:
    rng = bar.high - bar.low
    if rng <= 1e-12:
        return False
    body = abs(bar.close - bar.open)
    if body / rng < 0.6:
        return False
    return (bar.close > bar.open) if long else (bar.close < bar.open)


def _mss_shift(bars: list[OHLCVBar], i: int, *, long: bool, look: int = 5) -> bool:
    prior = bars[max(0, i - look) : i]
    if not prior:
        return False
    if long:
        return bars[i].close > max(b.high for b in prior)
    return bars[i].close < min(b.low for b in prior)


def _s4_confirm(prev: OHLCVBar, bar: OHLCVBar, bars: list[OHLCVBar], i: int, *, long: bool, params: DetectorParams) -> bool:
    engulf = _is_engulfing(prev, bar, long=long)
    pin = _is_pin(bar, long=long, ratio=params.pin_wick_ratio)
    mss = _mss_shift(bars, i, long=long)
    mode = params.s4_confirm
    if mode == "engulfing":
        return engulf
    if mode == "pin":
        return pin
    if mode == "mss_1m5m":
        return mss
    return engulf or pin or mss


def _band_extension(bar: OHLCVBar, vwap: float, dev: float, *, long: bool) -> float:
    """How many σ the wick reached beyond VWAP (signed by fade side)."""
    if dev <= 1e-12:
        return 0.0
    if long:
        return (vwap - bar.low) / dev
    return (bar.high - vwap) / dev


def detect_sd_extension_fade(bars: list[OHLCVBar], params: DetectorParams | None = None) -> list[BacktestSignal]:
    """Setup 4 — fade a 2σ/3σ session-band tag back to session VWAP."""
    params = params or DEFAULT_PARAMS
    if len(bars) < params.atr_period + 8:
        return []
    vwap, dev = session_vwap_and_dev(bars)
    out: list[BacktestSignal] = []
    i = max(params.atr_period + 2, 3)
    while i < len(bars) - 1:
        bar = bars[i]
        if in_news_window(bar.close_ts_ms, symbol=bar.symbol, skip_minutes=params.news_skip_minutes):
            i += 1
            continue
        if not in_kill_zone(bar, params.resolved_kill_zone(bar.asset_class)):
            i += 1
            continue
        prev_v, prev_d = vwap[i - 1], dev[i - 1]
        if prev_d <= 1e-12:
            i += 1
            continue
        ext_long = _band_extension(bar, prev_v, prev_d, long=True)
        ext_short = _band_extension(bar, prev_v, prev_d, long=False)
        trigger = params.s4_band_trigger
        side: Side | None = None
        tagged_sigma = 0.0
        if trigger == "2s":
            if 2.0 <= ext_long < 3.0:
                side, tagged_sigma = Side.LONG, ext_long
            elif 2.0 <= ext_short < 3.0:
                side, tagged_sigma = Side.SHORT, ext_short
        elif trigger == "3s":
            if ext_long >= 3.0:
                side, tagged_sigma = Side.LONG, ext_long
            elif ext_short >= 3.0:
                side, tagged_sigma = Side.SHORT, ext_short
        else:  # either ≥2σ
            if ext_long >= 2.0:
                side, tagged_sigma = Side.LONG, ext_long
            elif ext_short >= 2.0:
                side, tagged_sigma = Side.SHORT, ext_short
        if side is None:
            i += 1
            continue
        avg_vol = _avg_volume(bars, i, params.s4_vol_avg_period)
        if bar.volume > params.s4_vol_max_frac * avg_vol + 1e-12:
            i += 1
            continue
        confirm = bars[i + 1]
        if not _s4_confirm(bar, confirm, bars, i + 1, long=side is Side.LONG, params=params):
            i += 1
            continue
        atr = _atr_at(bars, i + 1, params.atr_period)
        band3 = prev_v - 3.0 * prev_d if side is Side.LONG else prev_v + 3.0 * prev_d
        buf = params.s4_stop_buffer_atr * atr
        entry = confirm.close
        stop = band3 - buf if side is Side.LONG else band3 + buf
        target = vwap[i + 1]
        need_rr = params.s4_min_rr_at_3s if tagged_sigma >= 3.0 else params.s4_min_rr
        if _rr(side, entry, stop, target) + 1e-12 < HARD_RR_FLOOR:
            i += 1
            continue
        if _rr(side, entry, stop, target) + 1e-12 < need_rr:
            i += 1
            continue
        vol_ok = confirm.volume >= 1.1 * _avg_volume(bars, i + 1)
        conv = _s456_conviction(confluence=1.0, volume_ok=vol_ok, bar=confirm, params=params)
        out.append(
            BacktestSignal(
                ts_ms=confirm.close_ts_ms,
                symbol=confirm.symbol,
                setup_type="sd_extension_fade",
                side=side,
                entry=entry,
                stop=stop,
                target=target,
                atr=atr,
                signal_id=f"sd_extension_fade-{confirm.symbol}-{confirm.open_ts_ms}",
                confidence=max(conv / 100.0, 0.60),
            )
        )
        i = i + 3
    orch = params if params.min_conviction <= 60 else with_params(params, min_conviction=60)
    return _apply_orchestrator(out, orch)


def _local_fvg_or_ob(bars: list[OHLCVBar], i: int, *, long: bool) -> bool:
    lo = max(2, i - 12)
    for k in range(lo, i):
        left, right = bars[k - 2], bars[k]
        if long and left.high < right.low:
            return True
        if not long and left.low > right.high:
            return True
    if i >= 2:
        impulse, prior = bars[i - 1], bars[i - 2]
        if long and impulse.close > impulse.open and prior.close < prior.open:
            return True
        if not long and impulse.close < impulse.open and prior.close > prior.open:
            return True
    return False


def _touched_pullback(bar: OHLCVBar, vwap: float, dev: float, level: str, *, long: bool) -> bool:
    band = vwap - dev if long else vwap + dev
    hit_vwap = bar.low <= vwap <= bar.high
    hit_band = bar.low <= band <= bar.high
    if level == "vwap":
        return hit_vwap
    if level == "band_1s":
        return hit_band
    return hit_vwap or hit_band


def _away_from_pullback(bar: OHLCVBar, vwap: float, dev: float, *, long: bool) -> bool:
    pad = 0.35 * max(dev, 1e-9)
    if long:
        return bar.close > vwap + pad
    return bar.close < vwap - pad


def detect_vwap_pullback_cont(bars: list[OHLCVBar], params: DetectorParams | None = None) -> list[BacktestSignal]:
    """Setup 5 — with-trend pullback to VWAP / 1σ, first touch, OB or FVG."""
    params = params or DEFAULT_PARAMS
    look = params.s5_trend_lookback_bars
    if len(bars) < look + params.atr_period + 6:
        return []
    vwap, dev = session_vwap_and_dev(bars)
    out: list[BacktestSignal] = []
    i = look + 1
    while i < len(bars) - 1:
        now, then = bars[i], bars[i - look]
        if then.close <= 0:
            i += 1
            continue
        up = now.close > then.close
        down = now.close < then.close
        if not up and not down:
            i += 1
            continue
        long = up
        side = Side.LONG if long else Side.SHORT
        window = params.s5_first_touch_window_bars
        touch_i = None
        for k in range(max(look + 3, i - window), i + 1):
            if not _touched_pullback(bars[k], vwap[k], dev[k], params.s5_pullback_level, long=long):
                continue
            prior = bars[max(look, k - 3) : k]
            if prior and all(
                _away_from_pullback(b, vwap[j], dev[j], long=long)
                for j, b in zip(range(k - len(prior), k), prior)
            ):
                touch_i = k
                break
        if touch_i is None or i - touch_i > window:
            i += 1
            continue
        confirm = bars[i]
        engulf = _is_engulfing(bars[i - 1], confirm, long=long)
        strong = _is_strong_body(confirm, long=long)
        if not (engulf or strong):
            i += 1
            continue
        if params.s5_require_ob_or_fvg and not _local_fvg_or_ob(bars, i, long=long):
            i += 1
            continue
        pullback = bars[touch_i : i + 1]
        impulse = bars[max(0, i - look) : touch_i] or bars[max(0, i - look) : i]
        swing_ext = min(b.low for b in pullback) if long else max(b.high for b in pullback)
        prior_liq = max(b.high for b in impulse) if long else min(b.low for b in impulse)
        atr = _atr_at(bars, i, params.atr_period)
        buf = params.s5_stop_buffer_atr * atr
        entry = confirm.close
        stop = swing_ext - buf if long else swing_ext + buf
        target = prior_liq
        if _rr(side, entry, stop, target) + 1e-12 < params.s5_min_rr:
            i += 1
            continue
        if _rr(side, entry, stop, target) + 1e-12 < HARD_RR_FLOOR:
            i += 1
            continue
        vol_ok = confirm.volume >= 1.1 * _avg_volume(bars, i)
        conv = _s456_conviction(confluence=1.0, volume_ok=vol_ok, bar=confirm, params=params)
        out.append(
            BacktestSignal(
                ts_ms=confirm.close_ts_ms,
                symbol=confirm.symbol,
                setup_type="vwap_pullback_cont",
                side=side,
                entry=entry,
                stop=stop,
                target=target,
                atr=atr,
                signal_id=f"vwap_pullback_cont-{confirm.symbol}-{confirm.open_ts_ms}",
                confidence=max(conv / 100.0, 0.60),
            )
        )
        i += params.s5_first_touch_window_bars + 2
    return _apply_orchestrator(out, params)


HTF_GROUP_5M: dict[str, int] = {"1h": 12, "4h": 48, "1d": 288}


def resample_htf(bars: list[OHLCVBar], timeframe: str) -> list[OHLCVBar]:
    """Synthesize HTF bars from 5m (12≈1h, 48≈4h, calendar day≈1d)."""
    if not bars:
        return []
    if timeframe == "1d":
        groups: dict[str, list[OHLCVBar]] = {}
        for bar in bars:
            key = utc_dt(bar.open_ts_ms).date().isoformat()
            groups.setdefault(key, []).append(bar)
        return [_merge_bars(chunk, "1d") for chunk in groups.values() if len(chunk) >= 2]
    n = HTF_GROUP_5M.get(timeframe)
    if n is None:
        return list(bars)
    out: list[OHLCVBar] = []
    for i in range(0, len(bars), n):
        chunk = bars[i : i + n]
        if len(chunk) < max(n // 2, 2):
            continue
        out.append(_merge_bars(chunk, timeframe))
    return out


def _merge_bars(chunk: list[OHLCVBar], timeframe: str) -> OHLCVBar:
    return OHLCVBar(
        symbol=chunk[0].symbol,
        asset_class=chunk[0].asset_class,
        timeframe=timeframe,
        open_ts_ms=chunk[0].open_ts_ms,
        close_ts_ms=chunk[-1].close_ts_ms,
        open=chunk[0].open,
        high=max(b.high for b in chunk),
        low=min(b.low for b in chunk),
        close=chunk[-1].close,
        volume=sum(b.volume or 0.0 for b in chunk),
        n_ticks=sum(b.n_ticks or 0 for b in chunk),
    )


def _bar_index_at_or_after(bars: list[OHLCVBar], ts_ms: int) -> int:
    return next((k for k, bar in enumerate(bars) if bar.open_ts_ms >= ts_ms), 0)


def _swing_anchor_index(
    bars: list[OHLCVBar],
    i: int,
    lookback: int,
    *,
    kind: str,
) -> int | None:
    start = max(0, i - lookback)
    window = bars[start:i]
    if len(window) < 3:
        return None
    if kind == "swing_high":
        return start + max(range(len(window)), key=lambda k: window[k].high)
    return start + min(range(len(window)), key=lambda k: window[k].low)


def _s6_avwap(
    bars: list[OHLCVBar],
    i: int,
    origin_ts: int,
    params: DetectorParams,
) -> float:
    """AVWAP from OB origin and/or swing_high/low / earnings/news stubs."""
    allowed = params.resolved_s6_anchors()
    starts: list[int] = []
    if "ob" in allowed:
        starts.append(_bar_index_at_or_after(bars, origin_ts))
    look = params.s6_swing_lookback
    if "swing_high" in allowed:
        idx = _swing_anchor_index(bars, i, look, kind="swing_high")
        if idx is not None:
            starts.append(idx)
    if "swing_low" in allowed:
        idx = _swing_anchor_index(bars, i, look, kind="swing_low")
        if idx is not None:
            starts.append(idx)
    kinds = tuple(k for k in ("earnings", "news") if k in allowed)
    if kinds:
        for event in calendar_anchor_events(bars[i].open_ts_ms, kinds=kinds):
            starts.append(_bar_index_at_or_after(bars, event.ts_ms))
    starts = [s for s in dict.fromkeys(starts) if 0 <= s < i]
    if not starts:
        starts = [_bar_index_at_or_after(bars, origin_ts)]
    price = bars[i].close
    vwaps = [_anchored_vwap(bars, s, i) for s in starts]
    return min(vwaps, key=lambda v: abs(v - price))


def _anchored_vwap(bars: list[OHLCVBar], start: int, end: int) -> float:
    num = 0.0
    den = 0.0
    for bar in bars[start : end + 1]:
        vol = bar.volume if bar.volume and bar.volume > 0 else 1.0
        num += typical_price(bar) * vol
        den += vol
    return num / den if den else typical_price(bars[end])


def _find_htf_obs(htf: list[OHLCVBar]) -> list[tuple[Side, float, float, int, int]]:
    """(side, lo, hi, htf_index, origin_open_ts_ms)."""
    obs: list[tuple[Side, float, float, int, int]] = []
    for i in range(1, len(htf)):
        prev, cur = htf[i - 1], htf[i]
        rng = max(cur.high - cur.low, 1e-9)
        body = abs(cur.close - cur.open)
        if body < 0.35 * rng:
            continue
        if cur.close > cur.open and prev.close < prev.open:
            obs.append((Side.LONG, min(prev.open, prev.close), max(prev.open, prev.close), i - 1, prev.open_ts_ms))
        if cur.close < cur.open and prev.close > prev.open:
            obs.append((Side.SHORT, min(prev.open, prev.close), max(prev.open, prev.close), i - 1, prev.open_ts_ms))
    return obs


def detect_avwap_ob_confluence(bars: list[OHLCVBar], params: DetectorParams | None = None) -> list[BacktestSignal]:
    """Setup 6 — HTF OB + AVWAP approach, rejection/MSS on 1h or 4h."""
    params = params or DEFAULT_PARAMS
    if len(bars) < 60:
        return []
    htf_ob = resample_htf(bars, params.s6_ob_timeframe)
    htf_cf = resample_htf(bars, params.s6_confirm_tf)
    if len(htf_ob) < 2:
        return []
    obs = _find_htf_obs(htf_ob)
    if not obs:
        return []
    out: list[BacktestSignal] = []
    last_i = -10**9
    for i in range(params.atr_period + 2, len(bars) - 1):
        bar = bars[i]
        atr = _atr_at(bars, i, params.atr_period)
        tol = params.s6_approach_tol_atr * atr
        hit = None
        for side, lo, hi, _idx, origin_ts in reversed(obs):
            if origin_ts >= bar.open_ts_ms:
                continue
            near = (lo - tol) <= bar.close <= (hi + tol) or (lo - tol) <= typical_price(bar) <= (hi + tol)
            if not near:
                continue
            avwap = _s6_avwap(bars, i, origin_ts, params)
            if abs(bar.close - avwap) > 1.5 * atr and not ((lo - tol) <= avwap <= (hi + tol)):
                continue
            hit = (side, lo, hi, avwap)
            break
        if hit is None:
            continue
        side, lo, hi, _avwap = hit
        long = side is Side.LONG
        confirm_ok = False
        if params.s6_confirm == "rejection":
            confirm_ok = _is_pin(bar, long=long, ratio=max(params.pin_wick_ratio, 2.0))
        elif params.s6_confirm == "mss":
            ref = htf_cf or htf_ob
            prior = [h for h in ref if h.close_ts_ms <= bar.close_ts_ms]
            if len(prior) >= 3:
                confirm_ok = _mss_shift(prior, len(prior) - 1, long=long, look=2)
        else:
            confirm_ok = _is_pin(bar, long=long, ratio=2.0) or _mss_shift(bars, i, long=long)
        if not confirm_ok:
            continue
        buf = params.s6_stop_buffer_atr * atr
        entry = bar.close
        stop = (lo - buf) if long else (hi + buf)
        lookback = [b for b in bars[:i] if b.open_ts_ms >= bars[max(0, i - 80)].open_ts_ms]
        if not lookback:
            continue
        target = max(b.high for b in lookback) if long else min(b.low for b in lookback)
        if _rr(side, entry, stop, target) + 1e-12 < params.s6_min_rr:
            continue
        if i - last_i < 8:
            continue
        vol_ok = bar.volume >= 1.1 * _avg_volume(bars, i)
        conv = _s456_conviction(confluence=1.0, volume_ok=vol_ok, bar=bar, params=params)
        conf = max(conv / 100.0, params.s6_min_conviction / 100.0)
        out.append(
            BacktestSignal(
                ts_ms=bar.close_ts_ms,
                symbol=bar.symbol,
                setup_type="avwap_ob_confluence",
                side=side,
                entry=entry,
                stop=stop,
                target=target,
                atr=atr,
                signal_id=f"avwap_ob_confluence-{bar.symbol}-{bar.open_ts_ms}",
                confidence=conf,
            )
        )
        last_i = i
    orch = with_params(params, min_conviction=params.s6_min_conviction)
    return _apply_orchestrator(out, orch)


DETECTORS = {
    "sweep_reclaim": detect_sweep_reclaim,
    "fvg_entry": detect_fvg_entry,
    "po3_judas": detect_po3_judas,
    "sd_extension_fade": detect_sd_extension_fade,
    "vwap_pullback_cont": detect_vwap_pullback_cont,
    "avwap_ob_confluence": detect_avwap_ob_confluence,
}


def detect_setup(setup_type: str, bars: list[OHLCVBar], params: DetectorParams | None = None) -> list[BacktestSignal]:
    fn = DETECTORS.get(setup_type)
    if fn is None:
        raise ValueError(f"no detector for {setup_type!r}")
    return fn(bars, params)
