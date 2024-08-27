VENV:=.venv
BIN:=${VENV}/bin

ci: lint test

${VENV}: poetry.toml poetry.lock
	poetry install
	touch .venv

.PHONY: test
test: ${VENV}
	${BIN}/pytest

.PHONY: lint
lint: lint-ruff lint-mypy

.PHONY: lint-ruff
lint-ruff: ${VENV}
	${BIN}/ruff check .

.PHONY: lint-mypy
lint-mypy: ${VENV}
	${BIN}/mypy .

.PHONY: d-up
d-up:
	docker compose stop
	docker compose up -d
	docker compose logs -f

.PHONY: d-stop
d-stop:
	docker compose stop

.PHONY: clean
clean:
	echo rm -r .venv
	echo rm -r .*_cache
