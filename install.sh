#!/usr/bin/env bash
# install.sh [<vault-dir>] [--backend claude|opencode] [--workbench-dir DIR] [--no-launchd-bootstrap]
# Installs the auto-organizer into the target Vault. Idempotent.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Auto-source .env if present (gitignored, holds per-machine values like VAULT_PATH).
if [ -f "$REPO_ROOT/.env" ]; then
    set -a
    # shellcheck disable=SC1091
    . "$REPO_ROOT/.env"
    set +a
fi

usage() {
    cat <<EOF
Usage: install.sh [<vault-dir>] [--backend claude|opencode] [--workbench-dir DIR] [--no-launchd-bootstrap]

  <vault-dir>             Absolute path to the Obsidian Vault (iCloud-synced).
                          Falls back to \$VAULT_PATH (e.g. set in .env) if omitted.
  --backend NAME          Agent CLI backend: claude (default) or opencode.
  --workbench-dir DIR     Worktree location. Default: \$HOME/Workspace/vault-workbench
  --no-launchd-bootstrap  Render plists but don't print bootstrap instructions.
EOF
    exit "${1:-0}"
}

if [ $# -ge 1 ] && [ "${1:0:1}" != "-" ]; then
    VAULT_DIR="$1"; shift
elif [ -n "${VAULT_PATH:-}" ]; then
    VAULT_DIR="$VAULT_PATH"
else
    echo "ERROR: vault-dir not given and \$VAULT_PATH not set (copy .env.example to .env and edit)" >&2
    usage 1
fi

WORKBENCH_DIR="${HOME}/Workspace/vault-workbench"
DO_BOOTSTRAP=1
BACKEND="claude"
while [ $# -gt 0 ]; do
    case "$1" in
        --backend) BACKEND="$2"; shift 2 ;;
        --workbench-dir) WORKBENCH_DIR="$2"; shift 2 ;;
        --no-launchd-bootstrap) DO_BOOTSTRAP=0; shift ;;
        -h|--help) usage 0 ;;
        *) echo "unknown arg: $1" >&2; usage 1 ;;
    esac
done

case "$BACKEND" in
    claude|opencode) ;;
    *) echo "ERROR: --backend must be 'claude' or 'opencode' (got: $BACKEND)" >&2; exit 1 ;;
esac

[ -f "$REPO_ROOT/scripts/lib/agent-backends/${BACKEND}.sh" ] \
    || { echo "ERROR: backend script not found: agent-backends/${BACKEND}.sh" >&2; exit 1; }

# Strip trailing slash for consistency
VAULT_DIR="${VAULT_DIR%/}"
WORKBENCH_DIR="${WORKBENCH_DIR%/}"

# 1. Prerequisite checks
command -v git >/dev/null || { echo "ERROR: git not found" >&2; exit 1; }
case "$BACKEND" in
    claude)
        AGENT_BIN_NAME="claude"
        AGENT_BIN_VAR="CLAUDE_BIN"
        ;;
    opencode)
        AGENT_BIN_NAME="opencode"
        AGENT_BIN_VAR="OPENCODE_BIN"
        ;;
esac
AGENT_BIN="$(command -v "$AGENT_BIN_NAME" || true)"
if [ -z "$AGENT_BIN" ]; then
    echo "WARNING: $AGENT_BIN_NAME CLI not on PATH. Install will continue, but the launchd jobs will fail until it is installed." >&2
    AGENT_BIN="$AGENT_BIN_NAME"
fi

mkdir -p "$VAULT_DIR"

# 2. Init git in the Vault if needed
if [ ! -d "$VAULT_DIR/.git" ]; then
    echo "[install] initializing git in $VAULT_DIR"
    (cd "$VAULT_DIR" && git init -q && \
        git -c user.email="auto-organizer@local" -c user.name="auto-organizer" \
            commit -q --allow-empty -m "initial commit")
fi

# 3. Create directories
mkdir -p "$VAULT_DIR/00_Inbox" "$VAULT_DIR/04_Resources" "$VAULT_DIR/01_Projects" \
         "$VAULT_DIR/02_Ideas" "$VAULT_DIR/03_Context/_pending-updates" \
         "$VAULT_DIR/05_Archive/logs" "$VAULT_DIR/05_Archive/daily-reports" \
         "$VAULT_DIR/05_Archive/lint-reports" "$VAULT_DIR/05_Archive/orphans"
for d in 05_Archive/logs 05_Archive/daily-reports 05_Archive/lint-reports 05_Archive/orphans 03_Context/_pending-updates; do
    [ -f "$VAULT_DIR/$d/.gitkeep" ] || touch "$VAULT_DIR/$d/.gitkeep"
done

# 4. CLAUDE.md (agent-owned: always overwrite to pick up updates)
cp "$REPO_ROOT/templates/CLAUDE.md" "$VAULT_DIR/CLAUDE.md"

# 5. Routing rules (user-editable: skip if it already exists)
if [ ! -f "$VAULT_DIR/03_Context/_routing-rules.md" ]; then
    cp "$REPO_ROOT/templates/routing-rules.md" "$VAULT_DIR/03_Context/_routing-rules.md"
fi

# 6. MyContext.md
#    - empty/missing: bootstrap with the full template (Arrival + section skeletons)
#    - has content but no Arrival Protocol: prepend just the Arrival Protocol
#    - already has Arrival Protocol: leave alone
mc="$VAULT_DIR/03_Context/MyContext.md"
if [ ! -f "$mc" ] || [ ! -s "$mc" ]; then
    cp "$REPO_ROOT/templates/mycontext-bootstrap.md" "$mc"
elif ! grep -q "## AI Arrival Protocol" "$mc"; then
    {
        cat "$REPO_ROOT/templates/mycontext-arrival-protocol.md"
        printf '\n'
        cat "$mc"
    } > "$mc.new"
    mv "$mc.new" "$mc"
fi

# 7. log.md
[ -f "$VAULT_DIR/log.md" ] || : > "$VAULT_DIR/log.md"

# 8. .gitignore (merge our entries)
gi="$VAULT_DIR/.gitignore"
[ -f "$gi" ] || : > "$gi"
for entry in ".obsidian/workspace.json" ".obsidian/workspace-mobile.json" \
             ".obsidian/cache" ".DS_Store" ".trash/" "scripts/lib/config.sh"; do
    grep -qxF "$entry" "$gi" || echo "$entry" >> "$gi"
done

# 9. rsync scripts/ — exclude agent-backends so we can selectively install only
#    the chosen backend (the repo carries every backend side-by-side).
mkdir -p "$VAULT_DIR/scripts"
rsync -a --delete \
    --exclude 'lib/config.sh' \
    --exclude 'lib/agent-backends/' \
    "$REPO_ROOT/scripts/" "$VAULT_DIR/scripts/"
chmod +x "$VAULT_DIR/scripts/daily-ingest.sh" "$VAULT_DIR/scripts/weekly-lint.sh"

# 9a. Install the chosen backend snippet (and any backend-specific subdir).
mkdir -p "$VAULT_DIR/scripts/lib/agent-backends"
# Wipe stale backend files from a previous install (e.g. switching backends).
find "$VAULT_DIR/scripts/lib/agent-backends" -mindepth 1 -maxdepth 1 -exec rm -rf {} +
cp "$REPO_ROOT/scripts/lib/agent-backends/${BACKEND}.sh" \
   "$VAULT_DIR/scripts/lib/agent-backends/${BACKEND}.sh"
if [ -d "$REPO_ROOT/scripts/lib/agent-backends/${BACKEND}" ]; then
    cp -R "$REPO_ROOT/scripts/lib/agent-backends/${BACKEND}" \
          "$VAULT_DIR/scripts/lib/agent-backends/${BACKEND}"
fi

# 10. Render config.sh
sed \
    -e "s|__VAULT_DIR__|${VAULT_DIR}|g" \
    -e "s|__WORKBENCH_DIR__|${WORKBENCH_DIR}|g" \
    -e "s|__AGENT_BIN_VAR__|${AGENT_BIN_VAR}|g" \
    -e "s|__AGENT_BIN__|${AGENT_BIN}|g" \
    "$REPO_ROOT/templates/config.sh.template" > "$VAULT_DIR/scripts/lib/config.sh"

# 11. Render plists
mkdir -p "$HOME/Library/LaunchAgents"
PATH_FOR_LAUNCHD="$(dirname "$AGENT_BIN"):/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin"
# launchd does not inherit TZ; pin it from /etc/localtime so date calls in
# both the orchestrator and the agent's bash subprocesses use local time.
TZ_FOR_LAUNCHD="$(readlink /etc/localtime 2>/dev/null | sed 's|.*/zoneinfo/||')"
[ -n "$TZ_FOR_LAUNCHD" ] || TZ_FOR_LAUNCHD="UTC"
for kind in ingest lint; do
    sed \
        -e "s|__VAULT_DIR__|${VAULT_DIR}|g" \
        -e "s|__PATH__|${PATH_FOR_LAUNCHD}|g" \
        -e "s|__USER_HOME__|${HOME}|g" \
        -e "s|__TZ__|${TZ_FOR_LAUNCHD}|g" \
        "$REPO_ROOT/templates/plists/com.user.vault-organizer.${kind}.plist.template" \
        > "$HOME/Library/LaunchAgents/com.user.vault-organizer.${kind}.plist"
done

echo "[install] done."

# 12. launchd bootstrap instructions (or skip)
if [ "$DO_BOOTSTRAP" -eq 1 ]; then
    cat <<EOF

To activate the schedule, run:

  launchctl bootstrap gui/\$(id -u) ~/Library/LaunchAgents/com.user.vault-organizer.ingest.plist
  launchctl bootstrap gui/\$(id -u) ~/Library/LaunchAgents/com.user.vault-organizer.lint.plist

Verify with:

  launchctl print gui/\$(id -u)/com.user.vault-organizer.ingest
EOF
fi
