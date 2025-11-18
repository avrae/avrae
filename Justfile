set shell := ["bash", "-euo", "pipefail", "-c"]

help:
	@just --list

# Sync base runtime dependencies into .venv
[group('deps')]
sync:
	uv sync --group test --group lint --group docs

# Sync dependencies needed for running tests
[group('deps')]
sync-test:
	uv sync --group test

# Sync dependencies needed for linting/formatting
[group('deps')]
sync-lint:
	uv sync --group lint

# Sync dependencies needed for documentation builds
[group('deps')]
sync-docs:
	uv sync --group docs

# Run pytest locally using the test dependency group
[group('test')]
run-tests: sync-test
	TESTING=1 uv run pytest tests/

# Run the Docker Compose-based CI tests
[group('test')]
docker-tests:
	docker compose -f docker-compose.ci.yml -p avrae up -d --build
	docker logs -f avrae-tests-1

# Run ruff format + flake8 against the repo
[group('lint')]
lint: sync-lint
	uv run ruff format --check .
	git diff -u origin/master HEAD | uv run flake8 . --count --select=E9,F63,F7,F82 --show-source --statistics --diff
	git diff -u origin/master HEAD | uv run flake8 . --count --exit-zero --max-line-length=120 --statistics --diff

# Build HTML docs via Sphinx
[group('docs')]
docs-html: sync-docs
	cd docs && uv run make html && cd ..

# Open the docs preview (macOS `open`)
[group('docs')]
docs-preview: sync-docs
	cd docs && uv run make preview && cd ..

# Run the bot via docker compose for local development
[group('run')]
run-bot:
	docker compose up --build

# Run the bot locally without Docker
[group('run')]
run-bot-local: sync
	uv run python dbot.py
