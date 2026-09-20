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


class SetupSignal(BaseModel):
    schema_version: Literal["1.1"] = SCHEMA_VERSION
    id: str
    symbol: str
    asset_class: AssetClass
    setup_type: str
    side: Literal["long", "short"]
    confidence: float | None = None
    ref_vwap: float | None = None
    ref_session: str | None = None
    ts_ms: int
