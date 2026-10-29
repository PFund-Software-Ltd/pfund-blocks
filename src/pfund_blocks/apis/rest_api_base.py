from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar, Literal, Protocol, TypedDict, cast

if TYPE_CHECKING:
    from httpx2 import Response

    from pfund_blocks.entities.accounts.account_base import BaseAccount
    from pfund_blocks.parsers.parser_base import BaseParser

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from http import HTTPMethod
from json import JSONDecodeError

from httpx2 import AsyncClient, HTTPStatusError, RequestError

from pfund_blocks.enums.env import Environment


@dataclass(frozen=True, slots=True)
class RestRequest:
    """A REST API request built by an endpoint method, signed by the venue's signer if private.

    It holds everything needed to send the request, so that a signer can sign any part of it,
    e.g. Bybit signs headers over the serialized body, Hyperliquid adds a signature into the body.
    """

    name: str  # endpoint name, e.g. "get_markets"
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


class RestSigner[AccountT: BaseAccount](Protocol):
    def sign(self, request: RestRequest, account: AccountT) -> RestRequest:
        """Returns a new signed request (e.g. via dataclasses.replace), the input request is left unchanged.

        e.g. Bybit adds the X-BAPI-* headers and sets content to the signed body,
        Hyperliquid adds the nonce and signature into the body.
        """
        ...


class RestRequestData(TypedDict):
    """The request in a RestResult, as plain data (e.g. for logging, pickling and serialization).

    Built from the unsigned RestRequest, with the full url instead of the path for debugging.
    """

    name: str
    method: HTTPMethod
    url: str
    params: dict[str, Any] | None


class RestResult(TypedDict):
    """The outcome of sending a request, with both the raw and the parsed response."""

    success: bool
    error: str
    venue: str
    account: str | None  # account name, None for public requests
    request: RestRequestData
    status_code: int | None  # None if no response is received
    response: Any  # None if no response is received
    data: Any  # parsed response, None if not parsed


class BaseRestAPI(ABC):
    venue: ClassVar[str]  # upper case, consistent with BaseAccount.venue, e.g. "BYBIT"
    URLS: ClassVar[dict[Literal[Environment.PAPER, Environment.LIVE], str]]
    VERSION: ClassVar[str | None] = None  # e.g. "v5" for Bybit, None if the venue's API is not versioned
    signer: ClassVar[RestSigner[Any] | None] = None  # None if the venue has no private endpoints
    parser: ClassVar[BaseParser | None] = None  # None if responses are not parsed, i.e. data is always None

    def __init__(self, env: Literal[Environment.PAPER, Environment.LIVE, "PAPER", "LIVE"]):
        """
        Args:
            env: PAPER (e.g. testnet) or LIVE.
        """
        self._env = self._validate_env(env)
        self._logger = logging.getLogger(f"pfund.{self.venue.lower()}")
        self._url: str = self.URLS[self._env]
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

    @abstractmethod
    def _is_success(self, request: RestRequest, response: Any) -> bool:
        """Venue-level success check on top of the HTTP status, e.g. Bybit's retCode == 0."""
        ...

    @abstractmethod
    def _extract_error(self, request: RestRequest, response: Any) -> str:
        """Venue's error message in the response, e.g. Bybit's retMsg."""
        ...

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

    async def send(self, request: RestRequest, account: BaseAccount | None = None) -> RestResult:
        """Signs the request if private, sends it and returns a RestResult.

        If successful, the response is parsed into result["data"] by the venue's parser.
        """
        if request.private:
            if self.signer is None:
                raise ValueError(f"{self.venue} REST API has no signer for private requests")
            account = self._check_account(account)
            signed_request = self.signer.sign(request, account)
        else:
            signed_request = request

        url = self._url + request.path
        result: RestResult = {
            "success": False,
            "error": "",
            "venue": self.venue,
            "account": account.name if account else None,
            "request": {
                "name": request.name,
                "method": request.method,
                "url": url,
                "params": request.params,
            },
            "status_code": None,
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
            response = http_response.json()
            result["status_code"] = http_response.status_code
            result["response"] = response
            is_http_success = http_response.is_success
            result["success"] = is_http_success and self._is_success(request, response)
            if result["success"]:
                if self.parser is not None:
                    result["data"] = self.parser.parse_rest(request.name, response)
            else:
                error = self._extract_error(request, response)
                if not is_http_success:
                    http_error = f"HTTP {http_response.status_code} {http_response.reason_phrase}"
                    error = f"{error} ({http_error})" if error else http_error
                result["error"] = error
        except (JSONDecodeError, RequestError, HTTPStatusError) as exc:
            result["success"] = False
            result["error"] = repr(exc)
            self._logger.exception(f'REST API "{request.name}" error:')
        except Exception as exc:
            result["success"] = False
            result["error"] = repr(exc)
            self._logger.exception(f'Unhandled REST API "{request.name}" error:')
        finally:
            self._logger.debug(
                f'REST API "{request.name}" response: {result["response"]}'
            )
        return result

    def __getstate__(self) -> dict[str, Any]:
        # NOTE: drop the unpicklable client so the object survives Ray/cloudpickle;
        # __setstate__ rebuilds a fresh one in the destination process.
        state = self.__dict__.copy()
        del state["_client"]
        return state

    def __setstate__(self, state: dict[str, Any]):
        self.__dict__.update(state)
        self._client = AsyncClient()
