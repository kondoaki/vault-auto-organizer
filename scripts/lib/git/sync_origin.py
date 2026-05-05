from __future__ import annotations

import subprocess
from pathlib import Path

from lib.common import OrganizerError, log_error, log_info


def _git(vault_dir: Path, *args: str, capture: bool = False) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        ["git", "-C", str(vault_dir), *args],
        capture_output=capture,
    )


def sync_with_origin(vault_dir: Path) -> None:
    """Align local main with origin/main before the run starts.

    Tries ff-only first; on divergence falls back to a mixed
    ``git reset origin/main``. Assumes the vault content is also kept
    in sync across devices by an external file syncer (Syncthing /
    iCloud) — see README §Sync prerequisites.
    """
    if _git(vault_dir, "remote", "get-url", "origin", capture=True).returncode != 0:
        log_info("no origin remote configured; skipping pre-run sync")
        return

    if _git(vault_dir, "fetch", "origin").returncode != 0:
        log_error("git fetch origin failed; proceeding with local state")
        return

    if _git(vault_dir, "rev-parse", "--verify", "origin/main", capture=True).returncode != 0:
        log_info("origin/main not found after fetch; skipping merge")
        return

    if _git(vault_dir, "merge", "--ff-only", "origin/main").returncode == 0:
        log_info("synced local main to origin/main (ff-only)")
        return

    # Diverged: mixed reset HEAD to origin/main. The working tree is left
    # alone — file-sync (Syncthing / iCloud) is expected to keep on-disk
    # content aligned across devices, so the result ends up clean.
    if _git(vault_dir, "reset", "origin/main").returncode != 0:
        raise OrganizerError(
            "git reset to origin/main failed; resolve manually before the next run."
        )
    log_info("local main diverged from origin/main; reset HEAD to origin/main")


__all__ = ["sync_with_origin"]
