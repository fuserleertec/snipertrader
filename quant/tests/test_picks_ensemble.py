"""GET /picks/ensemble — dynamic top 10, not a fixed mock list."""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

from sniper_quant.api import create_app
from sniper_quant.picks import (
    DEMO_UNIVERSE,
    REFRESH_SEC,
    categorize_setups,
    demo_unit_score,
    rank_ensemble,
    refresh_bucket,
)
from sniper_quant.models import PickCategory
from sniper_quant.risk.engine import RiskEngine, RiskState
from sniper_quant.store.signals import InMemorySignalStore
from tests.conftest import make_settings
from tests.test_validate import _payload

PICK_FIELDS = {"rank", "symbol", "asset_class", "score", "setup_types", "confidence"}


def _client():
    settings = make_settings()
    engine = RiskEngine(settings=settings, state=RiskState(equity=100_000))
    return TestClient(create_app(settings=settings, signals=InMemorySignalStore(), engine=engine))


def test_empty_book_rotating_top10_not_fixed_mock():
    http = _client()
    spec = http.get("/openapi.json").json()
    assert "/picks/ensemble" in spec["paths"]

    a = http.get("/picks/ensemble", params={"as_of_ts_ms": 0}).json()
    assert a["refresh_sec"] == 900
    assert a["as_of_ts_ms"] == 0
    assert len(a["items"]) == 10
    assert [row["rank"] for row in a["items"]] == list(range(1, 11))
    for row in a["items"]:
        assert PICK_FIELDS <= set(row)
        assert row["notes"]
        assert "demo_universe" in row["notes"]

    assert len(DEMO_UNIVERSE) >= 20
    tops = set()
    for bucket in range(16):
        body = http.get(
            "/picks/ensemble",
            params={"as_of_ts_ms": bucket * REFRESH_SEC * 1000},
        ).json()
        tops.add(tuple(row["symbol"] for row in body["items"]))
    assert len(tops) >= 2

    same_bucket = http.get("/picks/ensemble", params={"as_of_ts_ms": 1}).json()
    assert [row["symbol"] for row in same_bucket["items"]] == [
        row["symbol"] for row in a["items"]
    ]
    assert refresh_bucket(0) == refresh_bucket(1)
    assert demo_unit_score("BTCUSDT", 0) != demo_unit_score("ETHUSDT", 0)


def test_book_signals_outrank_demo_and_are_dynamic():
    http = _client()
    as_of = 1_700_000_400_000
    for i, setup in enumerate(("sweep_reclaim", "fvg_entry", "po3_judas")):
        resp = http.post(
            "/signals",
            json=_payload(
                symbol="BTCUSDT",
                setup_type=setup,
                ts_ms=as_of - (i * 60_000),
                confidence=0.92,
                ref_session="ny_am",
            ),
        )
        assert resp.status_code == 201, resp.text

    weak = http.post(
        "/signals",
        json=_payload(
            symbol="ETHUSDT",
            setup_type="fvg_entry",
            ts_ms=as_of - 3_600_000,
            confidence=0.61,
            asset_class="crypto",
        ),
    )
    assert weak.status_code == 201, weak.text

    body = http.get("/picks/ensemble", params={"as_of_ts_ms": as_of}).json()
    assert body["refresh_sec"] == 900
    assert len(body["items"]) == 10
    assert body["items"][0]["symbol"] == "BTCUSDT"
    assert body["items"][0]["rank"] == 1
    assert body["items"][0]["asset_class"] == "crypto"
    assert set(body["items"][0]["setup_types"]) == {
        "sweep_reclaim",
        "fvg_entry",
        "po3_judas",
    }
    assert body["items"][0]["confidence"] > 0.8
    assert body["items"][0]["ref_session"] == "ny_am"
    assert "book" in (body["items"][0]["notes"] or "")
    assert body["items"][1]["symbol"] == "ETHUSDT"

    empty = rank_ensemble([], as_of_ts_ms=as_of)
    assert empty.items[0].symbol != "BTCUSDT" or "demo_universe" in (empty.items[0].notes or "")


def test_ml_overlay_lifts_symbol_and_rejects_bad_json():
    http = _client()
    as_of = 900_000
    baseline = http.get("/picks/ensemble", params={"as_of_ts_ms": as_of}).json()

    lifted = http.get(
        "/picks/ensemble",
        params={"as_of_ts_ms": as_of, "ml_scores": json.dumps({"AAPL": 1.0})},
    ).json()
    assert lifted["items"][0]["symbol"] == "AAPL"
    assert lifted["items"][0]["score"] > baseline["items"][0]["score"]
    assert "ml=1.000" in (lifted["items"][0]["notes"] or "")

    bad = http.get("/picks/ensemble", params={"ml_scores": "not-json"})
    assert bad.status_code == 422


def test_picks_do_not_enable_live_trading():
    http = _client()
    http.get("/picks/ensemble")
    acct = http.get("/paper/account").json()
    assert acct["live_trading"] is False


CATEGORIZED_FIELDS = {
    "rank",
    "symbol",
    "asset_class",
    "category",
    "score",
    "setup_types",
    "confidence",
}


def test_categorized_picks_shape_filter_and_mapping():
    http = _client()
    spec = http.get("/openapi.json").json()
    assert "/picks/categorized" in spec["paths"]
    params = {p["name"] for p in spec["paths"]["/picks/categorized"]["get"]["parameters"]}
    assert {"asset_class", "limit"} <= params
    schema = spec["components"]["schemas"]["CategorizedPick"]
    assert set(schema["required"]) >= CATEGORIZED_FIELDS
    assert "momentum" in str(spec["components"]["schemas"]["PickCategory"])

    empty = http.get("/picks/categorized", params={"as_of_ts_ms": 0, "limit": 20}).json()
    assert empty["refresh_sec"] == 900
    assert 1 <= len(empty["items"]) <= 20
    assert [row["rank"] for row in empty["items"]] == list(range(1, len(empty["items"]) + 1))
    for row in empty["items"]:
        assert CATEGORIZED_FIELDS <= set(row)
        assert row["category"] == "other"

    equity = http.get(
        "/picks/categorized",
        params={"asset_class": "stocks", "as_of_ts_ms": 0, "limit": 20},
    ).json()
    assert equity["items"]
    assert {row["asset_class"] for row in equity["items"]} == {"equity"}
    named = http.get(
        "/picks/categorized",
        params={"asset_class": "equity", "as_of_ts_ms": 0},
    ).json()
    assert [r["symbol"] for r in named["items"]] == [r["symbol"] for r in equity["items"]]

    futures = http.get(
        "/picks/categorized",
        params={"asset_class": "futures", "as_of_ts_ms": 0, "limit": 20},
    ).json()
    assert futures["items"]
    assert {row["asset_class"] for row in futures["items"]} == {"futures"}
    assert {row["symbol"] for row in futures["items"]} <= {"ES", "NQ", "CL", "GC"}

    as_of = 1_700_000_400_000
    assert (
        http.post(
            "/signals",
            json=_payload(
                symbol="AAPL",
                asset_class="equity",
                setup_type="vwap_pullback_cont",
                ts_ms=as_of,
                confidence=0.91,
            ),
        ).status_code
        == 201
    )
    assert (
        http.post(
            "/signals",
            json=_payload(
                symbol="BTCUSDT",
                setup_type="sd_extension_fade",
                ts_ms=as_of,
                confidence=0.90,
            ),
        ).status_code
        == 201
    )
    assert (
        http.post(
            "/signals",
            json=_payload(
                symbol="ES",
                asset_class="futures",
                setup_type="avwap_ob_confluence",
                ts_ms=as_of,
                confidence=0.86,
            ),
        ).status_code
        == 201
    )

    body = http.get("/picks/categorized", params={"as_of_ts_ms": as_of, "limit": 20}).json()
    by_sym = {row["symbol"]: row for row in body["items"]}
    assert by_sym["AAPL"]["category"] == "momentum"
    assert by_sym["BTCUSDT"]["category"] == "mean_reversion"
    assert by_sym["ES"]["category"] == "confluence"
    assert body["items"][0]["rank"] == 1
    assert len(body["items"]) <= 20

    assert categorize_setups([]) is PickCategory.OTHER
    assert categorize_setups(["vwap_pullback_cont"]) is PickCategory.MOMENTUM
    assert categorize_setups(["sweep_reclaim", "fvg_entry"]) is PickCategory.MEAN_REVERSION
    assert categorize_setups(["vwap_pullback_cont", "sweep_reclaim"]) is PickCategory.CONFLUENCE

    assert http.get("/picks/categorized", params={"asset_class": "fx"}).status_code == 422
    assert http.get("/picks/categorized", params={"limit": 21}).status_code == 422
    assert http.get("/paper/account").json()["live_trading"] is False
