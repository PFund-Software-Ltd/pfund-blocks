from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pfund_blocks.datas.bar_data import BarData, ClosedBar
    from pfund_blocks.datas.tick_data import TickData
    from pfund_blocks.entities.products.product_base import BaseProduct
    from pfund_blocks.resolution import Resolution

from abc import ABC, abstractmethod

from pfund_blocks.datas.data_base import BaseData


class MarketData(BaseData, ABC):
    def __init__(self, product: BaseProduct, resolution: Resolution):
        self.product: BaseProduct = product
        self.resolution: Resolution = resolution
        self._resampler: TickData | BarData | None = None  # data used to be resampled into this data
        self._resamplees: list[BarData] = []  # opposite of resampler

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
    def update(self, value: Any) -> list[ClosedBar]:
        """Updates the data and all its resamplees, returns every bar closed by this update, finest first."""

    def is_resamplee(self) -> bool:
        return self._resampler is not None

    def is_resampler(self) -> bool:
        return bool(self._resamplees)

    def get_resampler(self) -> TickData | BarData | None:
        return self._resampler

    def get_resamplees(self) -> list[BarData]:
        return self._resamplees

    def _add_resamplee(self, resamplee: BarData):
        self._resamplees.append(resamplee)

    def _remove_resamplee(self, resamplee: BarData):
        self._resamplees.remove(resamplee)
