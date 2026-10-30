from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar, Literal, cast

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from pfund_blocks.entities.accounts.account_base import BaseAccount
    from pfund_blocks.entities.products.product_base import BaseProduct
    from pfund_blocks.parsers.parser_base import BaseParser
    from pfund_blocks.resolution import Resolution
    from pfund_blocks.typing import (
        AccountName,
        DecodedMessage,
        FullChannel,
        Message,
        ProductName,
        RawMessage,
        WebSocketName,
    )

import asyncio
import inspect
import logging
import time
from abc import ABC, abstractmethod

import websockets
from msgspec import json
from websockets.asyncio.client import ClientConnection
from websockets.exceptions import ConnectionClosed, ConnectionClosedError

from pfund_blocks.enums import Channel, ChannelType, Environment, PrivateChannel
from pfund_blocks.typing import ChannelInfo


class WebSocket(ClientConnection):
    name: WebSocketName  # set once connected, for logging and routing


class BaseWebSocketAPI(ABC):
    venue: ClassVar[str]  # upper case, consistent with BaseRestAPI.venue, e.g. "BYBIT"
    urls: ClassVar[dict[Literal[Environment.PAPER, Environment.LIVE], dict[ChannelType, str]]]
    version: ClassVar[str | None] = None  # e.g. "v5" for Bybit, None if the venue's API is not versioned
    parser: ClassVar[BaseParser | None] = None  # None if messages are not parsed, i.e. callbacks only get raw messages
    # the venue's app-level ping, e.g. {"op": "ping"} for Bybit, None if not required.
    # NOTE: protocol-level pings (for detecting dead connections) are always sent by websockets
    ping_message: ClassVar[dict[str, Any] | None] = None
    ping_interval: ClassVar[float] = 20  # seconds between app-level pings

    def __init__(self, env: Literal[Environment.PAPER, Environment.LIVE, "PAPER", "LIVE"]):
        """
        Args:
            env: PAPER (e.g. testnet) or LIVE.
        """
        self._env = self._validate_env(env)
        self._logger = logging.getLogger(f"pfund.{self.venue.lower()}")

        self._products: dict[ProductName, BaseProduct] = {}
        self._accounts: dict[AccountName, BaseAccount] = {}
        self._channels: dict[ChannelType, list[FullChannel]] = {
            ChannelType.public: [],
            ChannelType.private: [],
        }
        # filled when channels are created, to know a message's channel (for parsing) and product
        self._channel_infos: dict[FullChannel, ChannelInfo] = {}

        self._websockets: dict[WebSocketName, WebSocket] = {}
        self._is_running = False
        self._callback: Callable[[Message], Awaitable[None] | None] | None = None
        self._include_raw_message = True

    @staticmethod
    def _validate_env(env: Environment | str) -> Literal[Environment.PAPER, Environment.LIVE]:
        env = Environment(env.upper())
        if env not in (Environment.PAPER, Environment.LIVE):
            raise ValueError(f"environment {env} is not supported, only PAPER or LIVE")
        return env

    @property
    def env(self) -> Literal[Environment.PAPER, Environment.LIVE]:
        return self._env

    def add_account(self, account: BaseAccount) -> None:
        if account.env != self._env:
            raise ValueError(f"account env {account.env} does not match websocket env {self._env}")
        if account.venue != self.venue:
            raise ValueError(f"account venue {account.venue} does not match websocket venue {self.venue}")
        if account in self._accounts.values():
            return
        if account.name not in self._accounts:
            self._accounts[account.name] = account
        else:
            raise ValueError(f"account name {account.name} has already been registered")

    def add_product(self, product: BaseProduct) -> None:
        if product in self._products.values():
            return
        if product.name not in self._products:
            self._products[product.name] = product
        else:
            raise ValueError(f"product name {product.name} has already been registered")

    def create_market_data_channel(self, product: BaseProduct, resolution: Resolution) -> FullChannel:
        """Creates the venue's market data channel of the product, e.g. "kline.1.BTCUSDT" for Bybit's 1m bars."""
        supported_resolutions = self.get_supported_resolutions(product)
        if resolution not in supported_resolutions:
            raise ValueError(
                f"{self.venue} {product.name} {resolution=} is not supported, " +
                f"supported resolutions: {[repr(r) for r in supported_resolutions]}"
            )
        full_channel = self._create_market_data_channel(product, resolution)
        self.add_product(product)
        if resolution.is_quote():
            channel = Channel.orderbook
        elif resolution.is_tick():
            channel = Channel.tradebook
        else:
            channel = Channel.candlestick
        self._channel_infos[full_channel] = ChannelInfo(channel=channel, product=product.name)
        return full_channel

    @abstractmethod
    def _create_market_data_channel(self, product: BaseProduct, resolution: Resolution) -> FullChannel: ...

    @abstractmethod
    def get_supported_resolutions(self, product: BaseProduct) -> list[Resolution]:
        """Returns the resolutions the venue streams for the product, checked in create_market_data_channel(),
        e.g. Bybit's depend on the product's category.
        """
        ...

    def create_private_channels(self) -> list[FullChannel]:
        """Creates the venue's channels for private data (balances, positions, orders, trades),
        e.g. ["wallet", "position", "order", "execution"] for Bybit.

        A venue's channels don't map cleanly to PrivateChannel, e.g. Alpaca's order and trade updates
        are both "trade_updates", and it has no balance channel at all.
        So by default, every PrivateChannel mapped in the parser's adapter's "channel" group is used,
        an unmapped one means the venue doesn't stream it.
        Override it for venue-specific channels.

        NOTE: account-specific parts (e.g. Hyperliquid's user address) are not in the channel,
        they are added to the subscription request on the account's connection.
        """
        if self.parser is None:
            raise ValueError(f"{self.venue} has no parser, override create_private_channels() without its adapter")
        channels: list[FullChannel] = []
        for private_channel in PrivateChannel:
            try:
                # NOTE: strict=True, otherwise an unmapped channel is returned as is and wrongly subscribed
                echannel = str(self.parser.adapter.to_source(Channel(private_channel), group="channel", strict=True))
            except KeyError:
                continue  # unmapped, i.e. the venue doesn't stream it
            if echannel not in channels:
                channels.append(echannel)
                self._channel_infos[echannel] = ChannelInfo(channel=Channel(private_channel), product=None)
        return channels

    def add_channel(self, channel: FullChannel, *, channel_type: ChannelType | Literal["public", "private"]):
        channel_type = ChannelType(channel_type.lower())
        if channel not in self._channels[channel_type]:
            self._channels[channel_type].append(channel)
            self._logger.debug(f"added {channel_type} channel '{channel}'")

    def remove_channel(self, channel: FullChannel, *, channel_type: ChannelType | Literal["public", "private"]):
        channel_type = ChannelType(channel_type.lower())
        if channel in self._channels[channel_type]:
            self._channels[channel_type].remove(channel)
            self._logger.debug(f"removed {channel_type} channel '{channel}'")

    @abstractmethod
    async def subscribe(self, ws: WebSocket, channels: list[FullChannel], channel_type: ChannelType) -> None:
        """Converts the channels into the venue's subscription request(s) and sends them via _send().

        NOTE: a manual call only lasts until the websocket reconnects, also call add_channel() to keep it.
        """
        ...

    @abstractmethod
    async def unsubscribe(self, ws: WebSocket, channels: list[FullChannel], channel_type: ChannelType) -> None:
        """Converts the channels into the venue's unsubscription request(s) and sends them via _send().

        NOTE: a manual call only lasts until the websocket reconnects, also call remove_channel() to keep it.
        """
        ...

    def set_callback(self, callback: Callable[[Message], Awaitable[None] | None], *, include_raw_message: bool = True) -> None:
        """Sets the callback that receives every data and error message (control messages are filtered out by _parse_message).

        The callback can be sync or async, a sync one runs in the event loop, so it should return quickly.

        Args:
            include_raw_message: if False, Message["message"] (the venue's raw message) is None,
                e.g. to reduce the size of messages serialized via zeromq when only the parsed data is needed.
        """
        if not include_raw_message and self.parser is None:
            raise ValueError(f"{self.venue} has no parser, the venue's message can't be excluded")
        self._callback = callback
        self._include_raw_message = include_raw_message

    @abstractmethod
    def _parse_message(self, ws: WebSocket, raw_msg: RawMessage) -> tuple[FullChannel | None, DecodedMessage] | None:
        """Decodes the venue's message (e.g. JSON, decompression) and finds its channel.
        The decoded message is then checked for errors and parsed by the venue's parser.

        Returns:
            None for control messages (e.g. successful subscription acks, pongs), not passed to the callback,
            otherwise (full_channel, decoded message), where full_channel is None if unknown, e.g. a venue's error.
            NOTE: a venue's error (e.g. a rejected subscription) must not be returned as None, otherwise it is dropped.
        """
        ...

    async def _send(self, ws: WebSocket, msg: dict[str, Any]) -> None:
        await ws.send(json.encode(msg), text=True)
        self._logger.debug(f"{ws.name} sent {msg}")

    # TODO: step 4, auth before subscribe, reads its own reply via ws.recv() and raises if failed
    # @abstractmethod
    # async def _authenticate(self, ws: WebSocket, account: BaseAccount) -> None: ...

    async def _ping_loop(self, ws: WebSocket) -> None:
        assert self.ping_message is not None
        try:
            while True:
                await asyncio.sleep(self.ping_interval)
                await self._send(ws, self.ping_message)
        except ConnectionClosed:
            pass  # the message loop handles the closed connection

    def _get_url(self, channel_type: ChannelType) -> str:
        return self.urls[self._env][channel_type]

    def _create_ws_name(self, account: BaseAccount | None = None) -> WebSocketName:
        if account:
            return f"{account.name}_ws"
        else:
            return f"{self.venue.lower()}_ws"

    def get_websocket(self, account: BaseAccount | None = None) -> WebSocket:
        """Returns the connected public websocket, or the private one of the account, e.g. for manual subscribe()."""
        ws_name = self._create_ws_name(account)
        if ws_name not in self._websockets:
            raise ConnectionError(f"{ws_name} is not connected")
        return self._websockets[ws_name]

    def _add_websocket(self, ws_name: WebSocketName, ws: WebSocket) -> None:
        if ws_name in self._websockets:
            raise ValueError(f"{ws_name} already exists")
        ws.name = ws_name
        self._websockets[ws_name] = ws

    async def connect(self) -> None:
        """Connects all websockets and runs until disconnect() is called.
        One websocket for public channels, one per account for private channels.

        Raises if any websocket fails, the others are then cancelled.
        """
        public_channels = self._channels[ChannelType.public]
        private_channels = self._channels[ChannelType.private]
        if private_channels and not self._accounts:
            raise ValueError(f"private channels {private_channels} are added but no accounts")
        if not public_channels and not private_channels:
            raise ValueError("no channels added, nothing to connect")
        if self._callback is None:
            self._logger.warning("no callback set, data messages will be dropped")
        # set before any websocket starts, so that even a drop during startup is reconnected
        self._is_running = True
        try:
            async with asyncio.TaskGroup() as tg:
                if public_channels:
                    tg.create_task(self._connect_ws())
                if private_channels:
                    for account in self._accounts.values():
                        tg.create_task(self._connect_ws(account=account))
        finally:
            self._is_running = False

    async def _connect_ws(self, account: BaseAccount | None = None) -> None:
        # one public websocket, one private websocket per account
        channel_type = ChannelType.public if account is None else ChannelType.private
        ws_name = self._create_ws_name(account)
        url = self._get_url(channel_type)
        self._logger.debug(f"{ws_name} is connecting to {url}")
        # NOTE: this async for IS the reconnect loop, each iteration is a new connection.
        # failed handshakes are retried with exponential backoff (capped at 60s) on retryable errors (network, 5xx),
        # fatal ones (e.g. 401) raise.
        async for conn in websockets.connect(url, create_connection=WebSocket):
            if not self._is_running:  # disconnect() was called during the handshake
                break
            ws = cast(WebSocket, conn)  # connect() isn't generic, it is typed as ClientConnection
            self._add_websocket(ws_name, ws)
            self._logger.debug(f"{ws_name} is connected")
            ping_task = asyncio.create_task(self._ping_loop(ws)) if self.ping_message else None
            try:
                # TODO: step 4
                # if account:
                #     await self._authenticate(ws, account)
                # read on every (re)connection, so that reconnects resubscribe the latest channels
                await self.subscribe(ws, self._channels[channel_type], channel_type)
                # ends normally when closed with code 1000 (by disconnect() or the server), raises when dropped
                async for raw_msg in ws:
                    received_at = time.time()
                    try:
                        # NOTE: _parse_message() runs even without a callback, it also handles control messages
                        if (result := self._parse_message(ws, raw_msg)) is None or self._callback is None:
                            continue
                        full_channel, msg = result
                        error = self.parser.parse_message_error(full_channel, msg) if self.parser else None
                        data = None
                        if self.parser and full_channel and error is None:
                            data = self.parser.parse_message(self._channel_infos[full_channel].channel, msg)
                        channel_info = self._channel_infos.get(full_channel) if full_channel else None
                        message: Message = {
                            "source": self.venue,
                            "account": account.name if account else None,
                            "product": channel_info.product if channel_info else None,
                            "channel": full_channel,
                            "received_at": received_at,
                            "message": raw_msg if self._include_raw_message else None,
                            "data": data,
                            "error": error,
                        }
                        if inspect.isawaitable(ret := self._callback(message)):
                            await ret
                    except Exception:
                        # one bad message shouldn't kill the stream
                        self._logger.exception(f"{ws_name} failed to handle message {raw_msg!r}")
            except ConnectionClosedError as err:
                self._logger.warning(f"{ws_name} connection lost ({err})")
            finally:
                if ping_task:
                    ping_task.cancel()
                del self._websockets[ws_name]
            if not self._is_running:  # closed by disconnect()
                break
            self._logger.warning(f"{ws_name} is reconnecting")
        self._logger.warning(f"{ws_name} is disconnected")

    async def disconnect(self, reason: str = "") -> None:
        """Closes all websockets, which ends their message loops so that connect() returns."""
        self._is_running = False
        for ws_name, ws in list(self._websockets.items()):
            self._logger.info(f"{ws_name} is disconnecting, {reason=}")
            await ws.close(code=1000, reason=reason)
