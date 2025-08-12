# Chrono Scraper Migration Plan: Django to FastAPI + SvelteKit 5 + SQLModel

## Executive Summary

This document outlines a comprehensive plan to reimplement the Chrono Scraper project using a modern tech stack:
- **Backend**: FastAPI with SQLModel
- **Frontend**: SvelteKit 5 with Shadcn-svelte
- **Database**: PostgreSQL with SQLModel ORM
- **Search**: Meilisearch
- **Task Queue**: Celery with Redis
- **Monitoring**: Full monitoring stack (Prometheus, Grafana, Loki, etc.)
- **Development**: Hot-reloading for both backend and frontend

## Current Architecture Analysis

### Core Functionality
1. **Web Scraping System**
   - Wayback Machine integration via CDX toolkit
   - Firecrawl integration for content extraction
   - Parallel processing with circuit breakers
   - Proxy management for scraping

2. **Project Management**
   - User projects with domains and pages
   - Scrape session tracking
   - Status monitoring and progress tracking

3. **Search & Indexing**
   - Meilisearch for full-text search
   - Secure API key management
   - Index rebuilding capabilities

4. **Entity Processing**
   - Named entity recognition with spaCy
   - Entity linking to DBpedia/Wikidata
   - Timeline analysis and visualization

5. **User Management**
   - Authentication with django-allauth
   - User approval system
   - Plan-based feature access

6. **Advanced Features**
   - OSINT investigations
   - Timeline visualizations
   - Document processing (PDF, DOCX)
   - Content change analysis
   - Collaborative features

### Infrastructure Services
- PostgreSQL database
- Redis for caching and Celery
- Meilisearch for search
- Mailpit for email (dev)
- Monitoring stack (Prometheus, Grafana, Loki, GlitchTip, Uptime Kuma)
- Traefik for routing (production)

## Migration Phases

### Phase 1: Foundation Setup (Week 1)
**Goal**: Establish the basic project structure with hot-reloading

1. **Project Initialization**
   - Create FastAPI project structure
   - Setup SQLModel with PostgreSQL
   - Configure Alembic for migrations
   - Setup Poetry for dependency management

2. **Docker Configuration**
   - FastAPI container with uvicorn hot-reload
   - PostgreSQL container
   - Redis container
   - Meilisearch container
   - Mailpit container (dev)

3. **SvelteKit 5 Setup**
   - Initialize SvelteKit project
   - Configure Tailwind CSS
   - Setup Shadcn-svelte components
   - Configure Vite for hot-reloading
   - Setup API proxy to FastAPI

4. **Development Environment**
   - Docker Compose for local development
   - Hot-reloading for both backend and frontend
   - Environment variable management
   - Basic logging setup

**Deliverables**:
- Working development environment
- Basic project structure
- Hot-reloading functional
- Database connection established

### Phase 2: Core Models & Authentication (Week 2)
**Goal**: Implement core data models and authentication

1. **SQLModel Models**
   - User model with authentication
   - Project, Domain, Page models
   - API Configuration models
   - Plan and subscription models

2. **Authentication System**
   - JWT-based authentication with FastAPI
   - User registration and login
   - Password reset functionality
   - Email verification
   - OAuth2 support (GitHub, Google)

3. **Authorization**
   - Role-based access control
   - Project ownership verification
   - API key management
   - Rate limiting implementation

4. **Frontend Auth**
   - Login/Register pages with Shadcn-svelte
   - Protected routes in SvelteKit
   - JWT token management
   - User profile pages

**Deliverables**:
- Complete authentication system
- Core database models
- User management functionality
- Protected API endpoints

### Phase 3: Project Management & CRUD (Week 3)
**Goal**: Implement project management features

1. **API Endpoints**
   - Project CRUD operations
   - Domain management
   - Page management
   - Bulk operations support

2. **Frontend Components**
   - Project list view
   - Project creation wizard
   - Project detail view
   - Domain management interface
   - Real-time updates with WebSockets

3. **Meilisearch Integration**
   - Index management
   - Search API endpoints
   - Secure key generation
   - Index rebuilding tasks

4. **Background Tasks**
   - Celery integration with FastAPI
   - Task monitoring
   - Progress tracking
   - Error handling

**Deliverables**:
- Complete project management system
- Meilisearch integration
- Background task processing
- Real-time updates

### Phase 4: Scraping Engine (Week 4-5)
**Goal**: Implement the web scraping functionality

1. **Scraping Services**
   - CDX API integration
   - Wayback Machine fetching
   - Firecrawl integration
   - Document processing

2. **Scrape Management**
   - Scrape session tracking
   - Progress monitoring
   - Error recovery
   - Circuit breakers

3. **Proxy Management**
   - Proxy rotation
   - Rate limiting
   - Error handling
   - Performance monitoring

4. **Frontend Scraping UI**
   - Scrape initiation interface
   - Progress visualization
   - Error reporting
   - Scrape history

**Deliverables**:
- Complete scraping engine
- Proxy management system
- Progress tracking UI
- Error recovery mechanisms

### Phase 5: Advanced Features (Week 6-7)
**Goal**: Implement entity processing and advanced features

1. **Entity Processing**
   - spaCy integration
   - Named entity recognition
   - Entity linking services
   - Entity storage and retrieval

2. **Timeline Features**
   - Timeline data models
   - Timeline API endpoints
   - D3.js visualizations
   - Timeline analysis tools

3. **OSINT Features**
   - Investigation management
   - Pattern analysis
   - Website ownership tracking
   - Content change detection

4. **Collaboration**
   - Project sharing
   - Public search configs
   - Collaborative editing
   - Activity feeds

**Deliverables**:
- Entity processing pipeline
- Timeline visualizations
- OSINT tools
- Collaboration features

### Phase 6: Search & Discovery (Week 8)
**Goal**: Implement advanced search features

1. **Search Interface**
   - InstantSearch.js integration
   - Advanced search builder
   - Faceted search
   - Search history

2. **User Library**
   - Saved searches
   - Starred items
   - Collections
   - Export functionality

3. **Public Features**
   - Public project search
   - Shared configurations
   - Embed widgets
   - API documentation

**Deliverables**:
- Advanced search interface
- User library features
- Public search capabilities
- API documentation

### Phase 7: Monitoring & Production (Week 9)
**Goal**: Setup monitoring and prepare for production

1. **Monitoring Stack**
   - Prometheus metrics
   - Grafana dashboards
   - Loki log aggregation
   - Alertmanager setup
   - Custom application metrics

2. **Error Tracking**
   - Sentry/GlitchTip integration
   - Error reporting
   - Performance monitoring
   - User feedback system

3. **Production Configuration**
   - Docker production builds
   - Traefik configuration
   - SSL/TLS setup
   - Backup strategies
   - Security hardening

4. **Performance Optimization**
   - Database indexing
   - Query optimization
   - Caching strategies
   - CDN setup
   - Load testing

**Deliverables**:
- Complete monitoring stack
- Production-ready configuration
- Performance optimizations
- Security hardening

### Phase 8: Testing & Documentation (Week 10)
**Goal**: Comprehensive testing and documentation

1. **Backend Testing**
   - Unit tests with pytest
   - Integration tests
   - API testing
   - Performance testing

2. **Frontend Testing**
   - Component tests with Vitest
   - E2E tests with Playwright
   - Visual regression testing
   - Accessibility testing

3. **Documentation**
   - API documentation with OpenAPI
   - User documentation
   - Developer documentation
   - Deployment guides

4. **CI/CD Pipeline**
   - GitHub Actions setup
   - Automated testing
   - Docker image building
   - Deployment automation

**Deliverables**:
- Comprehensive test suite
- Complete documentation
- CI/CD pipeline
- Deployment automation

## Technology Stack Details

### Backend Stack
```python
# Core
fastapi = "^0.115.0"
sqlmodel = "^0.0.22"
uvicorn = { extras = ["standard"], version = "^0.32.0" }
pydantic-settings = "^2.5.0"

# Database
alembic = "^1.13.0"
asyncpg = "^0.30.0"
psycopg2-binary = "^2.9.0"

# Authentication
python-jose = { extras = ["cryptography"], version = "^3.3.0" }
passlib = { extras = ["bcrypt"], version = "^1.7.0" }
python-multipart = "^0.0.0"

# Task Queue
celery = { extras = ["redis"], version = "^5.4.0" }
redis = "^5.0.0"
flower = "^2.0.0"

# Search
meilisearch = "^0.36.0"

# Scraping
httpx = "^0.27.0"
beautifulsoup4 = "^4.12.0"
firecrawl-py = "^2.16.0"

# Entity Processing
spacy = "^3.7.0"
spacy-entity-linker = "^1.0.0"

# Monitoring
prometheus-client = "^0.21.0"
opentelemetry-api = "^1.28.0"
opentelemetry-instrumentation-fastapi = "^0.50.0"

# Development
pytest = "^8.3.0"
pytest-asyncio = "^0.24.0"
black = "^24.10.0"
ruff = "^0.8.0"
mypy = "^1.13.0"
```

### Frontend Stack
```json
{
  "dependencies": {
    "@sveltejs/kit": "^2.0.0",
    "svelte": "^5.0.0",
    "tailwindcss": "^3.4.0",
    "shadcn-svelte": "^0.9.0",
    "bits-ui": "^0.21.0",
    "lucide-svelte": "^0.400.0",
    "d3": "^7.9.0",
    "@meilisearch/instant-meilisearch": "^0.14.0",
    "instantsearch.js": "^4.64.0"
  },
  "devDependencies": {
    "vite": "^5.0.0",
    "@playwright/test": "^1.40.0",
    "vitest": "^1.0.0",
    "@testing-library/svelte": "^4.0.0"
  }
}
```

## File Structure

```
chrono-scraper-fastapi/
├── backend/
│   ├── app/
│   │   ├── api/
│   │   │   ├── v1/
│   │   │   │   ├── auth.py
│   │   │   │   ├── projects.py
│   │   │   │   ├── scraping.py
│   │   │   │   ├── search.py
│   │   │   │   └── entities.py
│   │   │   └── deps.py
│   │   ├── core/
│   │   │   ├── config.py
│   │   │   ├── security.py
│   │   │   └── celery.py
│   │   ├── models/
│   │   │   ├── user.py
│   │   │   ├── project.py
│   │   │   ├── scraping.py
│   │   │   └── entities.py
│   │   ├── schemas/
│   │   │   ├── user.py
│   │   │   ├── project.py
│   │   │   └── common.py
│   │   ├── services/
│   │   │   ├── scraping.py
│   │   │   ├── meilisearch.py
│   │   │   ├── entities.py
│   │   │   └── timeline.py
│   │   ├── tasks/
│   │   │   ├── scraping.py
│   │   │   ├── indexing.py
│   │   │   └── monitoring.py
│   │   └── main.py
│   ├── tests/
│   ├── alembic/
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/
│   ├── src/
│   │   ├── routes/
│   │   │   ├── +layout.svelte
│   │   │   ├── +page.svelte
│   │   │   ├── auth/
│   │   │   ├── projects/
│   │   │   └── search/
│   │   ├── lib/
│   │   │   ├── components/
│   │   │   ├── stores/
│   │   │   └── utils/
│   │   └── app.html
│   ├── static/
│   ├── tests/
│   ├── package.json
│   ├── vite.config.js
│   └── Dockerfile
├── docker/
│   ├── compose/
│   │   ├── local.yml
│   │   ├── production.yml
│   │   └── monitoring.yml
│   └── nginx/
├── monitoring/
│   ├── prometheus/
│   ├── grafana/
│   └── loki/
├── scripts/
├── docs/
└── .github/
    └── workflows/
```

## Deployment Strategy

### Hosting Recommendations

1. **Primary Option: Hetzner Cloud**
   - VPS: CPX41 or higher
   - Managed Database: PostgreSQL
   - Object Storage: For backups
   - Load Balancer: For scaling
   - **Pros**: Cost-effective, European data centers, good performance
   - **Cons**: Manual setup required

2. **Alternative: DigitalOcean**
   - App Platform for easy deployment
   - Managed PostgreSQL
   - Spaces for object storage
   - **Pros**: Easy deployment, good developer experience
   - **Cons**: More expensive than Hetzner

3. **Enterprise: AWS/GCP**
   - ECS/GKE for container orchestration
   - RDS/Cloud SQL for database
   - S3/GCS for storage
   - **Pros**: Scalability, enterprise features
   - **Cons**: Complex, expensive

### CI/CD Pipeline

```yaml
# .github/workflows/main.yml
name: CI/CD Pipeline

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main]

jobs:
  test-backend:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      - name: Install dependencies
        run: |
          pip install poetry
          poetry install
      - name: Run tests
        run: poetry run pytest
      - name: Run linting
        run: |
          poetry run ruff check .
          poetry run mypy .

  test-frontend:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Setup Node
        uses: actions/setup-node@v3
        with:
          node-version: '20'
      - name: Install dependencies
        run: |
          cd frontend
          npm ci
      - name: Run tests
        run: |
          cd frontend
          npm run test:run
      - name: Run E2E tests
        run: |
          cd frontend
          npx playwright install
          npm run test:e2e

  build-and-push:
    needs: [test-backend, test-frontend]
    runs-on: ubuntu-latest
    if: github.ref == 'refs/heads/main'
    steps:
      - uses: actions/checkout@v3
      - name: Build and push Docker images
        run: |
          docker build -t myregistry/chrono-backend:latest ./backend
          docker build -t myregistry/chrono-frontend:latest ./frontend
          docker push myregistry/chrono-backend:latest
          docker push myregistry/chrono-frontend:latest

  deploy:
    needs: build-and-push
    runs-on: ubuntu-latest
    if: github.ref == 'refs/heads/main'
    steps:
      - name: Deploy to production
        run: |
          ssh user@server 'cd /app && docker-compose pull && docker-compose up -d'
```

## Testing Strategy

### Backend Testing
1. **Unit Tests** (70% coverage target)
   - Model tests
   - Service tests
   - API endpoint tests

2. **Integration Tests**
   - Database operations
   - External API calls
   - Celery task execution

3. **Performance Tests**
   - Load testing with Locust
   - Database query performance
   - API response times

### Frontend Testing
1. **Component Tests**
   - Vitest for unit tests
   - Testing Library for component tests

2. **E2E Tests**
   - Playwright for browser automation
   - Critical user flows
   - Cross-browser testing

3. **Visual Tests**
   - Percy or Chromatic for visual regression
   - Responsive design testing

## Migration Execution Plan

### Pre-Migration Checklist
- [ ] Backup existing database
- [ ] Document all environment variables
- [ ] Export Meilisearch indexes
- [ ] Save user data and configurations
- [ ] Create rollback plan

### Migration Steps
1. **Data Migration**
   - Export data from Django models
   - Transform to SQLModel schema
   - Import into new database
   - Verify data integrity

2. **Search Index Migration**
   - Export Meilisearch data
   - Recreate indexes
   - Import documents
   - Test search functionality

3. **User Migration**
   - Export user accounts
   - Migrate authentication data
   - Reset passwords if needed
   - Verify login functionality

4. **Content Migration**
   - Migrate scraped content
   - Preserve timestamps
   - Maintain relationships
   - Verify data access

### Post-Migration Validation
- [ ] All users can login
- [ ] Projects are accessible
- [ ] Search returns results
- [ ] Scraping functions work
- [ ] Monitoring is operational
- [ ] Backups are configured

## Risk Management

### Technical Risks
1. **Data Loss**
   - Mitigation: Comprehensive backups, gradual migration
2. **Performance Degradation**
   - Mitigation: Load testing, optimization phase
3. **Feature Parity**
   - Mitigation: Detailed feature mapping, user acceptance testing

### Business Risks
1. **Downtime**
   - Mitigation: Blue-green deployment, maintenance window
2. **User Disruption**
   - Mitigation: Communication plan, training materials
3. **Cost Overrun**
   - Mitigation: Phased approach, regular review

## Success Criteria

### Technical Metrics
- API response time < 200ms (p95)
- Page load time < 2s
- Test coverage > 70%
- Zero critical security vulnerabilities
- 99.9% uptime

### Business Metrics
- All existing features migrated
- User satisfaction maintained/improved
- Successful data migration (100%)
- Documentation complete
- Team trained on new stack

## Timeline Summary

- **Week 1**: Foundation Setup
- **Week 2**: Core Models & Authentication
- **Week 3**: Project Management & CRUD
- **Week 4-5**: Scraping Engine
- **Week 6-7**: Advanced Features
- **Week 8**: Search & Discovery
- **Week 9**: Monitoring & Production
- **Week 10**: Testing & Documentation

**Total Duration**: 10 weeks

## Next Steps

1. Review and approve this plan
2. Set up development environment
3. Begin Phase 1 implementation
4. Schedule weekly progress reviews
5. Adjust timeline based on progress

---

This migration plan provides a structured approach to reimplementing Chrono Scraper with modern technologies while maintaining all existing functionality and improving developer experience with hot-reloading and better tooling.