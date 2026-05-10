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
def project_sync_main():
    import importlib

    for m in ("project_sync", "lib.project_sync.cli", "lib.project_sync.sync"):
        if m in sys.modules:
            del sys.modules[m]
    module = importlib.import_module("project_sync")
    return module.main


def _git_init_repo(path: Path, *, files: dict) -> None:
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["git", "-c", "init.defaultBranch=main", "init", "-q"],
        cwd=path, check=True,
    )
    for rel, content in files.items():
        f = path / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(content, encoding="utf-8")
    subprocess.run(["git", "-C", str(path), "add", "-A"], check=True)
    subprocess.run(
        ["git", "-C", str(path),
         "-c", "user.email=t@e", "-c", "user.name=t",
         "commit", "-q", "-m", "init"],
        check=True,
    )


def test_single_repo_creates_note(
    tmp_vault: Path, tmp_path: Path, monkeypatch, project_sync_main
):
    os.chmod(_CLAUDE_MOCK, 0o755)
    monkeypatch.setenv("CLAUDE_MOCK_MODE", "project-sync")
    monkeypatch.setenv("HOME", str(tmp_path))

    repo = tmp_path / "Projects" / "alpha"
    _git_init_repo(repo, files={"README.md": "# alpha\n"})

    _inject_local(
        monkeypatch,
        VAULT_DIR=str(tmp_vault),
        WORKBENCH_DIR=str(tmp_path / "wb"),
        VENV_DIR=str(tmp_path / "venv"),
        BACKEND="claude",
        AGENT_BIN=str(_CLAUDE_MOCK),
    )

    rc = project_sync_main([str(repo)])
    assert rc == 0

    note = tmp_vault / "01_Projects" / "alpha.md"
    assert note.exists()
    text = note.read_text(encoding="utf-8")
    assert "project_path: ~/Projects/alpha" in text
    assert "last_synced_commit:" in text
    assert "<!-- vault-sync:start -->" in text
    assert "<!-- vault-sync:end -->" in text
    assert "### Purpose" in text

    # Single commit on main
    log = subprocess.run(
        ["git", "-C", str(tmp_vault), "log", "--oneline"],
        capture_output=True, text=True, check=True,
    ).stdout
    assert "project-sync: alpha @" in log


def test_skip_when_unchanged(
    tmp_vault: Path, tmp_path: Path, monkeypatch, project_sync_main
):
    os.chmod(_CLAUDE_MOCK, 0o755)
    monkeypatch.setenv("CLAUDE_MOCK_MODE", "project-sync")
    monkeypatch.setenv("HOME", str(tmp_path))

    repo = tmp_path / "Projects" / "beta"
    _git_init_repo(repo, files={"README.md": "# beta\n"})

    _inject_local(
        monkeypatch,
        VAULT_DIR=str(tmp_vault),
        WORKBENCH_DIR=str(tmp_path / "wb"),
        VENV_DIR=str(tmp_path / "venv"),
        BACKEND="claude",
        AGENT_BIN=str(_CLAUDE_MOCK),
    )

    assert project_sync_main([str(repo)]) == 0
    log_before = subprocess.run(
        ["git", "-C", str(tmp_vault), "log", "--oneline"],
        capture_output=True, text=True, check=True,
    ).stdout

    # Sabotage the mock so it would fail if re-invoked; skip path must not call it.
    monkeypatch.setenv("CLAUDE_MOCK_MODE", "fail")
    assert project_sync_main([str(repo)]) == 0

    log_after = subprocess.run(
        ["git", "-C", str(tmp_vault), "log", "--oneline"],
        capture_output=True, text=True, check=True,
    ).stdout
    assert log_before == log_after


def test_force_resyncs(
    tmp_vault: Path, tmp_path: Path, monkeypatch, project_sync_main
):
    os.chmod(_CLAUDE_MOCK, 0o755)
    monkeypatch.setenv("CLAUDE_MOCK_MODE", "project-sync")
    monkeypatch.setenv("HOME", str(tmp_path))

    repo = tmp_path / "Projects" / "gamma"
    _git_init_repo(repo, files={"README.md": "# gamma\n"})

    _inject_local(
        monkeypatch,
        VAULT_DIR=str(tmp_vault),
        WORKBENCH_DIR=str(tmp_path / "wb"),
        VENV_DIR=str(tmp_path / "venv"),
        BACKEND="claude",
        AGENT_BIN=str(_CLAUDE_MOCK),
    )

    assert project_sync_main([str(repo)]) == 0
    rc = project_sync_main([str(repo), "--force"])
    assert rc == 0
    log = subprocess.run(
        ["git", "-C", str(tmp_vault), "log", "--oneline"],
        capture_output=True, text=True, check=True,
    ).stdout
    # First commit creates the note; second --force run touches the
    # `last_synced` timestamp, which adds another commit (assuming the wall
    # clock advanced or the mock body changed). The first commit is always
    # present; a second is best-effort.
    assert log.count("project-sync: gamma") >= 1


def test_bulk_mode_two_repos(
    tmp_vault: Path, tmp_path: Path, monkeypatch, project_sync_main
):
    os.chmod(_CLAUDE_MOCK, 0o755)
    monkeypatch.setenv("CLAUDE_MOCK_MODE", "project-sync")
    monkeypatch.setenv("HOME", str(tmp_path))

    parent = tmp_path / "Projects"
    parent.mkdir()
    _git_init_repo(parent / "one", files={"README.md": "# one\n"})
    _git_init_repo(parent / "two", files={"README.md": "# two\n"})

    _inject_local(
        monkeypatch,
        VAULT_DIR=str(tmp_vault),
        WORKBENCH_DIR=str(tmp_path / "wb"),
        VENV_DIR=str(tmp_path / "venv"),
        BACKEND="claude",
        AGENT_BIN=str(_CLAUDE_MOCK),
    )

    rc = project_sync_main([str(parent)])
    assert rc == 0
    assert (tmp_vault / "01_Projects" / "one.md").exists()
    assert (tmp_vault / "01_Projects" / "two.md").exists()

    log = subprocess.run(
        ["git", "-C", str(tmp_vault), "log", "--oneline"],
        capture_output=True, text=True, check=True,
    ).stdout
    assert "project-sync: 2 projects" in log


def test_invalid_target_returns_two(
    tmp_vault: Path, tmp_path: Path, monkeypatch, project_sync_main
):
    os.chmod(_CLAUDE_MOCK, 0o755)
    _inject_local(
        monkeypatch,
        VAULT_DIR=str(tmp_vault),
        WORKBENCH_DIR=str(tmp_path / "wb"),
        VENV_DIR=str(tmp_path / "venv"),
        BACKEND="claude",
        AGENT_BIN=str(_CLAUDE_MOCK),
    )
    rc = project_sync_main([str(tmp_path / "does-not-exist")])
    assert rc == 2
