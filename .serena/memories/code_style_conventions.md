# Code Style & Conventions

## Backend (Python/FastAPI) Conventions

### Code Formatting & Linting
- **Black** - Code formatting (line length: 88 chars)
- **Ruff** - Fast linting and import sorting
- **MyPy** - Type checking with strict mode
- **Bandit** - Security linting

### Python Style Guidelines
- **Type Hints**: Mandatory for all function signatures and class attributes
- **Async/Await**: Use async patterns throughout FastAPI routes and services
- **SQLModel**: Preferred ORM with Pydantic integration for type safety
- **Pydantic**: Use for data validation and serialization
- **Docstrings**: Use triple quotes for module and function documentation
- **Import Organization**: Use Ruff for automatic import sorting

### FastAPI Patterns
- **Route Organization**: Group endpoints in `/api/v1/endpoints/` modules
- **Dependency Injection**: Use FastAPI's dependency system for database, auth
- **Response Models**: Always define Pydantic response models
- **Error Handling**: Use HTTPException with proper status codes
- **Middleware**: Custom middleware in `app/core/middleware.py`

### Database Patterns
- **SQLModel**: Use for all database models with type annotations
- **Alembic**: Database migrations with descriptive messages
- **Async Operations**: Use async database operations throughout
- **Relationships**: Define relationships with SQLModel's relationship()

## Frontend (TypeScript/SvelteKit) Conventions

### Code Formatting & Linting
- **Prettier** - Code formatting with consistent style
- **ESLint** - TypeScript and Svelte linting
- **TypeScript** - Strict mode enabled for type safety

### SvelteKit 5 Patterns
- **Component Organization**: Use `$lib/components/` for reusable components
- **State Management**: SvelteKit's built-in stores for local state
- **Route Structure**: File-based routing in `src/routes/`
- **Form Validation**: Use Zod schemas for form validation
- **API Integration**: Use SvelteKit's load functions for data fetching

### UI/Styling Conventions
- **Tailwind CSS**: Utility-first approach, mobile-first responsive design
- **shadcn-svelte**: Use for all UI components following design patterns
- **Component Library**: Prefer shadcn-svelte components over custom implementations
- **Button Events**: Use `onclick` not `on:click` for shadcn Button components
- **Dark Mode**: Support via mode-watcher with system preference detection

### TypeScript Guidelines
- **Strict Mode**: Enabled with strict type checking
- **Interface Definition**: Define interfaces for all API responses
- **Type Imports**: Use type-only imports where appropriate
- **Zod Schemas**: Use for runtime type validation

## Testing Conventions

### Backend Testing
- **Pytest Markers**: Use `@pytest.mark.unit`, `@pytest.mark.integration`, `@pytest.mark.slow`
- **Coverage**: Minimum 80% required (`--cov-fail-under=80`)
- **Async Testing**: Use `pytest-asyncio` for async test functions
- **Test Structure**: Organize tests in `tests/` with descriptive names

### Frontend Testing
- **Vitest**: Unit and component testing
- **Playwright**: E2E testing with Docker support
- **Testing Library**: Use `@testing-library/svelte` for component tests

## Development Workflow
- **Docker-First**: All development commands run inside Docker containers
- **Hot Reloading**: Both backend and frontend support live reload
- **Environment Variables**: Use `.env` file for configuration
- **Git Conventions**: Descriptive commit messages, no Claude coauthorship
- **Code Quality**: Run linting and formatting before commits