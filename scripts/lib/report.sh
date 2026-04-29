#!/usr/bin/env bash
# Report writer. Source — do not execute directly.
set -euo pipefail

# Private dir var (don't shadow caller's SCRIPT_DIR when sourced from orchestrators).
__REPORT_LIB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "$__REPORT_LIB_DIR/common.sh"
unset __REPORT_LIB_DIR

# commit_report <message>
# Stage everything in $VAULT_DIR and commit with the auto-organizer identity.
# No-op if the working tree is clean. Used to land report files (success,
# skipped, agent-failure, conflict) that are written outside the worktree.
commit_report() {
    local message="$1"
    if [ -n "$(git -C "$VAULT_DIR" status --porcelain)" ]; then
        git -C "$VAULT_DIR" add -A
        git -C "$VAULT_DIR" \
            -c user.email="auto-organizer@local" \
            -c user.name="auto-organizer" \
            commit -q -m "$message $(date '+%H:%M')"
    fi
}

# Reports are written under ${REPORT_BASE_DIR:-$VAULT_DIR}. Orchestrators set
# REPORT_BASE_DIR=$WORKBENCH_DIR for the success path so the report lands inside
# the worktree and is squash-merged into main as a single commit.

# write_skipped_report <date> <reason>
write_skipped_report() {
    local date="$1" reason="$2"
    local out="${REPORT_BASE_DIR:-$VAULT_DIR}/05_Archive/daily-reports/${date}-SKIPPED.md"
    cat > "$out" <<EOF
---
type: daily-report
date: ${date}
mode: skipped
result: skipped
---

# Daily Report ${date} — SKIPPED

Reason: ${reason}

The next scheduled run will retry.
EOF
}

# write_conflict_report <date> <branch> <conflict-files-newline-list>
write_conflict_report() {
    local date="$1" branch="$2" files="$3"
    local out="${REPORT_BASE_DIR:-$VAULT_DIR}/05_Archive/daily-reports/${date}-CONFLICT.md"
    cat > "$out" <<EOF
---
type: daily-report
date: ${date}
mode: conflict
result: conflict
branch: ${branch}
---

# Daily Report ${date} — CONFLICT

The agent's branch \`${branch}\` could not be merged cleanly into \`main\`.
The merge has been aborted; main is unchanged.

## Conflicting files
\`\`\`
${files}
\`\`\`

## Recovery
1. Inspect the workbench (if not yet cleaned up): \`~/Workspace/vault-workbench/\`
2. Either resolve manually and \`git merge --continue\`, or discard with \`git branch -D ${branch}\`.
EOF
}

# write_agent_failure_report <date> <run-id>
write_agent_failure_report() {
    local date="$1" run_id="$2"
    local out="${REPORT_BASE_DIR:-$VAULT_DIR}/05_Archive/daily-reports/${date}-AGENT-FAILURE.md"
    cat > "$out" <<EOF
---
type: daily-report
date: ${date}
mode: agent-failure
result: agent-failure
run_id: ${run_id}
---

# Daily Report ${date} — AGENT FAILURE

The \`claude\` CLI exited non-zero during run \`${run_id}\`. Main is unchanged.

## Diagnostics
- launchd stdout: \`~/Library/Logs/vault-organizer-{ingest,lint}.log\`
- launchd stderr: \`~/Library/Logs/vault-organizer-{ingest,lint}.err\`

The next scheduled run will retry from a clean slate.
EOF
}

# write_success_report <date> <mode> <processed-block> <unprocessed-block> <lint-block>
# mode ∈ ingest+light-lint | full-lint
write_success_report() {
    local date="$1" mode="$2" processed="$3" unprocessed="$4" lint="$5"
    local base="${REPORT_BASE_DIR:-$VAULT_DIR}"
    local out
    if [ "$mode" = "full-lint" ]; then
        out="$base/05_Archive/lint-reports/${date}-weekly.md"
    else
        out="$base/05_Archive/daily-reports/${date}.md"
    fi
    # Defer to the agent only if it actively wrote the file in this run
    # (dirty in git status). A committed copy inherited from a prior run is
    # clean → overwrite it so each run records its own outcome.
    local out_rel="${out#"$base/"}"
    if [ -n "$(git -C "$base" status --porcelain -- "$out_rel" 2>/dev/null)" ]; then
        log_info "report already written by agent: $out — leaving as-is"
        return 0
    fi
    cat > "$out" <<EOF
---
type: daily-report
date: ${date}
mode: ${mode}
result: success
---

# Daily Report ${date}

## Processed
${processed}

## Unprocessed
${unprocessed}

## Lint
${lint}

## Conflict / errors
(none)
EOF
}
