from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

if TYPE_CHECKING:
    from pfund_blocks.adapters.adapter_base import BaseAdapter
    from pfund_blocks.entities.markets.market_base import MarketDict
    from pfund_blocks.enums import Channel
    from pfund_blocks.typing import (
        DecodedMessage,
        EndpointName,
        FullChannel,
        ParsedResponse,
        RawResponse,
    )

from pfund_blocks.parsers.dsl import parse_schema


class BaseParser:
    """Parses a venue's responses into standardized data, shared by its REST and WS APIs.

    Subclasses map each API function (REST) or channel (WS) to the name of its parsing method, e.g.
        rest_api = {"get_markets": "parse_markets"}
        ws_api = {Channel.candlestick: "parse_candlestick"}
    so that maintainers can see which function or channel uses which parsing method.
    A parsing method takes the venue's response and returns the standardized data.
    The standard parsing methods (e.g. parse_markets) are declared below with their return types,
    so that overriding them with a different output fails type checking.

    For APIs other than REST and WS (e.g. FIX), define your own table and parse with
    self._parse(table, name, response), e.g.
        fix_api = {"new_order": "parse_order"}
        def parse_fix(self, name, response): return self._parse(self.fix_api, name, response)
    """

    adapter: ClassVar[BaseAdapter[Any]]  # maps the venue's values to pfund's, e.g. adapter = BybitAdapter()
    rest_api: ClassVar[dict[EndpointName, str]] = {}  # REST API function name -> parsing method name
    ws_api: ClassVar[dict[Channel, str]] = {}  # Channel -> parsing method name

    parse_schema = staticmethod(parse_schema)  # helper for parsing methods to convert a response by a DSL schema, see parsers/dsl.py

    def _parse[K: str](self, table: dict[K, str], name: K, response: Any) -> Any:
        """Parses the response with the parsing method mapped to `name` in `table`.

        Returns:
            The standardized data, or None if no parsing method is mapped to `name`.
        """
        if name not in table:
            return None
        return getattr(self, table[name])(response)

    def parse_response(self, name: EndpointName, response: RawResponse) -> ParsedResponse | None:
        """Parses the response of the REST API function `name`."""
        return self._parse(self.rest_api, name, response)

    def parse_response_success(self, name: EndpointName, response: RawResponse) -> bool:
        """Venue-level success check of the REST API function `name` on top of the HTTP status, e.g. Bybit's retCode == 0."""
        raise NotImplementedError(f"{type(self).__name__} does not implement parse_response_success()")

    def parse_response_error(self, name: EndpointName, response: RawResponse) -> str | None:
        """Venue's error message in the failed response of the REST API function `name`, e.g. Bybit's retMsg."""
        raise NotImplementedError(f"{type(self).__name__} does not implement parse_response_error()")

    # TODO: remove parse_message() and ws_api, the WS API calls the standard parsing methods per Channel directly,
    # e.g. Channel.candlestick -> parse_candlestick(), each declared here with its return type like parse_markets()
    def parse_message(self, channel: Channel, message: DecodedMessage) -> Any:
        """Parses the streaming message of the channel, e.g. Channel.candlestick."""
        return self._parse(self.ws_api, channel, message)

    def parse_message_error(self, channel: FullChannel | None, message: DecodedMessage) -> str | None:
        """Venue's error in the streaming message, e.g. a rejected subscription, None if not an error.

        NOTE: required so that a parser handles errors on purpose, e.g. only the channels it cares about,
        and returns None for the rest.

        Args:
            channel: the subscribed channel the message belongs to, None if unknown, e.g. an error.
        """
        raise NotImplementedError(f"{type(self).__name__} does not implement parse_message_error()")

    def parse_markets(self, response: RawResponse) -> list[MarketDict]:
        raise NotImplementedError(f"{type(self).__name__} does not implement parse_markets()")
