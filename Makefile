VENV:=.venv
BIN:=${VENV}/bin

ci: lint test ## Run all CI steps

${VENV}: poetry.toml poetry.lock
	poetry install
	touch .venv

.PHONY: test
test: ${VENV} ## Run tests with coverage
	${BIN}/pytest --cov-report xml --cov=custom_components

.PHONY: tox
tox: ${VENV} ## Run tests on different HA versions
	${BIN}/tox -p

.PHONY: tox-env
tox-env: ${VENV} ## Run tests on specific HA versions
	${BIN}/tox run -e ${HA_VERSION}

.PHONY: lint
lint: lint-ruff lint-mypy ## Run all linters

.PHONY: lint-ruff
lint-ruff: ${VENV} ## Lint with ruff
	${BIN}/ruff check .

.PHONY: lint-mypy
lint-mypy: ${VENV} ## Lint with mypy
	${BIN}/mypy .

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
