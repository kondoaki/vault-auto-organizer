from __future__ import annotations

import subprocess
from datetime import datetime
from pathlib import Path
from typing import Optional

from lib.common import log_info
from lib.config import Config

_TRACKED_PATHS = (
    "log.md",
    "05_Archive/logs",
    "05_Archive/daily-reports",
    "05_Archive/lint-reports",
)


def commit_report(cfg: Config, message: str) -> None:
    """Stage and commit only the orchestrator's own writes.

    No-op if all tracked paths are clean. The commit explicitly avoids
    sweeping unrelated user/agent edits — those belong to the next
    non-skipped run, captured by the worktree snapshot.
    """
    status = subprocess.run(
        ["git", "-C", str(cfg.vault_dir), "status", "--porcelain", "--", *_TRACKED_PATHS],
        capture_output=True,
        text=True,
    )
    if not status.stdout.strip():
        return

    subprocess.run(
        ["git", "-C", str(cfg.vault_dir), "add", "--", *_TRACKED_PATHS],
        check=True,
    )
    full_msg = f"{message} {datetime.now().strftime('%H:%M')}"
    subprocess.run(
        [
            "git", "-C", str(cfg.vault_dir),
            "-c", "user.email=auto-organizer@local",
            "-c", "user.name=auto-organizer",
            "commit", "-q", "-m", full_msg,
        ],
        check=True,
    )


def _base(cfg: Config, base_dir: Optional[Path]) -> Path:
    return base_dir if base_dir is not None else cfg.vault_dir


def write_skipped(
    cfg: Config,
    date: str,
    reason: str,
    *,
    base_dir: Optional[Path] = None,
) -> Path:
    out = _base(cfg, base_dir) / "05_Archive" / "daily-reports" / f"{date}-SKIPPED.md"
    out.write_text(
        f"""---
type: daily-report
date: {date}
mode: skipped
result: skipped
---

# Daily Report {date} — SKIPPED

Reason: {reason}

The next scheduled run will retry.
""",
        encoding="utf-8",
    )
    return out


def write_conflict(
    cfg: Config,
    date: str,
    branch: str,
    files: str,
    *,
    base_dir: Optional[Path] = None,
) -> Path:
    out = _base(cfg, base_dir) / "05_Archive" / "daily-reports" / f"{date}-CONFLICT.md"
    out.write_text(
        f"""---
type: daily-report
date: {date}
mode: conflict
result: conflict
branch: {branch}
---

# Daily Report {date} — CONFLICT

The agent's branch `{branch}` could not be merged cleanly into `main`.
The merge has been aborted; main is unchanged.

## Conflicting files
```
{files}
```

## Recovery
1. Inspect the workbench (if not yet cleaned up): `~/Workspace/vault-workbench/`
2. Either resolve manually and `git merge --continue`, or discard with `git branch -D {branch}`.
""",
        encoding="utf-8",
    )
    return out


def write_agent_failure(
    cfg: Config,
    date: str,
    run_id: str,
    *,
    base_dir: Optional[Path] = None,
) -> Path:
    out = _base(cfg, base_dir) / "05_Archive" / "daily-reports" / f"{date}-AGENT-FAILURE.md"
    out.write_text(
        f"""---
type: daily-report
date: {date}
mode: agent-failure
result: agent-failure
run_id: {run_id}
---

# Daily Report {date} — AGENT FAILURE

The `{cfg.backend}` CLI exited non-zero during run `{run_id}`. Main is unchanged.

## Diagnostics
- launchd stdout: `~/Library/Logs/vault-organizer-{{ingest,lint}}.log`
- launchd stderr: `~/Library/Logs/vault-organizer-{{ingest,lint}}.err`

The next scheduled run will retry from a clean slate.
""",
        encoding="utf-8",
    )
    return out


def write_success(
    cfg: Config,
    date: str,
    mode: str,
    processed: str,
    unprocessed: str,
    lint: str,
    *,
    base_dir: Optional[Path] = None,
) -> Path:
    """mode ∈ {"ingest+light-lint", "full-lint"}.

    If a report at the target path is already dirty in git (i.e. the agent
    wrote it during this run), leave it untouched.
    """
    base = _base(cfg, base_dir)
    if mode == "full-lint":
        out = base / "05_Archive" / "lint-reports" / f"{date}-weekly.md"
    else:
        out = base / "05_Archive" / "daily-reports" / f"{date}.md"

    out_rel = out.relative_to(base)
    status = subprocess.run(
        ["git", "-C", str(base), "status", "--porcelain", "--", str(out_rel)],
        capture_output=True,
        text=True,
    )
    if status.stdout.strip():
        log_info(f"report already written by agent: {out} — leaving as-is")
        return out

    out.write_text(
        f"""---
type: daily-report
date: {date}
mode: {mode}
result: success
---

# Daily Report {date}

## Processed
{processed}

## Unprocessed
{unprocessed}

## Lint
{lint}

## Conflict / errors
(none)
""",
        encoding="utf-8",
    )
    return out


__all__ = [
    "commit_report",
    "write_agent_failure",
    "write_conflict",
    "write_skipped",
    "write_success",
]
