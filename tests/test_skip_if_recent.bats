#!/usr/bin/env bats
load 'helpers'

setup() {
    VAULT="$(make_synthetic_vault)"
    export VAULT_DIR="$VAULT"
    export WORKBENCH_DIR="/tmp/unused"
}

teardown() {
    rm -rf "$VAULT"
}

@test "skip-if-recent returns 1 when no recent edits" {
    # Age every file in the vault, then create one explicitly old file.
    find "$VAULT" -mindepth 1 -exec touch -t 202001010000 {} \; 2>/dev/null || true
    echo "old" > "$VAULT/02_Ideas/old.md"
    touch -t 202001010000 "$VAULT/02_Ideas/old.md"
    run bash "$REPO_ROOT/scripts/lib/skip-if-recent.sh"
    assert_failure
}

@test "skip-if-recent returns 0 when a vault file was touched recently" {
    echo "fresh" > "$VAULT/02_Ideas/fresh.md"
    run bash "$REPO_ROOT/scripts/lib/skip-if-recent.sh"
    assert_success
}

@test "skip-if-recent ignores recent changes inside .git/" {
    mkdir -p "$VAULT/.git/objects"
    echo "x" > "$VAULT/.git/objects/blob"
    # Make sure no other file is recent.
    find "$VAULT" -mindepth 1 -not -path "*/.git/*" -exec touch -t 202001010000 {} \; 2>/dev/null || true
    run bash "$REPO_ROOT/scripts/lib/skip-if-recent.sh"
    assert_failure
}

@test "skip-if-recent ignores recent changes inside 05_Archive/" {
    echo "report" > "$VAULT/05_Archive/daily-reports/2026-04-27.md"
    find "$VAULT" -mindepth 1 -not -path "*/.git/*" -not -path "*/05_Archive/*" \
        -exec touch -t 202001010000 {} \; 2>/dev/null || true
    run bash "$REPO_ROOT/scripts/lib/skip-if-recent.sh"
    assert_failure
}

@test "skip-if-recent ignores recent changes inside scripts/" {
    mkdir -p "$VAULT/scripts/lib"
    echo "deploy" > "$VAULT/scripts/lib/foo.sh"
    find "$VAULT" -mindepth 1 -not -path "*/.git/*" -not -path "*/scripts/*" \
        -exec touch -t 202001010000 {} \; 2>/dev/null || true
    run bash "$REPO_ROOT/scripts/lib/skip-if-recent.sh"
    assert_failure
}

@test "skip-if-recent honors trailing slash in VAULT_DIR" {
    find "$VAULT" -mindepth 1 -exec touch -t 202001010000 {} \; 2>/dev/null || true
    echo "x" > "$VAULT/.git/recent-edit"
    VAULT_DIR="$VAULT/" run bash "$REPO_ROOT/scripts/lib/skip-if-recent.sh"
    assert_failure
}
