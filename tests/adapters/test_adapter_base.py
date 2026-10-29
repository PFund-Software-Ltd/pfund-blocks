from __future__ import annotations

import pydantic
import pytest

from pfund_blocks.adapters.adapter_base import BaseAdapter
from pfund_blocks.entities.products.future import FutureProduct
from pfund_blocks.entities.products.product_type import ProductType
from pfund_blocks.entities.products.spot import CryptoProduct
from pfund_blocks.enums import Channel, OptionType, Side
from pfund_blocks.resolution import Resolution

PERPETUAL = ProductType.model_validate("FUTURE-CRYPTO-PERPETUAL")
FUTURE = ProductType.model_validate("FUTURE-CRYPTO")
INVERSE_PERPETUAL = ProductType.model_validate("FUTURE-CRYPTO-INVERSE-PERPETUAL")


class TestToSource:
    def test_converts_internal_to_external(self):
        adapter = BaseAdapter(option_type={OptionType.CALL: "C", OptionType.PUT: "P"})
        assert adapter.to_source(OptionType.CALL, group="option_type") == "C"
        assert adapter.to_source(OptionType.PUT, group="option_type") == "P"

    def test_missing_raises(self):
        adapter = BaseAdapter(channel={Channel.tradebook: "publicTrade"})
        with pytest.raises(KeyError, match="has no source mapping in group 'channel'"):
            adapter.to_source(Channel.orderbook, group="channel", strict=True)

    def test_external_value_is_not_an_internal_key(self):
        adapter = BaseAdapter(option_type={OptionType.CALL: "C"})
        with pytest.raises(KeyError):
            adapter.to_source("C", group="option_type", strict=True)


class TestPassThrough:
    """Unmapped values are returned as is, unless strict=True."""

    def test_to_source(self):
        adapter = BaseAdapter(asset={"XBT": "BTC"})
        assert adapter.to_source("XBT", group="asset") == "BTC"
        assert adapter.to_source("ETH", group="asset") == "ETH"

    def test_to_source_keeps_the_type(self):
        assert BaseAdapter().to_source(Side.BUY, group="side") is Side.BUY

    def test_from_source(self):
        adapter = BaseAdapter(asset={"XBT": "BTC"})
        assert adapter.from_source("BTC", group="asset") == "XBT"
        assert adapter.from_source("ETH", group="asset") == "ETH"

    def test_ambiguous_raises_without_strict(self):
        adapter = BaseAdapter(product_type={PERPETUAL: "linear", FUTURE: "linear"})
        with pytest.raises(KeyError, match="is ambiguous"):
            adapter.from_source("linear", group="product_type")


class TestFromSource:
    def test_converts_external_to_internal(self):
        adapter = BaseAdapter(option_type={OptionType.CALL: "C", OptionType.PUT: "P"})
        assert adapter.from_source("C", group="option_type") is OptionType.CALL
        assert adapter.from_source("P", group="option_type") is OptionType.PUT

    def test_missing_raises(self):
        adapter = BaseAdapter(option_type={OptionType.CALL: "C"})
        with pytest.raises(
            KeyError, match="has no internal mapping in group 'option_type'"
        ):
            adapter.from_source("X", group="option_type", strict=True)

    def test_internal_value_is_not_an_external_key(self):
        adapter = BaseAdapter(option_type={OptionType.CALL: "C"})
        with pytest.raises(KeyError):
            adapter.from_source(OptionType.CALL, group="option_type", strict=True)

    def test_shared_external_value_is_ambiguous(self):
        # e.g. Bybit's category "linear" covers several product types
        adapter = BaseAdapter(
            product_type={
                PERPETUAL: "linear",
                FUTURE: "linear",
                INVERSE_PERPETUAL: "inverse",
            }
        )
        assert adapter.to_source(PERPETUAL, group="product_type") == "linear"
        assert adapter.to_source(FUTURE, group="product_type") == "linear"
        assert adapter.from_source("inverse", group="product_type") == INVERSE_PERPETUAL
        with pytest.raises(KeyError, match="is ambiguous"):
            adapter.from_source("linear", group="product_type")


class TestNoCollision:
    """Internal and external values that are equal in Python must not overwrite each other."""

    def test_str_enum_equal_to_its_external_value(self):
        # StrEnum: Channel.orderbook == "orderbook"
        adapter = BaseAdapter(channel={Channel.orderbook: "orderbook"})
        external = adapter.to_source(Channel.orderbook, group="channel")
        assert external == "orderbook"
        assert type(external) is str
        assert adapter.from_source("orderbook", group="channel") is Channel.orderbook

    def test_int_enum_with_bool_external_values(self):
        # IntEnum: Side.BUY == 1 == True, e.g. Hyperliquid's is_buy
        adapter = BaseAdapter(side={Side.BUY: True, Side.SELL: False})
        assert adapter.to_source(Side.BUY, group="side") is True
        assert adapter.to_source(Side.SELL, group="side") is False
        assert adapter.from_source(True, group="side") is Side.BUY
        assert adapter.from_source(False, group="side") is Side.SELL

    def test_int_enum_with_int_external_values(self):
        adapter = BaseAdapter(side={Side.BUY: 1, Side.SELL: -1})
        assert adapter.to_source(Side.BUY, group="side") == 1
        assert adapter.from_source(-1, group="side") is Side.SELL


class TestSide:
    def test_alias_resolves_to_same_member(self):
        adapter = BaseAdapter(side={Side.BUY: "Buy"})
        assert adapter.to_source(Side.LONG, group="side") == "Buy"

    def test_str_keys_are_parsed_into_sides(self):
        adapter = BaseAdapter(side={"BUY": "Buy"})  # ty: ignore[invalid-argument-type]
        assert adapter.from_source("Buy", group="side") is Side.BUY

    def test_invalid_key_raises(self):
        with pytest.raises(pydantic.ValidationError):
            BaseAdapter(side={"HOLD": "Hold"})  # ty: ignore[invalid-argument-type]


class TestExternalValueTypes:
    @pytest.mark.parametrize("external", ["BTC", 0, True])
    def test_keeps_the_given_type(self, external: str | int | bool):
        # e.g. Hyperliquid refers to an asset by its int index
        adapter = BaseAdapter(asset={"BTC": external})
        assert type(adapter.to_source("BTC", group="asset")) is type(external)

    def test_rejects_non_scalar(self):
        with pytest.raises(pydantic.ValidationError):
            BaseAdapter(asset={"BTC": ["XBT"]})  # ty: ignore[invalid-argument-type]


class TestAddMapping:
    def test_both_directions(self):
        adapter = BaseAdapter()
        adapter.add_mapping("BTC_USDT_PERP", "BTCUSDT", group="product")
        assert adapter.to_source("BTC_USDT_PERP", group="product") == "BTCUSDT"
        assert adapter.from_source("BTCUSDT", group="product") == "BTC_USDT_PERP"

    def test_writes_to_the_field(self):
        adapter = BaseAdapter()
        adapter.add_mapping("BTC_USDT_PERP", "BTCUSDT", group="product")
        assert adapter.product == {"BTC_USDT_PERP": "BTCUSDT"}
        assert adapter.model_dump()["product"] == {"BTC_USDT_PERP": "BTCUSDT"}

    def test_remap_drops_old_external_value(self):
        adapter = BaseAdapter()
        adapter.add_mapping("BTC_USDT_PERP", "BTCUSDT", group="product")
        adapter.add_mapping("BTC_USDT_PERP", "BTC-PERP", group="product")
        assert adapter.to_source("BTC_USDT_PERP", group="product") == "BTC-PERP"
        assert adapter.from_source("BTC-PERP", group="product") == "BTC_USDT_PERP"
        with pytest.raises(KeyError):
            adapter.from_source("BTCUSDT", group="product", strict=True)

    def test_same_mapping_twice_is_not_ambiguous(self):
        adapter = BaseAdapter()
        adapter.add_mapping("BTC_USDT_PERP", "BTCUSDT", group="product")
        adapter.add_mapping("BTC_USDT_PERP", "BTCUSDT", group="product")
        assert adapter.from_source("BTCUSDT", group="product") == "BTC_USDT_PERP"

    def test_shared_external_value_becomes_ambiguous(self):
        adapter = BaseAdapter()
        adapter.add_mapping("BTC_USDT_PERP", "BTC", group="product")
        adapter.add_mapping("BTC_USDC_PERP", "BTC", group="product")
        with pytest.raises(KeyError, match="is ambiguous"):
            adapter.from_source("BTC", group="product")

    def test_extends_configured_group(self):
        adapter = BaseAdapter(channel={Channel.tradebook: "publicTrade"})
        adapter.add_mapping(Channel.orderbook, "orderbook", group="channel")
        assert adapter.to_source(Channel.tradebook, group="channel") == "publicTrade"
        assert adapter.from_source("orderbook", group="channel") is Channel.orderbook

    def test_unknown_group_raises(self):
        adapter = BaseAdapter()
        with pytest.raises(ValueError, match="unknown adapter group 'prodcut'"):
            adapter.add_mapping("BTC_USDT_PERP", "BTCUSDT", group="prodcut")  # ty: ignore[invalid-argument-type]

    def test_does_not_leak_into_other_instances(self):
        adapter = BaseAdapter()
        adapter.add_mapping("BTC_USDT_PERP", "BTCUSDT", group="product")
        assert BaseAdapter().product == {}


class TestValidation:
    def test_str_keys_are_parsed_into_enums(self):
        adapter = BaseAdapter(channel={"tradebook": "publicTrade"})  # ty: ignore[invalid-argument-type]
        assert adapter.to_source(Channel.tradebook, group="channel") == "publicTrade"

    def test_str_keys_are_parsed_into_product_types(self):
        adapter = BaseAdapter(product_type={"FUTURE-CRYPTO-PERPETUAL": "linear"})  # ty: ignore[invalid-argument-type]
        assert adapter.to_source(PERPETUAL, group="product_type") == "linear"

    @pytest.mark.parametrize("key", ["1m", Resolution("1m")])
    def test_channel_resolution_keys_are_coerced(self, key: str | Resolution):
        adapter = BaseAdapter(channel_resolution={key: "1"})
        assert adapter.to_source(Resolution("1m"), group="channel_resolution") == "1"
        assert adapter.from_source("1", group="channel_resolution") == Resolution("1m")

    def test_unknown_field_is_forbidden(self):
        with pytest.raises(pydantic.ValidationError):
            BaseAdapter(channels={Channel.tradebook: "publicTrade"})  # ty: ignore[unknown-argument]

    def test_invalid_key_raises(self):
        with pytest.raises(pydantic.ValidationError):
            BaseAdapter(option_type={"STRADDLE": "S"})  # ty: ignore[invalid-argument-type]


class TestProductHooks:
    """The defaults follow the product class's own conventions, a source overrides them."""

    def test_create_symbol_defaults_to_the_product_convention(self):
        # NOTE: model_validate since basis is a string here, parsed by ProductBasis's own validator
        crypto = CryptoProduct.model_validate(
            {"source": "DUMMY", "basis": "BTC_USDT_CRYPTO", "symbol": "_"}
        )
        future = FutureProduct.model_validate(
            {
                "source": "DUMMY",
                "basis": "BTC_USDT_FUT",
                "symbol": "_",
                "expiration": "2025-08-22",
            }
        )
        assert BaseAdapter().create_symbol(crypto) == "BTCUSDT"
        assert BaseAdapter().create_symbol(future) == "BTCQ25"

    def test_create_name_defaults_to_the_product_convention(self):
        product = CryptoProduct.model_validate(
            {"source": "DUMMY", "basis": "BTC_USDT_CRYPTO"}
        )
        assert BaseAdapter().create_name(product) == "DUMMY_BTCUSDT"
