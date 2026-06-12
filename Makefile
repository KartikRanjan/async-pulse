.PHONY: dev test lint clean install help

help: ## Show this help message
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

install: ## Install all dependencies
	pip install -e ".[dev]"

dev: ## Run the FastAPI development server
	uvicorn src.main:app --reload --host 0.0.0.0 --port 8000

test: ## Run tests using pytest
	pytest -v

lint: ## Run linting and type checking
	ruff check .
	mypy .

clean: ## Remove python cache files
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
