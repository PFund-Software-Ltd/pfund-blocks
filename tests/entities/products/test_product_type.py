from __future__ import annotations

import pydantic
import pytest

from pfund_blocks.entities.products.product_type import ProductType, ProductTypeAlias
from pfund_blocks.enums.asset import AssetClass, AssetModifier, AssetType


def parse(product_type: str) -> ProductType:
    return ProductType.model_validate(product_type)


ALL_ALIASES = [
    (name.replace("_", "-"), alias)
    for name, alias in ProductTypeAlias.__members__.items()
]


class TestParsing:
    @pytest.mark.parametrize(
        "product_type, asset_type, asset_class, modifiers",
        [
            ("SPOT-EQUITY", AssetType.SPOT, AssetClass.EQUITY, ()),
            ("ETF-COMMODITY", AssetType.ETF, AssetClass.COMMODITY, ()),
            ("MUTUAL_FUND-BOND", AssetType.MUTUAL_FUND, AssetClass.BOND, ()),
            (
                "FUTURE-CRYPTO-PERPETUAL",
                AssetType.FUTURE,
                AssetClass.CRYPTO,
                (AssetModifier.PERPETUAL,),
            ),
            ("OPTION-EQUITY", AssetType.OPTION, AssetClass.EQUITY, ()),
            ("INDEX-EQUITY", AssetType.INDEX, AssetClass.EQUITY, ()),
            ("OUTCOME", AssetType.OUTCOME, None, ()),
        ],
    )
    def test_parse(
        self,
        product_type: str,
        asset_type: AssetType,
        asset_class: AssetClass | None,
        modifiers: tuple[AssetModifier, ...],
    ):
        ptype = parse(product_type)
        assert ptype.asset_type is asset_type
        assert ptype.asset_class is asset_class
        assert ptype.modifiers == modifiers

    def test_is_case_insensitive(self):
        assert parse("future-crypto-perpetual") == parse("FUTURE-CRYPTO-PERPETUAL")

    def test_token_order_does_not_matter(self):
        assert parse("PERPETUAL-CRYPTO-FUTURE") == parse("FUTURE-CRYPTO-PERPETUAL")

    @pytest.mark.parametrize(
        "product_type, expected",
        [
            ("FUT-CRYPTO-PERP", "FUTURE-CRYPTO-PERPETUAL"),
            ("MF-FX", "MUTUAL_FUND-FOREX"),
            ("OPT-CMDTY-INV", "OPTION-COMMODITY-INVERSE"),
            ("ETF-EQUITY-LEV", "ETF-EQUITY-LEVERAGED"),
        ],
    )
    def test_token_aliases(self, product_type: str, expected: str):
        assert parse(product_type) == parse(expected)

    @pytest.mark.parametrize(
        "product_type, expected",
        [
            ("FUTURE-FUT", "FUTURE"),
            ("SPOT-FX-FOREX", "SPOT-FOREX"),
            ("FUTURE-PERP-PERPETUAL", "FUTURE-PERPETUAL"),
        ],
    )
    def test_repeated_tokens_are_deduped(self, product_type: str, expected: str):
        assert parse(product_type) == parse(expected)

    def test_from_fields(self):
        ptype = ProductType(
            asset_type=AssetType.FUTURE,
            asset_class=AssetClass.CRYPTO,
            modifiers=(AssetModifier.PERPETUAL,),
        )
        assert ptype == parse("FUTURE-CRYPTO-PERPETUAL")

    def test_string_is_accepted_as_a_field(self):
        class Holder(pydantic.BaseModel):
            product_type: ProductType

        assert Holder(product_type="PERP").product_type == parse("FUTURE-PERPETUAL")  # ty: ignore[invalid-argument-type]

    @pytest.mark.parametrize(
        "product_type, match",
        [
            ("", "unknown part"),
            ("SPOT-EQUITY-FOO", "unknown part 'FOO'"),
            # "_" separates the parts of a product basis, not the tokens of a product type
            ("FUTURE_CRYPTO", "unknown part"),
            ("INVERSE_PERPETUAL", "unknown part"),
            # an alias must be the whole product type
            ("STK-EQUITY", "unknown part 'STK'"),
            ("EQUITY", "exactly one asset type"),
            ("SPOT-FUTURE", "exactly one asset type"),
            ("FUTURE-OPTION", "exactly one asset type"),
            ("SPOT-CRYPTO-FX", "at most one asset class"),
        ],
    )
    def test_invalid_raises(self, product_type: str, match: str):
        with pytest.raises(ValueError, match=match):
            parse(product_type)

    def test_is_frozen(self):
        ptype = parse("STOCK")
        with pytest.raises(pydantic.ValidationError):
            ptype.asset_type = AssetType.ETF  # ty: ignore[invalid-assignment]

    def test_extra_field_is_forbidden(self):
        with pytest.raises(pydantic.ValidationError):
            ProductType(asset_type=AssetType.SPOT, foo="bar")  # ty: ignore[unknown-argument]


class TestAliases:
    @pytest.mark.parametrize("name, alias", ALL_ALIASES)
    def test_alias_resolves(self, name: str, alias: ProductTypeAlias):
        assert parse(name) == parse("-".join(alias.value))

    @pytest.mark.parametrize(
        "alias, expected",
        [
            ("STK", "SPOT-EQUITY"),
            ("FX", "SPOT-FOREX"),
            ("CMDTY", "SPOT-COMMODITY"),
            ("PERP", "FUTURE-PERPETUAL"),
            ("IPERP", "FUTURE-INVERSE-PERPETUAL"),
            ("IFUT", "FUTURE-INVERSE"),
        ],
    )
    def test_short_alias(self, alias: str, expected: str):
        assert parse(alias) == parse(expected)

    def test_alias_is_case_insensitive(self):
        assert parse("stk") == parse("STOCK")
        assert parse("inverse-perpetual") == parse("INVERSE-PERPETUAL")

    def test_alias_equals_expanded_form(self):
        assert parse("PERP") == parse("PERPETUAL-FUTURE")

    def test_alias_without_asset_class_differs_from_one_with_it(self):
        # known limitation: PERP has no asset class, so it is not FUTURE-CRYPTO-PERPETUAL
        assert parse("PERP") != parse("FUTURE-CRYPTO-PERPETUAL")


class TestModifiers:
    def test_sorted_in_declaration_order(self):
        ptype = parse("FUTURE-PERPETUAL-INVERSE")
        assert ptype.modifiers == (AssetModifier.INVERSE, AssetModifier.PERPETUAL)

    def test_short_sorts_before_leverage(self):
        # e.g. SQQQ
        ptype = parse("ETF-EQUITY-3x-SHORT")
        assert ptype.modifiers == (AssetModifier.SHORT, AssetModifier("3x"))
        assert ptype.canonical == "ETF-EQUITY-SHORT-3x"

    def test_deduped_when_built_from_fields(self):
        ptype = ProductType(
            asset_type=AssetType.FUTURE,
            modifiers=(AssetModifier.PERPETUAL, AssetModifier.PERPETUAL),
        )
        assert ptype.modifiers == (AssetModifier.PERPETUAL,)

    @pytest.mark.parametrize(
        "product_type",
        [
            "SPOT-PERPETUAL",
            "OPTION-PERPETUAL",
            "SPOT-INVERSE",
            "ETF-INVERSE",
            "FUTURE-LEVERAGED",
            "SPOT-EQUITY-SHORT",
            "FUTURE-SHORT",
            "SPOT-EQUITY-3x",
        ],
    )
    def test_unsupported_asset_type_raises(self, product_type: str):
        with pytest.raises(ValueError, match="is not supported for"):
            parse(product_type)

    @pytest.mark.parametrize("product_type", ["FUTURE-INVERSE", "OPTION-INVERSE"])
    def test_inverse_is_supported_for_future_and_option(self, product_type: str):
        assert parse(product_type).is_inverse()


class TestLeverage:
    def test_leverage_modifier(self):
        ptype = parse("ETF-EQUITY-3x")
        (modifier,) = ptype.modifiers
        assert modifier.leverage == 3.0
        assert modifier.base is AssetModifier.LEVERAGED

    def test_same_leverage_is_the_same_modifier(self):
        assert parse("ETF-3x").modifiers[0] is parse("ETF-3.0X").modifiers[0]

    def test_fractional_leverage(self):
        assert parse("ETF-1.5x").modifiers[0].leverage == 1.5

    def test_plain_leveraged_has_no_number(self):
        assert parse("ETF-LEVERAGED").modifiers[0].leverage is None

    @pytest.mark.parametrize(
        "product_type, match",
        [
            ("ETF-0x", "'0X' is not a valid AssetModifier"),
            ("ETF-0.0x", "'0.0X' is not a valid AssetModifier"),
            ("ETF-3", "'3' is not a valid AssetModifier"),
            ("ETF-x", "unknown part 'X'"),
            ("ETF-1.123x", "at most 2 decimal places"),
        ],
    )
    def test_invalid_leverage_raises(self, product_type: str, match: str):
        with pytest.raises(ValueError, match=match):
            parse(product_type)

    @pytest.mark.parametrize("product_type", ["ETF-3x-2x", "ETF-LEVERAGED-3x"])
    def test_only_one_leverage_allowed(self, product_type: str):
        with pytest.raises(ValueError, match="only one leverage modifier"):
            parse(product_type)

    def test_same_leverage_twice_is_deduped(self):
        assert parse("ETF-3x-3.0x") == parse("ETF-3x")


class TestStrings:
    @pytest.mark.parametrize(
        "product_type, canonical",
        [
            ("STK", "SPOT-EQUITY"),
            ("PERPETUAL-FUTURE-CRYPTO", "FUTURE-CRYPTO-PERPETUAL"),
            ("IPERP", "FUTURE-INVERSE-PERPETUAL"),
            ("ETF-EQUITY-3.0x", "ETF-EQUITY-3x"),
            ("ETF-EQUITY-SHORT", "ETF-EQUITY-SHORT"),
            ("ETF-1.5X", "ETF-1.5x"),
            ("ETF-1000000x", "ETF-1000000x"),
            ("MF-BOND", "MUTUAL_FUND-BOND"),
            ("OUTCOME", "OUTCOME"),
        ],
    )
    def test_canonical(self, product_type: str, canonical: str):
        assert parse(product_type).canonical == canonical

    def test_canonical_round_trips(self):
        ptype = parse("ETF-EQUITY-3x")
        assert parse(ptype.canonical) == ptype

    def test_repr_is_canonical(self):
        assert repr(parse("STK")) == "ProductType(SPOT-EQUITY)"

    @pytest.mark.parametrize(
        "product_type, expected",
        [
            # the preferred alias name is used, e.g. STOCK over STK
            ("SPOT-EQUITY", "STOCK"),
            ("STK", "STOCK"),
            ("FX", "FOREX"),
            ("CMDTY", "COMMODITY"),
            ("PERP", "PERPETUAL"),
            ("FUTURE-INVERSE-PERPETUAL", "INVERSE-PERPETUAL"),
            ("IFUT", "INVERSE-FUTURE"),
            # no alias, falls back to the canonical form
            ("FUTURE-CRYPTO-PERPETUAL", "FUTURE-CRYPTO-PERPETUAL"),
            ("ETF-EQUITY-3x", "ETF-EQUITY-3x"),
        ],
    )
    def test_str_is_friendly(self, product_type: str, expected: str):
        assert str(parse(product_type)) == expected

    @pytest.mark.parametrize("name, _alias", ALL_ALIASES)
    def test_str_round_trips(self, name: str, _alias: ProductTypeAlias):
        ptype = parse(name)
        assert parse(str(ptype)) == ptype


class TestEquality:
    def test_equal_product_types_have_equal_hashes(self):
        assert hash(parse("STK")) == hash(parse("SPOT-EQUITY"))

    def test_usable_as_dict_key(self):
        assert {parse("PERP"): 1}[parse("FUTURE-PERPETUAL")] == 1

    def test_different_leverage_is_not_equal(self):
        assert parse("ETF-3x") != parse("ETF-2x")


class TestPredicates:
    @pytest.mark.parametrize(
        "product_type, predicate",
        [
            ("ETF-EQUITY", "is_etf"),
            ("MF-BOND", "is_mutual_fund"),
            ("FUTURE-CRYPTO", "is_future"),
            ("OPTION-EQUITY", "is_option"),
            ("INDEX-EQUITY", "is_index"),
            ("OUTCOME", "is_outcome"),
            ("IFUT", "is_inverse"),
            ("PERP", "is_perpetual"),
            ("ETF-EQUITY-3x", "is_leveraged"),
            ("ETF-EQUITY-LEVERAGED", "is_leveraged"),
            ("ETF-EQUITY-SHORT", "is_short"),
            ("ETF-EQUITY-SHORT-3x", "is_short"),
            ("STK", "is_stock"),
            ("BOND", "is_bond"),
            ("FX", "is_forex"),
            ("CRYPTO", "is_crypto_spot"),
            ("CMDTY", "is_commodity_spot"),
        ],
    )
    def test_predicate_is_true(self, product_type: str, predicate: str):
        assert getattr(parse(product_type), predicate)()

    @pytest.mark.parametrize(
        "product_type, predicate",
        [
            ("SPOT-EQUITY", "is_etf"),
            ("FUTURE-CRYPTO", "is_perpetual"),
            ("PERP", "is_inverse"),
            ("ETF-EQUITY", "is_leveraged"),
            ("ETF-EQUITY", "is_short"),
            # leveraged long, e.g. TQQQ
            ("ETF-EQUITY-3x", "is_short"),
            # spot + asset class only, not exposure, e.g. a bond ETF is not a bond
            ("ETF-BOND", "is_bond"),
            ("ETF-EQUITY", "is_stock"),
            ("FUTURE-CRYPTO-PERPETUAL", "is_crypto_spot"),
            ("FUTURE-FOREX", "is_forex"),
            ("ETF-COMMODITY", "is_commodity_spot"),
            ("SPOT", "is_stock"),
        ],
    )
    def test_predicate_is_false(self, product_type: str, predicate: str):
        assert not getattr(parse(product_type), predicate)()
