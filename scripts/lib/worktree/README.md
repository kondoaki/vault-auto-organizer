# lib/worktree

## Role
Manage the per-run git worktree at `cfg.workbench_dir`: create it on a
fresh branch, squash-merge it back into `main`, and clean up. The
worktree lives outside iCloud so the agent's intermediate writes do not
fight the vault's sync.

## Preconditions
- The vault is a git repository.
- For `merge_worktree`: the vault is not on a detached HEAD.

## Public API
- `prepare_worktree(cfg, run_id: str)` — drop any stale workbench /
  branch, create a new worktree at `cfg.workbench_dir` on branch `run_id`.
- `merge_worktree(cfg, run_id: str) -> str` — squash-merge the run
  branch. Returns `"success"` (commits merged) or `"noop"` (agent made
  no changes). Raises `WorktreeMergeConflict` on conflict; the conflict
  report is written and an `osascript` notification is fired before the
  exception is raised. The workbench is preserved on conflict so the
  user can investigate.
- `cleanup_worktree(cfg, run_id: str)` — best-effort removal of the
  workbench directory and the run branch. Idempotent.

## Side effects
- `git worktree add` / `git worktree remove`, `git branch -D`,
  `git merge --squash`, `git commit`.
- Filesystem writes inside `cfg.workbench_dir`.
- `osascript` notification on conflict (best-effort, errors swallowed).

## Environment variables
None.
