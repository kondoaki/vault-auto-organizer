from __future__ import annotations

import re

from lib.common import current_iso_minute, current_month_prefix, log_info
from lib.config import Config

_LOG_HEADER_RE = re.compile(r"^## \[(\d{4}-\d{2})")


def append_log(
    cfg: Config,
    *,
    action: str,
    summary: str,
    file: str,
    destination: str,
    linked: str,
    result: str,
) -> None:
    """Append one log.md entry. Mirrors the bash append_log format."""
    stamp = current_iso_minute()
    block = (
        f"\n## [{stamp}] {action} | {summary}\n"
        f"- file: {file}\n"
        f"- destination: {destination}\n"
        f"- linked: {linked}\n"
        f"- result: {result}\n"
    )
    log_path = cfg.vault_dir / "log.md"
    with log_path.open("a", encoding="utf-8") as f:
        f.write(block)


def rotate_log_if_needed(cfg: Config) -> None:
    """Slice entries older than the current month out of log.md.

    Older entries are appended to ``05_Archive/logs/YYYY-MM.md`` (one file
    per archived month). The active ``log.md`` is rewritten to contain only
    entries dated within the current month.
    """
    log_path = cfg.vault_dir / "log.md"
    if not log_path.exists() or log_path.stat().st_size == 0:
        return

    current = current_month_prefix()
    archive_dir = cfg.vault_dir / "05_Archive" / "logs"
    archive_dir.mkdir(parents=True, exist_ok=True)

    keep_lines: list[str] = []
    archive_buckets: dict[str, list[str]] = {}
    target: list[str] | None = None  # which bucket the current line belongs to

    for line in log_path.read_text(encoding="utf-8").splitlines(keepends=True):
        m = _LOG_HEADER_RE.match(line)
        if m:
            month = m.group(1)
            target = keep_lines if month == current else archive_buckets.setdefault(month, [])
        if target is not None:
            target.append(line)

    log_path.write_text("".join(keep_lines), encoding="utf-8")
    for month, lines in archive_buckets.items():
        archive_path = archive_dir / f"{month}.md"
        with archive_path.open("a", encoding="utf-8") as f:
            f.writelines(lines)

    log_info(f"rotated log.md (kept current month: {current})")


__all__ = ["append_log", "rotate_log_if_needed"]
