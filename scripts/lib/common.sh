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
