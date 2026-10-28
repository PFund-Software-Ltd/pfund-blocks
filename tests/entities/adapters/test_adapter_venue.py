from __future__ import annotations

import pydantic
import pytest

from pfund_blocks.entities.adapters.adapter_base import BaseAdapter
from pfund_blocks.entities.adapters.adapter_venue import VenueAdapter
from pfund_blocks.enums import Channel, MarginMode, OrderType, Side, TimeInForce


class TestTradingGroups:
    def test_converts_both_directions(self):
        adapter = VenueAdapter(
            order_type={OrderType.LIMIT: "Limit", OrderType.MARKET: "Market"}
        )
        assert adapter.to_source(OrderType.LIMIT, group="order_type") == "Limit"
        assert adapter.from_source("Market", group="order_type") is OrderType.MARKET

    def test_missing_raises(self):
        adapter = VenueAdapter(order_type={OrderType.LIMIT: "Limit"})
        with pytest.raises(
            KeyError, match="has no source mapping in group 'order_type'"
        ):
            adapter.to_source(OrderType.STOP_MARKET, group="order_type", strict=True)

    def test_order_status_maps_the_repr(self):
        adapter = VenueAdapter(order_status={"CF--": "Filled"})
        assert adapter.from_source("Filled", group="order_status") == "CF--"

    def test_str_keys_are_parsed_into_enums(self):
        adapter = VenueAdapter(margin_mode={"CROSS": "REGULAR_MARGIN"})  # ty: ignore[invalid-argument-type]
        assert adapter.to_source(MarginMode.CROSS, group="margin_mode") == (
            "REGULAR_MARGIN"
        )

    def test_invalid_key_raises(self):
        with pytest.raises(pydantic.ValidationError):
            VenueAdapter(order_type={"TWAP": "Twap"})  # ty: ignore[invalid-argument-type]


class TestNoCollision:
    def test_str_enum_equal_to_its_external_value(self):
        # StrEnum: OrderType.LIMIT == "LIMIT"
        adapter = VenueAdapter(order_type={OrderType.LIMIT: "LIMIT"})
        assert type(adapter.to_source(OrderType.LIMIT, group="order_type")) is str
        assert adapter.from_source("LIMIT", group="order_type") is OrderType.LIMIT


class TestTimeInForceDefault:
    def test_default_abbreviations(self):
        adapter = VenueAdapter()
        assert adapter.to_source(TimeInForce.GTC, group="time_in_force") == "GTC"
        assert adapter.to_source(TimeInForce.FOK, group="time_in_force") == "FOK"
        assert adapter.to_source(TimeInForce.IOC, group="time_in_force") == "IOC"
        assert adapter.from_source("IOC", group="time_in_force") is TimeInForce.IOC

    def test_override_replaces_the_whole_default(self):
        adapter = VenueAdapter(time_in_force={TimeInForce.GTC: "Gtc"})
        assert adapter.to_source(TimeInForce.GTC, group="time_in_force") == "Gtc"
        with pytest.raises(KeyError):
            adapter.to_source(TimeInForce.FOK, group="time_in_force", strict=True)

    def test_add_mapping_does_not_leak_into_the_default(self):
        adapter = VenueAdapter()
        adapter.add_mapping(TimeInForce.GTC, "Gtc", group="time_in_force")
        assert VenueAdapter().to_source(TimeInForce.GTC, group="time_in_force") == "GTC"


class TestSplit:
    def test_has_the_base_groups(self):
        adapter = VenueAdapter(
            side={Side.BUY: "Buy"}, channel={Channel.tradebook: "publicTrade"}
        )
        adapter.add_mapping("BTC_USDT_PERP", "BTCUSDT", group="product")
        assert adapter.to_source(Side.BUY, group="side") == "Buy"
        assert adapter.to_source(Channel.tradebook, group="channel") == "publicTrade"
        assert adapter.from_source("BTCUSDT", group="product") == "BTC_USDT_PERP"

    def test_base_has_no_trading_groups(self):
        # e.g. a data source has no order types
        assert "order_type" not in BaseAdapter.model_fields
        assert "time_in_force" not in BaseAdapter.model_fields
        with pytest.raises(pydantic.ValidationError):
            BaseAdapter(order_type={OrderType.LIMIT: "Limit"})  # ty: ignore[unknown-argument]

    def test_base_add_mapping_rejects_trading_groups(self):
        with pytest.raises(ValueError, match="unknown adapter group 'order_type'"):
            BaseAdapter().add_mapping(OrderType.LIMIT, "Limit", group="order_type")  # ty: ignore[invalid-argument-type]
