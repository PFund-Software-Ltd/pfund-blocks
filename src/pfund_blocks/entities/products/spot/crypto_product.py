from pfund_blocks.entities.products.spot.forex_product import ForexProduct
from pfund_blocks.enums.asset import AssetClass


class CryptoProduct(ForexProduct):
    """A crypto pair, symbol is the same as forex, e.g. BTC_USDT_CRYPTO -> BTCUSDT."""

    ASSET_CLASS = AssetClass.CRYPTO
