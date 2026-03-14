all: commands

## commands: show available commands
commands:
	@grep -h -E '^##' ${MAKEFILE_LIST} \
	| sed -e 's/## //g' \
	| column -t -s ':'

## run: run game
run:
	uv run python -m src.defense.main

## package: build package
package:
	@python -m build

## check: check Python code issues
check:
	@ruff check .

## clean: clean up
clean:
	@find . -path './.venv' -prune -o -type d -name '__pycache__' -exec rm -rf {} +
	@find . -path './.venv' -prune -o -type f -name '*~' -exec rm {} +

## fix: fix formatting and code issues
fix:
	@ruff format .
	@ruff check --fix .

## publish: publish using ~/.pypirc credentials
publish:
	twine upload --verbose dist/*

## test: run Python tests
test:
	@pytest tests
