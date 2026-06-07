# Forkmark — development & operations commands
# Usage: make <target>

.PHONY: help dev test migrate migrate-workspace lint docker-up docker-down

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

# ---------------------------------------------------------------------------
# Development
# ---------------------------------------------------------------------------

dev: ## Start local development server
	python run.py

test: ## Run test suite
	python -m pytest tests/ -q

lint: ## Run linter
	python -m ruff check .

# ---------------------------------------------------------------------------
# Database migrations (Alembic)
# ---------------------------------------------------------------------------

migrate: ## Run control plane migrations (public schema)
	cd migrations && alembic upgrade head

migrate-workspace: ## Run workspace schema migration (usage: make migrate-workspace SCHEMA=workspace_xxx)
	cd migrations && alembic -x schema=$(SCHEMA) upgrade head

migrate-down: ## Rollback last migration
	cd migrations && alembic downgrade -1

migrate-new: ## Create new migration (usage: make migrate-new MSG="add_foo_table")
	cd migrations && alembic revision -m "$(MSG)"

migrate-status: ## Show migration status
	cd migrations && alembic current

# ---------------------------------------------------------------------------
# Docker (local multi-service)
# ---------------------------------------------------------------------------

docker-up: ## Start all services (PostgreSQL, Redis, PgBouncer, API, Workers)
	docker compose up -d

docker-down: ## Stop all services
	docker compose down

docker-logs: ## Tail logs from all services
	docker compose logs -f

docker-rebuild: ## Rebuild and restart
	docker compose up -d --build

# ---------------------------------------------------------------------------
# Production operations
# ---------------------------------------------------------------------------

k8s-apply: ## Apply Kubernetes manifests
	kubectl apply -f k8s/namespace.yaml
	kubectl apply -f k8s/configmap.yaml
	kubectl apply -f k8s/api-deployment.yaml
	kubectl apply -f k8s/worker-deployment.yaml
	kubectl apply -f k8s/ingress.yaml

k8s-status: ## Show deployment status
	kubectl -n forkmark get pods,svc,hpa

health: ## Check API health
	curl -s http://localhost:8000/healthz | python -m json.tool
	curl -s http://localhost:8000/readyz | python -m json.tool
