VENV:=.venv
BIN:=${VENV}/bin
TOX:=$(shell uv tool dir)/tox/bin/tox

SRC:=$(shell find custom_components/gbb -type f -name "*.py") $(shell find tests -type f -name "*.py")

ci: lint test ## Run all CI steps

${VENV}: pyproject.toml uv.lock
	uv python install
	uv venv .venv
	uv sync --prerelease=allow

.PHONY: test
test: ${VENV} ## Run tests with coverage
	${BIN}/pytest --cov-report xml --cov=custom_components

.PHONY: test
test-filter: ${VENV} ## Run test with filter
	${BIN}/pytest -k ${TEST}

${TOX}: ${VENV}
	uv tool install tox --with tox-uv

.PHONY: tox
tox: ${TOX} ## Run tests on different HA versions
	${TOX} -p

.PHONY: tox-env
tox-env: ${TOX} ## Run tests on specific HA versions
	${TOX} run -e ${HA_VERSION}

.PHONY: lint
lint: lint-ruff lint-mypy lint-imports ## Run all linters

.PHONY: lint-ruff
lint-ruff: ${VENV} ## Lint with ruff
	${BIN}/ruff check $(SRC)

.PHONY: lint-mypy
lint-mypy: ${VENV} ## Lint with mypy
	${BIN}/mypy $(SRC)

.PHONY: lint-imports
lint-imports: ## Lint imports
	bash -c 'grep -r --include="*.py" "custom_components" custom_components >/dev/null && exit 1 || exit 0'

.PHONY: d-up
d-up: ## Docker compose reboot and tail logs
	docker compose stop
	docker compose up -d
	docker compose logs -f

.PHONY: d-stop
d-stop: ## Docker compose stop
	docker compose stop

.PHONY: clean
clean: ## Clean up caches and venv
	echo rm -r .venv
	echo rm -r .*_cache

.DEFAULT_GOAL:=help
help: ## Show this help
	$(eval HELP_COL_WIDTH:=13)
	@echo "Makefile targets:"
	@grep -E '[^\s]+:.*?## .*$$' ${MAKEFILE_LIST} | grep -v grep | envsubst | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-${HELP_COL_WIDTH}s\033[0m %s\n", $$1, $$2}'
