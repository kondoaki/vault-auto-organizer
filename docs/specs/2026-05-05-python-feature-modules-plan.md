# 実装プラン — Python Feature Modules

> 関連 spec: [2026-05-05-python-feature-modules-design.md](2026-05-05-python-feature-modules-design.md)
> 方針: ステップ毎にテストが通る状態を保つ。bats と Python の混在期間は作らない（最後に一括で bats を捨てる）。

## 進め方

10 ステップ。各ステップ末に `make test`（または手動 smoke）でグリーン確認、commit、ユーザー承認を得てから次へ。

## 作業ブランチ
feature/convert-to-python

---

## Step 1. 開発環境セットアップ

- `requirements-dev.txt` 作成（pytest, pytest-mock）
- リポジトリ `.gitignore` 更新（`.venv-dev/`, `__pycache__/`, `*.pyc`, `scripts/lib/config/local.py`）
- README に開発者向けセットアップ手順追記
- 動作確認: `python3 -m venv .venv-dev && .venv-dev/bin/pip install -r requirements-dev.txt`

## Step 2. 共通基盤（lib/common, lib/config）

- `scripts/lib/__init__.py`, `scripts/lib/common/`, `scripts/lib/config/` を作成
- `lib/common/exceptions.py`: `OrganizerError`, `AgentError`, `WorktreeMergeConflict`, `SkipRun`
- `lib/common/run_id.py`, `iso_date.py`, `sync_origin.py`, `signals.py`
- `lib/config/__init__.py` の `Config` dataclass と `load()`
- `templates/config.py.template` を作成（`__VAULT_DIR__` 等のプレースホルダ）
- 各 feature に README.md 雛形
- 単体テスト: `tests/unit/test_common.py`, `test_config.py`

## Step 3. log と report

- `lib/log/`: append、月次ローテーション
- `lib/report/`: skipped / success / agent-failure / conflict の各 writer、commit
- 単体テスト: tmp vault に書き込んで内容を assert

## Step 4. git 系 feature

- `lib/snapshot/`, `lib/skip_if_recent/`, `lib/worktree/`, `lib/push/`
- `subprocess` で `git` を呼ぶ実装
- 単体テスト: tmp git リポジトリで snapshot → worktree-prepare → merge → cleanup の流れを assert
- conflict のテストは tmp で意図的に conflict を作って `WorktreeMergeConflict` が投げられることを確認

## Step 5. agent 系 feature

- `lib/agent/__init__.py`: `invoke_agent(cfg, run_id, prompt: str)` の公開 API
- `lib/agent/backends/claude.py`, `opencode.py`: 既存 bash backend と同じ引数を `subprocess` で組み立てる
- `lib/agent/prompts/ingest.md`, `lint_full.md` を既存からコピー
- 単体テスト: 既存 `tests/fixtures/{claude,opencode}-mock/` を流用、Python から呼べることを確認

## Step 6. メインバッチ（枠）

- `scripts/daily_ingest.py`, `scripts/weekly_lint.py`
- spec §3.3 の構造に従い feature を順に呼ぶ
- 既存 bash 版と同じ stdout / stderr / exit code を出すこと
- 統合テスト: `tests/integration/test_daily_ingest.py`, `test_weekly_lint.py`（mock backend で end-to-end）

## Step 7. install.sh 書き換え

- 既存 install.sh を Python 化に対応：
  - `--workbench-dir` フラグ削除、`.env` の `WORKBENCH_DIR` 読み取り
  - `VENV_DIR` を `.env`／既定値で解決し iCloud 外チェック
  - `python3 -m venv "$VENV_DIR"` で venv 作成
  - rsync 対象を新ディレクトリ構成に
  - `templates/config.py.template` を sed 展開して `lib/config/local.py` 生成
  - 末尾で FDA 案内を表示
- `.env.example` に `WORKBENCH_DIR`, `VENV_DIR` の説明追記
- 動作確認: tmp vault に install して `daily_ingest.py` が手動で起動すること

## Step 8. plist テンプレ更新

- `templates/plists/com.user.vault-organizer.{ingest,lint}.plist.template` を Python 起動に書き換え
- `LANG`, `LC_ALL`, `PYTHONUTF8` を `EnvironmentVariables` に追加
- install.sh で `__VENV_DIR__` を sed 置換するよう対応
- 動作確認: rendered plist の中身を目視 + `plutil -lint` で構文チェック

## Step 9. Makefile と shellcheck

- `Makefile` を pytest ベースに更新（spec §9.3）
- `make shellcheck` は `install.sh` のみ対象
- 動作確認: `make test`, `make test-unit`, `make test-integration`, `make shellcheck` がそれぞれグリーン

## Step 10. bats と旧 bash の撤去

- `tests/lib/bats-core/` submodule 削除（`git submodule deinit` → `git rm`）
- `.gitmodules` 更新
- `tests/test_*.bats` 削除
- `scripts/daily-ingest.sh`, `scripts/weekly-lint.sh`, `scripts/lib/*.sh`, `scripts/lib/agent-backends/`, `scripts/lib/prompts/`, `templates/config.sh.template` 削除
- 最終確認: `make test` グリーン、`./install.sh` で tmp vault に install → 手動 smoke テストが通ること

---

## 各ステップのコミット粒度

各ステップ = 1 コミット（または機能粒度で 2〜3 コミット）。コミットメッセージは英語、`feat:` / `refactor:` / `test:` / `chore:` のプレフィックス。

## ロールバック

各ステップは独立した commit なので `git revert` で個別に戻せる。Step 10 だけは大量削除なので、不安なら branch を分けて squash merge。

## 想定外時の方針

- 既存 bash の挙動と差分が出たら、まず既存挙動を正として Python を合わせる。spec の修正が必要な場合はユーザーに確認。
- macOS 固有の問題（FDA、文字コード、launchd 環境）が出たら spec §13 の対策表を見直し、追記。
