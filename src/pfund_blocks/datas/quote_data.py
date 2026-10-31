from __future__ import annotations

from pfund_blocks.datas.data_point_base import BaseDataPoint
from pfund_blocks.datas.market_data import MarketData


class Quote(BaseDataPoint, kw_only=True, frozen=True):
    pass


class QuoteData(MarketData):
    pass
