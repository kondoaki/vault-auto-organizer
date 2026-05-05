from __future__ import annotations

import os
import subprocess
from pathlib import Path

from lib.common import AgentError, Config

_CONFIG_DIR = Path(__file__).parent / "opencode_config"


def invoke(cfg: Config, prompt_text: str) -> None:
    """Run the opencode CLI with the rendered prompt.

    Equivalent of the bash agent-backends/opencode.sh:
        OPENCODE_CONFIG_DIR=<dir> opencode run "$PROMPT_TEXT" \
            --dangerously-skip-permissions
    """
    env = os.environ.copy()
    env["OPENCODE_CONFIG_DIR"] = str(_CONFIG_DIR)
    result = subprocess.run(
        [cfg.agent_bin, "run", prompt_text, "--dangerously-skip-permissions"],
        cwd=str(cfg.workbench_dir),
        env=env,
    )
    if result.returncode != 0:
        raise AgentError(f"opencode exited {result.returncode}")
