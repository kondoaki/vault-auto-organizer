from __future__ import annotations

import subprocess

from lib.common import log_error, log_info
from lib.config import Config


def push_to_main(cfg: Config) -> None:
    """Best-effort push of the vault's current branch to its upstream.

    Returns silently if no upstream is configured. Logs (but does not
    raise) on push failure — the orchestrator's exit code reflects the
    run's outcome, not the push attempt.
    """
    upstream = subprocess.run(
        ["git", "-C", str(cfg.vault_dir), "rev-parse", "--abbrev-ref",
         "--symbolic-full-name", "@{u}"],
        capture_output=True, text=True,
    )
    if upstream.returncode != 0:
        log_info("no upstream configured; skipping push")
        return

    target = upstream.stdout.strip()
    log_info(f"pushing to {target}")
    push = subprocess.run(["git", "-C", str(cfg.vault_dir), "push"])
    if push.returncode == 0:
        log_info("push complete")
    else:
        log_error(f"git push to {target} failed (local commits retained)")


__all__ = ["push_to_main"]
