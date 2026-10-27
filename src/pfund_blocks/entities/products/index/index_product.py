from pfund_blocks.entities.products.product_base import BaseProduct


class IndexProduct(BaseProduct):
    """A reference index, not tradable, e.g. SPX."""

    def _create_symbol(self) -> str:
        # e.g. SPX_USD_INDEX -> SPX
        return self.base_asset
