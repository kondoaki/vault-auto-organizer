# Backend: opencode CLI. Sourced by invoke-agent.sh.
# Expects: $PROMPT_TEXT, $WORKBENCH_DIR, $OPENCODE_BIN.
# $__INVOKE_LIB_DIR is the directory of invoke-agent.sh (set by the caller).
# invoke-agent.sh sets cwd to $WORKBENCH_DIR before sourcing this.
#
# Permission rules and model live in agent-backends/opencode/opencode.json —
# opencode discovers the config via OPENCODE_CONFIG_DIR. To change the model,
# edit opencode.json and re-run install.sh.
export OPENCODE_CONFIG_DIR="$__INVOKE_LIB_DIR/agent-backends/opencode"

"$OPENCODE_BIN" run "$PROMPT_TEXT" --dangerously-skip-permissions
