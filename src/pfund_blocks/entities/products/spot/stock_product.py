from pfund_blocks.entities.products.spot.spot_product import SpotProduct
from pfund_blocks.enums.asset import AssetClass


class StockProduct(SpotProduct):
    ASSET_CLASS = AssetClass.EQUITY

    def _create_symbol(self) -> str:
        # e.g. AAPL_USD_STOCK -> AAPL
        return self.base_asset
