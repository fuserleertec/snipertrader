"""Classic 3-candle Fair Value Gap on 1m / 5m / 15m.

Uses landed ``fvg_zone.schema.json`` exactly. ``mitigated`` = filled when
a later bar's range overlaps ``[low, high]``. Redis+Kafka only.
"""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field

from sniper_data.models import AssetClass, FVGZone, OHLCVBar, Timeframe
from sniper_data.pattern_detection.ids import make_id

FVG_TIMEFRAMES = (Timeframe.M1, Timeframe.M5, Timeframe.M15)


@dataclass
class _TfBuf:
    bars: deque[OHLCVBar] = field(default_factory=lambda: deque(maxlen=8))
    open_zones: dict[str, FVGZone] = field(default_factory=dict)


class FVGDetector:
    def __init__(self) -> None:
        self._buf: dict[tuple[str, str], _TfBuf] = defaultdict(_TfBuf)

    def _slot(self, bar: OHLCVBar) -> _TfBuf:
        return self._buf[(bar.symbol, bar.timeframe.value)]

    def on_bar(self, bar: OHLCVBar) -> list[FVGZone]:
        slot = self._slot(bar)
        out: list[FVGZone] = []
        out.extend(self._mitigate(slot, bar))
        if bar.timeframe not in FVG_TIMEFRAMES:
            slot.bars.append(bar)
            return out
        slot.bars.append(bar)
        created = self._detect(slot, bar)
        if created is not None:
            out.append(created)
        return out

    def _detect(self, slot: _TfBuf, bar: OHLCVBar) -> FVGZone | None:
        if len(slot.bars) < 3:
            return None
        c1, _c2, c3 = list(slot.bars)[-3:]
        if c1.high < c3.low:
            direction = "bullish"
            low, high = c1.high, c3.low
        elif c1.low > c3.high:
            direction = "bearish"
            low, high = c3.high, c1.low
        else:
            return None
        zone_id = make_id("fvg", bar.symbol, bar.timeframe.value, c3.close_ts_ms, direction)
        if zone_id in slot.open_zones:
            return None
        zone = FVGZone(
            id=zone_id,
            symbol=bar.symbol,
            asset_class=bar.asset_class if isinstance(bar.asset_class, AssetClass) else AssetClass(bar.asset_class),
            direction=direction,  # type: ignore[arg-type]
            high=high,
            low=low,
            mitigated=False,
            created_ts_ms=c3.close_ts_ms,
        )
        slot.open_zones[zone_id] = zone
        return zone

    def _mitigate(self, slot: _TfBuf, bar: OHLCVBar) -> list[FVGZone]:
        updated: list[FVGZone] = []
        for zone_id, zone in list(slot.open_zones.items()):
            if zone.mitigated:
                continue
            if bar.low <= zone.high and bar.high >= zone.low:
                filled = zone.model_copy(update={"mitigated": True})
                slot.open_zones[zone_id] = filled
                updated.append(filled)
        return updated
