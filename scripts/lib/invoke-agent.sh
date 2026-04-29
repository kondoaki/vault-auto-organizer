#!/usr/bin/env bash
# invoke-agent.sh <run-id> <prompt-file>
# Renders the prompt with $RUN_ID/$RUN_DATE substituted, then sources the
# installed backend snippet under agent-backends/. install.sh decides which
# backend ends up here; this script is backend-agnostic.
set -euo pipefail

__INVOKE_LIB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "$__INVOKE_LIB_DIR/common.sh"

run_id="${1:?usage: invoke-agent.sh <run-id> <prompt-file>}"
prompt_file="${2:?usage: invoke-agent.sh <run-id> <prompt-file>}"

[ -f "$prompt_file" ] || die "prompt file not found: $prompt_file"
[ -d "$WORKBENCH_DIR" ] || die "workbench does not exist: $WORKBENCH_DIR"

run_date="$(current_iso_date)"

# Render only $RUN_ID / $RUN_DATE — every other dollar sign in the prompt is preserved.
PROMPT_TEXT=$(sed \
    -e "s|\$RUN_ID|${run_id}|g" \
    -e "s|\$RUN_DATE|${run_date}|g" \
    "$prompt_file")
export PROMPT_TEXT

# Pick the installed backend snippet. install.sh ships exactly one of
# agent-backends/{claude,opencode}.sh into the Vault; tests can override with
# AGENT_BACKEND_FILE since the repo carries every backend side-by-side.
if [ -n "${AGENT_BACKEND_FILE:-}" ]; then
    backend_file="$AGENT_BACKEND_FILE"
else
    shopt -s nullglob
    backend_files=("$__INVOKE_LIB_DIR"/agent-backends/*.sh)
    shopt -u nullglob
    [ "${#backend_files[@]}" -eq 1 ] \
        || die "expected exactly one agent backend in $__INVOKE_LIB_DIR/agent-backends/, found ${#backend_files[@]}"
    backend_file="${backend_files[0]}"
fi

[ -f "$backend_file" ] || die "agent backend not found: $backend_file"

log_info "invoking agent (backend=$(basename "$backend_file" .sh), run_id=$run_id, prompt=$(basename "$prompt_file"))"

# Run the agent with cwd = workbench. The prompts tell the agent "the Vault is
# mounted at the current working directory", and CLAUDE.md path resolution
# depends on this. Backends therefore should not need to cd themselves.
cd "$WORKBENCH_DIR"

# shellcheck disable=SC1090
source "$backend_file"
