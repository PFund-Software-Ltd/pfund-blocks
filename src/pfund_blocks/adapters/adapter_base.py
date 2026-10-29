from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar, Literal

if TYPE_CHECKING:
    from pfund_blocks.entities.products.product_base import BaseProduct

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, field_validator

from pfund_blocks.entities.products.product_type import ProductType
from pfund_blocks.enums import Channel, OptionType, Side
from pfund_blocks.resolution import Resolution
from pfund_blocks.typing import Currency

type InternalName = str
# sources don't always use strings, e.g. Hyperliquid sends side as a bool (is_buy)
type ExternalValue = str | int | bool
# = field names of BaseAdapter
type AdapterGroup = Literal[
    "product",
    "product_type",
    "asset",
    "side",
    "option_type",
    "channel",
    "channel_resolution",
]


class BaseAdapter[GroupT: str = AdapterGroup](BaseModel):
    """Maps pfund's internal values to a source's external values, per group (= field name).

    A source is anything with its own naming, either a trading venue (see VenueAdapter) or a data source (e.g. Yahoo Finance),
    so this class only has the groups both need, e.g. products, sides (e.g. in trade ticks) and channels.

    Each field is the internal -> external mapping; the external -> internal index is built from it.
    Several internal values can share one external value (e.g. Bybit's category "linear" covers
    several product types), in which case from_source() can't tell them apart and raises.

    Usage:
        adapter.to_source(Side.BUY, group="side")  # -> "Buy", when sending to the source
        adapter.from_source("Buy", group="side")  # -> Side.BUY, when parsing the source's messages
        adapter.add_mapping(product.name, product.symbol, group="product")  # runtime mapping, both directions

    Override create_symbol() and create_name() for the source's product conventions,
    they are called by the product itself when it's validated with the adapter in the context, e.g.
        Product.model_validate({...}, context={"adapter": adapter})
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
        default_factory=dict,
        description="e.g. side BUY -> Buy, also used by data sources, e.g. the aggressor side of a trade tick",
    )
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
    _from_source: dict[str, dict[ExternalValue, list[Any]]] = PrivateAttr(
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
            self._from_source[group] = {}
            for internal, external in getattr(self, group).items():
                self._index(group, internal, external)

    def _index(self, group: str, internal: Any, external: ExternalValue) -> None:
        """Adds internal to the external -> internals index for O(1) reverse lookup.

        Appends instead of overwriting, so several internal values sharing one external value are all kept.
        """
        internals = self._from_source[group].setdefault(external, [])
        if internal not in internals:
            internals.append(internal)

    def to_source(self, internal: Any, *, group: GroupT, strict: bool = False) -> Any:
        """Converts an internal value to the source's, e.g. to_source(Side.BUY, group="side") -> "Buy".

        An unmapped value is returned as is, since most values are the same on the source, unless strict=True.
        """
        mapping: dict[Any, ExternalValue] = getattr(self, group)
        if internal not in mapping:
            if strict:
                raise KeyError(f"{internal!r} has no source mapping in group '{group}'")
            return internal
        return mapping[internal]

    def from_source(
        self, external: ExternalValue, *, group: GroupT, strict: bool = False
    ) -> Any:
        """Converts a source's value to the internal one, e.g. from_source("Buy", group="side") -> Side.BUY.

        An unmapped value is returned as is, unless strict=True.
        An ambiguous value always raises, since returning it as is would hide that it maps to several internal values.
        """
        internals = self._from_source[group].get(external)
        if not internals:
            if strict:
                raise KeyError(
                    f"source value {external!r} has no internal mapping in group '{group}'"
                )
            return external
        if len(internals) > 1:
            raise KeyError(
                f"source value {external!r} in group '{group}' is ambiguous, it maps to {internals}"
            )
        return internals[0]

    def add_mapping(
        self, internal: Any, external: ExternalValue, *, group: GroupT
    ) -> None:
        """Adds a mapping at runtime, e.g. a product's symbol once the product is added."""
        if group not in type(self).model_fields:
            raise ValueError(f"unknown adapter group '{group}'")
        mapping: dict[Any, ExternalValue] = getattr(self, group)
        # remapping an internal value drops it from its old external value's index
        if internal in mapping:
            self._from_source[group][mapping[internal]].remove(internal)
        mapping[internal] = external
        self._index(group, internal, external)

    # Override this method for the source's symbol conventions
    def create_symbol(self, product: BaseProduct) -> str:
        """Derives the source's symbol of a product, called by the product during validation.

        Defaults to the product class's own convention, e.g. BTC_USDT_CRYPTO -> BTCUSDT.
        """
        return product._create_symbol()

    # Override this method for the source's name conventions, e.g. when the source's symbols aren't unique
    def create_name(self, product: BaseProduct) -> str:
        """Derives the unique name of a product, called by the product during validation, after its symbol is set.

        Defaults to the product class's own convention, i.e. source + symbol.
        """
        return product._create_name()
