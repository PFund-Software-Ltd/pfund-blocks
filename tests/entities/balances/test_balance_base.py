from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest
from pydantic import ValidationError

from pfund_blocks.entities.balances.balance_base import BalanceUpdate, BaseBalance

SNAPSHOT_FIELDS = {
    "updated_at",
    "cash",
    "equity",
    "available",
    "initial_margin",
    "maintenance_margin",
    "unrealized_pnl",
    "realized_pnl",
}


def create_snapshot(**overrides: Any) -> BaseBalance.Snapshot:
    fields: dict[str, Any] = {
        "updated_at": 1_700_000_000_000_000_000,
        "cash": Decimal("100"),
        "equity": Decimal("110"),
        "available": Decimal("90"),
        "initial_margin": Decimal("5"),
        "maintenance_margin": Decimal("2"),
        "unrealized_pnl": Decimal("10"),
        "realized_pnl": Decimal("-1"),
    }
    return BaseBalance.Snapshot(**(fields | overrides))


# a venue's balance that extends the snapshot with its own field
class VenueBalance(BaseBalance):
    class Snapshot(BaseBalance.Snapshot):
        bonus: Decimal | None


class TestSnapshot:
    def test_every_field_is_required(self):
        with pytest.raises(ValidationError) as exc_info:
            BaseBalance.Snapshot(cash=Decimal("1"))  # ty: ignore[missing-argument]
        missing = {
            error["loc"][0]
            for error in exc_info.value.errors()
            if error["type"] == "missing"
        }
        assert missing == SNAPSHOT_FIELDS - {"cash"}

    def test_none_is_accepted(self):
        snapshot = create_snapshot(cash=None, available=None)
        assert snapshot.cash is None
        assert snapshot.available is None

    def test_extra_field_is_rejected(self):
        with pytest.raises(ValidationError, match="extra_forbidden"):
            create_snapshot(oops=1)

    def test_is_frozen(self):
        snapshot = create_snapshot()
        with pytest.raises(ValidationError, match="frozen_instance"):
            snapshot.cash = Decimal("1")  # ty: ignore[invalid-assignment]

    def test_negative_available_is_rejected(self):
        with pytest.raises(ValidationError, match="greater_than_equal"):
            create_snapshot(available=Decimal("-1"))

    def test_str_numbers_are_converted_to_decimal(self):
        snapshot = create_snapshot(cash="1.5")
        assert snapshot.cash == Decimal("1.5")
        assert isinstance(snapshot.cash, Decimal)

    def test_empty_sets_every_field_to_none(self):
        snapshot = BaseBalance.Snapshot.empty()
        assert snapshot.model_dump() == dict.fromkeys(SNAPSHOT_FIELDS)

    def test_empty_includes_subclass_fields(self):
        snapshot = VenueBalance.Snapshot.empty()
        assert snapshot.model_dump() == dict.fromkeys(SNAPSHOT_FIELDS | {"bonus"})


class TestBaseBalance:
    def test_new_balance_has_empty_snapshot(self):
        balance = BaseBalance(currency="USDT")
        assert balance.snapshot == BaseBalance.Snapshot.empty()
        assert balance.updated_at is None

    def test_new_balance_can_be_dumped_and_printed(self):
        balance = BaseBalance(currency="USDT")
        assert balance.model_dump() == {
            "currency": "USDT",
            "cash": None,
            "equity": None,
            "available": None,
            "initial_margin": None,
            "maintenance_margin": None,
            "unrealized_pnl": None,
            "realized_pnl": None,
        }
        assert (
            str(balance) == "Currency=USDT | Cash=None | Equity=None | Available=None"
        )
        assert repr(balance) == "USDT | cash=None | equity=None | available=None"

    def test_on_update_replaces_snapshot(self):
        balance = BaseBalance(currency="USDT")
        snapshot = create_snapshot()
        balance.on_update(snapshot)
        assert balance.snapshot == snapshot
        assert balance.updated_at == snapshot.updated_at
        assert balance.cash == Decimal("100")
        assert balance.equity == Decimal("110")
        assert balance.available == Decimal("90")
        assert balance.initial_margin == Decimal("5")
        assert balance.maintenance_margin == Decimal("2")
        assert balance.unrealized_pnl == Decimal("10")
        assert balance.realized_pnl == Decimal("-1")

    def test_on_update_replaces_the_whole_snapshot(self):
        balance = BaseBalance(currency="USDT")
        balance.on_update(create_snapshot())
        balance.on_update(create_snapshot(equity=None))
        assert balance.equity is None
        assert balance.cash == Decimal("100")

    def test_dump_includes_computed_fields(self):
        balance = BaseBalance(currency="USDT")
        balance.on_update(create_snapshot())
        dumped = balance.model_dump()
        assert dumped["cash"] == Decimal("100")
        assert dumped["realized_pnl"] == Decimal("-1")
        assert "updated_at" not in dumped  # a plain property, not a computed field

    def test_str_and_repr(self):
        balance = BaseBalance(currency="USDT")
        balance.on_update(create_snapshot())
        assert str(balance) == "Currency=USDT | Cash=100 | Equity=110 | Available=90"
        assert repr(balance) == "USDT | cash=100 | equity=110 | available=90"

    def test_extra_field_is_rejected(self):
        with pytest.raises(ValidationError, match="extra_forbidden"):
            BaseBalance(currency="USDT", oops=1)  # ty: ignore[unknown-argument]


class TestSubclassSnapshot:
    def test_new_balance_uses_subclass_snapshot(self):
        balance = VenueBalance(currency="USDT")
        assert isinstance(balance.snapshot, VenueBalance.Snapshot)
        assert balance.snapshot.bonus is None

    def test_on_update_with_subclass_snapshot(self):
        balance = VenueBalance(currency="USDT")
        fields = create_snapshot().model_dump()
        balance.on_update(VenueBalance.Snapshot(**fields, bonus=Decimal("5")))
        assert balance.snapshot.bonus == Decimal("5")  # ty: ignore[missing-attribute]

    def test_on_update_rejects_base_snapshot(self):
        balance = VenueBalance(currency="USDT")
        with pytest.raises(ValidationError, match="model_type"):
            balance.on_update(create_snapshot())


class TestBalanceUpdate:
    def create_update(self, **overrides: Any) -> BalanceUpdate[BaseBalance.Snapshot]:
        fields: dict[str, Any] = {
            "source": "BYBIT",
            "account": "main",
            "received_at": 1_700_000_000_000_000_001,
            "snapshots": {"USDT": create_snapshot(), "BTC": create_snapshot()},
        }
        return BalanceUpdate[BaseBalance.Snapshot](**(fields | overrides))

    def test_create(self):
        update = self.create_update()
        assert update.source == "BYBIT"
        assert update.account == "main"
        assert update.snapshots["USDT"] == create_snapshot()

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
        data["snapshots"]["USDT"]["cash"] = "100"
        rebuilt = BalanceUpdate[BaseBalance.Snapshot].model_validate(data)
        assert rebuilt.snapshots["USDT"].cash == Decimal("100")
        assert isinstance(rebuilt.snapshots["USDT"].cash, Decimal)

    def test_round_trip_with_subclass_snapshot(self):
        snapshot = VenueBalance.Snapshot(
            **create_snapshot().model_dump(), bonus=Decimal("5")
        )
        update = BalanceUpdate[VenueBalance.Snapshot](
            source="BYBIT",
            account="main",
            received_at=1,
            snapshots={"USDT": snapshot},
        )
        rebuilt = BalanceUpdate[VenueBalance.Snapshot].model_validate(
            update.model_dump()
        )
        assert rebuilt.snapshots["USDT"].bonus == Decimal("5")
