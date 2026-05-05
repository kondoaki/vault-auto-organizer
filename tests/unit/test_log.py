from __future__ import annotations

from pathlib import Path

from lib.log import append_log, rotate_log_if_needed


def test_append_log_writes_block(tmp_vault: Path, make_config) -> None:
    cfg = make_config(vault_dir=tmp_vault)
    append_log(
        cfg,
        action="ingest",
        summary="routed 1 file",
        file="00_Inbox/foo.md",
        destination="04_Resources/foo.md",
        linked="[[bar]]",
        result="success",
    )
    text = (tmp_vault / "log.md").read_text(encoding="utf-8")
    assert "ingest | routed 1 file" in text
    assert "- file: 00_Inbox/foo.md" in text
    assert "- destination: 04_Resources/foo.md" in text
    assert "- linked: [[bar]]" in text
    assert "- result: success" in text


def test_rotate_noop_when_empty(tmp_vault: Path, make_config) -> None:
    cfg = make_config(vault_dir=tmp_vault)
    rotate_log_if_needed(cfg)  # log.md exists but empty — must not raise
    assert (tmp_vault / "log.md").read_text(encoding="utf-8") == ""


def test_rotate_archives_old_months(
    tmp_vault: Path, make_config, monkeypatch
) -> None:
    cfg = make_config(vault_dir=tmp_vault)
    log_path = tmp_vault / "log.md"
    log_path.write_text(
        """## [2025-11-15 03:00] ingest | old1
- file: a.md
- destination: 05_Archive/a.md
- linked:
- result: success

## [2025-12-02 03:00] ingest | old2
- file: b.md
- destination: 02_Ideas/b.md
- linked:
- result: success

## [2026-01-05 03:00] ingest | new1
- file: c.md
- destination: 02_Ideas/c.md
- linked:
- result: success
""",
        encoding="utf-8",
    )

    monkeypatch.setattr("lib.log.current_month_prefix", lambda: "2026-01")
    rotate_log_if_needed(cfg)

    kept = log_path.read_text(encoding="utf-8")
    assert "new1" in kept
    assert "old1" not in kept
    assert "old2" not in kept

    nov = (tmp_vault / "05_Archive" / "logs" / "2025-11.md").read_text(encoding="utf-8")
    assert "old1" in nov

    dec = (tmp_vault / "05_Archive" / "logs" / "2025-12.md").read_text(encoding="utf-8")
    assert "old2" in dec
