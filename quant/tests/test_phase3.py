"""Phase 3: enum lock, S4–6 risk, alerts, paper, history, performance, auth."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from time import perf_counter

from fastapi.testclient import TestClient

from sniper_quant.alerts import CHANNELS, MAX_ALERTS_PER_HOUR
from sniper_quant.api import create_app
from sniper_quant.news import TEST_NEWS_TS_MS
from sniper_quant.risk.engine import RiskEngine, RiskState
from sniper_quant.setups import DORMANT_SETUP_TYPES, PRODUCT_KEYS, SETUP_TYPES
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
    assert listed["walkforward_s4_s6"] == [
        "sd_extension_fade",
        "vwap_pullback_cont",
        "avwap_ob_confluence",
    ]
    assert listed["dedupe_window_sec"] == 300
    assert listed["kz_conviction_bonus"] == 30
    assert listed["s6_anchors"] == [
        "ob",
        "swing_high",
        "swing_low",
        "earnings",
        "news",
    ]
    assert listed["contributing_factors"] == "publish_only"
    assert "mss_break" not in listed["walkforward_s4_s6"]
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
    published = created.json()
    assert published["contributing_factors"] == ["2s_tag", "pin"]
    assert published["factor_breakdown"][0]["name"] == "confluence_count"
    http.patch(
        f"/signals/{created.json()['id']}",
        json={"status": "TP_HIT", "exit_price": 108.0, "realized_r": 2.0, "closed_ts_ms": 99},
    )
    summary = http.get("/performance/summary").json()
    assert list(summary["by_setup"]) == list(PRODUCT_KEYS)
    assert "sd_extension_fade" not in summary["by_setup"]
    assert "mss_break" not in summary["by_setup"]
    assert "4_pending_user_confirm" not in summary["by_setup"]
    assert summary["win_rate"] == 1.0
    assert summary["n_signals"] == 1
    fade = summary["by_setup"]["4_sd_extension_fade"]
    assert fade["setup_type"] == "sd_extension_fade"
    assert fade["product_key"] == "4_sd_extension_fade"
    assert fade["n_signals"] == 1
    assert fade["win_rate"] == 1.0
    assert summary["by_setup"]["3_po3_asia_range_sweep"]["setup_type"] == "po3_judas"
    sweep = summary["by_setup"]["1_liquidity_sweep_vwap_reclaim"]
    assert sweep["setup_type"] == "sweep_reclaim"
    assert sweep["n_signals"] == 0
    assert "sharpe_ratio" in sweep
    assert "max_drawdown_pct" in sweep
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
    assert demo["gate_started_at_utc"]
    assert demo["gate_ends_at_ms"] > demo["gate_started_at_ms"]
    assert demo["win_rate"] == 0.5
    acct = http.get("/paper/account").json()
    assert acct["closed_trades"] == 12
    assert acct["live_trading"] is False
    assert "2-week" in acct["gate"]
    started = http.post("/paper/gate/start").json()
    assert started["live_trading"] is False
    assert started["gate_started_at_utc"]


def test_paper_gate_start_restores_window_from_env(monkeypatch):
    """Host cutover: restore the original 2-week window instead of now+14d."""
    start_ms = 1_757_057_594_000
    end_ms = 1_758_267_194_000
    monkeypatch.setenv("PAPER_GATE_STARTED_AT_MS", str(start_ms))
    monkeypatch.setenv("PAPER_GATE_ENDS_AT_MS", str(end_ms))
    http = _client()
    started = http.post("/paper/gate/start").json()
    assert started["live_trading"] is False
    assert started["gate_started_at_ms"] == start_ms
    assert started["gate_ends_at_ms"] == end_ms
    monkeypatch.delenv("PAPER_GATE_ENDS_AT_MS", raising=False)
    partial = http.post("/paper/gate/start").json()
    assert partial["live_trading"] is False
    assert partial["gate_started_at_ms"] != start_ms
    assert partial["gate_ends_at_ms"] - partial["gate_started_at_ms"] == 14 * 86_400_000
    monkeypatch.delenv("PAPER_GATE_STARTED_AT_MS", raising=False)
    fallback = http.post("/paper/gate/start").json()
    assert fallback["live_trading"] is False
    assert fallback["gate_ends_at_ms"] - fallback["gate_started_at_ms"] == 14 * 86_400_000


def test_paper_mark_signal_hydrates_missing_open_on_close():
    from sniper_quant.models import AssetClass, Side, SignalStatus, StoredSignal
    from sniper_quant.paper import PaperEngine

    book = PaperEngine(starting_equity=100_000.0)
    row = StoredSignal(
        id="missed-open",
        symbol="ES",
        asset_class=AssetClass.FUTURES,
        setup_type="sweep_reclaim",
        side=Side.LONG,
        ts_ms=1_000,
        entry=100.0,
        stop=96.0,
        target=108.0,
        position_size=2.0,
        status=SignalStatus.TP_HIT,
        exit_px=108.0,
        r_multiple=2.0,
        closed_ts_ms=2_000,
    )
    book.mark_signal(row)
    snap = book.snapshot()
    assert snap["live_trading"] is False
    assert snap["open_positions"] == 0
    assert snap["closed_trades"] == 1
    assert snap["closed"][0]["status"] == "TP_HIT"
    assert snap["realized_pnl"] == 16.0


async def test_lifespan_hydrates_paper_then_starts_gate(monkeypatch):
    from fastapi import FastAPI

    from sniper_quant.api import lifespan
    from sniper_quant.models import AssetClass, Side, SignalStatus, StoredSignal
    from sniper_quant.risk.engine import RiskEngine, RiskState
    from sniper_quant.store.ohlcv import InMemoryOHLCVLoader
    from sniper_quant.store.signals import InMemorySignalStore

    settings = make_settings()
    store = InMemorySignalStore()
    await store.insert(
        StoredSignal(
            id="boot-open",
            symbol="NQ",
            asset_class=AssetClass.FUTURES,
            setup_type="fvg_entry",
            side=Side.LONG,
            ts_ms=1_000,
            entry=50.0,
            stop=49.0,
            target=53.0,
            position_size=1.0,
            status=SignalStatus.ACTIVE,
        )
    )
    await store.insert(
        StoredSignal(
            id="boot-closed",
            symbol="ES",
            asset_class=AssetClass.FUTURES,
            setup_type="sweep_reclaim",
            side=Side.LONG,
            ts_ms=1_100,
            entry=100.0,
            stop=96.0,
            target=108.0,
            position_size=1.0,
            status=SignalStatus.SL_HIT,
            exit_px=96.0,
            r_multiple=-1.0,
            closed_ts_ms=2_000,
        )
    )
    ohlcv = InMemoryOHLCVLoader()
    engine = RiskEngine(settings=settings, state=RiskState(equity=100_000))
    monkeypatch.setattr("sniper_quant.api.get_settings", lambda: settings)
    monkeypatch.setattr(
        "sniper_quant.api._build_stores", lambda _settings: (store, ohlcv, engine)
    )
    start_ms = 1_757_057_594_000
    end_ms = 1_758_267_194_000
    monkeypatch.setenv("PAPER_GATE_STARTED_AT_MS", str(start_ms))
    monkeypatch.setenv("PAPER_GATE_ENDS_AT_MS", str(end_ms))
    app = FastAPI()
    async with lifespan(app):
        snap = app.state.paper.snapshot()
        assert snap["live_trading"] is False
        assert snap["open_positions"] == 1
        assert snap["closed_trades"] == 1
        assert snap["positions"][0]["signal_id"] == "boot-open"
        assert snap["closed"][0]["signal_id"] == "boot-closed"
        assert snap["gate_started_at_ms"] == start_ms
        assert snap["gate_ends_at_ms"] == end_ms


def test_paper_load_snapshot_round_trip_and_bundle(monkeypatch):
    from sniper_quant.paper import PaperEngine, PaperPosition

    book = PaperEngine(starting_equity=100_000.0)
    book.cash = 94_019.24
    book.gate_started_at_ms = 1_757_057_594_000
    book.gate_ends_at_ms = 1_758_267_194_000
    book.closed.append(
        PaperPosition(
            signal_id="nq-1",
            symbol="NQ",
            setup_type="po3_judas",
            side="long",
            size=1.0,
            entry=20_000.0,
            stop=19_900.0,
            target=20_200.0,
            opened_ts_ms=1_000,
            status="TP_HIT",
            exit_price=20_200.0,
            realized_pnl=200.0,
            realized_r=2.0,
            closed_ts_ms=2_000,
        )
    )
    book.positions["es-open"] = PaperPosition(
        signal_id="es-open",
        symbol="ES",
        setup_type="sweep_reclaim",
        side="long",
        size=2.0,
        entry=5_000.0,
        stop=4_980.0,
        target=5_040.0,
        opened_ts_ms=3_000,
    )
    raw = book.snapshot()
    assert raw["live_trading"] is False
    restored = PaperEngine()
    restored.load_snapshot(raw)
    snap = restored.snapshot()
    assert snap["live_trading"] is False
    assert snap["cash"] == raw["cash"]
    assert snap["starting_equity"] == raw["starting_equity"]
    assert snap["closed_trades"] == 1
    assert snap["open_positions"] == 1
    assert snap["equity"] == raw["equity"]
    assert snap["gate_started_at_ms"] == 1_757_057_594_000
    assert snap["gate_ends_at_ms"] == 1_758_267_194_000
    assert snap["closed"][0]["signal_id"] == "nq-1"
    assert snap["positions"][0]["signal_id"] == "es-open"

    monkeypatch.setenv("PAPER_GATE_STARTED_AT_MS", "111")
    monkeypatch.setenv("PAPER_GATE_ENDS_AT_MS", "222")
    env_wins = PaperEngine()
    env_wins.load_snapshot(raw)
    env_wins.start_gate(keep_existing=True)
    env_snap = env_wins.snapshot()
    assert env_snap["live_trading"] is False
    assert env_snap["gate_started_at_ms"] == 111
    assert env_snap["gate_ends_at_ms"] == 222
    monkeypatch.delenv("PAPER_GATE_STARTED_AT_MS")
    monkeypatch.delenv("PAPER_GATE_ENDS_AT_MS")

    bundled = PaperEngine()
    bundled.load_snapshot({"meta": {"written_at": "2026-09-09"}, "account": raw})
    assert bundled.snapshot()["closed_trades"] == 1
    assert bundled.snapshot()["live_trading"] is False


def test_paper_load_snapshot_path_meta_account(tmp_path):
    """Shared-box API: load_snapshot(path) on {meta, account} JSON."""
    import json

    from sniper_quant.paper import PaperEngine

    closed = []
    for i in range(121):
        closed.append(
            {
                "signal_id": f"c-{i}",
                "symbol": "ES",
                "setup_type": "sweep_reclaim",
                "side": "long",
                "size": 1.0,
                "entry": 5000.0,
                "stop": 4990.0,
                "target": 5020.0,
                "opened_ts_ms": i,
                "status": "TP_HIT",
                "exit_price": 5020.0,
                "realized_pnl": 31390.0 if i == 0 else 0.0,
                "realized_r": 2.0 if i == 0 else 0.0,
                "closed_ts_ms": i + 1,
            }
        )
    payload = {
        "meta": {"written_at": "2026-09-09T00:00:00Z"},
        "account": {
            "starting_equity": 100_000.0,
            "cash": 103_070.0,
            "equity": 103_070.0,
            "realized_pnl": 31_390.0,
            "positions": [],
            "closed": closed,
            "live_trading": False,
        },
    }
    path = tmp_path / "LATEST.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    book = PaperEngine()
    book.load_snapshot(path)
    snap = book.snapshot()
    assert snap["live_trading"] is False
    assert snap["closed_trades"] == 121
    assert snap["equity"] == 103_070.0
    assert snap["realized_pnl"] == 31_390.0


def test_paper_load_snapshot_refuses_live_trading(tmp_path):
    import json

    import pytest

    from sniper_quant.paper import LiveTradingSnapshotError, PaperEngine

    live = {"starting_equity": 100_000.0, "cash": 100_000.0, "live_trading": True}
    with pytest.raises(LiveTradingSnapshotError):
        PaperEngine().load_snapshot(live)
    with pytest.raises(LiveTradingSnapshotError):
        PaperEngine().load_snapshot({"meta": {}, "account": live})
    path = tmp_path / "LIVE.json"
    path.write_text(
        json.dumps({"meta": {"live_trading": True}, "account": {"cash": 1.0}}),
        encoding="utf-8",
    )
    with pytest.raises(LiveTradingSnapshotError):
        PaperEngine().load_snapshot(path)


async def test_lifespan_prefers_paper_snapshot_file(tmp_path, monkeypatch):
    import json

    from fastapi import FastAPI

    from sniper_quant.api import lifespan
    from sniper_quant.paper import PaperEngine, PaperPosition
    from sniper_quant.risk.engine import RiskEngine, RiskState
    from sniper_quant.store.ohlcv import InMemoryOHLCVLoader
    from sniper_quant.store.signals import InMemorySignalStore

    seed = PaperEngine(starting_equity=100_000.0)
    seed.cash = 97_015.04
    seed.gate_started_at_ms = 1_700_000_000_000
    seed.gate_ends_at_ms = 1_701_000_000_000
    seed.closed.append(
        PaperPosition(
            signal_id="from-file",
            symbol="CL",
            setup_type="fvg_entry",
            side="long",
            size=1.0,
            entry=80.0,
            stop=79.0,
            target=83.0,
            opened_ts_ms=10,
            status="SL_HIT",
            exit_price=79.0,
            realized_pnl=-1.0,
            realized_r=-1.0,
            closed_ts_ms=20,
        )
    )
    path = tmp_path / "LATEST.json"
    path.write_text(json.dumps({"meta": {}, "account": seed.snapshot()}), encoding="utf-8")
    settings = make_settings(PAPER_SNAPSHOT_PATH=str(path))
    store = InMemorySignalStore()
    ohlcv = InMemoryOHLCVLoader()
    engine = RiskEngine(settings=settings, state=RiskState(equity=100_000))
    monkeypatch.setattr("sniper_quant.api.get_settings", lambda: settings)
    monkeypatch.setattr(
        "sniper_quant.api._build_stores", lambda _settings: (store, ohlcv, engine)
    )
    monkeypatch.setenv("PAPER_GATE_STARTED_AT_MS", "1757057594000")
    monkeypatch.setenv("PAPER_GATE_ENDS_AT_MS", "1758267194000")
    app = FastAPI()
    async with lifespan(app):
        snap = app.state.paper.snapshot()
        assert snap["live_trading"] is False
        assert snap["closed_trades"] == 1
        assert snap["closed"][0]["signal_id"] == "from-file"
        assert snap["cash"] == 97_015.04
        assert snap["gate_started_at_ms"] == 1_757_057_594_000
        assert snap["gate_ends_at_ms"] == 1_758_267_194_000


async def test_lifespan_snapshot_missing_falls_back_to_signals(tmp_path, monkeypatch):
    from fastapi import FastAPI

    from sniper_quant.api import lifespan
    from sniper_quant.models import AssetClass, Side, SignalStatus, StoredSignal
    from sniper_quant.risk.engine import RiskEngine, RiskState
    from sniper_quant.store.ohlcv import InMemoryOHLCVLoader
    from sniper_quant.store.signals import InMemorySignalStore

    missing = tmp_path / "nope.json"
    settings = make_settings(PAPER_SNAPSHOT_PATH=str(missing))
    store = InMemorySignalStore()
    await store.insert(
        StoredSignal(
            id="sig-fallback",
            symbol="GC",
            asset_class=AssetClass.FUTURES,
            setup_type="sweep_reclaim",
            side=Side.LONG,
            ts_ms=1_000,
            entry=10.0,
            stop=9.0,
            target=13.0,
            position_size=1.0,
            status=SignalStatus.ACTIVE,
        )
    )
    ohlcv = InMemoryOHLCVLoader()
    engine = RiskEngine(settings=settings, state=RiskState(equity=100_000))
    monkeypatch.setattr("sniper_quant.api.get_settings", lambda: settings)
    monkeypatch.setattr(
        "sniper_quant.api._build_stores", lambda _settings: (store, ohlcv, engine)
    )
    app = FastAPI()
    async with lifespan(app):
        snap = app.state.paper.snapshot()
        assert snap["live_trading"] is False
        assert snap["open_positions"] == 1
        assert snap["positions"][0]["signal_id"] == "sig-fallback"


async def test_lifespan_corrupt_snapshot_falls_back_to_signals(tmp_path, monkeypatch):
    from fastapi import FastAPI

    from sniper_quant.api import lifespan
    from sniper_quant.models import AssetClass, Side, SignalStatus, StoredSignal
    from sniper_quant.risk.engine import RiskEngine, RiskState
    from sniper_quant.store.ohlcv import InMemoryOHLCVLoader
    from sniper_quant.store.signals import InMemorySignalStore

    bad = tmp_path / "LATEST.json"
    bad.write_text("{not-json", encoding="utf-8")
    settings = make_settings(PAPER_SNAPSHOT_PATH=str(bad))
    store = InMemorySignalStore()
    await store.insert(
        StoredSignal(
            id="after-corrupt",
            symbol="ES",
            asset_class=AssetClass.FUTURES,
            setup_type="sweep_reclaim",
            side=Side.LONG,
            ts_ms=1_000,
            entry=10.0,
            stop=9.0,
            target=13.0,
            position_size=1.0,
            status=SignalStatus.ACTIVE,
        )
    )
    ohlcv = InMemoryOHLCVLoader()
    engine = RiskEngine(settings=settings, state=RiskState(equity=100_000))
    monkeypatch.setattr("sniper_quant.api.get_settings", lambda: settings)
    monkeypatch.setattr(
        "sniper_quant.api._build_stores", lambda _settings: (store, ohlcv, engine)
    )
    app = FastAPI()
    async with lifespan(app):
        snap = app.state.paper.snapshot()
        assert snap["live_trading"] is False
        assert snap["open_positions"] == 1
        assert snap["positions"][0]["signal_id"] == "after-corrupt"


async def test_lifespan_live_trading_snapshot_falls_back_to_signals(tmp_path, monkeypatch):
    import json

    from fastapi import FastAPI

    from sniper_quant.api import lifespan
    from sniper_quant.models import AssetClass, Side, SignalStatus, StoredSignal
    from sniper_quant.risk.engine import RiskEngine, RiskState
    from sniper_quant.store.ohlcv import InMemoryOHLCVLoader
    from sniper_quant.store.signals import InMemorySignalStore

    live = tmp_path / "LATEST.json"
    live.write_text(
        json.dumps(
            {
                "meta": {},
                "account": {
                    "starting_equity": 100_000.0,
                    "cash": 103_070.0,
                    "closed": [],
                    "positions": [],
                    "live_trading": True,
                },
            }
        ),
        encoding="utf-8",
    )
    settings = make_settings(PAPER_SNAPSHOT_PATH=str(live))
    store = InMemorySignalStore()
    await store.insert(
        StoredSignal(
            id="after-live-refuse",
            symbol="NQ",
            asset_class=AssetClass.FUTURES,
            setup_type="po3_judas",
            side=Side.LONG,
            ts_ms=1_000,
            entry=20_000.0,
            stop=19_900.0,
            target=20_200.0,
            position_size=1.0,
            status=SignalStatus.ACTIVE,
        )
    )
    ohlcv = InMemoryOHLCVLoader()
    engine = RiskEngine(settings=settings, state=RiskState(equity=100_000))
    monkeypatch.setattr("sniper_quant.api.get_settings", lambda: settings)
    monkeypatch.setattr(
        "sniper_quant.api._build_stores", lambda _settings: (store, ohlcv, engine)
    )
    app = FastAPI()
    async with lifespan(app):
        snap = app.state.paper.snapshot()
        assert snap["live_trading"] is False
        assert snap["open_positions"] == 1
        assert snap["positions"][0]["signal_id"] == "after-live-refuse"
        assert snap["closed_trades"] == 0


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
