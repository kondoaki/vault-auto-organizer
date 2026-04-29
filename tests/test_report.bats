#!/usr/bin/env bats
load 'helpers'

setup() {
    VAULT="$(make_synthetic_vault)"
    export VAULT_DIR="$VAULT"
    export WORKBENCH_DIR="/tmp/unused"
}
teardown() { rm -rf "$VAULT"; }

@test "write_skipped_report writes correct frontmatter and reason" {
    bash -c '
      source "'"$REPO_ROOT"'/scripts/lib/report.sh"
      write_skipped_report 2026-04-28 "vault edited within last 5 minutes"
    '
    [ -f "$VAULT/05_Archive/daily-reports/2026-04-28-SKIPPED.md" ]
    run cat "$VAULT/05_Archive/daily-reports/2026-04-28-SKIPPED.md"
    assert_output --partial "type: daily-report"
    assert_output --partial "result: skipped"
    assert_output --partial "vault edited within last 5 minutes"
}

@test "write_conflict_report writes branch and conflict-file list" {
    bash -c '
      source "'"$REPO_ROOT"'/scripts/lib/report.sh"
      write_conflict_report 2026-04-28 daily-2026-04-28 "02_Ideas/foo.md
01_Projects/bar.md"
    '
    run cat "$VAULT/05_Archive/daily-reports/2026-04-28-CONFLICT.md"
    assert_output --partial "result: conflict"
    assert_output --partial "branch: daily-2026-04-28"
    assert_output --partial "02_Ideas/foo.md"
    assert_output --partial "01_Projects/bar.md"
}

@test "write_success_report ingest mode writes to daily-reports/" {
    bash -c '
      source "'"$REPO_ROOT"'/scripts/lib/report.sh"
      write_success_report 2026-04-28 "ingest+light-lint" \
        "- foo" "(none)" "L1: 0 issues"
    '
    [ -f "$VAULT/05_Archive/daily-reports/2026-04-28.md" ]
}

@test "write_success_report full-lint mode writes to lint-reports/" {
    bash -c '
      source "'"$REPO_ROOT"'/scripts/lib/report.sh"
      write_success_report 2026-04-28 "full-lint" "" "" "L1: 3 fixed"
    '
    [ -f "$VAULT/05_Archive/lint-reports/2026-04-28-weekly.md" ]
}

@test "write_agent_failure_report writes the AGENT-FAILURE report" {
    bash -c '
      source "'"$REPO_ROOT"'/scripts/lib/report.sh"
      write_agent_failure_report 2026-04-28 daily-2026-04-28
    '
    [ -f "$VAULT/05_Archive/daily-reports/2026-04-28-AGENT-FAILURE.md" ]
    run cat "$VAULT/05_Archive/daily-reports/2026-04-28-AGENT-FAILURE.md"
    assert_output --partial "result: agent-failure"
    assert_output --partial "vault-organizer-{ingest,lint}.err"
}

@test "write_success_report does not clobber an existing report" {
    bash -c '
      source "'"$REPO_ROOT"'/scripts/lib/report.sh"
      printf "AGENT REPORT\n" > "'"$VAULT"'/05_Archive/daily-reports/2026-04-28.md"
      write_success_report 2026-04-28 "ingest+light-lint" "stub" "stub" "stub"
    '
    run cat "$VAULT/05_Archive/daily-reports/2026-04-28.md"
    assert_output "AGENT REPORT"
}
