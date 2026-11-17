from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar, Literal, cast

if TYPE_CHECKING:
    from collections.abc import Coroutine, Mapping

    from pfund_blocks.adapters.adapter_venue import VenueAdapter
    from pfund_blocks.entities import BaseProduct
    from pfund_blocks.entities.products.product_basis import ProductBasis
    from pfund_blocks.typing import AccountName, ProductName

import asyncio
import json
import logging
import queue
import warnings
from pathlib import Path

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    GetCoreSchemaHandler,
    HttpUrl,
)
from pydantic_core import core_schema

from pfund_blocks.entities.accounts.account_base import BaseAccount
from pfund_blocks.entities.markets.market_base import BaseMarket
from pfund_blocks.entities.products.product_base import ProductKey
from pfund_blocks.entities.products.product_factory import create_product
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
    cache_path: Path = Field(
        default=Path.home() / ".pfund" / "cache",
        description="where the venue's cached files are stored, e.g. {cache_path}/BYBIT/markets.json",
    )
    refetch_markets: bool = Field(
        default=False,
        description="refetch markets.json on startup, if the trading venue has an endpoint to fetch all trading markets.",
    )
    stream_api_first: bool = Field(
        default=True,
        description="Always use the Stream API (e.g. WebSocket API) for actions such as placing or canceling orders, even if RESTful API is available.",
    )


# DRAFT: the unified interface is driven by pfund-bybit, pfund-hyperliquid, pfund-alpaca and pfund-ibkr together
class BaseVenue[
    AccountT: BaseAccount,
    MarketT: BaseMarket,
    ConfigT: VenueConfig,
]:
    MARKETS_FILENAME: ClassVar[str] = "markets.json"

    metadata: ClassVar[VenueMetadata]
    # set by the subclass, holds the venue's mappings, e.g. product name -> symbol
    # NOTE: class-level to be consistent with pfeed's BaseSource.adapter,
    # so the product mappings are shared by all instances of the venue
    adapter: ClassVar[VenueAdapter]
    Config: ClassVar[type[VenueConfig]]

    Account: ClassVar[type[BaseAccount]]
    Market: ClassVar[type[BaseMarket]]

    def __init__(
        self,
        env: Environment | str,
        config: ConfigT | None = None,
        read_only: bool = True,
    ):
        """
        Args:
            read_only: if True (default), the venue can only read, e.g. fetch markets, funding rates, balances,
                and can't change any state, e.g. place or cancel orders.
        """
        self._env = Environment(env.upper())
        if self._env == Environment.BACKTEST:
            warnings.warn(
                f"{self.__class__.__name__} is created with env=BACKTEST, make sure it is not passed in by mistake.",
                stacklevel=2,
            )
        self._logger: logging.Logger = logging.getLogger(f"pfund.{self.name.lower()}")

        self._config: ConfigT = config or cast(ConfigT, self.Config())
        self._queue: queue.Queue[Any] | None = None

        self._accounts: dict[AccountName, AccountT] = {}
        self._products: dict[ProductName, BaseProduct] = {}
        self._markets: Mapping[ProductKey, MarketT] | None = None

        # TODO: read_only is stored but NOT enforced yet
        self._read_only = read_only

        self.initialize_markets()

    @property
    def env(self) -> Environment:
        return self._env

    @property
    def name(self) -> str:
        return self.metadata.name

    @property
    def accounts(self) -> dict[AccountName, AccountT]:
        return self._accounts

    @property
    def products(self) -> dict[ProductName, BaseProduct]:
        return self._products

    @classmethod
    def get_streaming_resolutions(cls, product: BaseProduct) -> list[Resolution]:
        """Returns the resolutions the venue can stream for the product, e.g. used to decide what to resample from.

        For streaming only, the resolutions of historical data (e.g. REST klines) may differ.
        Callers don't need to know which API of the venue streams the data,
        each venue decides it, e.g. Bybit returns its websocket API's resolutions.
        """
        raise NotImplementedError(
            f"{cls.metadata.name} has not implemented get_streaming_resolutions()"
        )

    def initialize_markets(self):
        """Loads the venue's markets into self._markets, refetches them if refetch_markets=True or the markets file is missing.

        Skipped if the venue has not implemented get_markets().
        """
        # NOTE: compared on the class, self.get_markets is a bound method, which is never BaseVenue.get_markets
        can_fetch_markets = type(self).get_markets is not BaseVenue.get_markets
        if not can_fetch_markets:
            return
        data_path = self._config.cache_path
        markets_file = self.get_markets_file_path(data_path)
        if self._config.refetch_markets or not markets_file.exists():
            self._markets = self.refetch_markets(data_path)
        else:
            self._markets = self.load_markets(data_path)

    # NOTE: Mapping since it is covariant in the value, so a venue can return its own market class
    async def get_markets(self) -> Mapping[ProductKey, MarketT]:
        """Fetches all the venue's markets, keyed by ProductKey (symbol + product type)."""
        raise NotImplementedError(f"{self.name} has not implemented get_markets()")

    def get_markets_sync(
        self, *args: Any, **kwargs: Any
    ) -> Mapping[ProductKey, MarketT]:
        return self._run_async(self.get_markets(*args, **kwargs))

    @classmethod
    def get_markets_file_path(cls, data_path: Path) -> Path:
        """Returns the path of the venue's markets file, e.g. {data_path}/BYBIT/markets.json."""
        return data_path / cls.metadata.name / cls.MARKETS_FILENAME

    def refetch_markets(self, data_path: Path) -> Mapping[ProductKey, MarketT]:
        """Fetches the venue's markets by get_markets() and dumps them to the markets file.

        Raises if get_markets() returns no markets, so that the existing file is not overwritten by nothing.
        """
        markets: Mapping[ProductKey, MarketT] = self.get_markets_sync()
        if not markets:
            raise RuntimeError(
                f"{self.name} get_markets() returned no markets, the markets file is not updated"
            )
        file_path = self.get_markets_file_path(data_path)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        # NOTE: keyed by str(ProductKey), e.g. "BTCUSDT.PERPETUAL"
        document = {
            str(key): market.model_dump(mode="json") for key, market in markets.items()
        }
        file_path.write_text(json.dumps(document, indent=2))
        return markets

    @classmethod
    def load_markets(cls, data_path: Path) -> dict[ProductKey, MarketT]:
        """Loads the venue's markets from the markets file, returns {} if the file does not exist."""
        file_path = cls.get_markets_file_path(data_path)
        if not file_path.exists():
            return {}
        document: dict[str, dict[str, Any]] = json.loads(file_path.read_text())
        markets: dict[ProductKey, MarketT] = {}
        for key, market in document.items():
            # NOTE: rsplit since a symbol may contain ".", e.g. BRK.B, a product type never does
            symbol, product_type = key.rsplit(".", 1)
            product_key = ProductKey(symbol, ProductType.model_validate(product_type))
            markets[product_key] = cast("MarketT", cls.Market.model_validate(market))
        return markets

    @staticmethod
    def _run_async[T](coro: Coroutine[Any, Any, T]) -> T:
        """Runs an async method from sync code, e.g. get_markets() in refetch_markets()."""
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            # no running event loop, safe to run the coroutine with asyncio.run()
            return asyncio.run(coro)
        coro.close()  # avoid "coroutine was never awaited" RuntimeWarning
        raise RuntimeError(
            "can't run an async method from sync code inside a running event loop, await it instead"
        )

    def is_read_only(self) -> bool:
        return self._read_only

    def _set_queue(self, queue: queue.Queue[Any]) -> None:
        """Set the queue for the venue to send data back to the trade engine."""
        self._queue = queue

    def get_account(self, name: AccountName) -> AccountT:
        return self.accounts[name]

    def add_account(self, account: AccountT) -> None:
        """Registers the account, adding the same account again is a no-op."""
        if account.venue != self.name:
            raise ValueError(
                f"account venue {account.venue} does not match venue {self.name}"
            )
        if account.env != self._env:
            raise ValueError(
                f"account env {account.env} does not match venue env {self._env}"
            )
        existing = self._accounts.get(account.name)
        if existing is None:
            self._accounts[account.name] = account
        elif existing != account:
            raise ValueError(
                f"account name {account.name} is already registered by {existing!r}"
            )

    @classmethod
    def create_product(
        cls, basis: str | ProductBasis, symbol: str = "", name: str = "", **specs: Any
    ) -> BaseProduct:
        """Creates a product with the venue's symbol and name, and maps them in the adapter's group "product".

        Args:
            basis: e.g. "BTC_USDT_PERP"
            symbol: the venue's symbol, if not provided, derived by the adapter's create_symbol(),
                pass it when the derived symbol is wrong
            name: unique product name, if not provided, derived by the adapter's create_name()
            specs: the product class's specs, e.g. expiration for a future
        """
        return create_product(
            cls.metadata.name,
            basis,
            cls.adapter,
            symbol=symbol,
            name=name,
            **specs,
        )

    def get_product(self, name: ProductName) -> BaseProduct:
        return self.products[name]

    def add_product(self, product: BaseProduct) -> None:
        """Registers the product, adding the same product again is a no-op.

        The product's symbol is already mapped in the adapter by create_product().
        If the venue has markets, the product's market is attached, raises if the product has no market.
        """
        if product.source != self.name:
            raise ValueError(
                f"product source {product.source} does not match venue {self.name}"
            )
        existing = self._products.get(product.name)
        if existing is None:
            if product.market is None and self._markets is not None:
                if product.key not in self._markets:
                    raise ValueError(
                        f"{product.key} is not in {self.name}'s markets, "
                        f"the markets file {self.get_markets_file_path(self._config.cache_path)} may be outdated, "
                        f"set the venue config's refetch_markets=True and re-run to refetch it"
                    )
                # NOTE: object.__setattr__ is needed since the product is frozen,
                # it is safe since the market is not part of the product's identity (ignored by == and hash())
                object.__setattr__(product, "market", self._markets[product.key])
            self._products[product.name] = product
        elif existing != product:
            raise ValueError(
                f"product name {product.name} is already registered by {existing}"
            )
