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
    project_repo: str
    default_branch: str
    head_commit: str
    spec_files: list = field(default_factory=list)
    adr_dir: str = None
    adr_files: list = field(default_factory=list)
    recent_commits: str = ""
    exploration_mode: bool = False


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True, text=True, check=True,
    ).stdout


def _git_quiet(repo: Path, *args: str):
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


def _candidate_spec_files(repo: Path):
    found = []
    seen = set()
    for name in _SPEC_GLOBS_ROOT:
        if (repo / name).is_file() and name not in seen:
            found.append(name)
            seen.add(name)
    for entry in sorted(repo.iterdir()):
        if not entry.is_file() or not entry.name.endswith(".md"):
            continue
        for prefix in _SPEC_PREFIX_ROOT:
            if entry.name.startswith(prefix) and entry.name not in seen:
                found.append(entry.name)
                seen.add(entry.name)
    docs = repo / "docs"
    if docs.is_dir():
        for entry in sorted(docs.iterdir()):
            if entry.is_file() and entry.name.startswith("SPEC") and entry.name.endswith(".md"):
                rel = f"docs/{entry.name}"
                if rel not in seen:
                    found.append(rel)
                    seen.add(rel)
    return found


def _adr_dir_and_files(repo: Path):
    for rel in _ADR_PRIORITY:
        d = repo / rel
        if d.is_dir():
            files = sorted(p.name for p in d.iterdir() if p.is_file() and p.suffix == ".md")
            return rel, files
    return None, []


def collect_facts(repo: Path) -> RepoFacts:
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
    """Render facts as the YAML block injected into the agent prompt."""
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
