from __future__ import annotations

import pytest

from pfund_blocks.enums.asset import AssetClass, AssetModifier, AssetType


class TestAssetType:
    @pytest.mark.parametrize(
        "alias, expected",
        [
            ("MF", AssetType.MUTUAL_FUND),
            ("FUND", AssetType.MUTUAL_FUND),
            ("FUT", AssetType.FUTURE),
            ("OPT", AssetType.OPTION),
        ],
    )
    def test_member_alias(self, alias: str, expected: AssetType):
        assert AssetType[alias] is expected

    def test_aliases_are_not_members(self):
        assert list(AssetType) == [
            AssetType.SPOT,
            AssetType.ETF,
            AssetType.MUTUAL_FUND,
            AssetType.FUTURE,
            AssetType.OPTION,
            AssetType.INDEX,
            AssetType.OUTCOME,
        ]

    def test_is_str(self):
        assert AssetType.FUTURE == "FUTURE"

    @pytest.mark.parametrize(
        "asset_type", [AssetType.SPOT, AssetType.ETF, AssetType.MUTUAL_FUND]
    )
    def test_is_spot(self, asset_type: AssetType):
        assert asset_type.is_spot()

    @pytest.mark.parametrize(
        "asset_type",
        [AssetType.FUTURE, AssetType.OPTION, AssetType.INDEX, AssetType.OUTCOME],
    )
    def test_is_not_spot(self, asset_type: AssetType):
        assert not asset_type.is_spot()


class TestAssetClass:
    @pytest.mark.parametrize(
        "alias, expected",
        [("FX", AssetClass.FOREX), ("CMDTY", AssetClass.COMMODITY)],
    )
    def test_member_alias(self, alias: str, expected: AssetClass):
        assert AssetClass[alias] is expected

    def test_aliases_are_not_members(self):
        assert list(AssetClass) == [
            AssetClass.EQUITY,
            AssetClass.BOND,
            AssetClass.FOREX,
            AssetClass.CRYPTO,
            AssetClass.COMMODITY,
        ]


class TestAssetModifier:
    @pytest.mark.parametrize(
        "alias, expected",
        [
            ("INV", AssetModifier.INVERSE),
            ("PERP", AssetModifier.PERPETUAL),
            ("LEV", AssetModifier.LEVERAGED),
        ],
    )
    def test_member_alias(self, alias: str, expected: AssetModifier):
        assert AssetModifier[alias] is expected

    def test_members(self):
        assert list(AssetModifier) == [
            AssetModifier.INVERSE,
            AssetModifier.PERPETUAL,
            AssetModifier.SHORT,
            AssetModifier.LEVERAGED,
        ]

    @pytest.mark.parametrize("modifier", list(AssetModifier))
    def test_declared_member_has_no_leverage(self, modifier: AssetModifier):
        assert modifier.leverage is None

    @pytest.mark.parametrize("modifier", list(AssetModifier))
    def test_declared_member_base_is_itself(self, modifier: AssetModifier):
        assert modifier.base is modifier

    @pytest.mark.parametrize(
        "modifier, expected",
        [
            (AssetModifier.INVERSE, {AssetType.FUTURE, AssetType.OPTION}),
            (AssetModifier.PERPETUAL, {AssetType.FUTURE}),
            (AssetModifier.SHORT, {AssetType.ETF}),
            (AssetModifier.LEVERAGED, {AssetType.ETF}),
        ],
    )
    def test_supported_asset_types(
        self, modifier: AssetModifier, expected: set[AssetType]
    ):
        assert modifier.supported_asset_types == expected


class TestLeverage:
    def test_leverage_modifier(self):
        modifier = AssetModifier("3x")
        assert modifier == "3X"
        assert modifier.leverage == 3.0
        assert modifier.name == "LEVERAGED_3X"
        assert modifier.base is AssetModifier.LEVERAGED

    def test_uses_leveraged_supported_asset_types(self):
        assert AssetModifier("3x").supported_asset_types == {AssetType.ETF}

    @pytest.mark.parametrize("value", ["3X", "3.0x", "3.00X", "03x"])
    def test_same_leverage_is_the_same_modifier(self, value: str):
        assert AssetModifier(value) is AssetModifier("3x")

    def test_fractional_leverage(self):
        modifier = AssetModifier("1.5x")
        assert modifier == "1.5X"
        assert modifier.leverage == 1.5

    @pytest.mark.parametrize(
        "value, expected, leverage",
        [
            ("1.50x", "1.5X", 1.5),
            ("100.10x", "100.1X", 100.1),
            ("0.25x", "0.25X", 0.25),
            # no exponent form or lost digits, unlike f"{leverage:g}"
            ("1000000x", "1000000X", 1000000.0),
            ("12345.67x", "12345.67X", 12345.67),
        ],
    )
    def test_normalized_value_is_exact(
        self, value: str, expected: str, leverage: float
    ):
        modifier = AssetModifier(value)
        assert modifier == expected
        assert modifier.leverage == leverage

    @pytest.mark.parametrize("value", ["1.123x", "0.001x", "3.000x"])
    def test_more_than_two_decimal_places_raises(self, value: str):
        with pytest.raises(ValueError, match="at most 2 decimal places"):
            AssetModifier(value)

    def test_different_leverage_is_a_different_modifier(self):
        assert AssetModifier("2x") is not AssetModifier("3x")

    def test_is_not_a_declared_member(self):
        assert AssetModifier("3x") not in list(AssetModifier)

    @pytest.mark.parametrize("value", ["0x", "0.0X", "00x"])
    def test_zero_leverage_raises(self, value: str):
        with pytest.raises(ValueError):
            AssetModifier(value)

    @pytest.mark.parametrize(
        "value", ["", "x", "3", "-3x", "3xx", "x3", "1e3x", ".5x", "3.x", 3, 3.0, None]
    )
    def test_invalid_value_raises(self, value: object):
        with pytest.raises(ValueError):
            AssetModifier(value)
