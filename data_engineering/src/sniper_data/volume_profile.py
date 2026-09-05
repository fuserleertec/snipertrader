"""Per-session volume profile, HVN / LVN, and POC (Phase 2).

Redis key: ``volume_profile:{symbol}:{session_type}``
Wire payload matches ``schemas/volume_profile.schema.json`` exactly.

POC = price bin with maximum accumulated volume.
HVN = local maxima at or above mean bin volume (POC is always included).
LVN = local minima at or below mean bin volume (never the POC).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from sniper_data.models import AssetClass, SessionType, VolumeNode, VolumeProfile
from sniper_data.sessions import dt_from_ms, sessions_at
from sniper_data.symbols import infer_asset_class


def redis_volume_profile_key(symbol: str, session_type: str | SessionType) -> str:
    st = session_type.value if isinstance(session_type, SessionType) else session_type
    return f"volume_profile:{symbol}:{st}"


def redis_volume_profile_channel(symbol: str) -> str:
    return f"volume_profile:{symbol}"


def redis_volume_profile_acc_key(symbol: str, session_type: str | SessionType) -> str:
    st = session_type.value if isinstance(session_type, SessionType) else session_type
    return f"volume_profile:acc:{symbol}:{st}"


# Demo / default tick sizes. Override via VolumeProfileEngine(tick_sizes=...).
DEFAULT_TICK_SIZES: dict[str, float] = {
    "BTCUSDT": 5.0,
    "ETHUSDT": 1.0,
    "AAPL": 0.05,
    "MSFT": 0.05,
    "NVDA": 0.05,
    "ES": 0.25,
    "NQ": 0.25,
    "MES": 0.25,
    "MNQ": 0.25,
}


def default_tick_size(symbol: str, asset_class: AssetClass | str | None = None) -> float:
    if symbol in DEFAULT_TICK_SIZES:
        return DEFAULT_TICK_SIZES[symbol]
    klass = infer_asset_class(symbol, asset_class)
    if klass is AssetClass.FUTURES:
        return 0.25
    if klass is AssetClass.EQUITY:
        return 0.01
    return 1.0


def price_bin(price: float, tick_size: float) -> float:
    if tick_size <= 0:
        raise ValueError("tick_size must be > 0")
    return round(round(price / tick_size) * tick_size, 10)


def detect_nodes(bins: dict[float, float]) -> tuple[list[VolumeNode], list[VolumeNode], float]:
    """Return (HVN, LVN, poc_price) from a price→volume histogram."""
    if not bins:
        raise ValueError("empty volume profile")
    items = sorted(bins.items(), key=lambda kv: kv[0])
    poc_price = max(bins.items(), key=lambda kv: (kv[1], -kv[0]))[0]
    volumes = [v for _, v in items]
    mean = sum(volumes) / len(volumes)
    hvn: list[VolumeNode] = []
    lvn: list[VolumeNode] = []
    n = len(items)
    for i, (px, vol) in enumerate(items):
        left = items[i - 1][1] if i > 0 else None
        right = items[i + 1][1] if i + 1 < n else None
        is_max = (left is None or vol >= left) and (right is None or vol >= right)
        is_min = (left is None or vol <= left) and (right is None or vol <= right)
        if n == 1:
            is_max, is_min = True, False
        elif is_max and is_min:
            # Flat neighbourhood — count as neither unless it is the POC.
            is_max = px == poc_price
            is_min = False
        if is_max and vol >= mean:
            hvn.append(VolumeNode(price=px, volume=vol))
        if is_min and vol <= mean and px != poc_price:
            lvn.append(VolumeNode(price=px, volume=vol))
    if not any(math.isclose(node.price, poc_price, rel_tol=0, abs_tol=1e-9) for node in hvn):
        hvn.append(VolumeNode(price=poc_price, volume=bins[poc_price]))
    hvn.sort(key=lambda node: (-node.volume, node.price))
    lvn.sort(key=lambda node: (node.volume, node.price))
    return hvn, lvn, poc_price


@dataclass
class _SessionBins:
    session_id: str
    session_type: SessionType
    bins: dict[float, float] = field(default_factory=dict)
    last_ts: int = 0


class VolumeProfileEngine:
    def __init__(self, tick_sizes: dict[str, float] | None = None) -> None:
        self.tick_sizes = {**(tick_sizes or {})}
        self._books: dict[str, _SessionBins] = {}

    def _tick_size(self, symbol: str, klass: AssetClass) -> float:
        if symbol in self.tick_sizes:
            return self.tick_sizes[symbol]
        return default_tick_size(symbol, klass)

    def on_tick(
        self,
        symbol: str,
        price: float,
        volume: float,
        ts_ms: int,
        asset_class: AssetClass | str | None = None,
    ) -> list[VolumeProfile]:
        if volume <= 0:
            return []
        klass = infer_asset_class(symbol, asset_class)
        windows = sessions_at(klass, dt_from_ms(ts_ms))
        if not windows:
            return []
        tick = self._tick_size(symbol, klass)
        binned = price_bin(price, tick)
        out: list[VolumeProfile] = []
        for window in windows:
            key = f"{symbol}:{window.session_type.value}"
            state = self._books.get(key)
            if state is None or state.session_id != window.session_id:
                state = _SessionBins(
                    session_id=window.session_id,
                    session_type=window.session_type,
                )
                self._books[key] = state
            state.bins[binned] = state.bins.get(binned, 0.0) + volume
            state.last_ts = ts_ms
            hvn, lvn, poc = detect_nodes(state.bins)
            out.append(
                VolumeProfile(
                    symbol=symbol,
                    session_type=window.session_type,
                    high_volume_nodes=hvn,
                    low_volume_nodes=lvn,
                    poc=poc,
                    timestamp=ts_ms,
                )
            )
        return out

    def get(self, symbol: str, session_type: str | SessionType) -> VolumeProfile | None:
        st = session_type.value if isinstance(session_type, SessionType) else session_type
        state = self._books.get(f"{symbol}:{st}")
        if state is None or not state.bins:
            return None
        hvn, lvn, poc = detect_nodes(state.bins)
        return VolumeProfile(
            symbol=symbol,
            session_type=state.session_type,
            high_volume_nodes=hvn,
            low_volume_nodes=lvn,
            poc=poc,
            timestamp=state.last_ts,
        )
