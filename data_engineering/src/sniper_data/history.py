"""Synthetic paper OHLCV history for every configured universe symbol.

Demo/compose previously only had live ticks, so ``GET /v1/ohlcv/{symbol}``
was empty for ES / CL / GC / NQ / equities until bars closed. This seeder
writes deterministic bars for all timeframes so Frontend can plot charts
on day one. ``live_trading=false`` — no exchange fetch.
"""

from __future__ import annotations

import hashlib
import logging
import random
import time
from typing import Iterable

from sniper_data.models import AssetClass, OHLCVBar, Timeframe
from sniper_data.ohlcv import TIMEFRAME_MS
from sniper_data.symbols import infer_asset_class, normalize_symbol

log = logging.getLogger(__name__)

# Typical (price, volume) seeds — mixed crypto / equity / futures.
SYMBOL_SEEDS: dict[str, tuple[float, float]] = {
    "BTCUSDT": (67_250.0, 12.0),
    "ETHUSDT": (3_420.0, 40.0),
    "SOLUSDT": (148.0, 80.0),
    "BNBUSDT": (580.0, 25.0),
    "AAPL": (228.40, 1_200.0),
    "MSFT": (415.20, 900.0),
    "NVDA": (118.50, 2_400.0),
    "SPY": (542.10, 3_500.0),
    "ES": (5_812.25, 400.0),
    "NQ": (20_140.0, 280.0),
    "CL": (78.35, 1_800.0),
    "GC": (2_364.50, 220.0),
    "AMZN": (186.0, 800.0),
    "GOOG": (168.0, 700.0),
    "META": (512.0, 650.0),
    "TSLA": (248.0, 1_500.0),
    "QQQ": (472.0, 2_200.0),
    "YM": (39_800.0, 180.0),
    "RTY": (2_180.0, 260.0),
    "SI": (28.40, 400.0),
}

DEFAULT_BARS = {
    Timeframe.M1: 200,
    Timeframe.M5: 120,
    Timeframe.M15: 96,
    Timeframe.H1: 72,
    Timeframe.H4: 48,
}


def seed_price(symbol: str) -> tuple[float, float]:
    if symbol in SYMBOL_SEEDS:
        return SYMBOL_SEEDS[symbol]
    klass = infer_asset_class(symbol)
    digest = hashlib.sha1(symbol.encode()).digest()
    if klass is AssetClass.CRYPTO:
        return (50.0 + digest[0] * 20.0, 15.0)
    if klass is AssetClass.FUTURES:
        return (100.0 + digest[0] * 8.0, 200.0)
    return (20.0 + digest[0] * 2.0, 500.0)


def generate_history(
    symbol: str,
    timeframe: Timeframe | str,
    n_bars: int,
    *,
    now_ms: int | None = None,
    seed: int = 7,
) -> list[OHLCVBar]:
    """Deterministic random-walk bars ending at the last closed bucket."""
    symbol = normalize_symbol(symbol)
    tf = timeframe if isinstance(timeframe, Timeframe) else Timeframe(timeframe)
    width = TIMEFRAME_MS[tf]
    now = now_ms if now_ms is not None else int(time.time() * 1000)
    last_open = ((now // width) * width) - width
    klass = infer_asset_class(symbol)
    px0, vol0 = seed_price(symbol)
    rng = random.Random(seed + int.from_bytes(symbol.encode()[:4].ljust(4, b"\0"), "big") + n_bars)
    price = px0
    bars: list[OHLCVBar] = []
    for i in range(n_bars):
        open_ts = last_open - (n_bars - 1 - i) * width
        shock = rng.gauss(0.0, price * 0.0018)
        drift = rng.uniform(-0.0004, 0.0006) * price
        close = max(0.01, price + shock + drift)
        high = max(price, close) + abs(rng.gauss(0, price * 0.0006))
        low = min(price, close) - abs(rng.gauss(0, price * 0.0006))
        low = max(0.01, low)
        volume = max(0.0001, abs(rng.gauss(vol0, vol0 * 0.28)))
        buy = volume * rng.uniform(0.35, 0.65)
        bars.append(
            OHLCVBar(
                symbol=symbol,
                asset_class=klass,
                timeframe=tf,
                open_ts_ms=open_ts,
                close_ts_ms=open_ts + width,
                open=round(price, 6),
                high=round(high, 6),
                low=round(low, 6),
                close=round(close, 6),
                volume=round(volume, 6),
                n_ticks=max(1, int(rng.gauss(18, 4))),
                buy_volume=round(buy, 6),
                sell_volume=round(volume - buy, 6),
            )
        )
        price = close
    return bars


async def seed_ohlcv_history(
    bars_store,
    symbols: Iterable[str],
    *,
    now_ms: int | None = None,
    per_timeframe: dict[Timeframe, int] | None = None,
    seed: int = 7,
) -> dict[str, int]:
    """Idempotent upsert of synthetic history for every symbol × timeframe."""
    counts = per_timeframe or DEFAULT_BARS
    written = 0
    symbols = [normalize_symbol(s) for s in symbols]
    for symbol in symbols:
        for tf, n in counts.items():
            rows = generate_history(symbol, tf, n, now_ms=now_ms, seed=seed)
            if hasattr(bars_store, "upsert_many"):
                await bars_store.upsert_many(rows)
            else:
                for bar in rows:
                    await bars_store.upsert(bar)
            written += len(rows)
    log.info("seeded %s historical OHLCV bars for %s symbols (paper)", written, len(symbols))
    return {"symbols": len(symbols), "bars": written}
