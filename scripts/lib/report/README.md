# lib/report

## Role
Writers for the four daily-report variants (skipped / conflict / agent-failure /
success) and the helper that commits orchestrator-owned files.

## Preconditions
- The target archive directories exist (created by `install.sh`).
- For `commit_report`: the vault is a git repository.

## Public API
- `write_skipped(cfg, date, reason, *, base_dir=None) -> Path`
- `write_conflict(cfg, date, branch, files, *, base_dir=None) -> Path`
- `write_agent_failure(cfg, date, run_id, *, base_dir=None) -> Path`
- `write_success(cfg, date, mode, processed, unprocessed, lint, *, base_dir=None) -> Path`
- `commit_report(cfg, message)` — stage + commit `log.md` and the archive
  reports / logs directories; no-op if all clean.

`base_dir` overrides the report root (default `cfg.vault_dir`). Frames pass
`cfg.workbench_dir` so success reports land inside the worktree and merge
back as a single commit.

## Side effects
- Writes one report file per call.
- `commit_report` runs `git add` + `git commit` inside `cfg.vault_dir`.
- `write_success` is a no-op if the target file is already dirty in git
  (i.e., the agent wrote it during the run).

## Environment variables
None. The bash version honored `REPORT_BASE_DIR`; the Python version uses
the explicit `base_dir` keyword instead.
