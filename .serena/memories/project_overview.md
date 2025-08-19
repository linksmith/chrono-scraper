# Chrono Scraper v2 - Project Overview

## Purpose
Chrono Scraper v2 is a production-ready Wayback Machine scraping platform built with FastAPI + SvelteKit. It provides comprehensive web scraping, content extraction, entity processing, and full-text search capabilities specifically designed for OSINT investigations and historical research.

## Architecture
- **Backend**: FastAPI with async/await patterns, SQLModel for type-safe database operations
- **Frontend**: SvelteKit 5 with TypeScript, Tailwind CSS with shadcn-svelte components
- **Database**: PostgreSQL with Alembic migrations
- **Search**: Meilisearch for full-text search indexing
- **Task Queue**: Celery with Redis for distributed background processing
- **Content Extraction**: Firecrawl-only approach with local services for high-quality extraction
- **Development**: Docker Compose with hot-reloading for all services

## Key Features
- **Intelligent Scraping**: CDX API integration with 47 list page pattern filtering
- **Content Processing**: Firecrawl-based extraction with digest deduplication
- **Circuit Breakers**: Service reliability and fault tolerance
- **Real-time Updates**: WebSocket-based progress tracking
- **Email System**: Mailgun (production) + SMTP/Mailpit (development) fallback
- **Authentication**: JWT with refresh tokens and professional user verification

## Migration Context
This is a complete rewrite from a Django-based system, modernized with:
- FastAPI async/await instead of Django sync
- SQLModel instead of Django ORM  
- Pydantic for serialization instead of Django REST Framework
- SvelteKit instead of Django templates
- Component-based frontend instead of server-rendered templates