"""In-process delta. No wire ``delta`` field. No Redis keys.

Locked DE contract
------------------
* Tick optionals: ``aggressor``, ``is_buyer_maker``.
* Bar optionals: ``buy_volume``, ``sell_volume``.
* Signed tick volume = ``+volume`` (buy) / ``−volume`` (sell).
* If ``aggressor`` is missing: DE mid ``(bid+ask)/2``, else **last print**
  (uptick → buy, downtick → sell).
* Cumulative divergence **prefers bars**:
  ``delta = buy_volume - sell_volume``.
* Tick signed volume is only a fallback when both bar fields are null.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sniper_data.models import OHLCVBar, RawTick
from sniper_data.ohlcv import classify_aggressor, signed_volume

Aggressor = classify_aggressor  # re-export DE helper for tests


def classify_tick(tick: RawTick, last_price: float | None = None) -> str | None:
    """Explicit aggressor → is_buyer_maker → mid → last print."""
    side = classify_aggressor(tick)
    if side is not None:
        return side
    if last_price is None:
        return None
    if tick.price > last_price:
        return "buy"
    if tick.price < last_price:
        return "sell"
    return None


def signed_tick_volume(tick: RawTick, last_price: float | None = None) -> float | None:
    """+volume if buy, −volume if sell. None if unclassified."""
    signed = signed_volume(tick)
    if signed is not None:
        return signed
    side = classify_tick(tick, last_price)
    if side == "buy":
        return float(tick.volume)
    if side == "sell":
        return -float(tick.volume)
    return None


def bar_delta(bar: OHLCVBar) -> float | None:
    """``buy_volume - sell_volume``. None if both bar fields are unset."""
    if bar.buy_volume is None and bar.sell_volume is None:
        return None
    return float(bar.buy_volume or 0.0) - float(bar.sell_volume or 0.0)


def resolve_bar_delta(bar: OHLCVBar, tick_fallback: float | None = None) -> float | None:
    """Prefer the bar contract; use in-process tick sum only if the bar is unclassified."""
    preferred = bar_delta(bar)
    if preferred is not None:
        return preferred
    return tick_fallback


@dataclass
class DeltaBook:
    """Per-symbol in-memory tick signed-volume. Never written to Redis/Kafka."""

    last_price: dict[str, float] = field(default_factory=dict)
    tick_signed: dict[str, float] = field(default_factory=dict)

    def on_tick(self, tick: RawTick) -> float | None:
        signed = signed_tick_volume(tick, self.last_price.get(tick.symbol))
        self.last_price[tick.symbol] = tick.price
        if signed is not None:
            self.tick_signed[tick.symbol] = self.tick_signed.get(tick.symbol, 0.0) + signed
        return signed

    def consume_bar(self, bar: OHLCVBar) -> float | None:
        fallback = self.tick_signed.pop(bar.symbol, None)
        return resolve_bar_delta(bar, fallback)
