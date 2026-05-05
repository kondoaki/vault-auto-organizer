# lib/snapshot

## Role
Capture uncommitted vault changes into a single snapshot commit before the
worktree is created. Lets the run start from a known-clean main.

## Preconditions
- The vault is a git repository.
- The vault is currently on `main`.

## Public API
- `take_snapshot(cfg, *, label: str)` — `label` (typically the run_id) is
  embedded in the commit message.

## Side effects
- May add up to one new commit on `main` in `cfg.vault_dir`.
- No-op if the working tree is clean.

## Environment variables
None.
