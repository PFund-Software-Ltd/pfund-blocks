from __future__ import annotations

import pytest

from pfund_blocks.entities.products.fund import ETFProduct, MutualFundProduct
from pfund_blocks.entities.products.future import FutureProduct, PerpetualProduct
from pfund_blocks.entities.products.index import IndexProduct
from pfund_blocks.entities.products.option import OptionProduct
from pfund_blocks.entities.products.product_base import BaseProduct
from pfund_blocks.entities.products.product_basis import ProductBasis
from pfund_blocks.entities.products.product_factory import ProductFactory
from pfund_blocks.entities.products.spot import (
    CryptoProduct,
    ForexProduct,
    SpotProduct,
    StockProduct,
)


class TestProductFactory:
    @pytest.mark.parametrize(
        "basis, product_class",
        [
            # SPOT is split by asset class
            ("AAPL_USD_STK", StockProduct),
            ("EUR_USD_FX", ForexProduct),
            ("BTC_USDT_CRYPTO", CryptoProduct),
            ("XAU_USD_CMDTY", SpotProduct),
            ("US10Y_USD_BOND", SpotProduct),
            ("X_USD_SPOT", SpotProduct),
            # FUTURE is split by the PERPETUAL modifier
            ("BTC_USDT_PERP", PerpetualProduct),
            ("BTC_USD_IPERP", PerpetualProduct),
            ("BTC_USDT_FUTURE-CRYPTO-PERPETUAL", PerpetualProduct),
            ("BTC_USD_IFUT", FutureProduct),
            ("ES_USD_FUTURE-EQUITY", FutureProduct),
            # the rest by asset type alone
            ("SPY_USD_ETF-EQUITY", ETFProduct),
            ("SQQQ_USD_ETF-EQUITY-SHORT-3x", ETFProduct),
            ("VFIAX_USD_MUTUAL_FUND-EQUITY", MutualFundProduct),
            ("AAPL_USD_OPTION-EQUITY", OptionProduct),
            ("SPX_USD_INDEX-EQUITY", IndexProduct),
        ],
    )
    def test_product_class(self, basis: str, product_class: type[BaseProduct]):
        # NOTE: "is" instead of issubclass, e.g. CryptoProduct is a subclass of ForexProduct
        assert ProductFactory(basis) is product_class

    def test_accepts_product_basis(self):
        basis = ProductBasis.model_validate("BTC_USDT_PERP")
        assert ProductFactory(basis) is PerpetualProduct

    def test_is_case_insensitive(self):
        assert ProductFactory("btc_usdt_perp") is PerpetualProduct

    def test_no_product_class_raises(self):
        with pytest.raises(ValueError, match="no product class for"):
            ProductFactory("ELECTION_USD_OUTCOME")

    def test_invalid_basis_raises(self):
        # pydantic's ValidationError is a ValueError
        with pytest.raises(ValueError, match="invalid product basis"):
            ProductFactory("BTC_USDT")
