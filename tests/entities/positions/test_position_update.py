from __future__ import annotations

from typing import Any

from decimal import Decimal

import pytest
from pydantic import ValidationError

from pfund_blocks.entities.positions.position_base import BasePosition
from pfund_blocks.entities.positions.position_update import PositionUpdate
from pfund_blocks.entities.trades.quantity import Quantity
from pfund_blocks.enums.side import Side


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
            "product": "BYBIT_BTCUSDT",
            "side": None,
            "position": create_snapshot(),
        }
        return PositionUpdate[BasePosition.Snapshot](**(fields | overrides))

    def test_create(self):
        update = self.create_update()
        assert update.venue == "BYBIT"
        assert update.account == "main"
        assert update.product == "BYBIT_BTCUSDT"
        assert update.side is None
        assert update.position == create_snapshot()

    def test_side_of_hedge_mode_leg(self):
        update = self.create_update(side="SHORT")
        assert update.side is Side.SHORT

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
        data["position"]["size"] = "-0.5"
        data["position"]["avg_price"] = "95000"
        rebuilt = PositionUpdate[BasePosition.Snapshot].model_validate(data)
        snapshot = rebuilt.position
        assert isinstance(snapshot.size, Quantity)
        assert snapshot.avg_price == Decimal("95000")
        assert isinstance(snapshot.avg_price, Decimal)

    def test_round_trip_with_subclass_snapshot(self):
        snapshot = VenuePosition.Snapshot(**create_snapshot().model_dump(), adl_rank=2)
        update = PositionUpdate[VenuePosition.Snapshot](
            venue="BYBIT",
            account="main",
            received_at=1,
            product="BYBIT_BTCUSDT",
            side=None,
            position=snapshot,
        )
        rebuilt = PositionUpdate[VenuePosition.Snapshot].model_validate(
            update.model_dump()
        )
        assert rebuilt.position.adl_rank == 2
