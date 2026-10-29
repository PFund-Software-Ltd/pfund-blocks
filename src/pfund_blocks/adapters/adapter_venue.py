from __future__ import annotations

from typing import Literal

from pydantic import Field

from pfund_blocks.adapters.adapter_base import (
    AdapterGroup,
    BaseAdapter,
    ExternalValue,
)
from pfund_blocks.enums import MarginMode, OrderType, TimeInForce

type OrderStatusRepr = str
# = field names of VenueAdapter
type VenueAdapterGroup = (
    AdapterGroup
    | Literal[
        "margin_mode",
        "order_type",
        "order_status",
        "time_in_force",
    ]
)


# EXTEND: offsets (reduce_only etc.), price_directions (PlusTick, MinusTick, ZeroPlusTick, ZeroMinusTick ...)
class VenueAdapter(BaseAdapter[VenueAdapterGroup]):
    """Adapter of a trading venue, adds the trading groups (e.g. order types) to BaseAdapter.

    Usage:
        adapter.to_source(OrderType.LIMIT, group="order_type")  # -> "Limit", when sending to the venue
        adapter.from_source("Limit", group="order_type")  # -> OrderType.LIMIT, when parsing the venue's messages
    """

    margin_mode: dict[MarginMode, ExternalValue] = Field(default_factory=dict)
    order_type: dict[OrderType, ExternalValue] = Field(
        default_factory=dict, description="e.g. order type LIMIT -> Limit"
    )
    order_status: dict[OrderStatusRepr, ExternalValue] = Field(
        default_factory=dict,
        description="e.g. order status S--- -> Submitted, for more details, see __repr__ in order_status.py",
    )
    # the only group with a default: most venues use these abbreviations, override it if not
    # NOTE: pydantic copies mutable defaults per instance, ruff just doesn't see VenueAdapter as a pydantic model
    time_in_force: dict[TimeInForce, ExternalValue] = {  # noqa: RUF012
        TimeInForce.GoodTilCancel: "GTC",
        TimeInForce.FillOrKill: "FOK",
        TimeInForce.ImmediateOrCancel: "IOC",
    }
