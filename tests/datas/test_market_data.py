from __future__ import annotations

import pickle
from datetime import UTC, datetime

import pytest

from pfund_blocks.datas.bar_data import BarData
from pfund_blocks.datas.data_base import BaseData
from pfund_blocks.datas.market_data import MarketData
from pfund_blocks.datas.tick_data import Tick
from pfund_blocks.entities.products.product_base import BaseProduct
from pfund_blocks.resolution import Resolution
from pfund_blocks.utils.temporal import NS_PER_SECOND

T0 = int(datetime(2026, 1, 1, tzinfo=UTC).timestamp()) * NS_PER_SECOND
TICK = Tick(ts=T0, price=100.0, volume=1.0)


# NOTE: inherits BarData only because a resampler must be a TickData or a BarData, what is tested here is MarketData
class DummyData(BarData):
    to_dict = MarketData.to_dict
    __str__ = MarketData.__str__


def create_product(symbol: str = "BTCUSDT") -> BaseProduct:
    return BaseProduct.model_validate(
        {"source": "BYBIT", "basis": "BTC_USDT_PERP", "symbol": symbol}
    )


def create_data(resolution: str = "1m", symbol: str = "BTCUSDT") -> DummyData:
    return DummyData(create_product(symbol), Resolution(resolution))


class TestBaseData:
    def test_to_dict_is_empty(self):
        assert BaseData().to_dict() == {}


class TestMarketData:
    def test_is_abstract(self):
        with pytest.raises(TypeError, match="abstract"):
            MarketData(create_product(), Resolution("1m"))  # ty: ignore[call-non-callable]

    def test_to_dict(self):
        data = create_data("5m")
        assert data.to_dict() == {
            "product": data.product.model_dump(),
            "resolution": "5m",
        }

    def test_str(self):
        assert str(create_data("5m")) == "[DummyData] BYBIT_BTCUSDT | 5_MINUTE"


class TestEqualityAndHash:
    def test_same_product_and_resolution_are_equal(self):
        assert create_data("5m") == create_data("5m")
        assert hash(create_data("5m")) == hash(create_data("5m"))

    def test_same_data_built_twice_is_one_item_in_a_set(self):
        assert len({create_data("5m"), create_data("5m")}) == 1

    def test_different_resolution_is_not_equal(self):
        assert create_data("1m") != create_data("5m")

    def test_different_product_is_not_equal(self):
        assert create_data(symbol="BTCUSDT") != create_data(symbol="ETHUSDT")

    def test_other_type_is_not_equal(self):
        assert create_data() != "1m"

    def test_state_is_not_part_of_the_identity(self):
        m1, updated_m1 = create_data(), create_data()
        hash_before_update = hash(updated_m1)
        updated_m1.update(TICK)
        assert m1 == updated_m1
        assert hash(updated_m1) == hash_before_update

    def test_pickled_copy_matches_the_original(self):
        # NOTE: Ray returns pickled copies, so identity can't be used to find a data
        m1 = create_data()
        pickled_m1 = pickle.loads(pickle.dumps(m1))
        assert pickled_m1 is not m1
        assert pickled_m1 == m1
        assert pickled_m1 in {m1}

    def test_pickling_keeps_the_links(self):
        m1, m5 = create_data("1m"), create_data("5m")
        m5.bind_resampler(m1)
        pickled_m5 = pickle.loads(pickle.dumps(m5))
        resampler = pickled_m5.get_resampler()
        assert resampler == m1
        assert resampler.get_resamplees()[0] is pickled_m5
