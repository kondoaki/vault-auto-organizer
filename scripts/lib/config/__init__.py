from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Config:
    vault_dir: Path
    workbench_dir: Path
    venv_dir: Path
    backend: str  # "claude" | "opencode"
    agent_bin: str
    check_recent: bool = False


def load(*, check_recent: bool = False) -> Config:
    """Load runtime config from the install-rendered ``local`` module.

    Imported lazily so tests can construct ``Config`` directly without
    depending on the install-time-generated ``local.py``.
    """
    from . import local  # noqa: PLC0415 — lazy import is intentional

    return Config(
        vault_dir=Path(local.VAULT_DIR),
        workbench_dir=Path(local.WORKBENCH_DIR),
        venv_dir=Path(local.VENV_DIR),
        backend=local.BACKEND,
        agent_bin=local.AGENT_BIN,
        check_recent=check_recent,
    )


__all__ = ["Config", "load"]
