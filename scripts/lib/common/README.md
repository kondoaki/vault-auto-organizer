# lib/common

## Role
The single shared package for cross-cutting utilities every feature and
frame depends on:
- `Config` dataclass + `load()` (install-rendered `config_local.py`)
- vault `log.md` writer (`append_log`, `rotate_log_if_needed`)
- date / run-id helpers
- stderr logging (`log_info`, `log_error`, `die`)
- signal handler registration
- `OrganizerError` exception hierarchy
- pre-run `sync_with_origin` git fast-forward

## Preconditions
- For `sync_with_origin` and `append_log`: the vault is a git repository
  that contains `log.md` (created by `install.sh`).
- For `load()`: `install.sh` has rendered `config_local.py`. Tests can
  bypass this by constructing `Config(...)` directly.

## Public API
Re-exported from the package root (`from lib.common import ...`):
- `Config`, `load`
- `append_log`, `rotate_log_if_needed`
- `current_iso_date`, `current_iso_minute`, `current_month_prefix`
- `generate_run_id`
- `log_info`, `log_error`, `die`
- `install_signal_handlers`
- `sync_with_origin`
- Exceptions: `OrganizerError` (base), `AgentError`,
  `WorktreeMergeConflict`, `SkipRun`

## Side effects
- `log_*` / `die` write to stderr; `die` exits 1.
- `install_signal_handlers` registers SIGTERM / SIGINT handlers.
- `sync_with_origin` runs `git fetch` / `git merge --ff-only`.
- `append_log` appends to `<vault>/log.md`.
- `rotate_log_if_needed` rewrites `log.md` and may write to
  `<vault>/05_Archive/logs/YYYY-MM.md`.

## Environment variables
None.

## Sub-layout
```
lib/common/
├── __init__.py        # re-exports the full public API above
├── config.py          # Config dataclass + load()
├── config_local.py    # install-rendered (gitignored)
├── exceptions.py      # OrganizerError hierarchy
├── iso_date.py        # date string helpers
├── log.py             # vault log.md writer + monthly rotation
├── logger.py          # stderr logging (log_info / log_error / die)
├── run_id.py          # generate_run_id
├── signals.py         # SIGTERM / SIGINT trapping
└── sync_origin.py     # pre-run ff-only merge of origin/main
```
