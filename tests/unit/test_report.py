from __future__ import annotations

import subprocess
from pathlib import Path

from lib.report import (
    commit_report,
    write_agent_failure,
    write_conflict,
    write_skipped,
    write_success,
)


def test_write_skipped(tmp_vault: Path, make_config) -> None:
    cfg = make_config(vault_dir=tmp_vault)
    out = write_skipped(cfg, "2026-05-05", "vault edited recently")
    assert out.exists()
    text = out.read_text(encoding="utf-8")
    assert "result: skipped" in text
    assert "vault edited recently" in text
    assert out.name == "2026-05-05-SKIPPED.md"


def test_write_conflict(tmp_vault: Path, make_config) -> None:
    cfg = make_config(vault_dir=tmp_vault)
    out = write_conflict(cfg, "2026-05-05", "daily-2026-05-05", "01_Projects/a.md\n02_Ideas/b.md")
    text = out.read_text(encoding="utf-8")
    assert "branch: daily-2026-05-05" in text
    assert "01_Projects/a.md" in text
    assert "02_Ideas/b.md" in text


def test_write_agent_failure(tmp_vault: Path, make_config) -> None:
    cfg = make_config(vault_dir=tmp_vault, backend="opencode")
    out = write_agent_failure(cfg, "2026-05-05", "daily-2026-05-05")
    text = out.read_text(encoding="utf-8")
    assert "run_id: daily-2026-05-05" in text
    assert "`opencode` CLI exited non-zero" in text


def test_write_success_daily(tmp_vault: Path, make_config) -> None:
    cfg = make_config(vault_dir=tmp_vault)
    out = write_success(
        cfg, "2026-05-05", "ingest+light-lint",
        processed="- a.md", unprocessed="(none)", lint="L1: 0",
    )
    text = out.read_text(encoding="utf-8")
    assert out.name == "2026-05-05.md"
    assert "mode: ingest+light-lint" in text
    assert "## Processed\n- a.md" in text


def test_write_success_full_lint(tmp_vault: Path, make_config) -> None:
    cfg = make_config(vault_dir=tmp_vault)
    out = write_success(cfg, "2026-05-05", "full-lint", "(see below)", "(none)", "L1: 3 fixed")
    assert out.parent.name == "lint-reports"
    assert out.name == "2026-05-05-weekly.md"


def test_write_success_skips_when_agent_already_wrote(
    tmp_vault: Path, make_config
) -> None:
    cfg = make_config(vault_dir=tmp_vault)
    daily_path = tmp_vault / "05_Archive" / "daily-reports" / "2026-05-05.md"
    daily_path.write_text("# agent-authored\n", encoding="utf-8")
    # Mark dirty in git (untracked counts as dirty for status --porcelain).
    out = write_success(cfg, "2026-05-05", "ingest+light-lint", "x", "y", "z")
    assert out.read_text(encoding="utf-8") == "# agent-authored\n"


def test_commit_report_noop_when_clean(tmp_vault: Path, make_config) -> None:
    cfg = make_config(vault_dir=tmp_vault)
    head_before = subprocess.run(
        ["git", "-C", str(tmp_vault), "rev-parse", "HEAD"],
        capture_output=True, text=True, check=True,
    ).stdout
    commit_report(cfg, "noop test")
    head_after = subprocess.run(
        ["git", "-C", str(tmp_vault), "rev-parse", "HEAD"],
        capture_output=True, text=True, check=True,
    ).stdout
    assert head_before == head_after


def test_commit_report_creates_commit(tmp_vault: Path, make_config) -> None:
    cfg = make_config(vault_dir=tmp_vault)
    write_skipped(cfg, "2026-05-05", "manual test")
    commit_report(cfg, "skipped daily-2026-05-05")
    msg = subprocess.run(
        ["git", "-C", str(tmp_vault), "log", "-1", "--pretty=%s"],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    assert msg.startswith("skipped daily-2026-05-05 ")
