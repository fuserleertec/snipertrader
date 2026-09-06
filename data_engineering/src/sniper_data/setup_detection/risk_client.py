"""Quant Risk Pre-Filter client — ``POST /risk/validate``.

Default ``http://localhost:8001/risk/validate`` (``RISK_VALIDATE_URL``).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Protocol

import httpx

from sniper_data.models import RiskValidateResponse

log = logging.getLogger(__name__)

DEFAULT_RISK_URL = "http://localhost:8001/risk/validate"


@dataclass(frozen=True)
class RiskDecision:
    approved: bool
    reason: str
    adjusted_position_size: float | None = None
    raw: dict[str, Any] | None = None


class RiskClient(Protocol):
    async def validate(self, payload: dict[str, Any]) -> RiskDecision: ...


class HttpRiskClient:
    def __init__(self, url: str = DEFAULT_RISK_URL, *, timeout_s: float = 5.0, transport=None) -> None:
        self.url = url
        self.timeout_s = timeout_s
        self._transport = transport

    async def validate(self, payload: dict[str, Any]) -> RiskDecision:
        if "id" in payload:
            raise ValueError("POST /risk/validate must omit id")
        kwargs: dict[str, Any] = {"timeout": self.timeout_s}
        if self._transport is not None:
            kwargs["transport"] = self._transport
        try:
            async with httpx.AsyncClient(**kwargs) as client:
                resp = await client.post(self.url, json=payload)
                resp.raise_for_status()
                body = resp.json()
        except Exception as exc:  # noqa: BLE001 — never publish on transport failure
            log.warning("risk validate failed (%s): %s", self.url, exc)
            return RiskDecision(approved=False, reason=f"risk_error:{exc}")
        parsed = RiskValidateResponse.model_validate(body)
        return RiskDecision(
            approved=bool(parsed.approved),
            reason=parsed.reason,
            adjusted_position_size=parsed.adjusted_position_size,
            raw=body if isinstance(body, dict) else None,
        )


class StaticRiskClient:
    """Test double. ``approve`` can be a bool or a callable(payload) -> Decision."""

    def __init__(
        self,
        *,
        approved: bool = True,
        reason: str = "ok",
        adjusted_position_size: float | None = 1.0,
        hook=None,
    ) -> None:
        self.approved = approved
        self.reason = reason
        self.adjusted_position_size = adjusted_position_size
        self.hook = hook
        self.calls: list[dict[str, Any]] = []

    async def validate(self, payload: dict[str, Any]) -> RiskDecision:
        if "id" in payload:
            raise ValueError("POST /risk/validate must omit id")
        self.calls.append(payload)
        if self.hook is not None:
            return self.hook(payload)
        return RiskDecision(
            approved=self.approved,
            reason=self.reason,
            adjusted_position_size=self.adjusted_position_size,
        )
