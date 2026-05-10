from __future__ import annotations

from pathlib import Path

from lib.common import OrganizerError


class InvalidTarget(OrganizerError):
    exit_code = 2


class NoRepositoriesFound(OrganizerError):
    exit_code = 2


def _is_working_repo(path: Path) -> bool:
    """True iff `path/.git` exists as a directory (worktree, not bare)."""
    return path.is_dir() and (path / ".git").is_dir()


def classify_target(target: Path):
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


__all__ = ["InvalidTarget", "NoRepositoriesFound", "classify_target"]
