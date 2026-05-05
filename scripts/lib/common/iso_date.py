from __future__ import annotations

from datetime import datetime


def current_iso_date() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def current_iso_minute() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def current_month_prefix() -> str:
    return datetime.now().strftime("%Y-%m")
