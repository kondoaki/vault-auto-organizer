from __future__ import annotations

import os
import time
from pathlib import Path

from lib.common import log_info
from lib.config import Config

_EXCLUDED_DIRS = {".git", ".obsidian", "05_Archive", "scripts"}
_EXCLUDED_FILES = {"log.md", "CLAUDE.md"}


def is_recent(cfg: Config, *, threshold_seconds: int = 300) -> bool:
    """True if any user-content file was modified within the last threshold.

    Mirrors the bash skip-if-recent: the gate only triggers on the user
    mid-edit, so orchestrator-owned and Obsidian-internal paths at the
    vault root are excluded.
    """
    cutoff = time.time() - threshold_seconds
    vault_root = str(cfg.vault_dir)

    for root, dirs, files in os.walk(cfg.vault_dir):
        if root == vault_root:
            dirs[:] = [d for d in dirs if d not in _EXCLUDED_DIRS]
        for name in files:
            if root == vault_root and name in _EXCLUDED_FILES:
                continue
            path = Path(root) / name
            try:
                if path.stat().st_mtime > cutoff:
                    log_info(f"recent edit detected: {path}")
                    return True
            except OSError:
                continue
    return False


__all__ = ["is_recent"]
