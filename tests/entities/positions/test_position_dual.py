from __future__ import annotations

from typing import Any

from decimal import Decimal

import pytest
from pydantic import ValidationError

from pfund_blocks.entities.positions.position_base import BasePosition
from pfund_blocks.entities.positions.position_dual import DualPosition
from pfund_blocks.entities.products.product_base import BaseProduct
from pfund_blocks.entities.trades.quantity import Quantity
from pfund_blocks.enums.position_mode import PositionMode
from pfund_blocks.enums.side import Side


@pytest.fixture
def product() -> BaseProduct:
    return BaseProduct(
        source="BYBIT",
        basis="BTC_USDT_PERP",  # ty: ignore[invalid-argument-type]
        symbol="BTCUSDT",
    )


@pytest.fixture
def position(product: BaseProduct) -> DualPosition:
    return DualPosition(product=product)


def create_long(**overrides: Any) -> BasePosition.Snapshot:
    fields: dict[str, Any] = {
        "updated_at": 1,
        "size": Decimal("2"),
        "avg_price": Decimal("100"),
        "mark_price": Decimal("105"),
        "liquidation_price": Decimal("50"),
        "initial_margin": Decimal("20"),
        "maintenance_margin": Decimal("1"),
        "unrealized_pnl": Decimal("10"),
        "realized_pnl": Decimal("-1"),
    }
    return BasePosition.Snapshot(**(fields | overrides))


def create_short(**overrides: Any) -> BasePosition.Snapshot:
    fields: dict[str, Any] = {
        "updated_at": 2,
        "size": Decimal("-1"),
        "avg_price": Decimal("110"),
        "mark_price": Decimal("106"),
        "liquidation_price": Decimal("200"),
        "initial_margin": Decimal("11"),
        "maintenance_margin": Decimal("0.5"),
        "unrealized_pnl": Decimal("4"),
        "realized_pnl": Decimal("-2"),
    }
    return BasePosition.Snapshot(**(fields | overrides))


# a venue's position class used for both legs
class VenuePosition(BasePosition):
    class Snapshot(BasePosition.Snapshot):
        adl_rank: int | None


class VenueDualPosition(DualPosition):
    VenuePosition = VenuePosition


class TestNewDualPosition:
    def test_has_no_snapshot(self, position: DualPosition):
        assert position.mode == PositionMode.DUAL
        assert position.snapshot is None
        assert position.long.snapshot is None
        assert position.short.snapshot is None
        assert position.size is None
        assert position.side is None

    def test_legs_are_normal_positions_of_the_same_product(
        self, position: DualPosition, product: BaseProduct
    ):
        assert type(position.long) is BasePosition
        assert type(position.short) is BasePosition
        assert position.long is not position.short
        assert position.long.product == position.short.product == product
        assert position.long.mode == position.short.mode == PositionMode.NORMAL

    def test_legs_use_venue_position(self, product: BaseProduct):
        position = VenueDualPosition(product=product)
        assert type(position.long) is VenuePosition
        assert type(position.short) is VenuePosition

    def test_is_empty_requires_a_snapshot(self, position: DualPosition):
        with pytest.raises(AssertionError, match="no snapshot yet"):
            position.is_empty()

    def test_compute_unrealized_pnl_requires_a_snapshot(self, position: DualPosition):
        with pytest.raises(AssertionError, match="no snapshot yet"):
            position.compute_unrealized_pnl(Decimal("105"))

    def test_can_be_dumped(self, position: DualPosition):
        dumped = position.model_dump()
        assert dumped["mode"] == PositionMode.DUAL
        assert dumped["size"] is None


class TestOnUpdate:
    def test_routes_to_the_leg(self, position: DualPosition):
        long, short = create_long(), create_short()
        position.on_update(Side.LONG, long)
        assert position.long.snapshot == long
        assert position.short.snapshot is None
        position.on_update(Side.SHORT, short)
        assert position.long.snapshot == long
        assert position.short.snapshot == short

    def test_replaces_the_leg_snapshot(self, position: DualPosition):
        position.on_update(Side.LONG, create_long())
        position.on_update(Side.LONG, create_long(size=Decimal("3")))
        assert position.long.size == position.size == Decimal("3")

    def test_flat_update_closes_one_leg(self, position: DualPosition):
        position.on_update(Side.LONG, create_long())
        position.on_update(Side.SHORT, create_short())
        position.on_update(Side.LONG, create_long(size=Decimal("0"), avg_price=None))
        assert position.long.is_empty()
        assert position.size == Decimal("-1")

    def test_long_leg_rejects_negative_size(self, position: DualPosition):
        with pytest.raises(ValueError, match="long leg size must be >= 0"):
            position.on_update(Side.LONG, create_long(size=Decimal("-1")))
        assert position.long.snapshot is None

    def test_short_leg_rejects_positive_size(self, position: DualPosition):
        with pytest.raises(ValueError, match="short leg size must be <= 0"):
            position.on_update(Side.SHORT, create_short(size=Decimal("1")))
        assert position.short.snapshot is None

    def test_rejects_invalid_side(self, position: DualPosition):
        with pytest.raises(ValueError, match="side must be LONG or SHORT"):
            position.on_update(None, create_long())  # ty: ignore[invalid-argument-type]

    def test_legs_enforce_venue_snapshot(self, product: BaseProduct):
        position = VenueDualPosition(product=product)
        with pytest.raises(ValidationError, match="model_type"):
            position.on_update(Side.LONG, create_long())


class TestNetSnapshot:
    def test_one_leg_is_the_net(self, position: DualPosition):
        position.on_update(Side.SHORT, create_short())
        assert position.size == Decimal("-1")
        assert isinstance(position.size, Quantity)
        assert position.side is Side.SHORT
        assert position.avg_price == Decimal("110")
        assert position.mark_price == Decimal("106")
        assert position.updated_at == 2
        assert position.unrealized_pnl == Decimal("4")
        assert position.realized_pnl == Decimal("-2")

    def test_net_long(self, position: DualPosition):
        position.on_update(Side.LONG, create_long())  # 2 @ 100
        position.on_update(Side.SHORT, create_short())  # -1 @ 110
        assert position.size == Decimal("1")
        assert isinstance(position.size, Quantity)
        assert position.side is Side.LONG
        assert position.avg_price == Decimal("100")

    def test_net_short(self, position: DualPosition):
        position.on_update(Side.LONG, create_long(size=Decimal("1")))
        position.on_update(Side.SHORT, create_short(size=Decimal("-2")))
        assert position.size == Decimal("-1")
        assert position.side is Side.SHORT
        assert position.avg_price == Decimal("110")

    def test_hedged_net_zero_is_not_empty(self, position: DualPosition):
        position.on_update(Side.LONG, create_long(size=Decimal("1")))
        position.on_update(Side.SHORT, create_short(size=Decimal("-1")))
        assert position.size == 0
        assert position.side is None
        assert position.avg_price is None
        assert not position.is_empty()

    def test_mark_price_and_updated_at_from_latest_leg(self, position: DualPosition):
        position.on_update(Side.SHORT, create_short(updated_at=2))
        position.on_update(Side.LONG, create_long(updated_at=1))
        assert position.updated_at == 2
        assert position.mark_price == Decimal("106")
        position.on_update(Side.LONG, create_long(updated_at=3))
        assert position.updated_at == 3
        assert position.mark_price == Decimal("105")

    def test_liquidation_price_and_margins_are_none(self, position: DualPosition):
        position.on_update(Side.LONG, create_long())
        position.on_update(Side.SHORT, create_short())
        assert position.liquidation_price is None
        assert position.initial_margin is None
        assert position.maintenance_margin is None
        assert position.long.liquidation_price == Decimal("50")
        assert position.short.initial_margin == Decimal("11")

    @pytest.mark.parametrize(
        ("long_pnl", "short_pnl", "net_pnl"),
        [
            (Decimal("10"), Decimal("4"), Decimal("14")),
            (Decimal("10"), None, Decimal("10")),
            (None, Decimal("4"), Decimal("4")),
            (None, None, None),
        ],
    )
    def test_pnls_are_summed(
        self,
        position: DualPosition,
        long_pnl: Decimal | None,
        short_pnl: Decimal | None,
        net_pnl: Decimal | None,
    ):
        position.on_update(
            Side.LONG, create_long(unrealized_pnl=long_pnl, realized_pnl=long_pnl)
        )
        position.on_update(
            Side.SHORT, create_short(unrealized_pnl=short_pnl, realized_pnl=short_pnl)
        )
        assert position.unrealized_pnl == net_pnl
        assert position.realized_pnl == net_pnl


class TestIsEmpty:
    def test_both_legs_flat(self, position: DualPosition):
        position.on_update(Side.LONG, create_long(size=Decimal("0")))
        position.on_update(Side.SHORT, create_short(size=Decimal("0")))
        assert position.is_empty()

    def test_one_leg_flat_and_the_other_without_snapshot(self, position: DualPosition):
        position.on_update(Side.LONG, create_long(size=Decimal("0")))
        assert position.is_empty()

    def test_one_leg_open(self, position: DualPosition):
        position.on_update(Side.LONG, create_long(size=Decimal("0")))
        position.on_update(Side.SHORT, create_short())
        assert not position.is_empty()


class TestComputeUnrealizedPnl:
    def test_sums_the_legs(self, position: DualPosition):
        position.on_update(Side.LONG, create_long())  # 2 @ 100
        position.on_update(Side.SHORT, create_short())  # -1 @ 110
        # 2 * (105 - 100) + -1 * (105 - 110), not net 1 * (105 - 100)
        assert position.compute_unrealized_pnl(Decimal("105")) == Decimal("15")

    def test_hedged_net_zero(self, position: DualPosition):
        position.on_update(Side.LONG, create_long(size=Decimal("1")))
        position.on_update(Side.SHORT, create_short(size=Decimal("-1")))
        assert position.compute_unrealized_pnl(Decimal("105")) == Decimal("10")

    def test_one_leg(self, position: DualPosition):
        position.on_update(Side.LONG, create_long())
        assert position.compute_unrealized_pnl(Decimal("105")) == Decimal("10")


class TestStrAndRepr:
    def test_str_and_repr(self, position: DualPosition, product: BaseProduct):
        position.on_update(Side.LONG, create_long())
        position.on_update(Side.SHORT, create_short())
        assert str(position) == (
            f"Product={product} | Mode=DUAL\n"
            "Net: Size=1 | AveragePrice=100 | MarkPrice=106 | "
            "UnrealizedPnL=14 | RealizedPnL=-3\n"
            "Long: Size=2 | AveragePrice=100 | MarkPrice=105 | "
            "LiquidationPrice=50 | UnrealizedPnL=10 | RealizedPnL=-1\n"
            "Short: Size=-1 | AveragePrice=110 | MarkPrice=106 | "
            "LiquidationPrice=200 | UnrealizedPnL=4 | RealizedPnL=-2"
        )
        assert repr(position) == (
            "BYBIT_BTCUSDT | DUAL | net=1@100 | long=2@100 | short=-1@110 | "
            "upnl=14 | rpnl=-3"
        )

    def test_new_position(self, position: DualPosition):
        assert repr(position) == (
            "BYBIT_BTCUSDT | DUAL | net=None@None | long=None@None | "
            "short=None@None | upnl=None | rpnl=None"
        )
