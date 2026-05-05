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
    """Reset local main to origin/main. Assumes file-sync keeps the working
    tree aligned across devices — see README §Sync prerequisites."""
    if _git(vault_dir, "remote", "get-url", "origin", capture=True).returncode != 0:
        log_info("no origin remote configured; skipping pre-run sync")
        return

    if _git(vault_dir, "fetch", "origin").returncode != 0:
        log_error("git fetch origin failed; proceeding with local state")
        return

    if _git(vault_dir, "rev-parse", "--verify", "origin/main", capture=True).returncode != 0:
        log_info("origin/main not found after fetch; skipping reset")
        return

    if _git(vault_dir, "reset", "origin/main").returncode != 0:
        raise OrganizerError("git reset to origin/main failed; resolve manually.")
    log_info("reset local main to origin/main")


__all__ = ["sync_with_origin"]
