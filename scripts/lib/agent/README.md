# lib/agent

## Role
Run the configured agent CLI (`claude` or `opencode`) against a prompt
inside the workbench. Owns the prompt files and the backend dispatch.

## Preconditions
- `cfg.workbench_dir` exists (lib.worktree.prepare_worktree has been called).
- `cfg.agent_bin` resolves to an executable.
- `cfg.backend` is either `"claude"` or `"opencode"`.

## Public API
- `invoke_agent(cfg, run_id: str, *, prompt: str)` — `prompt` is the bare
  filename under `lib/agent/prompts/` (e.g. `"ingest"`, `"lint_full"`).

## Side effects
- Spawns a subprocess with `cwd = cfg.workbench_dir`.
- The agent typically writes inside the workbench (vault-shaped checkout).
- Prompts use `$RUN_ID` and `$RUN_DATE` placeholders, substituted before
  the agent sees the text.

## Environment variables
- The opencode backend sets `OPENCODE_CONFIG_DIR` so opencode picks up
  `lib/agent/backends/opencode_config/opencode.json`.

## Sub-layout
```
lib/agent/
├── prompts/                 # ingest.md, lint_full.md
└── backends/
    ├── claude.py
    ├── opencode.py
    └── opencode_config/     # opencode.json (model + permissions)
```
