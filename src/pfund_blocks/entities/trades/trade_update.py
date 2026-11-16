from __future__ import annotations

from typing import ClassVar

from pydantic import BaseModel, ConfigDict

from pfund_blocks.entities.trades.trade import Trade
from pfund_blocks.typing import AccountName, TradingVenue


class TradeUpdate(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", frozen=True)

    venue: TradingVenue
    account: AccountName
    received_at: int  # int64 ns since epoch when the message was received
    trade: Trade
