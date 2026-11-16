from __future__ import annotations

from typing import Any

from decimal import Decimal

import pytest
from pydantic import ValidationError

from pfund_blocks.entities.balances.balance_base import BaseBalance

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

    def test_cash_equity_available_all_none_is_rejected(self):
        with pytest.raises(ValidationError, match="at least one of"):
            create_snapshot(cash=None, equity=None, available=None)


class TestBaseBalance:
    def test_new_balance_has_no_snapshot(self):
        balance = BaseBalance(currency="USDT")
        assert balance.snapshot is None
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

    def test_pnl_aliases(self):
        balance = BaseBalance(currency="USDT")
        balance.on_update(create_snapshot())
        assert balance.upnl == balance.unrealized_pnl == Decimal("10")
        assert balance.rpnl == balance.realized_pnl == Decimal("-1")

    def test_aliases_are_not_dumped(self):
        balance = BaseBalance(currency="USDT")
        dumped = balance.model_dump()
        assert "upnl" not in dumped
        assert "rpnl" not in dumped

    def test_str_and_repr(self):
        balance = BaseBalance(currency="USDT")
        balance.on_update(create_snapshot())
        assert str(balance) == "Currency=USDT | Cash=100 | Equity=110 | Available=90"
        assert repr(balance) == "USDT | cash=100 | equity=110 | available=90"

    def test_extra_field_is_rejected(self):
        with pytest.raises(ValidationError, match="extra_forbidden"):
            BaseBalance(currency="USDT", oops=1)  # ty: ignore[unknown-argument]


class TestSubclassSnapshot:
    def test_on_update_with_subclass_snapshot(self):
        balance = VenueBalance(currency="USDT")
        fields = create_snapshot().model_dump()
        balance.on_update(VenueBalance.Snapshot(**fields, bonus=Decimal("5")))
        assert balance.snapshot.bonus == Decimal("5")  # ty: ignore[missing-attribute]

    def test_on_update_rejects_base_snapshot(self):
        balance = VenueBalance(currency="USDT")
        with pytest.raises(ValidationError, match="model_type"):
            balance.on_update(create_snapshot())
