# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Chrono Scraper v2 is a full-text indexing application for the Wayback Machine, rebuilt with FastAPI + SvelteKit. It provides web scraping, data collection, entity extraction, and search capabilities for OSINT investigations and research.

## Architecture

### Backend (FastAPI)
- **FastAPI** with SQLModel for type-safe database operations
- **PostgreSQL** primary database with Alembic migrations
- **Celery** with Redis for background task processing
- **Meilisearch** for full-text search
- **Pydantic Settings** for environment-based configuration

### Frontend (SvelteKit 5)
- **SvelteKit 5** with TypeScript
- **Tailwind CSS** with shadcn-svelte components
- **Vite** for development and building

### Infrastructure
- **Docker Compose** for development environment
- **Firecrawl** services (API, worker, playwright) for web scraping
- **Redis** for caching and task queues
- **Mailpit** for email testing

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

# Run specific test file
docker compose exec backend pytest tests/test_auth.py

# Run tests with markers
docker compose exec backend pytest -m "unit"
docker compose exec backend pytest -m "integration"

# Format code
docker compose exec backend black .
docker compose exec backend ruff check . --fix

# Database migrations
docker compose exec backend alembic revision --autogenerate -m "Description"
docker compose exec backend alembic upgrade head

# Interactive Python shell with app context
docker compose exec backend python -c "from app.main import app; import IPython; IPython.embed()"
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

The application uses a comprehensive model system with the following key entities:

### Core Models
- **User**: Authentication, professional verification, approval workflow
- **Project**: Web scraping projects with domain management
- **Page**: Individual scraped pages with content and metadata
- **Domain**: Domain-specific scraping configuration

### Advanced Features
- **ContentExtractionSchema**: Custom data extraction templates
- **CanonicalEntity**: Entity linking and knowledge graph
- **Investigation**: OSINT investigation workflow
- **UserApproval**: LLM-based user verification system
- **ProjectShare**: Collaboration and public access

### Authentication & Authorization
- JWT-based authentication with refresh tokens
- Role-based access control (RBAC)
- Professional user verification with LLM evaluation
- API key management for programmatic access

## Database

### Connection
- Development: `postgresql://chrono_scraper:chrono_scraper_dev@localhost:5435/chrono_scraper`
- All models use SQLModel with automatic Pydantic serialization
- Alembic handles schema migrations

### Key Relationships
- Users have many Projects
- Projects have many Domains and Pages
- Pages can have ContentExtractions and EntityMentions
- Projects can be shared with ProjectShare
- Users can have approval workflows with UserEvaluation

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
- `POSTGRES_*` - Database connection
- `REDIS_HOST` - Redis connection
- `MEILISEARCH_*` - Search engine config
- `SECRET_KEY` - JWT signing key
- `OPENAI_API_KEY` - LLM integration for user approval

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