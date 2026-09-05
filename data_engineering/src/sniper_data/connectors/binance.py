"""Binance-style crypto adapter.

Public REST/WS endpoints do not require keys. Keys are read from the
environment only (BINANCE_API_KEY / BINANCE_API_SECRET) and are never
logged. This connector is a production-shaped stub: symbol mapping and
URL layout are real; the live stream is opt-in via BINANCE_ENABLE=1 so
the demo pipeline never depends on the public internet.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator

from sniper_data.connectors.base import ConnectorNotConfigured, ExchangeConnector
from sniper_data.models import AssetClass, RawTick
from sniper_data.symbols import normalize_symbol, to_utc_ms


class BinanceConnector(ExchangeConnector):
    name = "binance"

    def __init__(
        self,
        symbols: list[str] | None = None,
        rest_url: str | None = None,
        ws_url: str | None = None,
    ) -> None:
        self.symbols = [normalize_symbol(s) for s in (symbols or ["BTCUSDT"])]
        self.rest_url = (rest_url or os.getenv("BINANCE_REST_URL") or "https://api.binance.com").rstrip("/")
        self.ws_url = ws_url or os.getenv("BINANCE_WS_URL") or "wss://stream.binance.com:9443/ws"
        self.api_key = os.getenv("BINANCE_API_KEY", "")
        self.api_secret = os.getenv("BINANCE_API_SECRET", "")
        self.enabled = os.getenv("BINANCE_ENABLE", "").lower() in {"1", "true", "yes"}

    def _stream_path(self, symbol: str) -> str:
        stream = f"{symbol.lower()}@trade/{symbol.lower()}@depth5@100ms"
        return f"{self.ws_url}/{stream}"

    def rest_ticker_url(self, symbol: str) -> str:
        return f"{self.rest_url}/api/v3/ticker/bookTicker?symbol={symbol}"

    def rest_depth_url(self, symbol: str, limit: int = 10) -> str:
        return f"{self.rest_url}/api/v3/depth?symbol={symbol}&limit={limit}"

    def parse_trade(self, payload: dict) -> RawTick:
        """Map a Binance trade payload onto the global tick schema."""
        symbol = normalize_symbol(payload.get("s") or payload["symbol"])
        price = float(payload.get("p") or payload["price"])
        volume = float(payload.get("q") or payload.get("qty") or payload["volume"])
        ts = payload.get("T") or payload.get("E") or payload.get("ts_ms")
        maker = payload.get("m") if "m" in payload else payload.get("isBuyerMaker")
        is_buyer_maker = None if maker is None else bool(maker)
        aggressor = None
        if is_buyer_maker is True:
            aggressor = "sell"
        elif is_buyer_maker is False:
            aggressor = "buy"
        return RawTick(
            symbol=symbol,
            asset_class=AssetClass.CRYPTO,
            exchange="binance",
            ts_ms=to_utc_ms(ts),
            price=price,
            volume=volume,
            bid=float(payload["b"]) if payload.get("b") else None,
            ask=float(payload["a"]) if payload.get("a") else None,
            is_buyer_maker=is_buyer_maker,
            aggressor=aggressor,
        )

    async def stream(self) -> AsyncIterator[RawTick]:
        if not self.enabled:
            raise ConnectorNotConfigured(
                "Binance live stream is a stub. Set BINANCE_ENABLE=1 to opt in "
                f"(public WS {self.ws_url}/<symbol>@trade). Demo uses MockConnector."
            )
        # Opt-in live path kept minimal so we never pull keys into logs.
        import json

        import websockets

        streams = "/".join(f"{s.lower()}@trade" for s in self.symbols)
        url = f"{self.ws_url}/{streams}" if len(self.symbols) == 1 else (
            self.ws_url.replace("/ws", "/stream") + f"?streams={streams}"
        )
        async with websockets.connect(url, ping_interval=20) as ws:
            async for raw in ws:
                msg = json.loads(raw)
                data = msg.get("data", msg)
                if "p" in data or "price" in data:
                    yield self.parse_trade(data)

    async def snapshot(self, symbol: str) -> RawTick | None:
        if not self.enabled:
            return None
        import httpx

        symbol = normalize_symbol(symbol)
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(self.rest_ticker_url(symbol))
            r.raise_for_status()
            body = r.json()
        return self.parse_trade(
            {
                "s": body.get("symbol", symbol),
                "p": body.get("bidPrice") or body.get("askPrice"),
                "q": "0",
                "T": body.get("time") or 0,
                "b": body.get("bidPrice"),
                "a": body.get("askPrice"),
            }
        )
