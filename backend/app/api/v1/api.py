"""
Main API router that includes all v1 endpoints
"""
from fastapi import APIRouter

from app.api.v1.endpoints import (
    auth, users, projects, health, password_reset, email_verification, 
    oauth2, rbac, tasks, monitoring, search, plans, library, entities, extraction_schemas, websocket, profile, entity_config, meilisearch_routes, batch_sync, invitations, user_approval, sharing_secure, rate_limit_monitoring, key_health_dashboard, key_usage_analytics, shared_pages, dashboard, admin_settings, admin_users, admin_api, admin_dashboard, alert_api, scrape_pages, parquet_pipeline, hybrid_query_router_api, analytics, analytics_websocket, analytics_export, query_optimization, archive_source
    # backup_api, # Backup system disabled - requires SQLAlchemy model fix
)
from app.api.v1 import security

api_router = APIRouter()

# Include all endpoint routers
api_router.include_router(health.router, prefix="/health", tags=["health"])
api_router.include_router(auth.router, prefix="/auth", tags=["authentication"])
api_router.include_router(password_reset.router, prefix="/auth/password-reset", tags=["password-reset"])
api_router.include_router(email_verification.router, prefix="/auth/email", tags=["email-verification"])
api_router.include_router(oauth2.router, prefix="/auth/oauth2", tags=["oauth2"])
api_router.include_router(invitations.router, prefix="/invitations", tags=["invitations"])
api_router.include_router(rbac.router, prefix="/rbac", tags=["rbac"])
api_router.include_router(tasks.router, prefix="/tasks", tags=["tasks"])
api_router.include_router(monitoring.router, prefix="/monitoring", tags=["monitoring"])
api_router.include_router(users.router, prefix="/users", tags=["users"])
api_router.include_router(projects.router, prefix="/projects", tags=["projects"])
api_router.include_router(scrape_pages.router, prefix="/projects", tags=["scrape-pages"])
api_router.include_router(archive_source.router, prefix="/projects", tags=["archive-sources"])
api_router.include_router(shared_pages.router, prefix="/shared-pages", tags=["shared-pages"])
api_router.include_router(search.router, prefix="/search", tags=["search"])
api_router.include_router(plans.router, prefix="/plans", tags=["plans"])
api_router.include_router(library.router, prefix="/library", tags=["library"])
api_router.include_router(entities.router, prefix="/entities", tags=["entities"])
api_router.include_router(extraction_schemas.router, prefix="/extraction", tags=["extraction"])
api_router.include_router(entity_config.router, prefix="/users", tags=["entity-config"])
api_router.include_router(websocket.router, prefix="/ws", tags=["websocket"])
api_router.include_router(profile.router, prefix="/profile", tags=["profile"])
api_router.include_router(meilisearch_routes.router, prefix="/meilisearch", tags=["meilisearch"])
api_router.include_router(sharing_secure.router, prefix="/sharing", tags=["sharing"])
api_router.include_router(rate_limit_monitoring.router, prefix="/monitoring", tags=["rate-limiting"])
api_router.include_router(key_health_dashboard.router, prefix="/monitoring", tags=["key-health"])
api_router.include_router(key_usage_analytics.router, prefix="/monitoring", tags=["analytics"])
api_router.include_router(batch_sync.router, prefix="/batch-sync", tags=["batch-sync"])
api_router.include_router(user_approval.router, tags=["admin", "user-approval"])
api_router.include_router(admin_settings.router, prefix="/admin", tags=["admin", "settings"])
api_router.include_router(admin_users.router, prefix="/admin", tags=["admin", "users"])
api_router.include_router(admin_api.router, prefix="/admin/api", tags=["admin-api"])
api_router.include_router(admin_dashboard.router, prefix="/admin", tags=["admin-dashboard"])
api_router.include_router(dashboard.router, prefix="/dashboard", tags=["dashboard"])
# api_router.include_router(backup_api.router, prefix="/backup", tags=["backup", "recovery"])  # Disabled
api_router.include_router(alert_api.router, prefix="/alerts", tags=["alerts", "monitoring"])
api_router.include_router(parquet_pipeline.router, prefix="/parquet", tags=["parquet", "analytics"])
api_router.include_router(hybrid_query_router_api.router, prefix="/hybrid-query", tags=["hybrid-query", "database-routing"])
api_router.include_router(analytics.router, prefix="/analytics", tags=["analytics", "insights"])
api_router.include_router(analytics_websocket.router, prefix="/analytics", tags=["analytics", "websocket", "real-time"])
api_router.include_router(analytics_export.router, prefix="/analytics", tags=["analytics", "export"])
api_router.include_router(query_optimization.router, prefix="/optimization", tags=["optimization", "performance", "cache"])
api_router.include_router(security.router, prefix="/security", tags=["security", "monitoring"])