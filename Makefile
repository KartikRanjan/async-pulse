.PHONY: install install-dev lint format typecheck test test-cov run clean help

help: ## Show this help message
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-18s\033[0m %s\n", $$1, $$2}'

install: ## Install production dependencies
	pip install -e .

install-dev: ## Install all dependencies (dev + test + lint)
	pip install -e ".[dev,test,lint]"

format: ## Format code with ruff
	ruff format src/ tests/
	ruff check --fix src/ tests/

lint: ## Lint with ruff (check-only)
	ruff check src/ tests/

typecheck: ## Type-check with mypy
	mypy src/

test: ## Run tests with pytest
	pytest tests/ -v --tb=short

test-cov: ## Run tests with coverage report
	pytest tests/ -v --tb=short --cov=src --cov-report=term-missing

run: ## Run the application (dev mode)
	uvicorn src.main:app --host 0.0.0.0 --port 8000 --reload

clean: ## Remove build artifacts and caches
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	rm -rf dist/ build/ .pytest_cache/ .mypy_cache/ .ruff_cache/ htmlcov/ .coverage
