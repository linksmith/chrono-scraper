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

# =============================================================================
# SCALING AND COST OPTIMIZATION COMMANDS
# =============================================================================

# Scaling analysis and decision tools
scaling-analyze: ## Analyze current metrics and recommend scaling actions
	@echo "🔍 Analyzing scaling needs..."
	@python3 scripts/scaling/scaling_decision.py --current-phase=1
	
scaling-analyze-json: ## Analyze scaling needs and output JSON
	@python3 scripts/scaling/scaling_decision.py --current-phase=1 --format=json
	
scaling-report: ## Generate comprehensive scaling analysis report
	@python3 scripts/scaling/scaling_decision.py --current-phase=1 --output=scaling_report.txt
	@echo "📋 Scaling report saved to scaling_report.txt"
	
cost-optimize: ## Analyze cost optimization opportunities
	@echo "💰 Analyzing cost optimization opportunities..."
	@python3 scripts/scaling/cost_optimizer.py
	
cost-optimize-report: ## Generate cost optimization report
	@python3 scripts/scaling/cost_optimizer.py --output=cost_optimization_report.txt
	@echo "💰 Cost optimization report saved to cost_optimization_report.txt"
	
# Scaling dashboard
scaling-dashboard: ## Start real-time scaling dashboard
	@echo "🚀 Starting scaling dashboard on http://localhost:8080"
	@python3 scripts/monitoring/scaling_dashboard.py --host=0.0.0.0 --port=8080 --current-phase=1
	
scaling-dashboard-bg: ## Start scaling dashboard in background
	@echo "🚀 Starting scaling dashboard in background..."
	@nohup python3 scripts/monitoring/scaling_dashboard.py --host=0.0.0.0 --port=8080 --current-phase=1 > scaling_dashboard.log 2>&1 &
	@echo "📊 Dashboard available at http://localhost:8080"
	@echo "📝 Logs: tail -f scaling_dashboard.log"
	
# Phase migration tools
migrate-phase-1-to-2: ## Migrate from Phase 1 to Phase 2 (dry run first)
	@echo "🚀 Planning migration from Phase 1 to Phase 2..."
	@chmod +x scripts/scaling/migrate_phase.sh
	@./scripts/scaling/migrate_phase.sh --from 1 --to 2 --dry-run
	@echo ""
	@echo "⚠️  Review the dry run output above"
	@read -p "Proceed with actual migration? [y/N] " -n 1 -r; \
	if [[ $$REPLY =~ ^[Yy]$$ ]]; then \
		echo ""; \
		./scripts/scaling/migrate_phase.sh --from 1 --to 2; \
	else \
		echo ""; \
		echo "Migration cancelled"; \
	fi
	
migrate-phase-2-to-3: ## Migrate from Phase 2 to Phase 3 (dry run first)
	@echo "🚀 Planning migration from Phase 2 to Phase 3..."
	@chmod +x scripts/scaling/migrate_phase.sh
	@./scripts/scaling/migrate_phase.sh --from 2 --to 3 --dry-run
	@echo ""
	@echo "⚠️  Review the dry run output above"
	@read -p "Proceed with actual migration? [y/N] " -n 1 -r; \
	if [[ $$REPLY =~ ^[Yy]$$ ]]; then \
		echo ""; \
		./scripts/scaling/migrate_phase.sh --from 2 --to 3; \
	else \
		echo ""; \
		echo "Migration cancelled"; \
	fi
	
# Production deployment
deploy-phase1: ## Deploy to Phase 1 production (single server)
	@echo "🚀 Deploying to Phase 1 production..."
	@chmod +x scripts/deploy/phase1_single_server.sh
	@if [ -z "$(DOMAIN)" ]; then \
		echo "❌ DOMAIN environment variable required"; \
		echo "Usage: make deploy-phase1 DOMAIN=your-domain.com"; \
		exit 1; \
	fi
	@./scripts/deploy/phase1_single_server.sh --domain=$(DOMAIN) --email=$(EMAIL)
	
deploy-phase1-dry-run: ## Dry run Phase 1 deployment
	@echo "🔍 Dry run Phase 1 deployment..."
	@chmod +x scripts/deploy/phase1_single_server.sh
	@if [ -z "$(DOMAIN)" ]; then \
		echo "❌ DOMAIN environment variable required"; \
		echo "Usage: make deploy-phase1-dry-run DOMAIN=your-domain.com"; \
		exit 1; \
	fi
	@./scripts/deploy/phase1_single_server.sh --domain=$(DOMAIN) --email=$(EMAIL) --dry-run
	
# Backup and recovery for scaling
backup-pre-scaling: ## Create backup before scaling operations
	@echo "📦 Creating pre-scaling backup..."
	@mkdir -p backups/$(shell date +%Y%m%d_%H%M%S)_pre_scaling
	@docker compose exec postgres pg_dump -U chrono_scraper chrono_scraper > backups/$(shell date +%Y%m%d_%H%M%S)_pre_scaling/database.sql
	@docker compose exec redis redis-cli --rdb backups/$(shell date +%Y%m%d_%H%M%S)_pre_scaling/redis.rdb
	@cp .env backups/$(shell date +%Y%m%d_%H%M%S)_pre_scaling/
	@echo "✅ Backup created in backups/$(shell date +%Y%m%d_%H%M%S)_pre_scaling/"
	
backup-restore: ## Restore from backup (specify BACKUP_DIR)
	@if [ -z "$(BACKUP_DIR)" ]; then \
		echo "❌ BACKUP_DIR required"; \
		echo "Usage: make backup-restore BACKUP_DIR=backups/20241127_143022_pre_scaling"; \
		exit 1; \
	fi
	@echo "🔄 Restoring from backup: $(BACKUP_DIR)"
	@docker compose down
	@docker compose up -d postgres
	@sleep 10
	@docker compose exec -T postgres psql -U chrono_scraper chrono_scraper < $(BACKUP_DIR)/database.sql
	@docker compose exec redis redis-cli FLUSHALL
	@docker cp $(BACKUP_DIR)/redis.rdb $$(docker ps --format "table {{.Names}}" | grep redis | head -n1):/data/dump.rdb
	@cp $(BACKUP_DIR)/.env .env.restored
	@docker compose up -d
	@echo "✅ Backup restored successfully"

# Scaling metrics and monitoring
scaling-metrics: ## Show current scaling metrics
	@echo "📊 Current Scaling Metrics:"
	@echo ""
	@echo "💾 Memory Usage:"
	@docker stats --no-stream --format "table {{.Container}}\t{{.MemUsage}}\t{{.MemPerc}}" | grep chrono
	@echo ""
	@echo "🏗️ CPU Usage:"
	@docker stats --no-stream --format "table {{.Container}}\t{{.CPUPerc}}" | grep chrono
	@echo ""
	@echo "💽 Database Size:"
	@docker compose exec postgres psql -U chrono_scraper -d chrono_scraper -c "SELECT pg_size_pretty(pg_database_size('chrono_scraper'));"
	@echo ""
	@echo "👥 Active Users (30 days):"
	@docker compose exec postgres psql -U chrono_scraper -d chrono_scraper -c "SELECT COUNT(*) FROM users WHERE last_login > NOW() - INTERVAL '30 days' AND is_active = true;"
	@echo ""
	@echo "📈 Queue Length:"
	@docker compose exec redis redis-cli llen celery
	
scaling-thresholds: ## Show scaling trigger thresholds
	@echo "🎯 Scaling Trigger Thresholds:"
	@echo ""
	@echo "Phase 1 → 2 Triggers:"
	@echo "  - CPU Usage: >70% (7-day avg)"
	@echo "  - Memory Usage: >75%"
	@echo "  - Active Users: >100"
	@echo "  - Database Size: >20GB"
	@echo "  - Monthly Revenue: >€500"
	@echo ""
	@echo "Phase 2 → 3 Triggers:"
	@echo "  - CPU Usage: >75% (7-day avg)"
	@echo "  - Memory Usage: >85%"
	@echo "  - Active Users: >500"
	@echo "  - Database Size: >50GB"
	@echo "  - Monthly Revenue: >€2000"
	@echo ""
	@echo "📊 Run 'make scaling-analyze' for detailed analysis"

# Cost tracking
cost-current: ## Show current estimated monthly costs
	@echo "💰 Current Estimated Monthly Costs:"
	@echo ""
	@echo "Infrastructure (Phase 1):"
	@echo "  - Hetzner CX32: €25.85/month"
	@echo "  - Storage: €4.00/month (estimated)"
	@echo "  - Backup: €2.00/month (estimated)"
	@echo "  - Total: €31.85/month"
	@echo ""
	@echo "📊 Run 'make cost-optimize' for detailed cost analysis"
	
cost-projection: ## Show cost projections for all phases
	@echo "💰 Cost Projections by Phase:"
	@echo ""
	@echo "Phase 1 (Single Server): €25.85/month"
	@echo "  - Users: 0-100"
	@echo "  - Cost per user: €0.26-∞"
	@echo ""
	@echo "Phase 2 (Service Separation): €31.90/month"
	@echo "  - Users: 100-500"
	@echo "  - Cost per user: €0.06-0.32"
	@echo ""
	@echo "Phase 3 (Horizontal Scaling): €65.35/month"
	@echo "  - Users: 500-2000"
	@echo "  - Cost per user: €0.03-0.13"
	@echo ""
	@echo "Phase 4 (Multi-Region): €150-200/month"
	@echo "  - Users: 2000-10000"
	@echo "  - Cost per user: €0.02-0.10"
	@echo ""
	@echo "Phase 5 (Enterprise K8s): €200+/month"
	@echo "  - Users: 10000+"
	@echo "  - Cost per user: €0.02-0.05"

# Validation and testing
validate-scaling-tools: ## Validate that all scaling tools are properly configured
	@echo "🧪 Validating scaling tools configuration..."
	@chmod +x scripts/scaling/validate_scaling_tools.sh
	@./scripts/scaling/validate_scaling_tools.sh

# =============================================================================
# RESOURCE OPTIMIZATION COMMANDS
# =============================================================================

up-optimized: ## Start services with optimized resource allocation
	docker compose -f docker-compose.optimized.yml up -d
	@echo "✅ Services started with optimized resource allocation"
	@echo "📊 Run 'make monitor' to track resource usage"

down-optimized: ## Stop optimized services
	docker compose -f docker-compose.optimized.yml down

restart-optimized: ## Restart with optimized configuration
	$(MAKE) down-optimized
	$(MAKE) up-optimized

build-optimized: ## Build containers for optimized deployment
	docker compose -f docker-compose.optimized.yml build

monitor: ## Monitor container resource usage
	@if [ -f scripts/monitor-resources.sh ]; then \
		./scripts/monitor-resources.sh; \
	else \
		echo "❌ Monitoring script not found. Run from project root."; \
	fi

monitor-continuous: ## Start continuous resource monitoring
	@if [ -f scripts/monitor-resources.sh ]; then \
		./scripts/monitor-resources.sh continuous; \
	else \
		echo "❌ Monitoring script not found. Run from project root."; \
	fi

resource-cleanup: ## Clean up Docker resources to free memory
	@echo "🧹 Cleaning up Docker resources..."
	docker system prune -f
	docker volume prune -f
	docker image prune -f
	@echo "✅ Cleanup completed"

resource-stats: ## Show detailed resource statistics
	@echo "📊 Docker Resource Statistics:"
	@echo ""
	@echo "🐳 Container Resource Usage:"
	@docker stats --no-stream --format "table {{.Container}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.MemPerc}}\t{{.NetIO}}\t{{.BlockIO}}"
	@echo ""
	@echo "💾 Volume Usage:"
	@docker system df
	@echo ""
	@echo "🖥️  System Resource Usage:"
	@free -h
	@echo ""
	@uptime

performance-test: ## Run performance tests against the application
	@echo "⚡ Running performance tests..."
	@echo "Testing Backend API..."
	@if command -v ab >/dev/null 2>&1; then \
		ab -n 100 -c 5 http://localhost:8000/health; \
	else \
		echo "Apache Bench (ab) not found. Install with: sudo apt-get install apache2-utils"; \
	fi
	@echo ""
	@echo "Testing Database Connection..."
	@$(DOCKER_COMPOSE) exec postgres psql -U chrono_scraper -d chrono_scraper -c "SELECT COUNT(*) FROM users;"

memory-check: ## Check for memory leaks in services
	@echo "🔍 Checking for memory leaks..."
	@echo ""
	@echo "Celery Worker Memory Usage:"
	@docker stats chrono_celery_worker --no-stream --format "{{.MemUsage}} ({{.MemPerc}})"
	@echo ""
	@echo "Backend Memory Usage:"
	@docker stats chrono_backend --no-stream --format "{{.MemUsage}} ({{.MemPerc}})"
	@echo ""
	@echo "Firecrawl Playwright Memory Usage:"
	@docker stats chrono_firecrawl_playwright --no-stream --format "{{.MemUsage}} ({{.MemPerc}})"

db-optimize: ## Optimize database performance
	@echo "🔧 Optimizing database performance..."
	@$(DOCKER_COMPOSE) exec postgres psql -U chrono_scraper -d chrono_scraper -c "VACUUM ANALYZE;"
	@$(DOCKER_COMPOSE) exec postgres psql -U chrono_scraper -d chrono_scraper -c "REINDEX DATABASE chrono_scraper;"
	@echo "✅ Database optimization completed"

cache-stats: ## Show Redis cache statistics
	@echo "📈 Redis Cache Statistics:"
	@$(DOCKER_COMPOSE) exec redis redis-cli INFO memory
	@echo ""
	@echo "Cache Hit Rate:"
	@$(DOCKER_COMPOSE) exec redis redis-cli INFO stats | grep keyspace

scale-workers: ## Scale Celery workers (usage: make scale-workers count=3)
	@if [ -z "$(count)" ]; then \
		echo "Error: Please specify worker count"; \
		echo "Usage: make scale-workers count=3"; \
		exit 1; \
	fi
	docker compose up -d --scale celery_worker=$(count)
	@echo "✅ Scaled Celery workers to $(count) instances"

health-check-all: ## Run comprehensive health checks
	@echo "🏥 Running comprehensive health checks..."
	@echo ""
	@echo "Service Status:"
	@$(DOCKER_COMPOSE) ps
	@echo ""
	@echo "Health Endpoints:"
	@curl -s http://localhost:8000/health && echo " ✅ Backend API" || echo " ❌ Backend API"
	@curl -s http://localhost:7700/health > /dev/null && echo " ✅ Meilisearch" || echo " ❌ Meilisearch"
	@curl -s http://localhost:3002/v0/health/liveness > /dev/null && echo " ✅ Firecrawl API" || echo " ❌ Firecrawl API"
	@curl -s http://localhost:3000/health > /dev/null && echo " ✅ Firecrawl Playwright" || echo " ❌ Firecrawl Playwright"
	@curl -s http://localhost:5173 > /dev/null && echo " ✅ Frontend" || echo " ❌ Frontend"

benchmark: ## Run comprehensive benchmark tests
	@echo "🚀 Running benchmark tests..."
	@echo ""
	@echo "1. Database Query Performance:"
	@time $(DOCKER_COMPOSE) exec postgres psql -U chrono_scraper -d chrono_scraper -c "SELECT COUNT(*) FROM users;"
	@echo ""
	@echo "2. Cache Performance:"
	@time $(DOCKER_COMPOSE) exec redis redis-cli PING
	@echo ""
	@echo "3. API Response Time:"
	@time curl -s http://localhost:8000/health
	@echo ""
	@echo "4. Search Performance:"
	@time curl -s "http://localhost:7700/indexes/pages/search?q=test"

optimize-start: ## Start services with optimized resource allocation
	@echo "🚀 Starting services with optimized configuration..."
	@$(DOCKER_COMPOSE) -f docker-compose.yml -f docker-compose.optimized.yml up -d
	@echo "✅ Optimized services started"

optimize-restart: ## Restart services with optimized configuration
	@echo "🔄 Restarting services with optimized configuration..."
	@$(DOCKER_COMPOSE) down
	@$(DOCKER_COMPOSE) -f docker-compose.yml -f docker-compose.optimized.yml up -d
	@echo "✅ Services restarted with optimizations"

monitor: ## Start resource monitoring
	@echo "📊 Starting resource monitoring..."
	@chmod +x scripts/monitor-resources.sh
	@./scripts/monitor-resources.sh --continuous

monitor-once: ## Run single resource monitoring check
	@echo "📊 Running single monitoring check..."
	@chmod +x scripts/monitor-resources.sh
	@./scripts/monitor-resources.sh

performance-test: ## Run performance tests
	@echo "🧪 Running performance tests..."
	@chmod +x scripts/performance-test.sh
	@./scripts/performance-test.sh

performance-test-load: ## Run performance tests with load testing
	@echo "🧪 Running performance tests with load testing..."
	@chmod +x scripts/performance-test.sh
	@./scripts/performance-test.sh --load-test --concurrent=20 --duration=60

apply-optimizations: ## Apply all performance optimizations
	@echo "⚡ Applying performance optimizations..."
	@echo "1. Database indexes..."
	@$(DOCKER_COMPOSE) exec backend alembic upgrade head
	@echo "2. Restarting with optimized configuration..."
	@$(DOCKER_COMPOSE) down
	@$(DOCKER_COMPOSE) -f docker-compose.optimized.yml up -d
	@echo "3. Waiting for services..."
	@sleep 15
	@echo "4. Running validation..."
	@./scripts/performance-test.sh
	@echo "✅ All optimizations applied successfully!"

# =============================================================================
# INTELLIGENT EXTRACTION OPTIMIZATION COMMANDS
# =============================================================================

up-intelligent: ## Start services with intelligent extraction optimization
	@echo "🧠 Starting services with intelligent extraction optimization..."
	@$(DOCKER_COMPOSE) -f docker-compose.optimized.yml up -d
	@echo "✅ Intelligent extraction system started"
	@echo ""
	@echo "📊 Monitor performance with:"
	@echo "  make monitor-intelligent"
	@echo "  make test-intelligent-performance"

down-intelligent: ## Stop intelligent extraction services
	@$(DOCKER_COMPOSE) -f docker-compose.optimized.yml down

restart-intelligent: ## Restart with intelligent extraction optimization
	$(MAKE) down-intelligent
	$(MAKE) up-intelligent

monitor-intelligent: ## Start intelligent extraction performance monitoring
	@echo "📊 Starting intelligent extraction monitoring..."
	@chmod +x scripts/monitor-intelligent-extraction.sh
	@./scripts/monitor-intelligent-extraction.sh true 5

monitor-intelligent-once: ## Single intelligent extraction monitoring check
	@echo "📊 Running single intelligent extraction monitoring check..."
	@chmod +x scripts/monitor-intelligent-extraction.sh
	@./scripts/monitor-intelligent-extraction.sh

test-intelligent-performance: ## Run intelligent extraction performance test
	@echo "🧪 Running intelligent extraction performance test..."
	@chmod +x scripts/test-intelligent-extraction-performance.sh
	@./scripts/test-intelligent-extraction-performance.sh

test-intelligent-performance-high: ## Run high-load intelligent extraction performance test
	@echo "🧪 Running high-load intelligent extraction performance test..."
	@chmod +x scripts/test-intelligent-extraction-performance.sh
	@./scripts/test-intelligent-extraction-performance.sh 25 600 75

validate-intelligent-extraction: ## Validate intelligent extraction system setup
	@echo "✅ Validating intelligent extraction system..."
	@echo ""
	@echo "1. Checking service health..."
	@$(MAKE) status
	@echo ""
	@echo "2. Checking resource allocation..."
	@$(MAKE) resource-stats
	@echo ""
	@echo "3. Running performance test..."
	@$(MAKE) test-intelligent-performance
	@echo ""
	@echo "🎯 Intelligent extraction validation complete!"

intelligent-extraction-info: ## Show intelligent extraction system information
	@echo "🧠 Intelligent Content Extraction System"
	@echo "========================================"
	@echo ""
	@echo "📋 System Configuration:"
	@echo "  - Memory Allocation: 9.638GB (freed 6.5GB from Firecrawl)"
	@echo "  - CPU Allocation: 12.75 cores"
	@echo "  - Target Throughput: 50+ pages/second"
	@echo "  - Concurrent Extractions: 10-25"
	@echo "  - Archive.org Rate Limit: 15 requests/minute"
	@echo ""
	@echo "🔧 Resource Distribution:"
	@echo "  - Celery Worker: 3.0GB RAM, 2.5 CPU cores (primary extraction)"
	@echo "  - PostgreSQL: 2.0GB RAM, 1.5 CPU cores (content storage)"
	@echo "  - Meilisearch: 1.5GB RAM, 1.5 CPU cores (content indexing)"
	@echo "  - Backend API: 1.5GB RAM, 2.0 CPU cores (extraction coordination)"
	@echo "  - Redis Cache: 1.0GB RAM, 0.75 CPU cores (extraction caching)"
	@echo ""
	@echo "🎯 Performance Targets:"
	@echo "  - Throughput: 50+ pages/second sustained"
	@echo "  - Response Time: <45 seconds per extraction"
	@echo "  - Success Rate: >90%"
	@echo "  - Memory Efficiency: Recycling every 30 tasks"
	@echo ""
	@echo "📊 Commands:"
	@echo "  make up-intelligent          - Start optimized system"
	@echo "  make monitor-intelligent     - Monitor performance"
	@echo "  make test-intelligent-performance - Run performance tests"
	@echo "  make validate-intelligent-extraction - Full validation"
	@echo ""
	@echo "📚 Documentation: INTELLIGENT_EXTRACTION_OPTIMIZATION.md"

extraction-metrics: ## Show current extraction performance metrics
	@echo "📈 Current Extraction Performance Metrics:"
	@echo ""
	@echo "🔄 Active Extractions:"
	@docker compose exec -T celery_worker celery -A app.tasks.celery_app inspect active | grep -c '"name":' || echo "0"
	@echo ""
	@echo "📊 Queue Status:"
	@echo "  Celery Queue Length: $$(docker compose exec -T redis redis-cli llen celery 2>/dev/null || echo '0')"
	@echo "  Redis Memory Usage: $$(docker compose exec -T redis redis-cli info memory | grep used_memory_human | cut -d':' -f2 | tr -d '\r')"
	@echo ""
	@echo "💾 Resource Usage:"
	@docker stats --no-stream --format "table {{.Container}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.MemPerc}}" | grep chrono | head -5
	@echo ""
	@echo "🎯 Archive.org Rate Limiting:"
	@echo "  Requests/minute: $$(docker compose exec -T redis redis-cli get archive_requests_last_minute 2>/dev/null || echo '0')/15"

# System compatibility checks
check-intelligent-compatibility: ## Check system compatibility for intelligent extraction
	@echo "🔍 Checking System Compatibility for Intelligent Extraction"
	@echo "=========================================================="
	@echo ""
	
	# Get system resources
	@TOTAL_RAM=$$(free -g | grep Mem | awk '{print $$2}'); \
	TOTAL_CPU=$$(nproc); \
	echo "💻 System Resources:"; \
	echo "  RAM: $${TOTAL_RAM}GB"; \
	echo "  CPU Cores: $${TOTAL_CPU}"; \
	echo ""; \
	\
	echo "📊 Intelligent Extraction Requirements:"; \
	echo "  RAM: 9.638GB"; \
	echo "  CPU Cores: 12.75"; \
	echo ""; \
	\
	if [ $$TOTAL_RAM -ge 16 ] && [ $$TOTAL_CPU -ge 8 ]; then \
		echo "✅ OPTIMAL: Production configuration (16GB+/8+ cores)"; \
		echo "   - 60% memory usage, 159% CPU usage"; \
		echo "   - Excellent performance expected"; \
	elif [ $$TOTAL_RAM -ge 32 ] && [ $$TOTAL_CPU -ge 16 ]; then \
		echo "🚀 EXCELLENT: High-load configuration (32GB+/16+ cores)"; \
		echo "   - 30% memory usage, 80% CPU usage"; \
		echo "   - Outstanding performance with scaling headroom"; \
	elif [ $$TOTAL_RAM -ge 8 ] && [ $$TOTAL_CPU -ge 4 ]; then \
		echo "⚠️  DEVELOPMENT: Limited configuration (8GB/4 cores)"; \
		echo "   - 120% memory usage (requires swap), 319% CPU usage"; \
		echo "   - Performance will be limited, enable swap"; \
		echo "   - Recommendation: Use 'make up-optimized' with swap"; \
	else \
		echo "❌ INSUFFICIENT: Below minimum requirements"; \
		echo "   - Minimum: 8GB RAM, 4 CPU cores"; \
		echo "   - Current system cannot run intelligent extraction optimally"; \
	fi
	@echo ""
	@echo "🔧 Optimization Commands:"
	@echo "  make up-intelligent              - Start optimized system"
	@echo "  make validate-intelligent-extraction - Full validation"

# Development helpers with resource awareness
dev-setup: ## Setup development environment with resource optimization
	@echo "🚀 Setting up optimized development environment..."
	@if [ ! -f .env ]; then \
		echo "📝 Creating .env file..."; \
		cp .env.example .env; \
	fi
	$(MAKE) build-optimized
	$(MAKE) up-optimized
	@echo "⏳ Waiting for services to be ready..."
	@sleep 15
	$(MAKE) migrate
	@echo "✅ Development environment ready!"
	@echo ""
	@echo "📚 Access points:"
	@echo "  - Frontend:     http://localhost:5173"
	@echo "  - Backend API:  http://localhost:8000"
	@echo "  - API Docs:     http://localhost:8000/docs"
	@echo "  - Meilisearch:  http://localhost:7700"
	@echo "  - Flower:       http://localhost:5555"
	@echo "  - Mailpit:      http://localhost:8025"
	@echo ""
	@echo "📊 Monitor resources with: make monitor"