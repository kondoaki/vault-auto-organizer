"""Shared pytest fixtures and path setup."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

# Make `scripts/` importable as the top-level package source.
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))


import pytest  # noqa: E402


@pytest.fixture
def tmp_vault(tmp_path: Path) -> Path:
    """A synthetic vault under tmp_path: git-initialized, with the standard
    folder skeleton. Tests should not point at real vaults — CLAUDE.md rule.
    """
    vault = tmp_path / "vault"
    vault.mkdir()
    for sub in (
        "00_Inbox",
        "01_Projects",
        "02_Ideas",
        "03_Context/_pending-updates",
        "04_Resources",
        "05_Archive/logs",
        "05_Archive/daily-reports",
        "05_Archive/lint-reports",
        "05_Archive/orphans",
    ):
        (vault / sub).mkdir(parents=True, exist_ok=True)
    (vault / "log.md").write_text("")
    for keep_dir in (
        "00_Inbox",
        "01_Projects",
        "02_Ideas",
        "03_Context/_pending-updates",
        "04_Resources",
        "05_Archive/logs",
        "05_Archive/daily-reports",
        "05_Archive/lint-reports",
        "05_Archive/orphans",
    ):
        (vault / keep_dir / ".gitkeep").touch()

    subprocess.run(
        ["git", "-c", "init.defaultBranch=main", "init", "-q"],
        cwd=vault, check=True,
    )
    subprocess.run(["git", "add", "-A"], cwd=vault, check=True)
    subprocess.run(
        ["git", "-c", "user.email=test@local", "-c", "user.name=test",
         "commit", "-q", "-m", "initial"],
        cwd=vault, check=True,
    )
    # Ensure the default branch is exactly 'main' regardless of host git config.
    subprocess.run(["git", "branch", "-M", "main"], cwd=vault, check=True)
    return vault


@pytest.fixture
def make_config(tmp_path: Path):
    """Factory returning a Config bound to a tmp vault. Lets tests inject
    their own paths without touching the install-rendered local.py.
    """
    from lib.common import Config

    def _make(vault_dir: Path | None = None, **overrides) -> Config:
        v = vault_dir if vault_dir is not None else tmp_path / "vault"
        defaults = dict(
            vault_dir=v,
            workbench_dir=tmp_path / "workbench",
            venv_dir=tmp_path / "venv",
            backend="claude",
            agent_bin="/usr/bin/false",  # safe default for tests
            check_recent=False,
        )
        defaults.update(overrides)
        return Config(**defaults)

    return _make
