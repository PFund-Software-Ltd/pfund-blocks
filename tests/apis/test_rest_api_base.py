from __future__ import annotations

from typing import ClassVar

from http import HTTPMethod

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


class TestInitSubclass:
    def test_endpoint_in_both_tables_raises(self):
        with pytest.raises(ValueError, match=r"both public_endpoints and private_endpoints: \['get_markets'\]"):

            class _BadRestAPI(DummyRestAPI):
                private_endpoints = {"get_markets": Endpoint(HTTPMethod.GET, "/markets")}  # noqa: RUF012
