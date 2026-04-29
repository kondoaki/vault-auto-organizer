# Common test helpers. Source via:
#   load 'helpers'
# from any .bats file (assumes BATS_TEST_DIRNAME is tests/).

load 'lib/bats-support/load'
load 'lib/bats-assert/load'

# Repo root, resolved once.
REPO_ROOT="$(cd "${BATS_TEST_DIRNAME}/.." && pwd)"

# Create a synthetic Vault under a tempdir. Echoes the path.
# Layout matches what install.sh produces (minus scripts/, which the test
# adds explicitly when needed).
make_synthetic_vault() {
    local tmp
    tmp=$(mktemp -d "${BATS_TMPDIR:-/tmp}/vault-XXXXXX")
    mkdir -p "$tmp/00_Inbox" "$tmp/04_Resources" "$tmp/05_Archive/logs" \
             "$tmp/05_Archive/daily-reports" "$tmp/05_Archive/lint-reports" \
             "$tmp/05_Archive/orphans" "$tmp/01_Projects" "$tmp/02_Ideas" \
             "$tmp/03_Context/_pending-updates"
    : > "$tmp/log.md"
    : > "$tmp/CLAUDE.md"
    : > "$tmp/00_Inbox/.gitkeep"
    : > "$tmp/02_Ideas/.gitkeep"
    : > "$tmp/05_Archive/daily-reports/.gitkeep"
    : > "$tmp/05_Archive/lint-reports/.gitkeep"
    : > "$tmp/05_Archive/logs/.gitkeep"
    : > "$tmp/03_Context/MyContext.md"
    : > "$tmp/03_Context/_routing-rules.md"
    (cd "$tmp" && git init -q && git add -A && git -c user.email=t@t -c user.name=t commit -q -m init)
    echo "$tmp"
}

# Create a synthetic workbench dir (used by worktree tests).
make_workbench_dir() {
    mktemp -d "${BATS_TMPDIR:-/tmp}/wb-XXXXXX"
}

# Generate a deterministic run-id for tests.
test_run_id() {
    echo "daily-2026-04-28"
}

# Run a script under scripts/lib/ with VAULT_DIR/WORKBENCH_DIR stubbed in env.
# Usage: with_config "$vault" "$workbench" script-name.sh
with_config() {
    local vault="$1" wb="$2" script="$3"
    VAULT_DIR="$vault" WORKBENCH_DIR="$wb" bash "$REPO_ROOT/scripts/lib/$script"
}
