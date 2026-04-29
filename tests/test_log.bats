#!/usr/bin/env bats
load 'helpers'

setup() {
    VAULT="$(make_synthetic_vault)"
    export VAULT_DIR="$VAULT"
    export WORKBENCH_DIR="/tmp/unused"
}
teardown() { rm -rf "$VAULT"; }

@test "append_log writes a properly-formatted block" {
    bash -c '
      source "'"$REPO_ROOT"'/scripts/lib/log.sh"
      append_log ingest "routed clip-1.md to Resources" \
        "00_Inbox/clip-1.md" "04_Resources/clip-1.md" "[[02_Ideas/foo]]" success
    '
    run cat "$VAULT/log.md"
    assert_success
    assert_output --partial "] ingest |"
    assert_output --partial "routed clip-1.md to Resources"
    assert_output --partial "- file: 00_Inbox/clip-1.md"
    assert_output --partial "- destination: 04_Resources/clip-1.md"
    assert_output --partial "- linked: [[02_Ideas/foo]]"
    assert_output --partial "- result: success"
}

@test "rotate_log_if_needed slices old months into 05_Archive/logs/" {
    cat > "$VAULT/log.md" <<EOF
## [2026-03-15 03:00] ingest | march entry
- result: success

## [2026-04-02 03:00] ingest | april entry
- result: success
EOF
    bash -c '
      source "'"$REPO_ROOT"'/scripts/lib/log.sh"
      rotate_log_if_needed
    '
    run grep -c "march entry" "$VAULT/log.md"
    assert_output "0"
    run grep -c "april entry" "$VAULT/log.md"
    assert_output "1"
    [ -f "$VAULT/05_Archive/logs/2026-03.md" ]
    run grep -c "march entry" "$VAULT/05_Archive/logs/2026-03.md"
    assert_output "1"
}

@test "rotate_log_if_needed is a no-op when log only has current month" {
    local month
    month="$(date '+%Y-%m')"
    cat > "$VAULT/log.md" <<EOF
## [${month}-01 03:00] ingest | this month
- result: success
EOF
    bash -c '
      source "'"$REPO_ROOT"'/scripts/lib/log.sh"
      rotate_log_if_needed
    '
    run grep -c "this month" "$VAULT/log.md"
    assert_output "1"
    run ls "$VAULT/05_Archive/logs/"
    refute_output --partial ".md"
}
