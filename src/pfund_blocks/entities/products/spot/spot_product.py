from typing import ClassVar

from pydantic import field_validator

from pfund_blocks.entities.products.product_base import BaseProduct
from pfund_blocks.entities.products.product_basis import ProductBasis
from pfund_blocks.entities.products.product_type import ProductType
from pfund_blocks.enums.asset import AssetClass


class SpotProduct(BaseProduct):
    """A product owned outright, e.g. a stock, a currency pair or a crypto pair."""

    # asset class required by the subclass, None = any asset class, no check
    ASSET_CLASS: ClassVar[AssetClass | None] = None

    @field_validator("basis", mode="after")
    @classmethod
    def _ensure_asset_class(cls, basis: ProductBasis) -> ProductBasis:
        # e.g. for CryptoProduct, BTC_USDT_SPOT -> BTC_USDT_SPOT-CRYPTO, so it equals BTC_USDT_CRYPTO
        if cls.ASSET_CLASS is None:
            return basis
        product_type = basis.product_type
        if product_type.asset_class is None:
            return ProductBasis(
                base_asset=basis.base_asset,
                quote_asset=basis.quote_asset,
                product_type=ProductType(
                    asset_type=product_type.asset_type,
                    asset_class=cls.ASSET_CLASS,
                    modifiers=product_type.modifiers,
                ),
            )
        if product_type.asset_class != cls.ASSET_CLASS:
            raise ValueError(
                f"{cls.__name__} requires asset class {cls.ASSET_CLASS}, got {product_type.asset_class}"
            )
        return basis
