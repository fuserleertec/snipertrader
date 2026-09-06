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
    "ensemble_features",
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
    setup_universe: str = Field(default="", alias="SETUP_UNIVERSE")
    universe_backend: str = Field(default="auto", alias="UNIVERSE_BACKEND")
    universe_http_url: str = Field(default="", alias="UNIVERSE_HTTP_URL")
    setup_refresh_minutes: int = Field(default=15, alias="SETUP_REFRESH_MINUTES")
    live_trading: bool = Field(default=False, alias="LIVE_TRADING")
    risk_validate_url: str = Field(
        default="http://localhost:8001/risk/validate",
        alias="RISK_VALIDATE_URL",
    )
    swing_lookback: int = Field(default=5, alias="SWING_LOOKBACK")
    setup_atr_period: int = Field(default=14, alias="SETUP_ATR_PERIOD")
    setup_stop_buffer_atr: float = Field(default=0.05, alias="SETUP_STOP_BUFFER_ATR")
    setup1_min_rr: float = Field(default=2.0, alias="SETUP1_MIN_RR")
    setup1_mss_swing_lookback: int = Field(default=5, alias="SETUP1_MSS_SWING_LOOKBACK")
    setup1_max_bars_sweep_to_mss: int = Field(default=15, alias="SETUP1_MAX_BARS_SWEEP_TO_MSS")
    setup1_require_confirmed_sweep: bool = Field(default=True, alias="SETUP1_REQUIRE_CONFIRMED_SWEEP")
    setup1_timeframes: str = Field(default="5m,15m", alias="SETUP1_TIMEFRAMES")
    setup2_overlap_tol_atr: float = Field(default=0.05, alias="SETUP2_OVERLAP_TOL_ATR")
    setup2_pin_wick_ratio: float = Field(default=2.5, alias="SETUP2_PIN_WICK_RATIO")
    setup2_max_fvg_age_hours: float = Field(default=24.0, alias="SETUP2_MAX_FVG_AGE_HOURS")
    setup2_target_rr_fallback: float = Field(default=2.0, alias="SETUP2_TARGET_RR_FALLBACK")
    setup3_accum_session: str = Field(default="asia", alias="SETUP3_ACCUM_SESSION")
    setup3_kill_zone: str = Field(default="ny_am", alias="SETUP3_KILL_ZONE")
    setup3_displacement_min_body_atr: float = Field(default=1.2, alias="SETUP3_DISPLACEMENT_MIN_BODY_ATR")
    setup3_require_band_tag: bool = Field(default=True, alias="SETUP3_REQUIRE_BAND_TAG")
    setup3_max_bars_sweep_to_displace: int = Field(default=6, alias="SETUP3_MAX_BARS_SWEEP_TO_DISPLACE")
    setup_dedupe_window_sec: int = Field(default=300, alias="SETUP_DEDUPE_WINDOW_SEC")
    setup_min_conviction_to_validate: int = Field(default=60, alias="SETUP_MIN_CONVICTION_TO_VALIDATE")
    setup_atr_regime_high_frac: float = Field(default=0.02, alias="SETUP_ATR_REGIME_HIGH_FRAC")
    setup_conv_kill_zone_bonus: int = Field(default=10, alias="SETUP_CONV_KILL_ZONE_BONUS")
    setup_conv_volume_bonus: int = Field(default=10, alias="SETUP_CONV_VOLUME_BONUS")
    setup_conv_multi_pattern_bonus: int = Field(default=10, alias="SETUP_CONV_MULTI_PATTERN_BONUS")
    setup4_vol_avg_period: int = Field(default=20, alias="SETUP4_VOL_AVG_PERIOD")
    setup4_vol_frac: float = Field(default=0.8, alias="SETUP4_VOL_FRAC")
    setup4_min_rr: float = Field(default=1.5, alias="SETUP4_MIN_RR")
    setup4_min_rr_at_3s: float = Field(default=2.0, alias="SETUP4_MIN_RR_AT_3S")
    setup4_news_window_sec: int = Field(default=900, alias="SETUP4_NEWS_WINDOW_SEC")
    setup4_min_conviction: int = Field(default=60, alias="SETUP4_MIN_CONVICTION")
    setup4_timeframes: str = Field(default="1m,5m", alias="SETUP4_TIMEFRAMES")
    setup4_pin_wick_ratio: float = Field(default=2.5, alias="SETUP4_PIN_WICK_RATIO")
    setup4_band_tag_frac: float = Field(default=0.25, alias="SETUP4_BAND_TAG_FRAC")
    setup5_trend_bars: int = Field(default=20, alias="SETUP5_TREND_BARS")
    setup5_timeframes: str = Field(default="1m,5m", alias="SETUP5_TIMEFRAMES")
    setup5_first_touch_lookback_bars: int = Field(default=8, alias="SETUP5_FIRST_TOUCH_LOOKBACK_BARS")
    setup5_min_rr: float = Field(default=2.0, alias="SETUP5_MIN_RR")
    setup5_min_conviction: int = Field(default=60, alias="SETUP5_MIN_CONVICTION")
    setup5_pullback_tol_atr: float = Field(default=0.15, alias="SETUP5_PULLBACK_TOL_ATR")
    setup5_strong_body_frac: float = Field(default=0.5, alias="SETUP5_STRONG_BODY_FRAC")
    setup5_pin_wick_ratio: float = Field(default=2.5, alias="SETUP5_PIN_WICK_RATIO")
    setup5_liquidity_lookback_bars: int = Field(default=24, alias="SETUP5_LIQUIDITY_LOOKBACK_BARS")
    setup6_min_rr: float = Field(default=2.0, alias="SETUP6_MIN_RR")
    setup6_min_conviction: int = Field(default=70, alias="SETUP6_MIN_CONVICTION")
    setup6_htf_timeframes: str = Field(default="1h,4h", alias="SETUP6_HTF_TIMEFRAMES")
    setup6_wire_timeframe: str = Field(default="15m", alias="SETUP6_WIRE_TIMEFRAME")
    setup6_swing_lookback: int = Field(default=2, alias="SETUP6_SWING_LOOKBACK")
    setup6_daily_swing_lookback: int = Field(default=6, alias="SETUP6_DAILY_SWING_LOOKBACK")
    setup6_approach_tol_atr: float = Field(default=0.15, alias="SETUP6_APPROACH_TOL_ATR")
    setup6_pin_wick_ratio: float = Field(default=2.5, alias="SETUP6_PIN_WICK_RATIO")
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
