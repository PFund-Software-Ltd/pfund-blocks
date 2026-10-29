from __future__ import annotations

from pfund_blocks.entities.markets.market_base import BaseMarket, MarketDict


class TestMarketDict:
    def test_keys_match_base_market_fields(self):
        assert MarketDict.__required_keys__ | MarketDict.__optional_keys__ == set(BaseMarket.model_fields)

    def test_required_keys_match_base_market_required_fields(self):
        required = {name for name, field in BaseMarket.model_fields.items() if field.is_required()}
        assert required == MarketDict.__required_keys__
