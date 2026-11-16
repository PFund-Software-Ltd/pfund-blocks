from __future__ import annotations

from typing import Any, Literal

from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator

from pfund_blocks.entities.trades.quantity import Quantity
from pfund_blocks.enums.side import Side
from pfund_blocks.typing import Currency


class Trade(BaseModel):
    model_config = ConfigDict(extra="forbid")

    executed_at: int = Field(
        description="int64 ns since epoch, timestamp provided by the venue",
    )
    trade_id: str
    order_id: str = Field(description="which order this trade belongs to")
    side: Side | Literal["BUY", "SELL", 1, -1]
    price: Decimal = Field(gt=0.0, description="traded price")
    quantity: Quantity = Field(gt=0.0, description="traded quantity")
    fee: Decimal | None = Field(
        default=None,
        description="""
        the fee exactly as charged by the trading venue, in its native currency
        (e.g. 0.0001 BTC). Kept as-is for reconciliation against the venue's records
        """,
    )
    fee_currency: Currency = Field(
        default="",
        description="the native currency the fee was charged in (e.g. BTC), pairs with `fee`",
    )
    is_maker: bool | None = Field(default=None)

    @field_validator("side", mode="before")
    @classmethod
    def _validate_side(cls, value: Any) -> Side:
        if isinstance(value, str):
            side = Side[value.upper()]
        elif isinstance(value, int):
            side = Side(value)
        else:
            raise ValueError(f"Invalid side: {value}")
        return side

    @computed_field
    @property
    def size(self) -> Quantity:
        return self.quantity * Side(self.side)

    @property
    def qty(self) -> Quantity:
        return self.quantity

    @property
    def px(self) -> Decimal:
        return self.price

    def __str__(self) -> str:
        return (
            f"TradeID={self.trade_id} | OrderID={self.order_id} | ExecutedAt={self.executed_at}\n"
            f"Side={Side(self.side).name} | Price={self.price} | Quantity={self.quantity}\n"
            f"Fee={self.fee} | FeeCurrency={self.fee_currency} | IsMaker={self.is_maker}"
        )

    def __repr__(self) -> str:
        return (
            f"{self.trade_id} | order={self.order_id}\n"
            f"{self.size}@{self.price} | fee={self.fee} {self.fee_currency} | maker={self.is_maker}"
        )
