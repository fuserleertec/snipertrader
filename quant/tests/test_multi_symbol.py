"""Multi-symbol paper book (~20 symbols): ingest, list, history, performance, cursors."""

from __future__ import annotations

from fastapi.testclient import TestClient

from sniper_quant.api import create_app
from sniper_quant.picks import DEMO_UNIVERSE
from sniper_quant.risk.engine import RiskEngine, RiskState
from sniper_quant.setups import PRODUCT_KEYS, SETUP_TYPES
from sniper_quant.store.signals import InMemorySignalStore
from tests.conftest import make_settings
from tests.test_validate import _payload

UNIVERSE = DEMO_UNIVERSE[:20]
assert len(UNIVERSE) == 20


def _client():
    settings = make_settings()
    engine = RiskEngine(settings=settings, state=RiskState(equity=250_000))
    return TestClient(create_app(settings=settings, signals=InMemorySignalStore(), engine=engine))


def _seed(http: TestClient, *, copies: int = 2, via: str = "signals") -> list[dict]:
    created: list[dict] = []
    for i, (symbol, asset) in enumerate(UNIVERSE):
        for j in range(copies):
            setup = SETUP_TYPES[(i + j) % len(SETUP_TYPES)]
            body = _payload(
                symbol=symbol,
                asset_class=asset.value,
                setup_type=setup,
                ts_ms=1_700_000_000_000 + i * 10_000 + j * 100,
                confidence=0.88,
                ref_session="ny_am",
            )
            if via == "ingest":
                body["id"] = f"ing-{symbol}-{j}"
                body["status"] = "ACTIVE"
                body["position_size"] = 1.0
                resp = http.post("/v1/signals/ingest", json=body)
                assert resp.status_code == 200, resp.text
            else:
                resp = http.post("/signals", json=body)
                assert resp.status_code == 201, resp.text
            created.append(resp.json())
    return created


def _walk_pages(http: TestClient, path: str, *, limit: int, **params) -> list[dict]:
    items: list[dict] = []
    cursor = None
    pages = 0
    while True:
        q = {"limit": limit, **params}
        if cursor:
            q["cursor"] = cursor
        body = http.get(path, params=q).json()
        page = body["items"]
        items.extend(page)
        pages += 1
        cursor = body.get("next_cursor")
        if not cursor:
            break
        assert page, "cursor set on an empty page"
        assert pages < 50
    return items


def test_ingest_and_list_twenty_symbols():
    http = _client()
    created = _seed(http, copies=1, via="ingest")
    assert len(created) == 20
    assert len({row["symbol"] for row in created}) == 20

    listed = http.get("/signals", params={"limit": 500}).json()
    assert listed["next_cursor"] is None
    assert len(listed["items"]) == 20
    hist = http.get("/signals/history", params={"limit": 500}).json()
    assert [r["id"] for r in listed["items"]] == [r["id"] for r in hist["items"]]

    target = UNIVERSE[3][0]
    filtered = http.get("/signals", params={"symbol": target.lower()}).json()["items"]
    assert len(filtered) == 1
    assert filtered[0]["symbol"] == target

    by_setup = http.get("/signals", params={"setup_type": "fvg_entry", "limit": 100}).json()
    assert by_setup["items"]
    assert {r["setup_type"] for r in by_setup["items"]} == {"fvg_entry"}
    assert len({r["symbol"] for r in by_setup["items"]}) >= 2

    acct = http.get("/paper/account").json()
    assert acct["live_trading"] is False


def test_multi_symbol_cursor_pagination():
    http = _client()
    created = _seed(http, copies=2, via="signals")
    assert len(created) == 40

    walked = _walk_pages(http, "/signals", limit=7)
    ids = [row["id"] for row in walked]
    assert len(ids) == 40
    assert len(set(ids)) == 40
    assert {row["symbol"] for row in walked} == {sym for sym, _ in UNIVERSE}

    hist = _walk_pages(http, "/signals/history", limit=7)
    assert [row["id"] for row in hist] == ids

    target = UNIVERSE[0][0]
    one = _walk_pages(http, "/signals", limit=1, symbol=target)
    assert len(one) == 2
    assert {row["symbol"] for row in one} == {target}
    assert one[0]["ts_ms"] >= one[1]["ts_ms"]


def test_multi_symbol_performance_by_setup():
    http = _client()
    created = _seed(http, copies=1, via="ingest")
    # Close a spread of symbols so several product keys have n_closed.
    for row in created[::3]:
        patched = http.patch(
            f"/signals/{row['id']}",
            json={
                "status": "TP_HIT",
                "exit_price": 108.0,
                "realized_r": 2.0,
                "closed_ts_ms": row["ts_ms"] + 60_000,
            },
        )
        assert patched.status_code == 200, patched.text

    overall = http.get("/performance/summary").json()
    assert overall["n_signals"] == 20
    assert overall["n_closed"] >= 6
    assert list(overall["by_setup"]) == list(PRODUCT_KEYS)
    populated = [
        key
        for key, bucket in overall["by_setup"].items()
        if bucket["n_signals"] > 0
    ]
    assert len(populated) == 6
    closed_keys = [
        key for key, bucket in overall["by_setup"].items() if bucket["n_closed"] > 0
    ]
    assert len(closed_keys) >= 2
    for key, bucket in overall["by_setup"].items():
        assert bucket["product_key"] == key
        assert bucket["setup_type"] in SETUP_TYPES

    target = UNIVERSE[1][0]
    one = http.get("/performance/summary", params={"symbol": target}).json()
    assert one["n_signals"] == 1
    assert list(one["by_setup"]) == list(PRODUCT_KEYS)
    assert sum(b["n_signals"] for b in one["by_setup"].values()) == 1

    assert http.get("/paper/account").json()["live_trading"] is False
