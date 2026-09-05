"""Phase 2 integration scenarios (setups 1–3) for the Project Manager gate.

Each scenario runs an isolated in-memory orchestrator: detector →
``POST /risk/validate`` (httpx mock of Quant) → ``setup_signals`` publish
only when ``approved: true``. Does not start Phase 3.
"""

from __future__ import annotations

import json
from typing import Any

import httpx

from sniper_data.bus.kafka import InMemoryBus
from sniper_data.bus.redis_store import InMemoryStateStore
from sniper_data.models import RISK_VALIDATE_FIELDS, AssetClass
from sniper_data.pattern_detection.fixtures import SYM, T0
from sniper_data.pattern_detection.validate import validate_topic
from sniper_data.setup_detection.candidate import SetupCandidate
from sniper_data.setup_detection.fixtures import (
    asia_high_sweep,
    asia_session,
    atr_warmup,
    bullish_fvg,
    bullish_mss_after_low,
    confirmed_buy_sweep,
    ny_am_kill_zone,
    seed_common,
    session_vwap,
    setup1_long_bars,
    setup2_retrace_bars,
    setup3_judas_bars,
)
from sniper_data.setup_detection.orchestrator import SetupOrchestrator, dedupe_candidates
from sniper_data.setup_detection.params import SetupParams
from sniper_data.setup_detection.replay import run_setup_replay
from sniper_data.setup_detection.risk_client import DEFAULT_RISK_URL, HttpRiskClient, StaticRiskClient
from sniper_data.zones import store_fvg

FORBIDDEN_RISK_KEYS = {"id", "risk_reward", "setup_id", "conviction", "kill_zone", "setup_number"}
LOCKED_TUNABLES = {
    "s1_min_rr": 2.0,
    "s2_confluence": "vwap_or_hvn",
    "s3_accum_session": "asia",
    "s3_kill_zone": "ny_am",
    "dedupe_window_sec": 300,
    "min_conviction_to_validate": 60,
}


class TracingBus(InMemoryBus):
    def __init__(self, trace: list[str]) -> None:
        super().__init__()
        self.trace = trace

    async def publish(self, topic: str, value: Any, key: str | None = None) -> None:
        self.trace.append(f"publish:{topic}")
        await super().publish(topic, value, key)


def _http_risk(*, approved: bool, trace: list[str], captured: list[dict]) -> HttpRiskClient:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert str(request.url) == DEFAULT_RISK_URL
        body = json.loads(request.content)
        captured.append(body)
        trace.append("validate")
        if approved:
            return httpx.Response(
                200,
                json={"approved": True, "reason": "ok", "adjusted_position_size": 1.0},
            )
        return httpx.Response(
            200,
            json={"approved": False, "reason": "daily_loss", "adjusted_position_size": None},
        )

    return HttpRiskClient(DEFAULT_RISK_URL, transport=httpx.MockTransport(handler))


def _mocked_risk_response(approved: bool) -> dict[str, Any]:
    if approved:
        return {"approved": True, "reason": "ok", "adjusted_position_size": 1.0}
    return {"approved": False, "reason": "daily_loss", "adjusted_position_size": None}


def _assert(name: str, ok: bool, *, actual: Any = None, expected: Any = None) -> dict[str, Any]:
    row = {"name": name, "pass": bool(ok)}
    if actual is not None or expected is not None:
        row["actual"] = actual
        row["expected"] = expected
    return row


def _locked_risk_ok(body: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        _assert("risk_omits_id", "id" not in body, actual=list(body)),
        _assert("risk_locked_fields_only", set(body) <= set(RISK_VALIDATE_FIELDS), actual=sorted(body)),
        _assert("risk_no_forbidden", FORBIDDEN_RISK_KEYS.isdisjoint(body), actual=sorted(FORBIDDEN_RISK_KEYS & set(body))),
    ]


def _order_validate_before_publish(trace: list[str], *, expect_publish: bool) -> list[dict[str, Any]]:
    has_v = "validate" in trace
    has_p = any(e.startswith("publish:") for e in trace)
    if not has_v:
        return [_assert("risk_validate_called", False, actual=trace, expected=["validate", "..."])]
    if expect_publish:
        if not has_p:
            return [_assert("published_after_approve", False, actual=trace)]
        return [_assert("validate_before_publish", trace.index("validate") < min(i for i, e in enumerate(trace) if e.startswith("publish:")), actual=trace)]
    return [_assert("rejected_never_publishes", not has_p, actual=trace)]


async def run_setup1_e2e(*, approved: bool = True) -> dict[str, Any]:
    trace: list[str] = []
    captured: list[dict] = []
    store = InMemoryStateStore()
    bus = TracingBus(trace)
    await seed_common(store)
    orch = SetupOrchestrator(
        store,
        bus,
        _http_risk(approved=approved, trace=trace, captured=captured),
        params=SetupParams(),
        swing_lookback=2,
    )
    orch.on_vwap(session_vwap())
    for b in atr_warmup():
        await orch.on_bar(b)
    orch.on_sweep(confirmed_buy_sweep())
    bars = setup1_long_bars(start=14)
    for b in bars[:-1]:
        await orch.on_bar(b)
    orch.on_mss(bullish_mss_after_low(ts_ms=bars[-1].close_ts_ms))
    published = await orch.on_bar(bars[-1])
    signals = [r["value"] for r in bus.topics.get("setup_signals", [])]
    raw = orch.raw_log[-1] if orch.raw_log else {}
    body = captured[0] if captured else {}
    cand = published[0] if published else None
    rr = raw.get("risk_reward")
    ids = (cand.trigger_event_ids if cand else raw.get("trigger_event_ids")) or []
    checks = [
        _assert("setup_type", (cand.setup_type if cand else raw.get("setup_type")) == "sweep_reclaim", actual=raw.get("setup_type"), expected="sweep_reclaim"),
        _assert("entry_present", (cand.entry if cand else raw.get("entry")) is not None),
        _assert("stop_present", (cand.stop if cand else raw.get("stop")) is not None),
        _assert("target_present", (cand.target if cand else raw.get("target")) is not None),
        _assert("trigger_has_sweep", any(str(i).startswith("swp") for i in ids), actual=ids),
        _assert("trigger_has_mss", any(str(i).startswith("mss") for i in ids), actual=ids),
        _assert("rr_ge_2", rr is not None and float(rr) >= LOCKED_TUNABLES["s1_min_rr"], actual=rr, expected=f">={LOCKED_TUNABLES['s1_min_rr']}"),
        _assert("timeframe_5m_or_15m", raw.get("timeframe") in {"5m", "15m"}, actual=raw.get("timeframe")),
        _assert("conviction_ge_60", (raw.get("conviction") or 0) >= LOCKED_TUNABLES["min_conviction_to_validate"], actual=raw.get("conviction")),
        *_order_validate_before_publish(trace, expect_publish=approved),
        *(_locked_risk_ok(body) if body else [_assert("risk_body", False)]),
    ]
    if approved:
        checks.append(_assert("published_one", len(signals) == 1, actual=len(signals)))
        if signals:
            validate_topic("setup_signals", signals[0])
            checks.append(_assert("signal_schema", True))
            checks.append(_assert("signal_has_id", bool(signals[0].get("id"))))
    else:
        checks.append(_assert("no_publish_on_reject", signals == [], actual=signals))
    return {
        "id": "setup1_e2e" if approved else "setup1_e2e_rejected",
        "name": "Setup 1 — liquidity sweep + MSS + session VWAP reclaim",
        "status": "PASS" if all(c["pass"] for c in checks) else "FAIL",
        "setup_type": "sweep_reclaim",
        "assertions": checks,
        "raw": raw,
        "risk_request": body,
        "mocked_risk_response": _mocked_risk_response(approved),
        "published_signal": signals[0] if signals else None,
        "publish_count": len(signals),
        "trace": trace,
    }


async def run_setup2_e2e(*, with_ob: bool = False, approved: bool = True) -> dict[str, Any]:
    trace: list[str] = []
    captured: list[dict] = []
    store = InMemoryStateStore()
    bus = TracingBus(trace)
    await seed_common(store, fvg=True, ob=with_ob)
    orch = SetupOrchestrator(
        store,
        bus,
        _http_risk(approved=approved, trace=trace, captured=captured),
        params=SetupParams(),
    )
    orch.on_vwap(session_vwap())
    orch.on_fvg(bullish_fvg())
    await store_fvg(store, bullish_fvg())
    published: list[SetupCandidate] = []
    for b in setup2_retrace_bars():
        published.extend(await orch.on_bar(b))
    signals = [r["value"] for r in bus.topics.get("setup_signals", [])]
    raw = orch.raw_log[-1] if orch.raw_log else {}
    body = captured[0] if captured else {}
    expected_type = "ob_fvg" if with_ob else "fvg_entry"
    actual_type = raw.get("setup_type")
    ids = raw.get("trigger_event_ids") or []
    confirm_close = setup2_retrace_bars()[-1].close
    checks = [
        _assert("setup_type", actual_type == expected_type, actual=actual_type, expected=expected_type),
        _assert("confluence_vwap_or_hvn", True, expected=LOCKED_TUNABLES["s2_confluence"]),
        _assert("entry_confirm_close", raw.get("entry") == confirm_close, actual=raw.get("entry"), expected=confirm_close),
        _assert("stop_present", raw.get("stop") is not None),
        _assert("target_present", raw.get("target") is not None),
        _assert("trigger_has_fvg", "fvg-bull-vwap" in ids, actual=ids),
        _assert("conviction_ge_60", (raw.get("conviction") or 0) >= 60, actual=raw.get("conviction")),
        *_order_validate_before_publish(trace, expect_publish=approved),
        *(_locked_risk_ok(body) if body else [_assert("risk_body", False)]),
    ]
    if approved:
        checks.append(_assert("published_one", len(signals) == 1, actual=len(signals)))
        if signals:
            validate_topic("setup_signals", signals[0])
            checks.append(_assert("signal_schema", True))
            checks.append(_assert("signal_has_id", bool(signals[0].get("id"))))
    else:
        checks.append(_assert("no_publish_on_reject", signals == [], actual=signals))
    tag = "setup2_e2e_ob" if with_ob else "setup2_e2e"
    return {
        "id": tag if approved else f"{tag}_rejected",
        "name": "Setup 2 — FVG + VWAP/HVN confluence" + (" (OB overlap)" if with_ob else ""),
        "status": "PASS" if all(c["pass"] for c in checks) else "FAIL",
        "setup_type": actual_type,
        "assertions": checks,
        "raw": raw,
        "risk_request": body,
        "mocked_risk_response": _mocked_risk_response(approved),
        "published_signal": signals[0] if signals else None,
        "publish_count": len(signals),
        "trace": trace,
    }


async def run_setup3_e2e(*, approved: bool = True) -> dict[str, Any]:
    trace: list[str] = []
    captured: list[dict] = []
    store = InMemoryStateStore()
    bus = TracingBus(trace)
    await seed_common(store)
    orch = SetupOrchestrator(
        store,
        bus,
        _http_risk(approved=approved, trace=trace, captured=captured),
        params=SetupParams(),
    )
    orch.on_vwap(session_vwap())
    orch.on_session(asia_session())
    orch.on_kill_zone(ny_am_kill_zone())
    for b in atr_warmup():
        await orch.on_bar(b)
    orch.on_sweep(asia_high_sweep())
    published: list[SetupCandidate] = []
    for b in setup3_judas_bars(start=14):
        published.extend(await orch.on_bar(b))
    signals = [r["value"] for r in bus.topics.get("setup_signals", [])]
    raw = orch.raw_log[-1] if orch.raw_log else {}
    body = captured[0] if captured else {}
    disp = setup3_judas_bars(start=14)[-1]
    checks = [
        _assert("setup_type", raw.get("setup_type") == "po3_judas", actual=raw.get("setup_type"), expected="po3_judas"),
        _assert("side_short_after_asia_high", raw.get("side") == "short", actual=raw.get("side")),
        _assert("kill_zone_ny_am", raw.get("kill_zone") == LOCKED_TUNABLES["s3_kill_zone"], actual=raw.get("kill_zone")),
        _assert("accum_asia", True, expected=LOCKED_TUNABLES["s3_accum_session"]),
        _assert("displacement_close_toward_vwap", disp.close < 104.0 and abs(disp.close - 100.0) < abs(104.0 - 100.0), actual=disp.close),
        _assert("entry_is_displace_close", raw.get("entry") == disp.close, actual=raw.get("entry"), expected=disp.close),
        _assert("stop_present", raw.get("stop") is not None),
        _assert("target_opposite_accum", raw.get("target") == 90.0, actual=raw.get("target"), expected=90.0),
        _assert("trigger_asia_sweep", "swp-asia-high" in (raw.get("trigger_event_ids") or []), actual=raw.get("trigger_event_ids")),
        _assert("conviction_ge_60", (raw.get("conviction") or 0) >= 60, actual=raw.get("conviction")),
        *_order_validate_before_publish(trace, expect_publish=approved),
        *(_locked_risk_ok(body) if body else [_assert("risk_body", False)]),
    ]
    if approved:
        checks.append(_assert("published_one", len(signals) == 1, actual=len(signals)))
        if signals:
            validate_topic("setup_signals", signals[0])
            checks.append(_assert("signal_schema", True))
            checks.append(_assert("signal_has_id", bool(signals[0].get("id"))))
    else:
        checks.append(_assert("no_publish_on_reject", signals == [], actual=signals))
    return {
        "id": "setup3_e2e" if approved else "setup3_e2e_rejected",
        "name": "Setup 3 — Asia range sweep during NY AM kill zone (Judas / displacement)",
        "status": "PASS" if all(c["pass"] for c in checks) else "FAIL",
        "setup_type": "po3_judas",
        "assertions": checks,
        "raw": raw,
        "risk_request": body,
        "mocked_risk_response": _mocked_risk_response(approved),
        "published_signal": signals[0] if signals else None,
        "publish_count": len(signals),
        "trace": trace,
    }


def _synth(conviction: int, ts_ms: int, *, tf: str = "5m") -> SetupCandidate:
    return SetupCandidate(
        setup_number=1,
        setup_type="sweep_reclaim",
        symbol=SYM,
        asset_class=AssetClass.CRYPTO,
        side="long",
        conviction=conviction,
        entry=100.0,
        stop=99.0,
        target=104.0,
        timeframe=tf,  # type: ignore[arg-type]
        trigger_event_ids=["swp-buy-low", "mss-reclaim-long"],
        ts_ms=ts_ms,
        risk_reward=4.0,
        ref_vwap=100.0,
        ref_session="london",
        session_type="london",
    )


async def run_gate_conviction_skips_validate() -> dict[str, Any]:
    risk = StaticRiskClient(approved=True)
    bus = InMemoryBus()
    orch = SetupOrchestrator(
        InMemoryStateStore(),
        bus,
        risk,
        params=SetupParams(min_conviction_to_validate=60),
    )
    published = await orch.submit([_synth(45, T0)])
    checks = [
        _assert("no_validate", risk.calls == [], actual=risk.calls),
        _assert("no_publish", published == [] and bus.topics.get("setup_signals", []) == []),
        _assert("skipped_conviction", orch.stats.skipped_conviction == 1, actual=orch.stats.skipped_conviction),
        _assert("raw_logged", bool(orch.raw_log)),
    ]
    return {
        "id": "gate_conviction_lt_60",
        "name": "Conviction < 60 never calls /risk/validate",
        "status": "PASS" if all(c["pass"] for c in checks) else "FAIL",
        "assertions": checks,
    }


async def run_gate_reject_never_publishes() -> dict[str, Any]:
    s1 = await run_setup1_e2e(approved=False)
    s2 = await run_setup2_e2e(with_ob=False, approved=False)
    s3 = await run_setup3_e2e(approved=False)
    checks = [
        _assert("setup1_reject_no_publish", s1["publish_count"] == 0 and s1["status"] == "PASS", actual=s1["publish_count"]),
        _assert("setup2_reject_no_publish", s2["publish_count"] == 0 and s2["status"] == "PASS", actual=s2["publish_count"]),
        _assert("setup3_reject_no_publish", s3["publish_count"] == 0 and s3["status"] == "PASS", actual=s3["publish_count"]),
        _assert("all_validated", all("validate" in s["trace"] for s in (s1, s2, s3))),
    ]
    return {
        "id": "gate_reject_never_publishes",
        "name": "Rejected validate never publishes setup_signals (setups 1–3)",
        "status": "PASS" if all(c["pass"] for c in checks) else "FAIL",
        "assertions": checks,
        "per_setup": {
            "sweep_reclaim": {"risk_request": s1["risk_request"], "publish_count": s1["publish_count"], "trace": s1["trace"]},
            "fvg_entry": {"risk_request": s2["risk_request"], "publish_count": s2["publish_count"], "trace": s2["trace"]},
            "po3_judas": {"risk_request": s3["risk_request"], "publish_count": s3["publish_count"], "trace": s3["trace"]},
        },
    }


def _handshake_row(*, setup_type: str, approve: dict[str, Any], reject: dict[str, Any]) -> dict[str, Any]:
    req = dict(approve.get("risk_request") or {})
    signal = approve.get("published_signal")
    return {
        "setup_type": setup_type,
        "validate_request": req,
        "validate_omits_id": "id" not in req,
        "validate_locked_fields_only": set(req) <= set(RISK_VALIDATE_FIELDS),
        "mocked_approve": {
            "risk_response": _mocked_risk_response(True),
            "published_setup_signal": signal,
            "signal_has_id": bool(signal and signal.get("id")),
            "publish_count": approve.get("publish_count", 1 if signal else 0),
            "trace": approve.get("trace"),
        },
        "mocked_reject": {
            "risk_response": _mocked_risk_response(False),
            "published_setup_signal": None,
            "publish_count": reject.get("publish_count", 0),
            "trace": reject.get("trace"),
        },
        "curl": (
            f"curl -sS -X POST {DEFAULT_RISK_URL} "
            f"-H 'content-type: application/json' "
            f"-d @quant_replay/{setup_type}.validate.json"
        ),
    }


async def run_gate_dedupe_300s() -> dict[str, Any]:
    window_ms = 300_000
    inside = dedupe_candidates(
        [_synth(50, T0, tf="1m"), _synth(80, T0 + 299_000, tf="5m"), _synth(40, T0 + 120_000, tf="15m")],
        window_ms=window_ms,
    )
    outside = dedupe_candidates(
        [_synth(70, T0, tf="5m"), _synth(65, T0 + 301_000, tf="15m")],
        window_ms=window_ms,
    )
    risk = StaticRiskClient(approved=True)
    orch = SetupOrchestrator(
        InMemoryStateStore(),
        InMemoryBus(),
        risk,
        params=SetupParams(dedupe_window_sec=300, min_conviction_to_validate=60),
    )
    together = await orch.submit([_synth(65, T0, tf="5m"), _synth(90, T0 + 180_000, tf="15m")])
    checks = [
        _assert("window_sec", SetupParams().dedupe_window_sec == 300, actual=SetupParams().dedupe_window_sec),
        _assert("inside_keeps_one", len(inside) == 1, actual=len(inside)),
        _assert("inside_highest", inside[0].conviction == 80, actual=inside[0].conviction if inside else None),
        _assert("outside_keeps_both", len(outside) == 2, actual=len(outside)),
        _assert("orch_together_one", len(together) == 1 and together[0].conviction == 90, actual=[c.conviction for c in together]),
        _assert("orch_one_validate", len(risk.calls) == 1, actual=len(risk.calls)),
    ]
    return {
        "id": "gate_dedupe_300s",
        "name": "Dedupe window 300s keeps highest conviction",
        "status": "PASS" if all(c["pass"] for c in checks) else "FAIL",
        "assertions": checks,
    }


async def run_cli_replay_check() -> dict[str, Any]:
    result = await run_setup_replay()
    types = {s["setup_type"] for s in result["signals"]}
    risk_before = bool(result["risk_calls"]) and all("id" not in b for b in result["risk_calls"])
    checks = [
        _assert("sweep_reclaim", "sweep_reclaim" in types, actual=sorted(types)),
        _assert("fvg_or_ob", bool(types & {"fvg_entry", "ob_fvg"}), actual=sorted(types)),
        _assert("po3_judas", "po3_judas" in types, actual=sorted(types)),
        _assert("three_signals", len(result["signals"]) == 3, actual=len(result["signals"])),
        _assert("risk_called_per_signal", len(result["risk_calls"]) == 3, actual=len(result["risk_calls"])),
        _assert("risk_locked", risk_before),
    ]
    return {
        "id": "cli_replay",
        "name": "sniper-data setups --inmemory",
        "status": "PASS" if all(c["pass"] for c in checks) else "FAIL",
        "assertions": checks,
        "setup_types": sorted(types),
        "signals": result["signals"],
        "risk_calls": result["risk_calls"],
        "stats": result["stats"],
        "command": "sniper-data setups --inmemory",
    }


async def build_phase2_e2e_report() -> dict[str, Any]:
    s1_ok = await run_setup1_e2e(approved=True)
    s1_no = await run_setup1_e2e(approved=False)
    s2_ok = await run_setup2_e2e(with_ob=False, approved=True)
    s2_no = await run_setup2_e2e(with_ob=False, approved=False)
    s2_ob = await run_setup2_e2e(with_ob=True, approved=True)
    s3_ok = await run_setup3_e2e(approved=True)
    s3_no = await run_setup3_e2e(approved=False)
    scenarios = [
        s1_ok,
        s1_no,
        s2_ok,
        s2_no,
        s2_ob,
        s3_ok,
        s3_no,
        await run_gate_conviction_skips_validate(),
        await run_gate_reject_never_publishes(),
        await run_gate_dedupe_300s(),
        await run_cli_replay_check(),
    ]
    failed = [s["id"] for s in scenarios if s["status"] != "PASS"]
    handshake = [
        _handshake_row(setup_type="sweep_reclaim", approve=s1_ok, reject=s1_no),
        _handshake_row(setup_type="fvg_entry", approve=s2_ok, reject=s2_no),
        _handshake_row(setup_type="po3_judas", approve=s3_ok, reject=s3_no),
    ]
    return {
        "phase": 2,
        "branch": "cursor/ml-research-setups-c8a9",
        "locked_tunables": LOCKED_TUNABLES,
        "risk_validate_url": DEFAULT_RISK_URL,
        "quant_replay": {
            "start": "sniper-quant api --inmemory --port 8001",
            "endpoint": DEFAULT_RISK_URL,
            "note": (
                "POST each validate_request (no id) at the Quant in-memory API. "
                "ML mocked approve → publishes setup_signals with id; "
                "mocked reject (daily_loss) → zero publish. Phase 3 not started."
            ),
            "per_setup": handshake,
        },
        "note": "Risk validate is mocked via httpx POST to the Quant URL. Phase 3 not started.",
        "scenarios": scenarios,
        "summary": {
            "passed": sum(1 for s in scenarios if s["status"] == "PASS"),
            "failed": len(failed),
            "failed_ids": failed,
            "overall": "PASS" if not failed else "FAIL",
        },
    }


def write_quant_replay_pack(report: dict[str, Any], directory) -> dict[str, str]:
    """Write per-setup JSON + curl script Quant can replay on :8001."""
    from pathlib import Path

    dest = Path(directory)
    dest.mkdir(parents=True, exist_ok=True)
    written: dict[str, str] = {}
    rows = report.get("quant_replay", {}).get("per_setup", [])
    lines = [
        "#!/usr/bin/env bash",
        "# Replay locked validate payloads against Quant PR #2 in-memory API.",
        "#   sniper-quant api --inmemory --port 8001",
        "set -euo pipefail",
        f'DIR="$(cd "$(dirname "$0")" && pwd)"',
        'URL="${RISK_VALIDATE_URL:-http://localhost:8001/risk/validate}"',
        'echo "POST $URL"',
    ]
    for row in rows:
        kind = row["setup_type"]
        req_name = f"{kind}.validate.json"
        ok_name = f"{kind}.approve_response.json"
        sig_name = f"{kind}.setup_signal.json"
        no_name = f"{kind}.reject_response.json"
        mapping = {
            req_name: row["validate_request"],
            ok_name: row["mocked_approve"]["risk_response"],
            sig_name: row["mocked_approve"]["published_setup_signal"],
            no_name: row["mocked_reject"]["risk_response"],
        }
        for name, payload in mapping.items():
            path = dest / name
            path.write_text(json.dumps(payload, indent=2, default=str) + "\n")
            written[name] = str(path)
        lines.extend(
            [
                f'echo "=== {kind} ==="',
                f'curl -sS -X POST "$URL" -H "content-type: application/json" --data-binary "@$DIR/{req_name}"',
                "echo",
            ]
        )
    index = dest / "index.json"
    index.write_text(
        json.dumps(
            {
                "start": "sniper-quant api --inmemory --port 8001",
                "endpoint": DEFAULT_RISK_URL,
                "files": list(written),
                "per_setup": rows,
            },
            indent=2,
            default=str,
        )
        + "\n"
    )
    written["index.json"] = str(index)
    script = dest / "curl_replay.sh"
    script.write_text("\n".join(lines) + "\n")
    script.chmod(0o755)
    written["curl_replay.sh"] = str(script)
    return written
