from __future__ import annotations

from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from pfund_blocks.enums.env import Environment
    from pfund_blocks.utils import DotenvStore

from pfund_blocks.entities.accounts.account_base import BaseAccount


# TODO: for FUTURE integration with the US brokers — Tradier, TradeStation, Schwab, Tradovate.
class OAuthAccount(BaseAccount):
    """Account for venues that authenticate with an OAuth2 bearer token.

    Unlike HMAC venues, brokers such as Tradier don't sign each request: they send
    ``Authorization: Bearer <access_token>``. The hard part is the OAuth2 token lifecycle
    (obtaining/refreshing the access token) which is stateful and lives outside the signer;
    this account only carries the already-acquired token.
    """

    def __init__(
        self,
        venue: str,
        name: str = "",
        token: str = "",
        env: Literal[Environment.PAPER, Environment.LIVE] | None = None,
    ):
        # NOTE: set before super().__init__(), which may call _set_env() and needs it
        self._token: str = token
        super().__init__(venue=venue, name=name, env=env)

    def _load_credentials(self, dotenv: DotenvStore):
        self._token = self._token or (
            dotenv.get(f"{self.venue}_ACCESS_TOKEN", "") or ""
        )

    def _assert_credentials_provided(self):
        if not self._token:
            raise ValueError(
                f"{self.venue} ACCESS TOKEN must be provided, \n"
                + f"please set `{self.venue}_ACCESS_TOKEN` in .env.{self.env.lower()} file,\n"
                + "or by strategy.add_account(..., token=...)"
            )

    @property
    def token(self):
        return self._token
