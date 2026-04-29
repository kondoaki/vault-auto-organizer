#!/usr/bin/env bash
# worktree-prepare.sh <run-id>
# 1. snapshot any uncommitted changes in $VAULT_DIR
# 2. blow away any stale $WORKBENCH_DIR
# 3. add a fresh worktree at $WORKBENCH_DIR on branch <run-id>
set -euo pipefail

__WT_PREP_LIB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "$__WT_PREP_LIB_DIR/common.sh"
unset __WT_PREP_LIB_DIR

run_id="${1:?usage: worktree-prepare.sh <run-id>}"

[ -d "$VAULT_DIR/.git" ] || die "VAULT_DIR is not a git repo: $VAULT_DIR"

cd "$VAULT_DIR"

current_branch=$(git rev-parse --abbrev-ref HEAD)
[ "$current_branch" = "main" ] || die "expected main branch, got: $current_branch"

# 1. Snapshot. `git diff --quiet` returns 1 when there are unstaged changes;
#    we also need to check the index. -A captures both new and deleted files.
if ! git diff --quiet || ! git diff --cached --quiet || [ -n "$(git status --porcelain)" ]; then
    git add -A
    git -c user.email="auto-organizer@local" -c user.name="auto-organizer" \
        commit -m "snapshot before $run_id $(date '+%H:%M')"
    log_info "committed pre-batch snapshot"
fi

# 2. Stale workbench cleanup. Try worktree remove first (cleaner), then rm.
if [ -e "$WORKBENCH_DIR" ]; then
    log_info "removing stale workbench at $WORKBENCH_DIR"
    git worktree remove --force "$WORKBENCH_DIR" 2>/dev/null || true
    rm -rf "$WORKBENCH_DIR"
fi

# Also delete a stale branch with the same name, if any.
git branch -D "$run_id" 2>/dev/null || true

# 3. Create the worktree.
mkdir -p "$(dirname "$WORKBENCH_DIR")"
git worktree add -b "$run_id" "$WORKBENCH_DIR"
log_info "worktree ready at $WORKBENCH_DIR on branch $run_id"
