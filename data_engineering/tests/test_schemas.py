from __future__ import annotations

import json
from pathlib import Path

from sniper_data.models import (
    AVWAPBands,
    AnchoredVWAP,
    AssetClass,
    KillZoneEvent,
    MssEvent,
    OHLCVBar,
    OptionsChain,
    OrderBlock,
    OrderFlow,
    RawTick,
    SessionType,
    SweepEvent,
    Timeframe,
    VolumeNode,
    VolumeProfile,
)
from sniper_data.setups import SETUP_KEYS

ROOT = Path(__file__).resolve().parents[2]
SCHEMAS = ROOT / "schemas"

EXPECTED = {
    "raw_tick.schema.json",
    "ohlcv_bar.schema.json",
    "session_levels.schema.json",
    "vwap_values.schema.json",
    "sweep_event.schema.json",
    "fvg_zone.schema.json",
    "mss_event.schema.json",
    "order_block.schema.json",
    "setup_signal.schema.json",
}


def _load(name: str) -> dict:
    return json.loads((SCHEMAS / name).read_text())


def test_schema_catalog_present():
    names = {p.name for p in SCHEMAS.glob("*.schema.json")}
    assert EXPECTED <= names
    for name in EXPECTED:
        doc = _load(name)
        assert doc["$schema"].startswith("https://json-schema.org/")
        assert doc["title"]
        assert doc["additionalProperties"] is False
        assert doc["properties"]["schema_version"]["const"] == "1.1"


def test_raw_tick_aggressor_optional():
    doc = _load("raw_tick.schema.json")
    assert "aggressor" not in doc["required"]
    assert "is_buyer_maker" not in doc["required"]
    assert doc["properties"]["aggressor"]["enum"] == ["buy", "sell", None]
    tick = RawTick(
        symbol="BTCUSDT",
        asset_class=AssetClass.CRYPTO,
        exchange="mock",
        ts_ms=1,
        price=1.0,
        volume=1.0,
    )
    assert tick.aggressor is None
    assert tick.is_buyer_maker is None
    filled = tick.model_copy(update={"aggressor": "buy", "is_buyer_maker": False})
    dumped = filled.model_dump()
    assert dumped["aggressor"] == "buy"
    assert "delta" not in dumped


def test_ohlcv_buy_sell_optional_no_delta_field():
    doc = _load("ohlcv_bar.schema.json")
    assert "buy_volume" not in doc["required"]
    assert "sell_volume" not in doc["required"]
    assert "delta" not in doc["properties"]
    bar = OHLCVBar(
        symbol="BTCUSDT",
        asset_class=AssetClass.CRYPTO,
        timeframe=Timeframe.M1,
        open_ts_ms=0,
        close_ts_ms=60_000,
        open=1,
        high=1,
        low=1,
        close=1,
        volume=2,
        n_ticks=1,
    )
    assert bar.buy_volume is None
    assert bar.sell_volume is None
    assert "delta" not in bar.model_dump()


def test_sweep_optional_fields_and_no_aliases():
    doc = _load("sweep_event.schema.json")
    for alias in ("direction", "sweep_level"):
        assert alias not in doc["properties"]
    for field in ("volume_profile", "delta_divergence", "time_to_reclaim_ms", "confirmed"):
        assert field not in doc["required"]
        assert field in doc["properties"]
    event = SweepEvent(
        id="s1",
        symbol="AAPL",
        asset_class=AssetClass.EQUITY,
        side="sell",
        swept_level=228.0,
        ts_ms=1,
        volume_profile="aggressive",
        delta_divergence=True,
        time_to_reclaim_ms=1500,
        confirmed=True,
    )
    assert event.side == "sell"
    assert event.volume_profile == "aggressive"


def test_mss_required_and_optional():
    doc = _load("mss_event.schema.json")
    assert doc["required"] == [
        "schema_version",
        "id",
        "symbol",
        "asset_class",
        "ts_ms",
        "direction",
        "broken_level",
        "swing_high",
        "swing_low",
        "trigger_sweep_id",
        "trigger_sweep_side",
    ]
    assert "timeframe" not in doc["required"]
    assert "confirmed" not in doc["required"]
    mss = MssEvent(
        id="m1",
        symbol="BTCUSDT",
        asset_class=AssetClass.CRYPTO,
        ts_ms=1,
        direction="bullish",
        broken_level=99.0,
        swing_high=101.0,
        swing_low=98.0,
        trigger_sweep_id="s1",
        trigger_sweep_side="buy",
        timeframe="5m",
        confirmed=True,
    )
    assert mss.trigger_sweep_side == "buy"
    bare = MssEvent(
        id="m2",
        symbol="ES",
        asset_class=AssetClass.FUTURES,
        ts_ms=2,
        direction="bearish",
        broken_level=5000.0,
        swing_high=None,
        swing_low=None,
        trigger_sweep_id="s2",
        trigger_sweep_side="sell",
    )
    assert bare.timeframe is None
    assert bare.confirmed is None


PHASE2 = {
    "avwap.schema.json",
    "volume_profile.schema.json",
    "kill_zone_event.schema.json",
}


def test_phase2_schemas_match_exact_wire_payload():
    names = {p.name for p in SCHEMAS.glob("*.schema.json")}
    assert PHASE2 <= names
    avwap = _load("avwap.schema.json")
    assert "schema_version" not in avwap["properties"]
    assert avwap["required"] == [
        "anchor_id",
        "symbol",
        "anchor_time",
        "anchor_price",
        "vwap_value",
        "bands",
        "asset_class",
    ]
    vp = _load("volume_profile.schema.json")
    assert "schema_version" not in vp["properties"]
    assert vp["required"] == [
        "symbol",
        "session_type",
        "high_volume_nodes",
        "low_volume_nodes",
        "poc",
        "timestamp",
    ]
    kz = _load("kill_zone_event.schema.json")
    assert "schema_version" not in kz["properties"]
    assert kz["required"] == [
        "symbol",
        "kill_zone",
        "start_time",
        "end_time",
        "active",
        "asset_class",
    ]

    snap = AnchoredVWAP(
        anchor_id="uuid",
        symbol="BTCUSDT",
        anchor_time=1725458400000,
        anchor_price=64000.00,
        vwap_value=64500.00,
        bands=AVWAPBands(
            plus_1_sigma=64700.00,
            plus_2_sigma=64950.00,
            plus_3_sigma=65200.00,
            minus_1_sigma=64300.00,
            minus_2_sigma=64050.00,
            minus_3_sigma=63800.00,
        ),
        asset_class=AssetClass.CRYPTO,
    )
    dumped = snap.model_dump(mode="json")
    assert set(dumped) == set(avwap["required"])
    profile = VolumeProfile(
        symbol="BTCUSDT",
        session_type=SessionType.NY_AM,
        high_volume_nodes=[VolumeNode(price=65000.00, volume=1500.5)],
        low_volume_nodes=[VolumeNode(price=64900.00, volume=200.0)],
        poc=65000.00,
        timestamp=1725459000000,
    )
    assert set(profile.model_dump(mode="json")) == set(vp["required"])
    event = KillZoneEvent(
        symbol="BTCUSDT",
        kill_zone=SessionType.NY_AM,
        start_time=1725458400000,
        end_time=1725462000000,
        active=True,
        asset_class=AssetClass.CRYPTO,
    )
    assert set(event.model_dump(mode="json")) == set(kz["required"])


PHASE3 = {
    "performance_summary.schema.json",
    "options_chain.schema.json",
    "order_flow.schema.json",
}


def test_phase3_performance_and_us_equity_schemas():
    names = {p.name for p in SCHEMAS.glob("*.schema.json")}
    assert PHASE3 <= names
    summary = _load("performance_summary.schema.json")
    assert "schema_version" not in summary["properties"]
    assert summary["required"] == ["timestamp", "overall", "by_setup"]
    assert list(summary["properties"]["by_setup"]["required"]) == list(SETUP_KEYS)
    assert summary["properties"]["by_setup"]["additionalProperties"] is False

    chain = _load("options_chain.schema.json")
    assert chain["properties"]["schema_version"]["const"] == "1.1"
    for alias in ("iv", "oi", "right"):
        assert alias not in chain["properties"]
    flow = _load("order_flow.schema.json")
    assert "side" not in flow["properties"]
    assert "taker_side" not in flow["properties"]
    assert flow["properties"]["aggressor"]["enum"] == ["buy", "sell"]

    opt = OptionsChain(
        symbol="AAPL",
        asset_class=AssetClass.EQUITY,
        exchange="opra",
        ts_ms=1,
        expiry_ms=2,
        strike=230.0,
        option_type="call",
        contract_symbol="AAPL250912C00230000",
    )
    assert opt.schema_version == "1.1"
    of = OrderFlow(
        symbol="AAPL",
        asset_class=AssetClass.EQUITY,
        exchange="nasdaq",
        ts_ms=1,
        price=228.0,
        volume=100.0,
        aggressor="buy",
    )
    assert "side" not in of.model_dump()


def test_order_block_required_and_optional():
    doc = _load("order_block.schema.json")
    assert doc["required"] == [
        "schema_version",
        "id",
        "symbol",
        "asset_class",
        "direction",
        "high",
        "low",
        "created_ts_ms",
    ]
    ob = OrderBlock(
        id="ob1",
        symbol="NQ",
        asset_class=AssetClass.FUTURES,
        direction="bearish",
        high=20_000.0,
        low=19_980.0,
        created_ts_ms=1,
        timeframe=Timeframe.M15,
        origin_open=19_995.0,
        origin_close=19_982.0,
    )
    assert ob.mitigated is False
    assert ob.ttl_seconds is None
