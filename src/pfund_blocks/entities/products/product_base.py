from typing import Any, NamedTuple, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from pfund_blocks.entities.products.product_basis import ProductBasis
from pfund_blocks.entities.products.product_type import ProductType


class ProductKey(NamedTuple):
    """Unique key of a product within a source, the venue's symbol plus the product type,
    e.g. Bybit's BTCUSDT is both a spot pair and a perpetual."""

    symbol: str
    product_type: ProductType

    def __str__(self) -> str:
        # e.g. BTCUSDT.CRYPTO, BTCUSDT.PERPETUAL
        return f"{self.symbol}.{self.product_type}"


class BaseProduct(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    source: str = Field(
        description="""
            where the product comes from, either a trading venue (e.g. BYBIT, IBKR) or a data source (e.g. YAHOO_FINANCE).
            Whether the source is a trading venue is up to the consumer to decide, e.g. pfund checks it against its TradingVenue enum.
        """,
    )
    exchange: str | None = None
    basis: ProductBasis
    symbol: str = Field(
        default="",
        description="""
            product symbol used by the trading venue.
            If not provided, it will be derived automatically based on conventions e.g. AAPL_USD_STK -> AAPL.
            Note that the derived symbol might not be correct, it would be better to provide it manually when it is wrong.
        """,
    )
    name: str = Field(
        default="",
        description="unique product name, if not provided, source + symbol will be used",
    )

    @model_validator(mode="after")
    def _derive_symbol_and_name(self) -> Self:
        # NOTE: object.__setattr__ is needed since the model is frozen,
        # it is safe here because the product is still being constructed
        if not self.symbol:
            object.__setattr__(self, "symbol", self._create_symbol())
        if not self.name:
            object.__setattr__(self, "name", self._create_name())
        return self

    # Override this method to customize the symbol creation logic
    def _create_symbol(self) -> str:
        raise ValueError(
            f"symbol is required for {self.basis}, pass symbol=... or override _create_symbol()"
        )

    # Override this method to customize the name creation logic
    def _create_name(self) -> str:
        return f"{self.source}_{self.symbol}"

    @property
    def base_asset(self) -> str:
        return self.basis.base_asset

    base = base_asset

    @property
    def quote_asset(self) -> str:
        return self.basis.quote_asset

    quote = quote_asset

    @property
    def asset_pair(self) -> str:
        return self.basis.asset_pair

    @property
    def product_type(self) -> ProductType:
        return self.basis.product_type

    type = product_type

    @property
    def key(self) -> ProductKey:
        return ProductKey(symbol=self.symbol, product_type=self.product_type)

    @classmethod
    def get_allowed_specs(cls) -> set[str]:
        """Gets all spec field names (required + optional), i.e. the fields a product class adds on top of BaseProduct."""
        return set(cls.model_fields) - set(BaseProduct.model_fields)

    @classmethod
    def get_required_specs(cls) -> set[str]:
        """Gets spec fields that must be provided (no default)."""
        return {
            field_name
            for field_name in cls.get_allowed_specs()
            if cls.model_fields[field_name].is_required()
        }

    @property
    def specs(self) -> dict[str, Any]:
        """Specifications that make a product unique, e.g. for options, strike_price, expiration etc."""
        return {field_name: getattr(self, field_name) for field_name in sorted(self.get_allowed_specs())}

    def __str__(self) -> str:
        # e.g. BYBIT BTC_USDT_PERPETUAL (symbol=BTCUSDT, name=BYBIT_BTCUSDT)
        # NOTE: __repr__ is pydantic's default, which shows all fields including specs
        return f"{self.source} {self.basis} (symbol={self.symbol}, name={self.name})"

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump()

    def to_json(self) -> str:
        return self.model_dump_json()

    # shortcuts to the product type, e.g. product.is_perpetual() instead of product.type.is_perpetual()
    # asset type
    def is_etf(self) -> bool:
        return self.product_type.is_etf()

    def is_mutual_fund(self) -> bool:
        return self.product_type.is_mutual_fund()

    def is_future(self) -> bool:
        return self.product_type.is_future()

    def is_option(self) -> bool:
        return self.product_type.is_option()

    def is_index(self) -> bool:
        return self.product_type.is_index()

    def is_outcome(self) -> bool:
        return self.product_type.is_outcome()

    # modifiers
    def is_inverse(self) -> bool:
        return self.product_type.is_inverse()

    def is_perpetual(self) -> bool:
        return self.product_type.is_perpetual()

    is_perp = is_perpetual

    def is_leveraged(self) -> bool:
        return self.product_type.is_leveraged()

    # spot + asset class, same as the aliases STOCK, BOND etc., e.g. is_crypto_spot() is False for a crypto perpetual
    # NOTE: these are shortcuts for simple cases, for exposure instead, e.g. any crypto product, check product_type.asset_class directly
    def is_stock(self) -> bool:
        return self.product_type.is_stock()

    def is_bond(self) -> bool:
        return self.product_type.is_bond()

    def is_forex(self) -> bool:
        return self.product_type.is_forex()

    is_fx = is_forex

    def is_crypto_spot(self) -> bool:
        return self.product_type.is_crypto_spot()

    def is_commodity_spot(self) -> bool:
        return self.product_type.is_commodity_spot()
