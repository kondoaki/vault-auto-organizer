# Vault Auto-Organizer

Unattended ingestion + weekly lint for an Obsidian Vault, driven by an agent CLI (`claude` or `opencode`).

See [SPEC.md](SPEC.md) for the design.

## What it does

- **Every night at 03:00** — reads `00_Inbox/`, routes each note to its destination (Resources/Projects/Ideas/Archive), runs a fast Lint on touched files, writes a per-night report.
- **Every Sunday at 03:30** — runs the full 8-item Lint across the entire Vault.

The agent runs inside an isolated git worktree at `~/Workspace/vault-workbench/` (outside the Vault, so the agent's edits don't interleave with any sync activity on the Vault itself), and its commits are merged back into the Vault via `git merge --no-ff`. Conflicts abort safely.

## Requirements

- macOS (uses launchd + osascript)
- bash 3.2+
- git
- An agent CLI on PATH: `claude` (default) or `opencode`
- `rsync` (system default)

## Install

First, set your Vault path. Copy `.env.example` to `.env` and edit `VAULT_PATH`:

```sh
cp .env.example .env
$EDITOR .env
```

`install.sh` auto-sources `.env`, so subsequent commands don't need the path argument:

```sh
./install.sh
```

You can also pass the path explicitly (overrides `.env`):

```sh
./install.sh "$VAULT_PATH"
```

To use opencode instead of Claude Code:

```sh
./install.sh --backend opencode
```

The choice is fixed at install time — `install.sh` ships only the chosen backend's invocation snippet into `<vault>/scripts/lib/agent-backends/`. Switch backends by re-running install with a different `--backend`.

This is **idempotent** — re-run it whenever the source repo changes (it `rsync`s `scripts/` and rewrites `CLAUDE.md` and the plists).

After install, activate the schedule with the commands below.

### Activating the schedule

```sh
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.user.vault-organizer.ingest.plist
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.user.vault-organizer.lint.plist
```

Verify registration (both jobs should appear):

```sh
launchctl list | grep vault-organizer
```

### Deactivating the schedule

```sh
launchctl bootout gui/$(id -u) ~/Library/LaunchAgents/com.user.vault-organizer.ingest.plist
launchctl bootout gui/$(id -u) ~/Library/LaunchAgents/com.user.vault-organizer.lint.plist
```

### Updating scripts (re-registration not required)

The scripts that actually run live inside the Vault (`<vault>/scripts/`), not in this repo. After editing `.sh` files under this repo's `scripts/`, sync them into the Vault by re-running install:

```sh
./install.sh --no-launchd-bootstrap
```

`--no-launchd-bootstrap` suppresses the bootstrap-instructions banner since the schedule is already active. No `launchctl` re-registration is needed for script-only changes.

### Updating the schedule or paths (re-registration required)

Editing a plist directly (e.g. to change the schedule time):

```sh
# 1. Unregister
launchctl bootout gui/$(id -u) ~/Library/LaunchAgents/com.user.vault-organizer.ingest.plist

# 2. Edit the plist
vi ~/Library/LaunchAgents/com.user.vault-organizer.ingest.plist

# 3. Re-register
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.user.vault-organizer.ingest.plist
```

If you changed a plist template in `templates/plists/` in this repo, re-run `install.sh` first to regenerate the plist, then follow the same bootout → bootstrap sequence above.

## Manual smoke test (perform once after first install)

1. Drop two test notes into `<vault>/00_Inbox/`:
   - `test-clip.md` with frontmatter `tags: [clippings]` and 5+ lines of body.
   - `test-idea.md` with no tags, 5+ lines of body describing some new idea.
2. Run the batch immediately (manual invocations skip the 5-minute recency check):

   ```sh
   "$VAULT_PATH/scripts/daily-ingest.sh"
   ```
3. Verify:
   - `test-clip.md` is in `<vault>/Resources/`.
   - `test-idea.md` is in `<vault>/Ideas/` (or appended to a related Ideas note) and the original is in `<vault>/Archive/`.
   - `<vault>/log.md` has new entries.
   - `<vault>/Archive/daily-reports/<today>.md` exists.
   - `git -C <vault> log --oneline` shows a `merge daily-<today>` commit.

## Tests

```sh
make test
```

Tests use a synthetic Vault under `mktemp -d` and per-backend mocks under `tests/fixtures/{claude,opencode}-mock/`. Real agent invocations are exercised only by the manual smoke test above.

## Configuration

- `<vault>/Context/_routing-rules.md` — tag → destination map. User-editable; agent re-reads it every run.
- `<vault>/CLAUDE.md` — agent operating manual. Overwritten by `install.sh`. Edit the template at `templates/CLAUDE.md` in this repo, then re-run install.
- `<vault>/scripts/lib/config.sh` — paths (Vault, workbench, agent binary). Rendered by `install.sh`. Holds `CLAUDE_BIN` or `OPENCODE_BIN` depending on `--backend`.
- `<vault>/scripts/lib/agent-backends/` — only the chosen backend's snippet (and any backend-specific config like `opencode/opencode.json`).

### opencode model selection

When `--backend opencode` is used, the model is controlled by the `"model"` key in [scripts/lib/agent-backends/opencode/opencode.json](scripts/lib/agent-backends/opencode/opencode.json) — both in the source repo and in the Vault copy. Default is `ollama/gemma4:26b` (local LLM). Format is `provider/model` per [opencode's model docs](https://opencode.ai/docs/models). To change it, edit the source `opencode.json` in the Vault.

## Troubleshooting

- **launchd job didn't run**: check `~/Library/Logs/vault-organizer-{ingest,lint}.{log,err}`.
- **agent CLI not found at runtime**: edit the plist's `PATH` env var, or re-run install (it captures `which claude` / `which opencode`).
- **Conflict**: `<vault>/Archive/daily-reports/<date>-CONFLICT.md` describes which files clashed and how to recover.
- **Skipped runs**: `<vault>/Archive/daily-reports/<date>-SKIPPED.md` means a scheduled (launchd) run was skipped because the Vault was edited within 5 minutes before the run. The 5-minute guard only applies when the script is invoked with `--check-recent` (which the launchd plists do); manual invocations always run.
