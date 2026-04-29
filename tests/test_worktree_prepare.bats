#!/usr/bin/env bats
load 'helpers'

setup() {
    VAULT="$(make_synthetic_vault)"
    WB="$(make_workbench_dir)"; rm -rf "$WB"   # parent dir must exist; worktree path itself must NOT
    export VAULT_DIR="$VAULT"
    export WORKBENCH_DIR="$WB"
}
teardown() {
    (cd "$VAULT" && git worktree remove --force "$WB" 2>/dev/null) || true
    rm -rf "$VAULT" "$WB"
}

@test "prepare creates a worktree on a new branch named after run-id" {
    echo dirty > "$VAULT/02_Ideas/wip.md"
    run bash "$REPO_ROOT/scripts/lib/worktree-prepare.sh" daily-2026-04-28
    assert_success
    [ -d "$WB/.git" ] || [ -f "$WB/.git" ]
    run git -C "$WB" rev-parse --abbrev-ref HEAD
    assert_output "daily-2026-04-28"
    # Snapshot commit was made on main.
    run git -C "$VAULT" log --oneline -1
    assert_output --partial "snapshot before daily-2026-04-28"
}

@test "prepare is a no-op snapshot when working tree is clean" {
    run bash "$REPO_ROOT/scripts/lib/worktree-prepare.sh" daily-2026-04-28
    assert_success
    # No 'snapshot before' commit since there was nothing to commit.
    run git -C "$VAULT" log --oneline -1
    refute_output --partial "snapshot before"
}

@test "prepare cleans up a stale workbench dir" {
    mkdir -p "$WB"
    echo stale > "$WB/leftover"
    run bash "$REPO_ROOT/scripts/lib/worktree-prepare.sh" daily-2026-04-28
    assert_success
    [ ! -f "$WB/leftover" ]
}
