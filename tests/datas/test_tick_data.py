from __future__ import annotations

import pickle
from datetime import UTC, datetime

import msgspec
import pytest

from pfund_blocks.datas.bar_data import BarData
from pfund_blocks.datas.tick_data import Tick, TickData
from pfund_blocks.entities.products.product_base import BaseProduct
from pfund_blocks.resolution import Resolution
from pfund_blocks.utils.temporal import NS_PER_SECOND

MINUTE = 60 * NS_PER_SECOND
T0 = int(datetime(2026, 1, 1, tzinfo=UTC).timestamp()) * NS_PER_SECOND


def create_product(symbol: str = "BTCUSDT") -> BaseProduct:
    return BaseProduct.model_validate(
        {"source": "BYBIT", "basis": "BTC_USDT_PERP", "symbol": symbol}
    )


def create_data(symbol: str = "BTCUSDT") -> TickData:
    return TickData(create_product(symbol), Resolution("1t"))


def create_bar_data(resolution: str = "1m", symbol: str = "BTCUSDT") -> BarData:
    return BarData(create_product(symbol), Resolution(resolution))


def create_tick(minute: float = 0, price: float = 100.0, volume: float = 1.0) -> Tick:
    return Tick(ts=T0 + int(minute * MINUTE), price=price, volume=volume)


class TestTick:
    @pytest.mark.parametrize("price", [0.0, -37.63])
    def test_zero_or_negative_price_is_valid(self, price: float):
        assert create_tick(price=price).price == price

    def test_zero_volume_is_valid(self):
        assert create_tick(volume=0.0).volume == 0.0

    def test_negative_volume_raises(self):
        with pytest.raises(ValueError, match="volume"):
            create_tick(volume=-1.0)

    def test_dt(self):
        assert create_tick(minute=1).dt == datetime(2026, 1, 1, 0, 1, tzinfo=UTC)

    def test_is_frozen(self):
        tick = create_tick()
        with pytest.raises(AttributeError):
            tick.price = 1.0  # ty: ignore[invalid-assignment]

    def test_serialization_round_trip(self):
        tick = create_tick()
        assert msgspec.json.decode(msgspec.json.encode(tick), type=Tick) == tick

    def test_decoding_a_ts_in_seconds_raises(self):
        data = {
            "type": "Tick",
            "ts": T0 // NS_PER_SECOND,
            "price": 100.0,
            "volume": 1.0,
        }
        with pytest.raises(msgspec.ValidationError):
            msgspec.convert(data, Tick)

    def test_decoding_a_negative_volume_raises(self):
        data = {"type": "Tick", "ts": T0, "price": 100.0, "volume": -1.0}
        with pytest.raises(msgspec.ValidationError):
            msgspec.convert(data, Tick)


class TestTickDataInit:
    def test_defaults(self):
        data = create_data()
        assert data.tick is None
        assert data.resolution == Resolution("1t")

    @pytest.mark.parametrize("resolution", ["1s", "1m", "1q"])
    def test_other_resolutions_raise(self, resolution: str):
        with pytest.raises(ValueError, match="not a tick resolution"):
            TickData(create_product(), Resolution(resolution))

    def test_str(self):
        assert str(create_data()) == "[TickData] BYBIT_BTCUSDT | 1_TICK"

    def test_to_dict(self):
        data = create_data()
        assert data.to_dict() == {
            "product": data.product.model_dump(),
            "resolution": "1t",
        }


class TestIdentity:
    def test_same_product_is_equal(self):
        assert create_data() == create_data()
        assert hash(create_data()) == hash(create_data())

    def test_different_product_is_not_equal(self):
        assert create_data("BTCUSDT") != create_data("ETHUSDT")

    def test_state_is_not_part_of_the_identity(self):
        updated, data = create_data(), create_data()
        hash_before_update = hash(updated)
        updated.update(create_tick())
        assert updated == data
        assert hash(updated) == hash_before_update

    def test_pickled_copy_matches_the_original(self):
        data = create_data()
        data.update(create_tick())
        pickled_data = pickle.loads(pickle.dumps(data))
        assert pickled_data == data
        assert pickled_data.tick == data.tick


class TestUpdate:
    def test_keeps_the_latest_tick(self):
        data = create_data()
        first, second = create_tick(minute=0), create_tick(minute=1)
        data.update(first)
        assert data.tick is first
        data.update(second)
        assert data.tick is second

    def test_tick_with_the_same_ts_replaces_the_latest_tick(self):
        data = create_data()
        first, second = create_tick(price=100.0), create_tick(price=101.0)
        data.update(first)
        data.update(second)
        assert data.tick is second

    def test_older_tick_does_not_replace_the_latest_tick(self):
        data = create_data()
        latest = create_tick(minute=1)
        data.update(latest)
        data.update(create_tick(minute=0))
        assert data.tick is latest

    def test_without_resamplees_returns_nothing(self):
        assert create_data().update(create_tick()) == []


class TestBindToBarData:
    def test_links_both_sides(self):
        data, m1 = create_data(), create_bar_data()
        m1.bind_resampler(data)
        assert m1.get_resampler() is data
        assert data.get_resamplees() == [m1]
        assert data.is_resampler()

    def test_different_product_raises(self):
        with pytest.raises(ValueError, match="does not match"):
            create_bar_data(symbol="ETHUSDT").bind_resampler(create_data())

    def test_second_resampler_raises(self):
        data, m1, m5 = create_data(), create_bar_data("1m"), create_bar_data("5m")
        m5.bind_resampler(data)
        with pytest.raises(ValueError, match="already has a resampler"):
            m5.bind_resampler(m1)

    def test_tick_data_cannot_be_resampled(self):
        data = create_data()
        assert not hasattr(data, "bind_resampler")
        assert not data.is_resamplee()
        assert data.get_resampler() is None


class TestForwarding:
    def test_every_tick_reaches_every_resamplee(self):
        data, m1, m5 = create_data(), create_bar_data("1m"), create_bar_data("5m")
        m1.bind_resampler(data)
        m5.bind_resampler(data)
        data.update(create_tick(minute=0, price=100.0, volume=2.0))
        data.update(create_tick(minute=0.5, price=110.0, volume=3.0))
        for bar_data in (m1, m5):
            assert bar_data.bar is not None
            assert bar_data.bar.volume == 5.0
            assert bar_data.bar.close == 110.0
            assert not bar_data.bar.is_closed

    def test_returns_the_bars_it_closes(self):
        data, m1 = create_data(), create_bar_data("1m")
        m1.bind_resampler(data)
        assert data.update(create_tick(minute=0, volume=2.0)) == []
        closed_bars = data.update(create_tick(minute=1, volume=3.0))
        assert [(bar.resolution, bar.volume, bar.is_closed) for bar in closed_bars] == [
            (Resolution("1m"), 2.0, True)
        ]

    def test_returns_the_bars_of_every_resamplee(self):
        data, m1, m5 = create_data(), create_bar_data("1m"), create_bar_data("5m")
        m1.bind_resampler(data)
        m5.bind_resampler(data)
        data.update(create_tick(minute=0))
        closed_bars = data.update(create_tick(minute=5))
        assert [bar.resolution for bar in closed_bars] == [
            Resolution("1m"),
            Resolution("5m"),
        ]

    def test_chain_does_not_count_volume_twice(self):
        data, m1, m5 = create_data(), create_bar_data("1m"), create_bar_data("5m")
        m1.bind_resampler(data)
        m5.bind_resampler(m1)
        data.update(create_tick(minute=0, volume=2.0))
        data.update(create_tick(minute=0.5, volume=3.0))
        assert m5.bar is None  # the 1m bar hasn't closed yet
        data.update(create_tick(minute=1, volume=4.0))
        assert m5.bar is not None
        assert m5.bar.volume == 5.0

    def test_chain_returns_finest_first(self):
        data, m1, m5 = create_data(), create_bar_data("1m"), create_bar_data("5m")
        m1.bind_resampler(data)
        m5.bind_resampler(m1)
        data.update(create_tick(minute=4))
        # opens the next 1m bar, which closes the last 1m bar of the window, which closes the 5m bar
        closed_bars = data.update(create_tick(minute=5))
        assert [bar.resolution for bar in closed_bars] == [
            Resolution("1m"),
            Resolution("5m"),
        ]

    def test_older_tick_is_still_forwarded(self):
        data, m1 = create_data(), create_bar_data("1m")
        m1.bind_resampler(data)
        data.update(create_tick(minute=0.5, volume=2.0))
        data.update(create_tick(minute=0, volume=3.0))
        assert m1.bar is not None
        assert m1.bar.volume == 5.0

    def test_unbound_resamplee_receives_nothing(self):
        data, m1 = create_data(), create_bar_data()
        m1.bind_resampler(data)
        m1.unbind_resampler()
        data.update(create_tick())
        assert m1.bar is None
        assert data.get_resamplees() == []
