from __future__ import annotations

from sniper_data.models import RISK_VALIDATE_FIELDS, AssetClass, AnchorType, SessionType, VWAPValues
from sniper_data.setup_detection.candidate import SetupCandidate, to_risk_request
from sniper_data.setup_detection.ranking import (
    ENSEMBLE_WEIGHTS,
    PICKS_ENSEMBLE_FIELDS,
    EnsembleBook,
    consume_picks_ensemble,
    ensemble_features_snapshot,
    rank_top,
    score_ensemble,
    to_picks_ensemble_row,
)


def _vwap(*, sigma: float, vwap: float = 100.0) -> VWAPValues:
    return VWAPValues(
        symbol="ES",
        asset_class=AssetClass.FUTURES,
        anchor_type=AnchorType.SESSION,
        session_type=SessionType.RTH,
        anchor_start_ms=1,
        vwap=vwap,
        sigma=sigma,
        band_m3=vwap - 3 * sigma,
        band_m2=vwap - 2 * sigma,
        band_m1=vwap - sigma,
        band_p1=vwap + sigma,
        band_p2=vwap + 2 * sigma,
        band_p3=vwap + 3 * sigma,
        cum_volume=10.0,
        n_obs=3,
        updated_ts_ms=2,
    )


def test_weights_locked():
    assert ENSEMBLE_WEIGHTS == {
        "setup_quality": 0.40,
        "confluence": 0.20,
        "kill_zone": 0.15,
        "volume": 0.15,
        "freshness": 0.10,
    }
    assert abs(sum(ENSEMBLE_WEIGHTS.values()) - 1.0) < 1e-9


def test_score_is_dynamic_not_hardcoded():
    weak, weak_parts = score_ensemble(
        conviction=60,
        contributing_factors=["fvg"],
        kill_zone_aligned=False,
        volume_confirmed=False,
        entry=100.1,
        vwap=_vwap(sigma=2.0),
        ts_ms=1_000,
        now_ms=1_000,
    )
    strong, strong_parts = score_ensemble(
        conviction=90,
        contributing_factors=["fvg", "kill_zone", "volume_confirm", "multi_pattern"],
        kill_zone_aligned=True,
        volume_confirmed=True,
        entry=104.0,
        vwap=_vwap(sigma=2.0),
        ts_ms=1_000,
        now_ms=1_000,
    )
    assert 0 <= weak <= 100 and 0 <= strong <= 100
    assert strong > weak
    assert strong_parts["kill_zone"] == 100
    assert weak_parts["kill_zone"] == 0
    assert set(strong_parts) == set(ENSEMBLE_WEIGHTS)


def test_top10_stable_and_reorders_when_inputs_change():
    now = 10_000
    rows = [
        {"id": "a", "symbol": "ES", "asset_class": "futures", "side": "long", "setup_type": "sweep_reclaim",
         "ensemble_score": 40, "ts_ms": now, "confidence": 0.4, "contributing_factors": ["mss"]},
        {"id": "b", "symbol": "CL", "asset_class": "futures", "side": "short", "setup_type": "fvg_entry",
         "ensemble_score": 80, "ts_ms": now, "confidence": 0.8, "contributing_factors": ["fvg"]},
        {"id": "c", "symbol": "GC", "asset_class": "futures", "side": "long", "setup_type": "vwap_pullback_cont",
         "ensemble_score": 70, "ts_ms": now, "confidence": 0.7, "contributing_factors": ["vwap_pullback"]},
        {"id": "d", "symbol": "NQ", "asset_class": "futures", "side": "long", "setup_type": "po3_judas",
         "ensemble_score": 55, "ts_ms": now, "confidence": 0.55, "contributing_factors": ["liquidity_sweep"]},
    ]
    first = rank_top(rows, now_ms=now, universe=["ES", "CL", "GC", "NQ"])
    second = rank_top(rows, now_ms=now, universe=["ES", "CL", "GC", "NQ"])
    assert [p["symbol"] for p in first] == [p["symbol"] for p in second]
    assert first[0]["symbol"] == "CL"
    assert first[0]["rank"] == 1
    assert set(first[0]) >= set(PICKS_ENSEMBLE_FIELDS)

    flipped = [dict(r) for r in rows]
    flipped[0]["ensemble_score"] = 99
    flipped[1]["ensemble_score"] = 10
    reordered = rank_top(flipped, now_ms=now, universe=["ES", "CL", "GC", "NQ"])
    assert reordered[0]["symbol"] == "ES"
    assert [p["symbol"] for p in reordered] != [p["symbol"] for p in first]


def test_picks_ensemble_mapping_and_book():
    book = EnsembleBook()
    book.record(
        {
            "id": "sig-1",
            "symbol": "ES",
            "asset_class": "futures",
            "side": "long",
            "setup_type": "sweep_reclaim",
            "ensemble_score": 81,
            "rank_components": {"setup_quality": 80, "confluence": 50, "kill_zone": 100, "volume": 100, "freshness": 90},
            "contributing_factors": ["liquidity_sweep", "mss"],
            "ts_ms": 5,
            "entry": 5800.0,
            "target": 5900.0,
        }
    )
    picks = book.top(limit=10)
    assert picks[0]["signal"] == "Buy"
    assert picks[0]["category"] == "futures"
    assert picks[0]["conviction"] == 81
    assert picks[0]["score"] == 81
    assert picks[0]["best_confidence"] == picks[0]["confidence"]
    mapped = to_picks_ensemble_row(book.signals[0], rank=1)
    assert mapped["ensemble_score"] == 81
    assert mapped["score"] == 81


def test_ensemble_fields_never_on_risk_validate():
    cand = SetupCandidate(
        setup_number=1,
        setup_type="sweep_reclaim",
        symbol="ES",
        asset_class=AssetClass.FUTURES,
        side="long",
        conviction=70,
        entry=100,
        stop=99,
        target=103,
        timeframe="5m",
        trigger_event_ids=["swp-es"],
        ts_ms=1,
        ensemble_score=77,
        rank_components={"setup_quality": 70, "confluence": 40, "kill_zone": 0, "volume": 0, "freshness": 100},
    )
    body = to_risk_request(cand)
    assert "id" not in body
    assert "ensemble_score" not in body
    assert "rank_components" not in body
    assert "category" not in body
    assert "contributing_factors" not in body
    assert set(body) <= set(RISK_VALIDATE_FIELDS)


def test_consume_prefers_ensemble_features_over_signal_mirrors():
    stale = {
        "id": "old",
        "symbol": "ES",
        "side": "long",
        "setup_type": "sweep_reclaim",
        "ensemble_score": 10,
        "confidence": 0.1,
        "ts_ms": 1,
        "rank_components": {"setup_quality": 10, "confluence": 0, "kill_zone": 0, "volume": 0, "freshness": 0},
        "contributing_factors": ["mss"],
    }
    parts = {"setup_quality": 90, "confluence": 80, "kill_zone": 100, "volume": 100, "freshness": 80}
    features = ensemble_features_snapshot(
        [
            {
                "symbol": "CL",
                "rank": 1,
                "ensemble_score": 88,
                "best_confidence": 0.77,
                "side": "short",
                "setup_type": "fvg_entry",
                "rank_components": parts,
                "contributing_factors": ["fvg", "kill_zone"],
                "ts_ms": 2,
                "active_levels": True,
            }
        ],
        signals=[stale],
        universe=["ES", "CL", "GC", "NQ"],
    )
    out = consume_picks_ensemble(features=features, signals=[stale], limit=10)
    assert out["source"] == "ensemble_features"
    assert out["refresh_seconds"] == 900
    assert out["weights"] == ENSEMBLE_WEIGHTS
    assert out["live_trading"] is False
    assert out["picks"][0]["symbol"] == "CL"
    assert out["picks"][0]["score"] == 88
    assert out["picks"][0]["ensemble_score"] == 88
    assert out["picks"][0]["confidence"] == 0.77
    assert out["picks"][0]["best_confidence"] == 0.77
    assert out["picks"][0]["rank_components"] == parts
    assert out["picks"][0]["contributing_factors"] == ["fvg", "kill_zone"]


def test_consume_skips_inactive_and_falls_back_to_signal_mirrors():
    features = {
        "picks": [
            {"symbol": "ES", "ensemble_score": 90, "confidence": 0.9, "active_levels": False, "side": "long", "ts_ms": 1},
            {"symbol": "CL", "ensemble_score": 80, "skip_reason": "no_active_levels", "side": "short", "ts_ms": 1},
        ]
    }
    skipped = consume_picks_ensemble(features=features, limit=10)
    assert skipped["picks"] == []
    assert {row["symbol"] for row in skipped["skipped"]} >= {"ES", "CL"}

    signals = [
        {
            "id": "nq-1",
            "symbol": "NQ",
            "side": "long",
            "setup_type": "po3_judas",
            "ensemble_score": 66,
            "confidence": 0.66,
            "ts_ms": 5,
            "rank_components": {"setup_quality": 66, "confluence": 40, "kill_zone": 0, "volume": 0, "freshness": 100},
            "contributing_factors": ["liquidity_sweep"],
        }
    ]
    fallback = consume_picks_ensemble(features=None, signals=signals, limit=10)
    assert fallback["source"] == "setup_signals"
    assert fallback["picks"][0]["symbol"] == "NQ"
    assert fallback["picks"][0]["score"] == 66
    assert fallback["picks"][0]["confidence"] == 0.66
    assert fallback["picks"][0]["rank_components"]["setup_quality"] == 66
    assert fallback["refresh_seconds"] == 900


def test_book_prefers_recorded_features():
    book = EnsembleBook()
    book.record(
        {
            "id": "es-old",
            "symbol": "ES",
            "side": "long",
            "setup_type": "sweep_reclaim",
            "ensemble_score": 11,
            "confidence": 0.11,
            "ts_ms": 1,
        }
    )
    book.record_features(
        ensemble_features_snapshot(
            [
                {
                    "symbol": "GC",
                    "ensemble_score": 99,
                    "best_confidence": 0.91,
                    "side": "long",
                    "setup_type": "vwap_pullback_cont",
                    "rank_components": {"setup_quality": 99, "confluence": 50, "kill_zone": 0, "volume": 0, "freshness": 100},
                    "contributing_factors": ["vwap_pullback"],
                    "ts_ms": 3,
                }
            ]
        )
    )
    picks = book.top(limit=10)
    assert picks[0]["symbol"] == "GC"
    assert picks[0]["score"] == 99
    assert picks[0]["confidence"] == 0.91
