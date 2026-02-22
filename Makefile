PYTHON ?= python3
APP_DIR ?= app

.PHONY: install lint format typecheck test compile check ci run-web cli-help release rollback

install:
	$(PYTHON) -m pip install -e "./$(APP_DIR)[dev]"

lint:
	cd $(APP_DIR) && $(PYTHON) -m ruff check app localfilesync

format:
	cd $(APP_DIR) && $(PYTHON) -m ruff format app localfilesync

typecheck:
	cd $(APP_DIR) && $(PYTHON) -m mypy app localfilesync

test:
	cd $(APP_DIR) && $(PYTHON) -m pytest

compile:
	cd $(APP_DIR) && $(PYTHON) -m compileall -q app localfilesync

check: lint typecheck test compile

ci: check

run-web:
	cd $(APP_DIR) && $(PYTHON) -m localfilesync.web.main

cli-help:
	cd $(APP_DIR) && $(PYTHON) -m localfilesync.cli.main --help

release:
	./scripts/release.sh --help

rollback:
	./scripts/rollback_release.sh --help
