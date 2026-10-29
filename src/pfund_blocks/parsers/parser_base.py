from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

if TYPE_CHECKING:
    from pfund_blocks.adapters.adapter_base import BaseAdapter

from pfund_blocks.parsers.schema import parse_schema


class BaseParser:
    """Parses a venue's responses into standardized data, shared by its REST and WS APIs.

    Subclasses map each API function to the name of its parsing method, e.g.
        rest_api = {"get_markets": "parse_markets"}
    so that maintainers can see which function uses which parsing method.
    A parsing method takes the venue's response and returns the standardized data.

    For APIs other than REST and WS (e.g. FIX), define your own table and parse with
    self._parse(table, name, response), e.g.
        fix_api = {"new_order": "parse_order"}
        def parse_fix(self, name, response): return self._parse(self.fix_api, name, response)
    """

    adapter: ClassVar[BaseAdapter[Any]]  # maps the venue's values to pfund's, e.g. adapter = BybitAdapter()
    rest_api: ClassVar[dict[str, str]] = {}  # REST API function name -> parsing method name
    ws_api: ClassVar[dict[str, str]] = {}  # WS API function name -> parsing method name

    parse_schema = staticmethod(parse_schema)  # converts a response into standardized data by a schema

    def _parse(self, table: dict[str, str], name: str, response: Any) -> Any:
        """Parses the response with the parsing method mapped to `name` in `table`.

        Returns:
            The standardized data, or None if no parsing method is mapped to `name`.
        """
        if name not in table:
            return None
        return getattr(self, table[name])(response)

    def parse_rest(self, name: str, response: Any) -> Any:
        """Parses the response of the REST API function `name`."""
        return self._parse(self.rest_api, name, response)

    def parse_ws(self, name: str, response: Any) -> Any:
        """Parses the response of the WS API function `name`."""
        return self._parse(self.ws_api, name, response)
