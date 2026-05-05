#!/usr/bin/env bash
# install.sh [<vault-dir>] [--backend claude|opencode] [--no-launchd-bootstrap]
# Installs the auto-organizer into the target Vault. Idempotent.
#
# Reads .env (if present) for VAULT_PATH, WORKBENCH_DIR, VENV_DIR.
# Renders templates/config.py.template into <vault>/scripts/lib/config/local.py
# and the plist templates into ~/Library/LaunchAgents/, then rsyncs scripts/
# into the Vault and creates a Python venv at $VENV_DIR for runtime use.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Auto-source .env if present (gitignored, holds per-machine values).
if [ -f "$REPO_ROOT/.env" ]; then
    set -a
    # shellcheck disable=SC1091
    . "$REPO_ROOT/.env"
    set +a
fi

usage() {
    cat <<EOF
Usage: install.sh [<vault-dir>] [--backend claude|opencode] [--no-launchd-bootstrap]

  <vault-dir>             Absolute path to the Obsidian Vault.
                          Falls back to \$VAULT_PATH (e.g. set in .env) if omitted.
  --backend NAME          Agent CLI backend: claude (default) or opencode.
  --no-launchd-bootstrap  Render plists but don't print bootstrap instructions.

Environment (optional, normally set in .env):
  WORKBENCH_DIR           Worktree location. Default: \$HOME/Workspace/vault-workbench
  VENV_DIR                Python venv location (must be outside iCloud).
                          Default: \$HOME/Library/Application Support/vault-organizer/venv
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

DO_BOOTSTRAP=1
BACKEND="claude"
while [ $# -gt 0 ]; do
    case "$1" in
        --backend) BACKEND="$2"; shift 2 ;;
        --no-launchd-bootstrap) DO_BOOTSTRAP=0; shift ;;
        -h|--help) usage 0 ;;
        *) echo "unknown arg: $1" >&2; usage 1 ;;
    esac
done

case "$BACKEND" in
    claude|opencode) ;;
    *) echo "ERROR: --backend must be 'claude' or 'opencode' (got: $BACKEND)" >&2; exit 1 ;;
esac

# Resolve and normalize paths.
WORKBENCH_DIR="${WORKBENCH_DIR:-$HOME/Workspace/vault-workbench}"
VENV_DIR="${VENV_DIR:-$HOME/Library/Application Support/vault-organizer/venv}"
VAULT_DIR="${VAULT_DIR%/}"
WORKBENCH_DIR="${WORKBENCH_DIR%/}"
VENV_DIR="${VENV_DIR%/}"

# Sanity: refuse a venv inside the Vault (iCloud would corrupt it).
case "$VENV_DIR" in
    "$VAULT_DIR"|"$VAULT_DIR"/*)
        echo "ERROR: VENV_DIR ($VENV_DIR) is inside VAULT_DIR ($VAULT_DIR)." >&2
        echo "       The venv must live outside iCloud-synced storage." >&2
        exit 1
        ;;
esac

# 1. Prerequisite checks.
command -v git >/dev/null || { echo "ERROR: git not found" >&2; exit 1; }
[ -x /usr/bin/python3 ] || {
    echo "ERROR: /usr/bin/python3 not found. Install Command Line Tools:" >&2
    echo "       xcode-select --install" >&2
    exit 1
}

case "$BACKEND" in
    claude)   AGENT_BIN_NAME="claude" ;;
    opencode) AGENT_BIN_NAME="opencode" ;;
esac
AGENT_BIN="$(command -v "$AGENT_BIN_NAME" || true)"
if [ -z "$AGENT_BIN" ]; then
    echo "WARNING: $AGENT_BIN_NAME CLI not on PATH. Install will continue, but the launchd jobs will fail until it is installed." >&2
    AGENT_BIN="$AGENT_BIN_NAME"
fi

mkdir -p "$VAULT_DIR"

# 2. Init git in the Vault if needed.
if [ ! -d "$VAULT_DIR/.git" ]; then
    echo "[install] initializing git in $VAULT_DIR"
    (cd "$VAULT_DIR" && git -c init.defaultBranch=main init -q && \
        git -c user.email="auto-organizer@local" -c user.name="auto-organizer" \
            commit -q --allow-empty -m "initial commit")
fi

# 3. Create the standard folder skeleton.
mkdir -p "$VAULT_DIR/00_Inbox" "$VAULT_DIR/04_Resources" "$VAULT_DIR/01_Projects" \
         "$VAULT_DIR/02_Ideas" "$VAULT_DIR/03_Context/_pending-updates" \
         "$VAULT_DIR/05_Archive/logs" "$VAULT_DIR/05_Archive/daily-reports" \
         "$VAULT_DIR/05_Archive/lint-reports" "$VAULT_DIR/05_Archive/orphans"
for d in 05_Archive/logs 05_Archive/daily-reports 05_Archive/lint-reports 05_Archive/orphans 03_Context/_pending-updates; do
    [ -f "$VAULT_DIR/$d/.gitkeep" ] || touch "$VAULT_DIR/$d/.gitkeep"
done

# 4. CLAUDE.md (agent-owned: always overwrite).
cp "$REPO_ROOT/templates/CLAUDE.md" "$VAULT_DIR/CLAUDE.md"

# 5. Routing rules (user-editable: skip if it already exists).
if [ ! -f "$VAULT_DIR/03_Context/_routing-rules.md" ]; then
    cp "$REPO_ROOT/templates/routing-rules.md" "$VAULT_DIR/03_Context/_routing-rules.md"
fi

# 6. MyContext.md.
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

# 7. log.md.
[ -f "$VAULT_DIR/log.md" ] || : > "$VAULT_DIR/log.md"

# 8. Vault-side .gitignore (merge our entries).
gi="$VAULT_DIR/.gitignore"
[ -f "$gi" ] || : > "$gi"
for entry in ".obsidian/workspace.json" ".obsidian/workspace-mobile.json" \
             ".obsidian/cache" ".DS_Store" ".trash/" "scripts/lib/config/local.py" \
             ".venv/"; do
    grep -qxF "$entry" "$gi" || echo "$entry" >> "$gi"
done

# 9. rsync scripts/ — exclude the install-rendered local.py.
mkdir -p "$VAULT_DIR/scripts"
rsync -a --delete \
    --exclude 'lib/config/local.py' \
    --exclude '__pycache__' \
    --exclude '*.pyc' \
    "$REPO_ROOT/scripts/" "$VAULT_DIR/scripts/"
chmod +x "$VAULT_DIR/scripts/daily_ingest.py" "$VAULT_DIR/scripts/weekly_lint.py"

# 10. Render lib/config/local.py from the template.
mkdir -p "$VAULT_DIR/scripts/lib/config"
sed \
    -e "s|__VAULT_DIR__|${VAULT_DIR}|g" \
    -e "s|__WORKBENCH_DIR__|${WORKBENCH_DIR}|g" \
    -e "s|__VENV_DIR__|${VENV_DIR}|g" \
    -e "s|__BACKEND__|${BACKEND}|g" \
    -e "s|__AGENT_BIN__|${AGENT_BIN}|g" \
    "$REPO_ROOT/templates/config.py.template" \
    > "$VAULT_DIR/scripts/lib/config/local.py"

# 11. Create the runtime Python venv (outside iCloud).
mkdir -p "$(dirname "$VENV_DIR")"
if [ ! -x "$VENV_DIR/bin/python" ]; then
    echo "[install] creating venv at $VENV_DIR"
    /usr/bin/python3 -m venv "$VENV_DIR"
fi

# 12. Render plists.
mkdir -p "$HOME/Library/LaunchAgents"
PATH_FOR_LAUNCHD="$(dirname "$AGENT_BIN"):/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin"
TZ_FOR_LAUNCHD="$(readlink /etc/localtime 2>/dev/null | sed 's|.*/zoneinfo/||')"
[ -n "$TZ_FOR_LAUNCHD" ] || TZ_FOR_LAUNCHD="UTC"
for kind in ingest lint; do
    sed \
        -e "s|__VAULT_DIR__|${VAULT_DIR}|g" \
        -e "s|__VENV_DIR__|${VENV_DIR}|g" \
        -e "s|__PATH__|${PATH_FOR_LAUNCHD}|g" \
        -e "s|__USER_HOME__|${HOME}|g" \
        -e "s|__TZ__|${TZ_FOR_LAUNCHD}|g" \
        "$REPO_ROOT/templates/plists/com.user.vault-organizer.${kind}.plist.template" \
        > "$HOME/Library/LaunchAgents/com.user.vault-organizer.${kind}.plist"
done

echo "[install] done."

# 13. FDA reminder (one-time).
cat <<EOF

NOTE: Full Disk Access is required so the launchd-spawned Python can
      read/write iCloud-backed files. Open:

        System Settings → Privacy & Security → Full Disk Access

      and add /usr/bin/python3 to the list (toggle ON).
EOF

# 14. launchd bootstrap instructions (or skip).
if [ "$DO_BOOTSTRAP" -eq 1 ]; then
    cat <<EOF

To activate the schedule, run:

  launchctl bootstrap gui/\$(id -u) ~/Library/LaunchAgents/com.user.vault-organizer.ingest.plist
  launchctl bootstrap gui/\$(id -u) ~/Library/LaunchAgents/com.user.vault-organizer.lint.plist

Verify with:

  launchctl print gui/\$(id -u)/com.user.vault-organizer.ingest
EOF
fi
