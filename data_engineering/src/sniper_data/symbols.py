"""Global symbol schema: uppercase, no hyphens, explicit asset class.

Futures convention (Phase 2)
----------------------------
Normalized form is ``^[A-Z0-9]+$`` (uppercase, no hyphens):

* Root / continuous (demo default): ``ES``, ``NQ``, ``CL``
* Dated CME contract (preferred): ``ESZ2024`` = root + month code + 4-digit year
* 2-digit year is accepted as-is: ``ESZ24`` (not rewritten to ``ESZ2024``)

CME month codes: F G H J K M N Q U V X Z (Jan–Dec).
"""

from __future__ import annotations

import re
from typing import Literal

from sniper_data.models import AssetClass, RawTick

_STRIP = re.compile(r"[^A-Za-z0-9]")

# Hint tables for demo / stub connectors. Unknown symbols default to crypto
# if they look like a pair (len >= 6), else equity.
_EQUITY = {
    "AAPL", "MSFT", "NVDA", "AMZN", "GOOG", "GOOGL", "META", "TSLA",
    "SPY", "QQQ", "IWM", "DIA",
}
_FUTURES = {
    "ES", "NQ", "YM", "RTY", "CL", "GC", "SI", "NG", "ZB", "ZN", "MES", "MNQ",
}
_FUTURES_ROOTS = tuple(sorted(_FUTURES, key=len, reverse=True))
_FUTURES_CONTRACT = re.compile(
    rf"^({'|'.join(_FUTURES_ROOTS)})[FGHJKMNQUVXZ](\d{{2}}|\d{{4}})$"
)

_EXCHANGE_DEFAULT = {
    AssetClass.CRYPTO: "binance",
    AssetClass.EQUITY: "nasdaq",
    AssetClass.FUTURES: "cme",
}


def normalize_symbol(raw: str) -> str:
    if raw is None:
        raise ValueError("symbol is required")
    cleaned = _STRIP.sub("", str(raw)).upper()
    if not cleaned:
        raise ValueError(f"cannot normalize symbol: {raw!r}")
    return cleaned


def infer_asset_class(symbol: str, hint: str | AssetClass | None = None) -> AssetClass:
    if hint is not None:
        return hint if isinstance(hint, AssetClass) else AssetClass(hint)
    if symbol in _FUTURES or _FUTURES_CONTRACT.match(symbol):
        return AssetClass.FUTURES
    if symbol in _EQUITY:
        return AssetClass.EQUITY
    if len(symbol) >= 6:
        return AssetClass.CRYPTO
    return AssetClass.EQUITY


def default_exchange(asset_class: AssetClass) -> str:
    return _EXCHANGE_DEFAULT[asset_class]


def to_utc_ms(ts) -> int:
    """Coerce seconds / ms / datetime-like values to UTC epoch milliseconds."""
    if hasattr(ts, "timestamp"):
        return int(ts.timestamp() * 1000)
    value = float(ts)
    # Heuristic: values below year ~2001 in ms are treated as seconds.
    if value < 1e11:
        return int(value * 1000)
    return int(value)


def normalize_tick(
    *,
    symbol: str,
    price: float,
    volume: float,
    ts,
    asset_class: str | AssetClass | None = None,
    exchange: str | None = None,
    bid: float | None = None,
    ask: float | None = None,
    bid_size: float | None = None,
    ask_size: float | None = None,
    book: dict | None = None,
    aggressor: Literal["buy", "sell"] | None = None,
    is_buyer_maker: bool | None = None,
) -> RawTick:
    from sniper_data.models import OrderBook

    sym = normalize_symbol(symbol)
    klass = infer_asset_class(sym, asset_class)
    payload = None
    if book is not None:
        payload = OrderBook.model_validate(book)
    return RawTick(
        symbol=sym,
        asset_class=klass,
        exchange=exchange or default_exchange(klass),
        ts_ms=to_utc_ms(ts),
        price=float(price),
        volume=float(volume),
        bid=bid,
        ask=ask,
        bid_size=bid_size,
        ask_size=ask_size,
        book=payload,
        aggressor=aggressor,
        is_buyer_maker=is_buyer_maker,
    )
