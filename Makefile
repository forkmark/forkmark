# Forkmark — development & operations commands
# Usage: make <target>

.PHONY: help dev test lint build-frontend docker-up docker-down docker-logs health

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-18s\033[0m %s\n", $$1, $$2}'

# ---------------------------------------------------------------------------
# Development
# ---------------------------------------------------------------------------

dev: ## Start the dev server with auto-reload
	FM_ENV=dev python run.py

test: ## Run the backend test suite
	python -m pytest tests/ -q

lint: ## Run the linter (ruff)
	python -m ruff check .

build-frontend: ## Build the React frontend into frontend/dist
	cd frontend && npm install && npm run build

# ---------------------------------------------------------------------------
# Docker — single-container stack (SQLite, no external services)
# ---------------------------------------------------------------------------

docker-up: ## Start Forkmark in Docker (SQLite, http://localhost:7700)
	docker compose -f docker-compose.simple.yml up --build -d

docker-down: ## Stop the Docker container
	docker compose -f docker-compose.simple.yml down

docker-logs: ## Tail container logs
	docker compose -f docker-compose.simple.yml logs -f

# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

health: ## Check the running server's health
	curl -s http://localhost:7700/api/health
