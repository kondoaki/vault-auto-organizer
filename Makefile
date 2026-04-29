BATS := tests/lib/bats-core/bin/bats

.PHONY: test test-unit test-integration shellcheck clean

test: test-unit test-integration

test-unit:
	$(BATS) tests/test_skip_if_recent.bats tests/test_log.bats tests/test_report.bats

test-integration:
	$(BATS) tests/test_worktree_prepare.bats tests/test_worktree_merge.bats \
	        tests/test_invoke_agent.bats tests/test_daily_ingest.bats \
	        tests/test_weekly_lint.bats tests/test_install.bats

shellcheck:
	shellcheck scripts/*.sh scripts/lib/*.sh scripts/lib/agent-backends/*.sh install.sh

clean:
	rm -rf tests/tmp
