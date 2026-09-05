"""Bar-level cumulative delta. No wire ``delta`` field — compute in-process.

Prefer ``ohlcv_bar.buy_volume − sell_volume``. Tick aggressor /
``is_buyer_maker`` are classified by ``sniper_data.ohlcv.classify_aggressor``
when the aggregator fills those optional bar fields.
"""

from __future__ import annotations

from sniper_data.models import OHLCVBar


def bar_delta(bar: OHLCVBar) -> float | None:
    """Signed aggressor delta: buy_volume − sell_volume. None if unclassified."""
    if bar.buy_volume is None and bar.sell_volume is None:
        return None
    return float(bar.buy_volume or 0.0) - float(bar.sell_volume or 0.0)
