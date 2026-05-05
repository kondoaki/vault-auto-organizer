from __future__ import annotations

import signal
import sys
from typing import Callable


def install_signal_handlers(cleanup: Callable[[], None]) -> None:
    """Run ``cleanup()`` on SIGTERM / SIGINT, then exit 128+signum.

    SIGKILL is unhandleable; the next scheduled run is responsible for
    recovery (worktree cleanup etc).
    """

    def _handler(signum: int, _frame) -> None:  # type: ignore[no-untyped-def]
        try:
            cleanup()
        finally:
            sys.exit(128 + signum)

    signal.signal(signal.SIGTERM, _handler)
    signal.signal(signal.SIGINT, _handler)
