"""Rule-based detectors for Setups 1–3 (defaults until ML publishes params).

1. Liquidity Sweep + VWAP Reclaim → ``sweep_reclaim``
2. FVG @ VWAP / HVN            → ``fvg_entry``
3. PO3 / Judas Swing           → ``po3_judas``

Tunable knobs (walk-forward + ML report):

- ``stop_atr_mult`` — stop distance in ATR units
- ``vwap_band_sigma`` — target at VWAP ± kσ
- ``confirm_bars`` — extra closes that must hold the reclaim / displacement
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from sniper_quant.backtest.engine import BacktestSignal
from sniper_quant.models import OHLCVBar, Side
from sniper_quant.usme import atr_from_bars, check_provided_levels

SETUP_INDEX: dict[int, str] = {
    1: "sweep_reclaim",
    2: "fvg_entry",
    3: "po3_judas",
}

SETUP_NAME_TO_INDEX: dict[str, int] = {v: k for k, v in SETUP_INDEX.items()}


@dataclass(frozen=True)
class DetectorParams:
    lookback: int = 20
    range_bars: int = 12
    stop_atr_mult: float = 2.0
    vwap_band_sigma: float = 2.0
    confirm_bars: int = 1
    atr_period: int = 14
    min_rr: float = 1.5
    cooldown_bars: int = 8
    std_window: int = 20


# Grid used by walk-forward. Marked as ML-tunable in the report.
PARAM_GRID: tuple[DetectorParams, ...] = tuple(
    DetectorParams(stop_atr_mult=stop, vwap_band_sigma=band, confirm_bars=confirm)
    for stop in (1.5, 2.0, 2.5)
    for band in (1.0, 2.0, 3.0)
    for confirm in (1, 2)
)

DEFAULT_PARAMS = DetectorParams()


def parse_setup_ids(raw: str) -> list[int]:
    ids: list[int] = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        if part in SETUP_NAME_TO_INDEX:
            ids.append(SETUP_NAME_TO_INDEX[part])
            continue
        n = int(part)
        if n not in SETUP_INDEX:
            raise ValueError(f"unknown setup id {n!r}; expected 1, 2, or 3")
        ids.append(n)
    if not ids:
        raise ValueError("no setups specified")
    return ids


def typical_price(bar: OHLCVBar) -> float:
    return (bar.high + bar.low + bar.close) / 3.0


def cumulative_vwap(bars: list[OHLCVBar]) -> list[float]:
    num = 0.0
    den = 0.0
    out: list[float] = []
    for bar in bars:
        vol = bar.volume if bar.volume and bar.volume > 0 else 1.0
        num += typical_price(bar) * vol
        den += vol
        out.append(num / den if den else typical_price(bar))
    return out


def rolling_dev(values: list[float], window: int) -> list[float]:
    out: list[float] = []
    for i in range(len(values)):
        start = max(0, i - window + 1)
        chunk = values[start : i + 1]
        if len(chunk) < 2:
            out.append(abs(values[i]) * 0.01 if values[i] else 0.01)
            continue
        mean = sum(chunk) / len(chunk)
        var = sum((x - mean) ** 2 for x in chunk) / (len(chunk) - 1)
        out.append(max(var**0.5, 1e-9))
    return out


def _atr_at(bars: list[OHLCVBar], i: int, period: int) -> float:
    # Exclude the signal bar so a sweep wick does not inflate ATR / stop.
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


def _confirmed(closes: list[float], vwap: float, *, long: bool, n: int) -> bool:
    if n <= 0:
        return True
    if len(closes) < n:
        return False
    if long:
        return all(c > vwap for c in closes[:n])
    return all(c < vwap for c in closes[:n])


def _levels(
    *,
    side: Side,
    entry: float,
    atr: float,
    vwap: float,
    band_dev: float,
    params: DetectorParams,
) -> tuple[float, float] | None:
    if side is Side.LONG:
        stop = entry - params.stop_atr_mult * atr
        risk = entry - stop
        band_target = vwap + params.vwap_band_sigma * band_dev
        floor = entry + params.min_rr * risk
        # Prefer the VWAP band when it is farther (more R); else USME 1.5R floor.
        target = max(band_target, floor)
    else:
        stop = entry + params.stop_atr_mult * atr
        risk = stop - entry
        band_target = vwap - params.vwap_band_sigma * band_dev
        floor = entry - params.min_rr * risk
        target = min(band_target, floor)
    try:
        check_provided_levels(
            side=side, entry=entry, stop=stop, target=target, min_rr=params.min_rr
        )
    except ValueError:
        return None
    return stop, target


def _emit(
    *,
    bars: list[OHLCVBar],
    i: int,
    setup_type: str,
    side: Side,
    params: DetectorParams,
    vwap: float,
    band_dev: float,
) -> BacktestSignal | None:
    atr = _atr_at(bars, i, params.atr_period)
    entry = bars[i].close
    levels = _levels(
        side=side, entry=entry, atr=atr, vwap=vwap, band_dev=band_dev, params=params
    )
    if levels is None:
        return None
    stop, target = levels
    return BacktestSignal(
        ts_ms=bars[i].close_ts_ms,
        symbol=bars[i].symbol,
        setup_type=setup_type,
        side=side,
        entry=entry,
        stop=stop,
        target=target,
        atr=atr,
        signal_id=f"{setup_type}-{bars[i].symbol}-{bars[i].open_ts_ms}",
    )


def detect_sweep_reclaim(bars: list[OHLCVBar], params: DetectorParams | None = None) -> list[BacktestSignal]:
    params = params or DEFAULT_PARAMS
    if len(bars) < params.lookback + params.confirm_bars + 2:
        return []
    vwap = cumulative_vwap(bars)
    residual = [typical_price(b) - v for b, v in zip(bars, vwap)]
    dev = rolling_dev(residual, params.std_window)
    out: list[BacktestSignal] = []
    last_i = -params.cooldown_bars
    start = max(params.lookback, params.atr_period + 1)
    for i in range(start, len(bars) - params.confirm_bars):
        if i - last_i < params.cooldown_bars:
            continue
        prior = bars[i - params.lookback : i]
        swing_low = min(b.low for b in prior)
        swing_high = max(b.high for b in prior)
        bar = bars[i]
        nxt = [b.close for b in bars[i + 1 : i + 1 + params.confirm_bars]]
        sig: BacktestSignal | None = None
        if bar.low < swing_low and bar.close > swing_low and bar.close >= vwap[i]:
            if _confirmed(nxt, vwap[i], long=True, n=params.confirm_bars):
                sig = _emit(
                    bars=bars,
                    i=i,
                    setup_type="sweep_reclaim",
                    side=Side.LONG,
                    params=params,
                    vwap=vwap[i],
                    band_dev=dev[i],
                )
        elif bar.high > swing_high and bar.close < swing_high and bar.close <= vwap[i]:
            if _confirmed(nxt, vwap[i], long=False, n=params.confirm_bars):
                sig = _emit(
                    bars=bars,
                    i=i,
                    setup_type="sweep_reclaim",
                    side=Side.SHORT,
                    params=params,
                    vwap=vwap[i],
                    band_dev=dev[i],
                )
        if sig is not None:
            out.append(sig)
            last_i = i
    return out


def detect_fvg_entry(bars: list[OHLCVBar], params: DetectorParams | None = None) -> list[BacktestSignal]:
    params = params or DEFAULT_PARAMS
    if len(bars) < 4 + params.confirm_bars:
        return []
    vwap = cumulative_vwap(bars)
    residual = [typical_price(b) - v for b, v in zip(bars, vwap)]
    dev = rolling_dev(residual, params.std_window)
    out: list[BacktestSignal] = []
    last_i = -params.cooldown_bars
    start = max(2, params.atr_period + 1)
    for i in range(start, len(bars) - params.confirm_bars):
        if i - last_i < params.cooldown_bars:
            continue
        left, mid, right = bars[i - 2], bars[i - 1], bars[i]
        _ = mid
        band = params.vwap_band_sigma * dev[i]
        nxt = [b.close for b in bars[i + 1 : i + 1 + params.confirm_bars]]
        sig: BacktestSignal | None = None
        # Bullish FVG: gap between left.high and right.low.
        if left.high < right.low:
            zone_lo, zone_hi = left.high, right.low
            if zone_lo - band <= vwap[i] <= zone_hi + band:
                if _confirmed(nxt, vwap[i], long=True, n=params.confirm_bars):
                    sig = _emit(
                        bars=bars,
                        i=i,
                        setup_type="fvg_entry",
                        side=Side.LONG,
                        params=params,
                        vwap=vwap[i],
                        band_dev=dev[i],
                    )
        # Bearish FVG.
        elif left.low > right.high:
            zone_lo, zone_hi = right.high, left.low
            if zone_lo - band <= vwap[i] <= zone_hi + band:
                if _confirmed(nxt, vwap[i], long=False, n=params.confirm_bars):
                    sig = _emit(
                        bars=bars,
                        i=i,
                        setup_type="fvg_entry",
                        side=Side.SHORT,
                        params=params,
                        vwap=vwap[i],
                        band_dev=dev[i],
                    )
        if sig is not None:
            out.append(sig)
            last_i = i
    return out


def detect_po3_judas(bars: list[OHLCVBar], params: DetectorParams | None = None) -> list[BacktestSignal]:
    params = params or DEFAULT_PARAMS
    need = params.range_bars + params.confirm_bars + 2
    if len(bars) < need:
        return []
    vwap = cumulative_vwap(bars)
    residual = [typical_price(b) - v for b, v in zip(bars, vwap)]
    dev = rolling_dev(residual, params.std_window)
    out: list[BacktestSignal] = []
    last_i = -params.cooldown_bars
    start = max(params.range_bars, params.atr_period + 1)
    for i in range(start, len(bars) - params.confirm_bars):
        if i - last_i < params.cooldown_bars:
            continue
        window = bars[i - params.range_bars : i]
        range_low = min(b.low for b in window)
        range_high = max(b.high for b in window)
        mid = (range_low + range_high) / 2.0
        bar = bars[i]
        nxt = [b.close for b in bars[i + 1 : i + 1 + params.confirm_bars]]
        sig: BacktestSignal | None = None
        # Judas long: sweep range low, close back through midpoint (displacement).
        if bar.low < range_low and bar.close > mid:
            if _confirmed(nxt, vwap[i], long=True, n=params.confirm_bars):
                sig = _emit(
                    bars=bars,
                    i=i,
                    setup_type="po3_judas",
                    side=Side.LONG,
                    params=params,
                    vwap=vwap[i],
                    band_dev=dev[i],
                )
        elif bar.high > range_high and bar.close < mid:
            if _confirmed(nxt, vwap[i], long=False, n=params.confirm_bars):
                sig = _emit(
                    bars=bars,
                    i=i,
                    setup_type="po3_judas",
                    side=Side.SHORT,
                    params=params,
                    vwap=vwap[i],
                    band_dev=dev[i],
                )
        if sig is not None:
            out.append(sig)
            last_i = i
    return out


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


def with_params(base: DetectorParams | None = None, **overrides) -> DetectorParams:
    return replace(base or DEFAULT_PARAMS, **overrides)
