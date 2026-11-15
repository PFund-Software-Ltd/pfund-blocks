from __future__ import annotations

from decimal import Decimal
from typing import ClassVar, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    PrivateAttr,
    computed_field,
    model_validator,
)

from pfund_blocks.typing import Currency


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

        @model_validator(mode="after")
        def _check_has_amount(self) -> Self:
            if self.cash is None and self.equity is None and self.available is None:
                raise ValueError(
                    "at least one of cash, equity, available must not be None"
                )
            return self

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")
    # None until the first update
    _snapshot: Snapshot | None = PrivateAttr(default=None)

    currency: Currency

    def on_update(self, update: Snapshot) -> None:
        # uses self.Snapshot so a subclass's own Snapshot is enforced
        self._snapshot = self.Snapshot.model_validate(update)

    @property
    def snapshot(self) -> Snapshot | None:
        return self._snapshot

    @computed_field
    @property
    def cash(self) -> Decimal | None:
        return self._snapshot.cash if self._snapshot is not None else None

    @computed_field
    @property
    def equity(self) -> Decimal | None:
        return self._snapshot.equity if self._snapshot is not None else None

    @computed_field
    @property
    def available(self) -> Decimal | None:
        return self._snapshot.available if self._snapshot is not None else None

    @computed_field
    @property
    def initial_margin(self) -> Decimal | None:
        return self._snapshot.initial_margin if self._snapshot is not None else None

    @computed_field
    @property
    def maintenance_margin(self) -> Decimal | None:
        return self._snapshot.maintenance_margin if self._snapshot is not None else None

    @computed_field
    @property
    def unrealized_pnl(self) -> Decimal | None:
        return self._snapshot.unrealized_pnl if self._snapshot is not None else None

    # plain property aliases, an alias of a computed field would be dumped twice
    upnl = property(lambda self: self.unrealized_pnl)

    @computed_field
    @property
    def realized_pnl(self) -> Decimal | None:
        return self._snapshot.realized_pnl if self._snapshot is not None else None

    rpnl = property(lambda self: self.realized_pnl)

    @property
    def updated_at(self) -> int | None:
        return self._snapshot.updated_at if self._snapshot is not None else None

    def __str__(self):
        return f"Currency={self.currency} | Cash={self.cash} | Equity={self.equity} | Available={self.available}"

    def __repr__(self):
        return f"{self.currency} | cash={self.cash} | equity={self.equity} | available={self.available}"
