from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from pfund_blocks.entities.products.product_type import ProductType

# NOT "_" or "-", which are the separators of a product basis
_ASSET_PATTERN = r"^[A-Z0-9.]+$"


class ProductBasis(BaseModel):
    model_config = ConfigDict(frozen=True)

    base_asset: str = Field(pattern=_ASSET_PATTERN)  # e.g. BTC, BRK.B, 1000PEPE
    quote_asset: str = Field(pattern=_ASSET_PATTERN)
    product_type: ProductType

    @model_validator(mode="before")
    @classmethod
    def _parse_string(cls, data: Any) -> Any:
        # allow a string (e.g. "BTC_USDT_PERP") wherever a ProductBasis is expected
        if isinstance(data, str):
            return cls._parse(data)
        return data

    @staticmethod
    def _parse(basis: str) -> dict[str, Any]:
        """Parse e.g. "BTC_USDT_PERP" or "VFIAX_USD_MUTUAL_FUND-EQUITY" into fields."""
        # maxsplit=2 since the product type itself can contain "_", e.g. MUTUAL_FUND
        parts = basis.split("_", 2)
        if len(parts) != 3:
            raise ValueError(
                f"invalid product basis {basis!r}, expected {{base_asset}}_{{quote_asset}}_{{product_type}}"
            )
        base_asset, quote_asset, product_type = parts
        return {
            "base_asset": base_asset.upper(),
            "quote_asset": quote_asset.upper(),
            "product_type": product_type,  # parsed by ProductType's own validator
        }

    def __repr__(self) -> str:
        # fully expanded form, e.g. ProductBasis(BTC_USDT_FUTURE-PERPETUAL)
        return f"ProductBasis({self.base_asset}_{self.quote_asset}_{self.product_type.canonical})"

    def __str__(self) -> str:
        # friendly form, e.g. BTC_USDT_PERPETUAL
        return f"{self.base_asset}_{self.quote_asset}_{self.product_type}"
