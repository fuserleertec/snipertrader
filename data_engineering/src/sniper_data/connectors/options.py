"""US-equities options-chain adapter (Greeks + open interest).

Live chain data requires ALPACA_API_KEY + ALPACA_SECRET_KEY (or a vendor
feed). This stub documents the frozen ``options_chain`` contract and
refuses to run without keys so the demo never pretends a paid OPRA feed
is connected. Use ``MockOptionsFlow`` for local / compose demos.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from datetime import datetime, timedelta, timezone

from sniper_data.connectors.base import ConnectorNotConfigured, ExchangeConnector
from sniper_data.models import AssetClass, OptionsChain, RawTick
from sniper_data.symbols import infer_asset_class, normalize_symbol, to_utc_ms


class OptionsChainConnector(ExchangeConnector):
    name = "us_options"

    def __init__(self, symbols: list[str] | None = None) -> None:
        self.symbols = [normalize_symbol(s) for s in (symbols or ["AAPL"])]
        self.api_key = os.getenv("ALPACA_API_KEY", "")
        self.api_secret = os.getenv("ALPACA_SECRET_KEY", "")
        self.base_url = (os.getenv("ALPACA_BASE_URL") or "https://paper-api.alpaca.markets").rstrip("/")

    def _configured(self) -> bool:
        return bool(self.api_key and self.api_secret)

    def chain_url(self, symbol: str) -> str:
        return f"{self.base_url}/v2/options/contracts?underlying_symbols={symbol}"

    def parse_quote(self, payload: dict) -> OptionsChain:
        """Normalize a vendor quote onto the frozen ``options_chain`` fields."""
        symbol = normalize_symbol(payload.get("underlying") or payload["symbol"])
        klass = infer_asset_class(symbol, payload.get("asset_class") or AssetClass.EQUITY)
        option_type = str(payload.get("option_type") or payload.get("type") or "call").lower()
        if option_type not in {"call", "put"}:
            raise ValueError(f"option_type must be call|put, got {option_type!r}")
        contract = normalize_symbol(
            payload.get("contract_symbol") or payload.get("occ") or f"{symbol}{option_type.upper()}"
        )
        return OptionsChain(
            symbol=symbol,
            asset_class=klass,
            exchange=str(payload.get("exchange") or "opra"),
            ts_ms=to_utc_ms(payload.get("ts_ms") or payload.get("t") or payload["ts"]),
            expiry_ms=to_utc_ms(payload.get("expiry_ms") or payload["expiry"]),
            strike=float(payload["strike"]),
            option_type=option_type,  # type: ignore[arg-type]
            contract_symbol=contract,
            bid=_opt_float(payload.get("bid")),
            ask=_opt_float(payload.get("ask")),
            last=_opt_float(payload.get("last")),
            volume=_opt_float(payload.get("volume")),
            open_interest=_opt_float(payload.get("open_interest")),
            implied_volatility=_opt_float(payload.get("implied_volatility")),
            delta=_opt_float(payload.get("delta")),
            gamma=_opt_float(payload.get("gamma")),
            theta=_opt_float(payload.get("theta")),
            vega=_opt_float(payload.get("vega")),
            rho=_opt_float(payload.get("rho")),
        )

    async def stream(self) -> AsyncIterator[RawTick]:
        raise ConnectorNotConfigured(
            "Options chain connector is a placeholder. Set ALPACA_API_KEY and "
            f"ALPACA_SECRET_KEY to wire {self.chain_url(self.symbols[0])}. "
            "Demo uses MockOptionsFlow."
        )
        if False:  # pragma: no cover
            yield RawTick(  # type: ignore[misc]
                symbol="AAPL",
                asset_class=AssetClass.EQUITY,
                exchange="opra",
                ts_ms=0,
                price=0.0,
                volume=0.0,
            )

    async def snapshot(self, symbol: str) -> RawTick | None:
        if not self._configured():
            return None
        raise ConnectorNotConfigured(
            "Options REST snapshot is scaffolded but not implemented. "
            f"Intended endpoint: {self.chain_url(normalize_symbol(symbol))}"
        )


def next_friday_expiry_ms(now_ms: int | None = None) -> int:
    now = datetime.fromtimestamp((now_ms or int(datetime.now(timezone.utc).timestamp() * 1000)) / 1000, tz=timezone.utc)
    days = (4 - now.weekday()) % 7
    if days == 0 and now.hour >= 21:
        days = 7
    expiry = (now + timedelta(days=days)).replace(hour=20, minute=0, second=0, microsecond=0)
    return int(expiry.timestamp() * 1000)


def occ_contract_symbol(underlying: str, expiry_ms: int, option_type: str, strike: float) -> str:
    """OCC-style root + YYMMDD + C/P + strike*1000. Uppercase, no hyphens."""
    dt = datetime.fromtimestamp(expiry_ms / 1000.0, tz=timezone.utc)
    right = "C" if option_type == "call" else "P"
    strike_int = int(round(strike * 1000))
    return f"{normalize_symbol(underlying)}{dt.strftime('%y%m%d')}{right}{strike_int:08d}"


def _opt_float(value: object) -> float | None:
    if value is None or value == "":
        return None
    return float(value)
