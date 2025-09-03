# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Chrono Scraper v2 is a production-ready Wayback Machine scraping platform built with FastAPI + SvelteKit. It provides comprehensive web scraping, content extraction, entity processing, and full-text search capabilities specifically designed for OSINT investigations and historical research.

## Architecture

### Backend (FastAPI)
- **FastAPI** with SQLModel for type-safe database operations
- **PostgreSQL** primary database with Alembic migrations
- **Celery** with Redis for distributed background task processing
- **Meilisearch** for full-text search indexing
- **Firecrawl-Only Content Extraction** using local Firecrawl service with intelligent filtering
- **Circuit Breakers** for service reliability and fault tolerance

### Frontend (SvelteKit 5)
- **SvelteKit 5** with TypeScript
- **Tailwind CSS** with shadcn-svelte components
- **Vite** for development and building
- **Real-time updates** via WebSocket connections

### Infrastructure
- **Docker Compose** for development environment with hot-reloading
- **Local Firecrawl** services (API, worker, Playwright) for high-quality content extraction
- **Redis** for caching, task queues, and session management
- **Mailpit** for email testing in development
- **Enhanced Email System** with Mailgun (production) + SMTP/Mailpit (development) fallback

## Key Development Commands

### Quick Start with Makefile
```bash
# Initialize complete development environment
make init    # Creates .env, builds containers, starts services, runs migrations

# Common development tasks  
make up      # Start all services
make down    # Stop all services
make logs    # View all service logs
make status  # Check status of all services

# Testing commands
make test              # Run complete test suite
make test-backend      # Backend tests only
make test-frontend     # Frontend tests only  
make test-e2e          # E2E tests only
make test-unit         # Unit tests only
make test-integration  # Integration tests only
make lint              # Lint both backend and frontend
make coverage          # Generate coverage reports

# Code formatting
make format-backend    # Format Python code (black + ruff)
make format-frontend   # Format TypeScript/Svelte code (prettier)

# Database operations
make migrate           # Run migrations
make makemigrations message="description"  # Create new migration
make db-shell          # Open PostgreSQL shell
make create-superuser  # Create admin user
make seed-db          # Seed with sample data

# Resource optimization
make up-optimized      # Start with optimized resource allocation
make monitor           # Monitor container resource usage
make resource-stats    # Show detailed resource statistics
```

### Backend Development
```bash
# Run tests with coverage
docker compose exec backend pytest
docker compose exec backend pytest --cov=app --cov-report=html
docker compose exec backend pytest tests/test_auth.py -v  # Specific test file

# Run tests with markers
docker compose exec backend pytest -m "unit" -v
docker compose exec backend pytest -m "integration" -v  
docker compose exec backend pytest -m "slow" -v

# Format and lint code
docker compose exec backend black .
docker compose exec backend ruff check . --fix
docker compose exec backend ruff format .

# Database operations
docker compose exec backend alembic revision --autogenerate -m "Description"
docker compose exec backend alembic upgrade head
docker compose exec backend alembic downgrade -1
docker compose exec backend alembic history --verbose

# Monitor Celery tasks
docker compose exec backend celery -A app.tasks.celery_app inspect active
docker compose exec backend celery -A app.tasks.celery_app inspect stats
docker compose exec backend celery -A app.tasks.celery_app control purge

# Direct database access
docker compose exec postgres psql -U chrono_scraper -d chrono_scraper

# Interactive Python shell
docker compose exec backend python
```

### Frontend Development
```bash
# Testing
docker compose exec frontend npm test
docker compose exec frontend npm run test:ui
docker compose exec frontend npm run test:e2e
docker compose exec frontend npm run test:e2e -- --headed  # Run E2E with browser visible

# Code quality
docker compose exec frontend npm run format
docker compose exec frontend npm run lint
docker compose exec frontend npm run check
docker compose exec frontend npm run build

# Package management
docker compose exec frontend npm install <package>

# Bundle analysis
docker compose exec frontend npm run build -- --analyze
```

### Service Health Monitoring
```bash
# Check service health
curl http://localhost:8000/api/v1/health  # Backend API
curl http://localhost:7700/health         # Meilisearch
curl http://localhost:3002/health         # Firecrawl API
curl http://localhost:3000                # Firecrawl Playwright

# Monitor service logs
docker compose logs -f backend
docker compose logs -f celery_worker
docker compose logs -f firecrawl-api
docker compose logs -f firecrawl-worker

# Flower (Celery monitoring)
http://localhost:5555
```

### Debugging Common Issues
```bash
# Check if services are running
make status

# View specific service logs
docker compose logs -f <service_name>

# Restart a specific service
docker compose restart <service_name>

# Clean rebuild if issues persist
make down
make resource-cleanup
make build
make up

# Database connection issues
docker compose exec postgres psql -U chrono_scraper -d chrono_scraper -c "SELECT 1;"

# Redis connection test
docker compose exec redis redis-cli ping

# Check Meilisearch indexes
curl http://localhost:7700/indexes
```

## Testing & Authentication

### Test User Setup
Users must be **both verified AND approved** to login successfully:
- **Email verification**: `is_verified = true`
- **Manual approval**: `approval_status = 'approved'`
- **Active status**: `is_active = true`

#### Quick Test User Creation
```bash
# Create pre-configured test user (playwright@test.com / TestPassword123!)
docker compose exec backend python -c "
import asyncio
from app.core.database import get_db
from app.models.user import User
from app.core.security import get_password_hash
from sqlmodel import select

async def create_test_user():
    async for db in get_db():
        stmt = select(User).where(User.email == 'playwright@test.com')
        result = await db.execute(stmt)
        if not result.scalar_one_or_none():
            user = User(
                email='playwright@test.com',
                full_name='Playwright Test User',
                hashed_password=get_password_hash('TestPassword123!'),
                is_verified=True,
                is_active=True,
                approval_status='approved',
                data_handling_agreement=True,
                ethics_agreement=True,
                research_interests='Automated testing',
                research_purpose='Application testing',
                expected_usage='Testing functionality'
            )
            db.add(user)
            await db.commit()
            print(f'Created test user: playwright@test.com')
        else:
            print(f'Test user already exists')
        break

asyncio.run(create_test_user())
"

# Check user status
docker compose exec postgres psql -U chrono_scraper -d chrono_scraper -c "SELECT email, is_verified, approval_status, is_active FROM users WHERE email = 'playwright@test.com';"

# Approve user if needed
docker compose exec postgres psql -U chrono_scraper -d chrono_scraper -c "UPDATE users SET approval_status = 'approved', approval_date = NOW() WHERE email = 'playwright@test.com';"
```

### Email Testing
- **Mailpit URL**: http://localhost:8025
- All development emails are captured in Mailpit
- Use for email verification testing during registration flow

## Model Architecture

### Core Application Models (`app/models/`)
- **User**: JWT authentication, professional verification, LLM-based approval workflow
- **Project**: Web scraping projects with domain management and collaboration
- **PageV2**: Shared pages with extracted content and metadata for multi-project search
- **ProjectPage**: Junction table managing many-to-many relationships between projects and shared pages
- **Domain**: Domain-specific scraping configuration and filtering rules

### Scraping Workflow Models (`app/models/scraping.py`)
- **ScrapePage**: Individual scraping operations with status tracking
- **CDXResumeState**: Crash recovery state for CDX pagination
- **ScrapeSession**: Batch scraping sessions with progress tracking
- **PageErrorLog**: Detailed error tracking for failed scraping attempts
- **ScrapeMonitoringLog**: Performance monitoring and metrics

### Key Relationships
- Users → Projects (one-to-many with ownership)
- Projects → Domains (one-to-many targets)
- Projects ←→ PageV2 (many-to-many via ProjectPage junction table)
- Domains → ScrapeSession → ScrapePage → PageV2 (shared scraping workflow)
- ScrapePage.page_id → PageV2.id (after successful processing)
- ProjectPage stores project-specific metadata (tags, review status, notes)

## API Structure

### Main API Endpoint Groups
- `/api/v1/auth/*` - Authentication and user management
- `/api/v1/projects/*` - Project and domain management  
- `/api/v1/search/*` - Full-text search with Meilisearch
- `/api/v1/entities/*` - Entity extraction and linking
- `/api/v1/shared-pages/*` - Shared page management and multi-project operations
- `/api/v1/library/*` - User library and collections
- `/api/v1/ws/*` - WebSocket connections for real-time updates
- `/api/v1/health` - Health check endpoint
- `/api/v1/tasks/*` - Task management and monitoring
- `/api/v1/monitoring/*` - System monitoring and metrics

### Authentication
- Bearer token authentication required for most endpoints
- Tokens obtained via `/api/v1/auth/login` (JWT with refresh tokens)
- Professional users require LLM-based approval
- OAuth2 support available via `/api/v1/oauth2/*`

## Scraping System Architecture

### Content Processing Pipeline
1. **CDX Discovery** (`wayback_machine.py`): Query CDX API with 5000 records/page, resume keys
2. **Intelligent Filtering** (`intelligent_filter.py`): 47 list page patterns, digest deduplication
3. **Firecrawl Extraction** (`firecrawl_extractor.py`): High-quality content extraction
4. **Indexing** (`meilisearch_service.py`): Full-text search indexing
5. **Storage**: Persist to ScrapePage and PageV2 models with ProjectPage associations

### Celery Task Architecture
- **Configuration**: `app/tasks/celery_app.py` (single consolidated config)
- **Primary Tasks**: `app/tasks/firecrawl_scraping.py` (main scraping)
- **Retry Tasks**: `app/tasks/scraping_simple.py` (lightweight retries)
- **Beat Schedule**: Periodic tasks for cleanup and monitoring

### Circuit Breaker Thresholds
- **Wayback Machine**: 5 failures, 60s timeout
- **Meilisearch**: 3 failures, 30s timeout
- **Content Extraction**: 10 failures, 120s timeout

### Intelligent Filtering System
**High-Value Content** (Priority 8-10):
- Government/educational domains (.gov, .edu, .org, .mil)
- Research keywords (research, report, analysis, study)
- Large content (>5KB), PDFs, recent content (<30 days)

**List Page Filtering** (47 patterns filtered out):
- Blog pagination, admin areas, search pages
- Category listings, date archives
- Size range: 1KB-10MB, HTML and PDF only

## Frontend Architecture

### Key Components
- **State Management**: `$lib/stores/` (auth, page-management, filters)
- **UI Components**: shadcn-svelte patterns throughout
- **Bulk Operations**: Shift-click range selection for multi-page operations
- **Real-time Updates**: WebSocket integration for progress tracking

### Important UI Patterns
- Always use `onclick` (not `on:click`) for shadcn Button components
- Prefer Sheet components over Dialog for mobile experience
- Use lucide-svelte icons with proper semantics
- Custom button elements for complex interactions (avoid shadcn Checkbox for shift-click)
- Mobile navigation uses Sheet-based overlays (z-index: 70)

### Frontend Scripts (package.json)
- `npm run dev` - Start development server with hot reload
- `npm run build` - Build for production
- `npm run check` - Type checking and sync
- `npm run test` - Run Vitest tests
- `npm run test:e2e` - Run Playwright E2E tests
- `npm run lint` - ESLint checking
- `npm run format` - Prettier formatting

## Configuration

### Environment Variables
Key variables in `.env`:
- `POSTGRES_*` - Database connection
- `REDIS_HOST` - Redis connection
- `MEILISEARCH_*` - Search engine config
- `SECRET_KEY` - JWT signing key
- `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` - LLM integration
- `FIRECRAWL_LOCAL_URL` / `FIRECRAWL_API_KEY` - Firecrawl service
- `WAYBACK_MACHINE_*` - CDX API settings
- `MAILGUN_*` / `SMTP_*` - Email configuration
- `FRONTEND_URL` - Frontend URL for email links

### Service Dependencies
Critical startup order:
1. PostgreSQL, Redis (data layer)
2. Meilisearch (search engine)
3. Firecrawl services (Playwright → API → Worker)
4. Backend API (depends on all above)
5. Frontend, Celery workers (depend on backend)

## Development Best Practices

### Code Standards
- Use async/await patterns in FastAPI routes
- Follow SQLModel patterns for database operations
- Use TypeScript strictly in frontend
- Use shadcn-svelte components for all UI
- Maintain 80% minimum test coverage

### Git Practices
- Never add Claude coauthorship to commits
- Commits should be per distinct feature
- Never commit secrets or API keys
- Always use `docker compose` (not `docker-compose`)

### Testing Requirements
- Test both backend and frontend before committing
- Users must be verified AND approved for authentication testing
- Run linting and type checking before commits
- Use Mailpit for email testing in development
- Run `make lint` and `make test` before pushing

## Shared Pages Architecture

### Migration from Legacy Page System
The system has migrated from a legacy single-project Page model to a shared PageV2 system that enables cross-project collaboration and content sharing.

**Key Changes:**
- **PageV2 Model**: Uses UUID primary keys instead of integers for better distribution
- **ProjectPage Junction**: Many-to-many relationship enabling page sharing across projects
- **Project-Specific Metadata**: Each project can have different tags, review status, and notes for the same page
- **Cross-Project Search**: Search across multiple projects simultaneously
- **Unified Content**: Same URL content shared across projects reduces storage and improves consistency

**API Endpoints:**
- **New**: `/api/v1/shared-pages/*` - All shared page operations
- **Deprecated**: `/api/v1/pages/*` - Legacy single-project endpoints (avoid for new development)

**Working with UUIDs:**
- PageV2 uses UUID primary keys (e.g., `550e8400-e29b-41d4-a716-446655440000`)
- Always use string type for page IDs in TypeScript interfaces
- No need for integer conversion when working with shared pages
- Use proper UUID validation for API requests

**Development Guidelines:**
- Always use `/api/v1/shared-pages/*` endpoints for new features
- Consider project context when displaying page actions and metadata
- Use the SharedPagesApiService for all shared page operations
- Enable shared pages API in stores with `enableSharedPagesApi(projectId?)`

## Important Notes

### System Architecture Key Points
- **Firecrawl-only extraction** provides consistent high-quality content
- **Intelligent filtering** reduces scraping load by 70%+
- **Circuit breakers** prevent cascade failures
- **CDX resume state** enables crash recovery for large jobs
- **Email verification** is mandatory with comprehensive error handling
- **Local Firecrawl services** replace cloud API for better control
- **WebSocket connections** provide real-time scraping updates

### Current Active Services (Post-Consolidation)
- **Content Extraction**: `firecrawl_extractor.py` (Firecrawl-only)
- **Wayback Machine**: `wayback_machine.py` (CDXAPIClient)
- **Tasks**: `firecrawl_scraping.py` (primary) + `scraping_simple.py` (retries)
- **Shared Models**: `extraction_data.py` (ExtractedContent class)
- **Meilisearch Key Manager**: `meilisearch_key_manager.py` (secure key management with rotation)

### Development Reminders
- Always run commands inside Docker containers
- Check CLAUDE.local.md for sensitive information and credentials
- Use Makefile commands for common tasks
- Monitor services with Flower (http://localhost:5555) and logs
- Run `make resource-stats` to check memory usage if performance degrades
- Use `make up-optimized` for resource-constrained environments