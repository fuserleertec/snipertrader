"""US equities REST/WS placeholder (Alpaca-shaped).

Live market data requires ALPACA_API_KEY + ALPACA_SECRET_KEY in the
environment. This adapter documents the contract and refuses to run
without keys so the demo never pretends a paid feed is connected.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator

from sniper_data.connectors.base import ConnectorNotConfigured, ExchangeConnector
from sniper_data.models import AssetClass, RawTick
from sniper_data.symbols import normalize_symbol, to_utc_ms


class USEquitiesConnector(ExchangeConnector):
    name = "us_equities"

    def __init__(self, symbols: list[str] | None = None) -> None:
        self.symbols = [normalize_symbol(s) for s in (symbols or ["AAPL"])]
        self.api_key = os.getenv("ALPACA_API_KEY", "")
        self.api_secret = os.getenv("ALPACA_SECRET_KEY", "")
        self.base_url = (os.getenv("ALPACA_BASE_URL") or "https://paper-api.alpaca.markets").rstrip("/")
        self.ws_url = os.getenv("ALPACA_DATA_WS_URL") or "wss://stream.data.alpaca.markets/v2/iex"

    def _configured(self) -> bool:
        return bool(self.api_key and self.api_secret)

    def bars_url(self, symbol: str, timeframe: str = "1Min") -> str:
        return (
            f"{self.base_url}/v2/stocks/{symbol}/bars"
            f"?timeframe={timeframe}&limit=1000&adjustment=raw"
        )

    def parse_trade(self, payload: dict) -> RawTick:
        symbol = normalize_symbol(payload.get("S") or payload["symbol"])
        return RawTick(
            symbol=symbol,
            asset_class=AssetClass.EQUITY,
            exchange=str(payload.get("x") or payload.get("exchange") or "nasdaq"),
            ts_ms=to_utc_ms(payload.get("t") or payload["ts_ms"]),
            price=float(payload.get("p") or payload["price"]),
            volume=float(payload.get("s") or payload.get("volume") or 0),
            bid=payload.get("bid"),
            ask=payload.get("ask"),
        )

    async def stream(self) -> AsyncIterator[RawTick]:
        raise ConnectorNotConfigured(
            "US equities connector is a placeholder. Set ALPACA_API_KEY and "
            f"ALPACA_SECRET_KEY to wire {self.ws_url} trades. Demo uses MockConnector."
        )
        if False:  # pragma: no cover — keeps this an async generator
            yield self.parse_trade({})

    async def snapshot(self, symbol: str) -> RawTick | None:
        if not self._configured():
            return None
        raise ConnectorNotConfigured(
            "US equities REST snapshot is scaffolded but not implemented. "
            f"Intended endpoint: {self.bars_url(normalize_symbol(symbol))}"
        )
