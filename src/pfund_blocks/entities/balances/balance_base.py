from __future__ import annotations

from decimal import Decimal
from typing import Any, ClassVar, Self

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, computed_field

from pfund_blocks.typing import AccountName, Currency, TradingVenue


class BaseBalance(BaseModel):
    class Snapshot(BaseModel):
        model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", frozen=True)

        updated_at: int | None = Field(
            description="int64 ns since epoch, timestamp provided by the venue",
        )
        cash: Decimal | None  # wallet balance
        equity: Decimal | None  # ≈ margin balance
        available: Decimal | None = Field(ge=0)
        initial_margin: Decimal | None
        maintenance_margin: Decimal | None
        unrealized_pnl: Decimal | None
        realized_pnl: Decimal | None

        @classmethod
        def empty(cls) -> Self:
            """Returns a snapshot with every field set to None."""
            return cls(**dict.fromkeys(cls.model_fields))

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")
    _snapshot: Snapshot = PrivateAttr()

    currency: Currency

    def model_post_init(self, context: Any, /) -> None:
        # uses self.Snapshot so a subclass's own Snapshot is picked up
        self._snapshot = self.Snapshot.empty()

    def on_update(self, update: Snapshot) -> None:
        self._snapshot = self.Snapshot.model_validate(update)

    @property
    def snapshot(self) -> Snapshot:
        return self._snapshot

    @computed_field
    @property
    def cash(self) -> Decimal | None:
        return self._snapshot.cash

    @computed_field
    @property
    def equity(self) -> Decimal | None:
        return self._snapshot.equity

    @computed_field
    @property
    def available(self) -> Decimal | None:
        return self._snapshot.available

    @computed_field
    @property
    def initial_margin(self) -> Decimal | None:
        return self._snapshot.initial_margin

    @computed_field
    @property
    def maintenance_margin(self) -> Decimal | None:
        return self._snapshot.maintenance_margin

    @computed_field
    @property
    def unrealized_pnl(self) -> Decimal | None:
        return self._snapshot.unrealized_pnl

    @computed_field
    @property
    def realized_pnl(self) -> Decimal | None:
        return self._snapshot.realized_pnl

    @property
    def updated_at(self) -> int | None:
        return self._snapshot.updated_at

    def __str__(self):
        return f"Currency={self.currency} | Cash={self.cash} | Equity={self.equity} | Available={self.available}"

    def __repr__(self):
        return f"{self.currency} | cash={self.cash} | equity={self.equity} | available={self.available}"


class BalanceUpdate[SnapshotT: BaseBalance.Snapshot](BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", frozen=True)

    source: TradingVenue
    account: AccountName
    received_at: int  # int64 ns since epoch when the message was received
    snapshots: dict[Currency, SnapshotT]
