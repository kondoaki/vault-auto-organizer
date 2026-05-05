from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from lib.common import OrganizerError, WorktreeMergeConflict
from lib.git import cleanup_worktree, merge_worktree, prepare_worktree


def _git(vault: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(vault), *args],
        capture_output=True, text=True, check=True,
    )


def test_prepare_creates_worktree(tmp_vault: Path, tmp_path: Path, make_config) -> None:
    cfg = make_config(vault_dir=tmp_vault, workbench_dir=tmp_path / "wb")
    prepare_worktree(cfg, "daily-test")
    assert cfg.workbench_dir.exists()
    assert (cfg.workbench_dir / ".git").exists()
    branches = _git(tmp_vault, "branch").stdout
    assert "daily-test" in branches


def test_prepare_cleans_up_stale(tmp_vault: Path, tmp_path: Path, make_config) -> None:
    cfg = make_config(vault_dir=tmp_vault, workbench_dir=tmp_path / "wb")
    prepare_worktree(cfg, "daily-test")
    # Re-running with the same run_id must not raise.
    prepare_worktree(cfg, "daily-test")
    assert cfg.workbench_dir.exists()


def test_merge_noop_when_agent_made_no_changes(
    tmp_vault: Path, tmp_path: Path, make_config
) -> None:
    cfg = make_config(vault_dir=tmp_vault, workbench_dir=tmp_path / "wb")
    prepare_worktree(cfg, "daily-test")
    result = merge_worktree(cfg, "daily-test")
    assert result == "noop"
    assert not cfg.workbench_dir.exists()


def test_merge_success(tmp_vault: Path, tmp_path: Path, make_config) -> None:
    cfg = make_config(vault_dir=tmp_vault, workbench_dir=tmp_path / "wb")
    prepare_worktree(cfg, "daily-test")
    (cfg.workbench_dir / "01_Projects" / "x.md").write_text("from agent", encoding="utf-8")
    result = merge_worktree(cfg, "daily-test")
    assert result == "success"
    assert (tmp_vault / "01_Projects" / "x.md").read_text(encoding="utf-8") == "from agent"
    assert not cfg.workbench_dir.exists()


def test_merge_conflict_raises_and_writes_report(
    tmp_vault: Path, tmp_path: Path, make_config
) -> None:
    cfg = make_config(vault_dir=tmp_vault, workbench_dir=tmp_path / "wb")
    target = tmp_vault / "01_Projects" / "shared.md"
    target.write_text("base content\n", encoding="utf-8")
    _git(tmp_vault, "add", "-A")
    _git(tmp_vault, "-c", "user.email=t@l", "-c", "user.name=t",
         "commit", "-m", "add shared")

    prepare_worktree(cfg, "daily-test")

    # Workbench writes one version
    (cfg.workbench_dir / "01_Projects" / "shared.md").write_text(
        "agent edit\n", encoding="utf-8"
    )
    # Main writes a conflicting version
    target.write_text("user edit\n", encoding="utf-8")
    _git(tmp_vault, "add", "-A")
    _git(tmp_vault, "-c", "user.email=t@l", "-c", "user.name=t",
         "commit", "-m", "concurrent main edit")

    with pytest.raises(WorktreeMergeConflict) as excinfo:
        merge_worktree(cfg, "daily-test")
    assert "01_Projects/shared.md" in excinfo.value.conflicted_files
    # Conflict report was written
    from lib.common import current_iso_date
    report = tmp_vault / "05_Archive" / "daily-reports" / f"{current_iso_date()}-CONFLICT.md"
    assert report.exists()
    # Workbench preserved on conflict
    assert cfg.workbench_dir.exists()


def test_merge_rejects_detached_head(
    tmp_vault: Path, tmp_path: Path, make_config
) -> None:
    cfg = make_config(vault_dir=tmp_vault, workbench_dir=tmp_path / "wb")
    prepare_worktree(cfg, "daily-test")
    # Detach HEAD on the main repo
    _git(tmp_vault, "checkout", "-q", "--detach", "HEAD")
    with pytest.raises(OrganizerError, match="detached"):
        merge_worktree(cfg, "daily-test")


def test_cleanup_idempotent(tmp_vault: Path, tmp_path: Path, make_config) -> None:
    cfg = make_config(vault_dir=tmp_vault, workbench_dir=tmp_path / "wb")
    prepare_worktree(cfg, "daily-test")
    cleanup_worktree(cfg, "daily-test")
    cleanup_worktree(cfg, "daily-test")  # second call must not raise
    assert not cfg.workbench_dir.exists()
