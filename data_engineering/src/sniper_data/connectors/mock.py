"""Deterministic-ish mock feed so the pipeline runs without exchange keys."""

from __future__ import annotations

import asyncio
import math
import random
import time
from collections.abc import AsyncIterator

from sniper_data.models import AssetClass, OrderBook, RawTick
from sniper_data.symbols import infer_asset_class, normalize_symbol


_SEEDS: dict[str, tuple[float, float]] = {
    "BTCUSDT": (67_250.0, 0.35),
    "ETHUSDT": (3_420.0, 1.2),
    "AAPL": (228.40, 120.0),
    "ES": (5_812.25, 40.0),
}


class MockConnector:
    name = "mock"

    def __init__(
        self,
        symbols: list[str] | None = None,
        interval_ms: int = 80,
        seed: int | None = 7,
    ) -> None:
        self.symbols = [normalize_symbol(s) for s in (symbols or list(_SEEDS))]
        self.interval_ms = interval_ms
        self._rng = random.Random(seed)
        self._px = {
            s: _SEEDS.get(s, (100.0, 50.0))[0] + self._rng.uniform(-0.5, 0.5)
            for s in self.symbols
        }
        self._running = True

    async def stream(self) -> AsyncIterator[RawTick]:
        i = 0
        while self._running:
            symbol = self.symbols[i % len(self.symbols)]
            yield self._tick(symbol)
            i += 1
            await asyncio.sleep(self.interval_ms / 1000.0)

    def _tick(self, symbol: str) -> RawTick:
        klass = infer_asset_class(symbol)
        last = self._px[symbol]
        shock = self._rng.gauss(0, last * 0.00025)
        # Mild session-shaped drift so VWAP/σ have something to chew on.
        drift = math.sin(time.time() / 40.0) * last * 0.00005
        price = max(0.01, last + shock + drift)
        self._px[symbol] = price
        base_vol = _SEEDS.get(symbol, (100.0, 10.0))[1]
        volume = max(0.0001, abs(self._rng.gauss(base_vol, base_vol * 0.25)))
        spread = max(price * 0.00005, 0.01 if klass is AssetClass.EQUITY else price * 0.00002)
        bid = price - spread / 2
        ask = price + spread / 2
        now_ms = int(time.time() * 1000)
        return RawTick(
            symbol=symbol,
            asset_class=klass,
            exchange="mock",
            ts_ms=now_ms,
            price=round(price, 6),
            volume=round(volume, 6),
            bid=round(bid, 6),
            ask=round(ask, 6),
            bid_size=round(abs(self._rng.gauss(8, 2)), 4),
            ask_size=round(abs(self._rng.gauss(8, 2)), 4),
            book=OrderBook(
                bids=[[round(bid - n * spread, 6), round(abs(self._rng.gauss(5, 1)), 4)] for n in range(5)],
                asks=[[round(ask + n * spread, 6), round(abs(self._rng.gauss(5, 1)), 4)] for n in range(5)],
            ),
        )

    async def snapshot(self, symbol: str) -> RawTick:
        return self._tick(normalize_symbol(symbol))

    async def close(self) -> None:
        self._running = False
