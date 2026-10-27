from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

    from pfund_blocks.enums.env import Environment

from decimal import Decimal


def trim_trailing_zeros(value: Decimal) -> Decimal:
    """Trims unnecessary trailing zeros from a Decimal without changing its value.

    e.g. 0.010 -> 0.01, 25000.00 -> 25000

    For whole numbers, `to_integral()` is used instead of `normalize()` to avoid
    the exponent form normalize() produces for integers (e.g. 25000 -> 2.5E+4).
    """
    integral = value.to_integral()
    return integral if value == integral else value.normalize()


class DotenvStore:
    """Read-only view over a single environment's `.env.{env}` file.

    Vars are loaded once at construction and kept in a private dict; they never
    enter `os.environ`, so two engines with different envs in the same process
    can't collide — no prefix is needed.
    """

    def __init__(self, env: Environment | str, env_dir: str | Path | None = None):
        """
        Args:
            env: The environment whose `.env.{env}` file is loaded.
            env_dir: The directory to load `.env.{env}` from, without searching anywhere else.
                If None, the file is searched for from the current working directory upwards.
                A missing file loads nothing.
        """
        from pfund_blocks.enums.env import Environment

        self._env = Environment(env.upper())
        self._vars: dict[str, str] = self._load(self._env, env_dir)

    @staticmethod
    def _load(env: Environment, env_dir: str | Path | None) -> dict[str, str]:
        from pathlib import Path

        from dotenv import dotenv_values, find_dotenv

        # load env vars manually to avoid loading into os.environ
        # NOTE: this allows multiple engines with different envs in the same process
        filename = f".env.{env.lower()}"
        if env_dir is None:
            env_file_path = find_dotenv(
                filename=filename, usecwd=True, raise_error_if_not_found=False
            )
        else:
            env_file_path = Path(env_dir).expanduser() / filename
        # interpolate=False keeps `${VAR}` literal, otherwise it would be expanded from os.environ
        values = dotenv_values(env_file_path, interpolate=False)
        # dotenv maps a bare `KEY` line (no `=`) to None; treat it as unset
        return {k: v for k, v in values.items() if v is not None}

    def get(self, key: str, default: str | None = None) -> str | None:
        return self._vars.get(key, default)
