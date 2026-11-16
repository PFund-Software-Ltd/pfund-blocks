from __future__ import annotations

from typing import ClassVar

from pydantic import BaseModel, ConfigDict

from pfund_blocks.entities.positions.position_base import BasePosition
from pfund_blocks.enums.side import Side
from pfund_blocks.typing import AccountName, ProductName, TradingVenue


class PositionUpdate[SnapshotT: BasePosition.Snapshot](BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", frozen=True)

    venue: TradingVenue
    account: AccountName
    received_at: int  # int64 ns since epoch when the message was received
    product: ProductName
    # LONG/SHORT for a hedge-mode leg (DualPosition), None for a one-way position
    side: Side | None
    position: SnapshotT
