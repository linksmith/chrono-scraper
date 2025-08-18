"""
Meilisearch FastAPI integration routes
Provides comprehensive Meilisearch API access with authentication
"""
from fastapi import APIRouter, Depends
from meilisearch_fastapi.routes import search_routes
from app.api.deps import get_current_active_user
from app.models.user import User

# Create router for meilisearch endpoints
router = APIRouter()

# Include search routes (protected - requires authentication)
router.include_router(
    search_routes.router,
    prefix="/search",
    dependencies=[Depends(get_current_active_user)],
    tags=["meilisearch-search"]
)