# Codebase Structure & Architecture

## Project Root Structure
```
chrono-scraper-fastapi-2/
├── backend/              # FastAPI backend application
├── frontend/             # SvelteKit frontend application  
├── external/             # External service configurations
├── monitoring/           # Monitoring and observability configs
├── scripts/              # Deployment and utility scripts
├── docs/                 # Project documentation
├── traefik/              # Reverse proxy configuration
├── docker-compose.yml    # Development environment
├── docker-compose.production.yml  # Production environment
├── Makefile              # Development commands
├── CLAUDE.md             # Project-specific Claude instructions
└── README.md             # Project overview
```

## Backend Structure (`backend/`)
```
backend/
├── app/
│   ├── api/              # API layer
│   │   └── v1/
│   │       ├── api.py    # Main API router
│   │       └── endpoints/# Individual endpoint modules
│   ├── core/             # Core functionality
│   │   ├── config.py     # Pydantic settings
│   │   ├── database.py   # Database connection
│   │   ├── middleware.py # Custom middleware
│   │   └── security.py   # Auth & security
│   ├── models/           # SQLModel database models
│   │   ├── __init__.py   # Model exports
│   │   ├── user.py       # User models
│   │   ├── project.py    # Project models
│   │   └── scraping.py   # Scraping workflow models
│   ├── schemas/          # Pydantic request/response schemas
│   ├── services/         # Business logic services
│   │   ├── auth_service.py
│   │   ├── firecrawl_extractor.py
│   │   ├── wayback_machine.py
│   │   ├── meilisearch_service.py
│   │   └── intelligent_filter.py
│   ├── tasks/            # Celery background tasks
│   │   ├── celery_app.py # Main Celery configuration
│   │   ├── firecrawl_scraping.py  # Primary scraping tasks
│   │   └── scraping_simple.py     # Retry tasks
│   └── main.py           # FastAPI application entry point
├── tests/                # Backend test suite
├── alembic/              # Database migrations
├── requirements.txt      # Python dependencies
├── pytest.ini           # Test configuration
└── Dockerfile.dev        # Development container
```

## Frontend Structure (`frontend/`)
```
frontend/
├── src/
│   ├── routes/           # SvelteKit file-based routing
│   │   ├── +layout.svelte # Global layout
│   │   ├── +page.svelte   # Home page
│   │   ├── auth/          # Authentication pages
│   │   ├── projects/      # Project management
│   │   ├── search/        # Search interface
│   │   └── library/       # User library
│   ├── lib/              # Reusable components and utilities
│   │   ├── components/    # Svelte components
│   │   │   ├── ui/        # shadcn-svelte components
│   │   │   ├── auth/      # Auth-specific components
│   │   │   ├── search/    # Search components
│   │   │   └── common/    # Shared components
│   │   ├── stores/        # Svelte stores for state
│   │   ├── utils/         # Utility functions
│   │   └── types/         # TypeScript type definitions
│   ├── app.html          # HTML template
│   └── app.css           # Global styles
├── static/               # Static assets
├── tests/                # Frontend tests
├── package.json          # Node.js dependencies and scripts
├── svelte.config.js      # SvelteKit configuration
├── vite.config.ts        # Vite build configuration
├── tailwind.config.js    # Tailwind CSS configuration
├── tsconfig.json         # TypeScript configuration
├── vitest.config.ts      # Vitest test configuration
└── playwright.config.ts  # E2E test configuration
```

## Key Architecture Components

### Model Architecture (Dual-Layer)
**Application Models** (`app/models/`):
- `User` - Authentication, professional verification
- `Project` - Web scraping projects with domains
- `PageV2` - Shared pages with UUID keys for multi-project search
- `ProjectPage` - Junction table for project-specific metadata (tags, review status, notes)
- `Domain` - Domain-specific scraping configuration

**Scraping Workflow Models** (`app/models/scraping.py`):
- `ScrapePage` - Individual scraping operations
- `CDXResumeState` - Crash recovery state
- `ScrapeSession` - Batch scraping sessions
- `PageErrorLog` - Error tracking with retry logic

### Service Layer (`app/services/`)
- **Firecrawl Extractor** - Content extraction service
- **Wayback Machine** - CDX API client with intelligent filtering
- **Meilisearch Service** - Full-text search indexing
- **Intelligent Filter** - 47 list page patterns, digest deduplication
- **Auth Service** - JWT authentication and user management

### API Structure (`app/api/v1/endpoints/`)
- `/auth/*` - Authentication and user management
- `/projects/*` - Project and domain management
- `/shared-pages/*` - Shared page management and multi-project operations
- `/search/*` - Full-text search with Meilisearch
- `/tasks/*` - Background task management
- `/ws/*` - WebSocket connections for real-time updates

### Task Processing (`app/tasks/`)
- **Consolidated Celery Configuration** - Single `celery_app.py`
- **Primary Tasks** - `firecrawl_scraping.py` for domain scraping
- **Retry Tasks** - `scraping_simple.py` for simplified retries
- **Shared Models** - `extraction_data.py` for content structures

## Development Environment Services
- **Backend** - FastAPI on port 8000
- **Frontend** - SvelteKit on port 5173  
- **PostgreSQL** - Database on port 5435
- **Redis** - Cache/queue on port 6379
- **Meilisearch** - Search on port 7700
- **Firecrawl API** - Content extraction on port 3002
- **Firecrawl Playwright** - Browser automation on port 3000
- **Flower** - Celery monitoring on port 5555
- **Mailpit** - Email testing on port 8025

## Configuration Files
- **Backend**: `app/core/config.py` - Pydantic settings
- **Frontend**: Multiple config files (svelte.config.js, vite.config.ts, etc.)
- **Database**: `alembic.ini` - Migration configuration
- **Docker**: `docker-compose.yml` - Service orchestration
- **Testing**: `pytest.ini`, `vitest.config.ts` - Test configurations