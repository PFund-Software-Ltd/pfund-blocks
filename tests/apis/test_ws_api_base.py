from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from pytest_mock import MockerFixture

    from pfund_blocks.typing import DecodedMessage, FullChannel, Message, RawMessage

import asyncio

import pytest
import websockets
from msgspec import json
from websockets.asyncio.server import ServerConnection

from pfund_blocks.adapters.adapter_base import BaseAdapter
from pfund_blocks.apis.ws_api_base import BaseWebSocketAPI, WebSocket
from pfund_blocks.entities.accounts.api_account import APIKeyAccount
from pfund_blocks.entities.products.product_base import BaseProduct
from pfund_blocks.enums import Channel, ChannelType, Environment
from pfund_blocks.parsers.parser_base import BaseParser
from pfund_blocks.resolution import Resolution
from pfund_blocks.typing import ChannelInfo

KLINE = "1m.BTCUSDT"  # = DummyWebSocketAPI._create_market_data_channel(BTCUSDT, 1m)


class DummyParser(BaseParser):
    # NOTE: order and trade share one channel, e.g. Alpaca's "trade_updates"; no balance channel
    adapter = BaseAdapter(
        channel={
            Channel.position: "position",
            Channel.order: "trade_updates",
            Channel.trade: "trade_updates",
        }
    )
    ws_api = {Channel.candlestick: "parse_candlestick"}  # noqa: RUF012

    def parse_candlestick(self, message: dict[str, Any]) -> list[int]:
        return [x * 10 for x in message["data"]]

    def parse_message_error(
        self, channel: FullChannel | None, message: dict[str, Any]
    ) -> str | None:
        return message["ret_msg"] if message.get("success") is False else None


class DummyWebSocketAPI(BaseWebSocketAPI):
    venue: ClassVar[str] = "DUMMY"
    urls = {  # noqa: RUF012
        Environment.PAPER: {
            ChannelType.public: "ws://paper.dummy",
            ChannelType.private: "ws://paper.dummy/private",
        },
        Environment.LIVE: {
            ChannelType.public: "ws://live.dummy",
            ChannelType.private: "ws://live.dummy/private",
        },
    }
    parser = DummyParser()

    def __init__(self, env: Any = "LIVE", url: str = ""):
        super().__init__(env)
        self.url = url  # the local test server
        self.subscribed: list[list[FullChannel]] = []

    def _get_url(self, channel_type: ChannelType) -> str:
        return self.url or super()._get_url(channel_type)

    def _create_market_data_channel(
        self, product: BaseProduct, resolution: Resolution
    ) -> FullChannel:
        return f"{resolution!r}.{product.symbol}"

    def get_supported_resolutions(self, product: BaseProduct) -> list[Resolution]:
        return [Resolution("1m"), Resolution("1t"), Resolution("1q")]

    async def subscribe(
        self, ws: WebSocket, channels: list[FullChannel], channel_type: ChannelType
    ) -> None:
        self.subscribed.append(list(channels))
        await self._send(ws, {"op": "subscribe", "args": channels})

    async def unsubscribe(
        self, ws: WebSocket, channels: list[FullChannel], channel_type: ChannelType
    ) -> None:
        await self._send(ws, {"op": "unsubscribe", "args": channels})

    def _parse_message(
        self, ws: WebSocket, raw_msg: RawMessage
    ) -> tuple[FullChannel | None, DecodedMessage] | None:
        msg = json.decode(raw_msg)
        if "op" in msg:
            # a successful subscription ack is a control message, a rejected one is the venue's error
            return None if msg["success"] else (None, msg)
        return msg["topic"], msg


class NoParserWebSocketAPI(DummyWebSocketAPI):
    parser = None


def create_product(symbol: str = "BTCUSDT", name: str = "") -> BaseProduct:
    data = {"source": "DUMMY", "basis": "BTC_USDT_PERP", "symbol": symbol}
    return BaseProduct.model_validate({**data, "name": name} if name else data)


def create_account(
    env: str = "LIVE", venue: str = "DUMMY", name: str = "acc"
) -> APIKeyAccount:
    return APIKeyAccount(env=env, venue=venue, name=name, key="key", secret="secret")


@pytest.fixture
def api() -> DummyWebSocketAPI:
    return DummyWebSocketAPI()


class TestInit:
    def test_env_is_case_insensitive(self):
        assert DummyWebSocketAPI("paper").env == Environment.PAPER

    def test_unsupported_env_raises(self):
        with pytest.raises(ValueError, match="only PAPER or LIVE"):
            DummyWebSocketAPI("BACKTEST")


class TestAddAccount:
    def test_add(self, api: DummyWebSocketAPI):
        account = create_account()
        api.add_account(account)
        assert api._accounts == {"acc": account}

    def test_same_account_is_ignored(self, api: DummyWebSocketAPI):
        api.add_account(create_account())
        api.add_account(create_account())
        assert len(api._accounts) == 1

    def test_env_mismatch_raises(self, api: DummyWebSocketAPI):
        with pytest.raises(ValueError, match="does not match websocket env"):
            api.add_account(create_account(env="PAPER"))

    def test_venue_mismatch_raises(self, api: DummyWebSocketAPI):
        with pytest.raises(ValueError, match="does not match websocket venue"):
            api.add_account(create_account(venue="OTHER"))


class TestAddProduct:
    def test_same_product_is_ignored(self, api: DummyWebSocketAPI):
        api.add_product(create_product())
        api.add_product(create_product())
        assert list(api._products) == ["DUMMY_BTCUSDT"]

    def test_duplicate_name_raises(self, api: DummyWebSocketAPI):
        api.add_product(create_product(name="btc"))
        with pytest.raises(
            ValueError, match="product name btc has already been registered"
        ):
            api.add_product(create_product(symbol="BTC-PERP", name="btc"))


class TestCreateMarketDataChannel:
    @pytest.mark.parametrize(
        "resolution, channel",
        [
            ("1m", Channel.candlestick),
            ("1t", Channel.tradebook),
            ("1q", Channel.orderbook),
        ],
    )
    def test_channel_info(
        self, api: DummyWebSocketAPI, resolution: str, channel: Channel
    ):
        product = create_product()
        full_channel = api.create_market_data_channel(product, Resolution(resolution))
        assert api._channel_infos[full_channel] == ChannelInfo(
            channel=channel, product=product.name
        )

    def test_adds_the_product(self, api: DummyWebSocketAPI):
        product = create_product()
        api.create_market_data_channel(product, Resolution("1m"))
        assert api._products == {product.name: product}

    def test_unsupported_resolution_raises(self, api: DummyWebSocketAPI):
        with pytest.raises(ValueError, match="is not supported, supported resolutions"):
            api.create_market_data_channel(create_product(), Resolution("5m"))
        assert api._products == {}


class TestCreatePrivateChannels:
    def test_mapped_channels_without_duplicates(self, api: DummyWebSocketAPI):
        assert api.create_private_channels() == ["position", "trade_updates"]

    def test_channel_info_of_shared_channel_is_the_first_mapped(
        self, api: DummyWebSocketAPI
    ):
        api.create_private_channels()
        assert api._channel_infos["position"] == ChannelInfo(
            channel=Channel.position, product=None
        )
        assert api._channel_infos["trade_updates"] == ChannelInfo(
            channel=Channel.order, product=None
        )

    def test_no_parser_raises(self):
        with pytest.raises(ValueError, match="has no parser"):
            NoParserWebSocketAPI().create_private_channels()


class TestChannels:
    def test_add_and_remove(self, api: DummyWebSocketAPI):
        api.add_channel(KLINE, channel_type="public")
        api.add_channel(KLINE, channel_type=ChannelType.public)
        assert api._channels[ChannelType.public] == [KLINE]
        api.remove_channel(KLINE, channel_type="public")
        assert api._channels[ChannelType.public] == []

    def test_remove_missing_is_ignored(self, api: DummyWebSocketAPI):
        api.remove_channel(KLINE, channel_type="private")
        assert api._channels[ChannelType.private] == []


class TestSetCallback:
    def test_exclude_raw_message_without_parser_raises(self):
        with pytest.raises(ValueError, match="the venue's message can't be excluded"):
            NoParserWebSocketAPI().set_callback(
                lambda message: None, include_raw_message=False
            )


class TestWebSockets:
    def test_get_unconnected_raises(self, api: DummyWebSocketAPI):
        with pytest.raises(ConnectionError, match="dummy_ws is not connected"):
            api.get_websocket()

    def test_ws_name(self, api: DummyWebSocketAPI):
        assert api._create_ws_name() == "dummy_ws"
        assert api._create_ws_name(create_account()) == "acc_ws"

    def test_add_duplicate_raises(self, api: DummyWebSocketAPI):
        api._add_websocket("dummy_ws", object.__new__(WebSocket))
        with pytest.raises(ValueError, match="dummy_ws already exists"):
            api._add_websocket("dummy_ws", object.__new__(WebSocket))


class TestConnectChecks:
    def test_no_channels_raises(self, api: DummyWebSocketAPI):
        with pytest.raises(ValueError, match="no channels added"):
            asyncio.run(api.connect())

    def test_private_channels_without_accounts_raises(self, api: DummyWebSocketAPI):
        api.add_channel("position", channel_type="private")
        with pytest.raises(ValueError, match="no accounts"):
            asyncio.run(api.connect())


class Server:
    """A local venue: acks subscriptions (or rejects them), then sends the messages of `on_subscribe`."""

    def __init__(self, on_subscribe: list[bytes | str], reject: bool = False):
        self.on_subscribe = on_subscribe
        self.reject = reject
        self.received: list[dict[str, Any]] = []
        self.connections: list[ServerConnection] = []

    async def handler(self, conn: ServerConnection) -> None:
        self.connections.append(conn)
        async for raw_msg in conn:
            msg = json.decode(raw_msg)
            self.received.append(msg)
            if msg.get("op") == "subscribe":
                ack = (
                    {"op": "subscribe", "success": False, "ret_msg": "invalid topic"}
                    if self.reject
                    else {"op": "subscribe", "success": True}
                )
                await conn.send(json.encode(ack).decode())
                for m in self.on_subscribe:
                    await conn.send(m)


def kline(*data: int) -> str:
    return json.encode({"topic": KLINE, "data": list(data)}).decode()


async def run(
    api: DummyWebSocketAPI,
    server: Server,
    until: Callable[[], bool],
    during: Callable[[], Awaitable[None]] | None = None,
) -> None:
    """Connects api to the server, runs `during` once connected, and disconnects when `until()` is true."""
    async with websockets.serve(server.handler, "localhost", 0) as ws_server:
        port = ws_server.sockets[0].getsockname()[1]
        api.url = f"ws://localhost:{port}"
        task = asyncio.create_task(api.connect())
        async with asyncio.timeout(5):
            while not server.connections:
                await asyncio.sleep(0.01)
            if during:
                await during()
            while not until():
                await asyncio.sleep(0.01)
        await api.disconnect()
        await task


def connected_api(**callback_kwargs: Any) -> tuple[DummyWebSocketAPI, list[Message]]:
    api = DummyWebSocketAPI()
    api.add_channel(
        api.create_market_data_channel(create_product(), Resolution("1m")),
        channel_type="public",
    )
    received: list[Message] = []
    api.set_callback(received.append, **callback_kwargs)
    return api, received


class TestMessageFlow:
    def test_callback_gets_parsed_data_messages_only(self):
        api, received = connected_api()
        server = Server([kline(1, 2)])
        asyncio.run(run(api, server, until=lambda: len(received) == 1))
        message = received[0]
        assert server.received == [{"op": "subscribe", "args": [KLINE]}]
        assert message["source"] == "DUMMY"
        assert message["account"] is None
        assert message["product"] == "DUMMY_BTCUSDT"
        assert message["channel"] == KLINE
        assert message["data"] == [10, 20]
        assert message["message"] == kline(1, 2)
        assert isinstance(message["received_at"], float)
        assert message["error"] is None

    def test_venue_error_goes_to_callback(self):
        api, received = connected_api()
        server = Server([], reject=True)
        asyncio.run(run(api, server, until=lambda: len(received) == 1))
        message = received[0]
        assert message["error"] == "invalid topic"
        assert message["channel"] is None
        assert message["product"] is None
        assert message["data"] is None

    def test_no_parser_passes_the_raw_message_only(self):
        api = NoParserWebSocketAPI()
        api.add_channel(
            api.create_market_data_channel(create_product(), Resolution("1m")),
            channel_type="public",
        )
        received: list[Message] = []
        api.set_callback(received.append)
        asyncio.run(run(api, Server([kline(1)]), until=lambda: len(received) == 1))
        message = received[0]
        assert message["channel"] == KLINE
        assert message["message"] == kline(1)
        assert message["data"] is None
        assert message["error"] is None

    def test_exclude_raw_message(self):
        api, received = connected_api(include_raw_message=False)
        asyncio.run(run(api, Server([kline(1)]), until=lambda: len(received) == 1))
        assert received[0]["message"] is None
        assert received[0]["data"] == [10]

    def test_bad_message_does_not_kill_the_stream(self):
        api, received = connected_api()
        asyncio.run(
            run(api, Server(["not json", kline(1)]), until=lambda: len(received) == 1)
        )
        assert received[0]["data"] == [10]

    def test_async_callback(self):
        api, received = connected_api()

        async def callback(message: Message) -> None:
            await asyncio.sleep(0)
            received.append(message)

        api.set_callback(callback)
        asyncio.run(run(api, Server([kline(1)]), until=lambda: len(received) == 1))
        assert received[0]["data"] == [10]

    def test_no_callback_still_handles_messages(self):
        api = DummyWebSocketAPI()
        api.add_channel(
            api.create_market_data_channel(create_product(), Resolution("1m")),
            channel_type="public",
        )
        server = Server([kline(1)])
        asyncio.run(run(api, server, until=lambda: bool(server.received)))
        assert server.received == [{"op": "subscribe", "args": [KLINE]}]

    def test_disconnect_removes_the_websocket(self):
        api, received = connected_api()
        asyncio.run(run(api, Server([kline(1)]), until=lambda: len(received) == 1))
        assert api._websockets == {}
        assert api._is_running is False


class TestReconnect:
    def test_dropped_connection_resubscribes_the_latest_channels(self):
        api, received = connected_api()
        server = Server([kline(1)])

        async def drop() -> None:
            while not received:
                await asyncio.sleep(0.01)
            api.add_channel("1m.ETHUSDT", channel_type="public")
            server.connections[0].transport.abort()  # dropped without a close frame

        asyncio.run(run(api, server, until=lambda: len(received) == 2, during=drop))
        assert len(server.connections) == 2
        assert api.subscribed == [[KLINE], [KLINE, "1m.ETHUSDT"]]

    def test_server_close_reconnects(self):
        api, received = connected_api()
        server = Server([kline(1)])

        async def close() -> None:
            while not received:
                await asyncio.sleep(0.01)
            await server.connections[0].close()

        asyncio.run(run(api, server, until=lambda: len(received) == 2, during=close))
        assert len(server.connections) == 2


class PingWebSocketAPI(DummyWebSocketAPI):
    ping_message: ClassVar[dict[str, Any] | None] = {"op": "ping"}
    ping_interval: ClassVar[float] = 0.01


class TestPing:
    def test_sends_ping_message(self):
        api = PingWebSocketAPI()
        api.add_channel(KLINE, channel_type="public")
        server = Server([])
        asyncio.run(run(api, server, until=lambda: {"op": "ping"} in server.received))
        assert server.received[0] == {"op": "subscribe", "args": [KLINE]}

    def test_no_ping_message_sends_no_pings(self, mocker: MockerFixture):
        api = DummyWebSocketAPI()
        ping_loop = mocker.spy(api, "_ping_loop")
        api.add_channel(KLINE, channel_type="public")
        server = Server([])
        asyncio.run(run(api, server, until=lambda: bool(server.received)))
        ping_loop.assert_not_called()
