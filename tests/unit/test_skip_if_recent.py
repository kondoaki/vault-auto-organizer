from __future__ import annotations

import os
import time
from pathlib import Path

from lib.skip_if_recent import is_recent


def _set_old_mtime(path: Path, age_seconds: int = 3600) -> None:
    """Force ``path`` to look ``age_seconds`` old so it is not 'recent'."""
    old = time.time() - age_seconds
    os.utime(path, (old, old))


def test_no_recent_edits(tmp_vault: Path, make_config) -> None:
    cfg = make_config(vault_dir=tmp_vault)
    # Tmp vault was just created — make every file old.
    for p in tmp_vault.rglob("*"):
        if p.is_file():
            _set_old_mtime(p)
    assert is_recent(cfg) is False


def test_recent_edit_in_user_content(tmp_vault: Path, make_config) -> None:
    cfg = make_config(vault_dir=tmp_vault)
    # Pre-age existing files so the new write is the only recent thing.
    for p in tmp_vault.rglob("*"):
        if p.is_file():
            _set_old_mtime(p)
    (tmp_vault / "00_Inbox" / "fresh.md").write_text("just now", encoding="utf-8")
    assert is_recent(cfg) is True


def test_recent_edit_in_excluded_dir_ignored(tmp_vault: Path, make_config) -> None:
    cfg = make_config(vault_dir=tmp_vault)
    for p in tmp_vault.rglob("*"):
        if p.is_file():
            _set_old_mtime(p)
    # Touch a file under 05_Archive (excluded) — should NOT trigger.
    (tmp_vault / "05_Archive" / "daily-reports" / "fresh.md").write_text(
        "report", encoding="utf-8"
    )
    assert is_recent(cfg) is False


def test_recent_log_md_ignored(tmp_vault: Path, make_config) -> None:
    cfg = make_config(vault_dir=tmp_vault)
    for p in tmp_vault.rglob("*"):
        if p.is_file():
            _set_old_mtime(p)
    (tmp_vault / "log.md").write_text("recent append", encoding="utf-8")
    assert is_recent(cfg) is False


def test_recent_scripts_dir_ignored(tmp_vault: Path, make_config) -> None:
    cfg = make_config(vault_dir=tmp_vault)
    for p in tmp_vault.rglob("*"):
        if p.is_file():
            _set_old_mtime(p)
    scripts = tmp_vault / "scripts"
    scripts.mkdir(exist_ok=True)
    (scripts / "fresh.sh").write_text("echo", encoding="utf-8")
    assert is_recent(cfg) is False
