# lib/git

## Role
All git-touching operations the orchestrator performs against the vault
(and its worktree). Centralizes everything that shells out to `git`,
keeping the rest of the codebase free of subprocess plumbing.

## Preconditions
- The vault directory is a git repository (`prepare_worktree`,
  `take_snapshot`, `merge_worktree`, `push_to_main`, `sync_with_origin`).
- `take_snapshot` and `merge_worktree` require the vault to be on `main`
  / not detached.

## Public API
Re-exported from the package root (`from lib.git import ...`):
- `take_snapshot(cfg, *, label)` — pre-batch snapshot commit.
- `prepare_worktree(cfg, run_id)` — create the per-run worktree.
- `merge_worktree(cfg, run_id) -> "success" | "noop"` — squash-merge,
  raises `WorktreeMergeConflict` on conflict.
- `cleanup_worktree(cfg, run_id)` — idempotent worktree + branch removal.
- `push_to_main(cfg)` — best-effort push, never raises.
- `sync_with_origin(vault_dir: Path)` — best-effort ff-only merge of
  `origin/main` before any pre-run commits.

## Side effects
- Various `git` subprocess invocations (status, commit, worktree add /
  remove, branch -D, merge --squash, push, fetch, reset --merge).
- `merge_worktree` writes the conflict report via `lib.report` and fires
  an `osascript` notification on conflict (best-effort).

## Environment variables
None.

## Sub-layout
```
lib/git/
├── __init__.py        # re-exports
├── snapshot.py        # take_snapshot
├── worktree.py        # prepare / merge / cleanup
├── push.py            # push_to_main
└── sync_origin.py     # sync_with_origin
```
