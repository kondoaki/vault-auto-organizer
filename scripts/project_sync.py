#!/usr/bin/env python3
"""project_sync — ad-hoc snapshot of external git projects into Vault notes.

CLI:
    project_sync.py [TARGET] [--force]

TARGET defaults to cwd. Single repo (.git present) → sync that repo;
parent of repos → sync each child (depth 1). User-invoked only; never
scheduled.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))  # make `lib` importable

from lib.common import load as load_config  # noqa: E402
from lib.project_sync.cli import main as cli_main  # noqa: E402


def main(argv) -> int:
    cfg = load_config()
    return cli_main(argv, cfg)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
