from typing import Any, Self

from datetime import datetime, timedelta
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from pfund_blocks.enums.option_type import OptionType


class OptionSpecs(BaseModel):
    """The market's option-only fields."""

    model_config = ConfigDict(frozen=True)

    option_type: OptionType
    strike_price: Decimal


class BaseMarket(BaseModel):
    model_config = ConfigDict(extra="allow")

    symbol: str
    base_asset: str
    quote_asset: str
    # NOTE: str instead of ProductType, importing ProductType here would be a circular import
    # (product_base imports market_base), it is validated by ProductType and stored in its canonical form
    product_type: str
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
    settlement_currency: str | None = Field(
        default=None, description="Settlement currency"
    )
    funding_interval: timedelta | None = Field(
        default=None, description="Funding interval"
    )
    option: OptionSpecs | None = Field(
        default=None,
        description="option-only fields, None if the market is not an option",
    )

    @field_validator("product_type", mode="before")
    @classmethod
    def _validate_product_type(cls, value: Any) -> str:
        from pfund_blocks.entities.products.product_type import ProductType

        return ProductType.model_validate(value).canonical

    @model_validator(mode="after")
    def _check_option(self) -> Self:
        from pfund_blocks.entities.products.product_type import ProductType

        is_option = ProductType.model_validate(self.product_type).is_option()
        if is_option and self.option is None:
            raise ValueError(f"{self.symbol} is an option market but option is not set")
        if not is_option and self.option is not None:
            raise ValueError(f"{self.symbol} is not an option market but option is set")
        return self
