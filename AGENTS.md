# AGENTS.md - Development Guidelines for AI Coding Agents

## Commands
- **Single test**: `docker compose exec backend pytest tests/test_specific.py::test_function -v`
- **Backend tests**: `make test-backend` or `docker compose exec backend pytest tests/ -v --cov=app`
- **Frontend tests**: `make test-frontend` or `docker compose exec frontend npm test`
- **Lint**: `make lint` (runs both backend ruff/black/mypy and frontend eslint)
- **Format**: `make format-backend && make format-frontend`

## Code Style
- **Backend**: Use async/await, SQLModel patterns, type hints everywhere, ruff+black formatting
- **Frontend**: TypeScript strict mode, Svelte 5 syntax, Tailwind CSS, shadcn-svelte components
- **Imports**: Absolute imports preferred (`from app.models.user import User`), group stdlib/3rd-party/local
- **Naming**: snake_case (Python), camelCase (TypeScript), PascalCase (classes/components)
- **Error handling**: Use HTTPException with status codes, proper async exception handling
- **Types**: Use SQLModel for DB models, Pydantic for schemas, TypeScript interfaces for frontend
- **Comments**: Only add when complex logic requires explanation, prefer self-documenting code

## Architecture
- FastAPI + SQLModel + PostgreSQL + Redis + Meilisearch + SvelteKit 5 stack
- Always use `docker compose` commands, never `docker-compose`
- Use shadcn-svelte UI components, `onclick` (not `on:click`) for buttons
- Follow existing patterns in models/, services/, api/endpoints/ structure
- Always verify users are `is_verified=true AND approval_status='approved'` for auth tests