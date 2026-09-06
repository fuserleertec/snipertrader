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
from sniper_quant.universe import load_paper_universe
from tests.conftest import make_settings
from tests.test_validate import _payload

PICK_FIELDS = {"rank", "symbol", "asset_class", "score", "setup_types", "confidence"}
REQUIRED_FUTURES = {"ES", "CL", "GC", "NQ"}
OUTSIDER = "IBM"


def _paper_symbols() -> set[str]:
    return {sym for sym, _ in load_paper_universe(make_settings())}


def _client(**overrides):
    settings = make_settings(**overrides)
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


def test_ensemble_score_then_confidence_sort():
    http = _client()
    as_of = 1_700_000_400_000
    low = _payload(
        symbol="BTCUSDT",
        setup_type="sweep_reclaim",
        ts_ms=as_of,
        confidence=0.99,
        ensemble_score=40,
    )
    high = _payload(
        symbol="ETHUSDT",
        setup_type="fvg_entry",
        ts_ms=as_of,
        confidence=0.61,
        ensemble_score=91,
    )
    assert http.post("/risk/validate", json=low).status_code == 422
    assert http.post("/signals", json=low).status_code == 201
    assert http.post("/signals", json=high).status_code == 201
    body = http.get("/picks/ensemble", params={"as_of_ts_ms": as_of}).json()
    assert body["items"][0]["symbol"] == "ETHUSDT"
    assert body["items"][0]["score"] == 91
    assert body["items"][1]["symbol"] == "BTCUSDT"

    a = _payload(
        symbol="SOLUSDT",
        setup_type="po3_judas",
        ts_ms=as_of + 1,
        confidence=0.70,
        ensemble_score=80,
    )
    b = _payload(
        symbol="AAPL",
        asset_class="equity",
        setup_type="vwap_pullback_cont",
        ts_ms=as_of + 2,
        confidence=0.95,
        ensemble_score=80,
    )
    assert http.post("/signals", json=a).status_code == 201
    assert http.post("/signals", json=b).status_code == 201
    tied = http.get("/picks/ensemble", params={"as_of_ts_ms": as_of + 2}).json()
    order = [row["symbol"] for row in tied["items"]]
    assert order.index("AAPL") < order.index("SOLUSDT")
    by_sym = {row["symbol"]: row for row in tied["items"]}
    assert by_sym["AAPL"]["score"] == by_sym["SOLUSDT"]["score"] == 80
    assert by_sym["AAPL"]["confidence"] > by_sym["SOLUSDT"]["confidence"]


def test_ensemble_ranks_paper_file_including_futures():
    http = _client()
    dump = http.get("/paper/universe").json()
    paper = _paper_symbols()
    assert dump["live_trading"] is False
    assert dump["handoff"] == "provisional"
    assert dump["ranking_source"] == "paper_universe"
    ranked = {r["symbol"] for r in dump["ranking_universe"]}
    assert ranked == paper
    assert REQUIRED_FUTURES <= ranked
    assert OUTSIDER not in ranked

    empty = http.get("/picks/ensemble", params={"as_of_ts_ms": 0}).json()
    assert {row["symbol"] for row in empty["items"]} <= paper
    assert len(empty["items"]) == 10
    empty_classes = {row["asset_class"] for row in empty["items"]}
    assert empty_classes <= {"crypto", "equity", "futures"}

    as_of = 1_700_000_400_000
    outsider = http.post(
        "/signals",
        json=_payload(
            symbol=OUTSIDER,
            asset_class="equity",
            setup_type="avwap_ob_confluence",
            ts_ms=as_of,
            confidence=0.99,
            ensemble_score=100,
        ),
    )
    assert outsider.status_code == 201
    inside = http.post(
        "/signals",
        json=_payload(
            symbol="CL",
            asset_class="futures",
            setup_type="vwap_pullback_cont",
            ts_ms=as_of,
            confidence=0.70,
            ensemble_score=10,
        ),
    )
    assert inside.status_code == 201
    body = http.get("/picks/ensemble", params={"as_of_ts_ms": as_of}).json()
    symbols = {row["symbol"] for row in body["items"]}
    assert OUTSIDER not in symbols
    assert symbols <= paper
    assert body["items"][0]["symbol"] == "CL"
    assert body["items"][0]["asset_class"] == "futures"

    de = _client(DE_UNIVERSE="ETHUSDT,MSFT")
    de_dump = de.get("/paper/universe").json()
    assert de_dump["handoff"] == "de_feed"
    assert {r["symbol"] for r in de_dump["ranking_universe"]} == {"ETHUSDT", "MSFT"}
    ranked_de = de.get("/picks/ensemble", params={"as_of_ts_ms": 0}).json()
    assert {row["symbol"] for row in ranked_de["items"]} == {"ETHUSDT", "MSFT"}


def test_rank_components_synthesize_and_universe_intersection():
    http = _client()
    as_of = 1_700_000_400_000
    body = _payload(
        symbol="NVDA",
        asset_class="equity",
        setup_type="avwap_ob_confluence",
        ts_ms=as_of,
        confidence=0.80,
        rank_components={
            "setup_quality": 0.9,
            "risk_adjusted": 0.7,
            "kill_zone": 1.0,
            "volume": 0.4,
            "freshness": 0.5,
        },
    )
    assert http.post("/risk/validate", json=body).status_code == 422
    assert http.post("/signals", json=body).status_code == 201
    picks = http.get("/picks/ensemble", params={"as_of_ts_ms": as_of}).json()
    nvda = next(r for r in picks["items"] if r["symbol"] == "NVDA")
    assert abs(nvda["score"] - 70.0) < 0.01
    assert "rank_components" in (nvda["notes"] or "")

    uni = http.get("/paper/universe").json()
    assert uni["live_trading"] is False
    assert uni["n_paper"] >= 20
    classes = {row["asset_class"] for row in uni["paper_universe"]}
    assert classes == {"crypto", "equity", "futures"}
    assert uni["setup_universe"] is None

    settings = make_settings(SETUP_UNIVERSE="BTCUSDT,AAPL")
    engine = RiskEngine(settings=settings, state=RiskState(equity=100_000))
    narrow = TestClient(create_app(settings=settings, signals=InMemorySignalStore(), engine=engine))
    dump = narrow.get("/paper/universe").json()
    assert dump["intersection"] is True
    assert {r["symbol"] for r in dump["ranking_universe"]} == {"BTCUSDT", "AAPL"}
    ranked = narrow.get("/picks/ensemble", params={"as_of_ts_ms": 0}).json()
    assert {r["symbol"] for r in ranked["items"]} <= {"BTCUSDT", "AAPL"}
    assert len(ranked["items"]) == 2


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


def test_openapi_documents_picks_and_asset_class():
    """Confirm OpenAPI publishes ensemble + categorized + signals filters."""
    http = _client()
    spec = http.get("/openapi.json").json()
    paths = spec["paths"]
    schemas = spec["components"]["schemas"]

    ens = paths["/picks/ensemble"]["get"]
    ens_params = {p["name"] for p in ens["parameters"]}
    assert {"as_of_ts_ms", "ml_scores"} <= ens_params
    assert "200" in ens["responses"]
    pick = schemas["EnsemblePick"]
    assert {"rank", "symbol", "asset_class", "score", "confidence"} <= set(pick["required"])
    assert "setup_types" in pick["properties"]
    assert "rank_components" in pick["properties"]
    assert "contributing_factors" in pick["properties"]
    assert "confluence_count" in pick["properties"]
    assert "EnsemblePicksResponse" in schemas
    assert "ensemble_features" in spec["info"]["description"]

    cat = paths["/picks/categorized"]["get"]
    cat_params = {p["name"] for p in cat["parameters"]}
    assert {"asset_class", "limit", "as_of_ts_ms"} <= cat_params
    categorized = schemas["CategorizedPick"]
    assert set(categorized["required"]) >= CATEGORIZED_FIELDS
    assert "momentum" in str(schemas["PickCategory"])
    assert "CategorizedPicksResponse" in schemas

    sig_params = {p["name"] for p in paths["/signals"]["get"]["parameters"]}
    hist_params = {p["name"] for p in paths["/signals/history"]["get"]["parameters"]}
    assert "asset_class" in sig_params
    assert "asset_class" in hist_params
    assert "/paper/universe" in paths

    acct = http.get("/paper/account").json()
    assert acct["live_trading"] is False
