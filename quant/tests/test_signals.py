from __future__ import annotations

from sniper_quant.models import AssetClass, Side, SignalStatus, StoredSignal
from sniper_quant.store.signals import InMemorySignalStore


def _sig(i: str, symbol: str = "AAPL", status: SignalStatus = SignalStatus.ACTIVE, ts: int = 100) -> StoredSignal:
    return StoredSignal(
        id=i,
        symbol=symbol,
        asset_class=AssetClass.EQUITY,
        setup_type="sweep_mss",
        side=Side.LONG,
        ts_ms=ts,
        entry=190.0,
        stop=186.0,
        target=198.0,
        position_size=10.0,
        status=status,
    )


async def test_memory_lifecycle_and_filters():
    store = InMemorySignalStore()
    await store.insert(_sig("a", ts=100))
    await store.insert(_sig("b", symbol="MSFT", ts=200))
    await store.insert(_sig("c", ts=300, status=SignalStatus.CANCELLED))

    await store.insert(_sig("d", symbol="NVDA", ts=50))
    store.rows["d"] = store.rows["d"].model_copy(update={"setup_type": "ob_fvg"})
    by_setup = await store.list(setup_type="ob_fvg")
    assert [r.id for r in by_setup] == ["d"]

    listed = await store.list(symbol="AAPL")
    assert {r.id for r in listed} == {"a", "c"}

    active = await store.list(status=SignalStatus.ACTIVE, from_ts=150, to_ts=250)
    assert [r.id for r in active] == ["b"]

    updated = await store.update_status("a", SignalStatus.TP_HIT)
    assert updated is not None
    assert updated.status is SignalStatus.TP_HIT
    assert updated.closed_ts_ms is not None
    assert await store.get("missing") is None
    assert {r.id for r in await store.active()} == {"b", "d"}


async def test_status_transitions():
    store = InMemorySignalStore()
    await store.insert(_sig("x"))
    for st in (SignalStatus.SL_HIT, SignalStatus.CANCELLED):
        store.rows["x"] = _sig("x")
        row = await store.update_status("x", st, closed_ts_ms=9)
        assert row.status is st
        assert row.closed_ts_ms == 9
