from __future__ import annotations

from typing import TYPE_CHECKING, Annotated, Any

if TYPE_CHECKING:
    from pfund_blocks.entities.products.product_base import BaseProduct

from datetime import datetime

from msgspec import Meta, structs

from pfund_blocks.datas.data_point_base import BaseDataPoint
from pfund_blocks.datas.market_data import MarketData
from pfund_blocks.datas.tick_data import Tick, TickData
from pfund_blocks.resolution import Resolution
from pfund_blocks.utils.temporal import NS_PER_SECOND, ns_to_dt


def get_bar_window(ts: int, resolution: Resolution, shift: int = 0) -> tuple[int, int]:
    """Returns the (start_ts, end_ts) of the bar that ts falls in, all int64 ns since epoch.

    start_ts is inclusive and end_ts is exclusive, i.e. end_ts is the start_ts of the next bar.

    Args:
        ts: the timestamp to find the bar for.
        resolution: must be a bar resolution, i.e. second, minute, hour or day.
        shift: moves the bar forward, in the next smaller unit of the resolution.
            e.g. for a 1h bar, shift=30 means the bar is 9:30 to 10:30 instead of 9:00 to 10:00.
            Second bars can't be shifted.
    """
    if shift and resolution.is_second():
        raise ValueError(f"{resolution!r} can't be shifted, there is no smaller unit than a second")
    max_shift = 24 if resolution.is_day() else 60
    if not 0 <= shift < max_shift:
        raise ValueError(f"{shift=} must be >= 0 and < {max_shift} for {resolution!r}")
    shift_ns = shift * resolution.timeframe.value * NS_PER_SECOND // max_shift
    resolution_ns = resolution.to_seconds() * NS_PER_SECOND
    # subtract the shift before flooring so that a ts in the early part of a shifted bar stays in that bar
    start_ts = (ts - shift_ns) // resolution_ns * resolution_ns + shift_ns
    return start_ts, start_ts + resolution_ns


class Bar(BaseDataPoint, kw_only=True, frozen=True):
    """The full state of a bar at updated_ts, an update replaces the previous Bar instead of adding to it."""

    resolution: Resolution
    # timestamps below are int64 ns since epoch; gt-bound catches passing seconds by mistake
    start_ts: Annotated[int, Meta(gt=10_000_000_000)]
    end_ts: Annotated[int, Meta(gt=10_000_000_000)]
    updated_ts: Annotated[int, Meta(gt=10_000_000_000)]  # when this state was produced, after end_ts if the venue confirms a closed bar late
    # NOTE: prices are not bound to > 0 on purpose, they can be zero or negative, e.g. WTI futures in 2020, calendar spreads
    open: float
    high: float
    low: float
    close: float
    volume: float
    is_closed: bool

    def __post_init__(self):
        if self.start_ts >= self.end_ts:
            raise ValueError(f"start_ts ({self.start_ts}) must be < end_ts ({self.end_ts})")
        if self.high < max(self.open, self.low, self.close):
            raise ValueError(f"high ({self.high}) must be >= open, low and close")
        if self.low > min(self.open, self.high, self.close):
            raise ValueError(f"low ({self.low}) must be <= open, high and close")
        if self.volume < 0:
            raise ValueError(f"volume ({self.volume}) must be >= 0")

    def __str__(self):
        return self._format(f"[Bar {self._closed_mark}]")

    @property
    def _closed_mark(self) -> str:
        return "●" if self.is_closed else "○"

    def _format(self, header: str) -> str:
        start_dt, end_dt = self.start_dt, self.end_dt
        end_format = "%H:%M:%S" if start_dt.date() == end_dt.date() else "%Y-%m-%d %H:%M:%S"
        header = f"{header} {self.resolution} | {start_dt:%Y-%m-%d %H:%M:%S} → {end_dt:{end_format}}"
        ohlcv = f"  O={self.open} | H={self.high} | L={self.low} | C={self.close} | volume={self.volume} (update@{self.updated_dt:%H:%M:%S.%f}"[:-3] + ")"
        return f"{header}\n{ohlcv}"

    @property
    def start_dt(self) -> datetime:
        return ns_to_dt(self.start_ts)

    @property
    def end_dt(self) -> datetime:
        return ns_to_dt(self.end_ts)

    @property
    def updated_dt(self) -> datetime:
        return ns_to_dt(self.updated_ts)


type ClosedBar = Bar  # a Bar with is_closed=True


class BarData(MarketData):
    def __init__(self, product: BaseProduct, resolution: Resolution, shift: int = 0):
        """
        Args:
            shift: see get_bar_window(), a venue's bar can't be shifted afterwards,
                so update() rejects a bar that is not in the shifted window.
        """
        if not resolution.is_bar():
            raise ValueError(f"{resolution!r} is not a bar resolution")
        if shift:
            get_bar_window(0, resolution, shift)  # raises if the shift is invalid for the resolution
        super().__init__(product, resolution)
        self.shift: int = shift
        self._bar: Bar | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            **super().to_dict(),
            "shift": self.shift,
        }

    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, BarData):
            return NotImplemented
        return (self.product, self.resolution, self.shift) == (other.product, other.resolution, other.shift)

    def __hash__(self):
        return hash((self.product, self.resolution, self.shift))

    def __str__(self):
        if self._bar is None:
            return f"[BarData ○] {self.product.name} | {self.resolution}"
        return self._bar._format(f"[BarData {self._bar._closed_mark}] {self.product.name} |")

    @property
    def bar(self) -> Bar | None:
        return self._bar
    kline = bar
    candlestick = bar

    def bind_resampler(self, resampler: TickData | BarData):
        """Resamples this data from the resampler, see MarketData.bind_resampler().

        A resampler's bars must fit in this data's windows, otherwise binding raises, instead of the first bar
        that doesn't fit raising mid-session. e.g. a 3m bar from 9:03 to 9:06 can't fit in a 5m bar.
        """
        if not isinstance(resampler, (TickData, BarData)):
            raise TypeError(f"resampler must be TickData or BarData, got {type(resampler).__name__}")
        # NOTE: a resampler that isn't finer is rejected by MarketData.bind_resampler()
        if isinstance(resampler, BarData) and resampler.resolution > self.resolution:
            # any window of this data and the resampler's bar it starts in, the same holds for all the other windows
            start_ts, end_ts = get_bar_window(0, self.resolution, self.shift)
            resampler_start_ts, resampler_end_ts = get_bar_window(start_ts, resampler.resolution, resampler.shift)
            starts_together = resampler_start_ts == start_ts  # e.g. 1m bars with shift=0 don't start with 5m bars with shift=30
            is_whole_number = (end_ts - start_ts) % (resampler_end_ts - resampler_start_ts) == 0  # e.g. a 5m bar isn't a whole number of 3m bars
            if not (starts_together and is_whole_number):
                raise ValueError(
                    f"{resampler.resolution!r} bars with shift={resampler.shift} do not fit in {self.resolution!r} bars with shift={self.shift}"
                )
        super().bind_resampler(resampler)

    def _update(self, value: Tick | Bar) -> list[ClosedBar]:
        """Updates the current bar, returns the bars closed by this update, oldest first.

        A bar in the same resolution replaces the current bar, since it is its full state.
        A tick or a finer closed bar is merged into the current bar, this is how a bar is resampled.

        Anything older than the current bar, or for a window that has already closed, is ignored.

        Usually zero or one bar is returned. Two are returned when the current bar never received
        its close and the incoming value is for a later window and also closes a bar.
        e.g. after a disconnection, the current bar is at t=0 and the incoming closed bar is at t=10:
            - returns the t=0 bar marked as closed, then the t=10 bar.
            - the t=0 bar only has its last known state, so it may be incomplete.
            - t=1 to t=9 stay missing, they are not backfilled and the gap is not flagged here,
              the caller can see the jump from the returned bars and backfill them, e.g. via REST.

        Args:
            value: a tick, or a bar in the same or a finer resolution, a finer bar must be closed
                otherwise its volume would be counted twice.
        """
        if isinstance(value, Bar):
            self._validate_bar(value)
            if value.resolution == self.resolution:
                return self._replace(value)
        return self._merge(value)

    def _validate_bar(self, bar: Bar):
        """Raises if the bar can't update this data, whether it comes from a resampler or directly from the caller."""
        start_ts, end_ts = get_bar_window(bar.start_ts, self.resolution, self.shift)
        if bar.resolution == self.resolution:
            # NOTE: only when shifted, an unshifted bar's window is whatever the venue says, e.g. a venue's daily bar may not start at 00:00 UTC
            if self.shift and (bar.start_ts, bar.end_ts) != (start_ts, end_ts):
                raise ValueError(f"bar {bar.start_dt} → {bar.end_dt} is not in the window of {self.resolution!r} with shift={self.shift}")
        elif bar.resolution < self.resolution:
            raise ValueError(f"{bar.resolution!r} is coarser than {self.resolution!r}")
        elif not bar.is_closed:
            raise ValueError(f"{bar.resolution!r} bar is not closed, it can't be merged into {self.resolution!r}")
        # e.g. a 3m bar from 9:03 to 9:06 can't be merged into a 5m bar, part of it belongs to the next 5m bar
        elif bar.end_ts > end_ts:
            raise ValueError(f"{bar.resolution!r} bar {bar.start_dt} → {bar.end_dt} does not fit in a {self.resolution!r} bar")

    def close(self) -> list[ClosedBar]:
        """Closes the current bar if it is still open and updates all its resamplees with it, returns every bar closed by this, finest first.

        A bar only closes when an update arrives, so in a quiet market it can stay open long after its end_ts.
        Use this to stop waiting for that update, when to do so is up to the caller,
        e.g. some time after end_ts, to leave room for the venue's final update.
        Later updates for the closed window are ignored.
        """
        if self._bar is None or self._bar.is_closed:
            return []
        closed_bar = structs.replace(self._bar, is_closed=True)
        self._bar = closed_bar
        all_closed_bars = [closed_bar]
        for resamplee in self.get_resamplees():
            all_closed_bars += resamplee.update(closed_bar)
        return all_closed_bars

    def _replace(self, bar: Bar) -> list[ClosedBar]:
        """Replaces the current bar with a bar in the same resolution, returns the bars closed by this, oldest first.

        A bar in an older window, or in the same window as a closed current bar, is ignored.
        A bar in a later window also closes the current bar if it is still open, with its last known state.
        """
        current = self._bar
        closed_bars: list[ClosedBar] = []
        if current is not None:
            if bar.start_ts < current.start_ts or (bar.start_ts == current.start_ts and current.is_closed):
                return closed_bars
            # the venue never closed the current bar before moving on to a later window
            if bar.start_ts > current.start_ts and not current.is_closed:
                closed_bars.append(structs.replace(current, is_closed=True))
        self._bar = bar
        if bar.is_closed:
            closed_bars.append(bar)
        return closed_bars

    def _merge(self, value: Tick | Bar) -> list[ClosedBar]:
        """Merges a tick or a finer closed bar into the current bar, returns the bars closed by this, oldest first.

        A value in the current window is added to the current bar, a value in a later window opens a new bar,
        and also closes the current bar if it is still open, with its last known state.
        A value older than the current bar, or in the window of a closed current bar, is ignored.

        A finer bar that ends with the window closes the bar it is merged into. A tick can't,
        it only closes a bar when it opens the next one.
        """
        if isinstance(value, Tick):
            ts, updated_ts = value.ts, value.ts
            open_, high, low, close = value.price, value.price, value.price, value.price
        else:
            ts, updated_ts = value.start_ts, value.updated_ts
            open_, high, low, close = value.open, value.high, value.low, value.close
        volume = value.volume
        current = self._bar
        closed_bars: list[ClosedBar] = []
        is_new_bar = False
        # no bar yet, or the value is past the current bar: open a new bar from the value alone
        if current is None or ts >= current.end_ts:
            is_new_bar = True
            start_ts, end_ts = get_bar_window(ts, self.resolution, self.shift)
        # the value is older than the current bar, or its window has already closed: ignore it
        elif ts < current.start_ts or current.is_closed:
            return closed_bars
        # the value is in the current bar's window: add it to the current bar
        else:
            start_ts, end_ts = current.start_ts, current.end_ts
            open_, high, low, volume = current.open, max(current.high, high), min(current.low, low), current.volume + volume
        # the current bar never received its close before moving on to a later window
        if is_new_bar and current is not None and not current.is_closed:
            closed_bars.append(structs.replace(current, is_closed=True))
        self._bar = Bar(
            resolution=self.resolution,
            start_ts=start_ts,
            end_ts=end_ts,
            updated_ts=updated_ts,
            server_ts=value.server_ts,
            open=open_,
            high=high,
            low=low,
            close=close,
            volume=volume,
            # the finer bar that ends with this bar closes it, a tick can't, it only closes a bar when the next window starts
            is_closed=isinstance(value, Bar) and value.end_ts == end_ts,
        )
        if self._bar.is_closed:
            closed_bars.append(self._bar)
        return closed_bars
