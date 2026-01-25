# Makefile for matric-eval development tasks

.PHONY: help test test-unit test-integration test-coverage test-fast lint format install clean

help:  ## Show this help message
	@echo "matric-eval development commands:"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

install:  ## Install dependencies (dev mode)
	uv sync --extra dev

test:  ## Run all tests
	uv run pytest

test-unit:  ## Run unit tests only (fast)
	uv run pytest -m unit -v

test-integration:  ## Run integration tests (requires Ollama)
	uv run pytest -m integration -v

test-fast:  ## Run tests excluding slow tests
	uv run pytest -m "not slow" -v

test-coverage:  ## Run tests with coverage report
	uv run pytest --cov=matric_eval --cov-report=term-missing --cov-report=html
	@echo ""
	@echo "HTML coverage report: htmlcov/index.html"

test-coverage-fail:  ## Run tests with coverage, fail if below 80%
	uv run pytest --cov=matric_eval --cov-report=term-missing --cov-fail-under=80

lint:  ## Run code linters
	uv run ruff check src/ tests/

lint-fix:  ## Fix linting issues automatically
	uv run ruff check --fix src/ tests/

format:  ## Format code with ruff
	uv run ruff format src/ tests/

format-check:  ## Check code formatting
	uv run ruff format --check src/ tests/

type-check:  ## Run type checking with mypy
	uv run mypy src/

clean:  ## Clean up generated files
	rm -rf .pytest_cache
	rm -rf htmlcov
	rm -rf .coverage
	rm -rf .ruff_cache
	rm -rf dist
	rm -rf build
	rm -rf *.egg-info
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true

test-verbose:  ## Run tests with verbose output
	uv run pytest -vv -s

test-debug:  ## Run tests with debugging (stop on first failure, show locals)
	uv run pytest -x -l -vv

test-specific:  ## Run specific test (usage: make test-specific TEST=tests/test_config.py)
	uv run pytest $(TEST) -v

smoke:  ## Run smoke tests
	uv run pytest -m smoke -v

ci:  ## Run CI test suite (lint + type-check + tests + coverage)
	uv run ruff check src/ tests/
	uv run ruff format --check src/ tests/
	uv run mypy src/
	uv run pytest --cov=matric_eval --cov-fail-under=80

dev:  ## Set up development environment
	uv sync --extra dev
	@echo ""
	@echo "Development environment ready!"
	@echo "Run 'make test' to run tests"

build:  ## Build Python package
	uv build
	@echo "Package built in dist/"

build-ts:  ## Build TypeScript bindings
	cd bindings/typescript && npm run build
	@echo "TypeScript bindings built"

publish-pypi:  ## Publish to Gitea PyPI (requires GITEA_TOKEN env var)
	@if [ -z "$$GITEA_TOKEN" ]; then echo "Error: GITEA_TOKEN not set. Get token from Gitea Settings > Applications"; exit 1; fi
	uv publish --publish-url https://git.integrolabs.net/api/packages/roctinam/pypi/ \
		--username roctinam --password "$$GITEA_TOKEN"

publish-npm:  ## Publish TypeScript to Gitea npm (requires GITEA_TOKEN env var)
	@if [ -z "$$GITEA_TOKEN" ]; then echo "Error: GITEA_TOKEN not set. Get token from Gitea Settings > Applications"; exit 1; fi
	cd bindings/typescript && \
		npm config set //git.integrolabs.net/api/packages/roctinam/npm/:_authToken="$$GITEA_TOKEN" && \
		npm publish

publish:  ## Publish both Python and TypeScript packages
	@echo "Publishing packages to Gitea..."
	$(MAKE) publish-pypi
	$(MAKE) publish-npm
	@echo ""
	@echo "Packages published successfully!"

release:  ## Full release process (build + publish)
	$(MAKE) build
	$(MAKE) build-ts
	$(MAKE) publish
