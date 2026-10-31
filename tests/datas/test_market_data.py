from __future__ import annotations

import pickle
from datetime import UTC, datetime

import pytest

from pfund_blocks.datas.bar_data import Bar
from pfund_blocks.datas.data_base import BaseData
from pfund_blocks.datas.market_data import MarketData
from pfund_blocks.datas.tick_data import Tick, TickData
from pfund_blocks.entities.products.product_base import BaseProduct
from pfund_blocks.resolution import Resolution
from pfund_blocks.utils.temporal import NS_PER_SECOND

T0 = int(datetime(2026, 1, 1, tzinfo=UTC).timestamp()) * NS_PER_SECOND
TICK = Tick(ts=T0, price=100.0, volume=1.0)


def create_closed_bar(minute: int = 0) -> Bar:
    start_ts = T0 + minute * 60 * NS_PER_SECOND
    return Bar(
        resolution=Resolution("1m"),
        start_ts=start_ts,
        end_ts=start_ts + 60 * NS_PER_SECOND,
        updated_ts=start_ts,
        open=100.0,
        high=100.0,
        low=100.0,
        close=100.0,
        volume=1.0,
        is_closed=True,
    )


BAR_A, BAR_B, BAR_C = create_closed_bar(0), create_closed_bar(1), create_closed_bar(2)


# NOTE: inherits TickData only because a resampler must be a TickData or a BarData, what is tested here is MarketData
class DummyData(TickData):
    """Closes whatever closed_bars it is told to, and records what it receives."""

    def __init__(
        self,
        product: BaseProduct,
        resolution: Resolution,
        closed_bars: list[Bar] | None = None,
    ):
        super().__init__(product, resolution)
        self.closed_bars: list[Bar] = closed_bars or []
        self.received: list[Tick | Bar] = []

    def _update(self, value: Tick | Bar) -> list[Bar]:
        self.received.append(value)
        return self.closed_bars


def create_product(symbol: str = "BTCUSDT") -> BaseProduct:
    return BaseProduct.model_validate(
        {"source": "BYBIT", "basis": "BTC_USDT_PERP", "symbol": symbol}
    )


def create_data(
    resolution: str = "1m",
    closed_bars: list[Bar] | None = None,
    symbol: str = "BTCUSDT",
) -> DummyData:
    return DummyData(create_product(symbol), Resolution(resolution), closed_bars)


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


class TestBindResampler:
    def test_links_both_sides(self):
        m1, m5 = create_data("1m"), create_data("5m")
        m5.bind_resampler(m1)
        assert m5.get_resampler() is m1
        assert m1.get_resamplees() == [m5]
        assert m5.is_resamplee() and not m5.is_resampler()
        assert m1.is_resampler() and not m1.is_resamplee()

    def test_not_bound_by_default(self):
        data = create_data()
        assert data.get_resampler() is None
        assert data.get_resamplees() == []
        assert not data.is_resamplee()
        assert not data.is_resampler()

    def test_resampler_can_have_many_resamplees(self):
        m1, m5, m15 = create_data("1m"), create_data("5m"), create_data("15m")
        m5.bind_resampler(m1)
        m15.bind_resampler(m1)
        assert m1.get_resamplees() == [m5, m15]

    def test_second_resampler_raises(self):
        m1, s1, m5 = create_data("1m"), create_data("1s"), create_data("5m")
        m5.bind_resampler(m1)
        with pytest.raises(ValueError, match="already has a resampler"):
            m5.bind_resampler(s1)
        assert m5.get_resampler() is m1
        assert s1.get_resamplees() == []

    def test_same_resampler_again_raises(self):
        m1, m5 = create_data("1m"), create_data("5m")
        m5.bind_resampler(m1)
        with pytest.raises(ValueError, match="already has a resampler"):
            m5.bind_resampler(m1)
        assert m1.get_resamplees() == [m5]

    def test_different_product_raises(self):
        m1, m5 = (
            create_data("1m", symbol="ETHUSDT"),
            create_data("5m", symbol="BTCUSDT"),
        )
        with pytest.raises(ValueError, match="does not match"):
            m5.bind_resampler(m1)
        assert not m5.is_resamplee()
        assert not m1.is_resampler()

    @pytest.mark.parametrize(
        "resampler, resamplee",
        [
            ("5m", "1m"),  # coarser
            ("5m", "5m"),  # same
            ("60m", "1h"),  # same in other words
        ],
    )
    def test_resampler_that_is_not_finer_raises(self, resampler: str, resamplee: str):
        with pytest.raises(ValueError, match="must be finer"):
            create_data(resamplee).bind_resampler(create_data(resampler))


class TestUnbindResampler:
    def test_unlinks_both_sides(self):
        m1, m5 = create_data("1m"), create_data("5m")
        m5.bind_resampler(m1)
        m5.unbind_resampler()
        assert m5.get_resampler() is None
        assert m1.get_resamplees() == []

    def test_without_resampler_does_nothing(self):
        m5 = create_data("5m")
        m5.unbind_resampler()
        assert m5.get_resampler() is None

    def test_can_bind_again(self):
        m1, s1, m5 = create_data("1m"), create_data("1s"), create_data("5m")
        m5.bind_resampler(m1)
        m5.unbind_resampler()
        m5.bind_resampler(s1)
        assert m5.get_resampler() is s1

    def test_removes_the_right_resamplee(self):
        m1, m5, m15 = create_data("1m"), create_data("5m"), create_data("15m")
        m5.bind_resampler(m1)
        m15.bind_resampler(m1)
        m5.unbind_resampler()
        assert m1.get_resamplees() == [m15]


class TestUpdate:
    def test_without_closed_bars_resamplees_receive_nothing(self):
        m1, m5 = create_data("1m"), create_data("5m")
        m5.bind_resampler(m1)
        assert m1.update(TICK) == []
        assert m1.received == [TICK]
        assert m5.received == []

    def test_each_closed_bar_goes_to_every_resamplee_oldest_first(self):
        m1, m5, m15 = (
            create_data("1m", [BAR_A, BAR_B]),
            create_data("5m"),
            create_data("15m"),
        )
        m5.bind_resampler(m1)
        m15.bind_resampler(m1)
        assert m1.update(TICK) == [BAR_A, BAR_B]
        assert m5.received == [BAR_A, BAR_B]
        assert m15.received == [BAR_A, BAR_B]

    def test_returns_all_closed_bars_finest_first(self):
        m1, m5, h1 = (
            create_data("1m", [BAR_A]),
            create_data("5m", [BAR_B]),
            create_data("1h", [BAR_C]),
        )
        m5.bind_resampler(m1)
        h1.bind_resampler(m5)
        assert m1.update(TICK) == [BAR_A, BAR_B, BAR_C]
        assert m5.received == [BAR_A]
        assert h1.received == [BAR_B]

    def test_unbound_resamplee_receives_nothing(self):
        m1, m5 = create_data("1m", [BAR_A]), create_data("5m")
        m5.bind_resampler(m1)
        m5.unbind_resampler()
        m1.update(TICK)
        assert m5.received == []
