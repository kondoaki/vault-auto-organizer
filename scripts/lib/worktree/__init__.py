from __future__ import annotations

import shutil
import subprocess
from datetime import datetime

from lib.common import (
    Config,
    OrganizerError,
    WorktreeMergeConflict,
    current_iso_date,
    log_error,
    log_info,
)


def prepare_worktree(cfg: Config, run_id: str) -> None:
    """Create a fresh git worktree at ``cfg.workbench_dir`` on branch ``run_id``.

    Removes any stale workbench directory and same-named branch first.
    The caller is expected to have run ``lib.snapshot.take_snapshot`` so
    the run starts from a clean ``main``.
    """
    if not (cfg.vault_dir / ".git").exists():
        raise OrganizerError(f"VAULT_DIR is not a git repo: {cfg.vault_dir}")

    if cfg.workbench_dir.exists():
        log_info(f"removing stale workbench at {cfg.workbench_dir}")
        subprocess.run(
            ["git", "-C", str(cfg.vault_dir), "worktree", "remove", "--force",
             str(cfg.workbench_dir)],
            capture_output=True,
        )
        shutil.rmtree(cfg.workbench_dir, ignore_errors=True)

    subprocess.run(
        ["git", "-C", str(cfg.vault_dir), "branch", "-D", run_id],
        capture_output=True,
    )

    cfg.workbench_dir.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["git", "-C", str(cfg.vault_dir), "worktree", "add", "-b", run_id,
         str(cfg.workbench_dir)],
        check=True,
    )
    log_info(f"worktree ready at {cfg.workbench_dir} on branch {run_id}")


def cleanup_worktree(cfg: Config, run_id: str) -> None:
    """Remove the workbench directory and the run branch. Idempotent."""
    subprocess.run(
        ["git", "-C", str(cfg.vault_dir), "worktree", "remove", "--force",
         str(cfg.workbench_dir)],
        capture_output=True,
    )
    shutil.rmtree(cfg.workbench_dir, ignore_errors=True)
    subprocess.run(
        ["git", "-C", str(cfg.vault_dir), "branch", "-D", run_id],
        capture_output=True,
    )


def merge_worktree(cfg: Config, run_id: str) -> str:
    """Squash-merge the run branch into main.

    Returns ``"success"`` when at least one commit was merged, ``"noop"``
    when the agent made no changes. Raises ``WorktreeMergeConflict`` on
    conflict — the conflict report is written and the user is notified
    before raising. The workbench is left in place on conflict so the
    user can investigate.
    """
    from lib.report import commit_report, write_conflict

    base_branch = subprocess.run(
        ["git", "-C", str(cfg.vault_dir), "rev-parse", "--abbrev-ref", "HEAD"],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    if base_branch == "HEAD":
        raise OrganizerError("VAULT_DIR is on a detached HEAD; refuse to merge")

    # 1. Commit any pending agent changes inside the workbench.
    status = subprocess.run(
        ["git", "-C", str(cfg.workbench_dir), "status", "--porcelain"],
        capture_output=True, text=True, check=True,
    )
    if status.stdout.strip():
        subprocess.run(
            ["git", "-C", str(cfg.workbench_dir), "add", "-A"], check=True,
        )
        subprocess.run(
            [
                "git", "-C", str(cfg.workbench_dir),
                "-c", "user.email=auto-organizer@local",
                "-c", "user.name=auto-organizer",
                "commit", "-m", f"{run_id} {datetime.now().strftime('%H:%M')}",
            ],
            check=True,
        )

    # 2. If the run branch has nothing ahead of base, treat as noop.
    ahead = subprocess.run(
        ["git", "-C", str(cfg.vault_dir), "rev-list", f"{base_branch}..{run_id}", "--count"],
        capture_output=True, text=True,
    )
    ahead_count = int(ahead.stdout.strip()) if ahead.returncode == 0 and ahead.stdout.strip() else 0
    if ahead_count == 0:
        log_info("agent made no changes; cleaning up worktree")
        cleanup_worktree(cfg, run_id)
        return "noop"

    # 3. Squash-merge into main. Agent changes + report land as one commit.
    merge = subprocess.run(
        ["git", "-C", str(cfg.vault_dir), "merge", "--squash", run_id],
        capture_output=True, text=True,
    )
    if merge.returncode == 0:
        subprocess.run(
            [
                "git", "-C", str(cfg.vault_dir),
                "-c", "user.email=auto-organizer@local",
                "-c", "user.name=auto-organizer",
                "commit", "-q", "-m", f"{run_id} {datetime.now().strftime('%H:%M')}",
            ],
            check=True,
        )
        log_info(f"squashed {run_id} into main")
        cleanup_worktree(cfg, run_id)
        return "success"

    # 4. Conflict path. --squash leaves the index conflicted but no MERGE_HEAD,
    #    so `git reset --merge` (not `merge --abort`) is the correct cleanup.
    log_error("merge conflict — aborting")
    conflicted_raw = subprocess.run(
        ["git", "-C", str(cfg.vault_dir), "diff", "--name-only", "--diff-filter=U"],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    subprocess.run(
        ["git", "-C", str(cfg.vault_dir), "reset", "--merge"], check=True,
    )

    write_conflict(cfg, current_iso_date(), run_id, conflicted_raw)
    commit_report(cfg, f"conflict report {run_id}")

    subprocess.run(
        ["osascript", "-e",
         f'display notification "Vault merge conflict on {run_id} — see '
         f'05_Archive/daily-reports/{current_iso_date()}-CONFLICT.md" '
         f'with title "Vault Auto-Organizer"'],
        capture_output=True,
    )

    files = conflicted_raw.split("\n") if conflicted_raw else []
    raise WorktreeMergeConflict(run_id=run_id, conflicted_files=files)


__all__ = ["cleanup_worktree", "merge_worktree", "prepare_worktree"]
