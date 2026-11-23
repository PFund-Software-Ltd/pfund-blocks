from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pfund_blocks.adapters.adapter_base import BaseAdapter

from pydantic import ValidationError

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


def create_product(
    source: str,
    basis: str | ProductBasis,
    adapter: BaseAdapter | None = None,
    symbol: str = "",
    name: str = "",
    **specs: Any,
) -> BaseProduct:
    """Creates a product with the source's symbol and name, and maps them in the adapter's group "product".

    Shared by pfund-blocks' BaseVenue.create_product() and pfeed's BaseSource.create_product().

    Args:
        source: where the product comes from, e.g. a trading venue "BYBIT" or a data source "YAHOO_FINANCE"
        basis: e.g. "BTC_USDT_PERP"
        adapter: the source's adapter, if None, the product class's own conventions are used and nothing is mapped
        symbol: the source's symbol, if not provided, derived by the adapter's create_symbol(),
            pass it when the derived symbol is wrong
        name: unique product name, if not provided, derived by the adapter's create_name()
        specs: the product class's specs, e.g. expiration for a future

    Raises:
        TypeError: if specs contain fields the product class does not have,
            e.g. a typo of a caller's parameter that fell into **specs
    """
    Product = ProductFactory(basis)
    try:
        # the adapter is passed via the validation context, so that the product derives its symbol and name
        # with the source's conventions once its specs are validated (e.g. expiration as a date)
        product = Product.model_validate(
            {
                "source": source,
                "basis": basis,
                "symbol": symbol,
                "name": name,
                **specs,
            },
            context={"adapter": adapter},
        )
    except ValidationError as err:
        # callers usually forward their unknown kwargs as **specs,
        # so a typo of their parameter surfaces as pydantic's "Extra inputs are not permitted"
        unknown = [
            str(e["loc"][0])
            for e in err.errors()
            if e["type"] == "extra_forbidden" and e["loc"]
        ]
        if not unknown:
            raise
        raise TypeError(
            f"unexpected product spec(s) {unknown} for '{basis}': {Product.__name__} does not have them. "
            f"If they were passed as extra kwargs, is it a typo of a parameter?"
        ) from err
    if adapter is not None:
        adapter.add_mapping(product.name, product.symbol, group="product")
    return product
