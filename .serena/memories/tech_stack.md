# Tech Stack & Dependencies

## Backend (FastAPI)
- **FastAPI 0.115.5** - Modern, fast web framework for building APIs
- **SQLModel 0.0.22** - SQL databases with Python type hints
- **Uvicorn** - ASGI server with hot-reloading
- **Pydantic** - Data validation and serialization
- **Alembic** - Database migrations
- **AsyncPG/Psycopg2** - PostgreSQL async/sync drivers

### Task Processing & Search
- **Celery 5.4.0** with Redis - Distributed task queue
- **Redis 5.2.1** - Caching and message broker
- **Meilisearch-Python-Async** - Full-text search engine integration
- **Flower** - Celery monitoring

### Content Processing
- **HTTPX/aiohttp** - Async HTTP clients
- **BeautifulSoup4** - HTML parsing
- **Readability-lxml** - Content extraction
- **html2text/markdownify** - HTML to markdown conversion
- **spaCy** - NLP and entity processing

### Development & Testing
- **Pytest** - Testing framework with asyncio support
- **Black** - Code formatting
- **Ruff** - Fast Python linter
- **MyPy** - Type checking
- **Bandit** - Security testing
- **Coverage** - Test coverage (80% minimum required)

## Frontend (SvelteKit 5)
- **SvelteKit 5** - Fast, modern web framework with TypeScript
- **Vite** - Development server and build tool
- **Tailwind CSS 3.4.17** - Utility-first CSS framework
- **shadcn-svelte** - Component library (bits-ui, lucide-svelte)
- **Zod** - Schema validation

### Testing & Development
- **Vitest** - Unit and component tests
- **Playwright** - End-to-end testing
- **ESLint** - Code linting
- **Prettier** - Code formatting
- **TypeScript 5.7.2** - Type safety

### UI Components
- **bits-ui** - Headless UI components
- **lucide-svelte** - Icon library
- **mode-watcher** - Dark/light mode
- **svelte-sonner** - Toast notifications
- **tailwind-merge/tailwind-variants** - CSS utilities

## Infrastructure & Services
- **Docker Compose** - Multi-service development environment
- **PostgreSQL 17** - Primary database
- **Redis 7** - Cache and task queue
- **Meilisearch** - Search engine
- **Firecrawl** - Local content extraction services (API, Worker, Playwright)
- **Mailpit** - Email testing in development
- **Flower** - Task monitoring