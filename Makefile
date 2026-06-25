.PHONY: install install-dev lint format typecheck test test-cov run clean help migrate migrate-gen migrate-up migrate-down migrate-history migrate-current hooks-install hooks-run

VENV := .venv/bin

help: ## Show this help message
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-18s\033[0m %s\n", $$1, $$2}'

install: ## Install production dependencies
	$(VENV)/pip install -e .

install-dev: ## Install all dependencies (dev + test + lint)
	$(VENV)/pip install -e ".[dev,test,lint]"

format: ## Format code with ruff
	$(VENV)/ruff format src/ tests/
	$(VENV)/ruff check --fix src/ tests/

lint: ## Lint with ruff (check-only)
	$(VENV)/ruff check src/ tests/

typecheck: ## Type-check with pyright
	$(VENV)/pyright src/

hooks-install: ## Install pre-commit and pre-push git hooks
	$(VENV)/pre-commit install --install-hooks
	$(VENV)/pre-commit install --hook-type pre-push

hooks-run: ## Run all pre-commit hooks against every file
	$(VENV)/pre-commit run --all-files

test: ## Run tests with pytest
	$(VENV)/pytest tests/ -v --tb=short

test-cov: ## Run tests with coverage report
	$(VENV)/pytest tests/ -v --tb=short --cov=src --cov-report=term-missing

run: ## Run the application (dev mode)
	$(VENV)/uvicorn src.main:app --host 0.0.0.0 --port 8000 --reload

clean: ## Remove build artifacts and caches
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	rm -rf dist/ build/ .pytest_cache/ .pyright_cache/ .ruff_cache/ .mypy_cache/ htmlcov/ .coverage

migrate-gen: ## Generate a new migration (usage: make migrate-gen m="description")
	$(VENV)/alembic revision --autogenerate -m "$(m)"

migrate-up: ## Apply all pending migrations
	$(VENV)/alembic upgrade head

migrate-down: ## Rollback last migration
	$(VENV)/alembic downgrade -1

migrate-history: ## Show migration history
	$(VENV)/alembic history --verbose

migrate-current: ## Show current migration revision
	$(VENV)/alembic current
