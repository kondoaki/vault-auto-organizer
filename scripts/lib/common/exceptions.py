from __future__ import annotations


class OrganizerError(Exception):
    """Base for known, recoverable orchestrator errors.

    Frame top-level catches this and exits with ``exit_code``.
    Anything else propagates as an uncaught traceback to launchd.
    """

    exit_code: int = 1


class AgentError(OrganizerError):
    exit_code = 3


class WorktreeMergeConflict(OrganizerError):
    exit_code = 2

    def __init__(self, run_id: str = "", conflicted_files: list[str] | None = None) -> None:
        self.run_id = run_id
        self.conflicted_files = conflicted_files or []
        suffix = f" on {run_id}" if run_id else ""
        super().__init__(f"merge conflict{suffix}")


class SkipRun(OrganizerError):
    """Signals an early, non-error return from a gate-style feature."""

    exit_code = 0
