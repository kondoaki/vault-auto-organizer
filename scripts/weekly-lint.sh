#!/usr/bin/env bash
# weekly-lint.sh [--check-recent] — orchestrates the Sunday 03:30 run.
#   --check-recent  Skip the run if the Vault was edited within the last 5 min.
#                   launchd passes this flag; manual invocations omit it to
#                   force a run.
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

run_id="$(generate_run_id lint-full)"
date="$(current_iso_date)"

# Push any commits this run produced to the configured remote on exit.
# Best-effort: failures are logged but don't change exit code.
trap 'push_to_main' EXIT

log_info "=== weekly-lint start (run_id=$run_id) ==="

rotate_log_if_needed

if [ "$CHECK_RECENT" -eq 1 ] && bash "$SCRIPT_DIR/lib/skip-if-recent.sh"; then
    log_info "vault has recent edits — skipping"
    write_skipped_report "$date" "vault edited within last 5 minutes"
    commit_report "skipped $run_id"
    exit 0
fi

bash "$SCRIPT_DIR/lib/worktree-prepare.sh" "$run_id"

if ! bash "$SCRIPT_DIR/lib/invoke-agent.sh" "$run_id" \
        "$SCRIPT_DIR/lib/prompts/lint-full.md"; then
    log_error "agent invocation failed; aborting"
    write_agent_failure_report "$date" "$run_id"
    (cd "$VAULT_DIR" && git worktree remove --force "$WORKBENCH_DIR" 2>/dev/null) || true
    git -C "$VAULT_DIR" branch -D "$run_id" 2>/dev/null || true
    commit_report "agent-failure $run_id"
    exit 1
fi

# Write the success report INTO the worktree so it gets squash-merged together
# with the agent's changes as a single commit on main. (No-op if the agent
# already wrote one inside the worktree.)
REPORT_BASE_DIR="$WORKBENCH_DIR" \
    write_success_report "$date" "full-lint" "" "" \
        "(see 05_Archive/lint-reports/${date}-weekly.md from agent)"

# Capture worktree-merge.sh output; last line is the status keyword.
_merge_out=$(bash "$SCRIPT_DIR/lib/worktree-merge.sh" "$run_id" || true)
merge_result=$(printf '%s' "$_merge_out" | tail -n1)

case "$merge_result" in
    success|noop)
        log_info "=== weekly-lint done ==="
        ;;
    conflict)
        log_error "merge conflict — see 05_Archive/daily-reports/${date}-CONFLICT.md"
        exit 1
        ;;
    *)
        die "unexpected merge result: $merge_result"
        ;;
esac
