#!/usr/bin/env bash
# daily-ingest.sh [--check-recent] — orchestrates the 03:00 run.
#   --check-recent  Skip the run if the Vault was edited within the last 5 min.
#                   launchd passes this flag; manual invocations omit it to
#                   force a run.
# Steps:
# 1. rotate log if month boundary
# 2. (if --check-recent) skip-if-recent → SKIPPED report and exit
# 3. worktree-prepare
# 4. invoke agent with prompts/ingest.md
# 5. worktree-merge
# 6. write success report
set -euo pipefail

CHECK_RECENT=0
[ "${1:-}" = "--check-recent" ] && CHECK_RECENT=1

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "$SCRIPT_DIR/lib/common.sh"
# shellcheck disable=SC1091
source "$SCRIPT_DIR/lib/log.sh"
# shellcheck disable=SC1091
source "$SCRIPT_DIR/lib/report.sh"

run_id="$(generate_run_id daily)"
date="$(current_iso_date)"

# Push any commits this run produced (success, skipped, agent-failure, or
# conflict) to the configured remote on exit. Best-effort: failures are logged
# but don't change the orchestrator's exit code.
trap 'push_to_main' EXIT

log_info "=== daily-ingest start (run_id=$run_id) ==="

rotate_log_if_needed

# Align local main with origin/main before any commits this run might add
# (snapshot, skipped report, agent merge). .git is no longer iCloud-synced.
sync_with_origin

if [ "$CHECK_RECENT" -eq 1 ] && bash "$SCRIPT_DIR/lib/skip-if-recent.sh"; then
    log_info "vault has recent edits — skipping"
    write_skipped_report "$date" "vault edited within last 5 minutes"
    commit_report "skipped $run_id"
    exit 0
fi

bash "$SCRIPT_DIR/lib/worktree-prepare.sh" "$run_id"

if ! bash "$SCRIPT_DIR/lib/invoke-agent.sh" "$run_id" \
        "$SCRIPT_DIR/lib/prompts/ingest.md"; then
    log_error "agent invocation failed; aborting"
    write_agent_failure_report "$date" "$run_id"
    (cd "$VAULT_DIR" && git worktree remove --force "$WORKBENCH_DIR" 2>/dev/null) || true
    git -C "$VAULT_DIR" branch -D "$run_id" 2>/dev/null || true
    commit_report "agent-failure $run_id"
    exit 1
fi

# Write the success report INTO the worktree so it gets squash-merged together
# with the agent's changes as a single commit on main.
REPORT_BASE_DIR="$WORKBENCH_DIR" \
    write_success_report "$date" "ingest+light-lint" \
        "(see log.md for per-file detail)" \
        "(none)" \
        "(see log.md)"

# Capture worktree-merge.sh output; last line is the status keyword.
_merge_out=$(bash "$SCRIPT_DIR/lib/worktree-merge.sh" "$run_id" || true)
merge_result=$(printf '%s' "$_merge_out" | tail -n1)

case "$merge_result" in
    success|noop)
        log_info "=== daily-ingest done ==="
        ;;
    conflict)
        log_error "merge conflict — see 05_Archive/daily-reports/${date}-CONFLICT.md"
        exit 1
        ;;
    *)
        die "unexpected merge result: $merge_result"
        ;;
esac
