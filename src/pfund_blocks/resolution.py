from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

import re

from pfund_blocks.enums.timeframe import Timeframe

if TYPE_CHECKING:
    from pydantic import GetCoreSchemaHandler
    from pydantic_core import CoreSchema


class Resolution:
    """Immutable, attributes can't be reassigned after __init__, since __hash__ depends on them."""

    DEFAULT_ORDERBOOK_LEVEL: ClassVar[int] = 1

    __slots__ = ("orderbook_level", "period", "timeframe")
    orderbook_level: int | None
    period: int
    timeframe: Timeframe

    @classmethod
    def __get_pydantic_core_schema__(
        cls, source_type: Any, handler: GetCoreSchemaHandler
    ) -> CoreSchema:
        from pydantic_core import core_schema

        def _validate(value: Any) -> Resolution:
            if isinstance(value, Resolution):
                return value
            if isinstance(value, str):
                return cls(value)
            # decline non-str (e.g. a Timeframe) so a `Resolution | Timeframe` union
            # falls through to its other arm instead of mis-coercing here
            raise ValueError(f"cannot coerce {type(value).__name__} to Resolution")

        return core_schema.no_info_plain_validator_function(
            _validate,
            # describe the input as a string so model_json_schema() works
            json_schema_input_schema=core_schema.str_schema(),
            serialization=core_schema.plain_serializer_function_ser_schema(repr),
        )

    def __init__(self, resolution: Resolution | str):
        """
        Args:
            resolution: e.g. '1m', '1minute', '1quote_L1'
            If the input is a data_type (e.g. 'minute', 'day'),
            it will be converted to resolution by adding '1' to the beginning.
            e.g. 'minute' -> '1m', 'day' -> '1d'
        """
        if isinstance(resolution, Resolution):
            # Copy all attributes from the resolution object
            for name in self.__slots__:
                object.__setattr__(self, name, getattr(resolution, name))
            return

        if isinstance(resolution, str):
            resolution = resolution.strip()
        if not resolution:
            raise ValueError(f"{resolution=} is not a valid resolution")

        period, timeframe_str, orderbook_level = self._parse(resolution)
        object.__setattr__(self, "period", int(period))
        object.__setattr__(self, "timeframe", Timeframe(timeframe_str))
        object.__setattr__(
            self, "orderbook_level", self._resolve_orderbook_level(orderbook_level)
        )

    def __setattr__(self, name: str, value: Any) -> None:
        raise AttributeError(f"{type(self).__name__} is immutable, cannot set '{name}'")

    def __delattr__(self, name: str) -> None:
        raise AttributeError(
            f"{type(self).__name__} is immutable, cannot delete '{name}'"
        )

    def __reduce__(self) -> tuple[type[Resolution], tuple[str]]:
        # rebuild from repr when pickling/copying, since __setattr__ blocks the default slot restore
        return (Resolution, (repr(self),))

    def _parse(self, resolution: str) -> tuple[str, str, str | None]:
        """Parse resolution string and extract period, timeframe, and orderbook level.
        Returns:
            tuple[str, str, str | None]: period string, timeframe string, orderbook level string
        """
        # Reject invalid characters before transformation
        if resolution.startswith("-"):
            raise ValueError(f"Invalid {resolution=}, period cannot be negative")

        # Add "1" if the resolution doesn't start with a number
        if not re.match(r"^\d", resolution):
            resolution = "1" + resolution

        # Only remove hyphens and underscores after the initial numbers
        resolution = re.sub(r"^(\d+)[-_]", r"\1", resolution)

        # validate resolution pattern
        if not re.match(
            rf"^[1-9]\d*({Timeframe.pattern()})(?:_L[1-3])?$", resolution, re.IGNORECASE
        ):
            raise ValueError(
                f"Invalid {resolution=}, pattern should be e.g. '1d', '2m', '3h', '1quote_L1' etc."
            )

        # extract orderbook level if it exists
        resolution, *levels = resolution.split("_")
        orderbook_level = levels[0] if levels else None

        # extract period and timeframe
        period, timeframe = re.split(r"(\d+)", resolution)[1:]
        return period, timeframe, orderbook_level

    def _resolve_orderbook_level(self, orderbook_level: str | None) -> int | None:
        if self.is_quote():
            if orderbook_level:
                resolved_orderbook_level = int(orderbook_level.upper().lstrip("L"))
            else:
                resolved_orderbook_level = self.DEFAULT_ORDERBOOK_LEVEL
            # L1 quotes are self-contained snapshots and can be stacked,
            # L2/L3 are orderbook deltas that must be applied one by one, so period must be 1
            if resolved_orderbook_level > 1 and self.period != 1:
                raise ValueError(
                    f"Invalid period {self.period} for L{resolved_orderbook_level} quotes, only L1 quotes support period > 1"
                )
        elif orderbook_level:
            raise ValueError(
                f"Invalid orderbook level '{orderbook_level}' for {self.timeframe.name}, only quotes have orderbook levels"
            )
        else:
            resolved_orderbook_level = None
        return resolved_orderbook_level

    def to_seconds(self) -> int:
        if not self.is_bar():
            raise ValueError(f"{self!r} is not a bar resolution")
        return self.period * self.timeframe.value

    def _comparable(self) -> tuple[int, int, int]:
        """Higher tuple = higher resolution.
        Time-based resolutions compare by negated total seconds (so 1h == 60m, 120m < 1h),
        quote and tick (negative timeframe values, negated to 2 and 1) rank above all of them,
        then compare by unit, then smaller period, then deeper orderbook level.
        """
        if self.is_quote() or self.is_tick():
            return (-self.timeframe.value, -self.period, self.orderbook_level or 1)
        return (-(self.period * self.timeframe.value), 0, 1)

    def is_quote_l1(self) -> bool:
        return self.is_quote() and self.orderbook_level == 1

    def is_quote_l2(self) -> bool:
        return self.is_quote() and self.orderbook_level == 2

    def is_quote_l3(self) -> bool:
        return self.is_quote() and self.orderbook_level == 3

    def is_quote(self) -> bool:
        return self.timeframe.is_quote()

    def is_tick(self) -> bool:
        return self.timeframe.is_tick()

    def is_bar(self) -> bool:
        return self.is_second() or self.is_minute() or self.is_hour() or self.is_day()

    def is_second(self) -> bool:
        return self.timeframe.is_second()

    def is_minute(self) -> bool:
        return self.timeframe.is_minute()

    def is_hour(self) -> bool:
        return self.timeframe.is_hour()

    def is_day(self) -> bool:
        return self.timeframe.is_day()

    def is_week(self) -> bool:
        return self.timeframe.is_week()

    def is_month(self) -> bool:
        return self.timeframe.is_month()

    def is_year(self) -> bool:
        return self.timeframe.is_year()

    def higher(self) -> Resolution:
        """Rotate to the next higher resolution. e.g. 1m > 1h, higher resolution = lower timeframe"""
        if self.is_quote():
            if self.orderbook_level is not None and self.orderbook_level < 3:
                return Resolution(
                    "1" + repr(self.timeframe) + "_L" + str(self.orderbook_level + 1)
                )
            else:
                return self
        else:
            return Resolution("1" + repr(self.timeframe.lower()))

    finer = higher

    def lower(self) -> Resolution:
        """Rotate to the next lower resolution. e.g. 1h < 1m, lower resolution = higher timeframe"""
        if (
            self.is_quote()
            and self.orderbook_level is not None
            and self.orderbook_level > 1
        ):
            return Resolution(
                "1" + repr(self.timeframe) + "_L" + str(self.orderbook_level - 1)
            )
        else:
            return Resolution("1" + repr(self.timeframe.higher()))

    coarser = lower

    def to_unit(self) -> Resolution:
        """Convert to unit resolution. e.g. 5m -> 1m"""
        timeframe = repr(self.timeframe)
        if self.is_quote():
            return Resolution("1" + timeframe + "_L" + str(self.orderbook_level))
        else:
            return Resolution("1" + timeframe)

    def get_higher_resolutions(
        self, ignore_period: bool = False, exclude_quote: bool = False
    ) -> list[Resolution]:
        """Get all resolutions with higher granularity (finer time intervals) than this one.

        Args:
            ignore_period: If False and this resolution has a period > 1 (e.g., 5m),
                the unit resolution (e.g., 1m) is included as a higher resolution.
                If True, only resolutions of different time units are considered.
            exclude_quote: If True, stop before including quote resolutions (tick is still included).

        Returns:
            List of resolutions with higher granularity, ordered from closest to finest.
        """
        higher_resolutions: list[Resolution] = []
        resolution = self
        unit_resolution = self.to_unit()
        if not ignore_period and resolution != unit_resolution:
            higher_resolutions.append(unit_resolution)
        while (higher_resolution := unit_resolution.higher()) != unit_resolution:
            unit_resolution = higher_resolution
            if higher_resolution.is_quote() and exclude_quote:
                break
            higher_resolutions.append(higher_resolution)
        return higher_resolutions

    get_finer_resolutions = get_higher_resolutions

    def get_lower_resolutions(self, exclude_quote: bool = False) -> list[Resolution]:
        """Get all resolutions with lower granularity (coarser time intervals) than this one.

        Args:
            exclude_quote: If True, skip quote resolutions in the result
                (they are still traversed but not included, tick is still included).

        Returns:
            List of resolutions with lower granularity, ordered from closest to coarsest.
        """
        lower_resolutions: list[Resolution] = []
        resolution = self
        while (lower_resolution := resolution.lower()) != resolution:
            resolution = lower_resolution
            if lower_resolution.is_quote() and exclude_quote:
                continue
            lower_resolutions.append(lower_resolution)
        return lower_resolutions

    get_coarser_resolutions = get_lower_resolutions

    def __str__(self):
        resolution = f"{self.period}_{self.timeframe.name}"
        if self.orderbook_level:
            resolution += f"_L{self.orderbook_level}"
        return resolution

    def __repr__(self):
        resolution = f"{self.period}{self.timeframe.canonical}"
        if self.orderbook_level:
            resolution += f"_L{self.orderbook_level}"
        return resolution

    def __hash__(self):
        return hash(self._comparable())

    def is_strict_equal(self, other: Any) -> bool:
        """1h = 60m when using __eq__ to compare resolutions, but in strict_equal, 1h != 60m"""
        if not isinstance(other, Resolution):
            return False
        return (
            self._comparable() == other._comparable()
            and self.timeframe == other.timeframe
        )

    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, Resolution):
            return NotImplemented
        return self._comparable() == other._comparable()

    # NOTE: higher tuple = higher resolution
    # e.g. 1m (-60, 0, 1) > 1h (-3600, 0, 1)
    def __lt__(self, other: Any) -> bool:
        if not isinstance(other, Resolution):
            return NotImplemented
        return self._comparable() < other._comparable()

    def __le__(self, other: Any) -> bool:
        if not isinstance(other, Resolution):
            return NotImplemented
        return self._comparable() <= other._comparable()

    def __gt__(self, other: Any) -> bool:
        if not isinstance(other, Resolution):
            return NotImplemented
        return self._comparable() > other._comparable()

    def __ge__(self, other: Any) -> bool:
        if not isinstance(other, Resolution):
            return NotImplemented
        return self._comparable() >= other._comparable()
