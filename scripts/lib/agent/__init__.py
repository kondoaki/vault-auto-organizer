from __future__ import annotations

from pathlib import Path

from lib.common import OrganizerError, current_iso_date, log_info
from lib.config import Config

from .backends import claude as _claude
from .backends import opencode as _opencode

_PROMPTS_DIR = Path(__file__).parent / "prompts"


def invoke_agent(cfg: Config, run_id: str, *, prompt: str) -> None:
    """Invoke the configured agent CLI inside ``cfg.workbench_dir``.

    ``prompt`` is the bare name (without ``.md``) of a file under
    ``lib/agent/prompts/``. ``$RUN_ID`` and ``$RUN_DATE`` placeholders
    inside the prompt are substituted; every other ``$`` is preserved.

    Raises ``AgentError`` on non-zero exit from the backend, or
    ``OrganizerError`` if the workbench / prompt are missing.
    """
    prompt_path = _PROMPTS_DIR / f"{prompt}.md"
    if not prompt_path.exists():
        raise OrganizerError(f"prompt file not found: {prompt_path}")
    if not cfg.workbench_dir.exists():
        raise OrganizerError(f"workbench does not exist: {cfg.workbench_dir}")

    raw = prompt_path.read_text(encoding="utf-8")
    prompt_text = (
        raw.replace("$RUN_ID", run_id).replace("$RUN_DATE", current_iso_date())
    )

    log_info(
        f"invoking agent (backend={cfg.backend}, run_id={run_id}, prompt={prompt})"
    )

    if cfg.backend == "claude":
        _claude.invoke(cfg, prompt_text)
    elif cfg.backend == "opencode":
        _opencode.invoke(cfg, prompt_text)
    else:
        raise OrganizerError(f"unknown backend: {cfg.backend}")


__all__ = ["invoke_agent"]
