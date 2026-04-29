#!/usr/bin/env bash
# Exit 0 (true in `if`) means "recent edit found — skip the batch".
# Exit 1 (false in `if`) means "vault is quiet — proceed".
# Excludes .git, Archive, and scripts (they are not user-edited content).
set -euo pipefail

__SKIP_LIB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "$__SKIP_LIB_DIR/common.sh"
unset __SKIP_LIB_DIR

[ -d "$VAULT_DIR" ] || die "VAULT_DIR does not exist: $VAULT_DIR"

# -mmin -5 : modified less than 5 minutes ago.
# Excluded paths: .git (internal), 05_Archive (we write reports there), scripts (deploy artifacts).
recent=$(find "$VAULT_DIR" \
    -mindepth 1 \
    \( -path "$VAULT_DIR/.git" -o -path "$VAULT_DIR/05_Archive" -o -path "$VAULT_DIR/scripts" \) -prune -o \
    -type f -mmin -5 -print 2>/dev/null | head -n 1 || true)

if [ -n "$recent" ]; then
    log_info "recent edit detected: $recent"
    exit 0
else
    exit 1
fi
