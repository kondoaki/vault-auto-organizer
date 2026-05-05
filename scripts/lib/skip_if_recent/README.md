# lib/skip_if_recent

## Role
Detect whether the user is actively editing the vault (any user-content
file modified within the last 5 minutes). Used as an early-exit gate so
scheduled runs do not race with concurrent edits.

## Preconditions
- The vault directory exists.

## Public API
- `is_recent(cfg, *, threshold_seconds: int = 300) -> bool` — `True` if
  a recent edit was found.

## Side effects
- Logs the path of the first detected recent file to stderr.

## Environment variables
None.

## Excluded paths (top level only)
Directories: `.git`, `.obsidian`, `05_Archive`, `scripts`
Files: `log.md`, `CLAUDE.md`
