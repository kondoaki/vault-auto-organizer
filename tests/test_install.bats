#!/usr/bin/env bats
load 'helpers'

setup() {
    VAULT="$(mktemp -d)"
    HOME_FAKE="$(mktemp -d)"
    mkdir -p "$HOME_FAKE/Library/LaunchAgents"
    export FAKE_HOME="$HOME_FAKE"
}
teardown() { rm -rf "$VAULT" "$HOME_FAKE"; }

@test "install creates expected dirs, copies CLAUDE.md, renders config.sh" {
    HOME="$HOME_FAKE" run bash "$REPO_ROOT/install.sh" "$VAULT" --no-launchd-bootstrap
    assert_success
    [ -f "$VAULT/CLAUDE.md" ]
    [ -f "$VAULT/log.md" ]
    [ -f "$VAULT/03_Context/_routing-rules.md" ]
    [ -f "$VAULT/05_Archive/logs/.gitkeep" ]
    [ -f "$VAULT/05_Archive/daily-reports/.gitkeep" ]
    [ -f "$VAULT/05_Archive/lint-reports/.gitkeep" ]
    [ -f "$VAULT/05_Archive/orphans/.gitkeep" ]
    [ -f "$VAULT/03_Context/_pending-updates/.gitkeep" ]
    [ -f "$VAULT/scripts/daily-ingest.sh" ]
    [ -f "$VAULT/scripts/lib/config.sh" ]
    [ -f "$HOME_FAKE/Library/LaunchAgents/com.user.vault-organizer.ingest.plist" ]
    [ -f "$HOME_FAKE/Library/LaunchAgents/com.user.vault-organizer.lint.plist" ]
    grep -q "__VAULT_DIR__" "$VAULT/scripts/lib/config.sh" && return 1 || true   # placeholders must be substituted
    grep -q "$VAULT" "$VAULT/scripts/lib/config.sh"
    grep -q "$VAULT" "$HOME_FAKE/Library/LaunchAgents/com.user.vault-organizer.ingest.plist"
}

@test "install (default backend) ships only claude.sh under agent-backends/" {
    HOME="$HOME_FAKE" run bash "$REPO_ROOT/install.sh" "$VAULT" --no-launchd-bootstrap
    assert_success
    [ -f "$VAULT/scripts/lib/agent-backends/claude.sh" ]
    [ ! -e "$VAULT/scripts/lib/agent-backends/opencode.sh" ]
    [ ! -e "$VAULT/scripts/lib/agent-backends/opencode" ]
    grep -q '^export CLAUDE_BIN=' "$VAULT/scripts/lib/config.sh"
}

@test "install --backend opencode ships only opencode.sh + opencode/opencode.json" {
    HOME="$HOME_FAKE" run bash "$REPO_ROOT/install.sh" "$VAULT" --backend opencode --no-launchd-bootstrap
    assert_success
    [ -f "$VAULT/scripts/lib/agent-backends/opencode.sh" ]
    [ -f "$VAULT/scripts/lib/agent-backends/opencode/opencode.json" ]
    [ ! -e "$VAULT/scripts/lib/agent-backends/claude.sh" ]
    grep -q '^export OPENCODE_BIN=' "$VAULT/scripts/lib/config.sh"
}

@test "install switches backends cleanly on re-run" {
    HOME="$HOME_FAKE" run bash "$REPO_ROOT/install.sh" "$VAULT" --backend opencode --no-launchd-bootstrap
    assert_success
    [ -f "$VAULT/scripts/lib/agent-backends/opencode.sh" ]
    HOME="$HOME_FAKE" run bash "$REPO_ROOT/install.sh" "$VAULT" --backend claude --no-launchd-bootstrap
    assert_success
    [ -f "$VAULT/scripts/lib/agent-backends/claude.sh" ]
    [ ! -e "$VAULT/scripts/lib/agent-backends/opencode.sh" ]
    [ ! -e "$VAULT/scripts/lib/agent-backends/opencode" ]
}

@test "install rejects unknown --backend" {
    HOME="$HOME_FAKE" run bash "$REPO_ROOT/install.sh" "$VAULT" --backend gemini --no-launchd-bootstrap
    assert_failure
    assert_output --partial "--backend must be 'claude' or 'opencode'"
}

@test "install is idempotent — running twice does not duplicate Arrival Protocol" {
    HOME="$HOME_FAKE" run bash "$REPO_ROOT/install.sh" "$VAULT" --no-launchd-bootstrap
    assert_success
    HOME="$HOME_FAKE" run bash "$REPO_ROOT/install.sh" "$VAULT" --no-launchd-bootstrap
    assert_success
    run grep -c "## AI Arrival Protocol" "$VAULT/03_Context/MyContext.md"
    assert_output "1"
}

@test "install initializes git when target is not a repo" {
    HOME="$HOME_FAKE" run bash "$REPO_ROOT/install.sh" "$VAULT" --no-launchd-bootstrap
    assert_success
    [ -d "$VAULT/.git" ]
}

@test "install does not duplicate user sections in a populated MyContext.md" {
    mkdir -p "$VAULT/03_Context"
    cat > "$VAULT/03_Context/MyContext.md" <<'EOF'
## Active Projects
- [[01_Projects/foo]]

## Active Ideas
- [[02_Ideas/bar]]

## Self-info
- [[03_Context/Identity]]
EOF
    HOME="$HOME_FAKE" run bash "$REPO_ROOT/install.sh" "$VAULT" --no-launchd-bootstrap
    assert_success
    run grep -c "^## Active Projects$" "$VAULT/03_Context/MyContext.md"
    assert_output "1"
    run grep -c "^## Active Ideas$" "$VAULT/03_Context/MyContext.md"
    assert_output "1"
    run grep -c "^## Self-info$" "$VAULT/03_Context/MyContext.md"
    assert_output "1"
    run grep -c "^## AI Arrival Protocol$" "$VAULT/03_Context/MyContext.md"
    assert_output "1"
    grep -q "01_Projects/foo" "$VAULT/03_Context/MyContext.md"
    grep -q "02_Ideas/bar" "$VAULT/03_Context/MyContext.md"
}
