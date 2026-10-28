from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar, Literal

if TYPE_CHECKING:
    from pfund_blocks.entities.adapters.adapter_venue import VenueAdapter
    from pfund_blocks.entities.products.product_base import BaseProduct
    from pfund_blocks.entities.products.product_basis import ProductBasis

from pydantic import BaseModel, ConfigDict, Field, GetCoreSchemaHandler, HttpUrl
from pydantic_core import core_schema

from pfund_blocks.entities.products.product_factory import ProductFactory
from pfund_blocks.entities.products.product_type import ProductType
from pfund_blocks.enums.env import Environment
from pfund_blocks.enums.timeframe import Timeframe
from pfund_blocks.resolution import Resolution


class _AllPeriods:
    """Sentinel for "any period" in SupportedResolutions, use the ALL_PERIODS instance.

    e.g. {Resolution("QUOTE_L2"): ALL_PERIODS} means any orderbook depth is supported.
    It only supports `in`, which is True for any int, so `period in supported_periods`
    works the same whether the value is a list of periods or ALL_PERIODS.
    """

    def __contains__(self, item: Any):
        return isinstance(item, int)

    @classmethod
    def __get_pydantic_core_schema__(
        cls, source_type: Any, handler: GetCoreSchemaHandler
    ) -> core_schema.CoreSchema:
        # not a validatable/serializable value — just a sentinel; validate by identity of type
        return core_schema.is_instance_schema(cls)


ALL_PERIODS = _AllPeriods()
type ResolutionPeriod = int
type SupportedResolutions = dict[
    Resolution | Timeframe, list[ResolutionPeriod] | _AllPeriods
]


class VenueMetadata(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    url: HttpUrl
    envs: list[Literal[Environment.PAPER, Environment.LIVE]] = Field(
        description="trading environments offered by the venue, e.g. [PAPER, LIVE] if it has a testnet/paper account"
    )
    product_types: list[ProductType]
    docs_url: HttpUrl | None = None
    github_repo: HttpUrl | None = None
    is_repo_official: bool | None = None


class VenueConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    cancel_all_at: list[Literal["start", "reconnect", "stop"]] = Field(
        default=["start", "reconnect", "stop"],
    )
    refetch_markets: bool = Field(
        default=False,
        description="refetch markets.yml on startup, if the trading venue has an endpoint to fetch all trading markets.",
    )
    stream_api_first: bool = Field(
        default=True,
        description="Always use the Stream API (e.g. WebSocket API) for actions such as placing or canceling orders, even if RESTful API is available.",
    )


# DRAFT: the unified interface is driven by pfund-bybit, pfund-hyperliquid, pfund-alpaca and pfund-ibkr together
class BaseVenue:
    metadata: ClassVar[VenueMetadata]
    # set by the subclass, holds the venue's mappings, e.g. product name -> symbol
    # NOTE: class-level to be consistent with pfeed's BaseSource.adapter,
    # so the product mappings are shared by all instances of the venue
    adapter: ClassVar[VenueAdapter]

    @property
    def name(self) -> str:
        return self.metadata.name

    def create_product(
        self, basis: str | ProductBasis, symbol: str = "", name: str = "", **specs: Any
    ) -> BaseProduct:
        """Creates a product with the venue's symbol and name, and maps them in the adapter's group "product".

        Args:
            basis: e.g. "BTC_USDT_PERP"
            symbol: the venue's symbol, if not provided, derived by the adapter's create_symbol(),
                pass it when the derived symbol is wrong
            name: unique product name, if not provided, derived by the adapter's create_name()
            specs: the product class's specs, e.g. expiration for a future
        """
        Product = ProductFactory(basis)
        # the adapter is passed via the validation context, so that the product derives its symbol and name
        # with the venue's conventions once its specs are validated (e.g. expiration as a date)
        product = Product.model_validate(
            {
                "source": self.name,
                "basis": basis,
                "symbol": symbol,
                "name": name,
                **specs,
            },
            context={"adapter": self.adapter},
        )
        self.adapter.add_mapping(product.name, product.symbol, group="product")
        return product
