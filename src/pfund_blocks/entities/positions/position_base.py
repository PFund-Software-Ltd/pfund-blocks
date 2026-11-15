from __future__ import annotations

from decimal import Decimal
from typing import ClassVar

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, computed_field

from pfund_blocks.entities.products.product_base import BaseProduct
from pfund_blocks.entities.trades.quantity import Quantity
from pfund_blocks.enums.position_mode import PositionMode
from pfund_blocks.enums.side import Side
from pfund_blocks.typing import TradingVenue


class BasePosition(BaseModel):
    class Snapshot(BaseModel):
        model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", frozen=True)

        updated_at: int | None = Field(
            description="int64 ns since epoch, timestamp provided by the venue",
        )
        size: Quantity  # signed, negative = short
        avg_price: Decimal | None = Field(ge=0)
        mark_price: Decimal | None = Field(ge=0)
        liquidation_price: Decimal | None = Field(ge=0)
        initial_margin: Decimal | None
        maintenance_margin: Decimal | None
        unrealized_pnl: Decimal | None
        realized_pnl: Decimal | None

    model_config: ClassVar[ConfigDict] = ConfigDict(
        arbitrary_types_allowed=True, extra="forbid"
    )
    _snapshot: Snapshot | None = PrivateAttr(
        default=None
    )  # None until the first update

    product: BaseProduct
    mode: PositionMode = Field(default=PositionMode.NORMAL)

    def on_update(self, update: Snapshot) -> None:
        self._snapshot = self.Snapshot.model_validate(update)

    @property
    def snapshot(self) -> Snapshot | None:
        return self._snapshot

    @property
    def venue(self) -> TradingVenue:
        return self.product.source

    @computed_field
    @property
    def size(self) -> Quantity | None:
        return self._snapshot.size if self._snapshot is not None else None

    @property
    def side(self) -> Side | None:
        # None when there is no snapshot yet or the position is flat (0)
        return Side(self.size) if self.size else None

    @property
    def quantity(self) -> Quantity | None:
        return None if self.size is None else Quantity(abs(self.size))

    qty = quantity

    @computed_field
    @property
    def mark_price(self) -> Decimal | None:
        return self._snapshot.mark_price if self._snapshot is not None else None

    # plain property aliases, an alias of a computed field would be dumped twice
    mark_px = property(lambda self: self.mark_price)

    @computed_field
    @property
    def avg_price(self) -> Decimal | None:
        return self._snapshot.avg_price if self._snapshot is not None else None

    entry_price = entry_px = avg_px = property(lambda self: self.avg_price)

    @computed_field
    @property
    def liquidation_price(self) -> Decimal | None:
        return self._snapshot.liquidation_price if self._snapshot is not None else None

    liq_price = liq_px = liquidation_px = property(lambda self: self.liquidation_price)

    @computed_field
    @property
    def initial_margin(self) -> Decimal | None:
        return self._snapshot.initial_margin if self._snapshot is not None else None

    @computed_field
    @property
    def maintenance_margin(self) -> Decimal | None:
        return self._snapshot.maintenance_margin if self._snapshot is not None else None

    @property
    def updated_at(self) -> int | None:
        return self._snapshot.updated_at if self._snapshot is not None else None

    def is_empty(self) -> bool:
        assert self._snapshot is not None, "no snapshot yet, cannot tell if empty"
        return self.size == 0

    @computed_field
    @property
    def unrealized_pnl(self) -> Decimal | None:
        return self._snapshot.unrealized_pnl if self._snapshot is not None else None

    upnl = property(lambda self: self.unrealized_pnl)

    def compute_unrealized_pnl(self, mark_price: Decimal) -> Decimal:
        assert self.size is not None, "no snapshot yet, cannot compute unrealized PnL"
        if self.is_empty():
            return Decimal(0)
        assert self.avg_price is not None, (
            "avg_price is None, cannot compute unrealized PnL"
        )
        return self.size * (mark_price - self.avg_price)

    @computed_field
    @property
    def realized_pnl(self) -> Decimal | None:
        return self._snapshot.realized_pnl if self._snapshot is not None else None

    rpnl = property(lambda self: self.realized_pnl)

    # TODO
    # def on_trade_update(self, order: BaseOrder):
    #     ttl_size = self.size + o.ltz
    #     new_side = sign(ttl_size)
    #     ttl_qty = abs(ttl_size)
    #     # calc avg_px
    #     if new_side != 0:
    #         if o.side != self.side:
    #             if o.ltq > self.qty:
    #                 avg_px = o.ltp
    #             else:
    #                 avg_px = self.long_avg_px if self.side == 1 else self.short_avg_px
    #         else:
    #             avg_px = self.long_avg_px if self.side == 1 else self.short_avg_px
    #             qty = self.long_qty if self.side == 1 else self.short_qty
    #             avg_px = (avg_px * qty + o.ltp * o.ltq) / ttl_qty
    #     else:
    #         avg_px = Decimal(0)
    #     update = {
    #         new_side: {
    #             "qty": ttl_qty,
    #             "avg_px": avg_px,
    #             "liquidation_px": Decimal(0),
    #             "unrealized_pnl": Decimal(0),
    #             "realized_pnl": Decimal(0),
    #         }
    #     }
    #     ts = o.ltt
    #     self.logger.debug(
    #         f"update {self.exch} {self.pdt} {update} by oid {o.oid} ({o.lts}@{o.ltp}) ts={ts}"
    #     )
    #     self.on_update(update)

    def __str__(self):
        return (
            f"Product={self.product}\n"
            f"Size={self.size} | AveragePrice={self.avg_price} | "
            f"MarkPrice={self.mark_price} | LiquidationPrice={self.liquidation_price}\n"
            f"UnrealizedPnL={self.unrealized_pnl} | RealizedPnL={self.realized_pnl}"
        )

    def __repr__(self):
        return (
            f"{self.product.name} | {self.size}@{self.avg_price} | "
            f"mark={self.mark_price} | liq={self.liquidation_price} | "
            f"upnl={self.unrealized_pnl} | rpnl={self.realized_pnl}"
        )
