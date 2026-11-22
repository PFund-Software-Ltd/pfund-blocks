from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

if TYPE_CHECKING:
    from collections.abc import Hashable

    from pfund_blocks.datas.bar_data import BarData, ClosedBar
    from pfund_blocks.datas.tick_data import TickData
    from pfund_blocks.entities.products.product_base import BaseProduct
    from pfund_blocks.resolution import Resolution

from abc import ABC, abstractmethod

from pfund_blocks.datas.data_base import BaseData
from pfund_blocks.enums.data_category import DataCategory


class MarketData(BaseData, ABC):
    category: ClassVar[DataCategory] = DataCategory.MARKET_DATA

    def __init__(
        self,
        product: BaseProduct,
        resolution: Resolution,
        *,
        source: str = "",
        origin: str = "",
    ):
        """
        Args:
            source: where the data comes from, e.g. a trading venue ('BYBIT') or a data vendor ('DATABENTO').
                Optional ("" means unspecified), the data works without it. It is part of the data's identity,
                e.g. BTC 1m bars from BYBIT and from DATABENTO are different data.
            origin: a sub-label for data from the same source but different origins, e.g. pfeed's data_origin.
        """
        self.product: BaseProduct = product
        self.resolution: Resolution = resolution
        self.source: str = source.upper()
        self.origin: str = origin
        self._resampler: TickData | BarData | None = (
            None  # data used to be resampled into this data
        )
        self._resamplees: list[BarData] = []  # opposite of resampler

    def to_dict(self) -> dict[str, Any]:
        return {
            **super().to_dict(),
            "product": self.product.model_dump(),
            "resolution": repr(self.resolution),
            "source": self.source,
            "origin": self.origin,
        }

    @property
    def key(self) -> tuple[Hashable, ...]:
        # subclasses may extend it, e.g. BarData adds its shift
        return (self.source, self.origin, self.product, self.resolution)

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
