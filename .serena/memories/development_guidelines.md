# Development Guidelines & Best Practices

## Core Development Principles

### Docker-First Development
- **All commands run inside Docker containers** - Never run Python, Node, or database commands locally
- **Use `docker compose` not `docker-compose`** - Modern Docker Compose syntax
- **Hot-reloading enabled** - Both backend and frontend support live code changes
- **Persistent volumes** - Database and cache data persists between container restarts

### Code Quality Standards
- **80% test coverage minimum** - Required for backend code (`--cov-fail-under=80`)
- **Type safety enforced** - MyPy for Python, TypeScript strict mode for frontend
- **Consistent formatting** - Black for Python, Prettier for TypeScript/Svelte
- **Security-first** - Bandit security scanning, no secrets in code

## Architecture Patterns

### Backend (FastAPI) Patterns
- **Async-first** - Use `async/await` throughout FastAPI routes and services
- **Dependency Injection** - Use FastAPI's dependency system for database, auth
- **Type-safe database** - SQLModel with Pydantic integration
- **Circuit breakers** - Service reliability for external dependencies
- **Middleware approach** - Custom middleware for security, validation, timeouts

### Frontend (SvelteKit) Patterns
- **Component-based** - Use shadcn-svelte components following design patterns
- **TypeScript strict** - All components and utilities fully typed
- **Stores for state** - SvelteKit's built-in stores, avoid complex state managers
- **Mobile-first responsive** - Tailwind CSS utility-first approach
- **Form validation** - Zod schemas for runtime validation

### Database Patterns
- **SQLModel everywhere** - Type-safe ORM with automatic Pydantic serialization
- **Alembic migrations** - All schema changes via migrations with descriptive messages
- **Dual model architecture** - Application models + scraping workflow models
- **Async operations** - Use async database operations throughout

## API Design Guidelines

### RESTful Conventions
- **Consistent URL structure** - `/api/v1/resource/` pattern
- **HTTP methods** - GET, POST, PUT, DELETE with proper status codes
- **Pydantic schemas** - Request/response validation with clear models
- **Error handling** - Consistent error response format with HTTPException

### Authentication & Security
- **JWT with refresh tokens** - Secure token rotation
- **Role-based access control** - Professional user verification
- **Input validation** - Pydantic validation on all inputs
- **Security headers** - Custom middleware for security headers

## Testing Strategy

### Backend Testing
- **Pytest markers** - `@pytest.mark.unit`, `@pytest.mark.integration`, `@pytest.mark.slow`
- **Async testing** - Use `pytest-asyncio` for async test functions
- **Database isolation** - Each test gets clean database state
- **Mock external services** - Don't hit real Wayback Machine, Firecrawl in tests

### Frontend Testing
- **Unit tests** - Vitest for component and utility testing
- **E2E tests** - Playwright for full user workflows
- **Component testing** - Testing Library for Svelte components
- **Visual regression** - Playwright screenshots for UI changes

## Scraping System Guidelines

### Firecrawl-Only Architecture
- **Local Firecrawl services** - Use containerized services, not cloud API
- **Intelligent filtering** - 47 list page patterns reduce load by 70%+
- **Digest deduplication** - Skip unchanged content automatically
- **Circuit breakers** - Prevent cascade failures in scraping operations

### Task Processing
- **Single Celery config** - Use `app/tasks/celery_app.py` only
- **Primary + retry tasks** - `firecrawl_scraping.py` primary, `scraping_simple.py` retries
- **WebSocket progress** - Real-time updates for long-running operations
- **Resume capability** - CDX resume state for crash recovery

## Git & Deployment Practices

### Version Control
- **Descriptive commits** - Clear, single-feature commits
- **No Claude coauthorship** - Never add Claude as coauthor in commits
- **Branch protection** - Don't commit directly to main
- **Clean history** - Squash related commits before merging

### Environment Management
- **Environment variables** - Use `.env` for all configuration
- **Development/production parity** - Same Docker images, different configs
- **Secret management** - Never commit API keys or passwords
- **Service health checks** - Built into Docker Compose

## Performance Guidelines

### Backend Performance
- **Async operations** - Use async/await for I/O operations
- **Connection pooling** - PostgreSQL and Redis connection pools
- **Caching strategy** - Redis for frequent queries and session data
- **Background tasks** - Use Celery for time-consuming operations

### Frontend Performance
- **Code splitting** - Vite automatic code splitting
- **Lazy loading** - Load components and routes on demand
- **Optimistic updates** - Update UI immediately, sync in background
- **Bundle analysis** - Monitor build size with `npm run build -- --analyze`

## Error Handling & Monitoring

### Error Management
- **Structured logging** - Use consistent log formats
- **Circuit breakers** - Fail fast and recover gracefully
- **Error tracking** - Comprehensive error logs with retry logic
- **User feedback** - Clear error messages in UI

### Monitoring & Observability
- **Health endpoints** - `/health` endpoints for all services
- **Celery monitoring** - Flower dashboard for task monitoring
- **Search metrics** - Meilisearch performance tracking
- **Email testing** - Mailpit for development email verification

## Design System Guidelines

### UI/UX Consistency
- **shadcn-svelte components** - Use design system components exclusively
- **Dark/light mode** - Support system preference detection
- **Accessibility** - ARIA labels, keyboard navigation
- **Responsive design** - Mobile-first with Tailwind breakpoints

### Component Architecture
- **Reusable components** - Build once, use everywhere
- **Props interface** - Clear TypeScript interfaces for all props
- **Event handling** - Use `onclick` not `on:click` for shadcn Button components
- **State management** - Keep component state local when possible