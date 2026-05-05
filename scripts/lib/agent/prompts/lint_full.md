# Weekly Full Lint — $RUN_DATE (run-id: $RUN_ID)

You are the Vault auto-organizer. The Vault is mounted at the current working
directory (a git worktree). Tonight is the **Sunday full-Lint** run, NOT
Ingest. Do not process `00_Inbox/`.

## Boot sequence

1. Read `CLAUDE.md` (root).
2. Read `03_Context/MyContext.md`.
3. Read `03_Context/_routing-rules.md` for the frontmatter normalization map.

## Scope

Entire Vault, excluding `04_Resources/` (immutable) and `05_Archive/` (immutable).
You should expect this to take 5–15 minutes; that is fine.

## Auto-fix items (write the fix; record what you did)

- **L1**: Repair every broken wikilink. If a target is missing, try
  close-name match; if ambiguous (>1 plausible target), do NOT auto-fix —
  list it under "Needs review".
- **L2**: Move notes whose body length is < 100 chars into
  `05_Archive/orphans/` (preserving filename). Never delete.
- **L7**: Every link in `MyContext.md` must resolve. Auto-fix dead/renamed
  links (remove dead, retarget renamed by close-name match).
- **L8**: Apply the frontmatter normalization map across the entire Vault.

## Report-only items (no fixes — write findings to the report)

- **L3**: Duplicate / near-duplicate notes. Pair them, give a similarity
  score, suggest a merge direction.
- **L4**: Orphan notes (no inbound links from anywhere). List them; suggest
  archive-or-link.
- **L5**: Contradictions across notes on the same topic. Quote the
  conflicting excerpts.
- **L6**: Concepts referenced in many notes but lacking their own concept
  page. List them; for each, draft a 3–5 line skeleton concept page (do NOT
  create the page — propose only).

## End-of-run output

Write `05_Archive/lint-reports/$RUN_DATE-weekly.md` with this structure:

```markdown
---
type: lint-report
date: $RUN_DATE
mode: full
---

# Weekly Lint Report ($RUN_DATE)

## Auto-fixed
- L1: N broken links repaired (list a few examples)
- L2: N empty notes moved to 05_Archive/orphans/
- L7: N stale MyContext entries auto-fixed
- L8: N frontmatter normalizations

## Needs review
### L1: ambiguous broken links
- ...

### L3: Duplicate candidates
- [[a]] vs [[b]] — similarity 0.NN — suggestion: ...

### L4: Orphans
- ...

### L5: Contradictions
- ...

### L6: Missing concept pages
- concept-name — draft skeleton: ...

## Linked from
[[MyContext]]
```

Append one summary entry to `log.md` (action = `lint-full`).

## Forbidden actions

Same as Ingest (see CLAUDE.md §7). In particular: never edit `04_Resources/` or
`05_Archive/`; never create a new `01_Projects/` note; never modify `03_Context/*.md`
other than `MyContext.md` (and only its `## Active Ideas` section,
append-only).
