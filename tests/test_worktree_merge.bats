#!/usr/bin/env bats
load 'helpers'

setup() {
    VAULT="$(make_synthetic_vault)"
    WB="$(make_workbench_dir)"; rm -rf "$WB"
    export VAULT_DIR="$VAULT"
    export WORKBENCH_DIR="$WB"
    bash "$REPO_ROOT/scripts/lib/worktree-prepare.sh" daily-2026-04-28
}
teardown() {
    (cd "$VAULT" && git worktree remove --force "$WB" 2>/dev/null) || true
    rm -rf "$VAULT" "$WB"
}

@test "merge is a noop when agent made no changes" {
    run bash "$REPO_ROOT/scripts/lib/worktree-merge.sh" daily-2026-04-28
    assert_success
    assert_output --partial "noop"
    [ ! -d "$WB" ]
    run git -C "$VAULT" branch --list daily-2026-04-28
    assert_output ""
}

@test "merge squashes agent commits into a single commit on main" {
    echo "new" > "$WB/02_Ideas/created-by-agent.md"
    run bash "$REPO_ROOT/scripts/lib/worktree-merge.sh" daily-2026-04-28
    assert_success
    assert_output --partial "success"
    [ -f "$VAULT/02_Ideas/created-by-agent.md" ]
    # Squash → single commit on main, no separate merge commit.
    run git -C "$VAULT" log --oneline -1
    assert_output --partial "daily-2026-04-28"
    run git -C "$VAULT" log --merges --oneline
    assert_output ""
}

@test "merge aborts on conflict, writes CONFLICT report, leaves main clean" {
    # Concurrent edit on main that conflicts with workbench.
    echo "agent version" > "$WB/02_Ideas/clash.md"
    git -C "$WB" add -A
    git -C "$WB" -c user.email=t@t -c user.name=t commit -m "agent edit"

    echo "user version" > "$VAULT/02_Ideas/clash.md"
    git -C "$VAULT" add -A
    git -C "$VAULT" -c user.email=t@t -c user.name=t commit -m "user edit"

    run bash "$REPO_ROOT/scripts/lib/worktree-merge.sh" daily-2026-04-28
    assert_failure
    assert_output --partial "conflict"
    [ -f "$VAULT/05_Archive/daily-reports/$(date '+%Y-%m-%d')-CONFLICT.md" ]
    # main should NOT have a merge commit.
    run git -C "$VAULT" status --porcelain
    assert_output ""
    run cat "$VAULT/02_Ideas/clash.md"
    assert_output "user version"
}
