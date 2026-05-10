# project_sync Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an ad-hoc CLI (`scripts/project_sync.py`) that snapshots external git project state into Vault notes under `01_Projects/`, idempotently rewriting only a marked region while preserving everything else.

**Architecture:** Sibling of `daily_ingest.py` / `weekly_lint.py`. New feature module under `scripts/lib/project_sync/` with five files (discover, facts, note, sync, cli) plus a new prompt at `scripts/lib/agent/prompts/project_sync.md`. Direct write to the Vault (no worktree); commits scoped to files this run touched. Reuses existing agent backends but with cwd=repo and `--add-dir <vault>`.

**Tech Stack:** Python 3.11+, pytest, stdlib only (no PyYAML — minimal scalar-only frontmatter parser). Existing claude/opencode backends.

---

## Conventions

- Tests live under `tests/unit/test_project_sync_*.py` and `tests/integration/test_project_sync_e2e.py`.
- All test commands assume `make test-unit` / `make test-integration` work via `.venv-dev/bin/python -m pytest`.
- Imports inside `scripts/lib/project_sync/` use `from lib.common import …` matching the existing convention (see `scripts/lib/agent/__init__.py`).
- When the plan says "commit", run **`git status` first** to confirm the change set, then add specific files (not `git add -A`). Never `git push`. Per CLAUDE.md, never `git commit` on `main` without explicit user permission — we are on `feature/project_synct`, which is fine.

---

## Task 1: Frontmatter + marker-block module (`note.py`)

**Files:**
- Create: `scripts/lib/project_sync/__init__.py` (empty for now)
- Create: `scripts/lib/project_sync/note.py`
- Create: `tests/unit/test_project_sync_note.py`

This module owns the round-trip: parsing a note into `(frontmatter dict, body)`, rendering back to text, locating the marker block, validating its shape, and resolving the note path (folder-form vs file-form).

- [ ] **Step 1: Write failing tests for parse/render round-trip and marker validation**

```python
# tests/unit/test_project_sync_note.py
from __future__ import annotations

from pathlib import Path

import pytest

from lib.project_sync import note as note_mod


def test_parse_note_with_frontmatter_and_body():
    text = (
        "---\n"
        "project_path: ~/Projects/foo\n"
        "last_synced_commit: a1b2c3d\n"
        "---\n"
        "\n"
        "body line\n"
    )
    parsed = note_mod.parse_note_text(text)
    assert parsed.frontmatter == {
        "project_path": "~/Projects/foo",
        "last_synced_commit": "a1b2c3d",
    }
    assert parsed.body == "\nbody line\n"


def test_parse_note_without_frontmatter():
    parsed = note_mod.parse_note_text("just body\n")
    assert parsed.frontmatter == {}
    assert parsed.body == "just body\n"


def test_render_round_trips():
    src = (
        "---\n"
        "a: 1\n"
        "b: two words\n"
        "---\n"
        "\nhello\n"
    )
    parsed = note_mod.parse_note_text(src)
    assert note_mod.render_note(parsed) == src


def test_update_frontmatter_fields_preserves_order_and_unknown_keys():
    parsed = note_mod.parse_note_text(
        "---\n"
        "title: Foo\n"
        "project_path: ~/Projects/foo\n"
        "last_synced_commit: old\n"
        "---\n"
        "body\n"
    )
    updated = note_mod.update_frontmatter_fields(
        parsed,
        last_synced_commit="new",
        last_synced="2026-05-10 14:32",
    )
    assert updated.frontmatter["title"] == "Foo"
    assert updated.frontmatter["last_synced_commit"] == "new"
    assert updated.frontmatter["last_synced"] == "2026-05-10 14:32"
    # title must remain first; new keys appended at end
    keys = list(updated.frontmatter.keys())
    assert keys[0] == "title"


def test_has_valid_markers_true_when_balanced():
    body = (
        "preamble\n"
        "<!-- vault-sync:start -->\n"
        "snapshot\n"
        "<!-- vault-sync:end -->\n"
        "tail\n"
    )
    assert note_mod.has_valid_markers(body) is True


def test_has_valid_markers_false_when_only_one():
    assert note_mod.has_valid_markers("<!-- vault-sync:start -->\nx\n") is False
    assert note_mod.has_valid_markers("x\n<!-- vault-sync:end -->\n") is False


def test_has_valid_markers_false_when_out_of_order():
    body = (
        "<!-- vault-sync:end -->\n"
        "<!-- vault-sync:start -->\n"
    )
    assert note_mod.has_valid_markers(body) is False


def test_resolve_note_path_prefers_folder_form_when_dir_exists(tmp_path: Path):
    vault = tmp_path / "vault"
    (vault / "01_Projects" / "foo").mkdir(parents=True)
    p = note_mod.resolve_note_path(vault, "foo")
    assert p == vault / "01_Projects" / "foo" / "foo.md"


def test_resolve_note_path_falls_back_to_file_form(tmp_path: Path):
    vault = tmp_path / "vault"
    (vault / "01_Projects").mkdir(parents=True)
    p = note_mod.resolve_note_path(vault, "foo")
    assert p == vault / "01_Projects" / "foo.md"


def test_default_skeleton_contains_marker_block():
    text = note_mod.default_skeleton()
    assert "<!-- vault-sync:start -->" in text
    assert "<!-- vault-sync:end -->" in text
    assert note_mod.has_valid_markers(text)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv-dev/bin/python -m pytest tests/unit/test_project_sync_note.py -v`
Expected: ImportError / AttributeError (module not yet implemented).

- [ ] **Step 3: Implement `note.py`**

```python
# scripts/lib/project_sync/note.py
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

MARKER_START = "<!-- vault-sync:start -->"
MARKER_END = "<!-- vault-sync:end -->"


@dataclass
class ParsedNote:
    frontmatter: dict[str, str] = field(default_factory=dict)
    body: str = ""


def parse_note_text(text: str) -> ParsedNote:
    """Split `---`-delimited scalar frontmatter from the body.

    Only `key: value` pairs are recognized. Lines without `:` inside the
    frontmatter region are skipped silently.
    """
    if not text.startswith("---\n"):
        return ParsedNote(frontmatter={}, body=text)
    rest = text[len("---\n"):]
    end = rest.find("\n---\n")
    if end == -1:
        # malformed — treat whole thing as body
        return ParsedNote(frontmatter={}, body=text)
    fm_block = rest[:end]
    body = rest[end + len("\n---\n"):]
    fm: dict[str, str] = {}
    for line in fm_block.splitlines():
        if ":" not in line:
            continue
        k, _, v = line.partition(":")
        fm[k.strip()] = v.strip()
    return ParsedNote(frontmatter=fm, body=body)


def render_note(parsed: ParsedNote) -> str:
    if not parsed.frontmatter:
        return parsed.body
    lines = [f"{k}: {v}" for k, v in parsed.frontmatter.items()]
    return "---\n" + "\n".join(lines) + "\n---\n" + parsed.body


def update_frontmatter_fields(parsed: ParsedNote, **fields: str) -> ParsedNote:
    """Return a new ParsedNote with the given keys set/replaced.

    Order: existing keys keep their position; new keys are appended.
    """
    fm = dict(parsed.frontmatter)
    for k, v in fields.items():
        fm[k] = v
    return ParsedNote(frontmatter=fm, body=parsed.body)


def has_valid_markers(body: str) -> bool:
    starts = [i for i in range(len(body)) if body.startswith(MARKER_START, i)]
    ends = [i for i in range(len(body)) if body.startswith(MARKER_END, i)]
    if len(starts) != 1 or len(ends) != 1:
        return False
    return starts[0] < ends[0]


def resolve_note_path(vault_dir: Path, name: str) -> Path:
    """Folder-form preferred if `01_Projects/<name>/` exists; else file-form."""
    folder = vault_dir / "01_Projects" / name
    if folder.is_dir():
        return folder / f"{name}.md"
    return vault_dir / "01_Projects" / f"{name}.md"


def default_skeleton() -> str:
    """Initial body for a brand-new note: empty marker block, plus a Notes
    region the user can extend. Frontmatter is added by the caller.
    """
    return (
        f"\n{MARKER_START}\n"
        "## Project Snapshot\n"
        "*Auto-generated by project_sync. Do not edit between markers — "
        "changes will be overwritten on next sync.*\n"
        f"{MARKER_END}\n\n"
        "## Notes\n"
        "<!-- Free-form. project_sync never touches this region. -->\n"
    )


__all__ = [
    "MARKER_START",
    "MARKER_END",
    "ParsedNote",
    "parse_note_text",
    "render_note",
    "update_frontmatter_fields",
    "has_valid_markers",
    "resolve_note_path",
    "default_skeleton",
]
```

Also create empty `scripts/lib/project_sync/__init__.py`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv-dev/bin/python -m pytest tests/unit/test_project_sync_note.py -v`
Expected: all 9 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/lib/project_sync/__init__.py scripts/lib/project_sync/note.py tests/unit/test_project_sync_note.py
git commit -m "feat(project_sync): note frontmatter/marker module"
```

---

## Task 2: Discover module (`discover.py`)

**Files:**
- Create: `scripts/lib/project_sync/discover.py`
- Create: `tests/unit/test_project_sync_discover.py`

Classify a TARGET path: single repo (has `.git/`), bulk (children with `.git/`), or fatal. Depth = exactly 1; submodules and bare repos skipped.

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/test_project_sync_discover.py
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv-dev/bin/python -m pytest tests/unit/test_project_sync_discover.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement `discover.py`**

```python
# scripts/lib/project_sync/discover.py
from __future__ import annotations

from pathlib import Path
from typing import Literal

from lib.common import OrganizerError

Mode = Literal["single", "bulk"]


class InvalidTarget(OrganizerError):
    exit_code = 2


class NoRepositoriesFound(OrganizerError):
    exit_code = 2


def _is_working_repo(path: Path) -> bool:
    """True iff `path/.git` exists as a directory (worktree, not bare)."""
    return path.is_dir() and (path / ".git").is_dir()


def classify_target(target: Path) -> tuple[Mode, list[Path]]:
    """Return ('single', [target]) or ('bulk', [child, ...]).

    Raises InvalidTarget if target does not resolve to a directory.
    Raises NoRepositoriesFound if neither single nor bulk apply.
    """
    if not target.exists() or not target.is_dir():
        raise InvalidTarget(f"target is not a directory: {target}")
    target = target.resolve()
    if _is_working_repo(target):
        return "single", [target]
    children = sorted(p for p in target.iterdir() if _is_working_repo(p))
    if not children:
        raise NoRepositoriesFound(f"no git repositories found in {target}")
    return "bulk", children


__all__ = ["Mode", "InvalidTarget", "NoRepositoriesFound", "classify_target"]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv-dev/bin/python -m pytest tests/unit/test_project_sync_discover.py -v`
Expected: all 6 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/lib/project_sync/discover.py tests/unit/test_project_sync_discover.py
git commit -m "feat(project_sync): TARGET classification (single/bulk)"
```

---

## Task 3: Facts collection (`facts.py`)

**Files:**
- Create: `scripts/lib/project_sync/facts.py`
- Create: `tests/unit/test_project_sync_facts.py`

Per spec §6: gather candidate spec files, ADR directory + filenames, git remote, default branch, HEAD sha, recent commits, exploration_mode flag. Pure function over a real git repo.

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/test_project_sync_facts.py
from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from lib.project_sync import facts as facts_mod


def _git(repo: Path, *args: str, env: dict | None = None) -> str:
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


def _make_repo(path: Path, *, files: dict[str, str]) -> None:
    path.mkdir(parents=True, exist_ok=True)
    _git(path.parent, "init", "-q") if False else None
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv-dev/bin/python -m pytest tests/unit/test_project_sync_facts.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement `facts.py`**

```python
# scripts/lib/project_sync/facts.py
from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pathlib import Path

_SPEC_GLOBS_ROOT = ("SPEC.md", "README.md", "ARCHITECTURE.md", "AGENTS.md", "CLAUDE.md")
_SPEC_PREFIX_ROOT = ("SPEC", "README")  # SPEC*.md / README*.md
_ADR_PRIORITY = ("docs/adr", "docs/decisions", "docs/architecture/decisions")


@dataclass
class RepoFacts:
    name: str
    project_path: str  # ~-relative if under $HOME
    project_repo: str | None
    default_branch: str | None
    head_commit: str
    spec_files: list[str] = field(default_factory=list)
    adr_dir: str | None = None
    adr_files: list[str] = field(default_factory=list)
    recent_commits: str = ""
    exploration_mode: bool = False


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True, text=True, check=True,
    ).stdout


def _git_quiet(repo: Path, *args: str) -> str | None:
    r = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True, text=True,
    )
    return r.stdout.strip() if r.returncode == 0 else None


def _home_relative(path: Path) -> str:
    home = Path.home()
    try:
        rel = path.resolve().relative_to(home.resolve())
        return f"~/{rel}"
    except ValueError:
        return str(path)


def _candidate_spec_files(repo: Path) -> list[str]:
    found: list[str] = []
    seen: set[str] = set()
    for name in _SPEC_GLOBS_ROOT:
        if (repo / name).is_file() and name not in seen:
            found.append(name)
            seen.add(name)
    # SPEC*.md / README*.md at root
    for entry in sorted(repo.iterdir()):
        if not entry.is_file() or not entry.name.endswith(".md"):
            continue
        for prefix in _SPEC_PREFIX_ROOT:
            if entry.name.startswith(prefix) and entry.name not in seen:
                found.append(entry.name)
                seen.add(entry.name)
    # docs/SPEC*.md
    docs = repo / "docs"
    if docs.is_dir():
        for entry in sorted(docs.iterdir()):
            if entry.is_file() and entry.name.startswith("SPEC") and entry.name.endswith(".md"):
                rel = f"docs/{entry.name}"
                if rel not in seen:
                    found.append(rel)
                    seen.add(rel)
    return found


def _adr_dir_and_files(repo: Path) -> tuple[str | None, list[str]]:
    for rel in _ADR_PRIORITY:
        d = repo / rel
        if d.is_dir():
            files = sorted(p.name for p in d.iterdir() if p.is_file() and p.suffix == ".md")
            return rel, files
    return None, []


def collect_facts(repo: Path) -> RepoFacts:
    head = _git(repo, "rev-parse", "HEAD").strip()
    short = _git(repo, "rev-parse", "--short", "HEAD").strip()
    project_repo = _git_quiet(repo, "remote", "get-url", "origin")
    default_branch = _git_quiet(
        repo, "symbolic-ref", "--short", "refs/remotes/origin/HEAD"
    )
    if default_branch and default_branch.startswith("origin/"):
        default_branch = default_branch[len("origin/"):]
    if not default_branch:
        default_branch = _git_quiet(repo, "symbolic-ref", "--short", "HEAD")

    recent_commits = _git(
        repo, "log", "--oneline", "--since=14 days ago", "--date=short",
        "--pretty=format:%h %ad %s",
    ).strip()

    spec_files = _candidate_spec_files(repo)
    adr_dir, adr_files = _adr_dir_and_files(repo)
    exploration_mode = (not spec_files) and (adr_dir is None)

    return RepoFacts(
        name=repo.name,
        project_path=_home_relative(repo),
        project_repo=project_repo or None,
        default_branch=default_branch,
        head_commit=short,
        spec_files=spec_files,
        adr_dir=adr_dir,
        adr_files=adr_files,
        recent_commits=recent_commits,
        exploration_mode=exploration_mode,
    )


def to_yaml_block(facts: RepoFacts, *, note_path: str, note_exists: bool) -> str:
    """Render facts as the YAML block injected into the agent prompt.

    Hand-rolled (no PyYAML dep). Only scalar/list fields; recent_commits is
    emitted as a literal block scalar so the agent gets multi-line text.
    """
    lines = [f"name: {facts.name}", f"project_path: {facts.project_path}"]
    if facts.project_repo:
        lines.append(f"project_repo: {facts.project_repo}")
    if facts.default_branch:
        lines.append(f"default_branch: {facts.default_branch}")
    lines.append(f"head_commit: {facts.head_commit}")
    if facts.spec_files:
        lines.append("spec_files:")
        for s in facts.spec_files:
            lines.append(f"  - {s}")
    else:
        lines.append("spec_files: []")
    if facts.adr_dir:
        lines.append(f"adr_dir: {facts.adr_dir}")
        lines.append("adr_files:")
        for a in facts.adr_files:
            lines.append(f"  - {a}")
    else:
        lines.append("adr_dir: ~")
        lines.append("adr_files: []")
    lines.append("recent_commits: |")
    if facts.recent_commits:
        for ln in facts.recent_commits.splitlines():
            lines.append(f"  {ln}")
    lines.append(f"exploration_mode: {'true' if facts.exploration_mode else 'false'}")
    lines.append(f"note_path: {note_path}")
    lines.append(f"note_exists: {'true' if note_exists else 'false'}")
    return "\n".join(lines) + "\n"


__all__ = ["RepoFacts", "collect_facts", "to_yaml_block"]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv-dev/bin/python -m pytest tests/unit/test_project_sync_facts.py -v`
Expected: all 7 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/lib/project_sync/facts.py tests/unit/test_project_sync_facts.py
git commit -m "feat(project_sync): collect git/spec/ADR facts per repo"
```

---

## Task 4: Skip-if-unchanged + per-repo state detection

**Files:**
- Create: `tests/unit/test_project_sync_skip.py`
- Modify: `scripts/lib/project_sync/note.py` (add a small helper used by sync)

The skip-if-unchanged logic is a tiny pure function over the parsed note + repo HEAD. Test it before wiring into sync.

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/test_project_sync_skip.py
from __future__ import annotations

from lib.project_sync import note as note_mod


def test_state_new_when_note_missing(tmp_path):
    p = tmp_path / "missing.md"
    state = note_mod.classify_note_state(p, repo_path=tmp_path / "fake")
    assert state == "new"


def test_state_linked_when_no_project_path(tmp_path):
    p = tmp_path / "x.md"
    p.write_text("---\ntitle: hi\n---\nbody\n", encoding="utf-8")
    state = note_mod.classify_note_state(p, repo_path=tmp_path / "fake")
    assert state == "adopt"


def test_state_registered_when_project_path_matches(tmp_path):
    repo = tmp_path / "Projects" / "foo"
    repo.mkdir(parents=True)
    p = tmp_path / "n.md"
    p.write_text(
        f"---\nproject_path: {repo}\n---\nx\n", encoding="utf-8"
    )
    state = note_mod.classify_note_state(p, repo_path=repo)
    assert state == "registered"


def test_state_registered_when_project_path_uses_tilde(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    repo = tmp_path / "Projects" / "foo"
    repo.mkdir(parents=True)
    p = tmp_path / "n.md"
    p.write_text("---\nproject_path: ~/Projects/foo\n---\nx\n", encoding="utf-8")
    state = note_mod.classify_note_state(p, repo_path=repo)
    assert state == "registered"


def test_state_mismatch_when_project_path_points_elsewhere(tmp_path):
    other = tmp_path / "other"
    other.mkdir()
    p = tmp_path / "n.md"
    p.write_text(
        f"---\nproject_path: {other}\n---\nx\n", encoding="utf-8"
    )
    state = note_mod.classify_note_state(p, repo_path=tmp_path / "actual")
    assert state == "mismatch"


def test_should_skip_when_commit_matches(tmp_path):
    p = tmp_path / "n.md"
    p.write_text(
        "---\n"
        "project_path: /tmp/x\n"
        "last_synced_commit: abc1234\n"
        "---\nbody\n",
        encoding="utf-8",
    )
    parsed = note_mod.parse_note_text(p.read_text())
    assert note_mod.should_skip(parsed, head_short="abc1234") is True
    assert note_mod.should_skip(parsed, head_short="differen") is False


def test_should_skip_false_when_no_last_synced(tmp_path):
    parsed = note_mod.parse_note_text("---\ntitle: x\n---\nbody\n")
    assert note_mod.should_skip(parsed, head_short="abc1234") is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv-dev/bin/python -m pytest tests/unit/test_project_sync_skip.py -v`
Expected: AttributeError on `classify_note_state` / `should_skip`.

- [ ] **Step 3: Add helpers to `note.py`**

Append to `scripts/lib/project_sync/note.py`:

```python
import os
from typing import Literal

NoteState = Literal["new", "adopt", "registered", "mismatch"]


def _expand(path_str: str) -> Path:
    return Path(os.path.expanduser(path_str)).resolve()


def classify_note_state(note_path: Path, *, repo_path: Path) -> NoteState:
    """Classify the relationship between an existing note and a repo.

    - "new"        : note file does not exist
    - "adopt"      : note exists but has no project_path frontmatter
    - "registered" : project_path resolves to repo_path
    - "mismatch"   : project_path resolves to something else
    """
    if not note_path.exists():
        return "new"
    parsed = parse_note_text(note_path.read_text(encoding="utf-8"))
    pp = parsed.frontmatter.get("project_path")
    if not pp:
        return "adopt"
    if _expand(pp) == repo_path.resolve():
        return "registered"
    return "mismatch"


def should_skip(parsed: ParsedNote, *, head_short: str) -> bool:
    last = parsed.frontmatter.get("last_synced_commit", "").strip()
    if not last:
        return False
    return last == head_short
```

Also extend `__all__` to include `NoteState`, `classify_note_state`, `should_skip`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv-dev/bin/python -m pytest tests/unit/test_project_sync_skip.py -v`
Expected: all 7 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/lib/project_sync/note.py tests/unit/test_project_sync_skip.py
git commit -m "feat(project_sync): note-state classification and skip-if-unchanged"
```

---

## Task 5: Agent prompt + project-sync-specific invocation

**Files:**
- Create: `scripts/lib/agent/prompts/project_sync.md`
- Create: `scripts/lib/project_sync/agent.py`

The existing `lib.agent.invoke_agent` is hardwired to cwd=workbench / `--add-dir workbench`. project_sync needs cwd=repo (so the agent's `Read`/`Bash` see source) and `--add-dir vault` (so it can write the note). New thin wrapper.

The prompt is rendered with `$FACTS_BLOCK` substitution in addition to the existing `$RUN_DATE`.

- [ ] **Step 1: Write the prompt file**

Create `scripts/lib/agent/prompts/project_sync.md`:

```markdown
# project_sync — repository snapshot ($RUN_DATE)

You are writing a snapshot of one external git repository into a single Vault
note. The repository is mounted at the current working directory; the Vault
is reachable at the absolute paths used below.

## Facts (do not modify these — they are inputs)

```yaml
$FACTS_BLOCK
```

## What you may modify

You may modify **only the region inside `<!-- vault-sync:start -->` and
`<!-- vault-sync:end -->`** in the file at `note_path`. You must:

- Preserve the markers themselves verbatim.
- Never touch the YAML frontmatter (Python rewrites it after you finish).
- Never touch any text outside the marker block. Other sections are
  human-owned.

If `note_exists: true`, read the note first with `Read` to see the current
shape. If `note_exists: false`, the note has already been pre-written with an
empty marker block — you only need to fill it.

## What to write between the markers

Render exactly four sections (`### Purpose`, `### Current spec`,
`### ADRs / decisions`, `### Recent activity (last 14 days)`). Each is
mandatory; if you have no source material for a section, write `*(none)*`
rather than fabricating.

### Normal mode (`exploration_mode: false`)

Read the listed `spec_files` and ADR files (under `adr_dir`) via the `Read`
tool. Summarize:

- **Purpose**: 2–3 lines of what this project is, in plain prose.
- **Current spec**: a short excerpt or summary from the spec files.
- **ADRs / decisions**: bulleted list of `mtime — adr_dir/<file>` (use
  `Bash ls -l` to get mtimes if needed).
- **Recent activity (last 14 days)**: reproduce `recent_commits` as a
  bulleted list, oldest last.

### Exploration mode (`exploration_mode: true`)

No candidate spec or ADR files were found. You may explore the repository:

- Use `Bash ls` / `Bash find` only to map structure (max depth 2 from repo
  root).
- Read package manifests (`package.json`, `pyproject.toml`, `Cargo.toml`,
  `go.mod`, `Gemfile`, `composer.json`) in full if present.
- Read at most 10 source files, max 50 lines each.
- If a section still lacks source material after exploration, write
  `*(insufficient information)*`. Never invent.

## Header inside the marker block

Open the block with:

```markdown
## Project Snapshot
*Auto-generated by project_sync. Do not edit between markers — changes will
be overwritten on next sync.*
```

Then the four sections. Close with the end marker.

## Tools

You have only `Bash`, `Read`, `Write`. No network. The Vault note is the
only file outside this repo you may write.
```

- [ ] **Step 2: Implement the agent invocation wrapper**

Create `scripts/lib/project_sync/agent.py`:

```python
from __future__ import annotations

import os
import subprocess
from pathlib import Path

from lib.common import AgentError, Config, current_iso_date, log_info

_PROMPT_PATH = (
    Path(__file__).resolve().parent.parent / "agent" / "prompts" / "project_sync.md"
)
_OPENCODE_CONFIG_DIR = (
    Path(__file__).resolve().parent.parent
    / "agent" / "backends" / "opencode_config"
)


def render_prompt(facts_block: str) -> str:
    raw = _PROMPT_PATH.read_text(encoding="utf-8")
    return (
        raw.replace("$FACTS_BLOCK", facts_block)
           .replace("$RUN_DATE", current_iso_date())
    )


def invoke_for_repo(cfg: Config, *, repo_path: Path, prompt_text: str) -> None:
    """Invoke the configured agent backend with cwd=repo, --add-dir=vault."""
    log_info(
        f"invoking agent (backend={cfg.backend}) for repo {repo_path.name}"
    )
    if cfg.backend == "claude":
        result = subprocess.run(
            [
                cfg.agent_bin,
                "-p", prompt_text,
                "--allowedTools", "Bash,Write,Read",
                "--add-dir", str(cfg.vault_dir),
            ],
            cwd=str(repo_path),
        )
        if result.returncode != 0:
            raise AgentError(f"claude exited {result.returncode}")
    elif cfg.backend == "opencode":
        env = os.environ.copy()
        env["OPENCODE_CONFIG_DIR"] = str(_OPENCODE_CONFIG_DIR)
        result = subprocess.run(
            [cfg.agent_bin, "run", prompt_text, "--dangerously-skip-permissions"],
            cwd=str(repo_path),
            env=env,
        )
        if result.returncode != 0:
            raise AgentError(f"opencode exited {result.returncode}")
    else:
        from lib.common import OrganizerError
        raise OrganizerError(f"unknown backend: {cfg.backend}")


__all__ = ["render_prompt", "invoke_for_repo"]
```

- [ ] **Step 3: Sanity-check imports**

Run: `.venv-dev/bin/python -c "from lib.project_sync.agent import render_prompt, invoke_for_repo; print('ok')"`
Expected: `ok` (with `PYTHONPATH=scripts` if needed; the conftest does this for tests).

If the import fails outside pytest context, that's expected — the test in Task 7 will exercise the real path.

- [ ] **Step 4: Commit**

```bash
git add scripts/lib/agent/prompts/project_sync.md scripts/lib/project_sync/agent.py
git commit -m "feat(project_sync): agent prompt and per-repo invocation"
```

---

## Task 6: Per-repo orchestration (`sync.py`)

**Files:**
- Create: `scripts/lib/project_sync/sync.py`

Pure orchestration of one repo: classify state, skip-if-unchanged, ensure skeleton, invoke agent, validate marker block, deterministically rewrite frontmatter. Returns a `SyncResult`. No git commit happens here — the CLI batches commits.

This task has no unit test of its own; it's exercised by the e2e test in Task 8 (the orchestrator's branches are mostly thin glue, and stubbing the agent requires the same plumbing as e2e). Keep the code small and obviously correct.

- [ ] **Step 1: Implement `sync.py`**

```python
# scripts/lib/project_sync/sync.py
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal

from lib.common import AgentError, Config, log_info

from . import agent as agent_mod
from . import facts as facts_mod
from . import note as note_mod

Status = Literal[
    "synced", "created", "linked", "skipped-unchanged", "skipped-missing-host",
    "error",
]


@dataclass
class SyncResult:
    name: str
    status: Status
    sha: str | None = None
    note_path: Path | None = None  # absolute; CLI uses this for `git add`
    message: str | None = None


def sync_repo(cfg: Config, repo_path: Path, *, force: bool) -> SyncResult:
    name = repo_path.name
    note_path = note_mod.resolve_note_path(cfg.vault_dir, name)
    note_path.parent.mkdir(parents=True, exist_ok=True)

    state = note_mod.classify_note_state(note_path, repo_path=repo_path)

    if state == "mismatch":
        existing = note_mod.parse_note_text(
            note_path.read_text(encoding="utf-8")
        )
        other = existing.frontmatter.get("project_path", "?")
        return SyncResult(
            name=name, status="error", sha=None,
            message=f"already linked to {other}",
        )

    facts = facts_mod.collect_facts(repo_path)

    if state == "registered" and not force:
        existing = note_mod.parse_note_text(
            note_path.read_text(encoding="utf-8")
        )
        if note_mod.should_skip(existing, head_short=facts.head_commit):
            return SyncResult(
                name=name, status="skipped-unchanged",
                sha=facts.head_commit, note_path=note_path,
            )

    note_existed_before = note_path.exists()

    if state in ("registered", "adopt"):
        existing = note_mod.parse_note_text(
            note_path.read_text(encoding="utf-8")
        )
        if not note_mod.has_valid_markers(existing.body):
            if note_mod.MARKER_START in existing.body or note_mod.MARKER_END in existing.body:
                return SyncResult(
                    name=name, status="error",
                    message="marker block malformed; repair manually",
                )
            existing = note_mod.ParsedNote(
                frontmatter=existing.frontmatter,
                body=existing.body.rstrip() + "\n\n" + note_mod.default_skeleton(),
            )
            note_path.write_text(
                note_mod.render_note(existing), encoding="utf-8"
            )
    else:  # state == "new"
        skeleton_body = note_mod.default_skeleton()
        bootstrap = note_mod.ParsedNote(
            frontmatter={"project_path": facts.project_path},
            body=skeleton_body,
        )
        note_path.write_text(
            note_mod.render_note(bootstrap), encoding="utf-8"
        )

    note_exists_for_agent = note_existed_before
    yaml_block = facts_mod.to_yaml_block(
        facts,
        note_path=str(note_path.relative_to(cfg.vault_dir)),
        note_exists=note_exists_for_agent,
    )
    prompt_text = agent_mod.render_prompt(yaml_block)

    try:
        agent_mod.invoke_for_repo(
            cfg, repo_path=repo_path, prompt_text=prompt_text,
        )
    except AgentError as e:
        return SyncResult(
            name=name, status="error",
            message=f"agent failed: {e}", note_path=note_path,
        )

    after = note_mod.parse_note_text(
        note_path.read_text(encoding="utf-8")
    )
    if not note_mod.has_valid_markers(after.body):
        return SyncResult(
            name=name, status="error",
            message="agent corrupted marker block",
            note_path=note_path,
        )

    final = note_mod.update_frontmatter_fields(
        after,
        project_path=facts.project_path,
        **({"project_repo": facts.project_repo} if facts.project_repo else {}),
        last_synced=datetime.now().strftime("%Y-%m-%d %H:%M"),
        last_synced_commit=facts.head_commit,
    )
    note_path.write_text(note_mod.render_note(final), encoding="utf-8")

    if state == "new":
        status: Status = "created"
    elif state == "adopt":
        status = "linked"
    else:
        status = "synced"

    log_info(f"{status} {name} @ {facts.head_commit}")
    return SyncResult(
        name=name, status=status, sha=facts.head_commit, note_path=note_path,
    )


__all__ = ["Status", "SyncResult", "sync_repo"]
```

- [ ] **Step 2: Confirm imports resolve**

Run: `.venv-dev/bin/python -c "import sys; sys.path.insert(0, 'scripts'); from lib.project_sync.sync import sync_repo; print('ok')"`
Expected: `ok`.

- [ ] **Step 3: Commit**

```bash
git add scripts/lib/project_sync/sync.py
git commit -m "feat(project_sync): per-repo orchestration"
```

---

## Task 7: CLI entry frame

**Files:**
- Create: `scripts/lib/project_sync/cli.py`
- Create: `scripts/project_sync.py`

CLI parses TARGET + `--force`, dispatches discover, runs `sync_repo` per result, prints one stdout line per repo, batches the final git commit, returns aggregated exit code per spec §3.2 (0 success, 1 partial errors, 2 fatal).

- [ ] **Step 1: Implement `cli.py`**

```python
# scripts/lib/project_sync/cli.py
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


def _commit_changes(cfg: Config, results: list[SyncResult]) -> None:
    """Commit only files this run wrote, scoped under the vault."""
    paths_to_add: list[str] = []
    written: list[SyncResult] = [
        r for r in results
        if r.note_path is not None and r.status in ("synced", "created", "linked")
    ]
    if not written:
        return

    for r in written:
        rel = r.note_path.relative_to(cfg.vault_dir)
        paths_to_add.append(str(rel))

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


def main(argv: list[str], cfg: Config) -> int:
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

    results: list[SyncResult] = []
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
    if n_ok > 0:
        return 1
    return 1  # all errored — still 1 (fatal is reserved for invalid TARGET)


__all__ = ["main"]
```

- [ ] **Step 2: Implement the entry frame**

Create `scripts/project_sync.py`:

```python
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


def main(argv: list[str]) -> int:
    cfg = load_config()
    return cli_main(argv, cfg)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
```

- [ ] **Step 3: Make it executable**

```bash
chmod +x /Users/akihiro/Projects/vault-auto-organizer/scripts/project_sync.py
```

- [ ] **Step 4: Commit**

```bash
git add scripts/lib/project_sync/cli.py scripts/project_sync.py
git commit -m "feat(project_sync): CLI entry frame and output formatting"
```

---

## Task 8: End-to-end integration test

**Files:**
- Modify: `tests/fixtures/claude-mock/claude` (add a `project-sync` mode)
- Create: `tests/integration/test_project_sync_e2e.py`

The mock currently knows three modes (`move-inbox-file`, `noop`, `fail`). Add a `project-sync` mode that:
- Detects the project_sync prompt by presence of the literal `project_sync — repository snapshot` header (or a marker we add).
- Reads `note_path:` out of the embedded YAML, resolves it via `--add-dir <vault>`, and rewrites the marker block with placeholder content.

Adapter point: the existing modes assume cwd=workbench (verified by the `$PWD == $add_dir` check). For project_sync that check would fail (cwd=repo, add_dir=vault). Relax the check to: when mode is `project-sync`, only require that `--add-dir` is set; otherwise keep the strict equality check.

- [ ] **Step 1: Edit the mock**

Replace the body of `tests/fixtures/claude-mock/claude` with:

```bash
#!/usr/bin/env bash
# Test stub for the `claude` CLI. Behavior controlled by CLAUDE_MOCK_MODE:
#   move-inbox-file → move first file in <wb>/00_Inbox to 05_Archive/
#   noop            → do nothing
#   fail            → exit 1
#   project-sync    → fill the marker block in the note named in the prompt
#
# We capture --add-dir, --allowedTools, and the -p prompt text.
set -euo pipefail
add_dir=""
allowed_tools=""
prompt=""
while [ $# -gt 0 ]; do
    case "$1" in
        --add-dir) add_dir="$2"; shift 2 ;;
        --allowedTools) allowed_tools="$2"; shift 2 ;;
        -p) prompt="$2"; shift 2 ;;
        *) shift ;;
    esac
done

if [ "$allowed_tools" != "Bash,Write,Read" ]; then
    echo "MOCK FAILURE: expected --allowedTools 'Bash,Write,Read', got '$allowed_tools'" >&2
    exit 99
fi

mode="${CLAUDE_MOCK_MODE:-noop}"

# For non-project-sync modes, enforce cwd == add_dir (workbench contract).
if [ "$mode" != "project-sync" ] && [ "$PWD" != "$add_dir" ]; then
    echo "MOCK FAILURE: expected cwd '$add_dir', got '$PWD'" >&2
    exit 99
fi

case "$mode" in
    move-inbox-file)
        f=$(find "$add_dir/00_Inbox" -type f -name '*.md' | head -1)
        if [ -n "$f" ]; then
            base=$(basename "$f")
            mv "$f" "$add_dir/05_Archive/$base"
            printf '\n## [test] ingest | moved %s to 05_Archive\n- result: success\n' "$base" \
                >> "$add_dir/log.md"
        fi
        ;;
    noop) : ;;
    fail) exit 1 ;;
    project-sync)
        # Extract note_path: <vault-relative path> from the prompt YAML.
        note_rel=$(printf '%s\n' "$prompt" | awk '/^note_path:/{print $2; exit}')
        if [ -z "$note_rel" ]; then
            echo "MOCK FAILURE: project-sync mode could not parse note_path from prompt" >&2
            exit 99
        fi
        note_abs="$add_dir/$note_rel"
        if [ ! -f "$note_abs" ]; then
            echo "MOCK FAILURE: note file does not exist: $note_abs" >&2
            exit 99
        fi
        python3 - "$note_abs" <<'PY'
import sys, re, pathlib
p = pathlib.Path(sys.argv[1])
text = p.read_text(encoding="utf-8")
start = "<!-- vault-sync:start -->"
end = "<!-- vault-sync:end -->"
i = text.index(start)
j = text.index(end)
new_block = (
    start + "\n"
    "## Project Snapshot\n"
    "*Auto-generated by project_sync. Do not edit between markers — "
    "changes will be overwritten on next sync.*\n\n"
    "### Purpose\n*(test)*\n\n"
    "### Current spec\n*(test)*\n\n"
    "### ADRs / decisions\n*(none)*\n\n"
    "### Recent activity (last 14 days)\n*(none)*\n"
)
p.write_text(text[:i] + new_block + text[j:], encoding="utf-8")
PY
        ;;
esac
```

- [ ] **Step 2: Verify other integration tests still pass**

Run: `.venv-dev/bin/python -m pytest tests/integration/test_daily_ingest.py tests/integration/test_weekly_lint.py -v`
Expected: all green (the mock changes are backward-compatible for existing modes).

- [ ] **Step 3: Write the e2e test**

```python
# tests/integration/test_project_sync_e2e.py
from __future__ import annotations

import os
import subprocess
import sys
import types
from pathlib import Path

import pytest


_REPO_ROOT = Path(__file__).resolve().parents[2]
_CLAUDE_MOCK = _REPO_ROOT / "tests" / "fixtures" / "claude-mock" / "claude"


def _inject_local(monkeypatch, **values: str) -> None:
    fake = types.ModuleType("lib.common.config_local")
    for k, v in values.items():
        setattr(fake, k, v)
    monkeypatch.setitem(sys.modules, "lib.common.config_local", fake)


@pytest.fixture
def project_sync_main():
    import importlib

    for m in ("project_sync", "lib.project_sync.cli", "lib.project_sync.sync"):
        if m in sys.modules:
            del sys.modules[m]
    module = importlib.import_module("project_sync")
    return module.main


def _git_init_repo(path: Path, *, files: dict[str, str]) -> None:
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["git", "-c", "init.defaultBranch=main", "init", "-q"],
        cwd=path, check=True,
    )
    for rel, content in files.items():
        f = path / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(content, encoding="utf-8")
    subprocess.run(["git", "-C", str(path), "add", "-A"], check=True)
    subprocess.run(
        ["git", "-C", str(path),
         "-c", "user.email=t@e", "-c", "user.name=t",
         "commit", "-q", "-m", "init"],
        check=True,
    )


def test_single_repo_creates_note(
    tmp_vault: Path, tmp_path: Path, monkeypatch, project_sync_main
):
    os.chmod(_CLAUDE_MOCK, 0o755)
    monkeypatch.setenv("CLAUDE_MOCK_MODE", "project-sync")
    monkeypatch.setenv("HOME", str(tmp_path))

    repo = tmp_path / "Projects" / "alpha"
    _git_init_repo(repo, files={"README.md": "# alpha\n"})

    _inject_local(
        monkeypatch,
        VAULT_DIR=str(tmp_vault),
        WORKBENCH_DIR=str(tmp_path / "wb"),
        VENV_DIR=str(tmp_path / "venv"),
        BACKEND="claude",
        AGENT_BIN=str(_CLAUDE_MOCK),
    )

    rc = project_sync_main([str(repo)])
    assert rc == 0

    note = tmp_vault / "01_Projects" / "alpha.md"
    assert note.exists()
    text = note.read_text(encoding="utf-8")
    assert "project_path: ~/Projects/alpha" in text
    assert "last_synced_commit:" in text
    assert "<!-- vault-sync:start -->" in text
    assert "<!-- vault-sync:end -->" in text
    assert "### Purpose" in text

    # Single commit on main
    log = subprocess.run(
        ["git", "-C", str(tmp_vault), "log", "--oneline"],
        capture_output=True, text=True, check=True,
    ).stdout
    assert "project-sync: alpha @" in log


def test_skip_when_unchanged(
    tmp_vault: Path, tmp_path: Path, monkeypatch, project_sync_main
):
    os.chmod(_CLAUDE_MOCK, 0o755)
    monkeypatch.setenv("CLAUDE_MOCK_MODE", "project-sync")
    monkeypatch.setenv("HOME", str(tmp_path))

    repo = tmp_path / "Projects" / "beta"
    _git_init_repo(repo, files={"README.md": "# beta\n"})

    _inject_local(
        monkeypatch,
        VAULT_DIR=str(tmp_vault),
        WORKBENCH_DIR=str(tmp_path / "wb"),
        VENV_DIR=str(tmp_path / "venv"),
        BACKEND="claude",
        AGENT_BIN=str(_CLAUDE_MOCK),
    )

    assert project_sync_main([str(repo)]) == 0
    # Second run, same HEAD → skipped, no new commit
    log_before = subprocess.run(
        ["git", "-C", str(tmp_vault), "log", "--oneline"],
        capture_output=True, text=True, check=True,
    ).stdout

    # Sabotage the mock so it would fail if re-invoked; skip path must not call it.
    monkeypatch.setenv("CLAUDE_MOCK_MODE", "fail")
    assert project_sync_main([str(repo)]) == 0

    log_after = subprocess.run(
        ["git", "-C", str(tmp_vault), "log", "--oneline"],
        capture_output=True, text=True, check=True,
    ).stdout
    assert log_before == log_after


def test_force_resyncs(
    tmp_vault: Path, tmp_path: Path, monkeypatch, project_sync_main
):
    os.chmod(_CLAUDE_MOCK, 0o755)
    monkeypatch.setenv("CLAUDE_MOCK_MODE", "project-sync")
    monkeypatch.setenv("HOME", str(tmp_path))

    repo = tmp_path / "Projects" / "gamma"
    _git_init_repo(repo, files={"README.md": "# gamma\n"})

    _inject_local(
        monkeypatch,
        VAULT_DIR=str(tmp_vault),
        WORKBENCH_DIR=str(tmp_path / "wb"),
        VENV_DIR=str(tmp_path / "venv"),
        BACKEND="claude",
        AGENT_BIN=str(_CLAUDE_MOCK),
    )

    assert project_sync_main([str(repo)]) == 0
    rc = project_sync_main([str(repo), "--force"])
    assert rc == 0
    log = subprocess.run(
        ["git", "-C", str(tmp_vault), "log", "--oneline"],
        capture_output=True, text=True, check=True,
    ).stdout
    # Two commits: initial create and a forced re-sync.
    assert log.count("project-sync: gamma") == 2


def test_bulk_mode_two_repos(
    tmp_vault: Path, tmp_path: Path, monkeypatch, project_sync_main
):
    os.chmod(_CLAUDE_MOCK, 0o755)
    monkeypatch.setenv("CLAUDE_MOCK_MODE", "project-sync")
    monkeypatch.setenv("HOME", str(tmp_path))

    parent = tmp_path / "Projects"
    parent.mkdir()
    _git_init_repo(parent / "one", files={"README.md": "# one\n"})
    _git_init_repo(parent / "two", files={"README.md": "# two\n"})

    _inject_local(
        monkeypatch,
        VAULT_DIR=str(tmp_vault),
        WORKBENCH_DIR=str(tmp_path / "wb"),
        VENV_DIR=str(tmp_path / "venv"),
        BACKEND="claude",
        AGENT_BIN=str(_CLAUDE_MOCK),
    )

    rc = project_sync_main([str(parent)])
    assert rc == 0
    assert (tmp_vault / "01_Projects" / "one.md").exists()
    assert (tmp_vault / "01_Projects" / "two.md").exists()

    log = subprocess.run(
        ["git", "-C", str(tmp_vault), "log", "--oneline"],
        capture_output=True, text=True, check=True,
    ).stdout
    assert "project-sync: 2 projects" in log


def test_invalid_target_returns_two(
    tmp_vault: Path, tmp_path: Path, monkeypatch, project_sync_main
):
    os.chmod(_CLAUDE_MOCK, 0o755)
    _inject_local(
        monkeypatch,
        VAULT_DIR=str(tmp_vault),
        WORKBENCH_DIR=str(tmp_path / "wb"),
        VENV_DIR=str(tmp_path / "venv"),
        BACKEND="claude",
        AGENT_BIN=str(_CLAUDE_MOCK),
    )
    rc = project_sync_main([str(tmp_path / "does-not-exist")])
    assert rc == 2
```

- [ ] **Step 4: Run the e2e test**

Run: `.venv-dev/bin/python -m pytest tests/integration/test_project_sync_e2e.py -v`
Expected: all 5 tests PASS.

- [ ] **Step 5: Run full test suite for regressions**

Run: `.venv-dev/bin/python -m pytest`
Expected: full green.

- [ ] **Step 6: Commit**

```bash
git add tests/fixtures/claude-mock/claude tests/integration/test_project_sync_e2e.py
git commit -m "test(project_sync): mock backend project-sync mode + e2e"
```

---

## Task 9: Update `templates/CLAUDE.md`

**Files:**
- Modify: `templates/CLAUDE.md`

Apply spec §11. Two new rows in the §2 permission table, one bullet in §7, new §11 explanation.

- [ ] **Step 1: Edit the §2 permission table — add two rows after the existing `05_Archive/` row**

Insert before `## 3. Routing`:

```markdown
| `01_Projects/**/*.md` frontmatter `project_path` / `project_repo` / `last_synced` / `last_synced_commit` | **Read only.** Owned by `project_sync`. Preserve when appending; never modify. |
| `01_Projects/**/*.md` content between `<!-- vault-sync:start -->` and `<!-- vault-sync:end -->` | **Read only.** Owned by `project_sync`. Do not modify either the markers or anything between them. Append elsewhere in the note. |
```

- [ ] **Step 2: Add a new bullet to §7 MUST NOT**

After the "Commit without a message" bullet, add:

```markdown
- Modify any `<!-- vault-sync:* -->` marker, the content between them, or the `project_*` / `last_synced*` frontmatter fields in any `01_Projects/` note.
```

- [ ] **Step 3: Append a new §11 at the end of the file**

```markdown
## 11. project_sync integration

Notes in `01_Projects/` may carry a snapshot block written by an out-of-band
tool called `project_sync`, which the user runs manually from their shell.
The block is bracketed by `<!-- vault-sync:start -->` and
`<!-- vault-sync:end -->`. You may read it for context but never edit it;
place any appended content outside the markers. The same applies to the
`project_*` and `last_synced*` frontmatter fields.

The existing "never create new notes in `01_Projects/`" rule is **not
relaxed** — it constrains the nightly agent (you) specifically.
`project_sync` runs as the user via a separate CLI and is not bound by it.
```

- [ ] **Step 4: Commit**

```bash
git add templates/CLAUDE.md
git commit -m "docs(templates): teach in-vault agent about project_sync regions"
```

---

## Task 10: Module README + final verification

**Files:**
- Create: `scripts/lib/project_sync/README.md`

A short README mirroring `scripts/lib/agent/README.md` style: one paragraph + the file list. Useful when reading the source tree.

- [ ] **Step 1: Write the README**

```markdown
# `lib/project_sync` — repository → Vault note snapshot

User-invoked counterpart to the nightly `daily_ingest` / `weekly_lint`
frames. Entry point: `scripts/project_sync.py`. Feature module here:

- `discover.py` — classify TARGET (single repo / bulk parent / fatal).
- `facts.py`    — collect git, spec-file, and ADR facts per repo.
- `note.py`     — frontmatter parse/render, marker-block validation, note
                  path resolution (folder-form vs file-form), state
                  classification, skip-if-unchanged check.
- `agent.py`    — render the `project_sync` prompt and invoke the configured
                  backend with `cwd=<repo>` and `--add-dir <vault>`.
- `sync.py`     — per-repo orchestration: state → skip → facts → bootstrap →
                  invoke → validate → rewrite frontmatter.
- `cli.py`      — argparse, output formatting, batch git commit, exit-code
                  aggregation.

Design: `docs/specs/2026-05-10-project-sync-design.md`.
```

- [ ] **Step 2: Final verification**

Run all of the following:

```bash
.venv-dev/bin/python -m pytest -v
```

Expected: full suite green, including the four new unit test files and the new e2e test file. Spot-check counts:

- `test_project_sync_note.py` — 9 tests
- `test_project_sync_discover.py` — 6 tests
- `test_project_sync_facts.py` — 7 tests
- `test_project_sync_skip.py` — 7 tests
- `test_project_sync_e2e.py` — 5 tests
- existing unit + integration suites unchanged.

If anything is red, fix it in place before committing.

- [ ] **Step 3: Commit**

```bash
git add scripts/lib/project_sync/README.md
git commit -m "docs(project_sync): module README"
```

---

## Self-review notes

**Spec coverage:** discover (§4.2 → Task 2), facts (§6 → Task 3), skip-if-unchanged (§8 → Task 4), prompt + agent invocation (§7 → Task 5), per-repo orchestration including states `new`/`adopt`/`registered`/`mismatch` (§3.2 + §9 → Task 6), CLI output and exit codes (§4.3 + §3.2 → Task 7), e2e covering single/bulk/skip/force/invalid (§13 examples → Task 8), templates/CLAUDE.md changes (§11 → Task 9).

**Out of v1 (per spec §14):** `--discover` mode, ignore patterns, reverse direction, MyContext.md maintenance, "missing on this host" warnings — none implemented. Cross-machine path resolution (§12, §2 non-goals) handled passively: repos absent on the current host simply don't get enumerated, so they don't appear in any sync result.

**Known cosmetic gap:** the spec mentions a `skipped <name> (project_path not present on this host)` output line; in v1 a repo absent on the current host never enters the result list (the user runs `project_sync` from a host where it does exist), so the line never fires. Acceptable for v1 — `Status` reserves `skipped-missing-host` for the future extension when bulk mode is run with a Vault-driven repo list.
