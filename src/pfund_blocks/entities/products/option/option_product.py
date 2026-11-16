from typing import Any

from datetime import date
from decimal import Decimal

from pydantic import Field, SerializeAsAny, field_validator

from pfund_blocks.entities.products.product_base import BaseProduct
from pfund_blocks.enums.option_type import OptionType
from pfund_blocks.utils import trim_trailing_zeros


# TODO: add Greeks
class OptionProduct(BaseProduct):
    """A right, not an obligation, to buy (call) or sell (put) the underlying at the strike price."""

    expiration: date
    strike_price: Decimal = Field(ge=0)
    option_type: OptionType
    # SerializeAsAny so that to_dict() keeps the subclass fields, e.g. the expiration of a future
    underlying: SerializeAsAny[BaseProduct] | None = Field(
        default=None,
        description="the product the option is on, e.g. a FutureProduct for a future option, None if it is just the base asset",
    )

    @field_validator("option_type", mode="before")
    @classmethod
    def _uppercase_option_type(cls, option_type: Any) -> Any:
        # e.g. "call" -> "CALL"
        return option_type.upper() if isinstance(option_type, str) else option_type

    @field_validator("strike_price", mode="after")
    @classmethod
    def _trim_strike_price(cls, strike_price: Decimal) -> Decimal:
        # e.g. 75.00 -> 75, so that the same strike makes the same product
        return trim_trailing_zeros(strike_price)

    def _create_symbol(self) -> str:
        # OSI (Option Symbology Initiative) format, e.g. TSLA 2024-12-13 75 CALL -> TSLA241213C00075000
        # i.e. root + yymmdd + C/P + strike x 1000 padded to 8 digits
        strike_price = str(int(self.strike_price * 1000)).zfill(8)
        return f"{self.base_asset}{self.expiration:%y%m%d}{self.option_type[0]}{strike_price}"
