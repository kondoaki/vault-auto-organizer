from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from lib.common import OrganizerError
from lib.snapshot import take_snapshot


def _head(vault: Path) -> str:
    return subprocess.run(
        ["git", "-C", str(vault), "rev-parse", "HEAD"],
        capture_output=True, text=True, check=True,
    ).stdout.strip()


def test_snapshot_noop_when_clean(tmp_vault: Path, make_config) -> None:
    cfg = make_config(vault_dir=tmp_vault)
    before = _head(tmp_vault)
    take_snapshot(cfg, label="daily-2026-05-05")
    assert _head(tmp_vault) == before


def test_snapshot_commits_dirty_changes(tmp_vault: Path, make_config) -> None:
    cfg = make_config(vault_dir=tmp_vault)
    (tmp_vault / "00_Inbox" / "new.md").write_text("hello", encoding="utf-8")
    before = _head(tmp_vault)
    take_snapshot(cfg, label="daily-2026-05-05")
    after = _head(tmp_vault)
    assert before != after
    msg = subprocess.run(
        ["git", "-C", str(tmp_vault), "log", "-1", "--pretty=%s"],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    assert msg.startswith("snapshot before daily-2026-05-05")


def test_snapshot_rejects_non_main_branch(tmp_vault: Path, make_config) -> None:
    cfg = make_config(vault_dir=tmp_vault)
    subprocess.run(
        ["git", "-C", str(tmp_vault), "checkout", "-q", "-b", "feature"],
        check=True,
    )
    with pytest.raises(OrganizerError, match="expected main"):
        take_snapshot(cfg, label="x")


def test_snapshot_rejects_non_repo(tmp_path: Path, make_config) -> None:
    bare = tmp_path / "bare"
    bare.mkdir()
    cfg = make_config(vault_dir=bare)
    with pytest.raises(OrganizerError, match="not a git repo"):
        take_snapshot(cfg, label="x")
