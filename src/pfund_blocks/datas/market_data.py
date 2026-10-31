from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pfund_blocks.datas.bar_data import Bar, BarData, ClosedBar
    from pfund_blocks.datas.quote_data import Quote
    from pfund_blocks.datas.tick_data import Tick, TickData
    from pfund_blocks.entities.products.product_base import BaseProduct
    from pfund_blocks.resolution import Resolution

from abc import ABC, abstractmethod

from pfund_blocks.datas.data_base import BaseData


class MarketData(BaseData, ABC):
    def __init__(self, product: BaseProduct, resolution: Resolution):
        self.product: BaseProduct = product
        self.resolution: Resolution = resolution
        self._resampler: TickData | BarData | None = None  # data used to be resampled into this data
        self._resamplees: list[MarketData] = []  # opposite of resampler

    def to_dict(self) -> dict[str, Any]:
        return {
            **super().to_dict(),
            "product": self.product.model_dump(),
            "resolution": repr(self.resolution),
        }

    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, MarketData):
            return NotImplemented
        return (self.product, self.resolution) == (other.product, other.resolution)

    def __hash__(self):
        return hash((self.product, self.resolution))

    def __str__(self):
        return f"[{type(self).__name__}] {self.product.name} | {self.resolution}"

    @abstractmethod
    def _update(self, value: Any) -> list[ClosedBar]:
        """Updates this data only, returns the bars closed by this update, oldest first."""

    def update(self, value: Tick | Bar | Quote) -> list[ClosedBar]:
        """Updates the data and all its resamplees, returns every bar closed by this update, finest first.

        A resamplee only receives closed bars from its resampler, otherwise the same volume would be counted twice.
        e.g. for 1m -> 5m -> 1h, a closed 1m bar updates the 5m bar, and the 1h bar is only updated if that closed the 5m bar.
        """
        closed_bars = self._update(value)
        all_closed_bars = list(closed_bars)
        for resamplee in self._resamplees:
            for closed_bar in closed_bars:
                all_closed_bars += resamplee.update(closed_bar)
        return all_closed_bars

    def is_resamplee(self) -> bool:
        return self._resampler is not None

    def is_resampler(self) -> bool:
        return bool(self._resamplees)

    def get_resampler(self) -> TickData | BarData | None:
        return self._resampler

    def get_resamplees(self) -> list[MarketData]:
        return self._resamplees

    def add_resamplee(self, resamplee: MarketData):
        self._resamplees.append(resamplee)

    def remove_resamplee(self, resamplee: MarketData):
        self._resamplees.remove(resamplee)

    def bind_resampler(self, resampler: TickData | BarData):
        """Resamples this data from the resampler, e.g. a 5m bar data binds a 1m bar data as its resampler.

        A data can only have one resampler, otherwise the same volume would be counted more than once.
        """
        if self._resampler is not None:
            raise ValueError(f"{self.resolution!r} data already has a resampler {self._resampler.resolution!r}")
        if resampler.product != self.product:
            raise ValueError(f"resampler's product {resampler.product} does not match {self.product}")
        if resampler.resolution <= self.resolution:
            raise ValueError(f"resampler's resolution {resampler.resolution!r} must be finer than {self.resolution!r}")
        self._resampler = resampler
        resampler.add_resamplee(self)

    def unbind_resampler(self):
        if self._resampler is not None:
            self._resampler.remove_resamplee(self)
            self._resampler = None
