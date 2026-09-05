from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


SCHEMA_VERSION = "1.1"


class AssetClass(str, Enum):
    CRYPTO = "crypto"
    EQUITY = "equity"
    FUTURES = "futures"


class Timeframe(str, Enum):
    M1 = "1m"
    M5 = "5m"
    M15 = "15m"
    H1 = "1h"
    H4 = "4h"


class SessionType(str, Enum):
    ASIA = "asia"
    LONDON = "london"
    NY_AM = "ny_am"
    NY_PM = "ny_pm"
    RTH = "rth"
    ETH = "eth"
    GLOBEX = "globex"


class AnchorType(str, Enum):
    SESSION = "session"
    WEEKLY = "weekly"
    ROLLING = "rolling"


class BookLevel(BaseModel):
    price: float
    size: float


class OrderBook(BaseModel):
    bids: list[list[float]] = Field(default_factory=list)
    asks: list[list[float]] = Field(default_factory=list)


class RawTick(BaseModel):
    schema_version: Literal["1.1"] = SCHEMA_VERSION
    symbol: str
    asset_class: AssetClass
    exchange: str
    ts_ms: int
    price: float
    volume: float
    bid: float | None = None
    ask: float | None = None
    bid_size: float | None = None
    ask_size: float | None = None
    book: OrderBook | None = None
    aggressor: Literal["buy", "sell"] | None = None
    is_buyer_maker: bool | None = None


class OHLCVBar(BaseModel):
    schema_version: Literal["1.1"] = SCHEMA_VERSION
    symbol: str
    asset_class: AssetClass
    timeframe: Timeframe
    open_ts_ms: int
    close_ts_ms: int
    open: float
    high: float
    low: float
    close: float
    volume: float
    n_ticks: int
    buy_volume: float | None = None
    sell_volume: float | None = None


class SessionLevels(BaseModel):
    schema_version: Literal["1.1"] = SCHEMA_VERSION
    symbol: str
    asset_class: AssetClass
    session_type: SessionType
    session_start_ms: int
    session_end_ms: int
    open: float
    high: float
    low: float
    close: float
    volume: float
    updated_ts_ms: int


class VWAPValues(BaseModel):
    schema_version: Literal["1.1"] = SCHEMA_VERSION
    symbol: str
    asset_class: AssetClass
    anchor_type: AnchorType
    session_type: SessionType | None = None
    anchor_start_ms: int
    lookback_periods: int | None = None
    vwap: float
    sigma: float
    band_m3: float
    band_m2: float
    band_m1: float
    band_p1: float
    band_p2: float
    band_p3: float
    cum_volume: float
    n_obs: int
    updated_ts_ms: int


class FVGZone(BaseModel):
    schema_version: Literal["1.1"] = SCHEMA_VERSION
    id: str
    symbol: str
    asset_class: AssetClass
    direction: Literal["bullish", "bearish"]
    high: float
    low: float
    mitigated: bool = False
    created_ts_ms: int
    ttl_seconds: int | None = None


class SweepEvent(BaseModel):
    schema_version: Literal["1.1"] = SCHEMA_VERSION
    id: str
    symbol: str
    asset_class: AssetClass
    side: Literal["buy", "sell"]
    swept_level: float
    reclaim: bool | None = None
    ts_ms: int
    volume_profile: Literal["aggressive", "low_volume"] | None = None
    delta_divergence: bool | None = None
    time_to_reclaim_ms: int | None = None
    confirmed: bool | None = None


class MssEvent(BaseModel):
    schema_version: Literal["1.1"] = SCHEMA_VERSION
    id: str
    symbol: str
    asset_class: AssetClass
    ts_ms: int
    direction: Literal["bullish", "bearish"]
    broken_level: float
    swing_high: float | None
    swing_low: float | None
    trigger_sweep_id: str
    trigger_sweep_side: Literal["buy", "sell"]
    timeframe: Literal["1m", "5m", "15m"] | None = None
    confirmed: bool | None = None


class OrderBlock(BaseModel):
    schema_version: Literal["1.1"] = SCHEMA_VERSION
    id: str
    symbol: str
    asset_class: AssetClass
    direction: Literal["bullish", "bearish"]
    high: float
    low: float
    created_ts_ms: int
    mitigated: bool = False
    ttl_seconds: int | None = None
    timeframe: Timeframe | None = None
    displacement_ts_ms: int | None = None
    origin_open: float | None = None
    origin_close: float | None = None


SETUP_TYPES = (
    "sweep_reclaim",
    "fvg_entry",
    "mss_break",
    "order_block",
    "sweep_mss",
    "ob_fvg",
    "po3_judas",
    "sd_extension_fade",
    "vwap_pullback_cont",
    "avwap_ob_confluence",
)

SetupType = Literal[
    "sweep_reclaim",
    "fvg_entry",
    "mss_break",
    "order_block",
    "sweep_mss",
    "ob_fvg",
    "po3_judas",
    "sd_extension_fade",
    "vwap_pullback_cont",
    "avwap_ob_confluence",
]

# Quant GET /performance/summary product keys (docs / metadata alignment).
SETUP_PRODUCT_KEYS = {
    "sd_extension_fade": "4_sd_extension_fade",
    "vwap_pullback_cont": "5_vwap_pullback_cont",
    "avwap_ob_confluence": "6_avwap_ob_confluence",
}

RISK_TIMEFRAMES = ("1m", "5m", "15m")
RiskTimeframe = Literal["1m", "5m", "15m"]

# Exact POST /risk/validate body. Never include id / risk_reward / conviction / kill_zone*.
RISK_VALIDATE_FIELDS = (
    "schema_version",
    "symbol",
    "asset_class",
    "setup_type",
    "side",
    "confidence",
    "ref_vwap",
    "ref_session",
    "ts_ms",
    "entry",
    "stop",
    "target",
    "timeframe",
    "trigger_event_ids",
    "session_type",
    "proposed_position_size",
)


class SetupSignal(BaseModel):
    """Kafka ``setup_signals`` — Quant-locked Phase 2 payload (id only after approval)."""

    schema_version: Literal["1.1"] = SCHEMA_VERSION
    id: str
    symbol: str
    asset_class: AssetClass
    setup_type: SetupType
    side: Literal["long", "short"]
    confidence: float | None = None
    ref_vwap: float | None = None
    ref_session: str | None = None
    ts_ms: int
    entry: float | None = None
    stop: float | None = None
    target: float | None = None
    timeframe: RiskTimeframe | None = None
    trigger_event_ids: list[str] | None = None
    session_type: SessionType | None = None
    position_size: float | None = None
    status: Literal["ACTIVE", "TP_HIT", "SL_HIT", "CANCELLED"] | None = None
    contributing_factors: list[str] | None = None
    factor_breakdown: dict[str, float] | None = None


class RiskValidateRequest(BaseModel):
    """POST /risk/validate candidate. ``id`` is omitted on purpose."""

    schema_version: Literal["1.1"] = SCHEMA_VERSION
    symbol: str
    asset_class: AssetClass
    setup_type: SetupType
    side: Literal["long", "short"]
    ts_ms: int
    entry: float
    stop: float
    target: float
    timeframe: RiskTimeframe
    trigger_event_ids: list[str]
    confidence: float | None = None
    ref_vwap: float | None = None
    ref_session: str | None = None
    session_type: SessionType | None = None
    proposed_position_size: float | None = None


class RiskValidateResponse(BaseModel):
    approved: bool
    reason: str
    adjusted_position_size: float | None = None


# ── Phase 2 wire models (NO schema_version — exact Redis / Kafka payloads) ──


class AnchorSource(str, Enum):
    MANUAL = "manual"
    SWING_HIGH = "swing_high"
    SWING_LOW = "swing_low"
    EARNINGS = "earnings"
    NEWS = "news"


class AVWAPBands(BaseModel):
    plus_1_sigma: float
    plus_2_sigma: float
    plus_3_sigma: float
    minus_1_sigma: float
    minus_2_sigma: float
    minus_3_sigma: float


class AnchoredVWAP(BaseModel):
    """Redis ``avwap:{symbol}:{anchor_id}`` — exact Phase 2 payload."""

    anchor_id: str
    symbol: str
    anchor_time: int
    anchor_price: float
    vwap_value: float
    bands: AVWAPBands
    asset_class: AssetClass


class VolumeNode(BaseModel):
    price: float
    volume: float


class VolumeProfile(BaseModel):
    """Redis ``volume_profile:{symbol}:{session_type}`` — exact Phase 2 payload."""

    symbol: str
    session_type: SessionType
    high_volume_nodes: list[VolumeNode]
    low_volume_nodes: list[VolumeNode]
    poc: float
    timestamp: int


class KillZoneEvent(BaseModel):
    """Kafka ``kill_zone_events`` / Redis ``kill_zone:{symbol}`` — exact Phase 2 payload."""

    symbol: str
    kill_zone: SessionType
    start_time: int
    end_time: int
    active: bool
    asset_class: AssetClass


class AnchorMeta(BaseModel):
    """Internal Redis ``avwap:meta:{symbol}:{anchor_id}`` (not a wire schema)."""

    anchor_id: str
    symbol: str
    anchor_time: int
    anchor_price: float
    source: AnchorSource
    asset_class: AssetClass
    created_ts_ms: int


class AnchorRegistration(BaseModel):
    """HTTP / Kafka inbound contract for ML + manual anchors."""

    symbol: str
    anchor_time: int
    anchor_price: float
    source: AnchorSource = AnchorSource.MANUAL
    asset_class: AssetClass | None = None
    anchor_id: str | None = None
