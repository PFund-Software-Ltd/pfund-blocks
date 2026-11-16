from __future__ import annotations

from typing import ClassVar

from pydantic import BaseModel, ConfigDict, Field

from pfund_blocks.entities.orders.order_base import OrderKey
from pfund_blocks.entities.orders.order_status import OrderStatusRepr
from pfund_blocks.typing import AccountName, TradingVenue


class OrderUpdate(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", frozen=True)

    venue: TradingVenue
    account: AccountName
    received_at: int  # int64 ns since epoch when the message was received
    updated_at: int | None = Field(
        description="int64 ns since epoch when the order was updated, provided by the venue",
    )
    order_id: str  # venue's order id
    order_key: OrderKey | None  # None for orders not placed by pfund (e.g. on the venue's UI)
    status: OrderStatusRepr  # venue status mapped by the parser, e.g. "CPC-", see OrderStatus.__repr__
    reason: str | None = None  # venue's reject/cancel reason, if any
