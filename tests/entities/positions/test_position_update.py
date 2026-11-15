from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest
from pydantic import ValidationError

from pfund_blocks.entities.positions.position_base import BasePosition
from pfund_blocks.entities.positions.position_update import PositionUpdate
from pfund_blocks.entities.trades.quantity import Quantity


def create_snapshot(**overrides: Any) -> BasePosition.Snapshot:
    fields: dict[str, Any] = {
        "updated_at": 1_700_000_000_000_000_000,
        "size": Decimal("-0.5"),
        "avg_price": Decimal("95000"),
        "mark_price": Decimal("94000"),
        "liquidation_price": Decimal("120000"),
        "initial_margin": Decimal("4750"),
        "maintenance_margin": Decimal("250"),
        "unrealized_pnl": Decimal("500"),
        "realized_pnl": Decimal("-12.3"),
    }
    return BasePosition.Snapshot(**(fields | overrides))


# a venue's position that extends the snapshot with its own field
class VenuePosition(BasePosition):
    class Snapshot(BasePosition.Snapshot):
        adl_rank: int | None


class TestPositionUpdate:
    def create_update(self, **overrides: Any) -> PositionUpdate[BasePosition.Snapshot]:
        fields: dict[str, Any] = {
            "venue": "BYBIT",
            "account": "main",
            "received_at": 1_700_000_000_000_000_001,
            "snapshots": {"BYBIT_BTCUSDT": create_snapshot()},
        }
        return PositionUpdate[BasePosition.Snapshot](**(fields | overrides))

    def test_create(self):
        update = self.create_update()
        assert update.venue == "BYBIT"
        assert update.account == "main"
        assert update.snapshots["BYBIT_BTCUSDT"] == create_snapshot()

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
            PositionUpdate[BasePosition.Snapshot].model_validate(update.model_dump())
            == update
        )

    def test_round_trip_restores_types_from_str(self):
        # e.g. msgspec msgpack decodes a Decimal as str when sent over zeromq
        update = self.create_update()
        data = update.model_dump()
        data["snapshots"]["BYBIT_BTCUSDT"]["size"] = "-0.5"
        data["snapshots"]["BYBIT_BTCUSDT"]["avg_price"] = "95000"
        rebuilt = PositionUpdate[BasePosition.Snapshot].model_validate(data)
        snapshot = rebuilt.snapshots["BYBIT_BTCUSDT"]
        assert isinstance(snapshot.size, Quantity)
        assert snapshot.avg_price == Decimal("95000")
        assert isinstance(snapshot.avg_price, Decimal)

    def test_round_trip_with_subclass_snapshot(self):
        snapshot = VenuePosition.Snapshot(**create_snapshot().model_dump(), adl_rank=2)
        update = PositionUpdate[VenuePosition.Snapshot](
            venue="BYBIT",
            account="main",
            received_at=1,
            snapshots={"BYBIT_BTCUSDT": snapshot},
        )
        rebuilt = PositionUpdate[VenuePosition.Snapshot].model_validate(
            update.model_dump()
        )
        assert rebuilt.snapshots["BYBIT_BTCUSDT"].adl_rank == 2
