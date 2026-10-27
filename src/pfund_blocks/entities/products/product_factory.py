from pfund_blocks.entities.products.fund import ETFProduct, MutualFundProduct
from pfund_blocks.entities.products.future import FutureProduct, PerpetualProduct
from pfund_blocks.entities.products.index import IndexProduct
from pfund_blocks.entities.products.option import OptionProduct
from pfund_blocks.entities.products.product_base import BaseProduct
from pfund_blocks.entities.products.product_basis import ProductBasis
from pfund_blocks.entities.products.spot import (
    CryptoProduct,
    ForexProduct,
    SpotProduct,
    StockProduct,
)
from pfund_blocks.enums.asset import AssetType

_PRODUCTS: dict[AssetType, type[BaseProduct]] = {
    AssetType.SPOT: SpotProduct,
    AssetType.ETF: ETFProduct,
    AssetType.MUTUAL_FUND: MutualFundProduct,
    AssetType.FUTURE: FutureProduct,
    AssetType.OPTION: OptionProduct,
    AssetType.INDEX: IndexProduct,
}


def ProductFactory(basis: str | ProductBasis) -> type[BaseProduct]:  # noqa: N802
    """Gets the product class of a product basis, e.g. BTC_USDT_PERP -> PerpetualProduct."""
    if isinstance(basis, str):
        basis = ProductBasis.model_validate(basis)
    product_type = basis.product_type
    # asset type alone is not enough for SPOT and FUTURE, which have more than one class:
    # SPOT is split further by asset class (e.g. StockProduct), FUTURE by the PERPETUAL modifier
    if product_type.is_stock():
        return StockProduct
    if product_type.is_forex():
        return ForexProduct
    if product_type.is_crypto_spot():
        return CryptoProduct
    if product_type.is_perpetual():
        return PerpetualProduct
    if product_type.asset_type not in _PRODUCTS:
        raise ValueError(f"no product class for {product_type!r} yet")
    return _PRODUCTS[product_type.asset_type]
