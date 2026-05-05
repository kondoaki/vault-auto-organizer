#!/usr/bin/env python3
"""Weekly full Lint frame — runs Sunday 03:30 via launchd.

CLI:
    weekly_lint.py [--check-recent]

Same skeleton as daily_ingest.py, but invokes the lint_full prompt and
writes a weekly lint report.
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
    log_error,
    log_info,
    sync_with_origin,
)
from lib.config import load as load_config  # noqa: E402
from lib.log import rotate_log_if_needed  # noqa: E402
from lib.push import push_to_main  # noqa: E402
from lib.report import (  # noqa: E402
    commit_report,
    write_agent_failure,
    write_skipped,
    write_success,
)
from lib.skip_if_recent import is_recent  # noqa: E402
from lib.snapshot import take_snapshot  # noqa: E402
from lib.worktree import (  # noqa: E402
    cleanup_worktree,
    merge_worktree,
    prepare_worktree,
)


def main(argv: list[str]) -> int:
    cfg = load_config(check_recent="--check-recent" in argv)
    run_id = generate_run_id("lint-full")
    run_date = current_iso_date()

    install_signal_handlers(lambda: push_to_main(cfg))

    log_info(f"=== weekly-lint start (run_id={run_id}) ===")

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
            invoke_agent(cfg, run_id, prompt="lint_full")
        except AgentError as e:
            log_error(f"agent invocation failed; aborting: {e}")
            write_agent_failure(cfg, run_date, run_id)
            cleanup_worktree(cfg, run_id)
            commit_report(cfg, f"agent-failure {run_id}")
            raise

        # write_success is a no-op if the agent already wrote the lint report.
        write_success(
            cfg, run_date, "full-lint",
            processed="",
            unprocessed="",
            lint=f"(see 05_Archive/lint-reports/{run_date}-weekly.md from agent)",
            base_dir=cfg.workbench_dir,
        )

        merge_worktree(cfg, run_id)
        log_info("=== weekly-lint done ===")
        return 0

    except OrganizerError as e:
        sys.stderr.write(f"{type(e).__name__}: {e}\n")
        return e.exit_code
    finally:
        push_to_main(cfg)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
