from __future__ import annotations

import re
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from sniper_quant.setups import SETUP_TYPES

SCHEMA_VERSION = "1.1"

_STRIP = re.compile(r"[^A-Za-z0-9]")


def normalize_symbol(raw: str) -> str:
    if raw is None:
        raise ValueError("symbol is required")
    cleaned = _STRIP.sub("", str(raw)).upper()
    if not cleaned:
        raise ValueError(f"cannot normalize symbol: {raw!r}")
    return cleaned


class AssetClass(str, Enum):
    CRYPTO = "crypto"
    EQUITY = "equity"
    FUTURES = "futures"


class SignalStatus(str, Enum):
    ACTIVE = "ACTIVE"
    TP_HIT = "TP_HIT"
    SL_HIT = "SL_HIT"
    CANCELLED = "CANCELLED"


class Side(str, Enum):
    LONG = "long"
    SHORT = "short"


class CandidateSignal(BaseModel):
    """Setup-signal candidate. ``id`` is optional until ML publishes."""

    schema_version: Literal["1.1"] = SCHEMA_VERSION
    id: str | None = None
    symbol: str
    asset_class: AssetClass
    setup_type: str = Field(min_length=1)
    side: Side
    confidence: float | None = Field(default=None, ge=0, le=1)
    ref_vwap: float | None = None
    ref_session: str | None = None
    ts_ms: int
    entry: float | None = None
    stop: float | None = None
    target: float | None = None
    position_size: float | None = Field(default=None, ge=0)
    invalidation: float | None = None
    atr: float | None = Field(default=None, ge=0)
    equity: float | None = Field(default=None, ge=0)
    account_id: str | None = "default"

    @field_validator("symbol", mode="before")
    @classmethod
    def _norm_symbol(cls, value: str) -> str:
        return normalize_symbol(value)


class ValidateResponse(BaseModel):
    approved: bool
    reason: str
    adjusted_position_size: float | None
    entry: float | None = None
    stop: float | None = None
    target: float | None = None
    risk_per_unit: float | None = None
    checks: dict[str, Any] = Field(default_factory=dict)

    def to_public(self) -> dict[str, Any]:
        """Required contract plus helpful extras for ML."""
        return self.model_dump()


class OpenPosition(BaseModel):
    symbol: str
    side: Side
    size: float
    entry: float
    stop: float | None = None
    opened_ts_ms: int = 0

    @field_validator("symbol", mode="before")
    @classmethod
    def _norm_symbol(cls, value: str) -> str:
        return normalize_symbol(value)


class StoredSignal(BaseModel):
    schema_version: Literal["1.1"] = SCHEMA_VERSION
    id: str
    symbol: str
    asset_class: AssetClass
    setup_type: str
    side: Side
    confidence: float | None = None
    ref_vwap: float | None = None
    ref_session: str | None = None
    ts_ms: int
    entry: float | None = None
    stop: float | None = None
    target: float | None = None
    position_size: float | None = None
    status: SignalStatus = SignalStatus.ACTIVE
    closed_ts_ms: int | None = None

    @field_validator("symbol", mode="before")
    @classmethod
    def _norm_symbol(cls, value: str) -> str:
        return normalize_symbol(value)


class OHLCVBar(BaseModel):
    schema_version: Literal["1.1"] = SCHEMA_VERSION
    symbol: str
    asset_class: AssetClass = AssetClass.CRYPTO
    timeframe: str = "1h"
    open_ts_ms: int
    close_ts_ms: int
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0
    n_ticks: int = 0


class TradeRecord(BaseModel):
    signal_id: str
    symbol: str
    setup_type: str
    side: Side
    entry: float
    stop: float
    target: float
    size: float
    entry_ts_ms: int
    exit_ts_ms: int | None = None
    exit_price: float | None = None
    pnl: float | None = None
    r_multiple: float | None = None
    status: SignalStatus = SignalStatus.ACTIVE


class BacktestMetrics(BaseModel):
    win_rate: float
    avg_rr: float
    sharpe: float
    max_drawdown: float
    n_trades: int
    n_wins: int
    n_losses: int
    net_pnl: float
    ending_equity: float
    starting_equity: float


class RiskParams(BaseModel):
    schema_version: Literal["1.1"] = SCHEMA_VERSION
    risk_fraction: float
    max_daily_loss_frac: float
    corr_lookback_days: int
    corr_threshold: float
    sl_atr_multiple: float
    tp_r_multiple: float
    min_rr: float
    commission_bps: float
    slippage_bps: float
    setup_types: tuple[str, ...] = SETUP_TYPES
