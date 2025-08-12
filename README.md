# Chrono Scraper v2 - FastAPI + SvelteKit

Full-text indexing for the Wayback Machine, rebuilt with modern technologies.

## Tech Stack

### Backend
- **FastAPI** - Modern, fast web framework for building APIs
- **SQLModel** - SQL databases with Python type hints
- **Celery** - Distributed task queue
- **Redis** - Caching and message broker
- **PostgreSQL** - Primary database
- **Meilisearch** - Full-text search engine

### Frontend
- **SvelteKit 5** - Fast, modern web framework
- **Tailwind CSS** - Utility-first CSS framework
- **Shadcn-svelte** - Component library
- **D3.js** - Data visualization
- **InstantSearch.js** - Search UI components

## Quick Start

### Prerequisites
- Docker and Docker Compose
- Node.js 20+ (for local development)
- Python 3.11+ (for local development)

### Development Setup

1. Clone the repository:
```bash
git clone <repository-url>
cd chrono-scraper-fastapi-2
```

2. Copy environment variables:
```bash
cp .env.example .env
```

3. Start the development environment:
```bash
docker compose up
```

This will start:
- FastAPI backend with hot-reloading on http://localhost:8000
- SvelteKit frontend with hot-reloading on http://localhost:5173
- PostgreSQL database on port 5432
- Redis on port 6379
- Meilisearch on http://localhost:7700
- Flower (Celery monitoring) on http://localhost:5555
- Mailpit (email testing) on http://localhost:8025

### API Documentation

Once running, visit:
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## Project Structure

```
├── backend/              # FastAPI backend
│   ├── app/
│   │   ├── api/         # API endpoints
│   │   ├── core/        # Core functionality
│   │   ├── models/      # SQLModel models
│   │   ├── schemas/     # Pydantic schemas
│   │   ├── services/    # Business logic
│   │   └── tasks/       # Celery tasks
│   ├── tests/           # Backend tests
│   └── alembic/         # Database migrations
├── frontend/            # SvelteKit frontend
│   ├── src/
│   │   ├── routes/      # SvelteKit routes
│   │   ├── lib/         # Components and utilities
│   │   └── app.html     # HTML template
│   └── tests/           # Frontend tests
├── docker/              # Docker configurations
├── monitoring/          # Monitoring configs
└── docs/               # Documentation
```

## Development

### Backend Development

Run backend tests:
```bash
docker compose exec backend pytest
```

Format code:
```bash
docker compose exec backend black .
docker compose exec backend ruff check . --fix
```

Create database migration:
```bash
docker compose exec backend alembic revision --autogenerate -m "Description"
```

Apply migrations:
```bash
docker compose exec backend alembic upgrade head
```

### Frontend Development

Run frontend tests:
```bash
docker compose exec frontend npm test
```

Format code:
```bash
docker compose exec frontend npm run format
```

Build for production:
```bash
docker compose exec frontend npm run build
```

## Features

### Phase 1: Foundation ✅
- [x] FastAPI project structure
- [x] Docker with hot-reloading
- [x] SvelteKit 5 frontend
- [x] Development environment

### Phase 2: Core Models & Auth (In Progress)
- [ ] User authentication with JWT
- [ ] SQLModel database models
- [ ] Role-based access control
- [ ] Frontend auth pages

### Phase 3: Project Management
- [ ] Project CRUD operations
- [ ] Domain management
- [ ] Meilisearch integration
- [ ] Background tasks with Celery

### Phase 4: Scraping Engine
- [ ] Wayback Machine integration
- [ ] Firecrawl integration
- [ ] Progress tracking
- [ ] Proxy management

### Phase 5: Advanced Features
- [ ] Entity processing with spaCy
- [ ] Timeline visualizations
- [ ] OSINT investigations
- [ ] Collaboration features

### Phase 6: Search & Discovery
- [ ] Advanced search interface
- [ ] User library
- [ ] Public search
- [ ] API documentation

### Phase 7: Monitoring & Production
- [ ] Prometheus metrics
- [ ] Grafana dashboards
- [ ] Error tracking
- [ ] Production deployment

### Phase 8: Testing & Documentation
- [ ] Comprehensive test suite
- [ ] API documentation
- [ ] User guides
- [ ] CI/CD pipeline

## Deployment

See [DEPLOYMENT.md](docs/DEPLOYMENT.md) for production deployment instructions.

## Contributing

Please read [CONTRIBUTING.md](docs/CONTRIBUTING.md) for details on our code of conduct and the process for submitting pull requests.

## License

This project is licensed under the Hippocratic License - see the [LICENSE](LICENSE) file for details.

## Migration from Django

This is a complete rewrite of the original Django-based Chrono Scraper. For migration instructions, see [MIGRATION_PLAN.md](MIGRATION_PLAN.md).