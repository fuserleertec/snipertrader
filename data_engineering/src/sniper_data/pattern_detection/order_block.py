"""Order-block detector: last opposite candle before displacement.

Uses landed ``OrderBlock`` / ``order_block.schema.json``. Zone bounds are
the origin candle's high/low. ``mitigated`` = filled on retrace into the zone.
"""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field

from sniper_data.models import AssetClass, OHLCVBar, OrderBlock, Timeframe
from sniper_data.pattern_detection.ids import make_id

_RANGE_LOOKBACK = 10
_DISPLACEMENT_RANGE_MULT = 1.5
_MIN_BODY_FRAC = 0.5


@dataclass
class _Slot:
    bars: deque[OHLCVBar] = field(default_factory=lambda: deque(maxlen=80))
    open_zones: dict[str, OrderBlock] = field(default_factory=dict)


def _is_bearish(bar: OHLCVBar) -> bool:
    return bar.close < bar.open


def _is_bullish(bar: OHLCVBar) -> bool:
    return bar.close > bar.open


def _range(bar: OHLCVBar) -> float:
    return max(0.0, bar.high - bar.low)


def _body(bar: OHLCVBar) -> float:
    return abs(bar.close - bar.open)


class OrderBlockDetector:
    def __init__(
        self,
        range_mult: float = _DISPLACEMENT_RANGE_MULT,
        min_body_frac: float = _MIN_BODY_FRAC,
    ) -> None:
        self.range_mult = range_mult
        self.min_body_frac = min_body_frac
        self._buf: dict[tuple[str, str], _Slot] = defaultdict(_Slot)

    def on_bar(self, bar: OHLCVBar) -> list[OrderBlock]:
        slot = self._buf[(bar.symbol, bar.timeframe.value)]
        out: list[OrderBlock] = []
        out.extend(self._mitigate(slot, bar))
        created = self._detect(slot, bar)
        slot.bars.append(bar)
        if created is not None:
            out.append(created)
        return out

    def _is_displacement(self, slot: _Slot, bar: OHLCVBar) -> bool:
        prior = [_range(b) for b in slot.bars][-_RANGE_LOOKBACK:]
        rng = _range(bar)
        if rng <= 0:
            return False
        body = _body(bar)
        if body < self.min_body_frac * rng:
            return False
        if not prior:
            return True
        avg = sum(prior) / len(prior)
        return rng >= self.range_mult * avg

    def _detect(self, slot: _Slot, bar: OHLCVBar) -> OrderBlock | None:
        if not slot.bars or not self._is_displacement(slot, bar):
            return None
        if _is_bullish(bar):
            origin = next((b for b in reversed(slot.bars) if _is_bearish(b)), None)
            direction = "bullish"
        elif _is_bearish(bar):
            origin = next((b for b in reversed(slot.bars) if _is_bullish(b)), None)
            direction = "bearish"
        else:
            return None
        if origin is None:
            return None
        zone_id = make_id("ob", bar.symbol, bar.timeframe.value, origin.close_ts_ms, direction)
        if zone_id in slot.open_zones:
            return None
        zone = OrderBlock(
            id=zone_id,
            symbol=bar.symbol,
            asset_class=bar.asset_class if isinstance(bar.asset_class, AssetClass) else AssetClass(bar.asset_class),
            direction=direction,  # type: ignore[arg-type]
            high=origin.high,
            low=origin.low,
            created_ts_ms=origin.close_ts_ms,
            mitigated=False,
            timeframe=bar.timeframe if isinstance(bar.timeframe, Timeframe) else Timeframe(bar.timeframe),
            displacement_ts_ms=bar.close_ts_ms,
            origin_open=origin.open,
            origin_close=origin.close,
        )
        slot.open_zones[zone_id] = zone
        return zone

    def _mitigate(self, slot: _Slot, bar: OHLCVBar) -> list[OrderBlock]:
        updated: list[OrderBlock] = []
        for zone_id, zone in list(slot.open_zones.items()):
            if zone.mitigated:
                continue
            if bar.low <= zone.high and bar.high >= zone.low:
                filled = zone.model_copy(update={"mitigated": True})
                slot.open_zones[zone_id] = filled
                updated.append(filled)
        return updated
