from __future__ import annotations

import pytest

from sniper_data.bus.kafka import InMemoryBus
from sniper_data.bus.redis_store import InMemoryStateStore
from sniper_data.bus.timescaledb import InMemoryOHLCVStore
from sniper_data.connectors.base import ConnectorNotConfigured
from sniper_data.connectors.options import OptionsChainConnector, occ_contract_symbol
from sniper_data.connectors.order_flow import MockOptionsFlow, OrderFlowConnector
from sniper_data.models import AssetClass, OptionsChain, OrderFlow
from sniper_data.pipeline import Runtime


@pytest.mark.asyncio
async def test_options_and_order_flow_stubs_refuse_without_keys():
    with pytest.raises(ConnectorNotConfigured):
        await anext(OptionsChainConnector().stream())
    with pytest.raises(ConnectorNotConfigured):
        await anext(OrderFlowConnector().stream())


def test_parse_quote_and_print_frozen_fields():
    opt = OptionsChainConnector()
    quote = opt.parse_quote(
        {
            "symbol": "aapl",
            "ts_ms": 1_725_458_400_000,
            "expiry": 1_725_545_600,
            "strike": 230.0,
            "option_type": "call",
            "contract_symbol": "AAPL250912C00230000",
            "bid": 1.2,
            "ask": 1.4,
            "open_interest": 900,
            "implied_volatility": 0.31,
            "delta": 0.55,
            "gamma": 0.04,
            "theta": -0.03,
            "vega": 0.11,
            "rho": 0.02,
        }
    )
    dumped = quote.model_dump(mode="json")
    assert dumped["symbol"] == "AAPL"
    assert dumped["asset_class"] == "equity"
    assert dumped["option_type"] == "call"
    assert "iv" not in dumped
    assert "oi" not in dumped
    assert "right" not in dumped
    assert occ_contract_symbol("AAPL", quote.expiry_ms, "call", 230.0).startswith("AAPL")

    flow = OrderFlowConnector()
    print_ = flow.parse_print(
        {
            "symbol": "aapl",
            "ts_ms": 1_725_458_400_000,
            "price": 228.5,
            "volume": 2_000,
            "aggressor": "buy",
        }
    )
    dumped = print_.model_dump(mode="json")
    assert dumped["aggressor"] == "buy"
    assert "side" not in dumped
    assert "taker_side" not in dumped
    assert dumped["notional"] == pytest.approx(228.5 * 2000)


def test_mock_options_flow_normalized():
    mock = MockOptionsFlow(["aapl"], seed=3)
    chain = mock.next_chain()
    flow = mock.next_order_flow()
    assert isinstance(chain, OptionsChain)
    assert isinstance(flow, OrderFlow)
    assert chain.symbol == "AAPL"
    assert chain.asset_class is AssetClass.EQUITY
    assert flow.aggressor in {"buy", "sell"}
    assert chain.schema_version == "1.1"


@pytest.mark.asyncio
async def test_pipeline_publishes_options_and_order_flow():
    bus = InMemoryBus()
    store = InMemoryStateStore()
    rt = Runtime(inmemory=True, bus=bus, store=store, bars=InMemoryOHLCVStore())
    await rt.start()
    mock = MockOptionsFlow(["AAPL"], seed=1)
    await bus.publish("order_flow", mock.next_order_flow("AAPL"), key="AAPL")
    await bus.publish("options_chain", mock.next_chain("AAPL"), key="AAPL")
    assert bus.latest("order_flow")["symbol"] == "AAPL"
    assert bus.latest("options_chain")["option_type"] in {"call", "put"}
    await rt.stop()
