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
- **Hybrid Content Extraction** using local Firecrawl + BeautifulSoup fallback
- **Circuit Breakers** for service reliability and fault tolerance

### Scraping Engine Architecture
The scraping system uses a multi-layered approach:
1. **CDX Discovery**: Parallel querying of Wayback Machine CDX API with intelligent batching
2. **Smart Content Routing**: Government/educational domains → Firecrawl, standard content → BeautifulSoup  
3. **Resilience Layer**: Circuit breakers, automatic retries, and crash recovery
4. **Progress Tracking**: WebSocket-based real-time updates for long-running operations
5. **Quality Assurance**: Content scoring and filtering of list pages/duplicates

### Frontend (SvelteKit 5)
- **SvelteKit 5** with TypeScript
- **Tailwind CSS** with shadcn-svelte components
- **Vite** for development and building
- **Real-time updates** via WebSocket connections

### Infrastructure
- **Docker Compose** for development environment with hot-reloading
- **Local Firecrawl** services (API, worker, playwright) for enhanced content extraction
- **Redis** for caching, task queues, and session management
- **Mailpit** for email testing in development

## Key Development Commands

### Environment Setup
```bash
# Start full development environment
docker compose up

# Start without Firecrawl services (lighter)
docker compose up backend frontend postgres redis meilisearch
```

### Backend Development
```bash
# Run tests with coverage
docker compose exec backend pytest

# Run specific test file or integration tests for scraping
docker compose exec backend pytest tests/test_auth.py
docker compose exec backend python test_wayback_integration.py
docker compose exec backend python test_hybrid_implementation.py

# Run tests with markers
docker compose exec backend pytest -m "unit"
docker compose exec backend pytest -m "integration"
docker compose exec backend pytest -m "slow"

# Format code
docker compose exec backend black .
docker compose exec backend ruff check . --fix

# Database migrations
docker compose exec backend alembic revision --autogenerate -m "Description"
docker compose exec backend alembic upgrade head

# Interactive Python shell with app context
docker compose exec backend python -c "from app.main import app; import IPython; IPython.embed()"

# Test scraping services directly
docker compose exec backend python -c "
from app.services.wayback_machine import CDXAPIClient
from app.services.hybrid_content_extractor import get_hybrid_extractor
import asyncio
"
```

### Frontend Development
```bash
# Run tests
docker compose exec frontend npm test

# Run tests in UI mode
docker compose exec frontend npm run test:ui

# Run E2E tests
docker compose exec frontend npm run test:e2e

# Format code
docker compose exec frontend npm run format

# Lint code
docker compose exec frontend npm run lint

# Type checking
docker compose exec frontend npm run check

# Build for production
docker compose exec frontend npm run build
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
- `/api/v1/users/*` - User CRUD and profile management
- `/api/v1/projects/*` - Project and domain management
- `/api/v1/search/*` - Full-text search with Meilisearch
- `/api/v1/entities/*` - Entity extraction and linking
- `/api/v1/extraction/*` - Content extraction schemas
- `/api/v1/library/*` - User library (starred, saved searches)
- `/api/v1/plans/*` - User plans and rate limiting

### Authentication
- Bearer token authentication required for most endpoints
- Tokens obtained via `/api/v1/auth/login`
- Professional users require approval via LLM evaluation

## Frontend Architecture

### Key Pages
- `/auth/login` - Authentication
- `/auth/register` - User registration with professional verification
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
- `HYBRID_PROCESSING_ENABLED` - Toggle for hybrid content extraction
- `WAYBACK_MACHINE_TIMEOUT` / `WAYBACK_MACHINE_MAX_RETRIES` - CDX API resilience settings
- `DECODO_*` / `PROXY_*` - Proxy configuration for enhanced scraping

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
1. **CDX Discovery** (`wayback_machine.py`): Query CDX API with intelligent filtering to avoid list pages
2. **Smart Routing** (`hybrid_content_extractor.py`): Route high-value content to Firecrawl, standard to BeautifulSoup
3. **Content Extraction**: Extract title, text, metadata with quality scoring (0-10 scale)
4. **Indexing** (`meilisearch_service.py`): Full-text index with project-specific indices
5. **Storage**: Persist to both ScrapePage (operational) and Page (application) models

### Celery Task Architecture (`celery_tasks/scraping_tasks.py`)
- **start_domain_scrape**: Orchestrates entire domain scraping workflow
- **process_cdx_records**: Converts CDX records to ScrapePage entries
- **extract_and_index_page**: Processes individual pages with hybrid extraction
- **Task Configuration**: Uses `task_acks_late`, `task_time_limit`, exponential backoff

### Circuit Breaker System (`circuit_breaker.py`)
Service-specific circuit breakers with different thresholds:
- **Wayback Machine**: 5 failures, 60s timeout (external dependency)
- **Meilisearch**: 3 failures, 30s timeout (local service)
- **Content Extraction**: 10 failures, 120s timeout (processing intensive)

### Smart Content Routing Logic
**Route to Firecrawl** (high-value content):
- Government/educational domains (`.gov`, `.edu`, `.org`, `.mil`)
- Large content (>1KB, likely articles)
- Research keywords (`research`, `report`, `analysis`, `study`, `whitepaper`)
- PDF files for enhanced extraction

**Route to BeautifulSoup** (standard content):
- Small files, CSS, JS, feeds
- Everything else for speed and efficiency

### WebSocket Progress Tracking (`websocket_service.py`)
Real-time updates for long-running scraping operations:
- CDX discovery progress
- Content extraction status
- Error notifications
- Completion statistics

## Important Notes

- Never add claude coauthorship to git commit messages
- Always use `docker compose` not `docker-compose`
- Never commit secrets or API keys
- Use async/await patterns in FastAPI routes
- Follow SQLModel patterns for database operations
- Use TypeScript strictly in frontend
- Use shadcn-svelte components and design patterns for all UI development
- Test both backend and frontend thoroughly
- Check code coverage requirements (80% minimum)
- Always run python and node, npm, uv commands etc. in docker
- **Hybrid extraction provides 22% quality improvement with zero additional costs**
- **Circuit breakers prevent cascade failures in scraping operations**
- **CDX resume state enables recovery from crashes in large scraping jobs**