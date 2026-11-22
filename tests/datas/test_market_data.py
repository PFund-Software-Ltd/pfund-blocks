from __future__ import annotations

import pickle
from datetime import UTC, datetime

import pytest

from pfund_blocks.datas.bar_data import BarData
from pfund_blocks.datas.data_base import BaseData
from pfund_blocks.datas.market_data import MarketData
from pfund_blocks.datas.tick_data import Tick
from pfund_blocks.entities.products.product_base import BaseProduct
from pfund_blocks.enums import DataCategory
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


class KeyedData(BaseData):
    category = DataCategory.MARKET_DATA

    def __init__(self, key: str):
        self._key = key

    @property
    def key(self) -> str:
        return self._key


class TestBaseData:
    def test_to_dict_is_empty(self):
        assert KeyedData("a").to_dict() == {}

    def test_subclass_without_key_cannot_be_created(self):
        class NoKeyData(BaseData):
            category = DataCategory.MARKET_DATA

        with pytest.raises(TypeError, match="abstract"):
            NoKeyData()  # ty: ignore[abstract-class-instantiation]

    def test_subclass_without_category_cannot_be_defined(self):
        with pytest.raises(TypeError, match="must declare its data category"):

            class NoCategoryData(BaseData):
                @property
                def key(self) -> str:
                    return ""

    def test_category_is_inherited(self):
        class OtherKeyedData(KeyedData):
            pass

        assert OtherKeyedData.category == DataCategory.MARKET_DATA

    def test_eq_and_hash_follow_key(self):
        assert KeyedData("a") == KeyedData("a")
        assert hash(KeyedData("a")) == hash(KeyedData("a"))
        assert KeyedData("a") != KeyedData("b")
        assert len({KeyedData("a"), KeyedData("a")}) == 1

    def test_different_types_with_same_key_are_not_equal(self):
        class OtherKeyedData(KeyedData):
            pass

        assert KeyedData("a") != OtherKeyedData("a")


class TestMarketData:
    def test_category_is_market_data(self):
        assert MarketData.category == DataCategory.MARKET_DATA
        assert create_data().category == DataCategory.MARKET_DATA

    def test_is_abstract(self):
        with pytest.raises(TypeError, match="abstract"):
            MarketData(create_product(), Resolution("1m"))  # ty: ignore[abstract-class-instantiation]

    def test_to_dict(self):
        data = create_data("5m")
        assert data.to_dict() == {
            "product": data.product.model_dump(),
            "resolution": "5m",
            "source": "",
            "origin": "",
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


class TestSourceAndOrigin:
    def test_source_and_origin_are_optional(self):
        data = create_data()
        assert data.source == ""
        assert data.origin == ""

    def test_source_is_uppercased(self):
        data = DummyData(create_product(), Resolution("1m"), source="databento")
        assert data.source == "DATABENTO"

    def test_different_source_is_different_data(self):
        bybit = DummyData(create_product(), Resolution("1m"), source="BYBIT")
        databento = DummyData(create_product(), Resolution("1m"), source="DATABENTO")
        assert bybit != databento
        assert len({bybit, databento}) == 2

    def test_different_origin_is_different_data(self):
        a = DummyData(create_product(), Resolution("1m"), source="BYBIT", origin="a")
        b = DummyData(create_product(), Resolution("1m"), source="BYBIT", origin="b")
        assert a != b

    def test_same_source_and_origin_are_equal(self):
        a = DummyData(create_product(), Resolution("1m"), source="bybit", origin="x")
        b = DummyData(create_product(), Resolution("1m"), source="BYBIT", origin="x")
        assert a == b
        assert hash(a) == hash(b)

    def test_pickling_keeps_source_and_origin(self):
        data = DummyData(create_product(), Resolution("1m"), source="BYBIT", origin="x")
        copy = pickle.loads(pickle.dumps(data))
        assert (copy.source, copy.origin) == ("BYBIT", "x")
        assert copy == data
