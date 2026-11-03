from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

if TYPE_CHECKING:
    from pfund_blocks.typing import Reply

import asyncio
from http import HTTPMethod

import httpx2
import pytest

from pfund_blocks.apis.rest_api_base import BaseRestAPI
from pfund_blocks.enums.env import Environment
from pfund_blocks.typing import Endpoint, Request


class DummyRestAPI(BaseRestAPI):
    venue: ClassVar[str] = "DUMMY"
    urls = {Environment.PAPER: "https://paper.dummy", Environment.LIVE: "https://live.dummy"}  # noqa: RUF012
    public_endpoints = {"get_markets": Endpoint(HTTPMethod.GET, "/markets")}  # noqa: RUF012
    private_endpoints = {"place_order": Endpoint(HTTPMethod.POST, "/order")}  # noqa: RUF012


@pytest.fixture
def api() -> DummyRestAPI:
    return DummyRestAPI("LIVE")


class TestGetEndpoint:
    def test_public(self, api: DummyRestAPI):
        assert api.get_endpoint("get_markets") == Endpoint(HTTPMethod.GET, "/markets")

    def test_private(self, api: DummyRestAPI):
        assert api.get_endpoint("place_order") == Endpoint(HTTPMethod.POST, "/order")

    def test_unregistered_raises(self, api: DummyRestAPI):
        with pytest.raises(ValueError, match='"get_trades" is not a registered endpoint'):
            api.get_endpoint("get_trades")


class TestCreateRequest:
    def test_public(self, api: DummyRestAPI):
        assert api._create_request("get_markets", params={"category": "spot"}) == Request(
            name="get_markets", method=HTTPMethod.GET, path="/markets", params={"category": "spot"}, private=False
        )

    def test_private(self, api: DummyRestAPI):
        assert api._create_request("place_order", body={"qty": "1"}) == Request(
            name="place_order", method=HTTPMethod.POST, path="/order", body={"qty": "1"}, private=True
        )

    def test_unregistered_raises(self, api: DummyRestAPI):
        with pytest.raises(ValueError, match="is not a registered endpoint"):
            api._create_request("get_trades")


class TestSend:
    @staticmethod
    def _send(api: DummyRestAPI, response: httpx2.Response) -> Reply:
        api._client = httpx2.AsyncClient(transport=httpx2.MockTransport(lambda request: response))
        return asyncio.run(api.send(api._create_request("get_markets")))

    def test_json_response(self, api: DummyRestAPI):
        reply = self._send(api, httpx2.Response(200, json={"ok": True}))
        assert reply["success"] is True
        assert reply["status_code"] == 200
        assert reply["response"] == {"ok": True}
        assert reply["error"] is None

    def test_non_json_error_keeps_status_and_body(self, api: DummyRestAPI):
        reply = self._send(api, httpx2.Response(502, text="<html>Bad Gateway</html>"))
        assert reply["success"] is False
        assert reply["status_code"] == 502
        assert reply["response"] == "<html>Bad Gateway</html>"
        assert reply["error"] == "non-JSON response (HTTP 502 Bad Gateway)"

    def test_non_json_success_is_not_success(self, api: DummyRestAPI):
        reply = self._send(api, httpx2.Response(200, text="OK"))
        assert reply["success"] is False
        assert reply["status_code"] == 200
        assert reply["error"] == "non-JSON response (HTTP 200 OK)"

    def test_http_error_with_json_body(self, api: DummyRestAPI):
        reply = self._send(api, httpx2.Response(500, json={"msg": "boom"}))
        assert reply["success"] is False
        assert reply["status_code"] == 500
        assert reply["error"] == "HTTP 500 Internal Server Error"


class TestInitSubclass:
    def test_endpoint_in_both_tables_raises(self):
        with pytest.raises(ValueError, match=r"both public_endpoints and private_endpoints: \['get_markets'\]"):

            class _BadRestAPI(DummyRestAPI):
                private_endpoints = {"get_markets": Endpoint(HTTPMethod.GET, "/markets")}  # noqa: RUF012
