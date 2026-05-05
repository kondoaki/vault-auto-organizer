# lib/log

## Role
Append-only writer for the vault's `log.md` and the monthly rotation that
slices older entries into `05_Archive/logs/YYYY-MM.md`.

## Preconditions
- The vault directory exists. `log.md` may be empty or missing.
- `05_Archive/logs/` is created if needed.

## Public API
- `append_log(cfg, *, action, summary, file, destination, linked, result)` —
  append one structured entry to `log.md`.
- `rotate_log_if_needed(cfg)` — move pre-current-month entries into the
  archive directory; idempotent.

## Side effects
- Appends to `<vault>/log.md`.
- During rotation, rewrites `log.md` and creates / appends to
  `<vault>/05_Archive/logs/YYYY-MM.md`.

## Environment variables
None.
