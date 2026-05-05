from __future__ import annotations

import os
import subprocess
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
def daily_main():
    """Reload the frame so each test starts from a clean module state."""
    import importlib

    if "daily_ingest" in sys.modules:
        del sys.modules["daily_ingest"]
    module = importlib.import_module("daily_ingest")
    return module.main


def test_daily_success(
    tmp_vault: Path, tmp_path: Path, monkeypatch, daily_main
) -> None:
    os.chmod(_CLAUDE_MOCK, 0o755)
    monkeypatch.setenv("CLAUDE_MOCK_MODE", "move-inbox-file")
    _inject_local(
        monkeypatch,
        VAULT_DIR=str(tmp_vault),
        WORKBENCH_DIR=str(tmp_path / "wb"),
        VENV_DIR=str(tmp_path / "venv"),
        BACKEND="claude",
        AGENT_BIN=str(_CLAUDE_MOCK),
    )
    (tmp_vault / "00_Inbox" / "test.md").write_text("hello", encoding="utf-8")

    rc = daily_main([])

    assert rc == 0
    # The file was moved by the agent inside the workbench, then merged back
    assert not (tmp_vault / "00_Inbox" / "test.md").exists()
    assert (tmp_vault / "05_Archive" / "test.md").exists()
    # Workbench cleaned up
    assert not (tmp_path / "wb").exists()
    # main moved forward
    log = subprocess.run(
        ["git", "-C", str(tmp_vault), "log", "--oneline"],
        capture_output=True, text=True, check=True,
    ).stdout
    assert "daily-" in log


def test_daily_skipped_when_recent(
    tmp_vault: Path, tmp_path: Path, monkeypatch, daily_main
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
    (tmp_vault / "00_Inbox" / "fresh.md").write_text("just now", encoding="utf-8")

    rc = daily_main(["--check-recent"])

    assert rc == 0
    from lib.common import current_iso_date
    skipped = tmp_vault / "05_Archive" / "daily-reports" / f"{current_iso_date()}-SKIPPED.md"
    assert skipped.exists()
    # Workbench should NOT have been created
    assert not (tmp_path / "wb").exists()


def test_daily_agent_failure(
    tmp_vault: Path, tmp_path: Path, monkeypatch, daily_main
) -> None:
    os.chmod(_CLAUDE_MOCK, 0o755)
    monkeypatch.setenv("CLAUDE_MOCK_MODE", "fail")
    _inject_local(
        monkeypatch,
        VAULT_DIR=str(tmp_vault),
        WORKBENCH_DIR=str(tmp_path / "wb"),
        VENV_DIR=str(tmp_path / "venv"),
        BACKEND="claude",
        AGENT_BIN=str(_CLAUDE_MOCK),
    )

    rc = daily_main([])

    from lib.common import AgentError, current_iso_date
    assert rc == AgentError.exit_code  # 3
    fail = tmp_vault / "05_Archive" / "daily-reports" / f"{current_iso_date()}-AGENT-FAILURE.md"
    assert fail.exists()
    assert not (tmp_path / "wb").exists()


def test_daily_noop_when_agent_quiet(
    tmp_vault: Path, tmp_path: Path, monkeypatch, daily_main
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

    # Even without a workbench commit, the success report we write into the
    # workbench triggers at least one commit, so merge_worktree returns
    # "success" rather than "noop". Just assert exit 0 and no crash.
    rc = daily_main([])
    assert rc == 0
    assert not (tmp_path / "wb").exists()
