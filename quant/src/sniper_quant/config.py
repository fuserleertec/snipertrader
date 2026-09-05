from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


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
    api_port: int = Field(default=8001, alias="API_PORT")

    database_url: str = Field(
        default="postgresql://sniper:sniper@localhost:5432/market",
        alias="DATABASE_URL",
    )
    redis_url: str = Field(default="redis://localhost:6379/0", alias="REDIS_URL")
    use_inmemory: bool = Field(default=False, alias="USE_INMEMORY")

    default_equity: float = Field(default=100_000.0, alias="DEFAULT_EQUITY")
    risk_fraction: float = Field(default=0.02, alias="RISK_FRACTION")
    max_daily_loss_frac: float = Field(default=0.03, alias="MAX_DAILY_LOSS_FRAC")
    corr_lookback_days: int = Field(default=60, alias="CORR_LOOKBACK_DAYS")
    corr_threshold: float = Field(default=0.70, alias="CORR_THRESHOLD")
    sl_atr_multiple: float = Field(default=2.0, alias="SL_ATR_MULTIPLE")
    tp_r_multiple: float = Field(default=2.0, alias="TP_R_MULTIPLE")
    min_rr: float = Field(default=1.5, alias="MIN_RR")
    commission_bps: float = Field(default=1.0, alias="COMMISSION_BPS")
    slippage_bps: float = Field(default=2.0, alias="SLIPPAGE_BPS")
    account_id: str = Field(default="default", alias="ACCOUNT_ID")
    kafka_bootstrap: str = Field(default="localhost:19092", alias="KAFKA_BOOTSTRAP")
    kafka_group: str = Field(default="sniper-quant-validate", alias="KAFKA_GROUP")
    alert_win_rate: float = Field(default=0.35, alias="ALERT_WIN_RATE")
    alert_avg_rr: float = Field(default=0.50, alias="ALERT_AVG_RR")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
