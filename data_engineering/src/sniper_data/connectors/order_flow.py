"""US-equities order-flow adapter (aggressor + large prints) + mock producer.

Live tape requires ALPACA_API_KEY + ALPACA_SECRET_KEY. ``parse_print`` is
real so tests / future vendors share the frozen ``order_flow`` field names
(``aggressor`` — no ``side`` / ``taker_side`` aliases).

``MockOptionsFlow`` emits both ``OptionsChain`` and ``OrderFlow`` so the
pipeline can demo Phase 3 topics without keys.
"""

from __future__ import annotations

import os
import random
import time
from collections.abc import AsyncIterator

from sniper_data.connectors.base import ConnectorNotConfigured, ExchangeConnector
from sniper_data.connectors.options import occ_contract_symbol, next_friday_expiry_ms
from sniper_data.models import AssetClass, OptionsChain, OrderFlow, RawTick
from sniper_data.symbols import infer_asset_class, normalize_symbol, to_utc_ms


class OrderFlowConnector(ExchangeConnector):
    name = "us_order_flow"

    def __init__(
        self,
        symbols: list[str] | None = None,
        large_notional: float = 250_000.0,
    ) -> None:
        self.symbols = [normalize_symbol(s) for s in (symbols or ["AAPL"])]
        self.large_notional = float(large_notional)
        self.api_key = os.getenv("ALPACA_API_KEY", "")
        self.api_secret = os.getenv("ALPACA_SECRET_KEY", "")
        self.ws_url = os.getenv("ALPACA_DATA_WS_URL") or "wss://stream.data.alpaca.markets/v2/iex"

    def _configured(self) -> bool:
        return bool(self.api_key and self.api_secret)

    def parse_print(self, payload: dict) -> OrderFlow:
        symbol = normalize_symbol(payload.get("S") or payload["symbol"])
        klass = infer_asset_class(symbol, payload.get("asset_class") or AssetClass.EQUITY)
        price = float(payload.get("p") or payload["price"])
        volume = float(payload.get("s") or payload.get("volume") or 0)
        aggressor = payload.get("aggressor")
        if aggressor not in {"buy", "sell"}:
            raise ValueError("aggressor must be 'buy' or 'sell' (same as raw_tick)")
        notional = price * volume
        is_large = payload.get("is_large")
        if is_large is None:
            is_large = notional >= self.large_notional
        return OrderFlow(
            symbol=symbol,
            asset_class=klass,
            exchange=str(payload.get("x") or payload.get("exchange") or "nasdaq"),
            ts_ms=to_utc_ms(payload.get("t") or payload["ts_ms"]),
            price=price,
            volume=volume,
            aggressor=aggressor,
            is_large=bool(is_large),
            notional=round(notional, 6),
            trade_id=payload.get("trade_id") or payload.get("i"),
        )

    async def stream(self) -> AsyncIterator[RawTick]:
        raise ConnectorNotConfigured(
            "Order-flow connector is a placeholder. Set ALPACA_API_KEY and "
            f"ALPACA_SECRET_KEY to wire {self.ws_url} trades. Demo uses MockOptionsFlow."
        )
        if False:  # pragma: no cover
            yield RawTick(  # type: ignore[misc]
                symbol="AAPL",
                asset_class=AssetClass.EQUITY,
                exchange="nasdaq",
                ts_ms=0,
                price=0.0,
                volume=0.0,
            )


class MockOptionsFlow:
    """Deterministic options-chain + order-flow prints for equity underlyings."""

    name = "mock_options_flow"

    def __init__(
        self,
        symbols: list[str] | None = None,
        *,
        large_notional: float = 250_000.0,
        seed: int | None = 11,
    ) -> None:
        raw = [normalize_symbol(s) for s in (symbols or ["AAPL"])]
        self.symbols = [s for s in raw if infer_asset_class(s) is AssetClass.EQUITY]
        self.large_notional = float(large_notional)
        self._rng = random.Random(seed)
        self._px = {s: 228.0 + self._rng.uniform(-1, 1) for s in self.symbols}
        self._n = 0

    def next_order_flow(self, symbol: str | None = None) -> OrderFlow:
        symbol = normalize_symbol(symbol or self.symbols[0])
        last = self._px.get(symbol, 100.0)
        shock = self._rng.gauss(0, last * 0.0004)
        price = max(0.01, last + shock)
        self._px[symbol] = price
        volume = max(1.0, abs(self._rng.gauss(200, 80)))
        if self._rng.random() < 0.08:
            volume *= 40
        notional = price * volume
        aggressor = "buy" if shock >= 0 else "sell"
        self._n += 1
        return OrderFlow(
            symbol=symbol,
            asset_class=AssetClass.EQUITY,
            exchange="mock",
            ts_ms=int(time.time() * 1000),
            price=round(price, 4),
            volume=round(volume, 4),
            aggressor=aggressor,
            is_large=notional >= self.large_notional,
            notional=round(notional, 4),
            trade_id=f"of-{symbol}-{self._n}",
        )

    def next_chain(self, symbol: str | None = None) -> OptionsChain:
        symbol = normalize_symbol(symbol or self.symbols[0])
        spot = self._px.get(symbol, 100.0)
        option_type = "call" if self._rng.random() >= 0.5 else "put"
        strike = round(spot / 5) * 5
        expiry_ms = next_friday_expiry_ms()
        iv = max(0.05, abs(self._rng.gauss(0.28, 0.04)))
        contract = occ_contract_symbol(symbol, expiry_ms, option_type, strike)
        moneyness = (spot - strike) / max(spot, 1e-9)
        delta = 0.5 + 0.4 * moneyness if option_type == "call" else -0.5 + 0.4 * moneyness
        return OptionsChain(
            symbol=symbol,
            asset_class=AssetClass.EQUITY,
            exchange="mock",
            ts_ms=int(time.time() * 1000),
            expiry_ms=expiry_ms,
            strike=float(strike),
            option_type=option_type,  # type: ignore[arg-type]
            contract_symbol=contract,
            bid=round(max(0.01, iv * 2 - 0.05), 4),
            ask=round(max(0.02, iv * 2 + 0.05), 4),
            last=round(max(0.01, iv * 2), 4),
            volume=round(abs(self._rng.gauss(400, 80)), 2),
            open_interest=round(abs(self._rng.gauss(4_000, 400)), 2),
            implied_volatility=round(iv, 4),
            delta=round(max(-1.0, min(1.0, delta)), 4),
            gamma=round(abs(self._rng.gauss(0.04, 0.01)), 4),
            theta=round(-abs(self._rng.gauss(0.03, 0.01)), 4),
            vega=round(abs(self._rng.gauss(0.12, 0.02)), 4),
            rho=round(self._rng.gauss(0.02, 0.01), 4),
        )
