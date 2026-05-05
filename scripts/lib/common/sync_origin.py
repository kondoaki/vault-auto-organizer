from __future__ import annotations

import subprocess
from pathlib import Path

from .exceptions import OrganizerError
from .logger import log_error, log_info


def _git(vault_dir: Path, *args: str, capture: bool = False) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        ["git", "-C", str(vault_dir), *args],
        capture_output=capture,
    )


def sync_with_origin(vault_dir: Path) -> None:
    """Best-effort fast-forward of local main from origin/main.

    Mirrors the bash sync_with_origin: missing remote, fetch failure, or
    missing origin/main are logged and skipped (offline runs proceed).
    True divergence (non-fast-forward) is fatal — caller should resolve
    manually before the next run.
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

    if _git(vault_dir, "merge", "--ff-only", "origin/main").returncode != 0:
        raise OrganizerError(
            "ff-only merge from origin/main failed: local main has diverged "
            "from origin/main. Resolve manually (rebase or merge) before the "
            "next run."
        )

    log_info("synced local main to origin/main (ff-only)")
