from __future__ import annotations

import subprocess
from pathlib import Path

from lib.push import push_to_main


def test_push_noop_when_no_upstream(tmp_vault: Path, make_config, capsys) -> None:
    cfg = make_config(vault_dir=tmp_vault)
    # tmp_vault has no remote configured → returns silently.
    push_to_main(cfg)
    captured = capsys.readouterr()
    assert "no upstream configured" in captured.err


def test_push_success(tmp_path: Path, tmp_vault: Path, make_config, capsys) -> None:
    bare = tmp_path / "origin.git"
    subprocess.run(["git", "init", "--bare", "-q", str(bare)], check=True)
    subprocess.run(
        ["git", "-C", str(tmp_vault), "remote", "add", "origin", str(bare)],
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(tmp_vault), "branch", "-M", "main"], check=True
    )
    subprocess.run(
        ["git", "-C", str(tmp_vault), "push", "-q", "-u", "origin", "main"],
        check=True,
    )
    cfg = make_config(vault_dir=tmp_vault)
    push_to_main(cfg)
    err = capsys.readouterr().err
    assert "push complete" in err


def test_push_failure_does_not_raise(tmp_path: Path, tmp_vault: Path, make_config, capsys) -> None:
    bogus = tmp_path / "nonexistent.git"
    subprocess.run(
        ["git", "-C", str(tmp_vault), "remote", "add", "origin", str(bogus)],
        check=True,
    )
    # Configure upstream tracking even though the remote doesn't exist.
    subprocess.run(
        ["git", "-C", str(tmp_vault), "branch", "--set-upstream-to=origin/main"],
        capture_output=True,
    )
    cfg = make_config(vault_dir=tmp_vault)
    # Should not raise even on push failure.
    push_to_main(cfg)
