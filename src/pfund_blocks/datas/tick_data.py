from __future__ import annotations

from typing import Annotated

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
    pass
