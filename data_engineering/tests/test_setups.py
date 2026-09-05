from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from sniper_data.bus.kafka import InMemoryBus
from sniper_data.bus.redis_store import InMemoryStateStore
from sniper_data.cli import main
from sniper_data.models import RISK_VALIDATE_FIELDS, Timeframe
from sniper_data.pattern_detection.fixtures import SYM, T0
from sniper_data.pattern_detection.validate import validate_topic
from sniper_data.setup_detection.candidate import attach_explainability, to_risk_request
from sniper_data.setup_detection.factors import STABLE_FACTORS, STABLE_FACTOR_SET
from sniper_data.setup_detection.fixtures import (
    asia_high_sweep,
    asia_session,
    atr_warmup,
    bearish_ob_overlap,
    bullish_fvg,
    bullish_mss_after_low,
    confirmed_buy_sweep,
    confirmed_sell_sweep,
    ny_am_kill_zone,
    seed_common,
    session_vwap,
    setup1_long_bars,
    setup1_short_bars,
    setup1_tight_rr_vwap,
    setup2_retrace_bars,
    setup3_judas_bars,
)
from sniper_data.setup_detection.orchestrator import SetupOrchestrator, dedupe_candidates
from sniper_data.setup_detection.replay import run_setup_replay
from sniper_data.setup_detection.risk_client import HttpRiskClient, StaticRiskClient
from sniper_data.setup_detection.setup1 import SweepReclaimDetector
from sniper_data.setup_detection.setup2 import FVGEntryDetector
from sniper_data.setup_detection.setup3 import JudasDetector
from sniper_data.zones import store_fvg, store_ob

ROOT = Path(__file__).resolve().parents[2]
SCHEMAS = ROOT / "schemas"

FORBIDDEN_RISK_KEYS = {"id", "risk_reward", "setup_id", "conviction", "kill_zone", "setup_number"}


def _assert_explain(c, *required: str) -> None:
    assert set(c.contributing_factors) <= STABLE_FACTOR_SET
    for name in required:
        assert name in c.contributing_factors
    assert isinstance(c.factor_breakdown, list) and c.factor_breakdown
    assert {row["name"] for row in c.factor_breakdown} == set(c.contributing_factors)
    total = sum(float(row["score"]) for row in c.factor_breakdown)
    assert abs(total - c.conviction) <= 0.05
    assert abs(c.confidence - c.conviction / 100.0) < 1e-9
    for row in c.factor_breakdown:
        assert {"name", "weight", "score"} <= set(row)


def _orch(store=None, bus=None, risk=None, lookback: int = 2) -> SetupOrchestrator:
    return SetupOrchestrator(
        store or InMemoryStateStore(),
        bus or InMemoryBus(),
        risk or StaticRiskClient(approved=True),
        swing_lookback=lookback,
    )


async def _warm(det, n: int = 14) -> None:
    for b in atr_warmup(n):
        await det.on_bar(b)


async def _setup1_long(store, det: SweepReclaimDetector, *, inject_mss: bool = True):
    det.on_vwap(session_vwap())
    await _warm(det)
    det.on_sweep(confirmed_buy_sweep())
    bars = setup1_long_bars(start=14)
    out = []
    for b in bars[:-1]:
        out.extend(await det.on_bar(b))
    if inject_mss:
        det.on_mss(bullish_mss_after_low(ts_ms=bars[-1].close_ts_ms))
    out.extend(await det.on_bar(bars[-1]))
    return out


@pytest.mark.asyncio
async def test_setup1_long_after_buy_side_low_sweep():
    store = InMemoryStateStore()
    await seed_common(store)
    det = SweepReclaimDetector(store, swing_lookback=2)
    cands = await _setup1_long(store, det)
    assert len(cands) == 1
    c = cands[0]
    assert c.setup_type == "sweep_reclaim"
    assert c.setup_number == 1
    assert c.side == "long"
    assert c.trigger_event_ids[0] == "swp-buy-low"
    assert any(i.startswith("mss") for i in c.trigger_event_ids)
    assert c.entry > c.stop
    assert c.target > c.entry
    assert c.risk_reward >= 2.0
    assert c.ref_vwap == 100.0
    assert 0 <= c.confidence <= 1
    _assert_explain(c, "liquidity_sweep", "mss", "vwap_reclaim")


@pytest.mark.asyncio
async def test_setup1_short_after_sell_side_high_sweep():
    store = InMemoryStateStore()
    await seed_common(store)
    det = SweepReclaimDetector(store, swing_lookback=2)
    det.on_vwap(session_vwap())
    await _warm(det)
    det.on_sweep(confirmed_sell_sweep())
    bars = setup1_short_bars(start=14)
    for b in bars[:-1]:
        assert await det.on_bar(b) == []
    det.on_mss(
        bullish_mss_after_low(ts_ms=bars[-1].close_ts_ms).model_copy(
            update={"id": "mss-reclaim-short", "direction": "bearish", "trigger_sweep_id": "swp-sell-high", "trigger_sweep_side": "sell"}
        )
    )
    cands = await det.on_bar(bars[-1])
    assert len(cands) == 1
    assert cands[0].setup_type == "sweep_reclaim"
    assert cands[0].side == "short"
    assert cands[0].target < cands[0].entry < cands[0].stop
    assert cands[0].risk_reward >= 2.0
    _assert_explain(cands[0], "liquidity_sweep", "mss", "vwap_reclaim")


@pytest.mark.asyncio
async def test_setup1_discards_rr_below_two():
    store = InMemoryStateStore()
    await seed_common(store, vwap=setup1_tight_rr_vwap())
    det = SweepReclaimDetector(store, swing_lookback=2)
    det.on_vwap(setup1_tight_rr_vwap())
    await _warm(det)
    det.on_sweep(confirmed_buy_sweep())
    bars = setup1_long_bars(start=14)
    for b in bars[:-1]:
        await det.on_bar(b)
    det.on_mss(bullish_mss_after_low(ts_ms=bars[-1].close_ts_ms))
    assert await det.on_bar(bars[-1]) == []


@pytest.mark.asyncio
async def test_setup1_ignores_unconfirmed_sweep():
    store = InMemoryStateStore()
    await seed_common(store)
    det = SweepReclaimDetector(store, swing_lookback=2)
    det.on_vwap(session_vwap())
    await _warm(det)
    raw = confirmed_buy_sweep().model_copy(update={"confirmed": False, "reclaim": False})
    det.on_sweep(raw)
    bars = setup1_long_bars(start=14)
    for b in bars[:-1]:
        await det.on_bar(b)
    det.on_mss(bullish_mss_after_low(ts_ms=bars[-1].close_ts_ms))
    assert await det.on_bar(bars[-1]) == []


@pytest.mark.asyncio
async def test_setup2_fvg_entry_at_vwap_node():
    store = InMemoryStateStore()
    await seed_common(store, fvg=True)
    det = FVGEntryDetector(store)
    det.on_vwap(session_vwap())
    det.on_fvg(bullish_fvg())
    cands = []
    for b in setup2_retrace_bars():
        cands.extend(await det.on_bar(b))
    assert len(cands) == 1
    c = cands[0]
    assert c.setup_type == "fvg_entry"
    assert c.side == "long"
    assert "fvg-bull-vwap" in c.trigger_event_ids
    assert c.target > c.entry > c.stop
    _assert_explain(c, "fvg", "engulfing")


@pytest.mark.asyncio
async def test_setup2_ob_fvg_when_order_block_overlaps():
    store = InMemoryStateStore()
    await seed_common(store, fvg=True, ob=True)
    await store_ob(store, bearish_ob_overlap())
    await store_fvg(store, bullish_fvg())
    det = FVGEntryDetector(store)
    det.on_vwap(session_vwap())
    det.on_fvg(bullish_fvg())
    cands = []
    for b in setup2_retrace_bars():
        cands.extend(await det.on_bar(b))
    assert cands
    assert cands[0].setup_type == "fvg_entry"
    assert "ob-bull-overlap" in cands[0].trigger_event_ids
    _assert_explain(cands[0], "fvg", "engulfing", "order_block")
    body = to_risk_request(cands[0])
    assert body["setup_type"] == "fvg_entry"


@pytest.mark.asyncio
async def test_setup3_po3_judas_asia_sweep_in_ny_am():
    store = InMemoryStateStore()
    await seed_common(store)
    det = JudasDetector(store)
    det.on_vwap(session_vwap())
    det.on_session(asia_session())
    det.on_kill_zone(ny_am_kill_zone())
    await _warm(det)
    det.on_sweep(asia_high_sweep())
    cands = []
    for b in setup3_judas_bars(start=14):
        cands.extend(await det.on_bar(b))
    assert len(cands) == 1
    c = cands[0]
    assert c.setup_type == "po3_judas"
    assert c.side == "short"
    assert c.trigger_event_ids == ["swp-asia-high"]
    assert c.target < c.entry < c.stop
    assert c.kill_zone == "ny_am"
    _assert_explain(c, "liquidity_sweep", "rejection_candle")


@pytest.mark.asyncio
async def test_setup3_requires_active_kill_zone():
    store = InMemoryStateStore()
    await seed_common(store)
    det = JudasDetector(store)
    det.on_vwap(session_vwap())
    det.on_session(asia_session())
    det.on_kill_zone(ny_am_kill_zone(active=False))
    await _warm(det)
    det.on_sweep(asia_high_sweep())
    cands = []
    for b in setup3_judas_bars(start=14):
        cands.extend(await det.on_bar(b))
    assert cands == []


def test_orchestrator_dedupe_keeps_highest_conviction():
    from sniper_data.models import AssetClass
    from sniper_data.setup_detection.candidate import SetupCandidate

    def _c(conv: int, ts: int, tf: str = "1m"):
        return SetupCandidate(
            setup_number=1,
            setup_type="sweep_reclaim",
            symbol=SYM,
            asset_class=AssetClass.CRYPTO,
            side="long",
            conviction=conv,
            entry=100,
            stop=99,
            target=104,
            timeframe=tf,  # type: ignore[arg-type]
            trigger_event_ids=["a"],
            ts_ms=ts,
            risk_reward=4.0,
        )

    kept = dedupe_candidates([_c(50, 1_000), _c(80, 1_000 + 60_000, "5m"), _c(40, 1_000 + 30_000, "15m")])
    assert len(kept) == 1
    assert kept[0].conviction == 80


@pytest.mark.asyncio
async def test_risk_reject_does_not_publish():
    store = InMemoryStateStore()
    bus = InMemoryBus()
    risk = StaticRiskClient(approved=False, reason="daily_loss")
    await seed_common(store)
    orch = _orch(store, bus, risk)
    orch.on_vwap(session_vwap())
    await _warm(orch)
    orch.on_sweep(confirmed_buy_sweep())
    bars = setup1_long_bars(start=14)
    for b in bars[:-1]:
        await orch.on_bar(b)
    orch.on_mss(bullish_mss_after_low(ts_ms=bars[-1].close_ts_ms))
    published = await orch.on_bar(bars[-1])
    assert published == []
    assert bus.topics.get("setup_signals", []) == []
    assert orch.stats.rejected >= 1
    assert orch.stats.published == 0
    assert orch.raw_log
    assert risk.calls
    body = risk.calls[0]
    assert "id" not in body
    assert set(body) <= set(RISK_VALIDATE_FIELDS)
    assert FORBIDDEN_RISK_KEYS.isdisjoint(body)
    assert body["setup_type"] == "sweep_reclaim"
    assert body["confidence"] == pytest.approx(body["confidence"])
    assert 0 <= body["confidence"] <= 1


@pytest.mark.asyncio
async def test_risk_http_client_omits_id_and_respects_schema():
    captured: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(json.loads(request.content))
        return httpx.Response(200, json={"approved": True, "reason": "ok", "adjusted_position_size": 2.5})

    client = HttpRiskClient("http://localhost:8001/risk/validate", transport=httpx.MockTransport(handler))
    store = InMemoryStateStore()
    await seed_common(store)
    det = SweepReclaimDetector(store, swing_lookback=2)
    cands = await _setup1_long(store, det)
    payload = to_risk_request(cands[0])
    decision = await client.validate(payload)
    assert decision.approved is True
    assert decision.adjusted_position_size == 2.5
    assert captured[0] == payload
    assert "id" not in captured[0]


@pytest.mark.asyncio
async def test_approved_publish_matches_setup_signal_schema():
    store = InMemoryStateStore()
    bus = InMemoryBus()
    risk = StaticRiskClient(approved=True, adjusted_position_size=3.0)
    await seed_common(store)
    orch = _orch(store, bus, risk)
    orch.on_vwap(session_vwap())
    await _warm(orch)
    orch.on_sweep(confirmed_buy_sweep())
    bars = setup1_long_bars(start=14)
    for b in bars[:-1]:
        await orch.on_bar(b)
    orch.on_mss(bullish_mss_after_low(ts_ms=bars[-1].close_ts_ms))
    published = await orch.on_bar(bars[-1])
    assert published
    records = [r["value"] for r in bus.topics["setup_signals"]]
    assert records
    payload = records[0]
    validate_topic("setup_signals", payload)
    assert payload["id"]
    assert payload["setup_type"] == "sweep_reclaim"
    assert payload["status"] == "ACTIVE"
    assert payload["position_size"] == 3.0
    assert "conviction" not in payload
    assert "risk_reward" not in payload
    assert "kill_zone" not in payload


@pytest.mark.asyncio
async def test_replay_emits_all_six_setup_types():
    result = await run_setup_replay()
    types = {s["setup_type"] for s in result["signals"]}
    assert "sweep_reclaim" in types
    assert "po3_judas" in types
    assert "fvg_entry" in types
    assert "ob_fvg" not in types
    assert all(b.get("setup_type") != "ob_fvg" for b in result["risk_calls"])
    assert "sd_extension_fade" in types
    assert "vwap_pullback_cont" in types
    assert "avwap_ob_confluence" in types
    assert len(result["signals"]) == 6
    for payload in result["signals"]:
        validate_topic("setup_signals", payload)
        assert "id" in payload
    for body in result["risk_calls"]:
        assert "id" not in body
        assert "contributing_factors" not in body
        assert set(body) <= set(RISK_VALIDATE_FIELDS)


def test_cli_setups_inmemory():
    rc = main(["setups", "--inmemory"])
    assert rc == 0


def test_cli_setups_e2e_report(tmp_path):
    dest = tmp_path / "phase2_e2e_report.json"
    rc = main(["setups", "--e2e-report", "--e2e-out", str(dest)])
    assert rc == 0
    report = json.loads(dest.read_text())
    assert report["summary"]["overall"] == "PASS"
    assert report["phase"] == 3
    pack = tmp_path / "quant_replay"
    assert (pack / "sweep_reclaim.validate.json").exists()
    assert (pack / "fvg_entry.validate.json").exists()
    assert (pack / "po3_judas.validate.json").exists()
    assert (pack / "sd_extension_fade.validate.json").exists()
    assert (pack / "vwap_pullback_cont.validate.json").exists()
    assert (pack / "avwap_ob_confluence.validate.json").exists()
    req = json.loads((pack / "sweep_reclaim.validate.json").read_text())
    sig = json.loads((pack / "sweep_reclaim.setup_signal.json").read_text())
    assert "id" not in req
    assert sig["id"]


@pytest.mark.asyncio
async def test_setup1_rejects_1m_timeframe():
    from sniper_data.pattern_detection.fixtures import bar as m1_bar

    store = InMemoryStateStore()
    await seed_common(store)
    det = SweepReclaimDetector(store)
    det.on_vwap(session_vwap())
    await _warm(det)
    det.on_sweep(confirmed_buy_sweep())
    seq = setup1_long_bars(start=14)
    last = None
    for i, b in enumerate(seq):
        last = m1_bar(30 + i, b.open, b.high, b.low, b.close, b.volume)
        if i == len(seq) - 1:
            det.on_mss(bullish_mss_after_low(ts_ms=last.close_ts_ms))
        assert await det.on_bar(last) == []


@pytest.mark.asyncio
async def test_setup2_skips_fvg_older_than_max_age():
    store = InMemoryStateStore()
    await seed_common(store, fvg=True)
    stale = bullish_fvg().model_copy(update={"created_ts_ms": T0 - 48 * 3_600_000})
    det = FVGEntryDetector(store)
    det.on_vwap(session_vwap())
    det.on_fvg(stale)
    cands = []
    for b in setup2_retrace_bars():
        cands.extend(await det.on_bar(b))
    assert cands == []


@pytest.mark.asyncio
async def test_setup3_requires_sigma_band_tag():
    store = InMemoryStateStore()
    await seed_common(store)
    det = JudasDetector(store)
    det.on_vwap(session_vwap())
    det.on_session(asia_session(high=110.0))
    det.on_kill_zone(ny_am_kill_zone())
    await _warm(det)
    far = asia_high_sweep().model_copy(update={"swept_level": 110.0})
    det.on_sweep(far)
    from sniper_data.pattern_detection.fixtures import bar as m1_bar
    from sniper_data.setup_detection.fixtures import S1_TF

    bars = [
        m1_bar(14, 108.0, 109.0, 107.5, 108.5, 40.0, timeframe=S1_TF),
        m1_bar(15, 108.5, 111.4, 108.2, 110.8, 90.0, timeframe=S1_TF),
        m1_bar(16, 110.6, 110.8, 101.2, 101.8, 120.0, timeframe=S1_TF),
    ]
    cands = []
    for b in bars:
        cands.extend(await det.on_bar(b))
    assert cands == []


@pytest.mark.asyncio
async def test_min_conviction_skips_validate():
    from sniper_data.models import AssetClass
    from sniper_data.setup_detection.candidate import SetupCandidate
    from sniper_data.setup_detection.params import SetupParams

    risk = StaticRiskClient(approved=True)
    orch = SetupOrchestrator(
        InMemoryStateStore(),
        InMemoryBus(),
        risk,
        params=SetupParams(min_conviction_to_validate=60),
    )
    weak = SetupCandidate(
        setup_number=1,
        setup_type="sweep_reclaim",
        symbol=SYM,
        asset_class=AssetClass.CRYPTO,
        side="long",
        conviction=45,
        entry=100,
        stop=99,
        target=104,
        timeframe="5m",
        trigger_event_ids=["a"],
        ts_ms=1_000,
        risk_reward=4.0,
    )
    published = await orch.submit([weak])
    assert published == []
    assert risk.calls == []
    assert orch.stats.skipped_conviction == 1
    assert orch.raw_log


def test_quant_walkforward_defaults():
    from sniper_data.setup_detection.params import SetupParams

    p = SetupParams()
    assert p.stop_buffer_atr == 0.05
    assert p.atr_period == 14
    assert p.s1_min_rr == 2.0
    assert p.s1_mss_swing_lookback == 5
    assert p.s1_max_bars_sweep_to_mss == 15
    assert p.s1_require_confirmed_sweep is True
    assert p.s1_timeframes == ("5m", "15m")
    assert p.s2_pin_wick_ratio == 2.5
    assert p.s2_max_fvg_age_hours == 24.0
    assert p.s3_displacement_min_body_atr == 1.2
    assert p.s3_require_band_tag is True
    assert p.s3_max_bars_sweep_to_displace == 6
    assert p.dedupe_window_sec == 300
    assert p.min_conviction_to_validate == 60
    assert p.s4_vol_frac == 0.8
    assert p.s4_min_rr == 1.5
    assert p.s4_min_rr_at_3s == 2.0
    assert p.s4_news_window_sec == 900
    assert p.s5_trend_bars == 20
    assert p.s5_first_touch_lookback_bars == 8
    assert p.s5_min_rr == 2.0
    assert p.s6_min_rr == 2.0
    assert p.s6_min_conviction == 70
    assert p.s6_approach_tol_atr == 0.15
    assert p.min_conviction_for("avwap_ob_confluence") == 70


def test_quant_schemas_include_po3_judas():
    setup = json.loads((SCHEMAS / "setup_signal.schema.json").read_text())
    req = json.loads((SCHEMAS / "risk_validate_request.schema.json").read_text())
    resp = json.loads((SCHEMAS / "risk_validate_response.schema.json").read_text())
    for doc in (setup, req):
        for slug in ("po3_judas", "sd_extension_fade", "vwap_pullback_cont", "avwap_ob_confluence"):
            assert slug in doc["properties"]["setup_type"]["enum"]
        assert doc["additionalProperties"] is False
        assert "id" not in req["required"]
    assert "contributing_factors" in setup["properties"]
    assert "contributing_factors" not in req["properties"]
    assert "id" not in req["properties"]
    assert resp["required"] == ["approved", "reason", "adjusted_position_size"]
    locked = set(req["properties"])
    assert locked == set(RISK_VALIDATE_FIELDS)
    assert Timeframe.M1.value in req["properties"]["timeframe"]["enum"]
    assert "factor_breakdown" in setup["properties"]
    assert "factor_breakdown" not in req["properties"]
    fb = setup["properties"]["factor_breakdown"]
    assert fb["type"] == ["array", "null"]
    assert fb["items"]["required"] == ["name", "weight", "score"]
    assert setup["properties"]["contributing_factors"]["items"]["enum"] == list(STABLE_FACTORS)
    assert fb["items"]["properties"]["name"]["enum"] == list(STABLE_FACTORS)
    assert "ob_fvg" not in req["properties"]["setup_type"]["enum"]
    assert "ob_fvg" not in setup["properties"]["setup_type"]["enum"]


@pytest.mark.asyncio
async def test_setup4_sd_extension_fade_long():
    from sniper_data.setup_detection.fixtures import setup4_fade_long_bars, setup4_vol_warmup
    from sniper_data.setup_detection.setup4 import SdExtensionFadeDetector

    store = InMemoryStateStore()
    await seed_common(store)
    det = SdExtensionFadeDetector(store)
    det.on_vwap(session_vwap())
    for b in setup4_vol_warmup():
        assert await det.on_bar(b) == []
    cands = []
    for b in setup4_fade_long_bars():
        cands.extend(await det.on_bar(b))
    assert len(cands) == 1
    c = cands[0]
    assert c.setup_type == "sd_extension_fade"
    assert c.side == "long"
    assert c.target == 100.0
    assert c.stop < 94.0
    assert c.risk_reward >= 1.5
    _assert_explain(c, "vwap_band_extension", "low_volume", "rejection_candle")


@pytest.mark.asyncio
async def test_setup4_news_stub_allows_and_skip_window_blocks():
    from sniper_data.setup_detection.fixtures import setup4_fade_long_bars, setup4_vol_warmup
    from sniper_data.setup_detection.news import AllowAllNewsFilter, SkipWindowNewsFilter
    from sniper_data.setup_detection.setup4 import SdExtensionFadeDetector

    store = InMemoryStateStore()
    await seed_common(store)
    det = SdExtensionFadeDetector(store, news=AllowAllNewsFilter())
    det.on_vwap(session_vwap())
    for b in setup4_vol_warmup():
        await det.on_bar(b)
    allowed = []
    for b in setup4_fade_long_bars():
        allowed.extend(await det.on_bar(b))
    assert allowed

    store2 = InMemoryStateStore()
    await seed_common(store2)
    last = setup4_fade_long_bars()[-1]
    blocked = SdExtensionFadeDetector(
        store2,
        news=SkipWindowNewsFilter({last.symbol: [last.close_ts_ms]}),
    )
    blocked.on_vwap(session_vwap())
    for b in setup4_vol_warmup():
        await blocked.on_bar(b)
    out = []
    for b in setup4_fade_long_bars():
        out.extend(await blocked.on_bar(b))
    assert out == []


@pytest.mark.asyncio
async def test_setup5_vwap_pullback_cont():
    from sniper_data.setup_detection.fixtures import (
        VWAP_SESSION,
        setup5_pullback_bars,
        setup5_rising_vwaps,
        setup5_trend_bars,
    )
    from sniper_data.setup_detection.setup5 import VwapPullbackContDetector
    from sniper_data.zones import store_fvg

    store = InMemoryStateStore()
    await seed_common(store, fvg=True)
    await store_fvg(store, bullish_fvg())
    det = VwapPullbackContDetector(store)
    det.on_fvg(bullish_fvg())
    trend = setup5_trend_bars()
    for snap, b in zip(setup5_rising_vwaps(len(trend)), trend, strict=True):
        det.on_vwap(snap)
        await det.on_bar(b)
    det.on_vwap(VWAP_SESSION)
    cands = []
    for b in setup5_pullback_bars(start=len(trend)):
        cands.extend(await det.on_bar(b))
    assert len(cands) == 1
    c = cands[0]
    assert c.setup_type == "vwap_pullback_cont"
    assert c.side == "long"
    assert c.risk_reward >= 2.0
    _assert_explain(c, "trend_align", "vwap_pullback", "first_touch")
    assert {"fvg", "order_block"} & set(c.contributing_factors)


@pytest.mark.asyncio
async def test_setup6_avwap_ob_confluence_uses_nested_bands():
    from sniper_data.setup_detection.fixtures import (
        phase2_avwap,
        seed_avwap,
        setup6_htf_warmup,
        setup6_rejection_bars,
    )
    from sniper_data.setup_detection.setup6 import AvwapObConfluenceDetector

    store = InMemoryStateStore()
    await seed_common(store)
    snap = await seed_avwap(store)
    dumped = snap.model_dump()
    assert "schema_version" not in dumped
    assert "band_p1" not in dumped
    assert "bands" in dumped
    assert set(dumped["bands"]) == {
        "plus_1_sigma",
        "plus_2_sigma",
        "plus_3_sigma",
        "minus_1_sigma",
        "minus_2_sigma",
        "minus_3_sigma",
    }
    assert dumped == phase2_avwap().model_dump()
    det = AvwapObConfluenceDetector(store)
    for b in setup6_htf_warmup():
        await det.on_bar(b)
    cands = []
    for b in setup6_rejection_bars():
        cands.extend(await det.on_bar(b))
    assert len(cands) == 1
    c = cands[0]
    assert c.setup_type == "avwap_ob_confluence"
    assert c.side == "long"
    assert c.ref_vwap == snap.vwap_value
    assert c.timeframe == "15m"
    assert c.conviction >= 70
    assert c.risk_reward >= 2.0
    _assert_explain(c, "avwap", "htf_ob", "rejection_candle")
    body = to_risk_request(c)
    assert "contributing_factors" not in body
    assert "factor_breakdown" not in body
    assert "id" not in body


def test_approved_signal_carries_factors_not_on_validate():
    from sniper_data.models import AssetClass
    from sniper_data.setup_detection.candidate import SetupCandidate, to_risk_request, to_setup_signal

    cand = SetupCandidate(
        setup_number=4,
        setup_type="sd_extension_fade",
        symbol=SYM,
        asset_class=AssetClass.CRYPTO,
        side="long",
        conviction=70,
        entry=96.2,
        stop=93.9,
        target=100.0,
        timeframe="5m",
        trigger_event_ids=["vwap-session-BTCUSDT"],
        ts_ms=T0,
        ref_vwap=100.0,
        session_type="london",
    )
    attach_explainability(cand, ["vwap_band_extension", "low_volume"])
    req = to_risk_request(cand)
    assert "contributing_factors" not in req
    assert "factor_breakdown" not in req
    sig = to_setup_signal(cand, "sig-test", position_size=1.0)
    dumped = sig.model_dump(mode="json", exclude_none=True)
    assert dumped["contributing_factors"] == ["vwap_band_extension", "low_volume"]
    assert isinstance(dumped["factor_breakdown"], list)
    assert {row["name"] for row in dumped["factor_breakdown"]} == {"vwap_band_extension", "low_volume"}
    assert abs(sum(row["score"] for row in dumped["factor_breakdown"]) - 70) <= 0.05
    assert dumped["confidence"] == 0.7
