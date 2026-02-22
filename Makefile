APP_DIR ?= app
ROOT_PYTHON ?= $(if $(wildcard ./venv/bin/python),./venv/bin/python,python3)
APP_PYTHON ?= $(if $(wildcard ./venv/bin/python),../venv/bin/python,$(if $(wildcard ./app/venv/bin/python),./venv/bin/python,python3))

.PHONY: install lint format typecheck test compile check ci run-web cli-help release rollback

install:
	$(ROOT_PYTHON) -m pip install -e "./$(APP_DIR)[dev]"

lint:
	cd $(APP_DIR) && $(APP_PYTHON) -m ruff check app localfilesync

format:
	cd $(APP_DIR) && $(APP_PYTHON) -m ruff format app localfilesync

typecheck:
	cd $(APP_DIR) && $(APP_PYTHON) -m mypy app localfilesync

test:
	cd $(APP_DIR) && $(APP_PYTHON) -m pytest

compile:
	cd $(APP_DIR) && $(APP_PYTHON) -m compileall -q app localfilesync

check: lint typecheck test compile

ci: check

run-web:
	cd $(APP_DIR) && $(APP_PYTHON) -m localfilesync.web.main

cli-help:
	cd $(APP_DIR) && $(APP_PYTHON) -m localfilesync.cli.main --help

release:
	./scripts/release.sh --help

rollback:
	./scripts/rollback_release.sh --help
