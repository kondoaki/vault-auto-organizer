# lib/common

## Role
Cross-cutting utilities used by every frame and most features: date helpers,
run-id generation, stderr logging, signal handlers, the `OrganizerError`
exception hierarchy, and the pre-run `sync_with_origin` git fast-forward.

## Preconditions
- For `sync_with_origin`: the vault path is a git repository.
- All others have no preconditions.

## Public API
- `current_iso_date() -> str` (`YYYY-MM-DD`)
- `current_iso_minute() -> str` (`YYYY-MM-DD HH:MM`)
- `current_month_prefix() -> str` (`YYYY-MM`)
- `generate_run_id(kind: str) -> str` (`<kind>-YYYY-MM-DD`)
- `log_info(msg: str)`, `log_error(msg: str)`, `die(msg: str)` — stderr writers; `die` exits 1
- `install_signal_handlers(cleanup: Callable[[], None])` — SIGTERM / SIGINT
- `sync_with_origin(vault_dir: Path)` — best-effort pre-run ff-only merge of `origin/main`
- Exceptions: `OrganizerError` (base), `AgentError`, `WorktreeMergeConflict`, `SkipRun`

## Side effects
- `log_*` / `die` write to stderr.
- `die` calls `sys.exit(1)`.
- `install_signal_handlers` registers signal handlers; on signal, calls
  `cleanup()` and exits with `128+signum`.
- `sync_with_origin` runs `git fetch origin` and `git merge --ff-only origin/main`
  inside `vault_dir`. Logs to stderr; raises `OrganizerError` on true divergence.

## Environment variables
None.
