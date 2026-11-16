from __future__ import annotations

from typing import Any

from decimal import Decimal

import pytest
from pydantic import ValidationError

from pfund_blocks.entities.positions.position_base import BasePosition
from pfund_blocks.entities.products.product_base import BaseProduct
from pfund_blocks.entities.trades.quantity import Quantity
from pfund_blocks.enums.position_mode import PositionMode
from pfund_blocks.enums.side import Side

SNAPSHOT_FIELDS = {
    "updated_at",
    "size",
    "avg_price",
    "mark_price",
    "liquidation_price",
    "initial_margin",
    "maintenance_margin",
    "unrealized_pnl",
    "realized_pnl",
}


@pytest.fixture
def product() -> BaseProduct:
    return BaseProduct(
        source="BYBIT",
        basis="BTC_USDT_PERP",  # ty: ignore[invalid-argument-type]
        symbol="BTCUSDT",
    )


@pytest.fixture
def position(product: BaseProduct) -> BasePosition:
    return BasePosition(product=product)


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


class TestSnapshot:
    def test_every_field_is_required(self):
        with pytest.raises(ValidationError) as exc_info:
            BasePosition.Snapshot(size=Decimal("1"))  # ty: ignore[missing-argument]
        missing = {
            error["loc"][0]
            for error in exc_info.value.errors()
            if error["type"] == "missing"
        }
        assert missing == SNAPSHOT_FIELDS - {"size"}

    def test_extra_field_is_rejected(self):
        with pytest.raises(ValidationError, match="extra_forbidden"):
            create_snapshot(oops=1)

    def test_is_frozen(self):
        snapshot = create_snapshot()
        with pytest.raises(ValidationError, match="frozen_instance"):
            snapshot.size = Quantity(1)  # ty: ignore[invalid-assignment]

    @pytest.mark.parametrize("field", ["avg_price", "mark_price", "liquidation_price"])
    def test_negative_price_is_rejected(self, field: str):
        with pytest.raises(ValidationError, match="greater_than_equal"):
            create_snapshot(**{field: Decimal("-1")})

    def test_size_is_converted_to_quantity(self):
        snapshot = create_snapshot(size="-0.5")
        assert snapshot.size == Decimal("-0.5")
        assert isinstance(snapshot.size, Quantity)


class TestBasePosition:
    def test_new_position_has_no_snapshot(self, position: BasePosition):
        assert position.snapshot is None
        assert position.mode == PositionMode.NORMAL
        assert position.updated_at is None
        assert position.side is None
        assert position.quantity is None
        with pytest.raises(AssertionError, match="no snapshot yet"):
            position.is_empty()

    def test_venue_is_product_source(self, position: BasePosition):
        assert position.venue == "BYBIT"

    def test_new_position_can_be_dumped_and_printed(
        self, position: BasePosition, product: BaseProduct
    ):
        dumped = position.model_dump()
        assert dumped.pop("product") == product.model_dump()
        assert dumped.pop("mode") == PositionMode.NORMAL
        assert dumped == dict.fromkeys(SNAPSHOT_FIELDS - {"updated_at"})
        assert str(position) == (
            f"Product={product}\n"
            "Size=None | AveragePrice=None | MarkPrice=None | LiquidationPrice=None\n"
            "UnrealizedPnL=None | RealizedPnL=None"
        )
        assert repr(position) == (
            "BYBIT_BTCUSDT | None@None | mark=None | liq=None | upnl=None | rpnl=None"
        )

    def test_on_update_replaces_snapshot(self, position: BasePosition):
        snapshot = create_snapshot()
        position.on_update(snapshot)
        assert position.snapshot == snapshot
        assert position.updated_at == snapshot.updated_at
        assert position.size == Decimal("-0.5")
        assert position.avg_price == Decimal("95000")
        assert position.mark_price == Decimal("94000")
        assert position.liquidation_price == Decimal("120000")
        assert position.initial_margin == Decimal("4750")
        assert position.maintenance_margin == Decimal("250")
        assert position.unrealized_pnl == Decimal("500")
        assert position.realized_pnl == Decimal("-12.3")

    def test_on_update_replaces_the_whole_snapshot(self, position: BasePosition):
        position.on_update(create_snapshot())
        position.on_update(create_snapshot(mark_price=None))
        assert position.mark_price is None
        assert position.avg_price == Decimal("95000")

    @pytest.mark.parametrize(
        ("size", "side"),
        [(Decimal("2"), Side.LONG), (Decimal("-0.5"), Side.SHORT)],
    )
    def test_side_and_quantity(self, position: BasePosition, size: Decimal, side: Side):
        position.on_update(create_snapshot(size=size))
        assert position.side is side
        assert position.quantity == position.qty == abs(size)
        assert isinstance(position.quantity, Quantity)
        assert not position.is_empty()

    def test_flat_position(self, position: BasePosition):
        position.on_update(create_snapshot(size=Decimal("0")))
        assert position.is_empty()
        assert position.side is None
        assert position.quantity == 0

    def test_aliases(self, position: BasePosition):
        position.on_update(create_snapshot())
        assert position.mark_px == position.mark_price
        assert (
            position.entry_price
            == position.entry_px
            == position.avg_px
            == position.avg_price
        )
        assert (
            position.liq_price
            == position.liq_px
            == position.liquidation_px
            == position.liquidation_price
        )
        assert position.upnl == position.unrealized_pnl
        assert position.rpnl == position.realized_pnl

    def test_aliases_are_not_dumped(self, position: BasePosition):
        dumped = position.model_dump()
        aliases = {"qty", "mark_px", "entry_price", "entry_px", "avg_px"}
        aliases |= {"liq_price", "liq_px", "liquidation_px", "upnl", "rpnl"}
        assert not aliases & dumped.keys()

    def test_compute_unrealized_pnl(self, position: BasePosition):
        position.on_update(create_snapshot())  # short 0.5 @ 95000
        assert position.compute_unrealized_pnl(Decimal("94000")) == Decimal("500")
        assert position.compute_unrealized_pnl(Decimal("96000")) == Decimal("-500")

    def test_compute_unrealized_pnl_when_flat(self, position: BasePosition):
        position.on_update(create_snapshot(size=Decimal("0"), avg_price=None))
        assert position.compute_unrealized_pnl(Decimal("94000")) == 0

    def test_compute_unrealized_pnl_requires_size_and_avg_price(
        self, position: BasePosition
    ):
        with pytest.raises(AssertionError, match="no snapshot yet"):
            position.compute_unrealized_pnl(Decimal("94000"))
        position.on_update(create_snapshot(avg_price=None))
        with pytest.raises(AssertionError, match="avg_price is None"):
            position.compute_unrealized_pnl(Decimal("94000"))

    def test_str_and_repr(self, position: BasePosition, product: BaseProduct):
        position.on_update(create_snapshot())
        assert str(position) == (
            f"Product={product}\n"
            "Size=-0.5 | AveragePrice=95000 | MarkPrice=94000 | LiquidationPrice=120000\n"
            "UnrealizedPnL=500 | RealizedPnL=-12.3"
        )
        assert repr(position) == (
            "BYBIT_BTCUSDT | -0.5@95000 | mark=94000 | liq=120000 | upnl=500 | rpnl=-12.3"
        )

    def test_extra_field_is_rejected(self, product: BaseProduct):
        with pytest.raises(ValidationError, match="extra_forbidden"):
            BasePosition(product=product, oops=1)  # ty: ignore[unknown-argument]


class TestSubclassSnapshot:
    def test_on_update_with_subclass_snapshot(self, product: BaseProduct):
        position = VenuePosition(product=product)
        fields = create_snapshot().model_dump()
        position.on_update(VenuePosition.Snapshot(**fields, adl_rank=2))
        assert position.snapshot.adl_rank == 2  # ty: ignore[missing-attribute]

    def test_on_update_rejects_base_snapshot(self, product: BaseProduct):
        position = VenuePosition(product=product)
        with pytest.raises(ValidationError, match="model_type"):
            position.on_update(create_snapshot())
