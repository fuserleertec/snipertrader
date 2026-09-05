"""Phase 3: enum lock, S4–6 risk, alerts, paper, history, performance, auth."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from time import perf_counter

from fastapi.testclient import TestClient

from sniper_quant.alerts import CHANNELS, MAX_ALERTS_PER_HOUR
from sniper_quant.api import create_app
from sniper_quant.news import TEST_NEWS_TS_MS
from sniper_quant.risk.engine import RiskEngine, RiskState
from sniper_quant.setups import DORMANT_SETUP_TYPES, PERFORMANCE_SETUP_TYPES, PRODUCT_KEYS, SETUP_TYPES
from sniper_quant.store.signals import InMemorySignalStore
from tests.conftest import make_settings
from tests.test_validate import _payload


def _client(settings=None):
    settings = settings or make_settings()
    engine = RiskEngine(settings=settings, state=RiskState(equity=100_000))
    app = create_app(settings=settings, signals=InMemorySignalStore(), engine=engine)
    return TestClient(app)


def test_enum_is_six_live_types_only():
    assert SETUP_TYPES == (
        "sweep_reclaim",
        "fvg_entry",
        "po3_judas",
        "sd_extension_fade",
        "vwap_pullback_cont",
        "avwap_ob_confluence",
    )
    assert "mss_break" in DORMANT_SETUP_TYPES
    http = _client()
    listed = http.get("/v1/setups").json()
    assert listed["setup_types"] == list(SETUP_TYPES)
    assert listed["product_keys"] == list(PRODUCT_KEYS)
    for dead in DORMANT_SETUP_TYPES:
        assert http.post("/risk/validate", json=_payload(setup_type=dead)).status_code == 422


def test_validate_rejects_publish_only_factor_fields():
    http = _client()
    body = _payload(
        contributing_factors=["vwap"],
        factor_breakdown=[{"name": "confluence", "weight": 40, "score": 40}],
    )
    assert http.post("/risk/validate", json=body).status_code == 422


def test_s4_s5_s6_approve_and_reject():
    http = _client()
    s4 = _payload(setup_type="sd_extension_fade", confidence=0.72)
    assert http.post("/risk/validate", json=s4).json()["approved"] is True

    news = _payload(setup_type="sd_extension_fade", ts_ms=TEST_NEWS_TS_MS, confidence=0.9)
    news_r = http.post("/risk/validate", json=news).json()
    assert news_r["approved"] is False
    assert news_r["reason"] == "news_window"

    s5 = _payload(setup_type="vwap_pullback_cont", confidence=0.7)
    assert http.post("/risk/validate", json=s5).json()["approved"] is True
    s5_low = _payload(setup_type="vwap_pullback_cont", stop=96.0, target=106.0, confidence=0.8)
    s5_r = http.post("/risk/validate", json=s5_low).json()
    assert s5_r["approved"] is False
    assert s5_r["reason"] == "invalid_levels"
    assert s5_r["checks"]["min_rr"] == 2.0

    s6 = _payload(setup_type="avwap_ob_confluence", confidence=0.75)
    assert http.post("/risk/validate", json=s6).json()["approved"] is True
    low = _payload(setup_type="avwap_ob_confluence", confidence=0.65)
    low_r = http.post("/risk/validate", json=low).json()
    assert low_r["approved"] is False
    assert low_r["reason"] == "low_conviction"

    # Mandatory validate-before-publish: reject is 409, no row.
    pub = http.post("/signals", json=low)
    assert pub.status_code == 409
    assert http.get("/signals").json()["items"] == []


def test_publish_factors_and_performance_product_keys():
    http = _client()
    created = http.post(
        "/signals",
        json=_payload(
            setup_type="sd_extension_fade",
            contributing_factors=["2s_tag", "pin"],
            factor_breakdown=[
                {"name": "confluence_count", "weight": 40, "score": 40},
                {"name": "volume_confirm", "weight": 30, "score": 30},
            ],
            confidence=0.8,
        ),
    )
    assert created.status_code == 201
    http.patch(
        f"/signals/{created.json()['id']}",
        json={"status": "TP_HIT", "exit_price": 108.0, "realized_r": 2.0, "closed_ts_ms": 99},
    )
    summary = http.get("/performance/summary").json()
    assert set(PERFORMANCE_SETUP_TYPES) <= set(summary["by_setup"])
    bucket = summary["by_setup"]["sd_extension_fade"]
    assert bucket["setup_type"] == "sd_extension_fade"
    assert bucket["product_key"] == "4_sd_extension_fade"
    assert bucket["n_signals"] == 1
    assert "sharpe_ratio" in bucket
    assert "max_drawdown_pct" in bucket
    hist = http.get("/signals/history", params={"setup_type": "sd_extension_fade"}).json()
    assert len(hist["items"]) == 1


def test_alerts_four_channels_and_throttle():
    http = _client()
    for ch, target in (
        ("telegram", "@desk"),
        ("discord", "https://discord.example/hook"),
        ("email", "pm@snipertrader.ai"),
        ("webhook", "https://hooks.example/quant"),
    ):
        assert http.post(
            "/alerts/subscribe",
            json={"user_id": "pm", "channel": ch, "target": target},
        ).status_code == 200
    assert set(CHANNELS) == {"telegram", "discord", "email", "webhook"}

    for i in range(MAX_ALERTS_PER_HOUR + 2):
        http.post(
            "/signals",
            json=_payload(symbol=f"T{i}USDT", ts_ms=2_000 + i, confidence=0.91),
        )
    dump = http.get("/alerts").json()
    assert dump["max_per_hour"] == 5
    # 4 channels × 7 publishes = 28 attempts; first 5/user/hour send, rest throttle.
    assert dump["sent"] == MAX_ALERTS_PER_HOUR
    assert dump["throttled"] == 4 * (MAX_ALERTS_PER_HOUR + 2) - MAX_ALERTS_PER_HOUR
    assert {row["channel"] for row in dump["log"] if not row["throttled"]} <= set(CHANNELS)


def test_paper_fortnight_and_account():
    http = _client()
    reset = http.post("/paper/reset").json()
    assert reset["live_trading"] is False
    demo = http.post("/paper/demo-fortnight").json()
    assert demo["days_simulated"] == 14
    assert demo["closed_trades"] == 12
    assert demo["live_trading"] is False
    acct = http.get("/paper/account").json()
    assert acct["closed_trades"] == 12
    assert "2-week" in acct["gate"]


def test_api_key_auth_default_off_and_on():
    open_http = _client()
    assert open_http.get("/v1/setups").status_code == 200
    locked = _client(make_settings(SNIPER_API_KEY="secret-gate"))
    assert locked.get("/v1/setups").status_code == 401
    assert locked.get("/v1/setups", headers={"X-API-Key": "secret-gate"}).status_code == 200
    assert locked.get("/health").status_code == 200


def test_load_100_concurrent_get_signals_p95():
    """In-process TestClient, 100 concurrent GET /signals (no 100 real sockets)."""
    http = _client()
    for i in range(20):
        http.post("/signals", json=_payload(symbol=f"L{i}USDT", ts_ms=10_000 + i, confidence=0.85))

    latencies: list[float] = []

    def one(_i: int) -> float:
        t0 = perf_counter()
        resp = http.get("/signals", params={"limit": 20})
        elapsed = (perf_counter() - t0) * 1000.0
        assert resp.status_code == 200
        assert "items" in resp.json()
        return elapsed

    with ThreadPoolExecutor(max_workers=100) as pool:
        futs = [pool.submit(one, i) for i in range(100)]
        for fut in as_completed(futs):
            latencies.append(fut.result())
    latencies.sort()
    p95 = latencies[int(0.95 * (len(latencies) - 1))]
    # Recorded for the PM evidence file; in-process should be well under 200ms.
    assert p95 < 200.0, f"p95 {p95:.2f}ms exceeded 200ms"
    assert len(latencies) == 100
