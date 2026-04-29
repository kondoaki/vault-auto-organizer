#!/usr/bin/env bats
load 'helpers'

setup() {
    VAULT="$(make_synthetic_vault)"
    WB="$(make_workbench_dir)"; rm -rf "$WB"
    export VAULT_DIR="$VAULT"
    export WORKBENCH_DIR="$WB"
    bash "$REPO_ROOT/scripts/lib/worktree-prepare.sh" daily-2026-04-28
    echo "hello" > "$WB/00_Inbox/note-1.md"
    cat > "$WB/_prompt.md" <<'EOF'
Run id: $RUN_ID. Date: $RUN_DATE. Move one inbox file to Archive.
EOF
}
teardown() {
    (cd "$VAULT" && git worktree remove --force "$WB" 2>/dev/null) || true
    rm -rf "$VAULT" "$WB"
}

# ── claude backend ────────────────────────────────────────────────────────────

@test "claude backend: renders prompt and runs against the workbench" {
    export CLAUDE_BIN="$REPO_ROOT/tests/fixtures/claude-mock/claude"
    export AGENT_BACKEND_FILE="$REPO_ROOT/scripts/lib/agent-backends/claude.sh"
    CLAUDE_MOCK_MODE=move-inbox-file run bash "$REPO_ROOT/scripts/lib/invoke-agent.sh" \
        daily-2026-04-28 "$WB/_prompt.md"
    assert_success
    [ -f "$WB/05_Archive/note-1.md" ]
    [ ! -f "$WB/00_Inbox/note-1.md" ]
}

@test "claude backend: exits non-zero when the agent fails" {
    export CLAUDE_BIN="$REPO_ROOT/tests/fixtures/claude-mock/claude"
    export AGENT_BACKEND_FILE="$REPO_ROOT/scripts/lib/agent-backends/claude.sh"
    CLAUDE_MOCK_MODE=fail run bash "$REPO_ROOT/scripts/lib/invoke-agent.sh" \
        daily-2026-04-28 "$WB/_prompt.md"
    assert_failure
}

@test "claude mock rejects invocation with wrong --allowedTools" {
    export CLAUDE_BIN="$REPO_ROOT/tests/fixtures/claude-mock/claude"
    run "$CLAUDE_BIN" -p "x" --allowedTools "Bash,WebFetch,Read" --add-dir "$WB"
    assert_failure
    assert_output --partial "MOCK FAILURE"
}

# ── opencode backend ──────────────────────────────────────────────────────────

@test "opencode backend: renders prompt and runs against the workbench" {
    export OPENCODE_BIN="$REPO_ROOT/tests/fixtures/opencode-mock/opencode"
    export AGENT_BACKEND_FILE="$REPO_ROOT/scripts/lib/agent-backends/opencode.sh"
    OPENCODE_MOCK_MODE=move-inbox-file run bash "$REPO_ROOT/scripts/lib/invoke-agent.sh" \
        daily-2026-04-28 "$WB/_prompt.md"
    assert_success
    [ -f "$WB/05_Archive/note-1.md" ]
    [ ! -f "$WB/00_Inbox/note-1.md" ]
}

@test "opencode backend: exits non-zero when the agent fails" {
    export OPENCODE_BIN="$REPO_ROOT/tests/fixtures/opencode-mock/opencode"
    export AGENT_BACKEND_FILE="$REPO_ROOT/scripts/lib/agent-backends/opencode.sh"
    OPENCODE_MOCK_MODE=fail run bash "$REPO_ROOT/scripts/lib/invoke-agent.sh" \
        daily-2026-04-28 "$WB/_prompt.md"
    assert_failure
}

@test "opencode mock rejects invocation when OPENCODE_CONFIG_DIR points at a permissive config" {
    export OPENCODE_BIN="$REPO_ROOT/tests/fixtures/opencode-mock/opencode"
    bad_cfg="$(mktemp -d)"
    cat > "$bad_cfg/opencode.json" <<'EOF'
{ "permission": { "edit": "allow", "webfetch": "allow", "bash": "allow" } }
EOF
    OPENCODE_CONFIG_DIR="$bad_cfg" run "$OPENCODE_BIN" run "x" --dangerously-skip-permissions
    assert_failure
    assert_output --partial "MOCK FAILURE"
    rm -rf "$bad_cfg"
}

# ── backend selection ─────────────────────────────────────────────────────────

@test "invoke-agent fails fast when multiple backends are present and AGENT_BACKEND_FILE is unset" {
    # The repo carries both backends side-by-side; without AGENT_BACKEND_FILE the
    # glob in invoke-agent.sh sees >1 file and must error.
    export CLAUDE_BIN="$REPO_ROOT/tests/fixtures/claude-mock/claude"
    unset AGENT_BACKEND_FILE
    run bash "$REPO_ROOT/scripts/lib/invoke-agent.sh" \
        daily-2026-04-28 "$WB/_prompt.md"
    assert_failure
    assert_output --partial "expected exactly one agent backend"
}
