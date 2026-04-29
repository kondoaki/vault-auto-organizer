# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Rules

- **Public repo**: never commit `.env`, `scripts/lib/config.sh`, or rendered plists (gitignored). Don't paste real `VAULT_PATH`, `$HOME` paths, hostnames, note titles, or Vault contents into source, tests, fixtures, commit messages, or `templates/CLAUDE.md`. Tests must use `mktemp -d` synthetic Vaults — never point at a real Vault.
- **Never `git push` without explicit user permission per push.** Prior approval doesn't carry over.

## Commands

- `make test` / `test-unit` / `test-integration` — bats suites; `make shellcheck` — lint shell
- `tests/lib/bats-core/bin/bats --filter 'NAME' tests/test_X.bats` — single case
- `git submodule update --init --recursive` — required after clone (bats lives in `tests/lib/`)
- `./install.sh [--backend claude|opencode] [--no-launchd-bootstrap]` — render & rsync into Vault from `.env`'s `VAULT_PATH`

## Architecture

Nothing here runs on a schedule. `install.sh` rsyncs `scripts/` into the user's Vault and `sed`-renders `templates/` (`__TOKEN__` placeholders) into `<vault>/CLAUDE.md`, `config.sh`, plists, and `MyContext.md`; **launchd** then triggers the in-Vault copies — editing a script here is a no-op until install is re-run.

**Two CLAUDE.md, different audiences**: this one guides Claude Code on the source. `templates/CLAUDE.md` is the runtime manual for the in-Vault LLM agent (`claude` or `opencode` CLI). Don't conflate them.

**Runtime** (in the Vault): snapshot commit → git worktree at `~/Workspace/vault-workbench/` (outside iCloud sync, so concurrent iPhone/iPad edits surface as normal merge conflicts) → agent invoked with `--allowedTools Bash,Write,Read` and a prompt from `lib/prompts/` → `git merge --no-ff` back; conflicts abort and write `*-CONFLICT.md`.

**Backend**: `claude` vs `opencode` is chosen at install time; only the selected `scripts/lib/agent-backends/<backend>.sh` ships. Keep both snippets' `invoke_agent` interface identical. **Vault folders** are numbered (`00_Inbox/`…`05_Archive/`); match `install.sh`, not SPEC.md prose. Integration tests use mocks under `tests/fixtures/{claude,opencode}-mock/`; real agent invocation only via the manual smoke test in README.md. See [SPEC.md](SPEC.md) §4/§5/§7 — changes there must propagate to `templates/CLAUDE.md` and `scripts/lib/prompts/`.
