"""Swing high/low detector + earnings/news placeholder hooks (Phase 2).

ML researchers should prefer the HTTP / Kafka registration contract
(see README). This detector is the in-process system path: a confirmed
fractal pivot becomes an ``AnchorRegistration`` with source
``swing_high`` / ``swing_low``.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Callable

from sniper_data.models import AnchorRegistration, AnchorSource, AssetClass
from sniper_data.symbols import infer_asset_class, normalize_symbol

Print = tuple[int, float, float]  # ts_ms, price, volume


class SwingDetector:
    """N-bar fractal: a pivot is confirmed ``right`` prints after the extreme."""

    def __init__(self, left: int = 2, right: int = 2) -> None:
        if left < 1 or right < 1:
            raise ValueError("left and right must be >= 1")
        self.left = left
        self.right = right
        self._buf: dict[str, deque[Print]] = {}
        self._emitted: set[tuple[str, int, str]] = set()

    def on_tick(
        self,
        symbol: str,
        price: float,
        volume: float,
        ts_ms: int,
        asset_class: AssetClass | str | None = None,
    ) -> list[AnchorRegistration]:
        symbol = normalize_symbol(symbol)
        klass = infer_asset_class(symbol, asset_class)
        buf = self._buf.setdefault(symbol, deque())
        buf.append((ts_ms, price, volume))
        need = self.left + self.right + 1
        while len(buf) > need:
            buf.popleft()
        if len(buf) < need:
            return []
        pivot_i = self.left
        pivot_ts, pivot_px, _ = buf[pivot_i]
        left_px = [buf[i][1] for i in range(0, pivot_i)]
        right_px = [buf[i][1] for i in range(pivot_i + 1, need)]
        out: list[AnchorRegistration] = []
        if pivot_px > max(left_px) and pivot_px > max(right_px):
            out.extend(self._emit(symbol, klass, pivot_ts, pivot_px, AnchorSource.SWING_HIGH))
        if pivot_px < min(left_px) and pivot_px < min(right_px):
            out.extend(self._emit(symbol, klass, pivot_ts, pivot_px, AnchorSource.SWING_LOW))
        return out

    def _emit(
        self,
        symbol: str,
        klass: AssetClass,
        ts_ms: int,
        price: float,
        source: AnchorSource,
    ) -> list[AnchorRegistration]:
        token = (symbol, ts_ms, source.value)
        if token in self._emitted:
            return []
        self._emitted.add(token)
        return [
            AnchorRegistration(
                symbol=symbol,
                anchor_time=ts_ms,
                anchor_price=price,
                source=source,
                asset_class=klass,
            )
        ]


def earnings_anchor(
    symbol: str,
    anchor_time: int,
    anchor_price: float,
    asset_class: AssetClass | str | None = None,
) -> AnchorRegistration:
    """Placeholder hook — call when an earnings timestamp is known."""
    symbol = normalize_symbol(symbol)
    return AnchorRegistration(
        symbol=symbol,
        anchor_time=anchor_time,
        anchor_price=anchor_price,
        source=AnchorSource.EARNINGS,
        asset_class=infer_asset_class(symbol, asset_class),
    )


def news_anchor(
    symbol: str,
    anchor_time: int,
    anchor_price: float,
    asset_class: AssetClass | str | None = None,
) -> AnchorRegistration:
    """Placeholder hook — call when a news/event timestamp is known."""
    symbol = normalize_symbol(symbol)
    return AnchorRegistration(
        symbol=symbol,
        anchor_time=anchor_time,
        anchor_price=anchor_price,
        source=AnchorSource.NEWS,
        asset_class=infer_asset_class(symbol, asset_class),
    )


AnchorSink = Callable[[AnchorRegistration], None]
