VENV:=.venv
BIN:=${VENV}/bin
TOX:=$(shell uv tool dir)/tox/bin/tox

SRC:=$(shell find custom_components/gbb -type f -name "*.py") $(shell find tests -type f -name "*.py")

ci: lint test ## Run all CI steps

${VENV}: pyproject.toml uv.lock
	uv python install
	uv venv --clear .venv
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
lint: lint-ruff lint-ty lint-imports ## Run all linters

.PHONY: lint-ruff
lint-ruff: ${VENV} ## Lint with ruff
	${BIN}/ruff check $(SRC)

.PHONY: lint-ty
lint-ty: ${VENV} ## Lint with ty
	${BIN}/ty check $(SRC)

.PHONY: lint-imports
lint-imports: ## Lint imports
	bash -c 'grep -r --include="*.py" "custom_components" custom_components >/dev/null && exit 1 || exit 0'

.PHONY: h-up
h-up: ## Podman compose reboot and tail logs
	podman compose stop
	podman compose up -d
	podman compose logs -f

.PHONY: h-stop
h-stop: ## Docker compose stop
	podman compose stop

.PHONY: clean
clean: ## Clean up caches and venv
	echo rm -r .venv
	echo rm -r .*_cache

.DEFAULT_GOAL:=help
help: ## Show this help
	@echo "Makefile targets:"
	@awk 'BEGIN {FS = ":.*## "} /^[a-zA-Z0-9_-]+:.*## /{printf "  \033[36m%-13s\033[0m %s\n", $$1, $$2}' ${MAKEFILE_LIST}
