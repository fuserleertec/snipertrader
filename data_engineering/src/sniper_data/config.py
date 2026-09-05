from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


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

    demo_symbols: str = Field(default="BTCUSDT,AAPL,ES", alias="DEMO_SYMBOLS")
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
    swing_lookback: int = Field(default=5, alias="SWING_LOOKBACK")
    risk_validate_url: str = Field(
        default="http://localhost:8001/risk/validate",
        alias="RISK_VALIDATE_URL",
    )

    # Quant walk-forward setup defaults (tunable; not magic numbers in detectors)
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

    # Setup 4 — sd_extension_fade
    setup4_vol_avg_period: int = Field(default=20, alias="SETUP4_VOL_AVG_PERIOD")
    setup4_vol_frac: float = Field(default=0.8, alias="SETUP4_VOL_FRAC")
    setup4_min_rr: float = Field(default=1.5, alias="SETUP4_MIN_RR")
    setup4_min_rr_at_3s: float = Field(default=2.0, alias="SETUP4_MIN_RR_AT_3S")
    setup4_news_window_sec: int = Field(default=900, alias="SETUP4_NEWS_WINDOW_SEC")
    setup4_min_conviction: int = Field(default=60, alias="SETUP4_MIN_CONVICTION")
    setup4_timeframes: str = Field(default="1m,5m", alias="SETUP4_TIMEFRAMES")
    setup4_pin_wick_ratio: float = Field(default=2.5, alias="SETUP4_PIN_WICK_RATIO")
    setup4_band_tag_frac: float = Field(default=0.25, alias="SETUP4_BAND_TAG_FRAC")

    # Setup 5 — vwap_pullback_cont
    setup5_trend_bars: int = Field(default=20, alias="SETUP5_TREND_BARS")
    setup5_timeframes: str = Field(default="5m", alias="SETUP5_TIMEFRAMES")
    setup5_first_touch_lookback_bars: int = Field(default=8, alias="SETUP5_FIRST_TOUCH_LOOKBACK_BARS")
    setup5_min_rr: float = Field(default=2.0, alias="SETUP5_MIN_RR")
    setup5_min_conviction: int = Field(default=60, alias="SETUP5_MIN_CONVICTION")
    setup5_pullback_tol_atr: float = Field(default=0.15, alias="SETUP5_PULLBACK_TOL_ATR")
    setup5_strong_body_frac: float = Field(default=0.5, alias="SETUP5_STRONG_BODY_FRAC")
    setup5_pin_wick_ratio: float = Field(default=2.5, alias="SETUP5_PIN_WICK_RATIO")
    setup5_liquidity_lookback_bars: int = Field(default=24, alias="SETUP5_LIQUIDITY_LOOKBACK_BARS")

    # Setup 6 — avwap_ob_confluence
    setup6_min_rr: float = Field(default=2.0, alias="SETUP6_MIN_RR")
    setup6_min_conviction: int = Field(default=70, alias="SETUP6_MIN_CONVICTION")
    setup6_htf_timeframes: str = Field(default="1h,4h", alias="SETUP6_HTF_TIMEFRAMES")
    setup6_wire_timeframe: str = Field(default="15m", alias="SETUP6_WIRE_TIMEFRAME")
    setup6_swing_lookback: int = Field(default=2, alias="SETUP6_SWING_LOOKBACK")
    setup6_daily_swing_lookback: int = Field(default=6, alias="SETUP6_DAILY_SWING_LOOKBACK")
    setup6_approach_tol_atr: float = Field(default=0.15, alias="SETUP6_APPROACH_TOL_ATR")
    setup6_pin_wick_ratio: float = Field(default=2.5, alias="SETUP6_PIN_WICK_RATIO")

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

    @property
    def symbols(self) -> list[str]:
        return [s.strip().upper() for s in self.demo_symbols.split(",") if s.strip()]

    @property
    def fvg_ttl_clamped(self) -> int:
        return max(1, min(int(self.fvg_ttl_seconds), FVG_TTL_MAX_SECONDS))


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
