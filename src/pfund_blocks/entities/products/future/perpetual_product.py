from pfund_blocks.entities.products.future.future_product import BaseFutureProduct


class PerpetualProduct(BaseFutureProduct):
    """A future without an expiration, e.g. a crypto perpetual swap."""

    # a perpetual never expires, kept so that it has the same specs as a dated future
    expiration: None = None

    def _create_symbol(self) -> str:
        # e.g. BTC_USDT_PERPETUAL -> BTC_USDT
        return self.asset_pair
