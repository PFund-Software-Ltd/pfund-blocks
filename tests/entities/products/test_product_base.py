from __future__ import annotations

import pydantic
import pytest

from pfund_blocks.entities.products.product_base import BaseProduct, ProductKey
from pfund_blocks.entities.products.product_basis import ProductBasis
from pfund_blocks.entities.products.product_type import ProductType


class DerivedSymbolProduct(BaseProduct):
    def _create_symbol(self) -> str:
        return f"{self.base_asset}{self.quote_asset}"


class SpecProduct(BaseProduct):
    strike_price: float
    style: str = "EUROPEAN"


OPTION = {
    "source": "BYBIT",
    "basis": "BTC_USDT_OPTION-CRYPTO",
    "symbol": "BTC-26DEC26-100000-C",
}


def create(basis: str = "BTC_USDT_PERP", **kwargs: object) -> DerivedSymbolProduct:
    # NOTE: model_validate since basis is a string here, parsed by ProductBasis's own validator
    return DerivedSymbolProduct.model_validate(
        {"source": "BYBIT", "basis": basis, **kwargs}
    )


class TestSymbolAndName:
    def test_symbol_is_derived(self):
        assert create().symbol == "BTCUSDT"

    def test_explicit_symbol_is_kept(self):
        assert create(symbol="BTC-PERP").symbol == "BTC-PERP"

    def test_symbol_is_required_without_override(self):
        with pytest.raises(pydantic.ValidationError, match="symbol is required"):
            BaseProduct.model_validate(
                {"source": "HYPERLIQUID", "basis": "HYPE_USDC_CRYPTO"}
            )

    def test_base_product_with_symbol(self):
        product = BaseProduct.model_validate(
            {"source": "HYPERLIQUID", "basis": "HYPE_USDC_CRYPTO", "symbol": "HYPE"}
        )
        assert product.symbol == "HYPE"
        assert product.name == "HYPERLIQUID_HYPE"

    def test_name_is_derived(self):
        assert create().name == "BYBIT_BTCUSDT"

    def test_name_uses_explicit_symbol(self):
        assert create(symbol="BTC-PERP").name == "BYBIT_BTC-PERP"

    def test_explicit_name_is_kept(self):
        assert create(name="my_btc").name == "my_btc"

    def test_source_and_exchange_are_uppercased(self):
        product = create(source="bybit", exchange="bybit")
        assert product.source == product.exchange == "BYBIT"
        assert product.name == "BYBIT_BTCUSDT"
        assert product == create(exchange="BYBIT")

    def test_extra_field_raises(self):
        with pytest.raises(pydantic.ValidationError, match="Extra inputs"):
            create(strike_price=100)

    def test_is_frozen(self):
        product = create()
        with pytest.raises(pydantic.ValidationError, match="frozen"):
            product.symbol = "ETHUSDT"  # ty: ignore[invalid-assignment]


class TestBasis:
    def test_basis_string_is_parsed(self):
        assert create().basis == ProductBasis.model_validate("BTC_USDT_PERP")

    def test_basis_properties(self):
        product = create()
        assert product.base_asset == product.base == "BTC"
        assert product.quote_asset == product.quote == "USDT"
        assert product.asset_pair == "BTC_USDT"
        assert (
            product.product_type == product.type == ProductType.model_validate("PERP")
        )

    def test_key(self):
        key = create().key
        assert key == ProductKey(
            symbol="BTCUSDT", product_type=ProductType.model_validate("PERP")
        )
        assert str(key) == "BTCUSDT.PERPETUAL"

    def test_same_symbol_different_product_type_has_different_key(self):
        # e.g. Bybit's BTCUSDT is both a spot pair and a perpetual
        assert create("BTC_USDT_CRYPTO").key != create("BTC_USDT_PERP").key


class TestSpecs:
    def test_base_product_has_no_specs(self):
        assert BaseProduct.get_allowed_specs() == set()
        assert BaseProduct.get_required_specs() == set()
        assert create().specs == {}

    def test_allowed_and_required_specs(self):
        assert SpecProduct.get_allowed_specs() == {"strike_price", "style"}
        assert SpecProduct.get_required_specs() == {"strike_price"}

    def test_specs_are_sorted_by_name(self):
        product = SpecProduct.model_validate({**OPTION, "strike_price": 100})
        assert product.specs == {"strike_price": 100.0, "style": "EUROPEAN"}
        assert list(product.specs) == ["strike_price", "style"]

    def test_missing_required_spec_raises(self):
        with pytest.raises(pydantic.ValidationError, match="strike_price"):
            SpecProduct.model_validate(OPTION)


class TestStringsAndSerialization:
    def test_str(self):
        assert (
            str(create())
            == "BYBIT BTC_USDT_PERPETUAL (symbol=BTCUSDT, name=BYBIT_BTCUSDT)"
        )

    def test_dict_round_trip(self):
        product = create()
        assert DerivedSymbolProduct.model_validate(product.to_dict()) == product

    def test_json_round_trip(self):
        product = create("SQQQ_USD_ETF-EQUITY-SHORT-3x")
        assert DerivedSymbolProduct.model_validate_json(product.to_json()) == product


class TestEquality:
    def test_alias_basis_is_equal(self):
        assert create("BTC_USDT_PERP") == create("BTC_USDT_FUTURE-PERPETUAL")
        assert hash(create("BTC_USDT_PERP")) == hash(
            create("BTC_USDT_FUTURE-PERPETUAL")
        )

    def test_different_source_is_not_equal(self):
        binance_product = DerivedSymbolProduct.model_validate(
            {"source": "BINANCE", "basis": "BTC_USDT_PERP"}
        )
        assert create() != binance_product


class TestPredicates:
    @pytest.mark.parametrize(
        "method",
        [
            "is_etf",
            "is_mutual_fund",
            "is_future",
            "is_option",
            "is_index",
            "is_outcome",
            "is_inverse",
            "is_perpetual",
            "is_leveraged",
            "is_short",
            "is_stock",
            "is_bond",
            "is_forex",
            "is_crypto_spot",
            "is_commodity_spot",
        ],
    )
    @pytest.mark.parametrize(
        "basis",
        [
            "AAPL_USD_STK",
            "TLT_USD_ETF-BOND",
            "SQQQ_USD_ETF-EQUITY-SHORT-3x",
            "VFIAX_USD_MUTUAL_FUND-EQUITY",
            "BTC_USD_IPERP",
            "AAPL_USD_OPTION-EQUITY",
            "SPX_USD_INDEX-EQUITY",
            "ELECTION_USD_OUTCOME",
            "EUR_USD_FX",
            "BTC_USDT_CRYPTO",
            "XAU_USD_CMDTY",
            "US10Y_USD_BOND",
        ],
    )
    def test_shortcut_matches_product_type(self, method: str, basis: str):
        product = create(basis)
        assert getattr(product, method)() == getattr(product.product_type, method)()

    def test_shortcuts_are_true_for_their_product(self):
        assert create("BTC_USD_IPERP").is_inverse()
        assert create("BTC_USD_IPERP").is_perpetual()
        assert create("SQQQ_USD_ETF-EQUITY-SHORT-3x").is_short()
        assert create("SQQQ_USD_ETF-EQUITY-SHORT-3x").is_leveraged()
        assert create("AAPL_USD_STK").is_stock()

    def test_aliases(self):
        assert create("BTC_USDT_PERP").is_perp()
        assert create("EUR_USD_FX").is_fx()
        assert not create("BTC_USDT_CRYPTO").is_perp()
        assert not create("BTC_USDT_CRYPTO").is_fx()
