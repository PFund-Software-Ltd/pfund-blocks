from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Hashable

from abc import ABC, abstractmethod


class BaseData(ABC):
    """Base class of all data.

    A data's identity is its `key`, from which `__eq__` and `__hash__` are derived,
    so subclasses only implement `key` and never `__eq__`/`__hash__` themselves.
    (defining only `__eq__` in a subclass would silently set its `__hash__` to None)
    """

    @property
    @abstractmethod
    def key(self) -> Hashable:
        """What makes two data the same, e.g. (product, resolution) for market data."""

    def __eq__(self, other: object) -> bool:
        # different data types are never equal, e.g. TickData and BarData of the same product and resolution
        if not isinstance(other, BaseData) or type(other) is not type(self):
            return NotImplemented
        return self.key == other.key

    def __hash__(self) -> int:
        return hash(self.key)

    def to_dict(self) -> dict[str, Any]:
        return {}
