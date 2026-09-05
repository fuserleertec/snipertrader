from __future__ import annotations

import re
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from sniper_quant.setups import SESSION_TYPES, SETUP_TYPES, SIGNAL_TIMEFRAMES

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


class SetupType(str, Enum):
    SWEEP_RECLAIM = "sweep_reclaim"
    FVG_ENTRY = "fvg_entry"
    PO3_JUDAS = "po3_judas"
    SD_EXTENSION_FADE = "sd_extension_fade"
    VWAP_PULLBACK_CONT = "vwap_pullback_cont"
    AVWAP_OB_CONFLUENCE = "avwap_ob_confluence"


class SignalTimeframe(str, Enum):
    M1 = "1m"
    M5 = "5m"
    M15 = "15m"


class SessionType(str, Enum):
    """Same session windows as ``data_engineering`` / ``session_levels``."""

    ASIA = "asia"
    LONDON = "london"
    NY_AM = "ny_am"
    NY_PM = "ny_pm"
    RTH = "rth"
    ETH = "eth"
    GLOBEX = "globex"


class FactorBreakdownRow(BaseModel):
    """Publish-only explainability row (ML PR #9). Not on ``POST /risk/validate``."""

    name: str
    weight: float = 0.0
    score: float = 0.0
    note: str | None = None


class CandidateSignal(BaseModel):
    """ML candidate for ``POST /risk/validate``. Omit ``id`` — assigned after approval."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.1"] = SCHEMA_VERSION
    symbol: str
    asset_class: AssetClass
    setup_type: SetupType
    side: Side
    confidence: float | None = Field(default=None, ge=0, le=1)
    ref_vwap: float | None = None
    ref_session: str | None = None
    ts_ms: int
    entry: float = Field(description="Intended entry price. Required for risk.")
    stop: float = Field(description="Stop-loss price. Required for risk.")
    target: float = Field(description="Take-profit price. Required for risk.")
    timeframe: SignalTimeframe = Field(description="Pattern timeframe: 1m, 5m, or 15m.")
    trigger_event_ids: list[str] = Field(
        description="IDs of sweep/FVG/MSS events that triggered this candidate."
    )
    session_type: SessionType | None = Field(
        default=None,
        description="Optional DE session window (asia/london/ny_am/ny_pm/rth/eth/globex).",
    )
    proposed_position_size: float | None = Field(
        default=None,
        ge=0,
        description="Optional proposed size in units. Engine may overwrite via adjusted_position_size.",
    )

    @field_validator("symbol", mode="before")
    @classmethod
    def _norm_symbol(cls, value: str) -> str:
        return normalize_symbol(value)


SIGNAL_VIEW_FIELDS = (
    "id",
    "ts_ms",
    "symbol",
    "asset_class",
    "setup_type",
    "side",
    "entry",
    "stop",
    "target",
    "status",
    "confidence",
    "timeframe",
    "ref_session",
    "trigger_event_ids",
    "realized_r",
    "exit_price",
    "closed_ts_ms",
)


class SignalView(BaseModel):
    """Dashboard / Frontend Signal row. Aligned with the ML validate candidate."""

    id: str
    ts_ms: int
    symbol: str
    asset_class: AssetClass
    setup_type: SetupType
    side: Side
    entry: float | None = None
    stop: float | None = None
    target: float | None = None
    status: SignalStatus
    confidence: float | None = None
    timeframe: SignalTimeframe | None = None
    ref_session: str | None = None
    trigger_event_ids: list[str] = Field(default_factory=list)
    realized_r: float | None = Field(
        default=None,
        description="Signed R multiple on TP_HIT / SL_HIT. Null for ACTIVE and CANCELLED.",
    )
    exit_price: float | None = Field(
        default=None,
        description="Fill price when the signal closes on TP/SL. Optional.",
    )
    closed_ts_ms: int | None = Field(
        default=None,
        description="UTC epoch ms when the signal left ACTIVE. Optional.",
    )
    # Storage / Grafana aliases — same values as exit_price / realized_r.
    exit_px: float | None = None
    r_multiple: float | None = None
    outcome: str | None = None

    @classmethod
    def from_stored(cls, row: "StoredSignal") -> "SignalView":
        setup = row.setup_type
        if not isinstance(setup, SetupType):
            setup = SetupType(str(setup))
        tf = row.timeframe
        if tf is not None and not isinstance(tf, SignalTimeframe):
            tf = SignalTimeframe(str(tf))
        closed = row.status in {SignalStatus.TP_HIT, SignalStatus.SL_HIT}
        realized = row.r_multiple if closed else None
        exit_price = row.exit_px
        return cls(
            id=row.id,
            ts_ms=row.ts_ms,
            symbol=row.symbol,
            asset_class=row.asset_class,
            setup_type=setup,
            side=row.side,
            entry=row.entry,
            stop=row.stop,
            target=row.target,
            status=row.status,
            confidence=row.confidence,
            timeframe=tf,
            ref_session=row.ref_session,
            trigger_event_ids=list(row.trigger_event_ids or []),
            realized_r=realized,
            exit_price=exit_price,
            closed_ts_ms=row.closed_ts_ms,
            exit_px=exit_price,
            r_multiple=realized,
            outcome=row.outcome,
        )


class SignalListResponse(BaseModel):
    items: list[SignalView]
    next_cursor: str | None = None


class SignalWsEvent(BaseModel):
    type: Literal["signal.upsert", "signal.status"]
    signal: SignalView


class ValidateResponse(BaseModel):
    approved: bool
    reason: str
    adjusted_position_size: float | None = Field(
        description="Position size in **asset units** (contracts/coins/shares), not USD notional."
    )
    size_unit: Literal["asset"] = "asset"
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
    setup_type: SetupType | str
    side: Side
    confidence: float | None = None
    ref_vwap: float | None = None
    ref_session: str | None = None
    ts_ms: int
    entry: float | None = None
    stop: float | None = None
    target: float | None = None
    position_size: float | None = None
    timeframe: SignalTimeframe | str | None = None
    trigger_event_ids: list[str] = Field(default_factory=list)
    session_type: SessionType | str | None = None
    status: SignalStatus = SignalStatus.ACTIVE
    closed_ts_ms: int | None = None
    exit_px: float | None = None
    r_multiple: float | None = None
    outcome: str | None = None
    contributing_factors: list[str] = Field(
        default_factory=list,
        description="Publish-only. Not accepted on POST /risk/validate.",
    )
    factor_breakdown: list[FactorBreakdownRow] = Field(
        default_factory=list,
        description="Publish-only {name, weight, score, note?}[]. Not on POST /risk/validate.",
    )

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


class PerformanceBucket(BaseModel):
    setup_type: str = Field(description="Locked setup_type for Frontend / signal joins.")
    win_rate: float = 0.0
    average_rr: float = 0.0
    sharpe_ratio: float = 0.0
    max_drawdown_pct: float = 0.0
    n_signals: int = 0
    n_closed: int = 0
    signals_today: int = 0
    signals_week: int = 0


class PerformanceSummary(BaseModel):
    win_rate: float
    average_rr: float
    sharpe_ratio: float
    max_drawdown_pct: float
    signals_today: int
    signals_week: int
    n_signals: int = 0
    n_closed: int = 0
    by_setup: dict[str, PerformanceBucket] = Field(
        description=(
            "Keyed by DE product strings "
            "(1_liquidity_sweep_vwap_reclaim, 2_fvg_mitigation_vwap, "
            "3_po3_asia_range_sweep, 4_sd_extension_fade, "
            "5_vwap_pullback_cont, 6_avwap_ob_confluence). "
            "Each value includes setup_type."
        )
    )
    rolling_win_rate_20: float | None = None
    drift_warning: bool = False
    drift_note: str = ""


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
    signal_timeframes: tuple[str, ...] = SIGNAL_TIMEFRAMES
    session_types: tuple[str, ...] = SESSION_TYPES
