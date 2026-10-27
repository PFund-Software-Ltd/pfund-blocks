from __future__ import annotations

from functools import cache

from pfund_blocks.entities.products.mixins.crypto import CryptoMixin
from pfund_blocks.entities.products.mixins.etf import ETFMixin
from pfund_blocks.entities.products.mixins.forex import ForexMixin
from pfund_blocks.entities.products.mixins.future import FutureMixin
from pfund_blocks.entities.products.mixins.index import IndexMixin
from pfund_blocks.entities.products.mixins.inverse import InverseMixin
from pfund_blocks.entities.products.mixins.option import OptionMixin
from pfund_blocks.entities.products.mixins.perpetual import PerpetualMixin
from pfund_blocks.entities.products.mixins.stock import StockMixin
from pfund_blocks.entities.products.product_base import BaseProduct
from pfund_blocks.enums.asset_type_DEPRECATED import AllAssetType, AssetTypeModifier

_MIXINS: dict[AssetTypeModifier | AllAssetType, type] = {
    AssetTypeModifier.INVERSE: InverseMixin,
    AllAssetType.INDEX: IndexMixin,
    AllAssetType.ETF: ETFMixin,
    AllAssetType.STOCK: StockMixin,
    AllAssetType.FUTURE: FutureMixin,
    AllAssetType.PERPETUAL: PerpetualMixin,
    AllAssetType.OPTION: OptionMixin,
    AllAssetType.FOREX: ForexMixin,
    AllAssetType.CRYPTO: CryptoMixin,
}


@cache
def _build_product_class(
    Product: type[BaseProduct],
    mixins: tuple[type, ...],
) -> type[BaseProduct]:
    class_name = (
        Product.__name__.replace("Product", "")
        + "".join(m.__name__.replace("Mixin", "") for m in mixins)
        + "Product"
    )
    return type(class_name, (Product, *mixins), {"__module__": __name__})


def ProductFactory(
    basis: str, Product: type[BaseProduct] = BaseProduct
) -> type[BaseProduct]:
    from pfund_blocks.entities.products.product_basis import ProductBasis

    asset_type = ProductBasis(basis=basis.upper()).asset_type
    if asset_type is None:
        raise ValueError(f"asset type is None for product basis {basis}")
    mixins = [_MIXINS[t] for t in asset_type]
    return _build_product_class(Product, tuple(mixins))
