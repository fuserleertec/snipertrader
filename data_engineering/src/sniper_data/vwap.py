"""VWAP with volume-weighted variance bands (Rev. 1.1).

    VWAP  = Σ(p_i * v_i) / Σ(v_i)
    σ_VWAP = sqrt( Σ(v_i * (p_i - VWAP)^2) / Σ(v_i) )

Maintained incrementally via sufficient statistics:

    W = Σ v_i
    S = Σ p_i v_i
    Q = Σ p_i² v_i
    σ² = Q/W − (S/W)²

This is **not** a simple rolling standard deviation of price (or of
price − VWAP). TradingView's built-in ``VWAP`` + ``stdev`` bands typically
apply an unweighted sample/population stdev to ``src − vwap``. Those bands
match this engine **only when every observation has equal volume**. With
unequal volume they diverge — that is intentional and correct.

Anchors
-------
session  reset at the start of the primary session (per asset-class rules)
weekly   Monday 00:00 UTC (crypto) or Monday RTH 09:30 America/New_York
rolling  last N observations (default 20)
"""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass, field

from sniper_data.models import AnchorType, AssetClass, SessionType, VWAPValues
from sniper_data.sessions import (
    dt_from_ms,
    primary_session,
    weekly_anchor_start,
)
from sniper_data.symbols import infer_asset_class


def volume_weighted_vwap_sigma(
    prices: list[float],
    volumes: list[float],
) -> tuple[float, float]:
    """Two-pass reference implementation used by tests and as a math oracle."""
    if len(prices) != len(volumes):
        raise ValueError("prices and volumes must be the same length")
    if not prices:
        raise ValueError("empty series")
    weight = 0.0
    weighted_price = 0.0
    for p, v in zip(prices, volumes, strict=True):
        if v < 0:
            raise ValueError("volume must be >= 0")
        weight += v
        weighted_price += p * v
    if weight <= 0:
        raise ValueError("total volume must be > 0")
    vwap = weighted_price / weight
    weighted_var = 0.0
    for p, v in zip(prices, volumes, strict=True):
        delta = p - vwap
        weighted_var += v * delta * delta
    sigma = math.sqrt(weighted_var / weight)
    return vwap, sigma


@dataclass
class _Accumulator:
    """Incremental W / S / Q sufficient statistics."""

    weight: float = 0.0
    price_vol: float = 0.0
    price_sq_vol: float = 0.0
    n_obs: int = 0

    def add(self, price: float, volume: float) -> None:
        if volume <= 0:
            return
        self.weight += volume
        self.price_vol += price * volume
        self.price_sq_vol += price * price * volume
        self.n_obs += 1

    def remove(self, price: float, volume: float) -> None:
        if volume <= 0:
            return
        self.weight -= volume
        self.price_vol -= price * volume
        self.price_sq_vol -= price * price * volume
        self.n_obs -= 1

    def reset(self) -> None:
        self.weight = 0.0
        self.price_vol = 0.0
        self.price_sq_vol = 0.0
        self.n_obs = 0

    def snapshot(self) -> tuple[float, float] | None:
        if self.weight <= 0 or self.n_obs <= 0:
            return None
        vwap = self.price_vol / self.weight
        var = self.price_sq_vol / self.weight - vwap * vwap
        # Guard tiny negative from fp error.
        sigma = math.sqrt(max(var, 0.0))
        return vwap, sigma


@dataclass
class _SessionState:
    acc: _Accumulator = field(default_factory=_Accumulator)
    session_id: str | None = None
    session_type: SessionType | None = None
    anchor_start_ms: int = 0


@dataclass
class _WeeklyState:
    acc: _Accumulator = field(default_factory=_Accumulator)
    anchor_start_ms: int = 0


@dataclass
class _RollingState:
    acc: _Accumulator = field(default_factory=_Accumulator)
    window: deque[tuple[float, float]] = field(default_factory=deque)


class VWAPEngine:
    def __init__(self, rolling_periods: int = 20) -> None:
        if rolling_periods < 1:
            raise ValueError("rolling_periods must be >= 1")
        self.rolling_periods = rolling_periods
        self._session: dict[str, _SessionState] = {}
        self._weekly: dict[str, _WeeklyState] = {}
        self._rolling: dict[str, _RollingState] = {}

    def on_tick(
        self,
        symbol: str,
        price: float,
        volume: float,
        ts_ms: int,
        asset_class: AssetClass | str | None = None,
    ) -> list[VWAPValues]:
        klass = infer_asset_class(symbol, asset_class)
        out: list[VWAPValues] = []
        sess = self._update_session(symbol, klass, price, volume, ts_ms)
        if sess is not None:
            out.append(sess)
        out.append(self._update_weekly(symbol, klass, price, volume, ts_ms))
        out.append(self._update_rolling(symbol, klass, price, volume, ts_ms))
        return [s for s in out if s is not None]

    def _update_session(
        self,
        symbol: str,
        klass: AssetClass,
        price: float,
        volume: float,
        ts_ms: int,
    ) -> VWAPValues | None:
        window = primary_session(klass, dt_from_ms(ts_ms))
        if window is None:
            return None
        state = self._session.setdefault(symbol, _SessionState())
        if state.session_id != window.session_id:
            state.acc.reset()
            state.session_id = window.session_id
            state.session_type = window.session_type
            state.anchor_start_ms = window.start_ms
        state.acc.add(price, volume)
        return self._to_values(
            symbol,
            klass,
            AnchorType.SESSION,
            state.acc,
            ts_ms,
            anchor_start_ms=state.anchor_start_ms,
            session_type=state.session_type,
        )

    def _update_weekly(
        self,
        symbol: str,
        klass: AssetClass,
        price: float,
        volume: float,
        ts_ms: int,
    ) -> VWAPValues | None:
        anchor = weekly_anchor_start(klass, dt_from_ms(ts_ms))
        anchor_ms = int(anchor.timestamp() * 1000)
        state = self._weekly.setdefault(symbol, _WeeklyState())
        if state.anchor_start_ms != anchor_ms:
            state.acc.reset()
            state.anchor_start_ms = anchor_ms
        state.acc.add(price, volume)
        return self._to_values(
            symbol,
            klass,
            AnchorType.WEEKLY,
            state.acc,
            ts_ms,
            anchor_start_ms=anchor_ms,
        )

    def _update_rolling(
        self,
        symbol: str,
        klass: AssetClass,
        price: float,
        volume: float,
        ts_ms: int,
    ) -> VWAPValues | None:
        state = self._rolling.setdefault(symbol, _RollingState())
        state.window.append((price, volume))
        state.acc.add(price, volume)
        while len(state.window) > self.rolling_periods:
            old_p, old_v = state.window.popleft()
            state.acc.remove(old_p, old_v)
        return self._to_values(
            symbol,
            klass,
            AnchorType.ROLLING,
            state.acc,
            ts_ms,
            anchor_start_ms=ts_ms,
            lookback=self.rolling_periods,
        )

    def _to_values(
        self,
        symbol: str,
        klass: AssetClass,
        anchor: AnchorType,
        acc: _Accumulator,
        ts_ms: int,
        *,
        anchor_start_ms: int,
        session_type: SessionType | None = None,
        lookback: int | None = None,
    ) -> VWAPValues | None:
        snap = acc.snapshot()
        if snap is None:
            return None
        vwap, sigma = snap
        return VWAPValues(
            symbol=symbol,
            asset_class=klass,
            anchor_type=anchor,
            session_type=session_type,
            anchor_start_ms=anchor_start_ms,
            lookback_periods=lookback,
            vwap=vwap,
            sigma=sigma,
            band_m3=vwap - 3 * sigma,
            band_m2=vwap - 2 * sigma,
            band_m1=vwap - 1 * sigma,
            band_p1=vwap + 1 * sigma,
            band_p2=vwap + 2 * sigma,
            band_p3=vwap + 3 * sigma,
            cum_volume=acc.weight,
            n_obs=acc.n_obs,
            updated_ts_ms=ts_ms,
        )


def redis_vwap_key(symbol: str, anchor_type: str | AnchorType) -> str:
    at = anchor_type.value if isinstance(anchor_type, AnchorType) else anchor_type
    return f"vwap:{symbol}:{at}"
