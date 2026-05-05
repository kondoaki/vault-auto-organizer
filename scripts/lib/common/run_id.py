from __future__ import annotations

from .iso_date import current_iso_date


def generate_run_id(kind: str) -> str:
    return f"{kind}-{current_iso_date()}"
