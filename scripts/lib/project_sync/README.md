# `lib/project_sync` — repository → Vault note snapshot

User-invoked counterpart to the nightly `daily_ingest` / `weekly_lint`
frames. Entry point: `scripts/project_sync.py`. Feature module here:

- `discover.py` — classify TARGET (single repo / bulk parent / fatal).
- `facts.py`    — collect git, spec-file, and ADR facts per repo.
- `note.py`     — frontmatter parse/render, marker-block validation, note
                  path resolution (folder-form vs file-form), state
                  classification, skip-if-unchanged check.
- `agent.py`    — render the `project_sync` prompt and invoke the configured
                  backend with `cwd=<repo>` and `--add-dir <vault>`.
- `sync.py`     — per-repo orchestration: state → skip → facts → bootstrap →
                  invoke → validate → rewrite frontmatter.
- `cli.py`      — argparse, output formatting, batch git commit, exit-code
                  aggregation.

Design: `docs/specs/2026-05-10-project-sync-design.md`.
