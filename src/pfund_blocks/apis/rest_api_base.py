from __future__ import annotations

from typing import (
    TYPE_CHECKING,
    Any,
    ClassVar,
    Literal,
)

if TYPE_CHECKING:
    from httpx2 import Response

    from pfund_blocks.entities.accounts.account_base import BaseAccount
    from pfund_blocks.parsers.parser_base import BaseParser
    from pfund_blocks.signer import RequestSigner
    from pfund_blocks.typing import EndpointName

import logging
import time
from json import JSONDecodeError

from httpx2 import AsyncClient, HTTPStatusError, RequestError

from pfund_blocks.enums.env import Environment
from pfund_blocks.typing import Endpoint, Reply, Request


class BaseRestAPI:
    venue: ClassVar[str]  # upper case, consistent with BaseAccount.venue, e.g. "BYBIT"
    urls: ClassVar[dict[Literal[Environment.PAPER, Environment.LIVE], str]]
    version: ClassVar[str | None] = None  # e.g. "v5" for Bybit, None if the venue's API is not versioned
    signer: ClassVar[RequestSigner[Any] | None] = None  # None if the venue has no private endpoints
    parser: ClassVar[BaseParser | None] = None  # None if responses are not parsed, i.e. data is always None
    # NOTE: endpoint names should match the function names, e.g. "get_markets" for get_markets()
    public_endpoints: ClassVar[dict[EndpointName, Endpoint]] = {}
    private_endpoints: ClassVar[dict[EndpointName, Endpoint]] = {}

    def __init_subclass__(cls, **kwargs: Any):
        super().__init_subclass__(**kwargs)
        if duplicates := cls.public_endpoints.keys() & cls.private_endpoints.keys():
            raise ValueError(f"{cls.__name__} has endpoints in both public_endpoints and private_endpoints: {sorted(duplicates)}")

    def __init__(self, env: Literal[Environment.PAPER, Environment.LIVE, "PAPER", "LIVE"]):
        """
        Args:
            env: PAPER (e.g. testnet) or LIVE.
        """
        self._env = self._validate_env(env)
        self._logger = logging.getLogger(f"pfund.{self.venue.lower()}")
        self._url: str = self.urls[self._env]
        self._client = AsyncClient()

    @staticmethod
    def _validate_env(env: Environment | str) -> Literal[Environment.PAPER, Environment.LIVE]:
        env = Environment(env.upper())
        if env not in (Environment.PAPER, Environment.LIVE):
            raise ValueError(f"environment {env} is not supported, only PAPER or LIVE")
        return env

    @property
    def env(self) -> Literal[Environment.PAPER, Environment.LIVE]:
        return self._env

    def get_endpoint(self, name: EndpointName) -> Endpoint:
        if name in self.public_endpoints:
            return self.public_endpoints[name]
        if name in self.private_endpoints:
            return self.private_endpoints[name]
        raise ValueError(
            f'"{name}" is not a registered endpoint, it must match a key in public_endpoints or private_endpoints'
        )

    def _create_request(
        self, name: EndpointName, *, params: dict[str, Any] | None = None, body: dict[str, Any] | None = None
    ) -> Request:
        """Creates the request of the registered endpoint `name`, private if it is in private_endpoints."""
        endpoint = self.get_endpoint(name)
        return Request(
            name=name,
            method=endpoint.method,
            path=endpoint.path,
            params=params,
            body=body,
            private=name in self.private_endpoints,
        )

    def _check_account(self, account: BaseAccount | None) -> BaseAccount:
        """Checks the account for a private request, which must be signed by an account
        in the same environment and venue as this REST API.

        Returns:
            The account, narrowed to non-None for type checkers.
        """
        if account is None:
            raise ValueError("an account is required for private requests")
        if account.env != self._env:
            raise ValueError(
                f"Account environment {account.env} does not match RestAPI environment {self._env}"
            )
        if account.venue != self.venue:
            raise ValueError(
                f"Account venue {account.venue} does not match RestAPI venue {self.venue}"
            )
        return account

    async def send(self, request: Request, account: BaseAccount | None = None) -> Reply:
        """Signs the request if private, sends it and returns a Reply.

        The venue's parser checks the venue-level success and error (e.g. Bybit's retCode and retMsg),
        and if successful, parses the response into reply["data"].
        """
        if request.private:
            if self.signer is None:
                raise ValueError(f"{self.venue} REST API has no signer for private requests")
            account = self._check_account(account)
            signed_request = self.signer.sign(request, account)
        else:
            signed_request = request

        url = self._url + request.path
        reply: Reply = {
            "success": False,
            "error": None,
            "source": self.venue,
            "account": account.name if account else None,
            "request": {
                "name": request.name,
                "method": request.method,
                "url": url,
                "params": request.params,
            },
            "status_code": None,
            "received_at": None,
            "response": None,
            "data": None,
        }
        try:
            http_response: Response = await self._client.request(
                method=signed_request.method,
                url=url,
                params=signed_request.params,
                # content is the signed bytes, otherwise let httpx2 serialize the body
                content=signed_request.content,
                json=signed_request.body if signed_request.content is None else None,
                headers=signed_request.headers,
            )
            reply["received_at"] = time.time()
            response = http_response.json()
            reply["status_code"] = http_response.status_code
            reply["response"] = response
            is_http_success = http_response.is_success
            # NOTE: without a parser, the response is not interpreted, i.e. success is the HTTP status only
            reply["success"] = is_http_success and (
                self.parser is None or self.parser.parse_response_success(request.name, response)
            )
            if reply["success"]:
                if self.parser is not None:
                    reply["data"] = self.parser.parse_response(request.name, response)
            else:
                error = self.parser.parse_response_error(request.name, response) if self.parser else None
                if not is_http_success:
                    http_error = f"HTTP {http_response.status_code} {http_response.reason_phrase}"
                    error = f"{error} ({http_error})" if error else http_error
                reply["error"] = error or None
        except (JSONDecodeError, RequestError, HTTPStatusError) as exc:
            reply["success"] = False
            reply["error"] = repr(exc)
            self._logger.exception(f'REST API "{request.name}" error:')
        except Exception as exc:
            reply["success"] = False
            reply["error"] = repr(exc)
            self._logger.exception(f'Unhandled REST API "{request.name}" error:')
        finally:
            self._logger.debug(
                f'REST API "{request.name}" response: {reply["response"]}'
            )
        return reply

    def __getstate__(self) -> dict[str, Any]:
        # NOTE: drop the unpicklable client so the object survives Ray/cloudpickle;
        # __setstate__ rebuilds a fresh one in the destination process.
        state = self.__dict__.copy()
        del state["_client"]
        return state

    def __setstate__(self, state: dict[str, Any]):
        self.__dict__.update(state)
        self._client = AsyncClient()
