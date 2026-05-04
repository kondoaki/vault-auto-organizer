# Common helpers. Source this from every orchestration script:
#   SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
#   source "$SCRIPT_DIR/lib/common.sh"
#
# Tests may pre-set VAULT_DIR / WORKBENCH_DIR (and the backend's *_BIN var) to
# skip config.sh.

set -euo pipefail

LIB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# If env vars aren't already provided (e.g. by tests), source config.sh.
if [ -z "${VAULT_DIR:-}" ] || [ -z "${WORKBENCH_DIR:-}" ]; then
    if [ -f "$LIB_DIR/config.sh" ]; then
        # shellcheck disable=SC1091
        source "$LIB_DIR/config.sh"
    else
        echo "ERROR: $LIB_DIR/config.sh not found. Run install.sh first." >&2
        exit 1
    fi
fi

# Strip trailing slashes — `find -path "$VAULT_DIR/.git"` breaks on a doubled slash.
VAULT_DIR="${VAULT_DIR%/}"
WORKBENCH_DIR="${WORKBENCH_DIR%/}"

log_info()  { printf '[%s] INFO  %s\n'  "$(date '+%Y-%m-%d %H:%M:%S')" "$*" >&2; }
log_error() { printf '[%s] ERROR %s\n'  "$(date '+%Y-%m-%d %H:%M:%S')" "$*" >&2; }
die()       { log_error "$*"; exit 1; }

current_iso_date()    { date '+%Y-%m-%d'; }
current_iso_minute()  { date '+%Y-%m-%d %H:%M'; }
current_month_prefix() { date '+%Y-%m'; }

# generate_run_id <kind>  → e.g. daily-2026-04-28 / lint-full-2026-04-28
generate_run_id() {
    local kind="$1"
    printf '%s-%s\n' "$kind" "$(current_iso_date)"
}

# sync_with_origin — best-effort fast pull of origin/main into local main
# before any pre-batch commits. iCloud sync excludes $VAULT_DIR/.git, so
# commits made on another device only reach this device through origin —
# without this, the snapshot in worktree-prepare.sh stacks on stale local
# history and the subsequent push diverges.
#
# Network-related failures (no remote, fetch error, missing origin/main)
# are best-effort: logged and skipped so an offline run still proceeds.
# --ff-only is deliberate — it preserves unpushed local commits from a
# previous run. True divergence (local and origin both moved from the
# common ancestor) is fatal: continuing would add commits on top of
# diverged state and the trailing push would be rejected anyway, so we
# stop now and let a human rebase/merge before the next run.
sync_with_origin() {
    if ! git -C "$VAULT_DIR" remote get-url origin >/dev/null 2>&1; then
        log_info "no origin remote configured; skipping pre-run sync"
        return 0
    fi
    if ! git -C "$VAULT_DIR" fetch origin >&2; then
        log_error "git fetch origin failed; proceeding with local state"
        return 0
    fi
    if ! git -C "$VAULT_DIR" rev-parse --verify origin/main >/dev/null 2>&1; then
        log_info "origin/main not found after fetch; skipping merge"
        return 0
    fi
    if ! git -C "$VAULT_DIR" merge --ff-only origin/main >&2; then
        die "ff-only merge from origin/main failed: local main has diverged from origin/main. Resolve manually (rebase or merge) before the next run."
    fi
    log_info "synced local main to origin/main (ff-only)"
}

# push_to_main — best-effort push of $VAULT_DIR's current branch.
# - Returns 0 if no upstream is configured (push is silently skipped).
# - Returns 0 on push success.
# - Logs an error on push failure but still returns 0 so the orchestrator's
#   exit code reflects the run's outcome, not the push attempt.
push_to_main() {
    local upstream
    if ! upstream=$(git -C "$VAULT_DIR" rev-parse --abbrev-ref --symbolic-full-name '@{u}' 2>/dev/null); then
        log_info "no upstream configured; skipping push"
        return 0
    fi
    log_info "pushing to $upstream"
    if git -C "$VAULT_DIR" push >&2; then
        log_info "push complete"
    else
        log_error "git push to $upstream failed (local commits retained)"
    fi
    return 0
}
