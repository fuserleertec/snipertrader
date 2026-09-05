"""Rule-based detectors for Setups 1–3 using locked ML parameter ranges."""

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
)
from sniper_quant.models import AssetClass, OHLCVBar, Side
from sniper_quant.usme import atr_from_bars

__all__ = [
    "DEFAULT_PARAMS",
    "SETUP_INDEX",
    "SETUP_NAME_TO_INDEX",
    "DetectorParams",
    "detect_fvg_entry",
    "detect_po3_judas",
    "detect_setup",
    "detect_sweep_reclaim",
    "grid_for",
    "parse_setup_ids",
    "with_params",
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


DETECTORS = {
    "sweep_reclaim": detect_sweep_reclaim,
    "fvg_entry": detect_fvg_entry,
    "po3_judas": detect_po3_judas,
}


def detect_setup(setup_type: str, bars: list[OHLCVBar], params: DetectorParams | None = None) -> list[BacktestSignal]:
    fn = DETECTORS.get(setup_type)
    if fn is None:
        raise ValueError(f"no detector for {setup_type!r}")
    return fn(bars, params)
