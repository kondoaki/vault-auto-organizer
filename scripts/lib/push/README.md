# lib/push

## Role
Best-effort push of the vault's current branch to its configured upstream
at the end of every run. The frame's outer `finally` invokes this so
even skipped / failure runs land on the remote.

## Preconditions
- The vault is a git repository.

## Public API
- `push_to_main(cfg)` — silent no-op if no upstream is configured;
  logs (but never raises) on push failure.

## Side effects
- `git push` against the configured upstream.

## Environment variables
None.
