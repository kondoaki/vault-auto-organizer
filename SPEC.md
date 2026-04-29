# Vault Auto-Organizer Design Spec

> **Status:** Draft (brainstorming complete, awaiting user spec review)
> **Date:** 2026-04-28
> **Owner:** @kondoaki
> **Scope:** Implementation of "Condition 3: Automated organization" from `00_Inbox/Second Brain.md` — automatic ingestion of Inbox notes plus weekly Vault hygiene (Lint).
> **Reference:** `00_Inbox/Claude + Obsidian have to be illegal.md` (Karpathy "LLM Wiki" pattern).

---

## 1. Goal

Build an unattended pipeline that, every night at 3:00 AM and every Sunday at 3:30 AM, lets a Claude Code agent process the Vault on the user's behalf:

- **Daily Ingest**: read every note in `00_Inbox/`, route it to the correct destination (Resources / Projects / Ideas / Context proposals / Archive), and propagate cross-references to related notes (Karpathy "LLM Wiki" full ingest).
- **Weekly full Lint**: run an 8-item health check (broken links, empty notes, duplicates, orphans, contradictions, missing concept pages, MyContext consistency, frontmatter normalization) — auto-fix safe items, report items that need human judgment.
- **Daily light Lint**: a fast subset (broken links / MyContext consistency / frontmatter) restricted to files touched that night.

The user wakes up to a Vault that has organized itself overnight, with a per-night report and a `log.md` audit trail.

## 2. Non-goals

- **Query layer (Condition 1)** — MCP exposure of the Vault to Claude Desktop / other AIs is a separate spec.
- **Auto-ingestion at the source (Condition 2)** — Web Clipper / YT Obsidian / Quick Capture are already in place; this spec only consumes what they drop in `00_Inbox/`.
- **Morning briefing / call-transcript processing** — the reference X post mentions these; they are out of scope for this spec.
- **Real-time / on-save processing** — this is a batch system. Latency between drop and processing can be up to 24h.
- **Cloud execution** — the Vault lives in iCloud Drive; the agent runs locally on the user's MacBook.

## 3. Architecture overview

### 3.1 Three-layer model (LLM Wiki pattern)

| Layer | Vault folders | Agent permission |
|---|---|---|
| **Raw sources** (immutable) | `Resources/`, `Archive/` | write-only (destination); never edit/delete existing files |
| **Wiki** (LLM-owned) | `Projects/` (append-only), `Ideas/` (full read/write), `Context/` (full read/write *via proposal file only* for `*.md`) | per-folder rules in §4 |
| **Schema** (human-owned) | `CLAUDE.md`, `Context/_routing-rules.md`, `Context/MyContext.md` | LLM reads only |

### 3.2 End-to-end flow

```
[main vault @ iCloud Drive]
        │
        │ 1. pre-batch: skip-if-recent + git commit -am "snapshot YYYY-MM-DD"
        ▼
[~/Workspace/vault-workbench/  (git worktree, OUTSIDE iCloud)]
        │
        │ 2. branch: daily-YYYY-MM-DD
        │    claude -p "$(cat scripts/lib/prompts/ingest.md)" \
        │      --allowedTools Bash,Write,Read \
        │      --add-dir ~/Workspace/vault-workbench
        │
        │      ┌─ 03:00 daily : Ingest + light Lint
        │      └─ 03:30 Sunday: full Lint
        │
        │ 3. workbench commits → main `git merge --no-ff <branch>`
        ▼
   conflict?
      ├─ yes → `git merge --abort`, write *-CONFLICT.md report, osascript notify, stop
      └─ no  → main updated, write daily-report, append log.md, delete worktree+branch
```

### 3.3 Why git-worktree isolation

- The main Vault is in iCloud Drive and is edited from iPhone, iPad, and other Macs at any time.
- Worktree at `~/Workspace/vault-workbench/` is **outside iCloud sync**, so the agent's intermediate writes never fight iCloud.
- Concurrent edits made on `main` while the agent runs are surfaced as a normal `git merge` conflict — easy to detect, easy to abort safely.
- Rollback on failure: delete the worktree and branch; main is untouched.

## 4. Permission boundaries (per folder)

| Folder | Permission |
|---|---|
| `00_Inbox/` | Read → route to Projects/Ideas (append) → move original to Archive/ or Resources/. Never modify in place except by moving. |
| `Projects/` | Read + append-only (link & section append). Never create new notes. Never delete or rewrite existing prose. |
| `Ideas/` | Full read/write. May create, edit, append, or merge notes. |
| `Resources/` | **Write-only as a destination** (move target only). Once a file is in Resources/, it is immutable. |
| `Context/*.md` (other than MyContext) | Read only for the agent. Updates flow via `Context/_pending-updates/YYYY-MM-DD.md` proposal files for human review. |
| `Context/_routing-rules.md` | Read only. |
| `Context/MyContext.md` | Read + **append-only** to the `## Active Ideas` section when the agent creates a new Ideas note. All other content (Arrival Protocol, Active Projects, Self-info, Archives) is human-owned: the agent must not modify it. |
| `Context/_pending-updates/` | Full write (agent-owned). |
| `Archive/` | Write-only as a destination. Never edit existing archived files. |

Forbidden globally:
- Writing to the iCloud-synced main Vault directly. All writes go through the worktree.
- Creating any `index.md` other than the existing `MyContext.md`.
- `WebFetch` or any tool other than `Bash`, `Write`, `Read` (enforced by `--allowedTools`).

## 5. Routing logic

### 5.1 Configuration: `Context/_routing-rules.md`

Single source of truth for tag-to-destination mapping and frontmatter normalization. Adding/removing a tag is a one-line edit.

```markdown
# Routing Rules

## Tag-based routing (highest priority — no LLM judgment)

| Tag        | Destination  | Note                                            |
|------------|--------------|-------------------------------------------------|
| clippings  | Resources/   | Web Clipper imports (primary source material)   |
| tubescribe | Resources/   | YT Obsidian + MacWhisper transcripts            |

## Frontmatter normalization map

| Source variants       | Canonical |
|-----------------------|-----------|
| #AI, #ai, #Ai         | #ai       |
| #claude, #Claude      | #claude   |

## LLM judgment fallback (no matching tag)

Read the note body and pick the first matching destination, in this order:

1. Clear relation to an existing project → append to that Projects/ note; move original to Archive/
2. New self-information learned (e.g., from an AI chat log) → append a proposal block to Context/_pending-updates/YYYY-MM-DD.md; move original to Archive/
3. New idea / future material / unfiled thought → create or append in Ideas/; move original to Archive/
4. None of the above → move to Archive/ unchanged

## Empty note threshold (L2)

body length < 100 chars → Archive/orphans/
```

### 5.2 Per-note ingest procedure

For each file in `00_Inbox/`:

1. Read frontmatter tags.
2. If any tag matches the **Tag-based routing** table → move to that destination unchanged. Skip LLM judgment. Go to step 6.
3. Otherwise read body and pick a destination from the **LLM judgment fallback** list.
4. Execute the destination-specific full-Ingest action (§5.3).
5. Move the original file to `Archive/` (or to `Resources/` for tag-routed primary sources).
6. Append one entry to `log.md` in the format specified in §8.

### 5.3 Destination-specific actions (full LLM Wiki Ingest, "depth C")

**→ Resources/** (tag-driven)
- Move original into `Resources/` keeping filename.
- Search for related Projects / Ideas notes; for each match:
  - Append a wikilink to the related note's `## Related Sources` section (create if missing).
  - Append a back-link to the Resources note's `## Related Notes` section.
- If the source mentions an undocumented concept that is repeatedly relevant, create a new concept page in `Ideas/`.
- **Do not** add Resources entries to MyContext.md (Resources are not part of the curated index — see §6).

**→ Projects/&lt;existing&gt;/** (LLM judgment)
- Identify the most relevant existing project note.
- Append the new content (or a summary of it) to an appropriate section of that note, citing the original via wikilink.
- Move the original to `Archive/`.
- **Never create a new Projects note.** If no project clearly matches, fall back to Ideas/.

**→ Ideas/** (LLM judgment)
- Either append to a closely matching existing Ideas note or create a new note.
- Add bidirectional wikilinks to related notes.
- Append a one-line entry under `## Active Ideas` in MyContext.md if a new note was created.
- Move the original to `Archive/`.

**→ Context/_pending-updates/YYYY-MM-DD.md** (LLM judgment)
- Append a proposal block in this exact form:
  ```markdown
  ## Proposed update to [[Context/Professional-Identity]]
  Source: [[Archive/2026-04-27-claude-chat-log]]
  Suggested addition:
  > Starting April 2026, introduced automated Vault organization using Claude Code...
  ```
- Never modify an existing `Context/*.md` file. The pending file is the only output.
- Move the original to `Archive/`.

**→ Archive/** (fallback)
- Move unchanged. No links added.
- Tag the log.md entry with `low-value`.

### 5.4 Ambiguous notes

If the agent cannot confidently pick a destination (multiple equally plausible candidates, unreadable content, etc.):

- Leave the original in `00_Inbox/` (do not move).
- Record under "Unprocessed" in the daily report with a reason.
- The next daily batch retries automatically. After three consecutive failures, raise a WARNING flag in the report.

## 6. Index strategy

`MyContext.md` is the **single index of the Vault**. There is no separate `index.md`.

- MyContext lists only currently-relevant material: active Projects, active Ideas, self-info pages.
- Archived content is reachable via `archived_idea_index.md`, `archived_projects_index.md`, etc., which MyContext links to.
- Resources are NOT listed in MyContext (they are immutable raw sources, reachable via the Wiki notes that reference them).
- Logs and reports are reachable via `Archive/logs/`, `Archive/daily-reports/`, `Archive/lint-reports/` directory links from MyContext.

The agent updates MyContext only by **appending** new Active-Ideas entries when it creates a new note. All other MyContext changes are human-driven.

## 7. Lint

### 7.1 Light Lint (every night, runs in the same batch as Ingest)

Scope: only files touched in tonight's Ingest, plus `MyContext.md`. Target runtime &lt; 1 minute.

| ID | What | Mode |
|---|---|---|
| L1-light | Wikilinks added tonight resolve to existing notes | Auto-fix (typo correction by close-name match) or report |
| L7 | MyContext.md links resolve | Auto-fix (remove dead, retarget renamed) |
| L8 | Frontmatter on tonight's edited notes follows the normalization map | Auto-fix |

### 7.2 Full Lint (Sunday 3:30, separate batch)

Scope: entire Vault. Target runtime 5–15 minutes.

**Auto-fix mode:**

| ID | What | Auto-fix |
|---|---|---|
| L1 | All broken wikilinks | Repair by close-name match; if ambiguous, escalate to report |
| L2 | Empty / near-empty notes (body &lt; 100 chars) | Move to `Archive/orphans/` (never delete) |
| L7 | All MyContext links | As in light Lint, applied across whole index |
| L8 | Frontmatter normalization across entire Vault | Apply normalization map |

**Report-only mode** (output to `Archive/lint-reports/YYYY-MM-DD-weekly.md`):

| ID | What | Report content |
|---|---|---|
| L3 | Duplicate / near-duplicate notes | Pairs + similarity score + merge suggestion |
| L4 | Orphan notes (no inbound links) | List + archive-or-link suggestion |
| L5 | Contradictions across notes on the same topic | Excerpts + flag |
| L6 | Concepts mentioned in many notes but lacking a page | List + draft concept-page skeleton |

### 7.3 Lint report structure

```markdown
---
type: lint-report
date: 2026-04-26
mode: full
---

# Weekly Lint Report (2026-04-26)

## Auto-fixed
- L1: 3 broken links repaired (`[[old-name]]` → `[[new-name]]`)
- L2: 2 empty notes moved to Archive/orphans/
- L7: 1 stale MyContext entry removed

## Needs review

### L3: Duplicate candidates
- [[Ideas/agent-loop]] vs [[Ideas/agent-loop-v2]] — similarity 0.87
  - Suggestion: merge v2 into v1
  - Diff: ...

### L4: Orphans
...

## Linked from
[[MyContext]]
```

## 8. Logging and reports

### 8.1 `log.md` (Vault root, current month only)

Append-only. Entry format:

```markdown
## [YYYY-MM-DD HH:MM] <ingest|lint-light|lint-full|merge> | <summary>
- file: <inbox-path>
- destination: <new-path>
- linked: [[note-a]], [[note-b]]
- result: success | conflict | aborted
```

### 8.2 Monthly rotation

On the first run of each month (typically the Sunday full Lint), the agent slices everything older than the current month out of `log.md` and appends it to `Archive/logs/YYYY-MM.md`. The active `log.md` only contains the current month.

### 8.3 Daily report

`Archive/daily-reports/YYYY-MM-DD.md` is written at the end of each batch:

```markdown
---
type: daily-report
date: 2026-04-28
mode: ingest+light-lint
result: success
---

# Daily Report 2026-04-28

## Processed (N=12)
- [[Archive/...-clip-1]] ← from Inbox via tag `clippings` → Resources/, linked: [[Ideas/...]]
- ...

## Unprocessed (N=1)
- 00_Inbox/foo.md — reason: ambiguous between Projects/A and Projects/B (1st failure)

## Light Lint
- L1: 0 issues
- L7: 1 fixed
- L8: 0 issues

## Conflict / errors
(none)
```

A `*-SKIPPED.md` variant is written when pre-batch skip-if-recent triggers, and a `*-CONFLICT.md` variant is written when the merge into main conflicts.

## 9. Execution

### 9.1 Trigger

`launchd` user agents:

- `~/Library/LaunchAgents/com.user.vault-organizer.ingest.plist` — daily at 03:00 → `scripts/daily-ingest.sh`
- `~/Library/LaunchAgents/com.user.vault-organizer.lint.plist` — Sunday 03:30 → `scripts/weekly-lint.sh`

`launchd` is preferred over cron because it survives macOS sleep/wake correctly via `StartCalendarInterval`.

### 9.2 Pre-batch safety: skip-if-recent

When invoked with `--check-recent` (the flag launchd passes via the plist), the orchestrator lists files in the Vault modified in the last 5 minutes before the pre-batch commit. If any exist, the run is skipped (the user is likely still working) and a `*-SKIPPED.md` report is written. The next scheduled run will retry.

Manual invocations omit `--check-recent` and always run regardless of recent edits — used for the smoke test or for re-running on demand.

### 9.3 Worktree lifecycle

```
1. cd <main vault>
2. git add -A && git commit -m "snapshot before <run-id>"   # no-op if clean
3. git worktree add ~/Workspace/vault-workbench -b <run-id>  # destroy any pre-existing
4. cd ~/Workspace/vault-workbench
5. claude -p "$(cat <main vault>/scripts/lib/prompts/<ingest|lint-full>.md)" \
       --allowedTools Bash,Write,Read \
       --add-dir ~/Workspace/vault-workbench
6. git add -A && git commit -m "<run-id>"   # no-op if agent made no changes
7. cd <main vault>
8. git merge --no-ff <run-id> -m "merge <run-id>"
   - on conflict: git merge --abort; write *-CONFLICT.md; osascript notify; exit 1
9. git worktree remove ~/Workspace/vault-workbench
10. git branch -D <run-id>
```

### 9.4 Agent invocation

```
claude -p "$(cat <vault>/scripts/lib/prompts/ingest.md)" \
  --allowedTools Bash,Write,Read \
  --add-dir ~/Workspace/vault-workbench
```

`--allowedTools Bash,Write,Read` is mandatory. WebFetch and other network/external tools are excluded — daily batches are local-only.

### 9.5 macOS prerequisites

- The user must grant Full Disk Access to `/bin/bash` (or to the launchd-spawned shell) via System Settings → Privacy & Security so that the agent can read/write inside `~/Library/Mobile Documents/...`.
- Node / Claude CLI must be on the PATH used by launchd (use absolute paths in the plist's `EnvironmentVariables` if needed).

## 10. CLAUDE.md (Vault root)

The agent reads this on every run before doing anything else. Section outline:

```
0. Boot sequence (read this → MyContext.md → _routing-rules.md → tail of log.md)
1. Vault folder responsibilities
2. Permission table (§4 of this spec)
3. Routing rules (pointer to _routing-rules.md + LLM-judgment fallback ordering)
4. Ingest procedure (§5.2, §5.3)
5. Lint procedure (light §7.1, full §7.2)
6. Logging and reports (§8 formats)
7. MUST NOT (forbidden actions, see below)
8. Failure protocol (ambiguous → leave in Inbox; 3 failures → WARNING; merge conflict → abort+notify)
9. Log entry format (§8.1)
10. Monthly log rotation rule (§8.2)
```

### 10.1 MUST NOT (forbidden actions)

- Edit or delete existing files in `Resources/` or `Archive/`.
- Create new notes in `Projects/`.
- Overwrite or delete existing prose in any `Context/*.md` (use `_pending-updates/` instead).
- Create any `index.md` other than `MyContext.md`.
- Write to the iCloud-synced main Vault directly (only via worktree).
- Commit without a message.

## 11. MyContext.md changes

Add / update the AI Arrival Protocol section so it points the agent at CLAUDE.md first:

```markdown
## AI Arrival Protocol

To any AI arriving here:
1. Read `/CLAUDE.md` in full before doing any work in this Vault.
2. Then follow the section links in this file (MyContext.md).
3. Strictly observe the routing/editing permission boundaries in CLAUDE.md §2.

## Active Projects
- [[Projects/...]]

## Active Ideas
- [[Ideas/...]]

## Self-info
- [[Context/Professional-Identity]]
- [[Context/Philosophy-Values]]
- ...

## Archives (jump-only)
- [[archived_idea_index]]
- [[archived_projects_index]]
- Logs: [[Archive/logs]]
- Daily reports: [[Archive/daily-reports]]
- Lint reports: [[Archive/lint-reports]]
```

## 12. File layout (new + modified)

```
[Vault root]
├── CLAUDE.md                                          [NEW]
├── log.md                                             [NEW]
├── .gitignore                                         [NEW or MODIFIED]
│
├── Context/
│   ├── MyContext.md                                   [MODIFIED — Arrival Protocol section]
│   ├── _routing-rules.md                              [NEW]
│   └── _pending-updates/
│       └── .gitkeep                                   [NEW]
│
├── Archive/
│   ├── logs/.gitkeep                                  [NEW]
│   ├── daily-reports/.gitkeep                       [NEW]
│   ├── lint-reports/.gitkeep                          [NEW]
│   └── orphans/.gitkeep                               [NEW]
│
└── scripts/
    ├── daily-ingest.sh                              [NEW]
    ├── weekly-lint.sh                                 [NEW]
    └── lib/
        ├── worktree-prepare.sh                        [NEW]
        ├── worktree-merge.sh                          [NEW]
        └── prompts/
            ├── ingest.md                              [NEW]
            └── lint-full.md                           [NEW]

[~/Library/LaunchAgents/]
├── com.user.vault-organizer.ingest.plist              [NEW]
└── com.user.vault-organizer.lint.plist                [NEW]

[~/Workspace/vault-workbench/]                         [NEW worktree, created at first run]
```

`.gitignore` additions:

```
.obsidian/workspace.json
.obsidian/workspace-mobile.json
.obsidian/cache
.DS_Store
.trash/
```

## 13. Initial setup checklist (executed by human, detailed in the implementation plan)

1. Create the new files / directories listed in §12.
2. Update `MyContext.md` with the new Arrival Protocol section.
3. Verify `claude` CLI is on PATH (`claude --version`).
4. Place a few synthetic test notes in `00_Inbox/`, then run `scripts/daily-ingest.sh` manually and verify expected behavior.
5. Install launchd plists with `launchctl bootstrap gui/$(id -u) <plist>`.
6. Confirm scheduling with `launchctl print gui/$(id -u)/com.user.vault-organizer.ingest`.
7. Grant Full Disk Access to bash if needed.

## 14. Open questions / assumptions

- L2 empty-note threshold of 100 chars is a starting value; can be tuned.
- The agent uses the `claude` CLI from the user's PATH at launchd-run time. If this changes (e.g., switching to Claude Agent SDK), only the script body changes — the plist and architecture do not.
- Conflict notification is via `osascript -e 'display notification ...'`. If the user prefers email / Pushover / something else, that's a one-line change in `worktree-merge.sh`.
