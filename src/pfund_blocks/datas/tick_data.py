from __future__ import annotations

from typing import TYPE_CHECKING, Annotated

if TYPE_CHECKING:
    from pfund_blocks.datas.bar_data import ClosedBar
    from pfund_blocks.entities.products.product_base import BaseProduct
    from pfund_blocks.resolution import Resolution

from datetime import datetime

from msgspec import Meta

from pfund_blocks.datas.data_point_base import BaseDataPoint
from pfund_blocks.datas.market_data import MarketData
from pfund_blocks.utils.temporal import ns_to_dt


class Tick(BaseDataPoint, kw_only=True, frozen=True):
    """A single trade in the market."""

    ts: Annotated[int, Meta(gt=10_000_000_000)]  # when the trade happened, int64 ns since epoch
    # NOTE: price is not bound to > 0 on purpose, it can be zero or negative, e.g. WTI futures in 2020, calendar spreads
    price: float
    volume: float

    def __post_init__(self):
        if self.volume < 0:
            raise ValueError(f"volume ({self.volume}) must be >= 0")

    @property
    def dt(self) -> datetime:
        return ns_to_dt(self.ts)


class TickData(MarketData):
    def __init__(self, product: BaseProduct, resolution: Resolution):
        if not resolution.is_tick():
            raise ValueError(f"{resolution!r} is not a tick resolution")
        super().__init__(product, resolution)
        self._tick: Tick | None = None

    @property
    def tick(self) -> Tick | None:
        return self._tick

    def update(self, value: Tick) -> list[ClosedBar]:
        """Keeps the latest tick and updates all its resamplees, returns every bar closed by this update, finest first.

        A tick older than the latest tick doesn't replace it, it is still forwarded, each resamplee decides what to do with it.

        Unlike BarData.update(), every tick is forwarded instead of only closed bars,
        since a tick is not an update of a previous one, its volume can't be counted twice.
        """
        if self._tick is None or value.ts >= self._tick.ts:
            self._tick = value
        all_closed_bars: list[ClosedBar] = []
        for resamplee in self._resamplees:
            all_closed_bars += resamplee.update(value)
        return all_closed_bars
