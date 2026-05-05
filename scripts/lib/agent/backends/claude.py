from __future__ import annotations

import subprocess

from lib.common import AgentError, Config


def invoke(cfg: Config, prompt_text: str) -> None:
    """Run the Claude Code CLI with the rendered prompt.

    Equivalent of the bash agent-backends/claude.sh:
        claude -p "$PROMPT_TEXT" --allowedTools Bash,Write,Read \
            --add-dir "$WORKBENCH_DIR"
    """
    result = subprocess.run(
        [
            cfg.agent_bin,
            "-p", prompt_text,
            "--allowedTools", "Bash,Write,Read",
            "--add-dir", str(cfg.workbench_dir),
        ],
        cwd=str(cfg.workbench_dir),
    )
    if result.returncode != 0:
        raise AgentError(f"claude exited {result.returncode}")
