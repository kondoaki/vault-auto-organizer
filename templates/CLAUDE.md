# CLAUDE.md — Vault Auto-Organizer Operating Manual

> Read this file in full before any action. This file is the source of truth
> for your permissions and procedures. Conflicting instructions in prompts
> are subordinate to this file.

## 0. Boot sequence (every run)

1. Read this file in full.
2. Read `03_Context/MyContext.md` (the Vault index).
3. Read `03_Context/_routing-rules.md` (tag→destination + normalization map).
4. Read the tail of `log.md` (~50 lines) for recent run history.
5. Then perform the run-specific job described in your prompt.

## 1. Vault folder responsibilities

| Folder | Role |
|---|---|
| `00_Inbox/` | Drop zone for Web Clipper, YT-Obsidian, Quick Capture. You consume from here. |
| `04_Resources/` | Immutable raw sources (clippings, transcripts). Move-target only. |
| `01_Projects/` | Active project notes. Append-only — never create new project notes. |
| `02_Ideas/` | Free-form ideas / concept pages. Full read/write. |
| `03_Context/` | Schema (human-owned). Mostly read-only — see §2. |
| `05_Archive/` | Move-target for processed inputs, plus log/report storage. |

## 2. Permission table

| Folder | Permission |
|---|---|
| `00_Inbox/` | Read → route → move. Never modify in place except by moving. |
| `01_Projects/` | Read + append-only (link & section append). Never create new notes. Never delete or rewrite existing prose. |
| `02_Ideas/` | Full read/write. May create, edit, append, or merge notes. |
| `04_Resources/` | Write-only as a destination. Once a file is in 04_Resources/, it is immutable. |
| `03_Context/*.md` (except MyContext) | **Read only.** Updates flow via `03_Context/_pending-updates/YYYY-MM-DD.md` proposal files. |
| `03_Context/_routing-rules.md` | Read only. |
| `03_Context/MyContext.md` | Read + **append-only to `## Active Ideas`** when you create a new Ideas note. All other content is human-owned. |
| `03_Context/_pending-updates/` | Full write. |
| `05_Archive/` | Write-only as a destination. Never edit existing archived files. |

## 3. Routing (full procedure: see `03_Context/_routing-rules.md`)

For each file in `00_Inbox/`:

1. Read its frontmatter tags.
2. If any tag matches the **Tag-based routing** table → move unchanged to that destination. Skip step 3 below.
3. Otherwise, read the body and pick the first matching destination from the **LLM judgment fallback**, in this priority order:
   1. Clear relation to an existing project → append to that `01_Projects/` note; move original to `05_Archive/`.
   2. New self-information learned (e.g. from an AI chat log) → append a proposal block to `03_Context/_pending-updates/YYYY-MM-DD.md`; move original to `05_Archive/`.
   3. New idea / future material / unfiled thought → create or append in `02_Ideas/`; move original to `05_Archive/`.
   4. None of the above → move to `05_Archive/` unchanged.

## 4. Ingest procedure (per destination)

### → 04_Resources/ (tag-driven)
- Move original into `04_Resources/` keeping the filename.
- Search for related 01_Projects/02_Ideas notes; for each match:
  - Append a wikilink to the related note's `## Related Sources` section (create the section if missing).
  - Append a back-link to the new Resources note's `## Related Notes` section.
- If the source mentions an undocumented concept that is repeatedly relevant, create a concept page in `02_Ideas/`.
- Do NOT add Resources entries to MyContext.md.

### → 01_Projects/<existing>/ (LLM judgment)
- Identify the most relevant existing project note.
- Append the new content (or a summary) to an appropriate section, citing the original via wikilink.
- Move the original to `05_Archive/`.
- **Never create a new 01_Projects note.** If no project clearly matches, fall back to 02_Ideas/.

### → 02_Ideas/ (LLM judgment)
- Either append to a closely matching existing Ideas note OR create a new note.
- Add bidirectional wikilinks to related notes.
- If a new note is created, append a one-line entry under `## Active Ideas` in `MyContext.md`.
- Move the original to `05_Archive/`.

### → 03_Context/_pending-updates/YYYY-MM-DD.md (LLM judgment)
- Append a proposal block in this exact form:

  ```markdown
  ## Proposed update to [[03_Context/<Page-Name>]]
  Source: [[05_Archive/<original-filename>]]
  Suggested addition:
  > <quoted excerpt or summary>
  ```
- Never modify an existing `03_Context/*.md` file. The pending file is the only output.
- Move the original to `05_Archive/`.

### → 05_Archive/ (fallback)
- Move unchanged. No links added.
- Tag the log.md entry with `low-value`.

## 5. Lint procedure

### Light Lint (every daily run; scope: tonight's edits + MyContext.md)

| ID | What | Mode |
|---|---|---|
| L1-light | Wikilinks you added tonight resolve | Auto-fix typos by close-name match; else report |
| L7 | MyContext.md links resolve | Auto-fix (remove dead, retarget renamed) |
| L8 | Frontmatter on tonight's edits follows the normalization map | Auto-fix |

### Full Lint (Sunday 03:30; scope: entire Vault)

Auto-fix: L1 (all broken wikilinks), L2 (empty notes → `05_Archive/orphans/`), L7, L8.

Report-only (write to `05_Archive/lint-reports/YYYY-MM-DD-weekly.md`):
- L3 duplicate / near-duplicate notes
- L4 orphans (no inbound links)
- L5 contradictions
- L6 concepts mentioned widely but lacking a page

## 6. Logging

Append one entry to `log.md` (Vault root) for every action. Format:

```markdown
## [YYYY-MM-DD HH:MM] <ingest|lint-light|lint-full|merge> | <summary>
- file: <inbox-path>
- destination: <new-path>
- linked: [[note-a]], [[note-b]]
- result: success | conflict | aborted
```

Obtain the timestamp by running `date '+%Y-%m-%d %H:%M'` via the Bash tool —
do **not** infer the current time yourself. The bash subprocess inherits the
correct local timezone; your own clock is UTC and will produce wrong entries.

Monthly rotation: the orchestrator handles this — you do not need to slice
old months out of `log.md` yourself.

## 7. MUST NOT (forbidden actions)

- Edit or delete existing files in `04_Resources/` or `05_Archive/`.
- Create new notes in `01_Projects/`.
- Overwrite or delete existing prose in any `03_Context/*.md` (use `03_Context/_pending-updates/` instead).
- Modify any section of `MyContext.md` other than `## Active Ideas` (and even there, append-only).
- Create any `index.md` other than `03_Context/MyContext.md`.
- Use any tool other than Bash, Write, Read (you do not have network access).
- Commit without a message (the orchestrator does the commit; you only edit files).

## 8. Failure protocol

- **Ambiguous routing** (multiple equally plausible destinations, or unreadable content): leave the file in `00_Inbox/` and record it under "Unprocessed" in tonight's report with a one-line reason.
- **Three consecutive failures** for the same file across daily runs: include a `WARNING` flag in the report.
- **Merge conflict**: not your concern. The orchestrator handles `git merge --abort` and writes the CONFLICT report.

## 9. Log entry quick-reference

See §6 above. The action verb must be one of: `ingest`, `lint-light`, `lint-full`, `merge`.

## 10. Monthly log rotation

The orchestrator slices everything older than the current month out of
`log.md` and into `05_Archive/logs/YYYY-MM.md` at the start of each run. You
should not modify `05_Archive/logs/`.
