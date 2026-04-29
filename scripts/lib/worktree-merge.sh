#!/usr/bin/env bash
# worktree-merge.sh <run-id>
# Commit any pending changes in the workbench, merge into main, clean up.
# Echoes one of: success | conflict | noop
set -euo pipefail

__WT_MERGE_LIB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "$__WT_MERGE_LIB_DIR/common.sh"
# shellcheck disable=SC1091
source "$__WT_MERGE_LIB_DIR/report.sh"
unset __WT_MERGE_LIB_DIR

run_id="${1:?usage: worktree-merge.sh <run-id>}"
date="$(current_iso_date)"

# Capture the Vault's current branch (caller's HEAD).
base_branch=$(git -C "$VAULT_DIR" rev-parse --abbrev-ref HEAD)
[ "$base_branch" = "HEAD" ] && die "VAULT_DIR is on a detached HEAD; refuse to merge"

cleanup() {
    (cd "$VAULT_DIR" && git worktree remove --force "$WORKBENCH_DIR" 2>/dev/null) || true
    rm -rf "$WORKBENCH_DIR"
    git -C "$VAULT_DIR" branch -D "$run_id" 2>/dev/null || true
}

# 1. Commit agent's changes inside the workbench (no-op if clean).
cd "$WORKBENCH_DIR"
if [ -n "$(git status --porcelain)" ]; then
    git add -A
    git -c user.email="auto-organizer@local" -c user.name="auto-organizer" \
        commit -m "$run_id $(date '+%H:%M')"
fi

# Check if the workbench branch has any commits ahead of the base branch.
ahead=$(git rev-list "${base_branch}..${run_id}" --count 2>/dev/null || echo 0)
if [ "$ahead" -eq 0 ]; then
    log_info "agent made no changes; cleaning up worktree"
    cleanup
    echo "noop"
    exit 0
fi

# 2. Squash-merge into main: agent changes + report land as one commit.
cd "$VAULT_DIR"
if git merge --squash "$run_id"; then
    git -c user.email="auto-organizer@local" -c user.name="auto-organizer" \
        commit -q -m "$run_id $(date '+%H:%M')"
    log_info "squashed $run_id into main"
    cleanup
    echo "success"
    exit 0
fi

# 3. Conflict path. --squash leaves the index conflicted but no MERGE_HEAD,
# so `git reset --merge` (not `merge --abort`) is the correct cleanup.
log_error "merge conflict — aborting"
conflicted=$(git diff --name-only --diff-filter=U)
git reset --merge
write_conflict_report "$date" "$run_id" "$conflicted"
commit_report "conflict report $run_id"

# Notify (best effort; do not fail the script if osascript is unavailable).
osascript -e "display notification \"Vault merge conflict on $run_id — see 05_Archive/daily-reports/${date}-CONFLICT.md\" with title \"Vault Auto-Organizer\"" 2>/dev/null || true

# Leave both the workbench AND the branch in place so the user can investigate.
echo "conflict"
exit 1
