from __future__ import annotations

import pydantic
import pytest

from pfund_blocks.entities.products.product_type import ProductType
from pfund_blocks.entities.venues.adapter_base import BaseAdapter
from pfund_blocks.enums import Channel, OrderType, Side, TimeInForce
from pfund_blocks.resolution import Resolution

PERPETUAL = ProductType.model_validate("FUTURE-CRYPTO-PERPETUAL")
FUTURE = ProductType.model_validate("FUTURE-CRYPTO")
INVERSE_PERPETUAL = ProductType.model_validate("FUTURE-CRYPTO-INVERSE-PERPETUAL")


class TestToVenue:
    def test_converts_internal_to_external(self):
        adapter = BaseAdapter(side={Side.BUY: "Buy", Side.SELL: "Sell"})
        assert adapter.to_venue(Side.BUY, group="side") == "Buy"
        assert adapter.to_venue(Side.SELL, group="side") == "Sell"

    def test_alias_resolves_to_same_member(self):
        adapter = BaseAdapter(side={Side.BUY: "Buy"})
        assert adapter.to_venue(Side.LONG, group="side") == "Buy"

    def test_missing_raises(self):
        adapter = BaseAdapter(order_type={OrderType.LIMIT: "Limit"})
        with pytest.raises(
            KeyError, match="has no venue mapping in group 'order_type'"
        ):
            adapter.to_venue(OrderType.STOP_MARKET, group="order_type")

    def test_external_value_is_not_an_internal_key(self):
        adapter = BaseAdapter(side={Side.BUY: "Buy"})
        with pytest.raises(KeyError):
            adapter.to_venue("Buy", group="side")


class TestFromVenue:
    def test_converts_external_to_internal(self):
        adapter = BaseAdapter(side={Side.BUY: "Buy", Side.SELL: "Sell"})
        assert adapter.from_venue("Buy", group="side") is Side.BUY
        assert adapter.from_venue("Sell", group="side") is Side.SELL

    def test_missing_raises(self):
        adapter = BaseAdapter(side={Side.BUY: "Buy"})
        with pytest.raises(KeyError, match="has no internal mapping in group 'side'"):
            adapter.from_venue("Hold", group="side")

    def test_internal_value_is_not_an_external_key(self):
        adapter = BaseAdapter(side={Side.BUY: "Buy"})
        with pytest.raises(KeyError):
            adapter.from_venue(Side.BUY, group="side")

    def test_shared_external_value_is_ambiguous(self):
        # e.g. Bybit's category "linear" covers several product types
        adapter = BaseAdapter(
            product_type={
                PERPETUAL: "linear",
                FUTURE: "linear",
                INVERSE_PERPETUAL: "inverse",
            }
        )
        assert adapter.to_venue(PERPETUAL, group="product_type") == "linear"
        assert adapter.to_venue(FUTURE, group="product_type") == "linear"
        assert adapter.from_venue("inverse", group="product_type") == INVERSE_PERPETUAL
        with pytest.raises(KeyError, match="is ambiguous"):
            adapter.from_venue("linear", group="product_type")


class TestNoCollision:
    """Internal and external values that are equal in Python must not overwrite each other."""

    def test_str_enum_equal_to_its_external_value(self):
        # StrEnum: OrderType.LIMIT == "LIMIT"
        adapter = BaseAdapter(order_type={OrderType.LIMIT: "LIMIT"})
        external = adapter.to_venue(OrderType.LIMIT, group="order_type")
        assert external == "LIMIT"
        assert type(external) is str
        assert adapter.from_venue("LIMIT", group="order_type") is OrderType.LIMIT

    def test_int_enum_with_bool_external_values(self):
        # IntEnum: Side.BUY == 1 == True, e.g. Hyperliquid's is_buy
        adapter = BaseAdapter(side={Side.BUY: True, Side.SELL: False})
        assert adapter.to_venue(Side.BUY, group="side") is True
        assert adapter.to_venue(Side.SELL, group="side") is False
        assert adapter.from_venue(True, group="side") is Side.BUY
        assert adapter.from_venue(False, group="side") is Side.SELL

    def test_int_enum_with_int_external_values(self):
        adapter = BaseAdapter(side={Side.BUY: 1, Side.SELL: -1})
        assert adapter.to_venue(Side.BUY, group="side") == 1
        assert adapter.from_venue(-1, group="side") is Side.SELL


class TestExternalValueTypes:
    @pytest.mark.parametrize("external", ["Buy", 1, True])
    def test_keeps_the_given_type(self, external: str | int | bool):
        adapter = BaseAdapter(side={Side.BUY: external})
        assert type(adapter.to_venue(Side.BUY, group="side")) is type(external)

    def test_rejects_non_scalar(self):
        with pytest.raises(pydantic.ValidationError):
            BaseAdapter(side={Side.BUY: ["Buy"]})  # ty: ignore[invalid-argument-type]


class TestAddMapping:
    def test_both_directions(self):
        adapter = BaseAdapter()
        adapter.add_mapping("BTC_USDT_PERP", "BTCUSDT", group="product")
        assert adapter.to_venue("BTC_USDT_PERP", group="product") == "BTCUSDT"
        assert adapter.from_venue("BTCUSDT", group="product") == "BTC_USDT_PERP"

    def test_writes_to_the_field(self):
        adapter = BaseAdapter()
        adapter.add_mapping("BTC_USDT_PERP", "BTCUSDT", group="product")
        assert adapter.product == {"BTC_USDT_PERP": "BTCUSDT"}
        assert adapter.model_dump()["product"] == {"BTC_USDT_PERP": "BTCUSDT"}

    def test_remap_drops_old_external_value(self):
        adapter = BaseAdapter()
        adapter.add_mapping("BTC_USDT_PERP", "BTCUSDT", group="product")
        adapter.add_mapping("BTC_USDT_PERP", "BTC-PERP", group="product")
        assert adapter.to_venue("BTC_USDT_PERP", group="product") == "BTC-PERP"
        assert adapter.from_venue("BTC-PERP", group="product") == "BTC_USDT_PERP"
        with pytest.raises(KeyError):
            adapter.from_venue("BTCUSDT", group="product")

    def test_same_mapping_twice_is_not_ambiguous(self):
        adapter = BaseAdapter()
        adapter.add_mapping("BTC_USDT_PERP", "BTCUSDT", group="product")
        adapter.add_mapping("BTC_USDT_PERP", "BTCUSDT", group="product")
        assert adapter.from_venue("BTCUSDT", group="product") == "BTC_USDT_PERP"

    def test_shared_external_value_becomes_ambiguous(self):
        adapter = BaseAdapter()
        adapter.add_mapping("BTC_USDT_PERP", "BTC", group="product")
        adapter.add_mapping("BTC_USDC_PERP", "BTC", group="product")
        with pytest.raises(KeyError, match="is ambiguous"):
            adapter.from_venue("BTC", group="product")

    def test_extends_configured_group(self):
        adapter = BaseAdapter(order_type={OrderType.LIMIT: "Limit"})
        adapter.add_mapping(OrderType.MARKET, "Market", group="order_type")
        assert adapter.to_venue(OrderType.LIMIT, group="order_type") == "Limit"
        assert adapter.from_venue("Market", group="order_type") is OrderType.MARKET

    def test_unknown_group_raises(self):
        adapter = BaseAdapter()
        with pytest.raises(ValueError, match="unknown adapter group 'prodcut'"):
            adapter.add_mapping("BTC_USDT_PERP", "BTCUSDT", group="prodcut")  # ty: ignore[invalid-argument-type]

    def test_does_not_leak_into_other_instances(self):
        adapter = BaseAdapter()
        adapter.add_mapping("BTC_USDT_PERP", "BTCUSDT", group="product")
        adapter.add_mapping(TimeInForce.GTC, "Gtc", group="time_in_force")
        other = BaseAdapter()
        assert other.product == {}
        assert other.to_venue(TimeInForce.GTC, group="time_in_force") == "GTC"


class TestTimeInForceDefault:
    def test_default_abbreviations(self):
        adapter = BaseAdapter()
        assert adapter.to_venue(TimeInForce.GTC, group="time_in_force") == "GTC"
        assert adapter.to_venue(TimeInForce.FOK, group="time_in_force") == "FOK"
        assert adapter.to_venue(TimeInForce.IOC, group="time_in_force") == "IOC"
        assert adapter.from_venue("IOC", group="time_in_force") is TimeInForce.IOC

    def test_override_replaces_the_whole_default(self):
        adapter = BaseAdapter(time_in_force={TimeInForce.GTC: "Gtc"})
        assert adapter.to_venue(TimeInForce.GTC, group="time_in_force") == "Gtc"
        with pytest.raises(KeyError):
            adapter.to_venue(TimeInForce.FOK, group="time_in_force")


class TestValidation:
    def test_str_keys_are_parsed_into_enums(self):
        adapter = BaseAdapter(side={"BUY": "Buy"}, channel={"tradebook": "publicTrade"})  # ty: ignore[invalid-argument-type]
        assert adapter.to_venue(Side.BUY, group="side") == "Buy"
        assert adapter.to_venue(Channel.tradebook, group="channel") == "publicTrade"

    def test_str_keys_are_parsed_into_product_types(self):
        adapter = BaseAdapter(product_type={"FUTURE-CRYPTO-PERPETUAL": "linear"})  # ty: ignore[invalid-argument-type]
        assert adapter.to_venue(PERPETUAL, group="product_type") == "linear"

    @pytest.mark.parametrize("key", ["1m", Resolution("1m")])
    def test_channel_resolution_keys_are_coerced(self, key: str | Resolution):
        adapter = BaseAdapter(channel_resolution={key: "1"})
        assert adapter.to_venue(Resolution("1m"), group="channel_resolution") == "1"
        assert adapter.from_venue("1", group="channel_resolution") == Resolution("1m")

    def test_unknown_field_is_forbidden(self):
        with pytest.raises(pydantic.ValidationError):
            BaseAdapter(sides={Side.BUY: "Buy"})  # ty: ignore[unknown-argument]

    def test_invalid_key_raises(self):
        with pytest.raises(pydantic.ValidationError):
            BaseAdapter(side={"HOLD": "Hold"})  # ty: ignore[invalid-argument-type]
