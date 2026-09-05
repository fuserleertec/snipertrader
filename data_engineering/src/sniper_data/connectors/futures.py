"""CME / Globex futures REST/WS placeholder.

Live market data is not wired in the demo. The mock pipeline emits
``asset_class=futures`` ticks for roots such as ``ES`` and dated contracts
such as ``ESZ2024``. This adapter documents the intended contract and
refuses to stream without an explicit enable flag.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator

from sniper_data.connectors.base import ConnectorNotConfigured, ExchangeConnector
from sniper_data.models import AssetClass, RawTick
from sniper_data.symbols import normalize_symbol, to_utc_ms


class FuturesConnector(ExchangeConnector):
    name = "cme"

    def __init__(self, symbols: list[str] | None = None) -> None:
        self.symbols = [normalize_symbol(s) for s in (symbols or ["ES"])]
        self.enabled = os.getenv("CME_ENABLE", "").lower() in {"1", "true", "yes"}
        self.ws_url = os.getenv("CME_WS_URL") or "wss://placeholder.invalid/cme"

    def parse_trade(self, payload: dict) -> RawTick:
        symbol = normalize_symbol(payload.get("symbol") or payload.get("s") or payload["contract"])
        return RawTick(
            symbol=symbol,
            asset_class=AssetClass.FUTURES,
            exchange=str(payload.get("exchange") or "cme"),
            ts_ms=to_utc_ms(payload.get("ts_ms") or payload.get("t") or payload["timestamp"]),
            price=float(payload.get("price") or payload["p"]),
            volume=float(payload.get("volume") or payload.get("size") or payload.get("q") or 0),
            bid=payload.get("bid"),
            ask=payload.get("ask"),
        )

    async def stream(self) -> AsyncIterator[RawTick]:
        raise ConnectorNotConfigured(
            "CME futures connector is a placeholder. Demo uses MockConnector "
            f"with asset_class=futures (symbols={self.symbols}). Set CME_ENABLE=1 "
            f"when a live Globex feed is wired at {self.ws_url}."
        )
        if False:  # pragma: no cover
            yield self.parse_trade({})

    async def snapshot(self, symbol: str) -> RawTick | None:
        if not self.enabled:
            return None
        raise ConnectorNotConfigured(
            f"CME REST snapshot is scaffolded but not implemented for {normalize_symbol(symbol)}."
        )
