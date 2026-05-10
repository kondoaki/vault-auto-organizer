from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from lib.common import Config, OrganizerError, log_error, log_info

from . import discover as discover_mod
from .sync import SyncResult, sync_repo


def _format_line(r: SyncResult) -> str:
    label = {
        "synced": "synced   ",
        "created": "created  ",
        "linked": "linked   ",
        "skipped-unchanged": "skipped  ",
        "skipped-missing-host": "skipped  ",
        "error": "ERROR    ",
    }[r.status]
    name = r.name.ljust(20)
    if r.status == "error":
        return f"{label} {name} - {r.message or 'unknown error'}"
    sha = r.sha or "       "
    suffix = ""
    if r.status == "skipped-unchanged":
        suffix = "  (unchanged since last sync)"
    elif r.status == "created":
        suffix = "  (new note)"
    elif r.status == "linked":
        suffix = "  (existing note adopted)"
    return f"{label} {name} @ {sha}{suffix}"


def _commit_changes(cfg: Config, results) -> None:
    """Commit only files this run wrote, scoped under the vault."""
    written = [
        r for r in results
        if r.note_path is not None and r.status in ("synced", "created", "linked")
    ]
    if not written:
        return

    paths_to_add = [str(r.note_path.relative_to(cfg.vault_dir)) for r in written]

    subprocess.run(
        ["git", "-C", str(cfg.vault_dir), "add", "--", *paths_to_add],
        check=True,
    )
    diff = subprocess.run(
        ["git", "-C", str(cfg.vault_dir), "diff", "--cached", "--name-only"],
        capture_output=True, text=True, check=True,
    )
    if not diff.stdout.strip():
        return

    if len(written) == 1:
        r = written[0]
        msg = f"project-sync: {r.name} @ {r.sha}"
    else:
        names = ", ".join(r.name for r in written)
        msg = f"project-sync: {len(written)} projects ({names})"

    subprocess.run(
        ["git", "-C", str(cfg.vault_dir),
         "-c", "user.email=auto-organizer@local",
         "-c", "user.name=auto-organizer",
         "commit", "-m", msg],
        check=True,
    )
    log_info(msg)


def main(argv, cfg: Config) -> int:
    parser = argparse.ArgumentParser(prog="project_sync")
    parser.add_argument("target", nargs="?", default=".")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args(argv)

    target = Path(args.target).expanduser().resolve()
    try:
        mode, repos = discover_mod.classify_target(target)
    except OrganizerError as e:
        sys.stderr.write(f"{type(e).__name__}: {e}\n")
        return e.exit_code

    log_info(f"project_sync: mode={mode}, repos={len(repos)}")

    results = []
    for repo in repos:
        try:
            r = sync_repo(cfg, repo, force=args.force)
        except OrganizerError as e:
            r = SyncResult(name=repo.name, status="error", message=str(e))
        except Exception as e:  # noqa: BLE001 — best-effort per repo
            log_error(f"unexpected error for {repo.name}: {e}")
            r = SyncResult(name=repo.name, status="error", message=str(e))
        results.append(r)
        print(_format_line(r))

    try:
        _commit_changes(cfg, results)
    except subprocess.CalledProcessError as e:
        log_error(f"git commit failed: {e}")

    n_err = sum(1 for r in results if r.status == "error")
    n_ok = len(results) - n_err
    sys.stderr.write(f"project_sync: {n_ok} ok, {n_err} errors\n")

    if n_err == 0:
        return 0
    return 1


__all__ = ["main"]
