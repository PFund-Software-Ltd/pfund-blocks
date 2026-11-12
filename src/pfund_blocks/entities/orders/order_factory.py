from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pfund_blocks.entities.orders.order_base import BaseOrder

from pfund.enums import TradingVenue

from pfund_blocks.enums.order_type import OrderType


def OrderFactory(  # noqa: N802
    venue: TradingVenue | str, order_type: OrderType | str
) -> type[BaseOrder]:
    import importlib

    VenueClass = TradingVenue[venue.upper()].venue_class  # noqa: N806 (holds a class)
    Order = VenueClass.Order  # noqa: N806 (holds a class)
    order_type = OrderType[order_type.upper()]
    OrderTypeMixin = getattr(  # noqa: N806 (holds a class)
        importlib.import_module(
            f"pfund_blocks.entities.orders.mixins.{order_type.lower()}_order"
        ),
        f"{order_type.capitalize()}OrderMixin",
    )
    class_name = (
        f"{Order.__name__.replace('Order', '')}"
        + OrderTypeMixin.__name__.replace("Mixin", "")
    )
    return type(class_name, (Order, OrderTypeMixin), {"__module__": __name__})
