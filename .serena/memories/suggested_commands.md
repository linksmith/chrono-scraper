# Essential Development Commands

## Quick Start Commands
```bash
# Initialize development environment
make init

# Start all services
docker compose up
# OR start in background
docker compose up -d

# Check service status
make status
```

## Backend Development Commands
```bash
# Run tests with coverage
docker compose exec backend pytest
docker compose exec backend pytest --cov=app --cov-report=html

# Run specific test types
docker compose exec backend pytest -m "unit" -v
docker compose exec backend pytest -m "integration" -v
docker compose exec backend pytest tests/test_auth.py

# Code formatting and linting
docker compose exec backend black .
docker compose exec backend ruff check . --fix
docker compose exec backend ruff format .
docker compose exec backend mypy app/

# Database operations
docker compose exec backend alembic revision --autogenerate -m "Description"
docker compose exec backend alembic upgrade head
docker compose exec backend alembic downgrade -1

# Interactive development
docker compose exec backend python
docker compose exec backend /bin/bash
```

## Frontend Development Commands
```bash
# Run tests
docker compose exec frontend npm test
docker compose exec frontend npm run test:ui
docker compose exec frontend npm run test:e2e

# Code quality
docker compose exec frontend npm run format
docker compose exec frontend npm run lint
docker compose exec frontend npm run check

# Build and package management
docker compose exec frontend npm run build
docker compose exec frontend npm install <package>
docker compose exec frontend /bin/sh
```

## Testing Commands (via Makefile)
```bash
# Run all tests
make test-all

# Run specific test suites
make test-backend
make test-frontend  
make test-e2e
make test-unit
make test-integration

# Security and performance
make test-security
make test-performance

# Generate coverage reports
make coverage
```

## Database & Services Commands
```bash
# Database shell access
docker compose exec postgres psql -U chrono_scraper chrono_scraper
make shell-db

# Redis CLI
docker compose exec redis redis-cli
make redis-cli

# Monitor Celery tasks
docker compose exec backend celery -A app.tasks.celery_app inspect active
docker compose exec backend celery -A app.tasks.celery_app inspect stats

# View service logs
docker compose logs -f backend
docker compose logs -f frontend
make logs
```

## Service Health Checks
```bash
# Check all service health
curl http://localhost:8000/health          # Backend API
curl http://localhost:7700/health          # Meilisearch
curl http://localhost:5173                 # Frontend
curl http://localhost:3002/health          # Firecrawl API

# Service monitoring dashboards
# Flower (Celery): http://localhost:5555
# Mailpit: http://localhost:8025
# API Docs: http://localhost:8000/docs
```

## Development Environment Management
```bash
# Clean and reset
docker compose down -v
make clean
make reset

# Build and rebuild
docker compose build
docker compose build --no-cache
make rebuild

# Environment setup
cp .env.example .env  # Configure environment variables
```

## Utility Commands (Linux)
```bash
# File operations
ls -la
find . -name "*.py" -type f
grep -r "pattern" backend/app/
cat filename.txt
head -20 filename.txt
tail -f logs/app.log

# Process management  
ps aux | grep python
kill -9 <pid>
jobs
fg

# Git operations
git status
git add .
git commit -m "Description"
git push origin main
git log --oneline
```

## When Task is Complete
```bash
# 1. Run all linting and formatting
make lint
make format-backend
make format-frontend

# 2. Run full test suite
make test-all

# 3. Check coverage
make coverage

# 4. Verify services health
make status

# 5. Database migrations (if schema changed)
make makemigrations message="Description"
make migrate
```