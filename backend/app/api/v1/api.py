"""
Main API router that includes all v1 endpoints
"""
from fastapi import APIRouter

from app.api.v1.endpoints import (
    auth, users, projects, pages, health, password_reset, email_verification, 
    oauth2, rbac, tasks, monitoring, search, plans, library, entities, extraction_schemas, websocket, profile, entity_config, meilisearch_routes, batch_sync
)

api_router = APIRouter()

# Include all endpoint routers
api_router.include_router(health.router, prefix="/health", tags=["health"])
api_router.include_router(auth.router, prefix="/auth", tags=["authentication"])
api_router.include_router(password_reset.router, prefix="/auth/password-reset", tags=["password-reset"])
api_router.include_router(email_verification.router, prefix="/auth/email", tags=["email-verification"])
api_router.include_router(oauth2.router, prefix="/auth/oauth2", tags=["oauth2"])
api_router.include_router(rbac.router, prefix="/rbac", tags=["rbac"])
api_router.include_router(tasks.router, prefix="/tasks", tags=["tasks"])
api_router.include_router(monitoring.router, prefix="/monitoring", tags=["monitoring"])
api_router.include_router(users.router, prefix="/users", tags=["users"])
api_router.include_router(projects.router, prefix="/projects", tags=["projects"])
api_router.include_router(pages.router, prefix="/pages", tags=["pages"])
api_router.include_router(search.router, prefix="/search", tags=["search"])
api_router.include_router(plans.router, prefix="/plans", tags=["plans"])
api_router.include_router(library.router, prefix="/library", tags=["library"])
api_router.include_router(entities.router, prefix="/entities", tags=["entities"])
api_router.include_router(extraction_schemas.router, prefix="/extraction", tags=["extraction"])
api_router.include_router(entity_config.router, prefix="/users", tags=["entity-config"])
api_router.include_router(websocket.router, prefix="/ws", tags=["websocket"])
api_router.include_router(profile.router, prefix="/profile", tags=["profile"])
api_router.include_router(meilisearch_routes.router, prefix="/meilisearch", tags=["meilisearch"])
api_router.include_router(batch_sync.router, prefix="/batch-sync", tags=["batch-sync"])