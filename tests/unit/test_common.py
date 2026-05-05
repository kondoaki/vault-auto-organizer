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
)
from lib.git import sync_with_origin


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


def test_sync_with_origin_diverged_resets_to_origin(tmp_path: Path) -> None:
    """When local main diverges from origin/main, sync_with_origin does a
    mixed reset: HEAD + index move to origin/main; the working tree is
    untouched. Deployed alongside file sync (Syncthing / iCloud), the
    on-disk content already matches origin/main, so the status ends up
    clean and take_snapshot has nothing to do.
    """
    origin = tmp_path / "origin.git"
    subprocess.run(["git", "init", "--bare", "-q", str(origin)], check=True)

    vault = tmp_path / "vault"
    vault.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=vault, check=True)
    git_env = ["-c", "user.email=t@l", "-c", "user.name=t"]
    (vault / "base.md").write_text("base\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=vault, check=True)
    subprocess.run(
        ["git", *git_env, "commit", "-q", "-m", "base"], cwd=vault, check=True
    )
    subprocess.run(["git", "branch", "-M", "main"], cwd=vault, check=True)
    subprocess.run(
        ["git", "remote", "add", "origin", str(origin)], cwd=vault, check=True
    )
    subprocess.run(["git", "push", "-q", "origin", "main"], cwd=vault, check=True)

    # Sibling clone adds a file that file-sync would normally also drop on the
    # local machine. Push it to origin to advance origin/main.
    sibling = tmp_path / "sibling"
    subprocess.run(["git", "clone", "-q", str(origin), str(sibling)], check=True)
    (sibling / "from-other-device.md").write_text("hello\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=sibling, check=True)
    subprocess.run(
        ["git", *git_env, "commit", "-q", "-m", "remote-side"], cwd=sibling, check=True
    )
    subprocess.run(["git", "push", "-q", "origin", "main"], cwd=sibling, check=True)

    # Simulate the file-sync side delivering the same content to local before
    # local commits its own snapshot of identical content.
    (vault / "from-other-device.md").write_text("hello\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=vault, check=True)
    subprocess.run(
        ["git", *git_env, "commit", "-q", "-m", "local-snapshot"], cwd=vault, check=True
    )

    sync_with_origin(vault)

    # HEAD now matches origin/main exactly (the local-snapshot commit is gone).
    head = subprocess.run(
        ["git", "-C", str(vault), "rev-parse", "HEAD"],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    origin_main = subprocess.run(
        ["git", "-C", str(vault), "rev-parse", "origin/main"],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    assert head == origin_main

    # Working-tree content is intact; status is clean because the file content
    # is identical to origin/main's tree.
    assert (vault / "from-other-device.md").exists()
    status = subprocess.run(
        ["git", "-C", str(vault), "status", "--porcelain"],
        capture_output=True, text=True, check=True,
    ).stdout
    assert status == ""
