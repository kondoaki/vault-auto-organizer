# lib/config

## Role
The single entry point for runtime configuration. Wraps the install-rendered
`local.py` (paths and backend choice) in a typed `Config` dataclass that
features receive as an argument.

## Preconditions
- For `load()`: `install.sh` has rendered `local.py` from
  `templates/config.py.template`.
- For tests: construct `Config(...)` directly — no `local.py` needed.

## Public API
- `Config` — frozen dataclass: `vault_dir`, `workbench_dir`, `venv_dir`,
  `backend`, `agent_bin`, `check_recent`.
- `load(*, check_recent: bool = False) -> Config` — reads `local.py`.

## Side effects
None. Pure value object.

## Environment variables
None directly. The values inside `local.py` are sourced from `.env` at
install time, not at runtime.
