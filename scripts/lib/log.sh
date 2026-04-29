#!/usr/bin/env bash
# Append-only log helpers and monthly rotation.
# Source — do not execute directly.
set -euo pipefail

# Private dir var (don't shadow caller's SCRIPT_DIR when sourced from orchestrators).
__LOG_LIB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "$__LOG_LIB_DIR/common.sh"
unset __LOG_LIB_DIR

# append_log <action> <summary> <inbox-path> <destination> <linked-csv> <result>
# action ∈ ingest | lint-light | lint-full | merge
append_log() {
    local action="$1" summary="$2" file="$3" dest="$4" linked="$5" result="$6"
    local stamp
    stamp="$(current_iso_minute)"
    {
        printf '\n## [%s] %s | %s\n' "$stamp" "$action" "$summary"
        printf -- '- file: %s\n' "$file"
        printf -- '- destination: %s\n' "$dest"
        printf -- '- linked: %s\n' "$linked"
        printf -- '- result: %s\n' "$result"
    } >> "$VAULT_DIR/log.md"
}

# rotate_log_if_needed
# Splits log.md so that only entries dated in the current month remain.
# Older entries (grouped per YYYY-MM) are appended to 05_Archive/logs/YYYY-MM.md.
rotate_log_if_needed() {
    local log="$VAULT_DIR/log.md"
    [ -s "$log" ] || return 0
    local current; current="$(current_month_prefix)"

    local tmp; tmp="$(mktemp)"
    awk -v current="$current" -v archive_dir="$VAULT_DIR/05_Archive/logs" -v keep="$tmp" '
        BEGIN { mode="keep"; outfile="" }
        /^## \[/ {
            # Extract YYYY-MM from "## [YYYY-MM-DD ..."
            if (match($0, /\[[0-9]{4}-[0-9]{2}/)) {
                month = substr($0, RSTART+1, 7)
                if (month == current) {
                    mode = "keep"
                    outfile = keep
                } else {
                    mode = "archive"
                    outfile = archive_dir "/" month ".md"
                }
            }
        }
        { if (outfile != "") print >> outfile }
    ' "$log"

    # Replace log.md with the kept portion (may be empty).
    mv "$tmp" "$log"
    log_info "rotated log.md (kept current month: $current)"
}
