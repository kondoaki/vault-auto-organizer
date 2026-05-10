from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from lib.project_sync import facts as facts_mod


def _git(repo: Path, *args: str, env: dict = None) -> str:
    full_env = os.environ.copy()
    full_env.update({
        "GIT_AUTHOR_NAME": "test", "GIT_AUTHOR_EMAIL": "t@e",
        "GIT_COMMITTER_NAME": "test", "GIT_COMMITTER_EMAIL": "t@e",
    })
    if env:
        full_env.update(env)
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True, capture_output=True, text=True, env=full_env,
    ).stdout


def _make_repo(path: Path, *, files: dict) -> None:
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["git", "-c", "init.defaultBranch=main", "init", "-q"],
        cwd=path, check=True,
    )
    for rel, content in files.items():
        f = path / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(content, encoding="utf-8")
    _git(path, "add", "-A")
    _git(path, "-c", "user.email=t@e", "-c", "user.name=t",
         "commit", "-q", "-m", "init")


def test_collect_basic_repo(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    repo = tmp_path / "Projects" / "foo"
    _make_repo(repo, files={
        "README.md": "# foo\n",
        "SPEC.md": "spec\n",
        "AGENTS.md": "agents\n",
        "docs/adr/0001-x.md": "adr\n",
        "docs/adr/0002-y.md": "adr\n",
    })
    f = facts_mod.collect_facts(repo)
    assert f.name == "foo"
    assert f.project_path == "~/Projects/foo"
    assert f.head_commit
    assert sorted(f.spec_files) == ["AGENTS.md", "README.md", "SPEC.md"]
    assert f.adr_dir == "docs/adr"
    assert sorted(f.adr_files) == ["0001-x.md", "0002-y.md"]
    assert f.exploration_mode is False


def test_exploration_mode_when_no_specs_or_adr(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    repo = tmp_path / "bar"
    _make_repo(repo, files={"src/main.py": "print('hi')\n"})
    f = facts_mod.collect_facts(repo)
    assert f.exploration_mode is True
    assert f.spec_files == []
    assert f.adr_dir is None
    assert f.adr_files == []


def test_no_origin_remote_yields_none(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    repo = tmp_path / "noremote"
    _make_repo(repo, files={"README.md": "x\n"})
    f = facts_mod.collect_facts(repo)
    assert f.project_repo is None


def test_origin_remote_captured(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    repo = tmp_path / "withremote"
    _make_repo(repo, files={"README.md": "x\n"})
    _git(repo, "remote", "add", "origin", "https://example.com/u/withremote.git")
    f = facts_mod.collect_facts(repo)
    assert f.project_repo == "https://example.com/u/withremote.git"


def test_recent_commits_string_lists_subjects(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    repo = tmp_path / "log"
    _make_repo(repo, files={"a.txt": "1\n"})
    (repo / "a.txt").write_text("2\n", encoding="utf-8")
    _git(repo, "add", "a.txt")
    _git(repo, "-c", "user.email=t@e", "-c", "user.name=t",
         "commit", "-q", "-m", "second commit")
    f = facts_mod.collect_facts(repo)
    assert "second commit" in f.recent_commits
    assert "init" in f.recent_commits


def test_adr_priority_decisions_when_no_adr(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    repo = tmp_path / "p2"
    _make_repo(repo, files={
        "README.md": "x\n",
        "docs/decisions/0001-foo.md": "x\n",
    })
    f = facts_mod.collect_facts(repo)
    assert f.adr_dir == "docs/decisions"
    assert f.adr_files == ["0001-foo.md"]


def test_to_yaml_block_renders_fields(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    repo = tmp_path / "y"
    _make_repo(repo, files={"README.md": "x\n"})
    f = facts_mod.collect_facts(repo)
    block = facts_mod.to_yaml_block(f, note_path="01_Projects/y.md", note_exists=True)
    assert "name: y" in block
    assert "note_path: 01_Projects/y.md" in block
    assert "note_exists: true" in block
    assert "exploration_mode:" in block
