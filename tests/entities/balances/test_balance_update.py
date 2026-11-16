from __future__ import annotations

from typing import Any

from decimal import Decimal

import pytest
from pydantic import ValidationError

from pfund_blocks.entities.balances.balance_base import BaseBalance
from pfund_blocks.entities.balances.balance_update import BalanceUpdate


def create_snapshot() -> BaseBalance.Snapshot:
    return BaseBalance.Snapshot(
        updated_at=1_700_000_000_000_000_000,
        cash=Decimal("100"),
        equity=Decimal("110"),
        available=Decimal("90"),
        initial_margin=Decimal("5"),
        maintenance_margin=Decimal("2"),
        unrealized_pnl=Decimal("10"),
        realized_pnl=Decimal("-1"),
    )


# a venue's balance that extends the snapshot with its own field
class VenueBalance(BaseBalance):
    class Snapshot(BaseBalance.Snapshot):
        bonus: Decimal | None


class TestBalanceUpdate:
    def create_update(self, **overrides: Any) -> BalanceUpdate[BaseBalance.Snapshot]:
        fields: dict[str, Any] = {
            "venue": "BYBIT",
            "account": "main",
            "received_at": 1_700_000_000_000_000_001,
            "currency": "USDT",
            "balance": create_snapshot(),
        }
        return BalanceUpdate[BaseBalance.Snapshot](**(fields | overrides))

    def test_create(self):
        update = self.create_update()
        assert update.venue == "BYBIT"
        assert update.account == "main"
        assert update.currency == "USDT"
        assert update.balance == create_snapshot()

    def test_extra_field_is_rejected(self):
        with pytest.raises(ValidationError, match="extra_forbidden"):
            self.create_update(oops=1)

    def test_is_frozen(self):
        update = self.create_update()
        with pytest.raises(ValidationError, match="frozen_instance"):
            update.account = "other"  # ty: ignore[invalid-assignment]

    def test_round_trip_through_dict(self):
        update = self.create_update()
        assert (
            BalanceUpdate[BaseBalance.Snapshot].model_validate(update.model_dump())
            == update
        )

    def test_round_trip_restores_decimal_from_str(self):
        # e.g. msgspec msgpack decodes a Decimal as str when sent over zeromq
        update = self.create_update()
        data = update.model_dump()
        data["balance"]["cash"] = "100"
        rebuilt = BalanceUpdate[BaseBalance.Snapshot].model_validate(data)
        assert rebuilt.balance.cash == Decimal("100")
        assert isinstance(rebuilt.balance.cash, Decimal)

    def test_round_trip_with_subclass_snapshot(self):
        snapshot = VenueBalance.Snapshot(
            **create_snapshot().model_dump(), bonus=Decimal("5")
        )
        update = BalanceUpdate[VenueBalance.Snapshot](
            venue="BYBIT",
            account="main",
            received_at=1,
            currency="USDT",
            balance=snapshot,
        )
        rebuilt = BalanceUpdate[VenueBalance.Snapshot].model_validate(
            update.model_dump()
        )
        assert rebuilt.balance.bonus == Decimal("5")
