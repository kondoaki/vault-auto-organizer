from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

from lib.common import (
    AgentError,
    OrganizerError,
    SkipRun,
    WorktreeMergeConflict,
    current_iso_date,
    current_iso_minute,
    current_month_prefix,
    generate_run_id,
    sync_with_origin,
)


def test_current_iso_date_format() -> None:
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", current_iso_date())


def test_current_iso_minute_format() -> None:
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}", current_iso_minute())


def test_current_month_prefix_format() -> None:
    assert re.fullmatch(r"\d{4}-\d{2}", current_month_prefix())


def test_generate_run_id_shape() -> None:
    rid = generate_run_id("daily")
    assert rid.startswith("daily-")
    assert re.fullmatch(r"daily-\d{4}-\d{2}-\d{2}", rid)


def test_exception_exit_codes() -> None:
    assert OrganizerError.exit_code == 1
    assert AgentError.exit_code == 3
    assert WorktreeMergeConflict.exit_code == 2
    assert SkipRun.exit_code == 0


def test_exception_inheritance() -> None:
    assert issubclass(AgentError, OrganizerError)
    assert issubclass(WorktreeMergeConflict, OrganizerError)
    assert issubclass(SkipRun, OrganizerError)


def test_sync_with_origin_no_remote_is_noop(tmp_vault: Path) -> None:
    # No origin configured → silently returns 0 (no exception).
    sync_with_origin(tmp_vault)


def test_sync_with_origin_diverged_raises(tmp_path: Path) -> None:
    # Set up: main repo + remote origin, then create divergence.
    origin = tmp_path / "origin.git"
    subprocess.run(["git", "init", "--bare", "-q", str(origin)], check=True)

    vault = tmp_path / "vault"
    vault.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=vault, check=True)
    git_env = ["-c", "user.email=t@l", "-c", "user.name=t"]
    subprocess.run(
        ["git", *git_env, "commit", "-q", "--allow-empty", "-m", "base"],
        cwd=vault, check=True,
    )
    subprocess.run(
        ["git", "-c", "init.defaultBranch=main", "branch", "-M", "main"],
        cwd=vault, check=True,
    )
    subprocess.run(
        ["git", "remote", "add", "origin", str(origin)], cwd=vault, check=True
    )
    subprocess.run(["git", "push", "-q", "origin", "main"], cwd=vault, check=True)

    # Push a new commit from a sibling clone, simulating another device.
    sibling = tmp_path / "sibling"
    subprocess.run(
        ["git", "clone", "-q", str(origin), str(sibling)], check=True
    )
    subprocess.run(
        ["git", *git_env, "commit", "-q", "--allow-empty", "-m", "remote-side"],
        cwd=sibling, check=True,
    )
    subprocess.run(["git", "push", "-q", "origin", "main"], cwd=sibling, check=True)

    # Local also moved → divergence after fetch.
    subprocess.run(
        ["git", *git_env, "commit", "-q", "--allow-empty", "-m", "local-side"],
        cwd=vault, check=True,
    )

    with pytest.raises(OrganizerError, match="diverged"):
        sync_with_origin(vault)
