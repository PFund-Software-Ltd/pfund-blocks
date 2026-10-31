from __future__ import annotations

from typing import Any

import pickle
from datetime import UTC, datetime

import msgspec
import pytest

from pfund_blocks.datas.bar_data import Bar, BarData, get_bar_window
from pfund_blocks.datas.market_data import MarketData
from pfund_blocks.datas.tick_data import Tick
from pfund_blocks.entities.products.product_base import BaseProduct
from pfund_blocks.resolution import Resolution
from pfund_blocks.utils.temporal import NS_PER_SECOND

SECOND = NS_PER_SECOND
MINUTE = 60 * SECOND
HOUR = 60 * MINUTE
DAY = 24 * HOUR
T0 = (
    int(datetime(2026, 1, 1, tzinfo=UTC).timestamp()) * SECOND
)  # a day, hour and minute boundary


class OtherData(MarketData):
    def update(self, value: Any) -> list[Any]:
        return []


def create_product(symbol: str = "BTCUSDT") -> BaseProduct:
    return BaseProduct.model_validate(
        {"source": "BYBIT", "basis": "BTC_USDT_PERP", "symbol": symbol}
    )


def create_data(
    resolution: str = "5m", shift: int = 0, symbol: str = "BTCUSDT"
) -> BarData:
    return BarData(create_product(symbol), Resolution(resolution), shift=shift)


def create_bar(
    resolution: str = "1m",
    minute: float = 0,
    open: float = 100.0,
    high: float | None = None,
    low: float | None = None,
    close: float | None = None,
    volume: float = 1.0,
    is_closed: bool = True,
    server_ts: int | None = None,
) -> Bar:
    """Creates a bar that starts at the given number of minutes after T0."""
    close = open if close is None else close
    resolution_ = Resolution(resolution)
    start_ts = T0 + int(minute * MINUTE)
    end_ts = start_ts + resolution_.to_seconds() * SECOND
    return Bar(
        resolution=resolution_,
        start_ts=start_ts,
        end_ts=end_ts,
        updated_ts=end_ts - SECOND,
        server_ts=server_ts,
        open=open,
        high=max(open, close) if high is None else high,
        low=min(open, close) if low is None else low,
        close=close,
        volume=volume,
        is_closed=is_closed,
    )


def create_tick(
    minute: float = 0,
    price: float = 100.0,
    volume: float = 1.0,
    server_ts: int | None = None,
) -> Tick:
    return Tick(
        ts=T0 + int(minute * MINUTE), price=price, volume=volume, server_ts=server_ts
    )


def starts(bars: list[Bar]) -> list[tuple[str, float]]:
    """(resolution, minutes after T0) of the bars, to compare them at a glance."""
    return [(repr(bar.resolution), (bar.start_ts - T0) / MINUTE) for bar in bars]


class TestGetBarWindow:
    @pytest.mark.parametrize(
        "resolution, ts, start_ts, end_ts",
        [
            ("1s", T0 + 1, T0, T0 + SECOND),
            ("1m", T0 + 59 * SECOND, T0, T0 + MINUTE),
            ("5m", T0 + 7 * MINUTE, T0 + 5 * MINUTE, T0 + 10 * MINUTE),
            ("1h", T0 + 90 * MINUTE, T0 + HOUR, T0 + 2 * HOUR),
            ("1d", T0 + 25 * HOUR, T0 + DAY, T0 + 2 * DAY),
        ],
    )
    def test_window_of_a_ts(self, resolution: str, ts: int, start_ts: int, end_ts: int):
        assert get_bar_window(ts, Resolution(resolution)) == (start_ts, end_ts)

    def test_start_is_inclusive(self):
        assert get_bar_window(T0, Resolution("5m")) == (T0, T0 + 5 * MINUTE)

    def test_end_is_exclusive(self):
        assert get_bar_window(T0 + 5 * MINUTE, Resolution("5m")) == (
            T0 + 5 * MINUTE,
            T0 + 10 * MINUTE,
        )
        assert get_bar_window(T0 + 5 * MINUTE - 1, Resolution("5m")) == (
            T0,
            T0 + 5 * MINUTE,
        )

    @pytest.mark.parametrize(
        "resolution, shift, shift_ns",
        [
            ("1h", 30, 30 * MINUTE),
            ("5m", 30, 30 * SECOND),
            ("1d", 8, 8 * HOUR),
        ],
    )
    def test_shift_counts_in_the_next_smaller_unit(
        self, resolution: str, shift: int, shift_ns: int
    ):
        resolution_ = Resolution(resolution)
        duration = resolution_.to_seconds() * SECOND
        assert get_bar_window(T0 + shift_ns, resolution_, shift) == (
            T0 + shift_ns,
            T0 + shift_ns + duration,
        )

    def test_ts_in_the_early_part_of_a_shifted_bar_stays_in_that_bar(self):
        # the 1h bar with shift=30 that covers 00:10 is 23:30 to 00:30
        assert get_bar_window(T0 + 10 * MINUTE, Resolution("1h"), 30) == (
            T0 - 30 * MINUTE,
            T0 + 30 * MINUTE,
        )

    def test_second_bars_cannot_be_shifted(self):
        with pytest.raises(ValueError, match="can't be shifted"):
            get_bar_window(T0, Resolution("5s"), 1)

    @pytest.mark.parametrize(
        "resolution, shift",
        [("1m", -1), ("1m", 60), ("1h", 60), ("1d", 24)],
    )
    def test_shift_out_of_range_raises(self, resolution: str, shift: int):
        with pytest.raises(ValueError, match="must be >= 0"):
            get_bar_window(T0, Resolution(resolution), shift)

    def test_largest_shift_is_allowed(self):
        assert get_bar_window(T0, Resolution("1m"), 59)[0] == T0 - MINUTE + 59 * SECOND
        assert get_bar_window(T0, Resolution("1d"), 23)[0] == T0 - DAY + 23 * HOUR


class TestBar:
    @pytest.mark.parametrize(
        "kwargs, error",
        [
            ({"open": 101.0, "high": 100.0, "low": 99.0, "close": 100.0}, "high"),
            ({"open": 100.0, "high": 100.0, "low": 99.0, "close": 101.0}, "high"),
            ({"open": 99.0, "high": 101.0, "low": 100.0, "close": 100.0}, "low"),
            ({"open": 100.0, "high": 101.0, "low": 100.0, "close": 99.0}, "low"),
            ({"open": 100.0, "high": 99.0, "low": 101.0, "close": 100.0}, "high"),
            ({"open": 100.0, "volume": -1.0}, "volume"),
        ],
    )
    def test_invalid_values_raise(self, kwargs: dict[str, Any], error: str):
        with pytest.raises(ValueError, match=error):
            create_bar(**kwargs)

    @pytest.mark.parametrize("end_ts", [T0, T0 - 1])
    def test_start_ts_must_be_before_end_ts(self, end_ts: int):
        with pytest.raises(ValueError, match="start_ts"):
            Bar(
                resolution=Resolution("1m"),
                start_ts=T0,
                end_ts=end_ts,
                updated_ts=T0,
                open=1.0,
                high=1.0,
                low=1.0,
                close=1.0,
                volume=1.0,
                is_closed=False,
            )

    @pytest.mark.parametrize("price", [0.0, -37.63])
    def test_zero_and_negative_prices_are_allowed(self, price: float):
        assert create_bar(open=price).close == price

    def test_zero_volume_is_allowed(self):
        assert create_bar(volume=0.0).volume == 0.0

    def test_datetimes(self):
        bar = create_bar("5m", minute=5)
        assert bar.start_dt == datetime(2026, 1, 1, 0, 5, tzinfo=UTC)
        assert bar.end_dt == datetime(2026, 1, 1, 0, 10, tzinfo=UTC)
        assert bar.updated_dt == datetime(2026, 1, 1, 0, 9, 59, tzinfo=UTC)

    def test_str_of_a_closed_bar(self):
        assert str(create_bar("5m", open=100.0, close=101.0, volume=2.0)) == (
            "[Bar ●] 5_MINUTE | 2026-01-01 00:00:00 → 00:05:00\n"
            "  O=100.0 | H=101.0 | L=100.0 | C=101.0 | volume=2.0 (update@00:04:59.000)"
        )

    def test_str_of_an_open_bar(self):
        assert str(create_bar(is_closed=False)).startswith("[Bar ○] ")

    def test_str_shows_the_end_date_when_it_is_another_day(self):
        assert "2026-01-01 00:00:00 → 2026-01-02 00:00:00" in str(create_bar("1d"))


class TestBarSerialization:
    @staticmethod
    def _encode(value: Any) -> bytes:
        return msgspec.json.encode(value, enc_hook=repr)

    @staticmethod
    def _decode(data: bytes, type_: Any) -> Any:
        def dec_hook(type_: type, value: Any) -> Any:
            return Resolution(value) if type_ is Resolution else value

        return msgspec.json.decode(data, type=type_, dec_hook=dec_hook)

    def test_round_trip(self):
        bar = create_bar("5m", server_ts=T0)
        assert self._decode(self._encode(bar), Bar) == bar

    @pytest.mark.parametrize("value", [create_bar(), create_tick()])
    def test_tag_tells_a_bar_from_a_tick(self, value: Bar | Tick):
        assert type(self._decode(self._encode(value), Tick | Bar)) is type(value)

    def test_decode_rejects_timestamps_in_seconds(self):
        raw = msgspec.json.decode(self._encode(create_bar()))
        raw["start_ts"] = T0 // SECOND
        with pytest.raises(msgspec.ValidationError):
            self._decode(msgspec.json.encode(raw), Bar)

    def test_decode_runs_the_same_checks_as_the_constructor(self):
        raw = msgspec.json.decode(self._encode(create_bar()))
        raw["volume"] = -1.0
        with pytest.raises(msgspec.ValidationError, match="volume"):
            self._decode(msgspec.json.encode(raw), Bar)


class TestBarDataInit:
    @pytest.mark.parametrize("resolution", ["1t", "1q", "1w", "1mo", "1y"])
    def test_rejects_non_bar_resolutions(self, resolution: str):
        with pytest.raises(ValueError, match="not a bar resolution"):
            create_data(resolution)

    def test_rejects_shift_of_second_bars(self):
        with pytest.raises(ValueError, match="can't be shifted"):
            create_data("5s", shift=1)

    def test_rejects_shift_out_of_range(self):
        with pytest.raises(ValueError, match="must be >= 0"):
            create_data("1h", shift=60)

    def test_starts_without_a_bar(self):
        data = create_data()
        assert data.bar is None
        assert data.shift == 0

    def test_aliases(self):
        data = create_data("1m")
        data.update(create_bar())
        assert data.bar is not None
        assert data.kline is data.bar
        assert data.candlestick is data.bar


class TestBarDataIdentity:
    def test_shift_is_part_of_the_identity(self):
        assert create_data("5m", shift=30) != create_data("5m")
        assert create_data("5m", shift=30) == create_data("5m", shift=30)
        assert (
            len({create_data("5m"), create_data("5m"), create_data("5m", shift=30)})
            == 2
        )

    def test_other_type_is_not_equal(self):
        assert create_data() != "5m"

    def test_different_product_is_not_equal(self):
        assert create_data(symbol="BTCUSDT") != create_data(symbol="ETHUSDT")

    def test_pickled_copy_matches_the_original(self):
        m5 = create_data("5m", shift=30)
        pickled_m5 = pickle.loads(pickle.dumps(m5))
        assert pickled_m5 == m5
        assert pickled_m5 in {m5}

    def test_pickling_keeps_the_links_and_the_bar(self):
        m1, m5 = create_data("1m"), create_data("5m")
        m5.bind_resampler(m1)
        m1.update(create_bar())
        pickled_m5 = pickle.loads(pickle.dumps(m5))
        assert pickled_m5.bar == m5.bar
        assert pickled_m5.get_resampler().get_resamplees()[0] is pickled_m5

    def test_to_dict(self):
        m5 = create_data("5m", shift=30)
        assert m5.to_dict() == {
            "product": m5.product.model_dump(),
            "resolution": "5m",
            "shift": 30,
        }


class TestBarDataStr:
    def test_without_a_bar(self):
        assert str(create_data("5m")) == "[BarData ○] BYBIT_BTCUSDT | 5_MINUTE"

    def test_with_an_open_bar(self):
        data = create_data("5m")
        data.update(create_bar("5m", is_closed=False))
        assert str(data).startswith(
            "[BarData ○] BYBIT_BTCUSDT | 5_MINUTE | 2026-01-01 00:00:00 → 00:05:00\n  O=100.0"
        )

    def test_with_a_closed_bar(self):
        data = create_data("5m")
        data.update(create_bar("5m"))
        assert str(data).startswith("[BarData ●] BYBIT_BTCUSDT | 5_MINUTE | ")


class TestBindResampler:
    @pytest.mark.parametrize(
        "resolution, shift, resampler_resolution, resampler_shift",
        [
            ("5m", 0, "1m", 0),
            ("1h", 0, "5m", 0),
            ("1d", 0, "1h", 0),
            ("1m", 0, "1s", 0),
            ("1h", 30, "5m", 0),  # 00:30 to 01:30 is made of 5m bars
            ("1h", 30, "1m", 0),
            ("1d", 8, "1h", 0),
            ("5m", 30, "1s", 0),  # 00:00:30 to 00:05:30 is made of 1s bars
            ("5m", 30, "1m", 30),  # both are 30 seconds late
        ],
    )
    def test_bars_that_fit(
        self,
        resolution: str,
        shift: int,
        resampler_resolution: str,
        resampler_shift: int,
    ):
        data = create_data(resolution, shift=shift)
        resampler = create_data(resampler_resolution, shift=resampler_shift)
        data.bind_resampler(resampler)
        assert data.get_resampler() is resampler

    @pytest.mark.parametrize(
        "resolution, shift, resampler_resolution, resampler_shift",
        [
            ("5m", 0, "3m", 0),  # not a whole number of 3m bars
            ("1h", 0, "7m", 0),
            ("5m", 30, "1m", 0),  # 1m bars don't start 30 seconds late
            ("5m", 0, "1m", 30),  # the other way around
            ("1h", 7, "5m", 0),  # 5m bars don't start at minute 7
            ("1h", 30, "1m", 30),  # 1m bars start at second 30, the 1h bar at second 0
        ],
    )
    def test_bars_that_do_not_fit_raise(
        self,
        resolution: str,
        shift: int,
        resampler_resolution: str,
        resampler_shift: int,
    ):
        data = create_data(resolution, shift=shift)
        resampler = create_data(resampler_resolution, shift=resampler_shift)
        with pytest.raises(ValueError, match="do not fit"):
            data.bind_resampler(resampler)
        assert not data.is_resamplee()
        assert not resampler.is_resampler()

    def test_other_data_types_raise(self):
        with pytest.raises(TypeError, match="must be TickData or BarData"):
            other_data = OtherData(create_product(), Resolution("1m"))
            create_data("5m").bind_resampler(other_data)  # ty: ignore[invalid-argument-type]

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


class ForwardingData(BarData):
    """Closes whatever closed_bars it is told to, and records what it receives."""

    def __init__(self, resolution: str, closed_bars: list[Bar] | None = None):
        super().__init__(create_product(), Resolution(resolution))
        self.closed_bars: list[Bar] = closed_bars or []
        self.received: list[Tick | Bar] = []

    def _update(self, value: Tick | Bar) -> list[Bar]:
        self.received.append(value)
        return self.closed_bars


def create_forwarding_data(
    resolution: str = "1m", closed_bars: list[Bar] | None = None
) -> ForwardingData:
    return ForwardingData(resolution, closed_bars)


TICK = create_tick()
BAR_A, BAR_B, BAR_C = create_bar(minute=0), create_bar(minute=1), create_bar(minute=2)


class TestForwarding:
    def test_without_closed_bars_resamplees_receive_nothing(self):
        m1, m5 = create_forwarding_data("1m"), create_forwarding_data("5m")
        m5.bind_resampler(m1)
        assert m1.update(TICK) == []
        assert m1.received == [TICK]
        assert m5.received == []

    def test_each_closed_bar_goes_to_every_resamplee_oldest_first(self):
        m1, m5, m15 = (
            create_forwarding_data("1m", [BAR_A, BAR_B]),
            create_forwarding_data("5m"),
            create_forwarding_data("15m"),
        )
        m5.bind_resampler(m1)
        m15.bind_resampler(m1)
        assert m1.update(TICK) == [BAR_A, BAR_B]
        assert m5.received == [BAR_A, BAR_B]
        assert m15.received == [BAR_A, BAR_B]

    def test_returns_all_closed_bars_finest_first(self):
        m1, m5, h1 = (
            create_forwarding_data("1m", [BAR_A]),
            create_forwarding_data("5m", [BAR_B]),
            create_forwarding_data("1h", [BAR_C]),
        )
        m5.bind_resampler(m1)
        h1.bind_resampler(m5)
        assert m1.update(TICK) == [
            BAR_A,
            BAR_B,
            BAR_C,
        ]
        assert m5.received == [BAR_A]
        assert h1.received == [BAR_B]

    def test_unbound_resamplee_receives_nothing(self):
        m1, m5 = (
            create_forwarding_data("1m", [BAR_A]),
            create_forwarding_data("5m"),
        )
        m5.bind_resampler(m1)
        m5.unbind_resampler()
        m1.update(TICK)
        assert m5.received == []


class TestUpdateValidation:
    def test_coarser_bar_raises(self):
        with pytest.raises(ValueError, match="coarser"):
            create_data("1m").update(create_bar("5m"))

    def test_finer_bar_that_is_not_closed_raises(self):
        with pytest.raises(ValueError, match="not closed"):
            create_data("5m").update(create_bar("1m", is_closed=False))

    def test_finer_bar_across_two_windows_raises(self):
        with pytest.raises(ValueError, match="does not fit"):
            create_data("5m").update(create_bar("3m", minute=3))

    def test_same_resolution_bar_outside_the_shifted_window_raises(self):
        with pytest.raises(ValueError, match="not in the window"):
            create_data("1h", shift=30).update(create_bar("1h"))

    def test_same_resolution_bar_in_the_shifted_window_is_accepted(self):
        data = create_data("1h", shift=30)
        data.update(create_bar("1h", minute=30))
        assert data.bar is not None

    def test_unshifted_same_resolution_bar_keeps_the_venues_window(self):
        # e.g. a venue's daily bar that doesn't start at 00:00 UTC
        data = create_data("1d")
        bar = create_bar("1d", minute=8 * 60)
        data.update(bar)
        assert data.bar is bar


class TestSameResolutionUpdate:
    def test_replaces_the_current_bar(self):
        data = create_data("1m")
        first = create_bar(close=101.0, volume=5.0, is_closed=False)
        second = create_bar(close=102.0, volume=7.0, is_closed=False)
        assert data.update(first) == []
        assert data.bar is first
        assert data.update(second) == []
        assert data.bar is second  # not added to the first one

    def test_returns_the_bar_that_closes(self):
        data = create_data("1m")
        data.update(create_bar(is_closed=False))
        closed = create_bar()
        assert data.update(closed) == [closed]

    def test_older_window_is_ignored(self):
        data = create_data("1m")
        current = create_bar(minute=5, is_closed=False)
        data.update(current)
        assert data.update(create_bar(minute=4)) == []
        assert data.bar is current

    def test_same_window_after_close_is_ignored(self):
        data = create_data("1m")
        closed = create_bar()
        data.update(closed)
        assert data.update(create_bar(close=999.0)) == []
        assert data.bar is closed

    def test_later_window_closes_the_open_bar_with_its_last_state(self):
        data = create_data("1m")
        data.update(create_bar(close=101.0, is_closed=False))
        later = create_bar(minute=1, is_closed=False)
        closed_bars = data.update(later)
        assert starts(closed_bars) == [("1m", 0)]
        assert closed_bars[0].is_closed
        assert closed_bars[0].close == 101.0
        assert data.bar is later

    def test_two_bars_close_when_a_closed_bar_skips_an_open_one(self):
        data = create_data("1m")
        data.update(create_bar(is_closed=False))
        later = create_bar(minute=10)
        closed_bars = data.update(later)
        assert starts(closed_bars) == [("1m", 0), ("1m", 10)]
        assert all(bar.is_closed for bar in closed_bars)

    def test_later_window_after_a_closed_bar_closes_nothing_again(self):
        data = create_data("1m")
        data.update(create_bar())
        assert data.update(create_bar(minute=1, is_closed=False)) == []


class TestMergeTicks:
    def test_first_tick_opens_the_window_it_falls_in(self):
        data = create_data("5m")
        assert (
            data.update(create_tick(minute=7, price=100.0, volume=2.0, server_ts=T0))
            == []
        )
        bar = data.bar
        assert bar is not None
        assert bar.resolution == Resolution("5m")
        assert (bar.start_ts, bar.end_ts) == (T0 + 5 * MINUTE, T0 + 10 * MINUTE)
        assert (bar.open, bar.high, bar.low, bar.close, bar.volume) == (
            100.0,
            100.0,
            100.0,
            100.0,
            2.0,
        )
        assert bar.updated_ts == T0 + 7 * MINUTE
        assert bar.server_ts == T0
        assert not bar.is_closed

    def test_ticks_in_the_window_are_added(self):
        data = create_data("5m")
        for minute, price in [(0, 100.0), (1, 105.0), (2, 95.0), (3, 101.0)]:
            data.update(
                create_tick(
                    minute=minute, price=price, volume=2.0, server_ts=T0 + minute
                )
            )
        bar = data.bar
        assert bar is not None
        assert (bar.open, bar.high, bar.low, bar.close, bar.volume) == (
            100.0,
            105.0,
            95.0,
            101.0,
            8.0,
        )
        assert bar.updated_ts == T0 + 3 * MINUTE
        assert bar.server_ts == T0 + 3
        assert not bar.is_closed

    def test_tick_at_the_end_of_the_window_opens_the_next_bar_and_closes_the_current_one(
        self,
    ):
        data = create_data("5m")
        data.update(create_tick(minute=0, price=100.0, volume=2.0))
        closed_bars = data.update(create_tick(minute=5, price=110.0, volume=3.0))
        assert starts(closed_bars) == [("5m", 0)]
        assert closed_bars[0].is_closed
        assert (closed_bars[0].close, closed_bars[0].volume) == (100.0, 2.0)
        assert data.bar is not None
        assert data.bar.start_ts == T0 + 5 * MINUTE
        assert (data.bar.open, data.bar.volume) == (110.0, 3.0)
        assert not data.bar.is_closed

    def test_last_tick_of_the_window_does_not_close_the_bar(self):
        data = create_data("5m")
        assert data.update(Tick(ts=T0 + 5 * MINUTE - 1, price=100.0, volume=1.0)) == []
        assert data.bar is not None
        assert not data.bar.is_closed

    def test_older_tick_is_ignored(self):
        data = create_data("5m")
        data.update(create_tick(minute=5, price=100.0))
        current = data.bar
        assert data.update(create_tick(minute=4, price=999.0)) == []
        assert data.bar is current

    def test_tick_in_a_closed_window_is_ignored(self):
        data = create_data("5m")
        data.update(create_tick(minute=0))
        data.close()
        closed = data.bar
        assert data.update(create_tick(minute=1, price=999.0)) == []
        assert data.bar is closed

    def test_shifted_window(self):
        data = create_data("1h", shift=30)
        data.update(create_tick(minute=10))
        assert data.bar is not None
        assert (data.bar.start_ts, data.bar.end_ts) == (
            T0 - 30 * MINUTE,
            T0 + 30 * MINUTE,
        )


class TestMergeFinerBars:
    def test_first_bar_opens_the_window_it_falls_in(self):
        data = create_data("5m")
        m1_bar = create_bar(
            minute=7,
            open=100.0,
            high=102.0,
            low=99.0,
            close=101.0,
            volume=2.0,
            server_ts=T0,
        )
        assert data.update(m1_bar) == []
        bar = data.bar
        assert bar is not None
        assert (bar.start_ts, bar.end_ts) == (T0 + 5 * MINUTE, T0 + 10 * MINUTE)
        assert (bar.open, bar.high, bar.low, bar.close, bar.volume) == (
            100.0,
            102.0,
            99.0,
            101.0,
            2.0,
        )
        assert bar.updated_ts == m1_bar.updated_ts
        assert bar.server_ts == T0
        assert not bar.is_closed

    def test_bars_in_the_window_are_merged(self):
        data = create_data("5m")
        data.update(
            create_bar(
                minute=0, open=100.0, high=102.0, low=99.0, close=101.0, volume=10.0
            )
        )
        data.update(
            create_bar(
                minute=1, open=101.0, high=105.0, low=100.0, close=103.0, volume=20.0
            )
        )
        data.update(
            create_bar(
                minute=2, open=103.0, high=104.0, low=95.0, close=98.0, volume=30.0
            )
        )
        bar = data.bar
        assert bar is not None
        assert (bar.open, bar.high, bar.low, bar.close, bar.volume) == (
            100.0,
            105.0,
            95.0,
            98.0,
            60.0,
        )
        assert not bar.is_closed

    def test_bar_that_ends_with_the_window_closes_it(self):
        data = create_data("5m")
        for minute in range(4):
            assert data.update(create_bar(minute=minute, volume=1.0)) == []
        closed_bars = data.update(create_bar(minute=4, volume=1.0))
        assert starts(closed_bars) == [("5m", 0)]
        assert closed_bars[0] is data.bar
        assert closed_bars[0].is_closed
        assert closed_bars[0].volume == 5.0

    def test_single_bar_can_open_and_close_a_window(self):
        data = create_data("5m")
        closed_bars = data.update(create_bar(minute=4))
        assert starts(closed_bars) == [("5m", 0)]

    def test_later_window_closes_the_open_bar_with_its_last_state(self):
        data = create_data("5m")
        data.update(create_bar(minute=0, close=101.0, volume=2.0))
        closed_bars = data.update(create_bar(minute=5, volume=3.0))
        assert starts(closed_bars) == [("5m", 0)]
        assert closed_bars[0].is_closed
        assert (closed_bars[0].close, closed_bars[0].volume) == (101.0, 2.0)
        assert data.bar is not None
        assert data.bar.start_ts == T0 + 5 * MINUTE
        assert data.bar.volume == 3.0

    def test_two_bars_close_after_a_gap(self):
        data = create_data("5m")
        data.update(create_bar(minute=0, volume=2.0))
        closed_bars = data.update(
            create_bar(minute=9, volume=3.0)
        )  # ends with the 5m bar from minute 5 to 10
        assert starts(closed_bars) == [("5m", 0), ("5m", 5)]
        assert [bar.volume for bar in closed_bars] == [2.0, 3.0]
        assert all(bar.is_closed for bar in closed_bars)

    def test_windows_in_a_gap_stay_missing(self):
        data = create_data("5m")
        data.update(create_bar(minute=0))
        assert starts(data.update(create_bar(minute=24))) == [("5m", 0), ("5m", 20)]

    def test_older_bar_is_ignored(self):
        data = create_data("5m")
        data.update(create_bar(minute=5))
        current = data.bar
        assert data.update(create_bar(minute=4, close=999.0)) == []
        assert data.bar is current

    def test_bar_in_a_closed_window_is_ignored(self):
        data = create_data("5m")
        data.update(create_bar(minute=4))
        closed = data.bar
        assert data.update(create_bar(minute=3, close=999.0)) == []
        assert data.bar is closed

    def test_shifted_window_closes_on_its_own_end(self):
        data = create_data("1h", shift=30)
        assert data.update(create_bar(minute=30)) == []
        assert starts(data.update(create_bar(minute=89))) == [("1h", 30)]


class TestClose:
    def test_without_a_bar_does_nothing(self):
        assert create_data().close() == []

    def test_closes_the_open_bar(self):
        data = create_data("1m")
        open_bar = create_bar(close=101.0, is_closed=False)
        data.update(open_bar)
        closed_bars = data.close()
        assert closed_bars == [data.bar]
        assert closed_bars[0].is_closed
        assert closed_bars[0].close == 101.0
        assert not open_bar.is_closed

    def test_already_closed_bar_does_nothing(self):
        data = create_data("1m")
        data.update(create_bar())
        assert data.close() == []

    def test_second_close_does_nothing(self):
        data = create_data("1m")
        data.update(create_bar(is_closed=False))
        data.close()
        assert data.close() == []

    def test_later_update_for_the_closed_window_is_ignored(self):
        data = create_data("1m")
        data.update(create_bar(is_closed=False))
        closed_bars = data.close()
        assert data.update(create_bar(close=999.0)) == []
        assert data.bar is closed_bars[0]

    def test_next_window_still_updates(self):
        data = create_data("1m")
        data.update(create_bar(is_closed=False))
        data.close()
        later = create_bar(minute=1, is_closed=False)
        assert data.update(later) == []  # the closed bar is not returned twice
        assert data.bar is later

    def test_updates_the_resamplee(self):
        m1, m5 = create_data("1m"), create_data("5m")
        m5.bind_resampler(m1)
        m1.update(create_bar(volume=2.0, is_closed=False))
        assert m5.bar is None
        assert starts(m1.close()) == [("1m", 0)]
        assert m5.bar is not None
        assert m5.bar.volume == 2.0

    def test_closes_the_chain_when_the_bar_ends_the_windows(self):
        m1, m5, h1 = create_data("1m"), create_data("5m"), create_data("1h")
        m5.bind_resampler(m1)
        h1.bind_resampler(m5)
        m1.update(create_bar(minute=59, is_closed=False))
        assert starts(m1.close()) == [("1m", 59), ("5m", 55), ("1h", 0)]

    def test_closing_a_resamplee_does_not_touch_its_resampler(self):
        m1, m5 = create_data("1m"), create_data("5m")
        m5.bind_resampler(m1)
        m1.update(create_bar(minute=0))
        assert starts(m5.close()) == [("5m", 0)]
        assert m1.bar is not None


class TestChain:
    def test_open_updates_do_not_reach_the_resamplee(self):
        m1, m5 = create_data("1m"), create_data("5m")
        m5.bind_resampler(m1)
        assert m1.update(create_bar(is_closed=False)) == []
        assert m5.bar is None

    def test_volume_is_counted_once_through_the_chain(self):
        m1, m5, h1 = create_data("1m"), create_data("5m"), create_data("1h")
        m5.bind_resampler(m1)
        h1.bind_resampler(m5)
        all_closed_bars: list[Bar] = []
        for minute in range(60):
            m1.update(create_bar(minute=minute, volume=1.0, is_closed=False))
            all_closed_bars += m1.update(create_bar(minute=minute, volume=2.0))
        assert len(all_closed_bars) == 60 + 12 + 1
        assert [
            bar.volume for bar in all_closed_bars if bar.resolution == Resolution("5m")
        ] == [10.0] * 12
        assert h1.bar is not None
        assert h1.bar.is_closed
        assert h1.bar.volume == 120.0

    def test_ohlc_through_the_chain(self):
        m1, m5, h1 = create_data("1m"), create_data("5m"), create_data("1h")
        m5.bind_resampler(m1)
        h1.bind_resampler(m5)
        for minute in range(60):
            m1.update(
                create_bar(minute=minute, open=100.0 + minute, close=101.0 + minute)
            )
        assert h1.bar is not None
        assert (h1.bar.open, h1.bar.high, h1.bar.low, h1.bar.close) == (
            100.0,
            160.0,
            100.0,
            160.0,
        )

    def test_closed_bars_are_returned_finest_first(self):
        m1, m5, h1 = create_data("1m"), create_data("5m"), create_data("1h")
        m5.bind_resampler(m1)
        h1.bind_resampler(m5)
        assert starts(m1.update(create_bar(minute=59))) == [
            ("1m", 59),
            ("5m", 55),
            ("1h", 0),
        ]

    def test_same_resolution_bar_skipping_an_open_one_feeds_both_to_the_resamplee(self):
        m1, m5 = create_data("1m"), create_data("5m")
        m5.bind_resampler(m1)
        m1.update(create_bar(minute=0, volume=2.0, is_closed=False))
        closed_bars = m1.update(create_bar(minute=1, volume=3.0))
        assert starts(closed_bars) == [("1m", 0), ("1m", 1)]
        assert m5.bar is not None
        assert m5.bar.volume == 5.0

    def test_gap_in_the_resampler_closes_two_resamplee_bars(self):
        m1, m5 = create_data("1m"), create_data("5m")
        m5.bind_resampler(m1)
        m1.update(create_bar(minute=0))
        closed_bars = m1.update(create_bar(minute=9))
        assert starts(closed_bars) == [("1m", 9), ("5m", 0), ("5m", 5)]

    def test_shifted_resamplee_in_a_chain(self):
        m1, h1 = create_data("1m"), create_data("1h", shift=30)
        h1.bind_resampler(m1)
        for minute in range(30, 89):
            assert starts(m1.update(create_bar(minute=minute))) == [("1m", minute)]
        assert starts(m1.update(create_bar(minute=89))) == [("1m", 89), ("1h", 30)]

    def test_resampler_with_many_resamplees(self):
        m1, m5, m15 = create_data("1m"), create_data("5m"), create_data("15m")
        m5.bind_resampler(m1)
        m15.bind_resampler(m1)
        assert starts(m1.update(create_bar(minute=14))) == [
            ("1m", 14),
            ("5m", 10),
            ("15m", 0),
        ]
