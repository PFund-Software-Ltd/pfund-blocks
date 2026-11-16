# on_update takes a side, which BasePosition.on_update doesn't
# ty: ignore[incompatible-method-override]
from __future__ import annotations

from typing import Any, ClassVar, Literal

from decimal import Decimal

from pydantic import Field, PrivateAttr

from pfund_blocks.entities.positions.position_base import BasePosition
from pfund_blocks.entities.trades.quantity import Quantity
from pfund_blocks.enums.position_mode import PositionMode
from pfund_blocks.enums.side import Side


class DualPosition(BasePosition):
    """A position with independent long and short legs (hedge mode).

    Each leg is a normal BasePosition with its own snapshot.
    The DualPosition itself acts like one position: its snapshot is the net (combined) one of the legs.
    A leg without a value (no snapshot, or not reported by the venue) counts as nothing.
    """

    # the class of both legs, a venue with a custom position class sets it, e.g. VenuePosition = BybitPosition
    VenuePosition: ClassVar[type[BasePosition]] = BasePosition
    _long: BasePosition = PrivateAttr()
    _short: BasePosition = PrivateAttr()

    mode: PositionMode = Field(default=PositionMode.DUAL)

    @property
    def long(self) -> BasePosition:
        return self._long

    @property
    def short(self) -> BasePosition:
        return self._short

    def model_post_init(self, context: Any, /) -> None:
        self._long = self.VenuePosition(product=self.product)
        self._short = self.VenuePosition(product=self.product)

    def on_update(self, side: Side, update: BasePosition.Snapshot) -> None:
        # side can't be deduced from the sign of size: a flat update (size 0) has no sign,
        # e.g. closing the long leg while both legs are open
        # the sign checks catch a parser that forgot to sign the short leg's size
        if side is Side.LONG:
            if update.size < 0:
                raise ValueError(f"long leg size must be >= 0, got {update.size}")
            self._long.on_update(update)
        elif side is Side.SHORT:
            if update.size > 0:
                raise ValueError(f"short leg size must be <= 0, got {update.size}")
            self._short.on_update(update)
        else:
            raise ValueError(f"side must be LONG or SHORT, got {side!r}")
        self._combine()

    def _combine(self) -> None:
        """Derives the net snapshot from the legs with a snapshot."""
        legs = self._get_legs_with_snapshot()
        long_size, short_size = self._long.size, self._short.size
        if long_size is None:
            assert short_size is not None, "no snapshot yet"
            net_size = short_size
        elif short_size is None:
            net_size = long_size
        else:
            net_size = Quantity(long_size + short_size)
        if net_size > 0:
            avg_price = self._long.avg_price
        elif net_size < 0:
            avg_price = self._short.avg_price
        else:
            avg_price = None
        # mark price is per product, take the most recently updated leg's
        latest = max(legs, key=lambda leg: leg.updated_at or 0)
        super().on_update(
            self.Snapshot(
                updated_at=latest.updated_at,
                size=net_size,
                avg_price=avg_price,
                mark_price=latest.mark_price,
                # each leg keeps its own, net liquidation price is undefined in hedge mode
                liquidation_price=None,
                # each leg keeps its own, net margins are not meaningful
                initial_margin=None,
                maintenance_margin=None,
                unrealized_pnl=self._combine_pnl("unrealized_pnl"),
                realized_pnl=self._combine_pnl("realized_pnl"),
            )
        )

    def _get_legs_with_snapshot(self) -> list[BasePosition]:
        legs = [leg for leg in (self._long, self._short) if leg.snapshot is not None]
        assert legs, "no snapshot yet"
        return legs

    def _combine_pnl(
        self,
        attr: Literal["unrealized_pnl", "realized_pnl"],
    ) -> Decimal | None:
        long_pnl = getattr(self._long, attr)
        short_pnl = getattr(self._short, attr)
        if long_pnl is None:
            return short_pnl
        if short_pnl is None:
            return long_pnl
        return long_pnl + short_pnl

    def is_empty(self) -> bool:
        legs = self._get_legs_with_snapshot()
        return all(leg.is_empty() for leg in legs)

    def compute_unrealized_pnl(self, mark_price: Decimal) -> Decimal:
        # per leg, the net avg price is only one leg's, so net size * (mark - avg) is wrong when hedged
        legs = self._get_legs_with_snapshot()
        return sum((leg.compute_unrealized_pnl(mark_price) for leg in legs), Decimal(0))

    def __str__(self):
        long, short = self._long, self._short
        return (
            f"Product={self.product} | Mode={self.mode}\n"
            f"Net: Size={self.size} | AveragePrice={self.avg_price} | MarkPrice={self.mark_price} | "
            f"UnrealizedPnL={self.unrealized_pnl} | RealizedPnL={self.realized_pnl}\n"
            f"Long: Size={long.size} | AveragePrice={long.avg_price} | MarkPrice={long.mark_price} | "
            f"LiquidationPrice={long.liquidation_price} | "
            f"UnrealizedPnL={long.unrealized_pnl} | RealizedPnL={long.realized_pnl}\n"
            f"Short: Size={short.size} | AveragePrice={short.avg_price} | MarkPrice={short.mark_price} | "
            f"LiquidationPrice={short.liquidation_price} | "
            f"UnrealizedPnL={short.unrealized_pnl} | RealizedPnL={short.realized_pnl}"
        )

    def __repr__(self):
        long, short = self._long, self._short
        return (
            f"{self.product.name} | {self.mode} | net={self.size}@{self.avg_price} | "
            f"long={long.size}@{long.avg_price} | short={short.size}@{short.avg_price} | "
            f"upnl={self.unrealized_pnl} | rpnl={self.realized_pnl}"
        )
