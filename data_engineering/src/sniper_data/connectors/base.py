from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator

from sniper_data.models import RawTick


class ConnectorError(RuntimeError):
    pass


class ConnectorNotConfigured(ConnectorError):
    """Raised by live stubs when API keys / enable flags are missing."""


class ExchangeConnector(ABC):
    """Pluggable exchange adapter. Implementations must emit normalized RawTick."""

    name: str = "base"

    @abstractmethod
    async def stream(self) -> AsyncIterator[RawTick]:
        if False:  # pragma: no cover
            yield RawTick(  # type: ignore[misc]
                symbol="X",
                asset_class="crypto",
                exchange=self.name,
                ts_ms=0,
                price=0.0,
                volume=0.0,
            )

    async def snapshot(self, symbol: str) -> RawTick | None:
        """Optional REST snapshot. Stubs may return None."""
        return None

    async def close(self) -> None:
        return None
