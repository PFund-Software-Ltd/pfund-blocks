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

type Price = float
type Size = float
type QuoteLevel = tuple[Price, Size]


class Quote(BaseDataPoint, kw_only=True, frozen=True):
    """A snapshot of the bids and asks in the market, best price first."""

    ts: Annotated[int, Meta(gt=10_000_000_000)]  # when the quote was made, int64 ns since epoch
    # NOTE: price is not bound to > 0 on purpose, it can be zero or negative, e.g. WTI futures in 2020, calendar spreads
    bids: tuple[QuoteLevel, ...]
    asks: tuple[QuoteLevel, ...]

    @property
    def dt(self) -> datetime:
        return ns_to_dt(self.ts)


# TODO: a Quote is always a snapshot; OrderBook handles updates such as L2 deltas and outputs a Quote
class OrderBook:
    """DRAFT: the live state of a product's bids and asks, used to derive a Quote when a venue sends deltas.

    A Quote is always a snapshot, so deltas never leave the parsing stage:
        raw message -> venue's parser -> OrderBook -> Quote -> QuoteData.update()
    A venue that only sends full snapshots doesn't need an OrderBook, its parser converts the message to a Quote directly.

    What it should do:
    - apply_snapshot(): replaces both sides of the book
    - apply_delta(): updates the levels, a size of 0 removes the level
    - track sequence numbers and report a gap, since the book is wrong until the next snapshot arrives
    - to_quote(depth): returns the top levels as a Quote, e.g. depth=10 for 10q_L2
    - keep the levels sorted as they change, instead of sorting on every read

    How it should be handled:
    - it is venue independent, a venue's parser only translates its messages into the operations above
    - parsers stay stateless, so the book is passed into the parser
    - whoever calls the parser owns one book per channel, kept in memory:
      the WS API when it does the parsing, or pfeed's T step when pfeed parses there
    - on a gap, only the WS API can resubscribe to get a new snapshot
    - L2 only, L3 tracks individual orders so it would be a different structure, most likely not needed
    """


class QuoteData(MarketData):
    def __init__(self, product: BaseProduct, resolution: Resolution):
        if not resolution.is_quote():
            raise ValueError(f"{resolution!r} is not a quote resolution")
        super().__init__(product, resolution)
        self._quote: Quote | None = None

    @property
    def quote(self) -> Quote | None:
        return self._quote

    def update(self, value: Quote) -> list[ClosedBar]:
        """Keeps the latest quote, a quote older than the latest quote is ignored.

        Always returns an empty list, since a quote can't be resampled into bars.
        """
        if self._quote is None or value.ts >= self._quote.ts:
            self._quote = value
        return []
