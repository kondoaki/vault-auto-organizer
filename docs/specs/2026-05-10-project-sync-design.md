# Project Sync — Design

> **Status:** Draft (brainstorming complete, awaiting user spec review)
> **Date:** 2026-05-10
> **Owner:** @kondoaki
> **Scope:** Ad-hoc CLI that snapshots external git project state (`~/Projects/<repo>/`) into Vault notes (`01_Projects/<name>.md`). Independent of the daily/weekly nightly batches. Implements the "実プロジェクト → Vault 同期" direction; the reverse direction (Idea → prototype generation) is out of scope.

---

## 1. Goal

Provide a user-invoked command that, given either a single git repository or a parent directory containing several, writes/updates a corresponding note in `01_Projects/` summarizing each repository's current state (purpose, spec, ADRs, recent activity). The summary is regenerated idempotently, with user-authored sections of the same note preserved verbatim.

Primary use case: the user has many existing projects under `~/Projects/`, runs `project_sync` once from `~/Projects/`, and gets a Vault note per repository ready for brainstorming with the in-Vault agent.

## 2. Non-goals

- **Reverse-direction generation** (Idea note → scaffolded prototype in `~/Projects/`) — separate spec, deferred.
- **Write-back to external repositories** — `project_sync` reads external repos, never writes.
- **Interactive in-Vault agent context injection** — pulling external repo content into a live brainstorming session is the user's responsibility (e.g. starting `claude` with `--add-dir ~/Projects/foo`). `project_sync` only writes pre-rendered snapshots into the note.
- **Cross-machine path resolution** — if the recorded `project_path` does not exist on the host running `project_sync`, the repo is skipped silently. No host-aware path dictionaries.
- **MyContext.md maintenance** — `project_sync` never touches `03_Context/MyContext.md`. Active-Projects entries remain a manual or nightly-agent concern.
- **launchd / scheduled execution** — strictly user-invoked.
- **Logging into Vault `log.md`** — `project_sync` writes to stdout/stderr only; history is recoverable via git.

## 3. Architecture overview

### 3.1 Position in the codebase

`project_sync` is a sibling of `daily_ingest.py` and `weekly_lint.py`: a top-level Python entry point under `scripts/` that imports a feature module under `scripts/lib/project_sync/`. It is rsynced into the Vault by `install.sh` along with the other scripts; editing the source repo has no effect until `install.sh` is re-run.

It does **not** integrate with the nightly batch frames. It does not use the orchestrator's worktree isolation. It writes to the Vault directly.

### 3.2 End-to-end flow (single invocation)

```
project_sync.py [TARGET]
        │
        │ 1. discover: classify TARGET as
        │      - single git repo (.git present)         → [repo]
        │      - container of git repos (children .git) → [repo, repo, ...]
        │      - neither                                → fatal exit
        ▼
   per repo:
        │
        │ 2. resolve Vault note path (folder form first, file form fallback)
        │      - 01_Projects/<name>/<name>.md    (folder form, if 01_Projects/<name>/ exists)
        │      - 01_Projects/<name>.md           (file form, default for new bootstrap)
        │
        │ 3. detect "already registered":
        │      note exists AND frontmatter project_path resolves to repo path
        │
        │ 4. skip-if-unchanged:
        │      registered AND last_synced_commit == repo HEAD AND not --force
        │      → no-op, log "skipped: unchanged"
        │
        │ 5. collect facts (Python, deterministic):
        │      git remote, default branch, candidate spec files,
        │      ADR directory listing, recent commits (14d),
        │      exploration_mode flag (true if no candidates found)
        │
        │ 6. invoke agent with facts + note path
        │      - agent reads existing note (if any)
        │      - rewrites only the <!-- vault-sync:start --> ... <!-- vault-sync:end --> block
        │      - never touches frontmatter
        │
        │ 7. Python finalizes:
        │      - rewrite frontmatter deterministically (project_path, project_repo,
        │        last_synced, last_synced_commit)
        │      - validate marker block well-formed
        │
   end per-repo loop
        │
        │ 8. single git commit on Vault main covering only files this run wrote:
        │      "project-sync: <name> @ <sha>"        (single repo)
        │      "project-sync: <N> projects (<n1>, <n2>, ...)" (bulk)
        │    if no repo produced changes (all skipped or all errored), no commit
        ▼
   exit code:
        0 = all targets succeeded (incl. skipped)
        1 = at least one repo errored, others succeeded
        2 = fatal (TARGET invalid, etc.)
```

### 3.3 Why no worktree

The nightly batch uses worktree isolation because (a) it runs unattended at 3 AM, (b) iCloud is actively syncing concurrent edits from other devices, and (c) batches take minutes during which conflicts accumulate. `project_sync` runs interactively under the user (so the user is present and can react), touches typically one or a handful of files, and finishes in seconds-to-minutes per repo. Direct write to the Vault, bracketed by `git commit` checkpoints, gives the same recoverability without the worktree-spawn overhead.

## 4. CLI surface

### 4.1 Synopsis

```
project_sync.py [TARGET] [--force]
```

- `TARGET` (optional): path to a directory. Defaults to cwd.
- `--force`: ignore skip-if-unchanged and re-sync every detected repo.

### 4.2 TARGET classification

After `realpath` resolution:

| Condition on TARGET | Mode | Action |
|---|---|---|
| TARGET contains `.git/` directly | single | sync just TARGET |
| TARGET's immediate children contain ≥1 dir with `.git/` | bulk | sync each such child; non-git children ignored |
| Neither | fatal | exit 2 with diagnostic |

In bulk mode, the recursion depth is exactly 1 — `~/Projects/work/<repo>` is **not** picked up by `project_sync ~/Projects/`. Submodules and bare repositories are also skipped in v1.

### 4.3 Output

Per repo, one line on stdout:

```
synced     foo  @ a1b2c3d
skipped    bar  @ e4f5g6h  (unchanged since last sync)
created    baz  @ 0011223  (new note)
linked     qux  @ 4455667  (existing note adopted)
skipped    pop          (project_path not present on this host)
ERROR      zap  - <reason>
```

Final summary line on stderr; exit code per §3.2.

## 5. Note shape

### 5.1 Skeleton (new bootstrap)

```markdown
---
project_path: ~/Projects/foo
project_repo: https://github.com/u/foo
last_synced: 2026-05-10 14:32
last_synced_commit: a1b2c3d
---

<!-- vault-sync:start -->
## Project Snapshot
*Auto-generated by project_sync. Do not edit between markers — changes will be overwritten on next sync.*

### Purpose
<2-3 line summary>

### Current spec
<excerpt or summary>

### ADRs / decisions
- 2026-05-08 — `docs/adr/0003-...` (title)
- ...

### Recent activity (last 14 days)
- 2026-05-09 b1e112a — <commit subject>
- ...
<!-- vault-sync:end -->

## Notes
<!-- Free-form. project_sync never touches this region. -->
```

### 5.2 Form selection (file vs folder)

- Default for a fresh bootstrap: single file `01_Projects/<name>.md`.
- If `01_Projects/<name>/` already exists as a directory, write to `01_Projects/<name>/<name>.md` (the convention is "main markdown filename equals the repo / folder name").
- `<name>` is the basename of the resolved repository path.
- The user may convert file → folder manually at any time; `project_sync` will pick up the new form on the next run by checking folder form first, file form second.

### 5.3 Ownership boundaries inside the note

| Region | Owner |
|---|---|
| Frontmatter `project_path` / `project_repo` / `last_synced` / `last_synced_commit` | `project_sync` (deterministic Python write) |
| Other frontmatter fields | User / nightly agent |
| Inside `<!-- vault-sync:start -->` … `<!-- vault-sync:end -->` | `project_sync` (agent rewrites on each run) |
| Outside the marker block | User / nightly agent (preserved verbatim) |

## 6. Fact collection (Python, deterministic)

### 6.1 Candidate files for spec content

Searched at repo root only (no recursion):

- `SPEC.md`, `SPEC*.md`
- `README.md`, `README*.md`
- `ARCHITECTURE.md`
- `AGENTS.md`
- `CLAUDE.md`
- `docs/SPEC*.md` (one level into `docs/`)

### 6.2 ADR detection

Searched in this priority order; first hit wins:

- `docs/adr/`
- `docs/decisions/`
- `docs/architecture/decisions/`

All `*.md` files directly under the chosen directory are listed (filename, mtime).

### 6.3 Git facts

- `git remote get-url origin` → `project_repo` (skipped silently if absent)
- `git symbolic-ref --short refs/remotes/origin/HEAD` (or `HEAD`) → default branch (informational only; surfaced to the agent as context for the prose, not stored in frontmatter)
- `git rev-parse HEAD` → current `last_synced_commit`
- `git log --oneline --since='14 days ago'` → recent activity list

### 6.4 Exploration mode trigger

If §6.1 candidate files set is empty AND §6.2 ADR directory not found, set `exploration_mode: true` in the fact set passed to the agent. The agent prompt branches accordingly (§7).

### 6.5 Fact set shape (passed to agent prompt)

```yaml
name: foo
project_path: ~/Projects/foo
project_repo: https://github.com/u/foo
default_branch: main
spec_files:
  - README.md
  - AGENTS.md
adr_dir: docs/adr
adr_files:
  - 0001-record-architecture-decisions.md
  - 0002-use-python-for-orchestrator.md
recent_commits: |
  a1b2c3d 2026-05-09 Port the orchestrator from bash to python
  e4f5g6h 2026-05-07 refactor: tighten orchestrator hygiene
exploration_mode: false
note_path: 01_Projects/foo.md
note_exists: true
```

## 7. Agent prompt

A single new prompt at `scripts/lib/agent/prompts/project_sync.md`. Two-mode body:

**Common preamble:** read `note_path` if `note_exists: true`. The only region you may modify is between `<!-- vault-sync:start -->` and `<!-- vault-sync:end -->` markers. Do not touch frontmatter. Do not touch any text outside the markers. Preserve the markers themselves verbatim.

**Normal mode** (`exploration_mode: false`): consume the listed `spec_files` and ADR files via `Read`. Render the four-section snapshot (§5.1). Each section is mandatory; if a section has no source material, write `*(none)*` rather than fabricating.

**Exploration mode** (`exploration_mode: true`): no candidate files were found. You may explore the repository to gather information for the four sections. Constraints:

- Use `Bash ls` / `find` only to map structure (max depth 2 from repo root).
- Look for package manifests: `package.json`, `pyproject.toml`, `Cargo.toml`, `go.mod`, `Gemfile`, `composer.json`. Read them in full if present.
- Read at most 10 source files, max 50 lines each.
- If after exploration a section still lacks source material, write `*(insufficient information)*`. Never invent.

`--allowedTools Bash,Read,Write` — same restriction as the nightly batches.

## 8. Skip-if-unchanged

After §3 step 3 establishes "already registered":

- Compare `frontmatter.last_synced_commit` (read raw from the note) with `git rev-parse HEAD` of the target repo.
- If equal AND `--force` is not set: emit `skipped <name> @ <sha> (unchanged)` and proceed to next repo. No agent call. No file write. No git commit contribution.
- If unequal OR `--force`: proceed to fact collection.

In bulk mode, this means the agent is invoked only for repositories whose HEAD has moved since their last `project_sync`, keeping cost roughly proportional to actual project activity.

## 9. Error handling and edge cases

| Situation | Behavior |
|---|---|
| TARGET does not exist or is not a directory | exit 2, message |
| TARGET is a git repo with no `origin` remote | continue; `project_repo` omitted from frontmatter |
| Bulk mode: zero git children | exit 2, message ("no git repositories found in ...") |
| Note exists with `project_path` pointing to a different repo | error for that repo: `ERROR <name> - already linked to <other-path>`; continue with rest in bulk mode |
| Note exists without `project_path` frontmatter | adopt: add `project_path` / `project_repo`, then sync. Output line `linked` instead of `synced` |
| Marker block malformed (only one of start/end, or out of order) | error for that repo; user must repair manually |
| `last_synced_commit` field present but unparseable | treat as unset (force re-sync) |
| Repo path absolute on this host but recorded `project_path` does not resolve here | not applicable in the run direction (this *is* the host). For other hosts where the repo is absent, `project_sync` is simply not run on that repo |
| Agent invocation returns non-zero | error for that repo; existing note left untouched (no partial frontmatter writes) |
| Vault git working tree dirty before run | continue; the final commit will still be scoped to files `project_sync` itself wrote (use `git add <specific-paths>`, not `git add -A`) |

## 10. File layout (new + modified)

```
scripts/
├── project_sync.py                              [NEW] entry frame
└── lib/
    ├── project_sync/                            [NEW] feature module
    │   ├── __init__.py
    │   ├── README.md
    │   ├── discover.py                          # TARGET classification, repo enumeration
    │   ├── facts.py                             # candidate file detection, git facts, exploration_mode trigger
    │   ├── note.py                              # note path resolution (file vs folder), marker parse, frontmatter rewrite
    │   ├── sync.py                              # per-repo orchestration: discover → skip → facts → invoke → finalize
    │   └── cli.py                               # argparse, output formatting, exit-code aggregation
    └── agent/
        └── prompts/
            └── project_sync.md                  [NEW] agent prompt (normal / exploration modes)

templates/
└── CLAUDE.md                                    [MODIFIED] §11 below

docs/specs/
└── 2026-05-10-project-sync-design.md            [NEW] this document

tests/
├── unit/
│   ├── test_project_sync_discover.py            [NEW]
│   ├── test_project_sync_facts.py               [NEW]
│   ├── test_project_sync_note.py                [NEW] marker parsing, frontmatter round-trip
│   └── test_project_sync_skip.py                [NEW]
├── integration/
│   └── test_project_sync_e2e.py                 [NEW] end-to-end against tests/fixtures/{claude,opencode}-mock/
└── fixtures/
    └── project-repos/                           [NEW] synthetic git repos for tests
```

`install.sh`: no code changes required — existing `scripts/` rsync covers `project_sync.py`, `lib/project_sync/`, and the new prompt automatically.

`Makefile`: no new targets. Existing `make test` / `test-unit` / `test-integration` pick up the new tests.

## 11. `templates/CLAUDE.md` changes

The nightly agent has append rights to `01_Projects/`, so it must be told to leave `project_sync`-owned regions alone.

### §2 Permission table — add two rows

| Folder/Field | Permission |
|---|---|
| `01_Projects/**/*.md` frontmatter `project_path` / `project_repo` / `last_synced` / `last_synced_commit` | **Read only.** Owned by `project_sync`. Preserve when appending; never modify. |
| `01_Projects/**/*.md` content between `<!-- vault-sync:start -->` and `<!-- vault-sync:end -->` | **Read only.** Owned by `project_sync`. Do not modify either the markers or anything between them. Append elsewhere in the note. |

### §7 MUST NOT — add one bullet

- Modify any `<!-- vault-sync:* -->` marker, the content between them, or the `project_*` / `last_synced*` frontmatter fields in any `01_Projects/` note.

### New §11 — "project_sync integration"

A short paragraph: notes in `01_Projects/` may carry a snapshot block written by an out-of-band tool called `project_sync`. The block is bracketed by `<!-- vault-sync:start -->` and `<!-- vault-sync:end -->`. You may read it for context but never edit it; place any appended content outside the markers. The same applies to the `project_*` and `last_synced*` frontmatter fields.

The existing "never create new notes in `01_Projects/`" rule is **not relaxed** — that rule constrains the nightly agent specifically. `project_sync` runs as the user via a separate CLI and is not bound by it.

## 12. Cross-machine behavior

The Vault syncs across multiple Macs via iCloud. External project folders (`~/Projects/<repo>/`) may live on different hosts.

`project_sync` is run by the user on a host where the relevant repos exist locally. It records `project_path` as a home-relative path (e.g. `~/Projects/foo`) so the same string resolves correctly on any host that has the project at the same location.

When run on a host where a previously-synced repo is *not* present locally, that repo is simply not enumerated (it does not appear in cwd or as a child of TARGET). The Vault note remains untouched. There is no "missing on this host" warning in v1; the user runs `project_sync` on the host that owns the project.

## 13. Cost and runtime

- Per-repo agent invocation: 1, only when HEAD has changed since last sync (or `--force`).
- Bulk-mode example: `~/Projects/` with 25 repos, of which 3 had commits in the last week → 3 agent invocations, 22 skip lines, finishes in well under a minute (skip path is pure Python).
- No background or scheduled cost. The tool exists and consumes nothing until the user runs it.

## 14. Future extensions (out of scope for v1)

- `--discover` mode: list `~/Projects/*` repositories that have no Vault note, without writing.
- Reverse direction (Idea → scaffolded `~/Projects/<name>/`): separate spec, will reuse `project_path` / `project_repo` frontmatter as input.
- Active-Projects line maintenance in `MyContext.md`.
- Cross-machine "missing on this host" reporting.

### Implemented in v1: `PROJECT_SYNC_IGNORE`

Colon-separated repo basenames in the env var skip those repos in **bulk
mode only** (single-target invocation always wins, so the user can still
force-sync an ignored repo by passing its path explicitly). Globs are not
supported; matches are exact basename. Example:

```
PROJECT_SYNC_IGNORE=scratch:dotfiles project_sync.py ~/Projects/
```

Output line: `skipped    <name> (ignored via PROJECT_SYNC_IGNORE)`.

## 15. Open questions / assumptions

- `last_synced` timestamp is wall-clock local time (matches existing `log.md` convention from `templates/CLAUDE.md` §6). Confirm.
- Recent-activity window of 14 days is a starting value; configurable later if it proves too noisy or too sparse for the user's commit cadence.
- ADR detection priority order (`docs/adr/` → `docs/decisions/` → `docs/architecture/decisions/`) covers the common conventions; if a project uses a different layout, the snapshot will simply omit the ADR section in normal mode (or fall back to exploration mode if no other candidates exist either).
- Exploration mode budget (max depth 2, max 10 files at 50 lines) is heuristic; tune after first real-world runs.
