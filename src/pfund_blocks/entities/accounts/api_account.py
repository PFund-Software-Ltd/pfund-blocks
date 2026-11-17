from __future__ import annotations

from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from pfund_blocks.enums.env import Environment
    from pfund_blocks.utils import DotenvStore

from pfund_blocks.entities.accounts.account_base import BaseAccount


class APIKeyAccount(BaseAccount):
    def __init__(
        self,
        venue: str,
        name: str = "",
        key: str = "",
        secret: str = "",
        env: Literal[Environment.PAPER, Environment.LIVE] | None = None,
    ):
        # NOTE: set before super().__init__(), which may call _set_env() and needs them
        self._key: str = key
        self._secret: str = secret
        super().__init__(venue=venue, name=name, env=env)

    def _load_credentials(self, dotenv: DotenvStore):
        self._key = self._key or (dotenv.get(f"{self.venue}_API_KEY", "") or "")
        self._secret = self._secret or (
            dotenv.get(f"{self.venue}_API_SECRET", "") or ""
        )

    def _assert_credentials_provided(self):
        if not self._key or not self._secret:
            raise ValueError(
                f"{self.venue} API KEY and SECRET must be provided, \n"
                + f"please set `{self.venue}_API_KEY` and `{self.venue}_API_SECRET` in .env.{self.env.lower()} file,\n"
                + "or by strategy.add_account(..., key=..., secret=...)"
            )

    @property
    def key(self):
        return self._key

    @property
    def secret(self):
        return self._secret
