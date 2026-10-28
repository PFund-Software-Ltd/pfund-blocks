from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, GetCoreSchemaHandler, HttpUrl
from pydantic_core import core_schema

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
    def __get_pydantic_core_schema__(cls, source_type: Any, handler: GetCoreSchemaHandler) -> core_schema.CoreSchema:
        # not a validatable/serializable value — just a sentinel; validate by identity of type
        return core_schema.is_instance_schema(cls)


ALL_PERIODS = _AllPeriods()
type ResolutionPeriod = int
type SupportedResolutions = dict[Resolution | Timeframe, list[ResolutionPeriod] | _AllPeriods]


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


class BaseVenue:
    pass
