"""PM extras on S4–S6: KZ bonus, S6 anchors, dedupe 300, publish-only factors."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi.testclient import TestClient
import pytest
from pydantic import ValidationError

from sniper_quant.api import create_app
from sniper_quant.backtest.detectors import (
    DETECTORS,
    _apply_orchestrator,
    _conviction,
    _kz_aligned,
    _s456_conviction,
    _s6_avwap,
    _swing_anchor_index,
    detect_avwap_ob_confluence,
    detect_sd_extension_fade,
    detect_vwap_pullback_cont,
)
from sniper_quant.backtest.engine import BacktestSignal
from sniper_quant.backtest.params import DEFAULT_PARAMS, KZ_CONVICTION_BONUS, with_params
from sniper_quant.backtest.synthetic_setups import synthetic_setup_tape
from sniper_quant.models import AssetClass, CandidateSignal, OHLCVBar, Side, StoredSignal
from sniper_quant.news import STUB_EARNINGS_TS_MS, calendar_anchor_events
from sniper_quant.risk.engine import RiskEngine, RiskState
from sniper_quant.setups import DORMANT_SETUP_TYPES, SETUP_TYPES, WALKFORWARD_S4_S6
from sniper_quant.store.signals import InMemorySignalStore
from tests.conftest import make_settings
from tests.test_validate import _payload

UTC = timezone.utc


def _bar(ts_ms: int, *, high: float = 101.0, low: float = 99.0, close: float = 100.0) -> OHLCVBar:
    return OHLCVBar(
        symbol="BTCUSDT",
        asset_class=AssetClass.CRYPTO,
        timeframe="5m",
        open_ts_ms=ts_ms,
        close_ts_ms=ts_ms + 299_999,
        open=close,
        high=high,
        low=low,
        close=close,
        volume=120.0,
    )


def test_kz_conviction_bonus_on_s4_s5_s6():
    assert KZ_CONVICTION_BONUS == 30
    with_kz = _conviction(confluence=1.0, volume_ok=True, kill_ok=True)
    without = _conviction(confluence=1.0, volume_ok=True, kill_ok=False)
    assert with_kz - without == KZ_CONVICTION_BONUS

    asia = _bar(int(datetime(2024, 6, 3, 1, 0, tzinfo=UTC).timestamp() * 1000))
    london = _bar(int(datetime(2024, 6, 3, 10, 0, tzinfo=UTC).timestamp() * 1000))
    assert _kz_aligned(asia, DEFAULT_PARAMS) is False
    assert _kz_aligned(london, DEFAULT_PARAMS) is True
    assert _s456_conviction(
        confluence=1.0, volume_ok=True, bar=london, params=DEFAULT_PARAMS
    ) - _s456_conviction(confluence=1.0, volume_ok=True, bar=asia, params=DEFAULT_PARAMS) == 30

    bars = synthetic_setup_tape("BTCUSDT", cycles=6, timeframe="5m")
    assert detect_sd_extension_fade(bars, DEFAULT_PARAMS)
    assert detect_vwap_pullback_cont(bars, DEFAULT_PARAMS)
    s6 = detect_avwap_ob_confluence(bars, DEFAULT_PARAMS)
    assert s6
    # S6 no longer hardcodes kill_ok=True — Asia confirms cannot get the bonus.
    asia_s6 = [s for s in s6 if not _kz_aligned(_bar(s.ts_ms - 299_999), DEFAULT_PARAMS)]
    in_kz = [s for s in s6 if _kz_aligned(_bar(s.ts_ms - 299_999), DEFAULT_PARAMS)]
    if asia_s6 and in_kz:
        assert max(s.confidence or 0 for s in in_kz) >= max(s.confidence or 0 for s in asia_s6)


def test_s6_swing_and_calendar_anchors():
    start = int(datetime(2024, 6, 3, 8, 0, tzinfo=UTC).timestamp() * 1000)
    bars = []
    for i in range(25):
        ts = start + i * 300_000
        high = 110.0 if i == 5 else 101.0 + i * 0.01
        low = 90.0 if i == 8 else 99.0
        bars.append(_bar(ts, high=high, low=low, close=100.0 + i * 0.02))
    i = 20
    assert _swing_anchor_index(bars, i, 20, kind="swing_high") == 5
    assert _swing_anchor_index(bars, i, 20, kind="swing_low") == 8
    events = calendar_anchor_events(bars[i].open_ts_ms, kinds=("earnings", "news"))
    assert any(e.kind == "earnings" and e.ts_ms == STUB_EARNINGS_TS_MS for e in events) or (
        bars[i].open_ts_ms <= STUB_EARNINGS_TS_MS
    )
    later = _bar(STUB_EARNINGS_TS_MS + 3_600_000)
    assert any(e.kind == "earnings" for e in calendar_anchor_events(later.open_ts_ms))

    ob_only = with_params(DEFAULT_PARAMS, s6_anchor="ob")
    swing = with_params(DEFAULT_PARAMS, s6_anchor="swing_high")
    origin_ts = bars[2].open_ts_ms
    av_ob = _s6_avwap(bars, i, origin_ts, ob_only)
    av_sw = _s6_avwap(bars, i, origin_ts, swing)
    assert av_ob > 0 and av_sw > 0
    tape = synthetic_setup_tape("BTCUSDT", cycles=6, timeframe="5m")
    assert detect_avwap_ob_confluence(tape, DEFAULT_PARAMS)
    assert detect_avwap_ob_confluence(tape, swing)


def test_orchestrator_dedupe_window_sec_default_300():
    assert DEFAULT_PARAMS.dedupe_window_sec == 300
    base = dict(
        symbol="BTCUSDT",
        setup_type="sd_extension_fade",
        side=Side.LONG,
        entry=100.0,
        stop=96.0,
        target=108.0,
        confidence=0.8,
    )
    close = [
        BacktestSignal(ts_ms=1_000_000, **base),
        BacktestSignal(ts_ms=1_000_000 + 60_000, **base),
    ]
    kept = _apply_orchestrator(close, DEFAULT_PARAMS)
    assert len(kept) == 1
    spaced = [
        BacktestSignal(ts_ms=1_000_000, **base),
        BacktestSignal(ts_ms=1_000_000 + 400_000, **base),
    ]
    assert len(_apply_orchestrator(spaced, DEFAULT_PARAMS)) == 2


def test_contributing_factors_publish_only_string_array():
    assert "contributing_factors" not in CandidateSignal.model_fields
    with pytest.raises(ValidationError):
        CandidateSignal.model_validate(_payload(contributing_factors=["kz_align"]))
    stored = StoredSignal.model_validate(
        {
            **_payload(),
            "id": "sig-1",
            "contributing_factors": ["kz_align", "2s_tag"],
        }
    )
    assert stored.contributing_factors == ["kz_align", "2s_tag"]
    http = TestClient(
        create_app(
            settings=make_settings(),
            signals=InMemorySignalStore(),
            engine=RiskEngine(settings=make_settings(), state=RiskState(equity=100_000)),
        )
    )
    assert http.post("/risk/validate", json=_payload(contributing_factors=["kz"])).status_code == 422
    spec = http.get("/openapi.json").json()
    cand = spec["components"]["schemas"]["CandidateSignal"]["properties"]
    assert "contributing_factors" not in cand
    items = spec["components"]["schemas"]["PublishBody"]["properties"]["contributing_factors"]["items"]
    assert items["type"] == "string"
    view = spec["components"]["schemas"]["SignalView"]["properties"]
    assert view["contributing_factors"]["items"]["type"] == "string"
    row = spec["components"]["schemas"]["FactorBreakdownRow"]
    assert set(row["required"]) >= {"name", "weight", "score"}

    import json
    from pathlib import Path

    schemas = Path(__file__).resolve().parents[2] / "schemas"
    setup = json.loads((schemas / "setup_signal.schema.json").read_text())
    dash = json.loads((schemas / "dashboard_signal.schema.json").read_text())
    validate = json.loads((schemas / "risk_validate_request.schema.json").read_text())
    assert "contributing_factors" in setup["properties"]
    assert "factor_breakdown" in setup["properties"]
    assert set(setup["properties"]["factor_breakdown"]["items"]["required"]) >= {
        "name",
        "weight",
        "score",
    }
    assert "contributing_factors" in dash["properties"]
    assert "factor_breakdown" in dash["properties"]
    assert "contributing_factors" not in validate["properties"]
    assert "factor_breakdown" not in validate["properties"]


def test_s4_s6_enum_and_detectors_exclude_dormant():
    assert WALKFORWARD_S4_S6 == (
        "sd_extension_fade",
        "vwap_pullback_cont",
        "avwap_ob_confluence",
    )
    assert set(DETECTORS) == set(SETUP_TYPES)
    for dead in DORMANT_SETUP_TYPES:
        assert dead not in DETECTORS
        assert dead not in WALKFORWARD_S4_S6
