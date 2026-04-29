#!/usr/bin/env bats
load 'helpers'

setup() {
    VAULT="$(make_synthetic_vault)"
    WB="$(make_workbench_dir)"; rm -rf "$WB"
    export VAULT_DIR="$VAULT"
    export WORKBENCH_DIR="$WB"
    export CLAUDE_BIN="$REPO_ROOT/tests/fixtures/claude-mock/claude"
    export AGENT_BACKEND_FILE="$REPO_ROOT/scripts/lib/agent-backends/claude.sh"
    find "$VAULT" -mindepth 1 -not -path "*/.git/*" -exec touch -t 202001010000 {} \; 2>/dev/null || true
}
teardown() {
    (cd "$VAULT" && git worktree remove --force "$WB" 2>/dev/null) || true
    rm -rf "$VAULT" "$WB"
}

@test "weekly-lint end-to-end happy path writes to lint-reports/" {
    CLAUDE_MOCK_MODE=noop run bash "$REPO_ROOT/scripts/weekly-lint.sh"
    assert_success
    local today; today=$(date '+%Y-%m-%d')
    [ -f "$VAULT/05_Archive/lint-reports/${today}-weekly.md" ]
    # Working tree is clean — report was committed, not left dangling.
    [ -z "$(git -C "$VAULT" status --porcelain)" ]
}
