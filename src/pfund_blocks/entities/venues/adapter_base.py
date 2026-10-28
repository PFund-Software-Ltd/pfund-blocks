from __future__ import annotations

from typing import Any, ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, field_validator

from pfund_blocks.entities.products.product_type import ProductType
from pfund_blocks.enums import (
    Channel,
    MarginMode,
    OptionType,
    OrderType,
    Side,
    TimeInForce,
)
from pfund_blocks.resolution import Resolution
from pfund_blocks.typing import Currency

type OrderStatusRepr = str
type InternalName = str
# venues don't always use strings, e.g. Hyperliquid sends side as a bool (is_buy)
type ExternalValue = str | int | bool
# = field names of BaseAdapter
type AdapterGroup = Literal[
    "product",
    "product_type",
    "asset",
    "side",
    "margin_mode",
    "order_type",
    "order_status",
    "time_in_force",
    "option_type",
    "channel",
    "channel_resolution",
]


# EXTEND: product_specs (per asset type, if necessary), offsets (reduce_only etc.), price_directions (PlusTick, MinusTick, ZeroPlusTick, ZeroMinusTick ...)
class BaseAdapter(BaseModel):
    """Maps pfund's internal values to a venue's external values, per group (= field name).

    Each field is the internal -> external mapping; the external -> internal index is built from it.
    Several internal values can share one external value (e.g. Bybit's category "linear" covers
    several product types), in which case from_venue() can't tell them apart and raises.

    Usage:
        adapter.to_venue(Side.BUY, group="side")  # -> "Buy", when sending to the venue
        adapter.from_venue("Buy", group="side")  # -> Side.BUY, when parsing the venue's messages
        adapter.add_mapping(product.name, product.symbol, group="product")  # runtime mapping, both directions
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(
        arbitrary_types_allowed=True, extra="forbid"
    )

    product: dict[InternalName, ExternalValue] = Field(
        default_factory=dict,
        description="product.name -> product.symbol, dynamically added",
    )
    product_type: dict[ProductType, ExternalValue] = Field(
        default_factory=dict,
        description="e.g. product type FUTURE-CRYPTO-PERPETUAL -> LinearPerpetual",
    )
    asset: dict[Currency, ExternalValue] = Field(
        default_factory=dict, description="assets mappings, e.g. BTC -> XBT"
    )
    side: dict[Side, ExternalValue] = Field(
        default_factory=dict, description="e.g. side BUY -> Buy"
    )
    margin_mode: dict[MarginMode, ExternalValue] = Field(default_factory=dict)
    order_type: dict[OrderType, ExternalValue] = Field(
        default_factory=dict, description="e.g. order type LIMIT -> Limit"
    )
    order_status: dict[OrderStatusRepr, ExternalValue] = Field(
        default_factory=dict,
        description="e.g. order status S--- -> Submitted, for more details, see __repr__ in order_status.py",
    )
    # the only group with a default: most venues use these abbreviations, override it if not
    time_in_force: dict[TimeInForce, ExternalValue] = {
        TimeInForce.GoodTilCancel: "GTC",
        TimeInForce.FillOrKill: "FOK",
        TimeInForce.ImmediateOrCancel: "IOC",
    }
    option_type: dict[OptionType, ExternalValue] = Field(
        default_factory=dict, description="e.g. option type CALL -> Call"
    )
    channel: dict[Channel, ExternalValue] = Field(
        default_factory=dict, description="e.g. tradebook -> publicTrade"
    )
    channel_resolution: dict[Resolution, ExternalValue] = Field(
        default_factory=dict, description="e.g. 1m -> 1"
    )

    # group -> external -> internals; kept separate from the fields (internal -> external)
    # so that an internal value equal to its external value (e.g. StrEnum OrderType.LIMIT == "LIMIT") can't collide
    _from_venue: dict[str, dict[ExternalValue, list[Any]]] = PrivateAttr(
        default_factory=dict
    )

    @field_validator("channel_resolution", mode="before")
    @classmethod
    def _coerce_resolution_keys(cls, channel_resolution: Any) -> Any:
        """Coerce all str keys to Resolution, e.g. '1m' -> Resolution('1m')."""
        if not isinstance(channel_resolution, dict):
            return channel_resolution
        return {
            (key if isinstance(key, Resolution) else Resolution(key)): value
            for key, value in channel_resolution.items()
        }

    def model_post_init(self, context: Any) -> None:
        super().model_post_init(context)
        for group in type(self).model_fields:
            self._from_venue[group] = {}
            for internal, external in getattr(self, group).items():
                self._index(group, internal, external)

    def _index(self, group: str, internal: Any, external: ExternalValue) -> None:
        """Adds internal to the external -> internals index for O(1) reverse lookup.

        Appends instead of overwriting, so several internal values sharing one external value are all kept.
        """
        internals = self._from_venue[group].setdefault(external, [])
        if internal not in internals:
            internals.append(internal)

    def to_venue(self, internal: Any, *, group: AdapterGroup) -> ExternalValue:
        """Converts an internal value to the venue's, e.g. to_venue(Side.BUY, group="side") -> "Buy"."""
        mapping: dict[Any, ExternalValue] = getattr(self, group)
        if internal not in mapping:
            raise KeyError(f"{internal!r} has no venue mapping in group '{group}'")
        return mapping[internal]

    def from_venue(self, external: ExternalValue, *, group: AdapterGroup) -> Any:
        """Converts a venue's value to the internal one, e.g. from_venue("Buy", group="side") -> Side.BUY."""
        internals = self._from_venue[group].get(external)
        if not internals:
            raise KeyError(
                f"venue value {external!r} has no internal mapping in group '{group}'"
            )
        if len(internals) > 1:
            raise KeyError(
                f"venue value {external!r} in group '{group}' is ambiguous, it maps to {internals}"
            )
        return internals[0]

    def add_mapping(
        self, internal: Any, external: ExternalValue, *, group: AdapterGroup
    ) -> None:
        """Adds a mapping at runtime, e.g. a product's symbol once the product is added."""
        if group not in type(self).model_fields:
            raise ValueError(f"unknown adapter group '{group}'")
        mapping: dict[Any, ExternalValue] = getattr(self, group)
        # remapping an internal value drops it from its old external value's index
        if internal in mapping:
            self._from_venue[group][mapping[internal]].remove(internal)
        mapping[internal] = external
        self._index(group, internal, external)
