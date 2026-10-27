from typing import Any, Self

from enum import Enum

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from pfund_blocks.enums.asset import AssetClass, AssetModifier, AssetType

# NOT "_", which already separates {base_asset}_{quote_asset}_{product_type}
_SEPARATOR = "-"


def _try_leverage(token: str) -> AssetModifier | None:
    """Leveraged modifier for tokens like "3X", None if the token is not a leverage."""
    try:
        return AssetModifier(token)
    except ValueError:
        return None


class ProductTypeAlias(Enum):
    """Shorthand for common product types, e.g. AAPL_USD_STK instead of AAPL_USD_SPOT-EQUITY.
    NOTE: an alias must be the whole product type, it can't be combined with other tokens.
    NOTE: the first name is the preferred one, e.g. STOCK over STK, used by __str__.
    """

    STOCK = STK = (AssetType.SPOT, AssetClass.EQUITY)
    BOND = (AssetType.SPOT, AssetClass.BOND)
    FOREX = FX = (AssetType.SPOT, AssetClass.FOREX)
    CRYPTO = (AssetType.SPOT, AssetClass.CRYPTO)
    COMMODITY = CMDTY = (AssetType.SPOT, AssetClass.COMMODITY)
    PERPETUAL = PERP = (AssetType.FUTURE, AssetModifier.PERPETUAL)
    INVERSE_PERPETUAL = IPERP = IPERPETUAL = (AssetType.FUTURE, AssetModifier.INVERSE, AssetModifier.PERPETUAL)
    INVERSE_FUTURE = IFUT = IFUTURE = (AssetType.FUTURE, AssetModifier.INVERSE)


# user-facing alias strings, e.g. INVERSE-PERPETUAL, since Python names can't contain "-"
# NOTE: INVERSE_PERPETUAL is rejected, "_" only separates the parts of a product basis
_ALIASES: dict[str, ProductTypeAlias] = {
    name.replace("_", _SEPARATOR): alias for name, alias in ProductTypeAlias.__members__.items()
}


class ProductType(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    asset_type: AssetType
    asset_class: AssetClass | None = None  # None e.g. for OUTCOME
    modifiers: tuple[AssetModifier, ...] = ()

    @model_validator(mode="before")
    @classmethod
    def _parse_string(cls, data: Any) -> Any:
        # allow a string (e.g. "FUTURE-CRYPTO-PERPETUAL") wherever a ProductType is expected
        if isinstance(data, str):
            return cls._parse(data)
        return data

    @staticmethod
    def _parse(product_type: str) -> dict[str, Any]:
        """Parse e.g. "FUTURE-CRYPTO-INVERSE-PERPETUAL" or "ETF-EQUITY-3x" into fields.

        Tokens are classified by which enum they belong to, so their order does not matter,
        e.g. "PERPETUAL-FUTURE-CRYPTO" is the same as "FUTURE-CRYPTO-PERPETUAL".
        """
        if alias := _ALIASES.get(product_type.upper()):
            product_type = _SEPARATOR.join(alias.value)
        tokens = product_type.upper().split(_SEPARATOR)
        asset_types: list[AssetType] = []
        asset_classes: list[AssetClass] = []
        modifiers: list[AssetModifier] = []
        for token in tokens:
            if token in AssetType.__members__:
                asset_types.append(AssetType[token])
            elif token in AssetClass.__members__:
                asset_classes.append(AssetClass[token])
            elif token in AssetModifier.__members__:
                modifiers.append(AssetModifier[token])
            elif leverage := _try_leverage(token):  # e.g. "3X"
                modifiers.append(leverage)
            else:
                raise ValueError(
                    f"invalid token {token!r} in product type {product_type!r}"
                )
        # dedupe (keeping order) so that e.g. "SPOT-FX-FOREX" is FOREX, like modifiers are deduped
        asset_types = list(dict.fromkeys(asset_types))
        asset_classes = list(dict.fromkeys(asset_classes))
        if len(asset_types) != 1:
            raise ValueError(
                f"exactly one asset type is required, got {asset_types} in {product_type!r}"
            )
        if len(asset_classes) > 1:
            raise ValueError(
                f"at most one asset class is allowed, got {asset_classes} in {product_type!r}"
            )
        return {
            "asset_type": asset_types[0],
            "asset_class": asset_classes[0] if asset_classes else None,
            "modifiers": tuple(modifiers),
        }

    @field_validator("modifiers", mode="after")
    @classmethod
    def _normalize_modifiers(
        cls, modifiers: tuple[AssetModifier, ...]
    ) -> tuple[AssetModifier, ...]:
        # dedupe and sort into canonical order, i.e. the declaration order of AssetModifier
        # (pseudo-members like "3x" sort by their base LEVERAGED)
        order = list(AssetModifier)
        return tuple(sorted(set(modifiers), key=lambda m: order.index(m.base)))

    @model_validator(mode="after")
    def _validate_modifiers(self) -> Self:
        if sum(m.base is AssetModifier.LEVERAGED for m in self.modifiers) > 1:
            raise ValueError(
                f"only one leverage modifier is allowed, got {self.modifiers}"
            )
        for modifier in self.modifiers:
            if self.asset_type not in modifier.supported_asset_types:
                raise ValueError(f"{modifier} is not supported for {self.asset_type}")
        return self

    @property
    def canonical(self) -> str:
        """Fully expanded form, e.g. FUTURE-CRYPTO-INVERSE-PERPETUAL, ETF-EQUITY-3x, OUTCOME."""
        parts: list[str] = [self.asset_type]
        if self.asset_class is not None:
            parts.append(self.asset_class)
        for modifier in self.modifiers:
            # leverage shows its number, e.g. 3x instead of LEVERAGED
            parts.append(
                f"{modifier.leverage:g}x" if modifier.leverage is not None else modifier
            )
        return _SEPARATOR.join(parts)

    def __repr__(self) -> str:
        return f"ProductType({self.canonical})"

    def __str__(self) -> str:
        # friendly form, e.g. STOCK instead of SPOT-EQUITY, falls back to the canonical form
        # NOTE: iterating an enum skips aliases, so the preferred name (e.g. STOCK, not STK) is used
        for alias in ProductTypeAlias:
            if _SEPARATOR.join(alias.value) == self.canonical:
                return alias.name.replace("_", _SEPARATOR)
        return self.canonical

    # asset type
    def is_etf(self) -> bool:
        return self.asset_type == AssetType.ETF

    def is_mutual_fund(self) -> bool:
        return self.asset_type == AssetType.MUTUAL_FUND

    def is_future(self) -> bool:
        return self.asset_type == AssetType.FUTURE

    def is_option(self) -> bool:
        return self.asset_type == AssetType.OPTION

    def is_index(self) -> bool:
        return self.asset_type == AssetType.INDEX

    def is_outcome(self) -> bool:
        return self.asset_type == AssetType.OUTCOME

    # modifiers
    def is_inverse(self) -> bool:
        return AssetModifier.INVERSE in self.modifiers

    def is_perpetual(self) -> bool:
        return AssetModifier.PERPETUAL in self.modifiers

    # spot + asset class, same as the aliases STOCK, BOND etc.
    # NOTE: for exposure instead, e.g. a bond ETF, check asset_class directly
    def is_stock(self) -> bool:
        return self._is_spot_of(AssetClass.EQUITY)

    def is_bond(self) -> bool:
        return self._is_spot_of(AssetClass.BOND)

    def is_forex(self) -> bool:
        return self._is_spot_of(AssetClass.FOREX)

    def is_crypto_spot(self) -> bool:
        return self._is_spot_of(AssetClass.CRYPTO)

    def is_commodity_spot(self) -> bool:
        return self._is_spot_of(AssetClass.COMMODITY)

    def _is_spot_of(self, asset_class: AssetClass) -> bool:
        return self.asset_type == AssetType.SPOT and self.asset_class == asset_class
