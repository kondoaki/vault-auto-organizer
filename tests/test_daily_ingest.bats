#!/usr/bin/env bats
load 'helpers'

setup() {
    VAULT="$(make_synthetic_vault)"
    WB="$(make_workbench_dir)"; rm -rf "$WB"
    export VAULT_DIR="$VAULT"
    export WORKBENCH_DIR="$WB"
    export CLAUDE_BIN="$REPO_ROOT/tests/fixtures/claude-mock/claude"
    export AGENT_BACKEND_FILE="$REPO_ROOT/scripts/lib/agent-backends/claude.sh"

    # mtime is aged so the --check-recent guard (when used) does not fire.
    echo "draft" > "$VAULT/00_Inbox/draft-1.md"
    git -C "$VAULT" add -A && git -C "$VAULT" -c user.email=t@t -c user.name=t commit -q -m seed
    find "$VAULT" -mindepth 1 -not -path "*/.git/*" -exec touch -t 202001010000 {} \; 2>/dev/null || true
}
teardown() {
    (cd "$VAULT" && git worktree remove --force "$WB" 2>/dev/null) || true
    rm -rf "$VAULT" "$WB"
}

@test "daily-ingest end-to-end happy path" {
    CLAUDE_MOCK_MODE=move-inbox-file run bash "$REPO_ROOT/scripts/daily-ingest.sh"
    assert_success
    # Inbox file moved to Archive on main.
    [ ! -f "$VAULT/00_Inbox/draft-1.md" ]
    [ -f "$VAULT/05_Archive/draft-1.md" ]
    # Workbench cleaned up.
    [ ! -d "$WB" ]
    # Daily report written.
    local today; today=$(date '+%Y-%m-%d')
    [ -f "$VAULT/05_Archive/daily-reports/${today}.md" ]
    # Working tree is clean — report was committed, not left dangling.
    [ -z "$(git -C "$VAULT" status --porcelain)" ]
}

@test "daily-ingest with --check-recent skips when vault was just edited" {
    # Touch a file to mimic recent edit.
    touch "$VAULT/02_Ideas/just-now.md"
    run bash "$REPO_ROOT/scripts/daily-ingest.sh" --check-recent
    assert_success
    local today; today=$(date '+%Y-%m-%d')
    [ -f "$VAULT/05_Archive/daily-reports/${today}-SKIPPED.md" ]
    # Worktree was never created.
    [ ! -d "$WB" ]
    # SKIPPED report was committed (now in HEAD).
    run git -C "$VAULT" log --oneline --name-only HEAD
    assert_output --partial "05_Archive/daily-reports/${today}-SKIPPED.md"
    # The triggering edit is intentionally left untracked: commit_report
    # narrows its add scope to orchestrator-managed paths so iCloud sync
    # locks on user-edited notes don't race with the commit. The next
    # non-skipped run picks it up via worktree-prepare's snapshot.
    run git -C "$VAULT" status --porcelain
    assert_output --partial "02_Ideas/just-now.md"
}

@test "daily-ingest without flag forces run even with recent edits" {
    # Without --check-recent the run must proceed regardless of recent edits.
    touch "$VAULT/02_Ideas/just-now.md"
    CLAUDE_MOCK_MODE=move-inbox-file run bash "$REPO_ROOT/scripts/daily-ingest.sh"
    assert_success
    local today; today=$(date '+%Y-%m-%d')
    [ ! -f "$VAULT/05_Archive/daily-reports/${today}-SKIPPED.md" ]
    [ -f "$VAULT/05_Archive/daily-reports/${today}.md" ]
}

@test "daily-ingest pushes to upstream when one is configured" {
    # Wire up a bare repo as origin and set main to track it.
    local remote; remote="$(mktemp -d)/origin.git"
    git init --bare -q "$remote"
    git -C "$VAULT" remote add origin "$remote"
    git -C "$VAULT" push -q -u origin main

    CLAUDE_MOCK_MODE=move-inbox-file run bash "$REPO_ROOT/scripts/daily-ingest.sh"
    assert_success
    # Local and remote main now point at the same commit.
    local local_head remote_head
    local_head=$(git -C "$VAULT" rev-parse main)
    remote_head=$(git -C "$remote" rev-parse main)
    [ "$local_head" = "$remote_head" ]
    rm -rf "$(dirname "$remote")"
}
