"""Product type: what a product is.

A product basis is {base_asset}_{quote_asset}_{product_type}, and the product type is the part that
tells you what kind of product you are looking at. It combines three parts:
    - AssetType: what contract is held, e.g. SPOT, ETF, FUTURE, OPTION
    - AssetClass: what it gives exposure to, e.g. EQUITY, CRYPTO, COMMODITY
    - AssetModifier: qualifiers that make a variant of the asset type, e.g. INVERSE, PERPETUAL

e.g. a perpetual future on crypto is FUTURE + CRYPTO + PERPETUAL, a gold ETF like GLD is ETF + COMMODITY.

Expanding product_type, the full form of a product basis is:
    {base_asset}_{quote_asset}_{asset_type}-{asset_class}-{asset_modifier}
e.g. AAPL_USD_SPOT-EQUITY, BTC_USDT_FUTURE-CRYPTO-PERPETUAL
Inside product_type, "-" is the separator since "_" already separates the basis.

Since the full form is too long to write, product type aliases are supported,
e.g. STOCK/STK = SPOT + EQUITY, so AAPL_USD_SPOT-EQUITY can be written as AAPL_USD_STK.

Product type only answers "what type is it". Details of a specific product, e.g. expiration, strike,
delivery, are product specs and belong to the product, not here.
"""

from typing import Self

import re
from enum import StrEnum


class AssetType(StrEnum):
    """What kind of contract is held, e.g. owning the asset directly (SPOT) or via a fund (ETF, MUTUAL_FUND), or a derivative on it."""

    SPOT = "SPOT"
    ETF = "ETF"  # exchange-traded fund
    MUTUAL_FUND = MF = FUND = "MUTUAL_FUND"
    FUTURE = FUT = "FUTURE"
    OPTION = OPT = "OPTION"
    INDEX = "INDEX"  # reference only, not tradable
    OUTCOME = "OUTCOME"  # prediction market event contract

    def is_spot(self) -> bool:
        """Whether the asset is owned outright, i.e. SPOT, including fund units (ETF, MUTUAL_FUND)."""
        return self in (AssetType.SPOT, AssetType.ETF, AssetType.MUTUAL_FUND)


class AssetClass(StrEnum):
    """What the asset gives exposure to, e.g. a SPOT EQUITY is a stock, an ETF COMMODITY is e.g. GLD."""

    EQUITY = "EQUITY"
    BOND = "BOND"
    FOREX = FX = "FOREX"
    CRYPTO = "CRYPTO"
    COMMODITY = CMDTY = "COMMODITY"


class AssetModifier(StrEnum):
    """Qualifies an asset type into a variant of it, e.g. PERPETUAL-FUTURE, INVERSE-PERPETUAL-FUTURE.

    LEVERAGED is ONLY for product-level leverage, i.e. a FIXED leverage built into the product,
    e.g. TQQQ (3x Nasdaq ETF).
    It is NOT position-level leverage, i.e. the leverage traders set, change or calculate on futures,
    options, margin accounts etc., e.g. trading a BTC perpetual at 10x is a position (or account) setting,
    the product itself stays the same.
    Never put position-level leverage here, otherwise the same contract would become different products.

    Leverage can be written with its number, e.g. AssetModifier("3x") creates a LEVERAGED modifier
    with value "3X" and leverage 3.0. It is not a declared member, so use `base` (LEVERAGED) for
    member-level logic such as ordering and supported asset types.
    """

    INVERSE = INV = "INVERSE"
    PERPETUAL = PERP = "PERPETUAL"  # future without expiration
    # product-level leverage ONLY (e.g. TQQQ), NOT position-level leverage, see docstring
    LEVERAGED = LEV = "LEVERAGED"

    _leverage: float  # only set on leveraged modifiers created by _missing_, e.g. "3x"

    @classmethod
    def _missing_(cls, value: object) -> Self | None:
        """Create a leveraged modifier on the fly for values like "3x" or "1.5X"."""
        if not isinstance(value, str):
            return None
        match = re.fullmatch(r"(\d+(?:\.\d+)?)X", value.upper())
        if not match:
            return None
        leverage = float(match.group(1))
        # e.g. "0x", a product can't have zero leverage
        if leverage <= 0:
            return None
        # normalize e.g. "3.0X" to "3X" so that they are the same modifier
        normalized_value = f"{leverage:g}X"
        if normalized_value in cls._value2member_map_:
            return cls(normalized_value)
        member = str.__new__(cls, normalized_value)
        member._name_ = f"LEVERAGED_{normalized_value}"
        member._value_ = normalized_value
        member._leverage = leverage
        cls._value2member_map_[normalized_value] = member
        return member

    @property
    def leverage(self) -> float | None:
        """Leverage of a leveraged modifier like "3x", None otherwise (including plain LEVERAGED)."""
        return getattr(self, "_leverage", None)

    @property
    def base(self) -> "AssetModifier":
        """The declared member this modifier belongs to, e.g. LEVERAGED for "3x", itself otherwise."""
        return AssetModifier.LEVERAGED if self.leverage is not None else self

    @property
    def supported_asset_types(self) -> frozenset[AssetType]:
        """Asset types this modifier can be applied to."""
        return {
            AssetModifier.INVERSE: frozenset({AssetType.FUTURE, AssetType.OPTION}),
            AssetModifier.PERPETUAL: frozenset({AssetType.FUTURE}),
            AssetModifier.LEVERAGED: frozenset({AssetType.ETF}),
        }[self.base]
