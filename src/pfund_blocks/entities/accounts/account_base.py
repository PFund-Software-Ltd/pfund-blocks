from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

if TYPE_CHECKING:
    from pfund_blocks.utils import DotenvStore

from abc import ABC, ABCMeta, abstractmethod

from pfund_blocks.enums.env import Environment


class _AccountMeta(ABCMeta):
    def __call__[AccountT: BaseAccount](
        cls: type[AccountT], *args: Any, **kwargs: Any
    ) -> AccountT:
        # run the checks after the whole __init__ chain, when subclasses have set their credentials
        account = super().__call__(*args, **kwargs)
        if account.env in (Environment.BACKTEST, Environment.SANDBOX):
            account._assert_no_credential_leak_in_backtest_or_sandbox_env()
        else:
            account._assert_credentials_provided_in_paper_or_live_trading_env()
        # only needed while constructing, don't carry the whole .env file around (e.g. when pickled to Ray workers)
        del account._dotenv
        return account


class BaseAccount(ABC, metaclass=_AccountMeta):
    _num: ClassVar[int] = 0

    @classmethod
    def _next_id(cls) -> str:
        cls._num += 1
        return str(cls._num)

    def _get_default_name(self) -> str:
        return f"{self.__class__.__name__}-{self._next_id()}"

    def __init__(self, env: Environment | str, venue: str, name: str = ""):
        """
        Args:
            env: The environment the account is in.
            venue: The trading venue of the account.
            name: The name of the account.
        """
        from pfund_blocks.utils import DotenvStore

        self._env = Environment(env.upper())
        self._venue: str = venue.upper()
        self._name: str = name or self._get_default_name()
        self._dotenv: DotenvStore | dict[str, str] = (
            DotenvStore(env=self._env) if self._env != Environment.BACKTEST else {}
        )

    @abstractmethod
    def _assert_no_credential_leak_in_backtest_or_sandbox_env(self) -> None: ...

    @abstractmethod
    def _assert_credentials_provided_in_paper_or_live_trading_env(self) -> None: ...

    @property
    def env(self) -> Environment:
        return self._env

    @property
    def venue(self) -> str:
        return self._venue

    @property
    def name(self) -> str:
        return self._name

    def __str__(self) -> str:
        return f"Env={self._env} | Venue={self._venue} | Account={self._name}"

    def __repr__(self) -> str:
        return ":".join([self._env, self._venue, self._name])

    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, BaseAccount):
            return NotImplemented
        return (
            self._env == other._env
            and self._venue == other._venue
            and self._name == other._name
        )

    def __hash__(self) -> int:
        return hash((self._env, self._venue, self._name))
