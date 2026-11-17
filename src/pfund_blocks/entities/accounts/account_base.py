from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

if TYPE_CHECKING:
    from pfund_blocks.utils import DotenvStore

from abc import ABC, abstractmethod

from pfund_blocks.enums.env import Environment


class BaseAccount(ABC):
    _num: ClassVar[int] = 0

    @classmethod
    def _next_id(cls) -> str:
        cls._num += 1
        return str(cls._num)

    def _get_default_name(self) -> str:
        return f"{self.__class__.__name__}-{self._next_id()}"

    def __init__(
        self,
        venue: str,
        name: str = "",
        env: Environment | str | None = None,
    ):
        """
        Args:
            venue: The trading venue of the account.
            name: The name of the account.
            env: The environment the account is in, only env=PAPER or env=LIVE.
                If None, it is set internally by the engine when the account is added.
        """
        self._env: Environment | None = None
        self._venue: str = venue.upper()
        self._name: str = name or self._get_default_name()
        # NOTE: _set_env() loads and checks the credentials, so subclasses must set theirs BEFORE calling super().__init__()
        if env is not None:
            self._set_env(env)

    def _set_env(self, env: Environment | str):
        from pfund_blocks.utils import DotenvStore

        if self._env is not None:
            raise ValueError(f"{self!r} already has env={self._env}, cannot set {env=}")
        _env = Environment(env.upper())
        # NOTE: a real account only exists in env=PAPER/LIVE, env=BACKTEST/SANDBOX use pfund's SimulatedAccount instead
        if _env.is_simulated():
            raise ValueError(
                f"{self.__class__.__name__} only supports env=PAPER or env=LIVE, got {env=}, "
                + "use pf.SimulatedAccount for env=BACKTEST or env=SANDBOX"
            )
        self._env = _env
        # NOTE: the dotenv store is local, so the whole .env file isn't carried around (e.g. when pickled to Ray workers)
        self._load_credentials(DotenvStore(env=self._env))
        self._assert_credentials_provided()

    @abstractmethod
    def _load_credentials(self, dotenv: DotenvStore) -> None:
        """Fills in the credentials not passed in explicitly from the env's .env file."""
        ...

    @abstractmethod
    def _assert_credentials_provided(self) -> None: ...

    @property
    def env(self) -> Environment:
        assert self._env is not None, "env is not set"
        return self._env

    @property
    def venue(self) -> str:
        return self._venue

    @property
    def name(self) -> str:
        return self._name

    def __str__(self) -> str:
        return f"Env={self.env} | Venue={self._venue} | Account={self._name}"

    def __repr__(self) -> str:
        return ":".join([self.env, self._venue, self._name])

    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, BaseAccount):
            return NotImplemented
        return (
            self.env == other.env
            and self._venue == other._venue
            and self._name == other._name
        )

    def __hash__(self) -> int:
        return hash((self.env, self._venue, self._name))
