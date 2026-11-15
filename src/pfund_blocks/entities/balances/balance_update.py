from __future__ import annotations

from typing import ClassVar

from pydantic import BaseModel, ConfigDict

from pfund_blocks.entities.balances.balance_base import BaseBalance
from pfund_blocks.typing import AccountName, Currency, TradingVenue


class BalanceUpdate[SnapshotT: BaseBalance.Snapshot](BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", frozen=True)

    venue: TradingVenue
    account: AccountName
    received_at: int  # int64 ns since epoch when the message was received
    snapshots: dict[Currency, SnapshotT]
