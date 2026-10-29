from typing import Required, TypedDict

from datetime import datetime, timedelta
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from pfund_blocks.entities.products.product_type import ProductType
from pfund_blocks.enums.option_type import OptionType


class BaseMarket(BaseModel):
    model_config = ConfigDict(extra="allow")

    symbol: str
    base_asset: str
    quote_asset: str
    product_type: ProductType
    tick_size: Decimal | None = Field(
        default=None, description="Tick size, minimum price increment"
    )
    lot_size: Decimal | None = Field(
        default=None, description="Lot size, minimum quantity incrementc"
    )
    min_leverage: Decimal | None = Field(default=None, description="Minimum leverage")
    max_leverage: Decimal | None = Field(default=None, description="Maximum leverage")
    leverage_step: Decimal | None = Field(
        default=None, description="Leverage step size"
    )
    min_price: Decimal | None = Field(default=None, description="Minimum price")
    max_price: Decimal | None = Field(default=None, description="Maximum price")
    min_quantity: Decimal | None = Field(
        default=None, description="Minimum order quantity"
    )
    max_quantity: Decimal | None = Field(
        default=None, description="Maximum order quantity"
    )
    listed_at: datetime | None = Field(
        default=None, description="Date the market was listed"
    )
    expiration: datetime | None = Field(default=None, description="expiration date")
    settlement_currency: str | None = Field(default=None, description="Settlement currency")
    funding_interval: timedelta | None = Field(
        default=None, description="Funding interval"
    )


class MarketDict(TypedDict, total=False):
    """BaseMarket's fields as a plain dict, e.g. the output of a parser's parse_markets."""

    symbol: Required[str]
    base_asset: Required[str]
    quote_asset: Required[str]
    product_type: Required[ProductType]
    tick_size: Decimal | None
    lot_size: Decimal | None
    min_leverage: Decimal | None
    max_leverage: Decimal | None
    leverage_step: Decimal | None
    min_price: Decimal | None
    max_price: Decimal | None
    min_quantity: Decimal | None
    max_quantity: Decimal | None
    listed_at: datetime | None
    expiration: datetime | None
    settlement_currency: str | None
    funding_interval: timedelta | None


class OptionMarketDict(MarketDict, total=False):
    option_type: OptionType
    strike_price: Decimal
