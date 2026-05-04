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
# Excluded paths: anything not representing a user-content edit — otherwise the
# guard either misfires (Obsidian's housekeeping writes) or self-triggers
# (orchestrator's own writes). The check should only catch the user mid-edit.
#   .git/        — internal
#   .obsidian/   — Obsidian UI state (workspace.json, caches, plugins) is
#                  rewritten continuously while Obsidian is open
#   05_Archive/  — report files (success/skipped/agent-failure/conflict) and rotated logs
#   scripts/     — deploy artifacts (rsync'd by install.sh)
#   log.md       — append target of every run + rewritten by rotate_log_if_needed
#   CLAUDE.md    — overwritten by install.sh on every re-install
recent=$(find "$VAULT_DIR" \
    -mindepth 1 \
    \( -path "$VAULT_DIR/.git" \
       -o -path "$VAULT_DIR/.obsidian" \
       -o -path "$VAULT_DIR/05_Archive" \
       -o -path "$VAULT_DIR/scripts" \
       -o -path "$VAULT_DIR/log.md" \
       -o -path "$VAULT_DIR/CLAUDE.md" \) -prune -o \
    -type f -mmin -5 -print 2>/dev/null | head -n 1 || true)

if [ -n "$recent" ]; then
    log_info "recent edit detected: $recent"
    exit 0
else
    exit 1
fi
