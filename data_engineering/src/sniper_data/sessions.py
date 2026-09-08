"""Asset-class session windows. Times are never hardcoded to 00:00 UTC for all assets.

Crypto (UTC):
  Asia   00:00–07:00
  London 07:00–13:30
  NY AM  13:30–15:00
  NY PM  18:00–20:00

US Equities (America/New_York, DST via zoneinfo):
  RTH 09:30–16:00
  ETH 04:00–20:00

CME futures (America/New_York):
  RTH    09:30–16:00
  Globex 18:00–09:30 (wraps midnight)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from sniper_data.config import NY_TZ
from sniper_data.models import AssetClass, SessionLevels, SessionType
from sniper_data.symbols import infer_asset_class

UTC = timezone.utc
NY = ZoneInfo(NY_TZ)


@dataclass(frozen=True)
class SessionWindow:
    session_type: SessionType
    start: datetime
    end: datetime

    @property
    def start_ms(self) -> int:
        return int(self.start.astimezone(UTC).timestamp() * 1000)

    @property
    def end_ms(self) -> int:
        return int(self.end.astimezone(UTC).timestamp() * 1000)

    @property
    def session_id(self) -> str:
        return f"{self.session_type.value}:{self.start_ms}"


def _aware(ts: datetime) -> datetime:
    if ts.tzinfo is None:
        return ts.replace(tzinfo=UTC)
    return ts


def _utc_clock(ts: datetime) -> datetime:
    return _aware(ts).astimezone(UTC)


def _ny_clock(ts: datetime) -> datetime:
    return _aware(ts).astimezone(NY)


def _combine(day: datetime, hhmm: time) -> datetime:
    return day.replace(
        hour=hhmm.hour,
        minute=hhmm.minute,
        second=0,
        microsecond=0,
    )


def crypto_sessions(ts: datetime) -> list[SessionWindow]:
    utc = _utc_clock(ts)
    day = utc.replace(hour=0, minute=0, second=0, microsecond=0)
    windows = (
        (SessionType.ASIA, time(0, 0), time(7, 0)),
        (SessionType.LONDON, time(7, 0), time(13, 30)),
        (SessionType.NY_AM, time(13, 30), time(15, 0)),
        (SessionType.NY_PM, time(18, 0), time(20, 0)),
    )
    hit: list[SessionWindow] = []
    tod = utc.time()
    for stype, start_t, end_t in windows:
        if start_t <= tod < end_t:
            hit.append(
                SessionWindow(
                    stype,
                    _combine(day, start_t),
                    _combine(day, end_t),
                )
            )
    return hit


def equity_sessions(ts: datetime, include_eth: bool = True) -> list[SessionWindow]:
    local = _ny_clock(ts)
    if local.weekday() >= 5:
        return []
    tod = local.time()
    day = local.replace(second=0, microsecond=0)
    out: list[SessionWindow] = []
    if include_eth and time(4, 0) <= tod < time(20, 0):
        out.append(
            SessionWindow(
                SessionType.ETH,
                _combine(day, time(4, 0)),
                _combine(day, time(20, 0)),
            )
        )
    if time(9, 30) <= tod < time(16, 0):
        out.append(
            SessionWindow(
                SessionType.RTH,
                _combine(day, time(9, 30)),
                _combine(day, time(16, 0)),
            )
        )
    return out


def futures_sessions(ts: datetime) -> list[SessionWindow]:
    local = _ny_clock(ts)
    tod = local.time()
    day = local.replace(second=0, microsecond=0)
    out: list[SessionWindow] = []

    # RTH weekdays only.
    if local.weekday() < 5 and time(9, 30) <= tod < time(16, 0):
        out.append(
            SessionWindow(
                SessionType.RTH,
                _combine(day, time(9, 30)),
                _combine(day, time(16, 0)),
            )
        )

    # Globex overnight 18:00 → 09:30 next calendar day.
    # Saturday after 09:30 and Sunday before 18:00 are dark.
    if tod >= time(18, 0):
        if local.weekday() == 5:
            return out
        start = _combine(day, time(18, 0))
        end = _combine(day + timedelta(days=1), time(9, 30))
        out.append(SessionWindow(SessionType.GLOBEX, start, end))
    elif tod < time(9, 30):
        if local.weekday() == 6:
            return out
        start = _combine(day - timedelta(days=1), time(18, 0))
        end = _combine(day, time(9, 30))
        out.append(SessionWindow(SessionType.GLOBEX, start, end))
    return out


def sessions_at(
    asset_class: AssetClass | str,
    ts: datetime,
    *,
    include_eth: bool = True,
) -> list[SessionWindow]:
    klass = asset_class if isinstance(asset_class, AssetClass) else AssetClass(asset_class)
    if klass is AssetClass.CRYPTO:
        return crypto_sessions(ts)
    if klass is AssetClass.EQUITY:
        return equity_sessions(ts, include_eth=include_eth)
    return futures_sessions(ts)


def primary_session(
    asset_class: AssetClass | str,
    ts: datetime,
) -> SessionWindow | None:
    """Most specific window: RTH over ETH; otherwise the single crypto/globex window."""
    windows = sessions_at(asset_class, ts, include_eth=True)
    if not windows:
        return None
    for w in windows:
        if w.session_type is SessionType.RTH:
            return w
    return windows[0]


def weekly_anchor_start(asset_class: AssetClass | str, ts: datetime) -> datetime:
    """Monday 00:00 UTC for crypto; Monday RTH open (09:30 NY) for equities/futures."""
    klass = asset_class if isinstance(asset_class, AssetClass) else AssetClass(asset_class)
    aware = _aware(ts)
    if klass is AssetClass.CRYPTO:
        utc = aware.astimezone(UTC)
        monday = utc - timedelta(days=utc.weekday())
        return monday.replace(hour=0, minute=0, second=0, microsecond=0)
    local = aware.astimezone(NY)
    monday = local - timedelta(days=local.weekday())
    anchor = monday.replace(hour=9, minute=30, second=0, microsecond=0)
    if aware < anchor:
        anchor = anchor - timedelta(days=7)
    return anchor


def dt_from_ms(ts_ms: int) -> datetime:
    return datetime.fromtimestamp(ts_ms / 1000.0, tz=UTC)


class SessionTracker:
    """Per-symbol running OHLC for the primary session; publishes Redis schema keys."""

    def __init__(self) -> None:
        self._books: dict[str, SessionLevels] = {}

    def on_tick(
        self,
        symbol: str,
        price: float,
        volume: float,
        ts_ms: int,
        asset_class: AssetClass | str | None = None,
    ) -> SessionLevels | None:
        klass = infer_asset_class(symbol, asset_class)
        window = primary_session(klass, dt_from_ms(ts_ms))
        if window is None:
            return None
        key = f"{symbol}:{window.session_type.value}"
        current = self._books.get(key)
        if current is None or current.session_start_ms != window.start_ms:
            current = SessionLevels(
                symbol=symbol,
                asset_class=klass,
                session_type=window.session_type,
                session_start_ms=window.start_ms,
                session_end_ms=window.end_ms,
                open=price,
                high=price,
                low=price,
                close=price,
                volume=volume,
                updated_ts_ms=ts_ms,
            )
        else:
            current = current.model_copy(
                update={
                    "high": max(current.high, price),
                    "low": min(current.low, price),
                    "close": price,
                    "volume": current.volume + volume,
                    "updated_ts_ms": ts_ms,
                }
            )
        self._books[key] = current
        return current

    def get(self, symbol: str, session_type: str) -> SessionLevels | None:
        return self._books.get(f"{symbol}:{session_type}")

    def all_for_symbol(self, symbol: str) -> list[SessionLevels]:
        prefix = f"{symbol}:"
        return [v for k, v in self._books.items() if k.startswith(prefix)]


def redis_session_key(symbol: str, session_type: str | SessionType) -> str:
    st = session_type.value if isinstance(session_type, SessionType) else session_type
    return f"session:{symbol}:{st}"


def redis_session_channel(symbol: str) -> str:
    return f"session:{symbol}"
