from __future__ import annotations

from pfund_blocks.entities.accounts.account_base import BaseAccount
from pfund_blocks.enums.env import Environment


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
        env: Environment | str,
        venue: str,
        name: str = "",
        token: str = "",
    ):
        super().__init__(env=env, venue=venue, name=name)
        self._token: str = token or (self._dotenv.get(f"{self.venue}_ACCESS_TOKEN", "") or "")

    def _assert_no_credential_leak_in_simulated_env(self):
        if self._token:
            raise ValueError(
                f"{self.venue} ACCESS TOKEN should NOT be provided for {self._env} environment, \n"
                + f"please remove it in .env.{self._env.lower()} file (if any),\n"
                + "or remove token= from strategy.add_account()"
            )

    def _assert_credentials_provided_in_paper_or_live_trading_env(self):
        if not self._token:
            raise ValueError(
                f"{self.venue} ACCESS TOKEN must be provided, \n"
                + f"please set `{self.venue}_ACCESS_TOKEN` in .env.{self._env.lower()} file,\n"
                + "or by strategy.add_account(..., token=...)"
            )

    @property
    def token(self):
        return self._token
