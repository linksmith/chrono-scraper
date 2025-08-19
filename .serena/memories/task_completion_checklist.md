# Task Completion Checklist

## Code Quality Requirements (Always Run)

### 1. Backend Code Quality
```bash
# Format code
docker compose exec backend black .
docker compose exec backend ruff check . --fix
docker compose exec backend ruff format .

# Type checking
docker compose exec backend mypy app/

# Security checks
docker compose exec backend bandit -r app/ -f json -o bandit-report.json
docker compose exec backend safety check
```

### 2. Frontend Code Quality  
```bash
# Format and lint
docker compose exec frontend npm run format
docker compose exec frontend npm run lint
docker compose exec frontend npm run check

# Build verification
docker compose exec frontend npm run build
```

### 3. Testing Requirements
```bash
# Backend tests (80% coverage minimum required)
docker compose exec backend pytest --cov=app --cov-report=html --cov-report=xml --cov-fail-under=80

# Frontend tests
docker compose exec frontend npm test

# E2E tests (when applicable)
docker compose exec frontend npm run test:e2e
```

## Database Changes

### 4. Migration Management (If Schema Changed)
```bash
# Create migration
docker compose exec backend alembic revision --autogenerate -m "Descriptive message"

# Apply migration
docker compose exec backend alembic upgrade head

# Verify migration
docker compose exec backend alembic history --verbose
```

## Service Health Verification

### 5. Service Health Checks
```bash
# Check all services are running
docker compose ps

# Health endpoints
curl -f http://localhost:8000/health     # Backend
curl -f http://localhost:7700/health     # Meilisearch  
curl -f http://localhost:3002/health     # Firecrawl API
curl -f http://localhost:5173            # Frontend
```

### 6. Functional Testing
```bash
# Test key functionality works
docker compose exec backend python -c "
from app.core.database import get_db
from app.models import *
print('Database models imported successfully')
"

# Test Celery workers
docker compose exec backend celery -A app.tasks.celery_app inspect active
```

## Documentation & Environment

### 7. Environment Verification
```bash
# Ensure .env is properly configured
cat .env | grep -E "(POSTGRES_|REDIS_|MEILISEARCH_)"

# Check Docker containers are healthy
docker compose exec postgres pg_isready -U chrono_scraper
docker compose exec redis redis-cli ping
```

### 8. Performance Checks (For Significant Changes)
```bash
# Check backend performance
docker compose exec backend python -m pytest tests/test_performance/ -v

# Frontend build size (when applicable)
docker compose exec frontend npm run build -- --analyze
```

## Git Workflow

### 9. Version Control Best Practices
```bash
# Verify no secrets in code
git diff --cached | grep -E "(API_KEY|PASSWORD|SECRET)"

# Clean commit message (no Claude coauthorship)
git add .
git commit -m "Descriptive message without Claude attribution"

# Ensure no large files or build artifacts
git status --ignored
```

## Production Readiness (Major Changes)

### 10. Production Considerations
```bash
# Check Docker builds work
docker compose -f docker-compose.production.yml build

# Verify environment configurations
docker compose exec backend python -c "from app.core.config import settings; print(f'Environment: {settings.ENVIRONMENT}')"

# Test with production-like data volumes (when applicable)
```

## Failure Recovery

### If Any Step Fails:
1. **Fix the specific issue** (formatting, tests, linting)
2. **Re-run the failed step** to verify the fix
3. **Run dependent steps** (e.g., if tests failed, run full test suite after fix)
4. **Document any configuration changes** needed

### Critical Failure Points:
- **Coverage below 80%**: Add tests before completing task
- **Type errors**: Fix all MyPy issues before proceeding  
- **Migration errors**: Never force migrations, fix schema issues
- **Service health failures**: Investigate and resolve before completion

## Notes
- **Never commit** with failing tests or linting errors
- **Always run commands inside Docker** containers, not locally
- **Use `docker compose`** not `docker-compose`
- **Never add Claude coauthorship** to git commits
- **Verify hot-reloading** works after significant changes