from __future__ import annotations

import os
import sys
import types
from pathlib import Path

import pytest


_REPO_ROOT = Path(__file__).resolve().parents[2]
_CLAUDE_MOCK = _REPO_ROOT / "tests" / "fixtures" / "claude-mock" / "claude"


def _inject_local(monkeypatch, **values: str) -> None:
    fake = types.ModuleType("lib.common.config_local")
    for k, v in values.items():
        setattr(fake, k, v)
    monkeypatch.setitem(sys.modules, "lib.common.config_local", fake)


@pytest.fixture
def weekly_main():
    import importlib

    if "weekly_lint" in sys.modules:
        del sys.modules["weekly_lint"]
    module = importlib.import_module("weekly_lint")
    return module.main


def test_weekly_success(
    tmp_vault: Path, tmp_path: Path, monkeypatch, weekly_main
) -> None:
    os.chmod(_CLAUDE_MOCK, 0o755)
    monkeypatch.setenv("CLAUDE_MOCK_MODE", "noop")
    _inject_local(
        monkeypatch,
        VAULT_DIR=str(tmp_vault),
        WORKBENCH_DIR=str(tmp_path / "wb"),
        VENV_DIR=str(tmp_path / "venv"),
        BACKEND="claude",
        AGENT_BIN=str(_CLAUDE_MOCK),
    )

    rc = weekly_main([])

    assert rc == 0
    from lib.common import current_iso_date
    report = tmp_vault / "05_Archive" / "lint-reports" / f"{current_iso_date()}-weekly.md"
    assert report.exists()
    assert not (tmp_path / "wb").exists()


def test_weekly_skipped(
    tmp_vault: Path, tmp_path: Path, monkeypatch, weekly_main
) -> None:
    os.chmod(_CLAUDE_MOCK, 0o755)
    _inject_local(
        monkeypatch,
        VAULT_DIR=str(tmp_vault),
        WORKBENCH_DIR=str(tmp_path / "wb"),
        VENV_DIR=str(tmp_path / "venv"),
        BACKEND="claude",
        AGENT_BIN=str(_CLAUDE_MOCK),
    )
    (tmp_vault / "02_Ideas" / "fresh.md").write_text("recent", encoding="utf-8")

    rc = weekly_main(["--check-recent"])
    assert rc == 0
    assert not (tmp_path / "wb").exists()
