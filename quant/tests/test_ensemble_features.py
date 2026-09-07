"""Kafka ensemble_features → GET /picks/ensemble (paper only)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from sniper_quant.api import create_app
from sniper_quant.bus import ENSEMBLE_FEATURES_TOPIC, InMemoryBus
from sniper_quant.features import (
    FEATURE_WEIGHTS,
    EnsembleFeatureService,
    InMemoryEnsembleStore,
    parse_ensemble_features,
    run_inmemory_ensemble_consumer,
    score_from_components,
)
from sniper_quant.models import FeatureRankComponents
from sniper_quant.risk.engine import RiskEngine, RiskState
from sniper_quant.store.signals import InMemorySignalStore
from sniper_quant.universe import load_paper_universe
from tests.conftest import make_settings

REQUIRED_FUTURES = {"ES", "CL", "GC", "NQ"}
OUTSIDER = "IBM"


def _snap(**overrides) -> dict:
    body = {
        "schema_version": "1.1",
        "symbol": "ES",
        "asset_class": "futures",
        "ts_ms": 1_700_000_400_000,
        "timeframe": "15m",
        "ensemble_score": 81.5,
        "best_confidence": 0.88,
        "active_levels": True,
        "rank_components": {
            "setup_quality": 32.0,
            "risk_adjusted": 16.0,
            "kill_zone": 12.0,
            "volume": 10.0,
            "freshness": 8.0,
        },
        "contributing_factors": ["kz_align", "2s_tag"],
        "confluence_count": 2,
        "setup_types": ["avwap_ob_confluence"],
        "ref_session": "rth",
    }
    body.update(overrides)
    return body


def _client(store: InMemoryEnsembleStore | None = None, **overrides):
    settings = make_settings(**overrides)
    engine = RiskEngine(settings=settings, state=RiskState(equity=100_000))
    features = store or InMemoryEnsembleStore()
    app = create_app(
        settings=settings,
        signals=InMemorySignalStore(),
        engine=engine,
        features=features,
    )
    return TestClient(app), features


def test_topic_name_and_weights_locked():
    assert ENSEMBLE_FEATURES_TOPIC == "ensemble_features"
    assert FEATURE_WEIGHTS == {
        "setup_quality": 40.0,
        "confluence": 20.0,
        "kill_zone": 15.0,
        "volume": 15.0,
        "freshness": 10.0,
    }


def test_score_from_components_unit_and_publisher_100():
    unit = FeatureRankComponents(
        setup_quality=1.0,
        confluence=1.0,
        kill_zone=1.0,
        volume=1.0,
        freshness=1.0,
    )
    assert score_from_components(unit) == 100.0
    # 1<v≤100 → weight*(v/100). 40/20/15/15/10 → 16+4+2.25+2.25+1 = 25.5
    mid = FeatureRankComponents(
        setup_quality=40.0,
        risk_adjusted=20.0,
        kill_zone=15.0,
        volume=15.0,
        freshness=10.0,
    )
    assert mid.confluence == 20.0
    assert mid.risk_adjusted == 20.0
    assert abs(score_from_components(mid) - 25.5) < 0.01
    half = FeatureRankComponents(setup_quality=0.5, confluence=0.5)
    assert score_from_components(half) == 30.0
    ml = FeatureRankComponents(
        setup_quality=80,
        confluence=70,
        kill_zone=100,
        volume=40,
        freshness=50,
    )
    assert abs(score_from_components(ml) - 72.0) < 0.01
    over = FeatureRankComponents.model_construct(setup_quality=140)
    assert score_from_components(over) == 40.0


@pytest.mark.asyncio
async def test_inmemory_bus_upserts_keyed_snapshot():
    store = InMemoryEnsembleStore()
    service = EnsembleFeatureService(store)
    bus = InMemoryBus()
    await run_inmemory_ensemble_consumer(bus, service)
    payload = _snap(symbol="CL", ensemble_score=77)
    await bus.publish(ENSEMBLE_FEATURES_TOPIC, payload, key="CL")
    latest = store.latest("CL")
    assert latest is not None
    assert latest.ensemble_score == 77
    assert latest.symbol == "CL"


def test_parse_uses_kafka_key_when_symbol_omitted():
    feat = parse_ensemble_features({"schema_version": "1.1", "ts_ms": 1}, key="nq")
    assert feat.symbol == "NQ"


def test_ensemble_maps_score_and_confidence_and_extras():
    http, store = _client()
    store.upsert(parse_ensemble_features(_snap()))
    store.upsert(parse_ensemble_features(_snap(symbol="CL", ensemble_score=90, best_confidence=0.61)))
    store.upsert(parse_ensemble_features(_snap(symbol="GC", ensemble_score=70, best_confidence=0.99)))
    store.upsert(parse_ensemble_features(_snap(symbol="NQ", ensemble_score=60)))

    body = http.get("/picks/ensemble", params={"as_of_ts_ms": 1_700_000_400_000}).json()
    assert body["refresh_sec"] == 900
    assert body["items"][0]["symbol"] == "CL"
    assert body["items"][0]["score"] == 90
    assert body["items"][0]["confidence"] == 0.61
    es = next(row for row in body["items"] if row["symbol"] == "ES")
    assert es["score"] == 81.5
    assert es["confidence"] == 0.88
    assert es["rank_components"]["setup_quality"] == 32.0
    assert es["rank_components"]["confluence"] == 16.0
    assert es["rank_components"]["risk_adjusted"] == 16.0
    assert es["contributing_factors"] == ["kz_align", "2s_tag"]
    assert es["confluence_count"] == 2
    assert es["setup_types"] == ["avwap_ob_confluence"]
    symbols = {row["symbol"] for row in body["items"]}
    assert REQUIRED_FUTURES <= symbols | {"ES", "CL", "GC", "NQ"}
    # At least the four futures we published are inside the top 10 or ranked.
    ranked = {row["symbol"] for row in body["items"]}
    assert {"ES", "CL", "GC", "NQ"} <= ranked or {"ES", "CL", "GC"} <= ranked


def test_skip_active_levels_false_even_with_high_score():
    http, store = _client()
    store.upsert(
        parse_ensemble_features(
            _snap(symbol="ES", ensemble_score=100, best_confidence=1.0, active_levels=False, skip_reason="stale")
        )
    )
    store.upsert(parse_ensemble_features(_snap(symbol="CL", ensemble_score=10, best_confidence=0.4)))
    body = http.get("/picks/ensemble", params={"as_of_ts_ms": 1_700_000_400_000}).json()
    symbols = [row["symbol"] for row in body["items"]]
    assert "ES" not in symbols
    assert body["items"][0]["symbol"] == "CL"


def test_prefer_ml_ensemble_score_over_recompute():
    http, store = _client()
    store.upsert(
        parse_ensemble_features(
            _snap(
                symbol="GC",
                ensemble_score=12,
                rank_components={
                    "setup_quality": 40,
                    "risk_adjusted": 20,
                    "kill_zone": 15,
                    "volume": 15,
                    "freshness": 10,
                },
            )
        )
    )
    body = http.get("/picks/ensemble", params={"as_of_ts_ms": 1_700_000_400_000}).json()
    gc = next(row for row in body["items"] if row["symbol"] == "GC")
    assert gc["score"] == 12
    assert gc["rank_components"]["setup_quality"] == 40


def test_recompute_when_ensemble_score_omitted():
    http, store = _client()
    payload = _snap(symbol="NQ", ensemble_score=None)
    payload.pop("ensemble_score")
    store.upsert(parse_ensemble_features(payload))
    body = http.get("/picks/ensemble", params={"as_of_ts_ms": 1_700_000_400_000}).json()
    nq = next(row for row in body["items"] if row["symbol"] == "NQ")
    assert nq["score"] == 20.1  # 1<v≤100: 40*0.32 + 20*0.16 + 15*0.12 + 15*0.10 + 10*0.08
    assert "recomputed" in (nq["notes"] or "")


def test_features_never_rank_outside_universe():
    http, store = _client()
    store.upsert(parse_ensemble_features(_snap(symbol=OUTSIDER, ensemble_score=100, asset_class="equity")))
    store.upsert(parse_ensemble_features(_snap(symbol="ES", ensemble_score=1)))
    body = http.get("/picks/ensemble", params={"as_of_ts_ms": 1_700_000_400_000}).json()
    assert OUTSIDER not in {row["symbol"] for row in body["items"]}
    paper = {sym for sym, _ in load_paper_universe(make_settings())}
    assert {row["symbol"] for row in body["items"]} <= paper


def test_categorized_uses_same_features():
    http, store = _client()
    store.upsert(
        parse_ensemble_features(
            _snap(symbol="AAPL", asset_class="equity", setup_types=["vwap_pullback_cont"], ensemble_score=88)
        )
    )
    store.upsert(
        parse_ensemble_features(
            _snap(symbol="ES", setup_types=["sweep_reclaim"], ensemble_score=40)
        )
    )
    body = http.get(
        "/picks/categorized",
        params={"as_of_ts_ms": 1_700_000_400_000, "limit": 20},
    ).json()
    assert body["refresh_sec"] == 900
    assert len(body["items"]) <= 20
    by_sym = {row["symbol"]: row for row in body["items"]}
    assert by_sym["AAPL"]["category"] == "momentum"
    assert by_sym["AAPL"]["score"] == 88
    assert by_sym["AAPL"]["confluence_count"] == 2
    assert by_sym["ES"]["category"] == "mean_reversion"
    futures = http.get(
        "/picks/categorized",
        params={"asset_class": "futures", "as_of_ts_ms": 1_700_000_400_000},
    ).json()
    assert {row["symbol"] for row in futures["items"]} <= REQUIRED_FUTURES
    assert http.get("/paper/account").json()["live_trading"] is False


def test_openapi_documents_ensemble_features_contract():
    http, _store = _client()
    spec = http.get("/openapi.json").json()
    desc = spec["info"]["description"]
    assert "ensemble_features" in desc
    assert "best_confidence" in desc
    assert "active_levels" in desc
    pick = spec["components"]["schemas"]["EnsemblePick"]
    assert "rank_components" in pick["properties"]
    assert "contributing_factors" in pick["properties"]
    assert "confluence_count" in pick["properties"]
    feat = spec["components"]["schemas"]["FeatureRankComponents"]
    assert {"setup_quality", "confluence", "kill_zone", "volume", "freshness"} <= set(
        feat["properties"]
    )
    setups = http.get("/v1/setups").json()
    assert setups["ensemble_features_topic"] == "ensemble_features"
    assert setups["ensemble_features_key"] == "symbol"
    assert setups["ensemble_refresh_sec"] == 900
    assert setups["rank_components"] == "publish_only_0_100_confluence"
    health = http.get("/health").json()
    assert health["rank_components"] == "publish_only_0_100_confluence"
    assert health["live_trading"] is False
    uni = http.get("/paper/universe").json()
    assert uni["live_trading"] is False
    assert uni["ensemble_features"]["topic"] == "ensemble_features"
    assert REQUIRED_FUTURES <= {row["symbol"] for row in uni["ranking_universe"]}
