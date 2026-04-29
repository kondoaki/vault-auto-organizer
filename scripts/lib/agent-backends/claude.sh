# Backend: Claude Code CLI. Sourced by invoke-agent.sh.
# Expects: $PROMPT_TEXT, $WORKBENCH_DIR, $CLAUDE_BIN.
# invoke-agent.sh sets cwd to $WORKBENCH_DIR before sourcing this.

"$CLAUDE_BIN" -p "$PROMPT_TEXT" \
    --allowedTools Bash,Write,Read \
    --add-dir "$WORKBENCH_DIR"
