# Makefile for matric-eval development tasks

.PHONY: help test test-unit test-integration test-coverage test-fast lint format install clean type-check type-check-strict type-check-update format-check test-coverage-fail operational-validation ci release-workflow-required publish-pypi publish-npm publish release

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
	uv run ruff check src/ tests/ scripts/

lint-fix:  ## Fix linting issues automatically
	uv run ruff check --fix src/ tests/ scripts/

format:  ## Format code with ruff
	uv run ruff format src/ tests/ scripts/

format-check:  ## Check code formatting
	uv run ruff format --check src/ tests/ scripts/

type-check:  ## Run type checking with mypy
	uv run python scripts/check_mypy_baseline.py

type-check-strict:  ## Show every strict mypy finding
	uv run mypy src/

type-check-update:  ## Reduce the mypy baseline to current reviewed findings
	uv run python scripts/check_mypy_baseline.py --update

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

operational-validation:  ## Generate scorer parity and operational evidence
	uv run python scripts/run_operational_validation.py

ci: lint format-check type-check test-coverage-fail  ## Run all authoritative CI gates

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

release-workflow-required:
	@echo "Direct publication is disabled. Dispatch .gitea/workflows/release.yml for a candidate, then publish the validated v* tag."
	@false

publish-pypi: release-workflow-required  ## Disabled; publish through the validated release workflow

publish-npm: release-workflow-required  ## Disabled; publish through the validated release workflow

publish: release-workflow-required  ## Disabled; publish through the validated release workflow

release: release-workflow-required  ## Disabled; release through the validated release workflow
