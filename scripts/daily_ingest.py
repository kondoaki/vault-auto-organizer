#!/usr/bin/env python3
"""Daily Ingest frame — runs nightly at 03:00 via launchd.

CLI:
    daily_ingest.py [--check-recent]

--check-recent  Skip the run if the vault was edited in the last 5 minutes.
                launchd passes this flag; manual invocations omit it.

Steps (in order):
    1. log rotation (month boundary)
    2. sync local main with origin (best-effort)
    3. skip-if-recent gate (when --check-recent)
    4. snapshot uncommitted vault changes
    5. prepare worktree on a fresh run branch
    6. invoke agent with the ingest prompt; on failure, write report and clean up
    7. squash-merge worktree into main
    8. write success report (best-effort, into the worktree before merge)
    9. push to upstream (best-effort, on EXIT)
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))  # make `lib` importable

from lib.agent import invoke_agent  # noqa: E402
from lib.common import (  # noqa: E402
    AgentError,
    OrganizerError,
    current_iso_date,
    generate_run_id,
    install_signal_handlers,
    load as load_config,
    log_error,
    log_info,
    rotate_log_if_needed,
)
from lib.git import (  # noqa: E402
    cleanup_worktree,
    merge_worktree,
    prepare_worktree,
    push_to_main,
    sync_with_origin,
    take_snapshot,
)
from lib.report import (  # noqa: E402
    commit_report,
    write_agent_failure,
    write_skipped,
    write_success,
)
from lib.skip_if_recent import is_recent  # noqa: E402


def main(argv: list[str]) -> int:
    cfg = load_config(check_recent="--check-recent" in argv)
    run_id = generate_run_id("daily")
    run_date = current_iso_date()

    install_signal_handlers(lambda: push_to_main(cfg))

    log_info(f"=== daily-ingest start (run_id={run_id}) ===")

    try:
        rotate_log_if_needed(cfg)
        sync_with_origin(cfg.vault_dir)

        if cfg.check_recent and is_recent(cfg):
            log_info("vault has recent edits — skipping")
            write_skipped(cfg, run_date, "vault edited within last 5 minutes")
            commit_report(cfg, f"skipped {run_id}")
            return 0

        take_snapshot(cfg, label=run_id)
        prepare_worktree(cfg, run_id)

        try:
            invoke_agent(cfg, run_id, prompt="ingest")
        except AgentError as e:
            log_error(f"agent invocation failed; aborting: {e}")
            write_agent_failure(cfg, run_date, run_id)
            cleanup_worktree(cfg, run_id)
            commit_report(cfg, f"agent-failure {run_id}")
            raise

        # Write the success report INTO the worktree so it gets merged with the
        # agent's changes as a single commit on main.
        write_success(
            cfg, run_date, "ingest+light-lint",
            processed="(see log.md for per-file detail)",
            unprocessed="(none)",
            lint="(see log.md)",
            base_dir=cfg.workbench_dir,
        )

        merge_worktree(cfg, run_id)
        log_info("=== daily-ingest done ===")
        return 0

    except OrganizerError as e:
        sys.stderr.write(f"{type(e).__name__}: {e}\n")
        return e.exit_code
    finally:
        push_to_main(cfg)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
