"""DE-aligned session clocks + session-anchored VWAP (not weekly/rolling)."""

from __future__ import annotations

from datetime import datetime, time, timezone
from zoneinfo import ZoneInfo

from sniper_quant.models import AssetClass, OHLCVBar

UTC = timezone.utc
NY = ZoneInfo("America/New_York")


def utc_dt(ts_ms: int) -> datetime:
    return datetime.fromtimestamp(ts_ms / 1000.0, tz=UTC)


def crypto_session(ts_ms: int) -> str | None:
    tod = utc_dt(ts_ms).timetz().replace(tzinfo=None)
    if time(0, 0) <= tod < time(7, 0):
        return "asia"
    if time(7, 0) <= tod < time(13, 30):
        return "london"
    if time(13, 30) <= tod < time(15, 0):
        return "ny_am"
    if time(18, 0) <= tod < time(20, 0):
        return "ny_pm"
    return None


def in_globex(ts_ms: int) -> bool:
    tod = utc_dt(ts_ms).astimezone(NY).time()
    return tod >= time(18, 0) or tod < time(9, 30)


def session_of(bar: OHLCVBar) -> str | None:
    if bar.asset_class is AssetClass.FUTURES and in_globex(bar.open_ts_ms):
        # Globex wraps; during RTH we still prefer crypto-style labels if needed.
        crypto = crypto_session(bar.open_ts_ms)
        return crypto or "globex"
    return crypto_session(bar.open_ts_ms)


def session_key(bar: OHLCVBar) -> str:
    sess = session_of(bar) or "off"
    day = utc_dt(bar.open_ts_ms).date().isoformat()
    return f"{day}:{sess}"


def typical_price(bar: OHLCVBar) -> float:
    return (bar.high + bar.low + bar.close) / 3.0


def session_vwap_and_dev(bars: list[OHLCVBar]) -> tuple[list[float], list[float]]:
    """Session-anchored VWAP + expanding residual σ (ML: session only)."""
    vwaps: list[float] = []
    devs: list[float] = []
    num: dict[str, float] = {}
    den: dict[str, float] = {}
    residuals: dict[str, list[float]] = {}
    for bar in bars:
        key = session_key(bar)
        vol = bar.volume if bar.volume and bar.volume > 0 else 1.0
        num[key] = num.get(key, 0.0) + typical_price(bar) * vol
        den[key] = den.get(key, 0.0) + vol
        vwap = num[key] / den[key] if den[key] else typical_price(bar)
        resid = typical_price(bar) - vwap
        bucket = residuals.setdefault(key, [])
        bucket.append(resid)
        if len(bucket) < 2:
            dev = max(abs(bar.close) * 0.004, 1e-9)
        else:
            mean = sum(bucket) / len(bucket)
            var = sum((x - mean) ** 2 for x in bucket) / (len(bucket) - 1)
            dev = max(var**0.5, 1e-9)
        vwaps.append(vwap)
        devs.append(dev)
    return vwaps, devs


def session_hvn(bars: list[OHLCVBar], i: int, *, bins: int = 16) -> float | None:
    """Highest-volume price in the current session (simple VP HVN)."""
    key = session_key(bars[i])
    window = [b for b in bars[: i + 1] if session_key(b) == key]
    if len(window) < 4:
        return None
    lo = min(b.low for b in window)
    hi = max(b.high for b in window)
    if hi <= lo:
        return window[-1].close
    width = (hi - lo) / bins
    vol_bins = [0.0] * bins
    for b in window:
        idx = min(int((typical_price(b) - lo) / width), bins - 1)
        vol_bins[idx] += b.volume or 1.0
    best = max(range(bins), key=lambda k: vol_bins[k])
    return lo + (best + 0.5) * width


def in_kill_zone(bar: OHLCVBar, kill: str) -> bool:
    sess = session_of(bar)
    if kill == "either":
        return sess in {"london", "ny_am"}
    return sess == kill


def session_range(bars: list[OHLCVBar], i: int, session_name: str) -> tuple[float, float] | None:
    """High/low of ``session_name`` on the same UTC day as bar i."""
    day = utc_dt(bars[i].open_ts_ms).date()
    chunk = [
        b
        for b in bars[: i + 1]
        if utc_dt(b.open_ts_ms).date() == day and session_of(b) == session_name
    ]
    if session_name == "globex":
        chunk = [
            b
            for b in bars[: i + 1]
            if in_globex(b.open_ts_ms) and abs(b.open_ts_ms - bars[i].open_ts_ms) < 20 * 3_600_000
        ]
    if not chunk:
        return None
    return min(b.low for b in chunk), max(b.high for b in chunk)
