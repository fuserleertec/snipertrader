"""Replay ML PR #9 quant_replay sample validate bodies against the Quant risk API.

Bodies match PR #9 locked-field handshake (no ``id``, no publish-only factors).
Geometry is the PR #9 e2e fixture world (session VWAP 100, S4 fade at −2σ,
S5 pullback engulf, S6 4h rejection into HTF OB).
https://github.com/fuserleertec/snipertrader/pull/9
"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from sniper_quant.api import create_app
from sniper_quant.backtest.params import DEFAULT_PARAMS
from sniper_quant.news import TEST_NEWS_TS_MS
from sniper_quant.risk.engine import RiskEngine, RiskState
from sniper_quant.store.signals import InMemorySignalStore
from tests.conftest import make_settings

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "pr9_quant_replay"
LOCKED = {
    "schema_version",
    "symbol",
    "asset_class",
    "setup_type",
    "side",
    "ts_ms",
    "entry",
    "stop",
    "target",
    "timeframe",
    "trigger_event_ids",
    "confidence",
    "ref_vwap",
    "ref_session",
    "session_type",
    "proposed_position_size",
}
FORBIDDEN = {"id", "contributing_factors", "factor_breakdown"}


def _client():
    settings = make_settings()
    engine = RiskEngine(settings=settings, state=RiskState(equity=100_000))
    return TestClient(create_app(settings=settings, signals=InMemorySignalStore(), engine=engine))


def _load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_pr9_defaults_match_locked_tunables():
    p = DEFAULT_PARAMS
    ml = p.to_ml_setup_params()
    assert p.s4_vol_max_frac == 0.8
    assert p.s4_vol_avg_period == 20
    assert p.s4_min_rr == 1.5
    assert p.s4_min_rr_at_3s == 2.0
    assert p.news_skip_minutes == 15
    assert ml["s4_news_window_sec"] == 900
    assert p.s5_trend_lookback_bars == 20
    assert p.s5_first_touch_window_bars == 8
    assert p.s5_min_rr == 2.0
    assert p.s6_min_rr == 2.0
    assert p.s6_min_conviction == 70
    assert p.s6_approach_tol_atr == 0.15
    assert p.s6_swing_lookback == 2
    assert p.dedupe_window_sec == 300
    assert ml["s6_htf_timeframes"] == ("1h", "4h")
    assert ml["s6_wire_timeframe"] == "15m"


def test_pr9_sample_validate_bodies_approve():
    http = _client()
    for name, setup in (
        ("sd_extension_fade.validate.json", "sd_extension_fade"),
        ("vwap_pullback_cont.validate.json", "vwap_pullback_cont"),
        ("avwap_ob_confluence.validate.json", "avwap_ob_confluence"),
    ):
        body = _load(name)
        assert body["setup_type"] == setup
        assert FORBIDDEN.isdisjoint(body)
        assert set(body) <= LOCKED
        resp = http.post("/risk/validate", json=body)
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["approved"] is True, (setup, data)
        assert data["reason"] == "ok"
        assert data["adjusted_position_size"] > 0


def test_pr9_sample_rejects_and_never_publishes():
    http = _client()
    s4 = _load("sd_extension_fade.validate.json")
    s4["ts_ms"] = TEST_NEWS_TS_MS
    news = http.post("/risk/validate", json=s4).json()
    assert news["approved"] is False
    assert news["reason"] == "news_window"

    s5 = _load("vwap_pullback_cont.validate.json")
    s5["stop"] = 96.0
    s5["target"] = 104.0
    low_rr = http.post("/risk/validate", json=s5).json()
    assert low_rr["approved"] is False
    assert low_rr["reason"] == "invalid_levels"

    s6 = _load("avwap_ob_confluence.validate.json")
    s6["confidence"] = 0.65
    low = http.post("/risk/validate", json=s6).json()
    assert low["approved"] is False
    assert low["reason"] == "low_conviction"
    pub = http.post("/signals", json=s6)
    assert pub.status_code == 409
    assert http.get("/signals").json()["items"] == []


def test_pr9_factors_rejected_on_validate_ok_on_publish():
    http = _client()
    body = _load("sd_extension_fade.validate.json")
    dirty = {
        **body,
        "contributing_factors": ["vwap_band_extension", "low_volume", "rejection_candle"],
        "factor_breakdown": [
            {"name": "vwap_band_extension", "weight": 20, "score": 25},
            {"name": "low_volume", "weight": 10, "score": 25},
            {"name": "rejection_candle", "weight": 15, "score": 25},
        ],
    }
    assert http.post("/risk/validate", json=dirty).status_code == 422
    clean = http.post("/risk/validate", json=body)
    assert clean.json()["approved"] is True
    published = http.post("/signals", json=dirty)
    assert published.status_code == 201
    row = published.json()
    assert row["contributing_factors"] == dirty["contributing_factors"]
    assert row["factor_breakdown"][0]["name"] == "vwap_band_extension"
    assert "id" in row
