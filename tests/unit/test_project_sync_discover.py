from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from lib.project_sync import discover


def _git_init(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["git", "-c", "init.defaultBranch=main", "init", "-q"],
        cwd=path, check=True,
    )


def test_single_repo(tmp_path: Path):
    repo = tmp_path / "foo"
    _git_init(repo)
    mode, repos = discover.classify_target(repo)
    assert mode == "single"
    assert repos == [repo.resolve()]


def test_bulk_with_two_children(tmp_path: Path):
    parent = tmp_path / "Projects"
    parent.mkdir()
    _git_init(parent / "foo")
    _git_init(parent / "bar")
    (parent / "not-a-repo").mkdir()
    mode, repos = discover.classify_target(parent)
    assert mode == "bulk"
    names = sorted(p.name for p in repos)
    assert names == ["bar", "foo"]


def test_fatal_when_no_git_anywhere(tmp_path: Path):
    parent = tmp_path / "empty"
    parent.mkdir()
    with pytest.raises(discover.NoRepositoriesFound):
        discover.classify_target(parent)


def test_fatal_when_target_does_not_exist(tmp_path: Path):
    with pytest.raises(discover.InvalidTarget):
        discover.classify_target(tmp_path / "nope")


def test_bulk_does_not_recurse_two_levels(tmp_path: Path):
    parent = tmp_path / "Projects"
    parent.mkdir()
    nested = parent / "work" / "deep"
    _git_init(nested)
    with pytest.raises(discover.NoRepositoriesFound):
        discover.classify_target(parent)


def test_bulk_skips_bare_repo(tmp_path: Path):
    parent = tmp_path / "Projects"
    parent.mkdir()
    bare = parent / "bare.git"
    bare.mkdir()
    subprocess.run(
        ["git", "-c", "init.defaultBranch=main", "init", "--bare", "-q"],
        cwd=bare, check=True,
    )
    _git_init(parent / "real")
    mode, repos = discover.classify_target(parent)
    assert [p.name for p in repos] == ["real"]
