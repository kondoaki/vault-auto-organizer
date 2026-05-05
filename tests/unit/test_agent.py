from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from lib.agent import invoke_agent
from lib.common import AgentError, OrganizerError
from lib.git import prepare_worktree


_REPO_ROOT = Path(__file__).resolve().parents[2]
_CLAUDE_MOCK = _REPO_ROOT / "tests" / "fixtures" / "claude-mock" / "claude"
_OPENCODE_MOCK = _REPO_ROOT / "tests" / "fixtures" / "opencode-mock" / "opencode"


def _make_mock_executable() -> None:
    for p in (_CLAUDE_MOCK, _OPENCODE_MOCK):
        os.chmod(p, 0o755)


def test_claude_backend_noop(
    tmp_vault: Path, tmp_path: Path, make_config, monkeypatch
) -> None:
    _make_mock_executable()
    monkeypatch.setenv("CLAUDE_MOCK_MODE", "noop")
    cfg = make_config(
        vault_dir=tmp_vault,
        workbench_dir=tmp_path / "wb",
        backend="claude",
        agent_bin=str(_CLAUDE_MOCK),
    )
    prepare_worktree(cfg, "daily-test")
    invoke_agent(cfg, "daily-test", prompt="ingest")  # must not raise


def test_claude_backend_failure_raises_agent_error(
    tmp_vault: Path, tmp_path: Path, make_config, monkeypatch
) -> None:
    _make_mock_executable()
    monkeypatch.setenv("CLAUDE_MOCK_MODE", "fail")
    cfg = make_config(
        vault_dir=tmp_vault,
        workbench_dir=tmp_path / "wb",
        backend="claude",
        agent_bin=str(_CLAUDE_MOCK),
    )
    prepare_worktree(cfg, "daily-test")
    with pytest.raises(AgentError):
        invoke_agent(cfg, "daily-test", prompt="ingest")


def test_claude_backend_modifies_workbench(
    tmp_vault: Path, tmp_path: Path, make_config, monkeypatch
) -> None:
    _make_mock_executable()
    monkeypatch.setenv("CLAUDE_MOCK_MODE", "move-inbox-file")
    cfg = make_config(
        vault_dir=tmp_vault,
        workbench_dir=tmp_path / "wb",
        backend="claude",
        agent_bin=str(_CLAUDE_MOCK),
    )
    prepare_worktree(cfg, "daily-test")
    inbox_file = cfg.workbench_dir / "00_Inbox" / "test.md"
    inbox_file.write_text("hello", encoding="utf-8")
    invoke_agent(cfg, "daily-test", prompt="ingest")
    assert not inbox_file.exists()
    assert (cfg.workbench_dir / "05_Archive" / "test.md").exists()


def test_opencode_backend_noop(
    tmp_vault: Path, tmp_path: Path, make_config, monkeypatch
) -> None:
    _make_mock_executable()
    monkeypatch.setenv("OPENCODE_MOCK_MODE", "noop")
    cfg = make_config(
        vault_dir=tmp_vault,
        workbench_dir=tmp_path / "wb",
        backend="opencode",
        agent_bin=str(_OPENCODE_MOCK),
    )
    prepare_worktree(cfg, "daily-test")
    invoke_agent(cfg, "daily-test", prompt="ingest")


def test_opencode_backend_failure(
    tmp_vault: Path, tmp_path: Path, make_config, monkeypatch
) -> None:
    _make_mock_executable()
    monkeypatch.setenv("OPENCODE_MOCK_MODE", "fail")
    cfg = make_config(
        vault_dir=tmp_vault,
        workbench_dir=tmp_path / "wb",
        backend="opencode",
        agent_bin=str(_OPENCODE_MOCK),
    )
    prepare_worktree(cfg, "daily-test")
    with pytest.raises(AgentError):
        invoke_agent(cfg, "daily-test", prompt="ingest")


def test_unknown_backend_raises(tmp_vault: Path, tmp_path: Path, make_config) -> None:
    cfg = make_config(
        vault_dir=tmp_vault,
        workbench_dir=tmp_path / "wb",
        backend="bogus",
    )
    prepare_worktree(cfg, "daily-test")
    with pytest.raises(OrganizerError, match="unknown backend"):
        invoke_agent(cfg, "daily-test", prompt="ingest")


def test_missing_workbench_raises(tmp_vault: Path, tmp_path: Path, make_config) -> None:
    cfg = make_config(
        vault_dir=tmp_vault,
        workbench_dir=tmp_path / "missing-wb",
        backend="claude",
        agent_bin=str(_CLAUDE_MOCK),
    )
    with pytest.raises(OrganizerError, match="workbench does not exist"):
        invoke_agent(cfg, "daily-test", prompt="ingest")


def test_missing_prompt_raises(tmp_vault: Path, tmp_path: Path, make_config) -> None:
    cfg = make_config(
        vault_dir=tmp_vault,
        workbench_dir=tmp_path / "wb",
        backend="claude",
        agent_bin=str(_CLAUDE_MOCK),
    )
    prepare_worktree(cfg, "daily-test")
    with pytest.raises(OrganizerError, match="prompt file not found"):
        invoke_agent(cfg, "daily-test", prompt="nonexistent")
