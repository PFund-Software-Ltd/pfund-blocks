from __future__ import annotations

import pydantic
import pytest

from pfund_blocks.entities.products.product_basis import ProductBasis
from pfund_blocks.entities.products.product_type import ProductType


def parse(basis: str) -> ProductBasis:
    return ProductBasis.model_validate(basis)


class TestParsing:
    @pytest.mark.parametrize(
        "basis, base_asset, quote_asset, product_type",
        [
            ("AAPL_USD_STK", "AAPL", "USD", "SPOT-EQUITY"),
            ("BTC_USDT_PERP", "BTC", "USDT", "FUTURE-PERPETUAL"),
            (
                "BTC_USD_FUTURE-CRYPTO-INVERSE-PERPETUAL",
                "BTC",
                "USD",
                "FUTURE-CRYPTO-INVERSE-PERPETUAL",
            ),
            ("SQQQ_USD_ETF-EQUITY-SHORT-3x", "SQQQ", "USD", "ETF-EQUITY-SHORT-3x"),
            ("ELECTION_USD_OUTCOME", "ELECTION", "USD", "OUTCOME"),
        ],
    )
    def test_parse(
        self, basis: str, base_asset: str, quote_asset: str, product_type: str
    ):
        product_basis = parse(basis)
        assert product_basis.base_asset == base_asset
        assert product_basis.quote_asset == quote_asset
        assert product_basis.product_type == ProductType.model_validate(product_type)

    def test_product_type_can_contain_underscore(self):
        # MUTUAL_FUND contains "_", the separator of a product basis
        product_basis = parse("VFIAX_USD_MUTUAL_FUND-EQUITY")
        assert product_basis.base_asset == "VFIAX"
        assert product_basis.quote_asset == "USD"
        assert product_basis.product_type.canonical == "MUTUAL_FUND-EQUITY"

    def test_is_case_insensitive(self):
        assert parse("btc_usdt_perp") == parse("BTC_USDT_PERP")
        assert parse("btc_usdt_perp").base_asset == "BTC"

    def test_fields_are_case_insensitive(self):
        product_basis = ProductBasis(
            base_asset="btc",
            quote_asset="usdt",
            product_type="perp",  # ty: ignore[invalid-argument-type]
        )
        assert product_basis == parse("BTC_USDT_PERP")

    @pytest.mark.parametrize("asset", ["BRK.B", "1000PEPE"])
    def test_asset_allows_digits_and_dots(self, asset: str):
        assert parse(f"{asset}_USD_STK").base_asset == asset

    def test_from_fields(self):
        product_basis = ProductBasis(
            base_asset="BTC",
            quote_asset="USDT",
            product_type="PERP",  # ty: ignore[invalid-argument-type]
        )
        assert product_basis == parse("BTC_USDT_PERP")

    @pytest.mark.parametrize("basis", ["BTC", "BTC_USDT", ""])
    def test_missing_parts_raises(self, basis: str):
        with pytest.raises(pydantic.ValidationError, match="invalid product basis"):
            parse(basis)

    @pytest.mark.parametrize(
        "basis",
        [
            "_USDT_PERP",  # empty base asset
            "BTC__PERP",  # empty quote asset
            "B-TC_USDT_PERP",  # "-" is the product type separator
            "BTC/USDT_USD_STK",
        ],
    )
    def test_invalid_asset_raises(self, basis: str):
        with pytest.raises(pydantic.ValidationError, match="should match pattern"):
            parse(basis)

    @pytest.mark.parametrize(
        "basis, match",
        [
            ("BTC_USDT_", "unknown part ''"),
            ("BTC_USDT_FOO", "unknown part 'FOO'"),
            # aliases use "-" inside a product basis, e.g. INVERSE-PERPETUAL
            ("BTC_USD_INVERSE_PERPETUAL", "unknown part 'INVERSE_PERPETUAL'"),
        ],
    )
    def test_invalid_product_type_raises(self, basis: str, match: str):
        with pytest.raises(pydantic.ValidationError, match=match):
            parse(basis)

    def test_extra_field_raises(self):
        with pytest.raises(pydantic.ValidationError, match="Extra inputs"):
            ProductBasis(
                base_asset="BTC",
                quote_asset="USDT",
                product_type="PERP",  # ty: ignore[invalid-argument-type]
                symbol="BTCUSDT",  # ty: ignore[unknown-argument]
            )


class TestStrings:
    @pytest.mark.parametrize(
        "basis, expected",
        [
            ("btc_usdt_perp", "BTC_USDT_PERPETUAL"),
            ("AAPL_USD_SPOT-EQUITY", "AAPL_USD_STOCK"),
            ("BTC_USD_IPERP", "BTC_USD_INVERSE-PERPETUAL"),
            ("BTC_USDT_FUTURE-CRYPTO-PERPETUAL", "BTC_USDT_FUTURE-CRYPTO-PERPETUAL"),
            ("TQQQ_USD_ETF-EQUITY-3.0X", "TQQQ_USD_ETF-EQUITY-3x"),
        ],
    )
    def test_str_is_friendly(self, basis: str, expected: str):
        assert str(parse(basis)) == expected

    @pytest.mark.parametrize(
        "basis, expected",
        [
            ("BTC_USDT_PERP", "ProductBasis(BTC_USDT_FUTURE-PERPETUAL)"),
            ("AAPL_USD_STK", "ProductBasis(AAPL_USD_SPOT-EQUITY)"),
            ("BTC_USD_IPERP", "ProductBasis(BTC_USD_FUTURE-INVERSE-PERPETUAL)"),
        ],
    )
    def test_repr_is_canonical(self, basis: str, expected: str):
        assert repr(parse(basis)) == expected

    @pytest.mark.parametrize(
        "basis", ["btc_usdt_perp", "AAPL_USD_STK", "VFIAX_USD_MUTUAL_FUND-EQUITY"]
    )
    def test_str_round_trips(self, basis: str):
        product_basis = parse(basis)
        assert parse(str(product_basis)) == product_basis

    def test_asset_pair(self):
        assert parse("BTC_USDT_PERP").asset_pair == "BTC_USDT"


class TestEquality:
    def test_alias_equals_expanded_form(self):
        assert parse("BTC_USDT_PERP") == parse("BTC_USDT_FUTURE-PERPETUAL")
        assert hash(parse("BTC_USDT_PERP")) == hash(parse("BTC_USDT_FUTURE-PERPETUAL"))

    def test_same_pair_different_product_type_is_not_equal(self):
        # e.g. Bybit's BTCUSDT is both a spot pair and a perpetual
        assert parse("BTC_USDT_CRYPTO") != parse("BTC_USDT_PERP")

    def test_usable_as_dict_key(self):
        bases = {parse("BTC_USDT_PERP"): 1}
        assert bases[parse("btc_usdt_future-perpetual")] == 1

    def test_is_frozen(self):
        product_basis = parse("BTC_USDT_PERP")
        with pytest.raises(pydantic.ValidationError, match="frozen"):
            product_basis.base_asset = "ETH"  # ty: ignore[invalid-assignment]


class TestSerialization:
    def test_dict_round_trip(self):
        product_basis = parse("BTC_USD_IPERP")
        assert ProductBasis.model_validate(product_basis.model_dump()) == product_basis

    def test_json_round_trip(self):
        product_basis = parse("SQQQ_USD_ETF-EQUITY-SHORT-3x")
        assert (
            ProductBasis.model_validate_json(product_basis.model_dump_json())
            == product_basis
        )

    def test_nested_string_is_parsed(self):
        # a string is accepted wherever a ProductBasis is expected
        class Holder(pydantic.BaseModel):
            basis: ProductBasis

        holder = Holder.model_validate({"basis": "BTC_USDT_PERP"})
        assert holder.basis == parse("BTC_USDT_PERP")
