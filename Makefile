.PHONY: help init up down build logs shell test format clean
.PHONY: test-backend test-frontend test-e2e test-all test-docker
.PHONY: test-unit test-integration test-security test-performance
.PHONY: lint lint-backend lint-frontend coverage

# Variables
DOCKER_COMPOSE = docker compose
BACKEND_CONTAINER = backend
FRONTEND_CONTAINER = frontend
DB_CONTAINER = postgres

help: ## Show this help message
	@echo 'Usage: make [target]'
	@echo ''
	@echo 'Available targets:'
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "  %-20s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

init: ## Initialize development environment
	@echo "🚀 Initializing Chrono Scraper Development Environment..."
	@if [ ! -f .env ]; then \
		echo "📝 Creating .env file from .env.example..."; \
		cp .env.example .env; \
		echo "⚠️  Please update .env with your configuration"; \
	fi
	@echo "🔨 Building Docker containers..."
	@$(DOCKER_COMPOSE) build
	@echo "🐳 Starting services..."
	@$(DOCKER_COMPOSE) up -d
	@echo "⏳ Waiting for services to be ready..."
	@sleep 10
	@echo "🔍 Running database migrations..."
	@$(DOCKER_COMPOSE) exec -T $(BACKEND_CONTAINER) alembic upgrade head || true
	@echo "✅ Development environment is ready!"
	@echo ""
	@echo "📚 Access points:"
	@echo "  - Frontend:     http://localhost:5173"
	@echo "  - Backend API:  http://localhost:8000"
	@echo "  - API Docs:     http://localhost:8000/docs"
	@echo "  - Meilisearch:  http://localhost:7700"
	@echo "  - Flower:       http://localhost:5555"
	@echo "  - Mailpit:      http://localhost:8025"

up: ## Start all services
	$(DOCKER_COMPOSE) up

up-d: ## Start all services in detached mode
	$(DOCKER_COMPOSE) up -d
	@echo "✅ Services started in background"
	@echo "Run 'make logs' to view logs"

down: ## Stop all services
	docker compose down

build: ## Build all containers
	docker compose build

rebuild: ## Rebuild all containers
	docker compose build --no-cache

logs: ## View logs for all services
	docker compose logs -f

logs-backend: ## View backend logs
	docker compose logs -f backend

logs-frontend: ## View frontend logs
	docker compose logs -f frontend

shell-backend: ## Open shell in backend container
	docker compose exec backend /bin/bash

shell-frontend: ## Open shell in frontend container
	docker compose exec frontend /bin/sh

shell-db: ## Open PostgreSQL shell
	docker compose exec postgres psql -U chrono_scraper chrono_scraper

# Testing targets
test: test-all ## Run all tests (alias for test-all)

test-all: ## Run complete test suite (unit, integration, e2e)
	@echo "🧪 Running complete test suite..."
	$(MAKE) test-backend
	$(MAKE) test-frontend
	$(MAKE) test-e2e
	@echo "✅ All tests completed!"

test-backend: ## Run backend tests
	@echo "🐍 Running backend tests..."
	docker compose exec backend pytest tests/ -v --cov=app --cov-report=html --cov-report=xml

test-frontend: ## Run frontend tests
	@echo "⚛️ Running frontend tests..."
	docker compose exec frontend npm run test

test-e2e: ## Run end-to-end tests
	@echo "🎭 Running E2E tests..."
	docker compose exec frontend npm run test:e2e

test-unit: ## Run only unit tests
	@echo "🔬 Running unit tests..."
	docker compose exec backend pytest tests/ -m "unit" -v
	docker compose exec frontend npm run test

test-integration: ## Run only integration tests
	@echo "🔗 Running integration tests..."
	docker compose exec backend pytest tests/test_integration/ -v

test-security: ## Run security tests
	@echo "🔒 Running security tests..."
	docker compose exec backend bandit -r app/ -f json -o bandit-report.json
	docker compose exec backend safety check --json --output safety-report.json
	docker compose exec frontend npm audit --audit-level=moderate

test-performance: ## Run performance tests
	@echo "⚡ Running performance tests..."
	docker compose exec backend python -m pytest tests/test_performance/ -v

test-docker: ## Run tests in Docker containers
	@echo "🐳 Running tests in Docker..."
	docker-compose -f docker-compose.test.yml up --build --abort-on-container-exit
	docker-compose -f docker-compose.test.yml down

# Code quality
lint: lint-backend lint-frontend ## Run linting for both backend and frontend

lint-backend: ## Run backend linting
	@echo "🔍 Linting backend code..."
	docker compose exec backend ruff check app/
	docker compose exec backend black --check app/
	docker compose exec backend mypy app/

lint-frontend: ## Run frontend linting
	@echo "🔍 Linting frontend code..."
	docker compose exec frontend npm run lint
	docker compose exec frontend npm run check

coverage: ## Generate coverage reports
	@echo "📊 Generating coverage reports..."
	docker compose exec backend pytest tests/ --cov=app --cov-report=html --cov-report=xml
	docker compose exec frontend npm run test -- --coverage
	@echo "📊 Coverage reports generated:"
	@echo "  Backend: backend/htmlcov/index.html"
	@echo "  Frontend: frontend/coverage/index.html"

format-backend: ## Format backend code
	docker compose exec backend black .
	docker compose exec backend ruff check . --fix

format-frontend: ## Format frontend code
	docker compose exec frontend npm run format

migrate: ## Run database migrations
	docker compose exec backend alembic upgrade head

makemigrations: ## Create new migration (usage: make makemigrations message="description")
	@if [ -z "$(message)" ]; then \
		echo "Error: Please provide a migration message"; \
		echo "Usage: make makemigrations message=\"your message\""; \
		exit 1; \
	fi
	$(DOCKER_COMPOSE) exec $(BACKEND_CONTAINER) alembic revision --autogenerate -m "$(message)"

clean: ## Clean up containers and volumes
	docker compose down -v
	find . -type d -name "__pycache__" -exec rm -r {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete

reset: clean ## Reset everything (containers, volumes, node_modules)
	rm -rf frontend/node_modules
	rm -rf backend/.venv

install-frontend: ## Install frontend dependencies
	cd frontend && npm install

install-backend: ## Install backend dependencies locally
	cd backend && python -m venv .venv && .venv/bin/pip install -r requirements.txt

dev: ## Start development environment
	docker compose up

prod-build: ## Build for production
	docker compose -f docker-compose.prod.yml build

prod-up: ## Start production environment
	docker compose -f docker-compose.prod.yml up -d

monitor: ## Open monitoring dashboards
	@echo "Opening monitoring dashboards..."
	@echo "Flower: http://localhost:5555"
	@echo "Mailpit: http://localhost:8025"
	@echo "Meilisearch: http://localhost:7700"

status: ## Check status of all services
	@echo "📊 Service Status:"
	@$(DOCKER_COMPOSE) ps
	@echo ""
	@echo "🔍 Health Checks:"
	@curl -s http://localhost:8000/health || echo "❌ Backend not responding"
	@curl -s http://localhost:5173 > /dev/null && echo "✅ Frontend running" || echo "❌ Frontend not responding"
	@curl -s http://localhost:7700/health || echo "❌ Meilisearch not responding"

backend-shell: ## Open Python shell in backend container
	$(DOCKER_COMPOSE) exec $(BACKEND_CONTAINER) python

db-shell: ## Open PostgreSQL shell
	$(DOCKER_COMPOSE) exec $(DB_CONTAINER) psql -U chrono_scraper chrono_scraper

redis-cli: ## Open Redis CLI
	$(DOCKER_COMPOSE) exec redis redis-cli

create-superuser: ## Create a superuser account
	$(DOCKER_COMPOSE) exec $(BACKEND_CONTAINER) python -c "from app.core.init_db import run_create_superuser; run_create_superuser()"

seed-db: ## Seed database with sample data
	$(DOCKER_COMPOSE) exec $(BACKEND_CONTAINER) python -c "from app.core.init_db import run_seed_database; run_seed_database()"