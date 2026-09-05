from __future__ import annotations

from fastapi.testclient import TestClient

from sniper_quant.api import create_app
from sniper_quant.lifecycle import LifecycleMonitor, evaluate_signal_on_bar
from sniper_quant.live import SignalHub
from sniper_quant.models import AssetClass, OHLCVBar, Side, SignalStatus, StoredSignal
from sniper_quant.risk.engine import RiskEngine, RiskState
from sniper_quant.store.signals import InMemorySignalStore
from tests.conftest import make_settings
from tests.test_validate import _payload


def _active(**kwargs) -> StoredSignal:
    payload = dict(
        id="live-1",
        symbol="BTCUSDT",
        asset_class=AssetClass.CRYPTO,
        setup_type="sweep_reclaim",
        side=Side.LONG,
        ts_ms=1_000,
        entry=100.0,
        stop=96.0,
        target=108.0,
        position_size=1.0,
        status=SignalStatus.ACTIVE,
    )
    payload.update(kwargs)
    return StoredSignal.model_validate(payload)


def _bar(*, high: float, low: float, close: float, ts: int = 2_000) -> OHLCVBar:
    return OHLCVBar(
        symbol="BTCUSDT",
        asset_class=AssetClass.CRYPTO,
        timeframe="1m",
        open_ts_ms=ts,
        close_ts_ms=ts + 59_999,
        open=100.0,
        high=high,
        low=low,
        close=close,
        volume=10,
    )


def test_evaluate_tp_and_sl():
    sig = _active()
    tp = evaluate_signal_on_bar(sig, _bar(high=108.5, low=99.5, close=108.2))
    assert tp is not None
    assert tp["status"] is SignalStatus.TP_HIT
    assert tp["outcome"] == "win"
    assert tp["r_multiple"] == 2.0

    sl = evaluate_signal_on_bar(sig, _bar(high=100.2, low=95.0, close=96.0))
    assert sl is not None
    assert sl["status"] is SignalStatus.SL_HIT
    assert sl["outcome"] == "loss"
    assert sl["r_multiple"] == -1.0


def test_same_bar_sl_wins():
    patch = evaluate_signal_on_bar(_active(), _bar(high=120.0, low=80.0, close=110.0))
    assert patch is not None
    assert patch["status"] is SignalStatus.SL_HIT
    assert patch["outcome"] == "loss"


async def test_monitor_updates_store_and_ws_payload():
    store = InMemorySignalStore()
    await store.insert(_active())
    monitor = LifecycleMonitor(store, SignalHub())
    closed = await monitor.apply_bar(_bar(high=109.0, low=99.0, close=108.5))
    assert len(closed) == 1
    row = await store.get("live-1")
    assert row is not None
    assert row.status is SignalStatus.TP_HIT
    assert row.outcome == "win"
    assert row.exit_px == 108.0
    assert row.r_multiple == 2.0
    assert await store.active() == []


def test_lifecycle_bar_endpoint():
    settings = make_settings()
    engine = RiskEngine(settings=settings, state=RiskState(equity=100_000))
    app = create_app(settings=settings, signals=InMemorySignalStore(), engine=engine)
    http = TestClient(app)
    created = http.post("/signals", json=_payload()).json()
    bar = {
        "symbol": "BTCUSDT",
        "asset_class": "crypto",
        "timeframe": "1m",
        "open_ts_ms": 1_700_000_060_000,
        "close_ts_ms": 1_700_000_119_999,
        "open": 100.0,
        "high": 109.0,
        "low": 99.5,
        "close": 108.5,
        "volume": 10,
    }
    resp = http.post("/v1/lifecycle/bar", json=bar)
    assert resp.status_code == 200
    body = resp.json()
    assert body["closed"] == 1
    assert body["signals"][0]["status"] == "TP_HIT"
    assert body["signals"][0]["outcome"] == "win"
    one = http.get(f"/signals/{created['id']}").json()
    assert one["status"] == "TP_HIT"
    assert one["r_multiple"] == 2.0
