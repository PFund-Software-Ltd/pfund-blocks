from datetime import date

from pydantic import Field, SerializeAsAny

from pfund_blocks.entities.products.product_base import BaseProduct
from pfund_blocks.enums.month_code import FutureMonthCode


class BaseFutureProduct(BaseProduct):
    """Common base of dated futures and perpetuals, e.g. for later margin/contract size fields."""

    # SerializeAsAny so that to_dict() keeps the subclass fields, e.g. an index's or a future's specs
    underlying: SerializeAsAny[BaseProduct] | None = Field(
        default=None,
        description="the product the contract is on, e.g. SPX index for ES, None if it is just the base asset",
    )


class FutureProduct(BaseFutureProduct):
    """A contract to buy or sell the underlying at a set price on a future date."""

    expiration: date

    @property
    def contract_code(self) -> str:
        # e.g. expiration 2023-12-15 -> Z23
        month_code = list(FutureMonthCode)[self.expiration.month - 1]
        return f"{month_code}{self.expiration:%y}"

    def _create_symbol(self) -> str:
        # e.g. ES_USD_FUTURE expiring 2023-12-15 -> ESZ23
        return self.base_asset + self.contract_code
