from pfund_blocks.entities.products.spot.spot_product import SpotProduct
from pfund_blocks.enums.asset import AssetClass


class ForexProduct(SpotProduct):
    ASSET_CLASS = AssetClass.FOREX

    def _create_symbol(self) -> str:
        # e.g. EUR_USD_FOREX -> EURUSD
        return self.base_asset + self.quote_asset
