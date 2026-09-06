from __future__ import annotations

from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from sniper_data.universe import DEFAULT_UNIVERSE_CSV, MAX_UNIVERSE_SYMBOLS, parse_universe


KAFKA_TOPICS = (
    "raw_ticks",
    "ohlcv_bars",
    "session_levels",
    "vwap_values",
    "sweep_events",
    "fvg_zones",
    "setup_signals",
    "mss_events",
    "order_block_zones",
    # Phase 2
    "kill_zone_events",
    "anchor_events",
    # Phase 3
    "options_chain",
    "order_flow",
    "performance_outcomes",
    # Multi-asset expansion (paper)
    "dashboard_snapshots",
)

FVG_TTL_MAX_SECONDS = 48 * 60 * 60  # 48 hours
NY_TZ = "America/New_York"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    env: str = Field(default="demo", alias="SNIPER_ENV")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    api_host: str = Field(default="0.0.0.0", alias="API_HOST")
    api_port: int = Field(default=8000, alias="API_PORT")

    kafka_bootstrap: str = Field(default="localhost:19092", alias="KAFKA_BOOTSTRAP")
    redis_url: str = Field(default="redis://localhost:6379/0", alias="REDIS_URL")
    database_url: str = Field(
        default="postgresql://sniper:sniper@localhost:5432/market",
        alias="DATABASE_URL",
    )

    dashboard_symbols: str = Field(default="", alias="DASHBOARD_SYMBOLS")
    universe: str = Field(default="", alias="UNIVERSE")
    demo_symbols: str = Field(default=DEFAULT_UNIVERSE_CSV, alias="DEMO_SYMBOLS")
    live_trading: bool = Field(default=False, alias="LIVE_TRADING")
    dashboard_snapshot_interval_s: int = Field(
        default=900, alias="DASHBOARD_SNAPSHOT_INTERVAL_S"
    )
    dashboard_snapshot_inprocess: bool = Field(
        default=True, alias="DASHBOARD_SNAPSHOT_INPROCESS"
    )
    seed_history: bool = Field(default=True, alias="SEED_HISTORY")
    seed_patterns: bool = Field(default=True, alias="SEED_PATTERNS")
    history_bars: int = Field(default=200, alias="HISTORY_BARS")
    rolling_vwap_periods: int = Field(default=20, alias="ROLLING_VWAP_PERIODS")
    fvg_ttl_seconds: int = Field(default=FVG_TTL_MAX_SECONDS, alias="FVG_TTL_SECONDS")
    tick_interval_ms: int = Field(default=80, alias="TICK_INTERVAL_MS")
    use_inmemory: bool = Field(default=False, alias="USE_INMEMORY")
    killzone_inprocess: bool = Field(default=True, alias="KILLZONE_INPROCESS")
    killzone_poll_s: float = Field(default=1.0, alias="KILLZONE_POLL_S")
    metrics_port: int = Field(default=0, alias="METRICS_PORT")
    max_anchors_per_symbol: int = Field(default=32, alias="MAX_ANCHORS_PER_SYMBOL")
    swing_detect: bool = Field(default=True, alias="SWING_DETECT")
    swing_left: int = Field(default=2, alias="SWING_LEFT")
    swing_right: int = Field(default=2, alias="SWING_RIGHT")

    kafka_partitions: int = Field(default=6, alias="KAFKA_PARTITIONS")
    kafka_send_wait: bool = Field(default=True, alias="KAFKA_SEND_WAIT")
    kafka_retries: int = Field(default=5, alias="KAFKA_RETRIES")
    redis_max_connections: int = Field(default=32, alias="REDIS_MAX_CONNECTIONS")
    redis_retries: int = Field(default=4, alias="REDIS_RETRIES")
    ws_heartbeat_s: float = Field(default=15.0, alias="WS_HEARTBEAT_S")
    ws_backlog: int = Field(default=64, alias="WS_BACKLOG")
    anchor_sync_interval_s: float = Field(default=1.0, alias="ANCHOR_SYNC_INTERVAL_S")
    demo_options_flow: bool = Field(default=True, alias="DEMO_OPTIONS_FLOW")
    outlier_move_pct: float = Field(default=0.08, alias="OUTLIER_MOVE_PCT")
    missing_tick_gap_ms: int = Field(default=5_000, alias="MISSING_TICK_GAP_MS")
    large_trade_notional: float = Field(default=250_000.0, alias="LARGE_TRADE_NOTIONAL")

    binance_api_key: str = Field(default="", alias="BINANCE_API_KEY")
    binance_api_secret: str = Field(default="", alias="BINANCE_API_SECRET")
    binance_ws_url: str = Field(
        default="wss://stream.binance.com:9443/ws", alias="BINANCE_WS_URL"
    )
    binance_rest_url: str = Field(
        default="https://api.binance.com", alias="BINANCE_REST_URL"
    )

    alpaca_api_key: str = Field(default="", alias="ALPACA_API_KEY")
    alpaca_secret_key: str = Field(default="", alias="ALPACA_SECRET_KEY")
    alpaca_base_url: str = Field(
        default="https://paper-api.alpaca.markets", alias="ALPACA_BASE_URL"
    )
    alpaca_data_ws_url: str = Field(
        default="wss://stream.data.alpaca.markets/v2/iex",
        alias="ALPACA_DATA_WS_URL",
    )

    @field_validator("live_trading")
    @classmethod
    def _paper_only(cls, value: bool) -> bool:
        if value:
            import logging

            logging.getLogger(__name__).warning(
                "LIVE_TRADING=true is ignored; this package is paper-only"
            )
        return False

    @property
    def symbols(self) -> list[str]:
        """DASHBOARD_SYMBOLS → UNIVERSE → DEMO_SYMBOLS. Max 20. Paper only."""
        return parse_universe(self.dashboard_symbols, self.universe, self.demo_symbols)

    @property
    def max_universe_symbols(self) -> int:
        return MAX_UNIVERSE_SYMBOLS

    @property
    def fvg_ttl_clamped(self) -> int:
        return max(1, min(int(self.fvg_ttl_seconds), FVG_TTL_MAX_SECONDS))


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
