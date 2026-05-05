from __future__ import annotations

import sys
import types
from pathlib import Path

from lib.common import Config, load


def test_config_is_frozen() -> None:
    cfg = Config(
        vault_dir=Path("/v"),
        workbench_dir=Path("/w"),
        venv_dir=Path("/e"),
        backend="claude",
        agent_bin="/usr/local/bin/claude",
    )
    try:
        cfg.backend = "opencode"  # type: ignore[misc]
    except Exception:
        return
    raise AssertionError("Config should be frozen / immutable")


def test_load_reads_local_module(monkeypatch) -> None:
    fake_local = types.ModuleType("lib.common.config_local")
    fake_local.VAULT_DIR = "/tmp/v"
    fake_local.WORKBENCH_DIR = "/tmp/w"
    fake_local.VENV_DIR = "/tmp/e"
    fake_local.BACKEND = "opencode"
    fake_local.AGENT_BIN = "/usr/local/bin/opencode"
    monkeypatch.setitem(sys.modules, "lib.common.config_local", fake_local)

    cfg = load(check_recent=True)
    assert cfg.vault_dir == Path("/tmp/v")
    assert cfg.workbench_dir == Path("/tmp/w")
    assert cfg.venv_dir == Path("/tmp/e")
    assert cfg.backend == "opencode"
    assert cfg.agent_bin == "/usr/local/bin/opencode"
    assert cfg.check_recent is True


def test_load_default_check_recent_false(monkeypatch) -> None:
    fake_local = types.ModuleType("lib.common.config_local")
    fake_local.VAULT_DIR = "/v"
    fake_local.WORKBENCH_DIR = "/w"
    fake_local.VENV_DIR = "/e"
    fake_local.BACKEND = "claude"
    fake_local.AGENT_BIN = "/usr/local/bin/claude"
    monkeypatch.setitem(sys.modules, "lib.common.config_local", fake_local)

    assert load().check_recent is False
