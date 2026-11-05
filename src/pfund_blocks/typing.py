from __future__ import annotations

from typing import TYPE_CHECKING, Any, NamedTuple, TypedDict

if TYPE_CHECKING:
    from http import HTTPMethod

    from pfund_blocks.entities.markets.market_base import MarketDict

from dataclasses import dataclass, field

type ProductName = str
type ResolutionRepr = str  # repr(Resolution), e.g. "1m", "1t", "1q_L1"
type ResolutionStr = str  # str(Resolution), e.g. "1_MINUTE", "1_TICK", "1_QUOTE_L1"
type EndpointName = str  # also the REST API function name, e.g. "get_markets"
type AccountName = str
type FullChannel = str
type WebSocketName = str
type Currency = str
type RawMessage = bytes | str  # the venue's message as received
type DecodedMessage = Any  # the venue's decoded but unparsed message, e.g. JSON decoded
type ParsedMessage = Any  # the message parsed by the venue's parser
type RawResponse = Any  # the venue's decoded but unparsed response
# the response parsed by the venue's parser, a union of the standardized outputs, e.g. parse_markets -> list[MarketDict]
type ParsedResponse = list[MarketDict]


class Endpoint(NamedTuple):
    method: HTTPMethod
    path: str  # path after the base url, e.g. "/v5/market/instruments-info"


class ChannelInfo(NamedTuple):
    product: ProductName | None  # None for private channels
    resolution: str | None  # e.g. "1m", None for private channels


@dataclass(frozen=True, slots=True)
class Request:
    """A request built by an endpoint method, signed by the venue's signer if private.

    It holds everything needed to send the request, so that a signer can sign any part of it,
    e.g. Bybit signs headers over the serialized body, Hyperliquid adds a signature into the body.
    """

    name: EndpointName
    method: HTTPMethod
    path: str  # path after the base url, e.g. "/v5/market/instruments-info"
    params: dict[str, Any] | None = None  # query string parameters
    body: dict[str, Any] | None = None  # JSON body before signing
    headers: dict[str, str] = field(default_factory=dict)
    # exact bytes to send, set by a signer that signs the serialized body,
    # so that the body is not re-serialized differently after signing
    # NOTE: the signer must then also set the "Content-Type" header
    content: bytes | None = None
    private: bool = False  # if True, the request is signed before sending


class RequestData(TypedDict):
    """The request in a Reply, as plain data (e.g. for logging, pickling and serialization).

    e.g. built from the unsigned Request, with the full url instead of the path for debugging.
    """

    name: EndpointName
    method: HTTPMethod
    url: str
    params: dict[str, Any] | None


class Reply(TypedDict):
    """The outcome of sending a request, with both the raw and the parsed response."""

    success: bool
    error: str | None  # None if successful
    source: str  # a trading venue (e.g. BYBIT) or a data source (e.g. YAHOO_FINANCE)
    account: str | None  # account name, None for public requests
    request: RequestData
    status_code: int | None  # None if no response is received
    received_at: int | None  # int64 ns since epoch when the response was received, None if not received
    response: RawResponse | None  # None if no response is received
    data: ParsedResponse | None  # None if not parsed


class Message(TypedDict):
    """A received data or error message, with both the decoded and the parsed message."""

    source: str  # a trading venue (e.g. BYBIT) or a data source (e.g. YAHOO_FINANCE)
    account: AccountName | None  # None for public messages
    channel: FullChannel | None  # the subscribed channel, e.g. "kline.1.BTCUSDT", None if unknown, e.g. an error
    product: ProductName | None  # None if the message is not for a single product, e.g. balances
    resolution: ResolutionRepr | None  # e.g. "1m", None if the message is not market data
    received_at: int  # int64 ns since epoch when the message was received
    message: DecodedMessage | None  # the venue's decoded but unparsed message, None if opted out
    data: ParsedMessage | None  # parsed by parser, None if not parsed or an error
    error: str | None  # the venue's error, e.g. a rejected subscription, None if not an error
    extra: dict[str, Any]  # fields added after receiving, e.g. by a user's transformation, empty when received
