from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

import os

import pytest

from pfund_blocks.enums.env import Environment
from pfund_blocks.utils import DotenvStore


@pytest.fixture
def cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Runs the test from an empty temp dir, so no real .env.{env} file is picked up."""
    monkeypatch.chdir(tmp_path)
    return tmp_path


class TestLoading:
    def test_loads_env_file(self, cwd: Path):
        (cwd / ".env.paper").write_text("BYBIT_API_KEY=key\nBYBIT_API_SECRET=secret\n")
        store = DotenvStore(env=Environment.PAPER)
        assert store.get("BYBIT_API_KEY") == "key"
        assert store.get("BYBIT_API_SECRET") == "secret"

    @pytest.mark.parametrize("env", ["live", "LIVE", "Live", Environment.LIVE])
    def test_env_is_case_insensitive(self, cwd: Path, env: Environment | str):
        (cwd / ".env.live").write_text("KEY=live\n")
        assert DotenvStore(env=env).get("KEY") == "live"

    def test_only_loads_its_own_env_file(self, cwd: Path):
        (cwd / ".env.paper").write_text("KEY=paper\n")
        (cwd / ".env.live").write_text("KEY=live\n")
        assert DotenvStore(env="paper").get("KEY") == "paper"
        assert DotenvStore(env="live").get("KEY") == "live"

    def test_finds_env_file_in_parent_dir(
        self, cwd: Path, monkeypatch: pytest.MonkeyPatch
    ):
        (cwd / ".env.sandbox").write_text("KEY=parent\n")
        subdir = cwd / "a" / "b"
        subdir.mkdir(parents=True)
        monkeypatch.chdir(subdir)
        assert DotenvStore(env="sandbox").get("KEY") == "parent"

    def test_missing_env_file_loads_nothing(self, cwd: Path):
        store = DotenvStore(env="paper")
        assert store.get("KEY") is None

    def test_vars_are_loaded_once(self, cwd: Path):
        env_file = cwd / ".env.paper"
        env_file.write_text("KEY=before\n")
        store = DotenvStore(env="paper")
        env_file.write_text("KEY=after\n")
        assert store.get("KEY") == "before"

    def test_invalid_env(self, cwd: Path):
        with pytest.raises(ValueError, match="'FOO' is not a valid Environment"):
            DotenvStore(env="foo")


class TestIsolation:
    def test_does_not_touch_os_environ(
        self, cwd: Path, monkeypatch: pytest.MonkeyPatch
    ):
        monkeypatch.delenv("PFUND_BLOCKS_TEST_KEY", raising=False)
        (cwd / ".env.paper").write_text("PFUND_BLOCKS_TEST_KEY=value\n")
        DotenvStore(env="paper")
        assert "PFUND_BLOCKS_TEST_KEY" not in os.environ

    def test_ignores_os_environ(self, cwd: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("PFUND_BLOCKS_TEST_KEY", "from-os")
        assert DotenvStore(env="paper").get("PFUND_BLOCKS_TEST_KEY") is None

    def test_does_not_interpolate_from_os_environ(
        self, cwd: Path, monkeypatch: pytest.MonkeyPatch
    ):
        monkeypatch.setenv("PFUND_BLOCKS_TEST_KEY", "from-os")
        (cwd / ".env.paper").write_text("KEY=${PFUND_BLOCKS_TEST_KEY}\n")
        assert DotenvStore(env="paper").get("KEY") == "${PFUND_BLOCKS_TEST_KEY}"


class TestGet:
    def test_missing_key_returns_default(self, cwd: Path):
        (cwd / ".env.paper").write_text("KEY=value\n")
        store = DotenvStore(env="paper")
        assert store.get("MISSING") is None
        assert store.get("MISSING", "default") == "default"

    def test_empty_value(self, cwd: Path):
        (cwd / ".env.paper").write_text("KEY=\n")
        assert DotenvStore(env="paper").get("KEY", "default") == ""

    def test_bare_key_is_unset(self, cwd: Path):
        (cwd / ".env.paper").write_text("KEY\n")
        assert DotenvStore(env="paper").get("KEY", "default") == "default"


class TestEnvDir:
    @pytest.mark.parametrize("as_str", [True, False])
    def test_loads_from_env_dir(self, cwd: Path, as_str: bool):
        env_dir = cwd / "config"
        env_dir.mkdir()
        (env_dir / ".env.paper").write_text("KEY=config\n")
        store = DotenvStore(env="paper", env_dir=str(env_dir) if as_str else env_dir)
        assert store.get("KEY") == "config"

    def test_picks_the_env_file_by_env(self, cwd: Path):
        (cwd / ".env.paper").write_text("KEY=paper\n")
        (cwd / ".env.live").write_text("KEY=live\n")
        assert DotenvStore(env="live", env_dir=cwd).get("KEY") == "live"

    def test_ignores_cwd(self, cwd: Path):
        (cwd / ".env.paper").write_text("KEY=cwd\n")
        env_dir = cwd / "config"
        env_dir.mkdir()
        (env_dir / ".env.paper").write_text("KEY=config\n")
        assert DotenvStore(env="paper", env_dir=env_dir).get("KEY") == "config"

    def test_does_not_search_parent_dirs(self, cwd: Path):
        (cwd / ".env.paper").write_text("KEY=parent\n")
        env_dir = cwd / "config"
        env_dir.mkdir()
        assert DotenvStore(env="paper", env_dir=env_dir).get("KEY") is None

    def test_missing_env_dir_loads_nothing(self, cwd: Path):
        assert DotenvStore(env="paper", env_dir=cwd / "missing").get("KEY") is None

    def test_expands_user(self, cwd: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("HOME", str(cwd))
        env_dir = cwd / "trading"
        env_dir.mkdir()
        (env_dir / ".env.paper").write_text("KEY=home\n")
        assert DotenvStore(env="paper", env_dir="~/trading").get("KEY") == "home"
