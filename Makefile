# agent-router: common tasks. Run `make` (or `make help`) to list targets.
# Tools come from .venv (created by `make venv`); uv is used only to create and fill it.

VENV    := .venv
BIN     := $(VENV)/bin
PY      := $(BIN)/python
CLI     := $(BIN)/agent-router
PORT    ?= 8765
# Offline by default. BACKEND=cascade or BACKEND=jev calls TypeSafe Jev (paid, needs a key).
BACKEND ?= local
Q       ?= What is 17% of 2,340 exactly?

.DEFAULT_GOAL := help
.PHONY: help venv install clean test test-model test-live lint format eval calibrate \
        calibrate-cascade run route

help: ## List available targets
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

venv: ## Create the virtual environment (.venv) with uv
	@test -d $(VENV) || uv venv $(VENV) --python 3.11

install: venv ## Install the package with dev dependencies
	uv pip install --python $(PY) -e ".[dev]"

clean: ## Remove caches and build artifacts (keeps .venv and audit logs)
	rm -rf build dist *.egg-info .pytest_cache .ruff_cache
	find . -path ./$(VENV) -prune -o -type d -name __pycache__ -exec rm -rf {} +

test: ## Offline unit tests (no network, no model download)
	$(BIN)/pytest -q

test-model: ## Tests that load model2vec potion-base-8M (downloads once)
	$(BIN)/pytest -q -m model

test-live: ## Live tests: real Claude session + paid Jev/OpenRouter calls
	$(BIN)/pytest -q -m live -s

lint: ## Ruff lint and format check
	$(BIN)/ruff check src tests
	$(BIN)/ruff format --check src tests

format: ## Format and autofix with ruff
	$(BIN)/ruff format src tests
	$(BIN)/ruff check --fix src tests

eval: ## Score a backend on the holdout split (BACKEND=local by default)
	$(CLI) eval --backend $(BACKEND)

calibrate: ## Re-fit local decider params on the cal split (rewrites calibration.json)
	$(CLI) calibrate

calibrate-cascade: ## Re-fit the cascade gate (PAID: one Jev call per cal case)
	$(CLI) calibrate-cascade

run: ## Start the demo server on http://127.0.0.1:$(PORT)
	$(CLI) demo --port $(PORT)

route: ## Route one prompt: make route Q="..." [BACKEND=cascade]
	$(CLI) route --backend $(BACKEND) "$(Q)"
