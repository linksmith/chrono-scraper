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

### Scraping Engine Architecture
The scraping system uses a Firecrawl-only approach with intelligent filtering:
1. **CDX Discovery**: Parallel querying of Wayback Machine CDX API with 47 list page patterns filtering
2. **Intelligent Filtering**: Digest-based deduplication, high-value content prioritization, size filtering (1KB-10MB)
3. **Firecrawl-Only Extraction**: Consistent high-quality content extraction with metadata and markdown
4. **Resilience Layer**: Circuit breakers, automatic retries, crash recovery with resume keys
5. **Progress Tracking**: WebSocket-based real-time updates for long-running operations

### Frontend (SvelteKit 5)
- **SvelteKit 5** with TypeScript
- **Tailwind CSS** with shadcn-svelte components
- **Vite** for development and building
- **Real-time updates** via WebSocket connections

### Infrastructure
- **Docker Compose** for development environment with hot-reloading
- **Local Firecrawl** services (API, worker) for high-quality content extraction
- **Redis** for caching, task queues, and session management
- **Mailpit** for email testing in development
- **Enhanced Email System** with Mailgun (production) + SMTP/Mailpit (development) fallback

## Key Development Commands

### Environment Setup
```bash
# Start full development environment (includes Firecrawl services)
docker compose up

# Start core services only (lighter, without Firecrawl)
docker compose up backend frontend postgres redis meilisearch celery_worker celery_beat flower mailpit

# Start services individually for debugging
docker compose up postgres redis  # Just data services
docker compose up backend         # Just API
docker compose up frontend        # Just UI

# Health check all services
curl http://localhost:8000/api/v1/health
curl http://localhost:7700/health
curl http://localhost:3002/health  # Firecrawl API
curl http://localhost:3000         # Firecrawl Playwright
```

### Backend Development
```bash
# Run tests with coverage
docker compose exec backend pytest
docker compose exec backend pytest --cov=app --cov-report=html

# Run specific test file or integration tests for scraping
docker compose exec backend pytest tests/test_auth.py
docker compose exec backend pytest tests/test_projects.py -v
docker compose exec backend python test_wayback_integration.py
docker compose exec backend python test_firecrawl_integration.py
docker compose exec backend python test_firecrawl_simple.py

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

# Interactive development
docker compose exec backend python -c "from app.main import app; import IPython; IPython.embed()"
docker compose exec backend python -c "from app.core.database import get_db; from app.models import *; import asyncio"

# Service testing and debugging
docker compose exec backend python test_email.py
docker compose exec backend python test_domain_scraping.py
docker compose exec backend python -c "
from app.services.firecrawl_extractor import FirecrawlExtractor
from app.services.intelligent_filter import IntelligentFilter  
from app.services.wayback_machine import CDXAPIClient
import asyncio
# Test service integration
"

# Monitor Celery tasks
docker compose exec backend celery -A app.tasks.celery_app inspect active
docker compose exec backend celery -A app.tasks.celery_app inspect stats
docker compose exec backend celery -A app.tasks.celery_app control purge

# Direct database access
docker compose exec postgres psql -U chrono_scraper -d chrono_scraper
```

### Frontend Development
```bash
# Development and testing
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
docker compose exec frontend npm run dev    # Alternative dev server (if needed)

# Component development with Storybook (if configured)
docker compose exec frontend npm run storybook

# Bundle analysis
docker compose exec frontend npm run build -- --analyze
```

## Model Architecture

The application uses a comprehensive dual-model system bridging scraping operations with application data:

### Core Application Models (`app/models/`)
- **User**: JWT authentication, professional verification, LLM-based approval workflow
- **Project**: Web scraping projects with domain management and collaboration
- **Page**: Final scraped pages with extracted content and metadata for search
- **Domain**: Domain-specific scraping configuration and filtering rules

### Scraping Workflow Models (`app/models/scraping.py`)
- **ScrapePage**: Individual scraping operations with status tracking and error handling
- **CDXResumeState**: Crash recovery state for CDX pagination with resume capability
- **ScrapeSession**: Batch scraping sessions with progress tracking and statistics
- **PageErrorLog**: Detailed error tracking for failed scraping attempts with retry logic
- **ScrapeMonitoringLog**: Performance monitoring and metrics collection

### Advanced Features
- **ContentExtractionSchema**: Custom data extraction templates
- **CanonicalEntity**: Entity linking and knowledge graph building
- **Investigation**: OSINT investigation workflow management
- **UserApproval**: LLM-based user verification system with professional validation
- **ProjectShare**: Collaboration and public access controls

### Authentication & Authorization
- JWT-based authentication with refresh tokens and secure rotation
- Role-based access control (RBAC) with professional user verification
- LLM-powered professional user evaluation using OpenAI/Anthropic models
- API key management for programmatic access and automation
- **Comprehensive Email Verification System** with token-based verification and resend functionality

## Database

### Connection
- Development: `postgresql://chrono_scraper:chrono_scraper_dev@localhost:5435/chrono_scraper`
- All models use SQLModel with automatic Pydantic serialization
- Alembic handles schema migrations

### Key Relationships
**Application Layer:**
- Users have many Projects with ownership and sharing controls
- Projects have many Domains (targets) and Pages (results)
- Pages can have ContentExtractions and EntityMentions for advanced analysis
- Projects can be shared with ProjectShare for collaboration

**Scraping Layer:**
- Domains have ScrapeSession records tracking batch operations
- ScrapeSession contains many ScrapePage records with individual page processing
- ScrapePage links to final Page records upon successful extraction
- CDXResumeState enables crash recovery for large scraping operations
- PageErrorLog tracks failures with retry logic and error categorization

**Cross-layer:** ScrapePage.page_id → Page.id (one-to-one after successful processing)

## API Structure

### Endpoints
- `/api/v1/auth/*` - Authentication and user management
- `/api/v1/auth/email/*` - Email verification and management endpoints  
- `/api/v1/auth/password-reset/*` - Password reset functionality
- `/api/v1/auth/oauth2/*` - OAuth2 social authentication
- `/api/v1/users/*` - User CRUD and profile management
- `/api/v1/profile/*` - User profile and settings
- `/api/v1/projects/*` - Project and domain management  
- `/api/v1/search/*` - Full-text search with Meilisearch
- `/api/v1/entities/*` - Entity extraction and linking
- `/api/v1/extraction/*` - Content extraction schemas
- `/api/v1/library/*` - User library (starred, saved searches)
- `/api/v1/plans/*` - User plans and rate limiting
- `/api/v1/rbac/*` - Role-based access control
- `/api/v1/tasks/*` - Background task management
- `/api/v1/monitoring/*` - System monitoring and metrics
- `/api/v1/ws/*` - WebSocket connections for real-time updates
- `/api/v1/meilisearch/*` - Direct Meilisearch integration endpoints
- `/api/v1/health` - Health check endpoint

### Key API Patterns
- **Authentication**: Bearer token authentication required for most endpoints
- **Tokens**: Obtained via `/api/v1/auth/login` (JWT with refresh tokens)
- **Professional Users**: Require approval via LLM evaluation
- **Rate Limiting**: Plan-based rate limiting on API endpoints
- **Real-time Updates**: WebSocket connections for scraping progress
- **Pagination**: Cursor-based pagination for large datasets
- **Error Handling**: Consistent error response format with detailed messages

## Frontend Architecture

### Key Pages
- `/auth/login` - Authentication
- `/auth/register` - User registration with professional verification
- `/auth/unverified` - Email verification status and resend functionality
- `/verify-email` - Email verification processing with token handling
- `/projects` - Project management dashboard
- `/projects/create` - New project creation
- `/search` - Advanced search interface
- `/library` - User's saved content and searches

### State Management
- `$lib/stores/auth.ts` - Authentication state
- SvelteKit's built-in stores for local state
- Form validation with Zod schemas

### Styling
- Tailwind CSS utility classes
- shadcn-svelte component library for all UI components
- Use shadcn-svelte design patterns and markup wherever possible
- Responsive design with mobile-first approach

## Testing

### Backend Tests
- **Unit tests**: Business logic and utilities
- **Integration tests**: API endpoints with database
- **Markers**: `@pytest.mark.unit`, `@pytest.mark.integration`, `@pytest.mark.slow`
- **Coverage**: Minimum 80% required

### Frontend Tests
- **Vitest**: Unit and component tests
- **Playwright**: E2E tests
- **Testing Library**: Component testing utilities

## Configuration

### Environment Variables
Key variables in `.env`:
- `POSTGRES_*` - Database connection configuration
- `REDIS_HOST` - Redis connection for caching and task queues
- `MEILISEARCH_*` - Search engine configuration and master key
- `SECRET_KEY` - JWT signing key for authentication
- `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` - LLM integration for user approval and analysis
- `FIRECRAWL_LOCAL_URL` / `FIRECRAWL_API_KEY` - Local Firecrawl service integration
- `FIRECRAWL_LOCAL_URL` / `FIRECRAWL_API_KEY` - Firecrawl service configuration
- `WAYBACK_MACHINE_TIMEOUT` / `WAYBACK_MACHINE_MAX_RETRIES` - CDX API resilience settings
- `DECODO_*` / `PROXY_*` - Proxy configuration for enhanced scraping
- **Email Configuration**:
  - `MAILGUN_API_KEY` / `MAILGUN_DOMAIN` - Mailgun integration for production
  - `SMTP_*` - SMTP fallback configuration
  - `EMAILS_FROM_EMAIL` / `EMAILS_FROM_NAME` - Email sender configuration
  - `FRONTEND_URL` - Frontend URL for email verification links
- **OAuth2 Settings**: `GOOGLE_*` / `GITHUB_*` - Social authentication providers

### Settings
- `backend/app/core/config.py` - Centralized Pydantic settings
- Supports both development and production configurations
- Environment-based feature toggles

## Migration from Django

This is a complete rewrite from a Django-based system. Key differences:
- FastAPI async/await instead of Django sync
- SQLModel instead of Django ORM
- Pydantic for serialization instead of Django REST Framework
- SvelteKit instead of Django templates
- Component-based frontend instead of server-rendered templates

## Scraping System Deep Dive

### Content Processing Pipeline
1. **CDX Discovery** (`wayback_machine.py`): Query CDX API with enhanced filtering (5000 records/page, resume keys)
2. **Intelligent Filtering** (`intelligent_filter.py`): 47 list page patterns, digest deduplication, priority scoring
3. **Firecrawl Extraction** (`firecrawl_extractor.py`): High-quality content extraction with metadata and markdown
4. **Indexing** (`meilisearch_service.py`): Full-text index with project-specific indices
5. **Storage**: Persist to both ScrapePage (operational) and Page (application) models

### Celery Task Architecture
The system uses a consolidated Celery configuration (`app/tasks/celery_app.py`) with two main task modules:

#### Primary Firecrawl Tasks (`app/tasks/firecrawl_scraping.py`)
- **scrape_domain_with_firecrawl**: Main domain scraping task using Firecrawl-only extraction
- **CDX Discovery**: Parallel querying with intelligent filtering and digest deduplication
- **Batch Processing**: Processes pages in parallel batches for optimal performance
- **Progress Tracking**: Real-time WebSocket updates for long-running operations
- **Error Handling**: Comprehensive error tracking and automatic retry mechanisms

#### Simple Retry Tasks (`app/tasks/scraping_simple.py`)
- **process_page_content**: Simplified content processing for retry operations
- **Lightweight Implementation**: Minimal dependencies for reliable retry processing
- **Meilisearch Integration**: Simple indexing without external service dependencies
- **Event Loop Management**: Proper async/await handling in Celery workers

### Circuit Breaker System (`circuit_breaker.py`)
Service-specific circuit breakers with different thresholds:
- **Wayback Machine**: 5 failures, 60s timeout (external dependency)
- **Meilisearch**: 3 failures, 30s timeout (local service)
- **Content Extraction**: 10 failures, 120s timeout (processing intensive)

### Intelligent Content Filtering System
**High-Value Content Prioritization** (Priority 8-10):
- Government/educational domains (`.gov`, `.edu`, `.org`, `.mil`)
- Research keywords (`research`, `report`, `analysis`, `study`, `whitepaper`)
- Large content (>5KB, likely articles)
- PDF documents
- Recent content (<30 days)

**List Page Filtering** (47 patterns to filter out):
- Blog pagination (`/blog/page/\d+`)
- Admin areas (`/wp-admin/`, `/admin/`)
- Search pages (`/search/`, `\?search=`)
- Category listings (`/category/`, `/tag/`)
- Date archives (`/\d{4}/\d{2}/?$`)

**Size and Format Filtering**:
- Content size: 1KB-10MB range
- MIME types: HTML and PDF only
- Skip media files (`.css`, `.js`, `.jpg`, etc.)

### WebSocket Progress Tracking (`websocket_service.py`)
Real-time updates for long-running scraping operations:
- CDX discovery progress
- Content extraction status
- Error notifications
- Completion statistics

## Email System Architecture

### Production Email Service (`app/core/email_service.py`)
- **Multi-Provider Support**: Mailgun (production) with SMTP fallback
- **Development Integration**: Uses Mailpit for local email testing
- **Advanced Features**:
  - Bulk email sending with batch processing (up to 1000 recipients)
  - Email address validation via Mailgun API
  - Attachment support for complex notifications
  - Automatic fallback from Mailgun to SMTP on failures
  - Custom headers for tracking and environment identification

### Email Verification Workflow
- **Token-Based Verification**: Secure email verification with expiring tokens
- **Multiple Endpoints**: GET (email links) and POST (API) verification
- **User Experience**: Comprehensive verification pages with error handling
- **Resend Functionality**: Multiple resend options (by email or current user)
- **Status Tracking**: Real-time verification status for authenticated users

## Firecrawl-Only Implementation (Current Architecture)

### Key Services
- **`app/services/firecrawl_extractor.py`** - Dedicated Firecrawl content extraction with quality scoring
- **`app/services/intelligent_filter.py`** - Smart CDX filtering with 47 list page patterns and digest deduplication  
- **`app/services/wayback_machine.py`** - Enhanced CDX API client with resume keys and 5000 records/page
- **`app/models/extraction_data.py`** - Shared data models for content extraction (ExtractedContent, ContentExtractionException)

### Local Firecrawl Integration
The system uses local Firecrawl services instead of cloud API:
- **Firecrawl API** (`firecrawl-api:3002`) - Main extraction service
- **Firecrawl Worker** (`firecrawl-worker`) - Background job processing  
- **Playwright Service** (`firecrawl-playwright:3000`) - Browser automation
- **Shared Redis** - Job queuing between Chrono Scraper and Firecrawl services
- **Environment Integration** - FIRECRAWL_* environment variables for configuration

### Content Extraction Flow
1. **CDX Query**: Fetch records with size filtering (1KB-10MB) and built-in deduplication
2. **Intelligent Filter**: Apply 47 list page patterns, digest deduplication, priority scoring (1-10)
3. **Firecrawl Extract**: Process all content through local Firecrawl service for consistent quality
4. **Index & Store**: Full-text search indexing and database persistence

### Load Reduction Strategies
- **Digest Deduplication**: Skip pages with unchanged content (70%+ reduction potential)
- **List Page Filtering**: Filter pagination, admin, search, category pages using 47 patterns
- **High-Value Prioritization**: Process research, reports, government content first
- **Resume Keys**: Crash recovery for large domains with millions of records

### Service Health & Monitoring
```bash
# Check service health
curl http://localhost:3002/health  # Firecrawl API
curl http://localhost:3000         # Playwright service
docker compose ps firecrawl-api firecrawl-worker firecrawl-playwright

# Monitor Firecrawl logs
docker compose logs -f firecrawl-api
docker compose logs -f firecrawl-worker  
docker compose logs -f firecrawl-playwright
```

## Architectural Consolidation (2025-01-15)

The system has been consolidated to remove technical debt from multiple scraping approaches:

### Consolidated Architecture
- **Single Celery Configuration**: `app/tasks/celery_app.py` is the only Celery configuration
- **Firecrawl-Only Extraction**: `app/services/firecrawl_extractor.py` is the primary content extraction service
- **Unified Data Models**: `app/models/extraction_data.py` provides shared `ExtractedContent` class
- **Two Task Modules**: `firecrawl_scraping.py` (primary) and `scraping_simple.py` (retries only)

### Removed Legacy Components
- **Duplicate Celery configs**: Removed `app/core/celery_app.py` and `app/celery_tasks/` directory
- **Legacy extraction services**: Removed `content_extractor.py`, `content_extraction.py`, `hybrid_content_extractor.py`
- **Unused Wayback services**: Removed `wayback_service.py`, `parallel_cdx_fetcher.py`
- **Legacy task implementations**: Removed `scraping_tasks.py`, `scraping.py`, `indexing.py`, `scraping_sync.py`

### Current Active Services
- **Content Extraction**: `firecrawl_extractor.py` (Firecrawl-only)
- **Wayback Machine**: `wayback_machine.py` (CDXAPIClient with intelligent filtering)
- **Tasks**: `firecrawl_scraping.py` (primary) + `scraping_simple.py` (retries)
- **Shared Models**: `extraction_data.py` (ExtractedContent, ContentExtractionException)

## Important Notes

### Development Practices
- Never add claude coauthorship to git commit messages (***NEVER***)
- Always use `docker compose` not `docker-compose`
- Never commit secrets or API keys
- Always run python, node, npm, uv commands etc. inside Docker containers
- Check code coverage requirements (80% minimum)
- Test both backend and frontend thoroughly before committing

### Code Architecture Patterns
- Use async/await patterns in FastAPI routes
- Follow SQLModel patterns for database operations  
- Use TypeScript strictly in frontend
- Use shadcn-svelte components and design patterns for all UI development
- Always use `onclick` and not `on:click` for shadcn Button components
- Follow Pydantic patterns for data validation and serialization

### System Architecture Key Points
- **Firecrawl-only extraction** provides consistent high-quality content with markdown and metadata
- **Intelligent filtering** reduces scraping load by 70%+ through digest deduplication and list page filtering
- **Circuit breakers** prevent cascade failures in scraping operations
- **CDX resume state** enables recovery from crashes in large scraping jobs
- **Email verification** is mandatory for user access and uses comprehensive error handling
- **Production email system** provides 99.9% delivery reliability with Mailgun + SMTP fallback
- **Local Firecrawl services** replace cloud API for better control and cost efficiency
- **WebSocket connections** provide real-time updates for long-running scraping operations

### Service Dependencies
Critical service startup order:
1. PostgreSQL, Redis (data layer)
2. Meilisearch (search engine)
3. Firecrawl services (Playwright → API → Worker)
4. Backend API (depends on all above)
5. Frontend, Celery workers (depend on backend)

# important-instruction-reminders
Do what has been asked; nothing more, nothing less.
NEVER create files unless they're absolutely necessary for achieving your goal.
ALWAYS prefer editing an existing file to creating a new one.
NEVER proactively create documentation files (*.md) or README files. Only create documentation files if explicitly requested by the User.