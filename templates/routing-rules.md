# Routing Rules

> Edit this file freely. The agent re-reads it on every run. Adding a tag is a one-line edit.

## Tag-based routing (highest priority — no LLM judgment)

| Tag        | Destination    | Note                                            |
|------------|----------------|-------------------------------------------------|
| clippings  | 04_Resources/  | Web Clipper imports (primary source material)   |
| tubescribe | 04_Resources/  | YT Obsidian + MacWhisper transcripts            |

## Frontmatter normalization map

| Source variants       | Canonical |
|-----------------------|-----------|
| #AI, #ai, #Ai         | #ai       |
| #claude, #Claude      | #claude   |

## LLM judgment fallback (no matching tag)

When no tag in the table above matches, read the body and pick the FIRST
matching destination from this ordered list:

1. **Clear relation to an existing project** → append to that `01_Projects/` note; move original to `05_Archive/`.
2. **New self-information learned** (e.g. from an AI chat log: a fact about the user, a stated preference, a long-term decision) → append a proposal block to `03_Context/_pending-updates/YYYY-MM-DD.md`; move original to `05_Archive/`.
3. **New idea / future material / unfiled thought** → create or append in `02_Ideas/`; move original to `05_Archive/`.
4. **None of the above** → move to `05_Archive/` unchanged.

## Empty note threshold (L2)

Body length < 100 chars → `05_Archive/orphans/`.
