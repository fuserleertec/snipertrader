from __future__ import annotations

from datetime import datetime, timezone

import pytest

from sniper_data.models import AssetClass
from sniper_data.symbols import infer_asset_class, normalize_symbol, normalize_tick, to_utc_ms


def test_uppercase_strip_hyphens():
    assert normalize_symbol("btc-usdt") == "BTCUSDT"
    assert normalize_symbol("AAPL") == "AAPL"
    assert normalize_symbol("es") == "ES"
    assert normalize_symbol("NQ1!") == "NQ1"


def test_asset_class_field():
    assert infer_asset_class("BTCUSDT") is AssetClass.CRYPTO
    assert infer_asset_class("AAPL") is AssetClass.EQUITY
    assert infer_asset_class("ES") is AssetClass.FUTURES
    assert infer_asset_class("XYZ", "futures") is AssetClass.FUTURES


def test_normalize_tick_utc_ms():
    dt = datetime(2024, 6, 4, 12, 0, tzinfo=timezone.utc)
    tick = normalize_tick(symbol="btc-usdt", price=1.0, volume=2.0, ts=dt)
    assert tick.symbol == "BTCUSDT"
    assert tick.asset_class is AssetClass.CRYPTO
    assert tick.ts_ms == int(dt.timestamp() * 1000)
    # seconds vs milliseconds
    assert to_utc_ms(dt.timestamp()) == tick.ts_ms
    assert to_utc_ms(tick.ts_ms) == tick.ts_ms


def test_empty_symbol_rejected():
    with pytest.raises(ValueError):
        normalize_symbol("---")
