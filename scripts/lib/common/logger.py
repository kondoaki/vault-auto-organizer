from __future__ import annotations

import sys
from datetime import datetime


def _ts() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def log_info(msg: str) -> None:
    print(f"[{_ts()}] INFO  {msg}", file=sys.stderr)


def log_error(msg: str) -> None:
    print(f"[{_ts()}] ERROR {msg}", file=sys.stderr)


def die(msg: str) -> None:
    log_error(msg)
    sys.exit(1)
