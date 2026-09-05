from __future__ import annotations

import sys
from pathlib import Path

import pytest

from sniper_quant.config import Settings
from sniper_quant.models import AssetClass, CandidateSignal, Side
from sniper_quant.risk.engine import RiskEngine, RiskState

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def make_settings(**overrides) -> Settings:
    base = dict(
        USE_INMEMORY=True,
        DEFAULT_EQUITY=100_000,
        RISK_FRACTION=0.02,
        MAX_DAILY_LOSS_FRAC=0.03,
        CORR_LOOKBACK_DAYS=60,
        CORR_THRESHOLD=0.70,
        SL_ATR_MULTIPLE=2.0,
        TP_R_MULTIPLE=2.0,
        MIN_RR=1.5,
    )
    base.update(overrides)
    return Settings(**base)


def candidate(**kwargs) -> CandidateSignal:
    payload = dict(
        schema_version="1.1",
        symbol="BTCUSDT",
        asset_class=AssetClass.CRYPTO,
        setup_type="sweep_reclaim",
        side=Side.LONG,
        confidence=0.9,
        ts_ms=1_700_000_000_000,
        entry=100.0,
        stop=96.0,
        target=108.0,
        timeframe="15m",
        trigger_event_ids=["sweep-demo-1"],
    )
    payload.update(kwargs)
    return CandidateSignal.model_validate(payload)


@pytest.fixture
def settings() -> Settings:
    return make_settings()


@pytest.fixture
def engine(settings: Settings) -> RiskEngine:
    return RiskEngine(settings=settings, state=RiskState(equity=settings.default_equity))
