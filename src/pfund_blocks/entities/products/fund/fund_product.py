from pfund_blocks.entities.products.product_base import BaseProduct


class BaseFundProduct(BaseProduct):
    """A unit of a fund, common base of ETFs and mutual funds."""

    def _create_symbol(self) -> str:
        # e.g. SPY_USD_ETF -> SPY, VFIAX_USD_MUTUAL_FUND -> VFIAX
        return self.base_asset
