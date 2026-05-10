from __future__ import annotations

import os
import subprocess
from pathlib import Path

from lib.common import AgentError, Config, OrganizerError, current_iso_date, log_info

_PROMPT_PATH = (
    Path(__file__).resolve().parent.parent / "agent" / "prompts" / "project_sync.md"
)
_OPENCODE_CONFIG_DIR = (
    Path(__file__).resolve().parent.parent
    / "agent" / "backends" / "opencode_config"
)


def render_prompt(facts_block: str) -> str:
    raw = _PROMPT_PATH.read_text(encoding="utf-8")
    return (
        raw.replace("$FACTS_BLOCK", facts_block)
           .replace("$RUN_DATE", current_iso_date())
    )


def invoke_for_repo(cfg: Config, *, repo_path: Path, prompt_text: str) -> None:
    """Invoke the configured agent backend with cwd=repo, --add-dir=vault."""
    log_info(
        f"invoking agent (backend={cfg.backend}) for repo {repo_path.name}"
    )
    if cfg.backend == "claude":
        result = subprocess.run(
            [
                cfg.agent_bin,
                "-p", prompt_text,
                "--allowedTools", "Bash,Write,Read",
                "--add-dir", str(cfg.vault_dir),
            ],
            cwd=str(repo_path),
        )
        if result.returncode != 0:
            raise AgentError(f"claude exited {result.returncode}")
    elif cfg.backend == "opencode":
        env = os.environ.copy()
        env["OPENCODE_CONFIG_DIR"] = str(_OPENCODE_CONFIG_DIR)
        result = subprocess.run(
            [cfg.agent_bin, "run", prompt_text, "--dangerously-skip-permissions"],
            cwd=str(repo_path),
            env=env,
        )
        if result.returncode != 0:
            raise AgentError(f"opencode exited {result.returncode}")
    else:
        raise OrganizerError(f"unknown backend: {cfg.backend}")


__all__ = ["render_prompt", "invoke_for_repo"]
