PY ?= .venv-dev/bin/python

.PHONY: test test-unit test-integration shellcheck clean

test:
	$(PY) -m pytest

test-unit:
	$(PY) -m pytest tests/unit

test-integration:
	$(PY) -m pytest tests/integration

shellcheck:
	shellcheck install.sh

clean:
	rm -rf tests/tmp .pytest_cache
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
