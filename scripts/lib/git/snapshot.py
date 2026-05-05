from __future__ import annotations

import subprocess
from datetime import datetime

from lib.common import Config, OrganizerError, log_info


def take_snapshot(cfg: Config, *, label: str) -> None:
    """Commit any uncommitted changes in the vault as a snapshot.

    No-op if the working tree is clean. ``label`` is interpolated into the
    commit message (typically the orchestrator's run_id).
    """
    if not (cfg.vault_dir / ".git").exists():
        raise OrganizerError(f"VAULT_DIR is not a git repo: {cfg.vault_dir}")

    branch = subprocess.run(
        ["git", "-C", str(cfg.vault_dir), "rev-parse", "--abbrev-ref", "HEAD"],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    if branch != "main":
        raise OrganizerError(f"expected main branch, got: {branch}")

    status = subprocess.run(
        ["git", "-C", str(cfg.vault_dir), "status", "--porcelain"],
        capture_output=True, text=True, check=True,
    )
    if not status.stdout.strip():
        return

    subprocess.run(
        ["git", "-C", str(cfg.vault_dir), "add", "-A"], check=True,
    )
    msg = f"snapshot before {label} {datetime.now().strftime('%H:%M')}"
    subprocess.run(
        [
            "git", "-C", str(cfg.vault_dir),
            "-c", "user.email=auto-organizer@local",
            "-c", "user.name=auto-organizer",
            "commit", "-m", msg,
        ],
        check=True,
    )
    log_info("committed pre-batch snapshot")


__all__ = ["take_snapshot"]
