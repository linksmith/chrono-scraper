"""
Secure Multi-Tenant Meilisearch API Routes

This module provides secure Meilisearch search endpoints that use project-specific
API keys and tenant tokens to ensure proper data isolation between projects.
"""
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query, Request
from fastapi.security import HTTPBearer
from sqlmodel import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from ....core.database import get_db
from ....models.user import User
from ....models.project import Project
from ....models.sharing import ProjectShare, PublicSearchConfig, ShareStatus
from ....services.meilisearch_service import MeilisearchService
from ....api.deps import get_current_active_user
from ....core.config import settings
from ....core.rate_limiter import (
    rate_limit_public_search, 
    rate_limit_public_key_access, 
    rate_limit_tenant_token,
    RateLimitResult
)

router = APIRouter()
security = HTTPBearer()
logger = logging.getLogger(__name__)


@router.get("/projects/{project_id}/search")
async def search_project_secure(
    project_id: int,
    q: str = Query("", description="Search query"),
    limit: int = Query(20, ge=1, le=100, description="Number of results"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
    filters: Optional[str] = Query(None, description="Meilisearch filter expression"),
    facets: Optional[str] = Query(None, description="Comma-separated facet fields"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Secure search within a specific project using project-specific API keys
    
    This endpoint ensures data isolation by using the project's dedicated
    search key, preventing access to other projects' data.
    """
    try:
        # Verify user has access to this project (owner or shared)
        project_access = await _verify_project_access(db, project_id, current_user.id)
        if not project_access['has_access']:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to this project"
            )
        
        project = project_access['project']
        index_name = f"project_{project.id}"
        
        # Use appropriate Meilisearch service based on access type
        if project_access['access_type'] == 'owner':
            # Use project-specific key for owners
            search_service = await MeilisearchService.for_project(project)
        elif project_access['access_type'] == 'shared':
            # For shared access, could use tenant tokens (future enhancement)
            # For now, use project key but apply permission-based filtering
            search_service = await MeilisearchService.for_project(project)
            
            # Apply permission-based filtering
            share = project_access['share']
            if share and share.permission.value in ['limited', 'restricted']:
                permission_filter = _build_permission_filter(share.permission)
                if filters:
                    filters = f"({filters}) AND ({permission_filter})"
                else:
                    filters = permission_filter
        else:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Invalid access type"
            )
        
        # Parse facets
        facet_list = []
        if facets:
            facet_list = [f.strip() for f in facets.split(",")]
        
        # Parse filters into dict format
        filter_dict = {}
        if filters:
            # Simple filter parsing - in production, you'd want more robust parsing
            filter_dict = {"filter": filters}
        
        # Perform secure search
        async with search_service as ms:
            results = await ms.search_with_entity_filters(
                index_name=index_name,
                query=q,
                filters=filter_dict,
                facets=facet_list,
                limit=limit,
                offset=offset
            )
        
        logger.info(f"Secure search performed on project {project_id} by user {current_user.id}")
        
        return {
            "hits": results.get("hits", []),
            "totalHits": results.get("totalHits", 0),
            "facetDistribution": results.get("facetDistribution", {}),
            "processingTimeMs": results.get("processingTimeMs", 0),
            "query": q,
            "limit": limit,
            "offset": offset,
            "projectId": project_id,
            "accessType": project_access['access_type']
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Secure search failed for project {project_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Search operation failed"
        )


@router.get("/public/projects/{project_id}/search")
async def search_public_project(
    project_id: int,
    q: str = Query("", description="Search query"),
    limit: int = Query(20, ge=1, le=50, description="Number of results (max 50 for public)"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
    db: AsyncSession = Depends(get_db),
    rate_limit_result: RateLimitResult = Depends(rate_limit_public_search)
):
    """
    Public search endpoint using dedicated public search keys
    
    This endpoint provides public access to projects that have enabled
    public search, using read-only keys with rate limiting.
    """
    try:
        # Get public search configuration
        config_query = select(PublicSearchConfig).where(
            and_(
                PublicSearchConfig.project_id == project_id,
                PublicSearchConfig.is_enabled == True
            )
        )
        
        result = await db.execute(config_query)
        public_config = result.scalar_one_or_none()
        
        if not public_config or not public_config.search_key:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Public search not available for this project"
            )
        
        # Rate limiting check (simplified - in production use Redis or similar)
        # TODO: Implement proper rate limiting based on IP/session
        
        index_name = f"project_{project_id}"
        
        # Use public search key
        search_service = await MeilisearchService.for_public(public_config)
        
        # Perform public search with limited results
        async with search_service as ms:
            results = await ms.search_with_entity_filters(
                index_name=index_name,
                query=q,
                limit=min(limit, 50),  # Enforce public limit
                offset=offset
            )
        
        # Get project info for display
        project_query = select(Project).where(Project.id == project_id)
        project_result = await db.execute(project_query)
        project = project_result.scalar_one_or_none()
        
        logger.info(f"Public search performed on project {project_id}")
        
        response_data = {
            "hits": results.get("hits", []),
            "totalHits": results.get("totalHits", 0),
            "processingTimeMs": results.get("processingTimeMs", 0),
            "query": q,
            "limit": min(limit, 50),
            "offset": offset,
            "projectId": project_id,
            "projectTitle": public_config.custom_title or (project.name if project else "Unknown"),
            "projectDescription": public_config.custom_description or (project.description if project else None),
            "allowDownloads": public_config.allow_downloads,
            "isPublicSearch": True,
            "rateLimitInfo": {
                "limit": rate_limit_result.limit,
                "remaining": rate_limit_result.remaining,
                "resetTime": rate_limit_result.reset_time
            }
        }
        
        return response_data
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Public search failed for project {project_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Public search operation failed"
        )


@router.get("/projects/{project_id}/search/tenant")
async def search_with_tenant_token(
    project_id: int,
    tenant_token: str = Query(..., description="JWT tenant token for shared access"),
    q: str = Query("", description="Search query"),
    limit: int = Query(20, ge=1, le=100, description="Number of results"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
    db: AsyncSession = Depends(get_db),
    rate_limit_result: RateLimitResult = Depends(rate_limit_tenant_token)
):
    """
    Search using JWT tenant token for time-limited shared access
    
    This endpoint accepts tenant tokens generated by the sharing system
    and provides access based on the token's embedded permissions.
    """
    try:
        index_name = f"project_{project_id}"
        
        # Use tenant token for search
        search_service = await MeilisearchService.for_tenant_token(tenant_token)
        
        # Perform search with tenant token
        async with search_service as ms:
            results = await ms.search_with_entity_filters(
                index_name=index_name,
                query=q,
                limit=limit,
                offset=offset
            )
        
        logger.info(f"Tenant token search performed on project {project_id}")
        
        return {
            "hits": results.get("hits", []),
            "totalHits": results.get("totalHits", 0),
            "processingTimeMs": results.get("processingTimeMs", 0),
            "query": q,
            "limit": limit,
            "offset": offset,
            "projectId": project_id,
            "accessType": "tenant_token"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Tenant token search failed for project {project_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Tenant search operation failed"
        )


@router.get("/health")
async def meilisearch_health():
    """Check Meilisearch service health"""
    try:
        admin_service = await MeilisearchService.for_admin()
        async with admin_service as ms:
            if hasattr(ms.client, 'health'):
                health = await ms.client.health()
                return {"status": "healthy", "meilisearch": health}
            else:
                return {"status": "mock", "meilisearch": "unavailable"}
    except Exception as e:
        logger.error(f"Meilisearch health check failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Meilisearch service unavailable"
        )


# Helper functions
async def _verify_project_access(db: AsyncSession, project_id: int, user_id: int) -> Dict[str, Any]:
    """
    Verify user has access to project and return access details
    
    Returns:
        Dict with has_access, access_type ('owner' or 'shared'), project, and share info
    """
    # Check if user owns the project
    owner_query = select(Project).where(
        and_(
            Project.id == project_id,
            Project.user_id == user_id
        )
    )
    
    result = await db.execute(owner_query)
    project = result.scalar_one_or_none()
    
    if project:
        return {
            "has_access": True,
            "access_type": "owner",
            "project": project,
            "share": None
        }
    
    # Check if user has shared access
    share_query = select(ProjectShare, Project).join(Project).where(
        and_(
            ProjectShare.project_id == project_id,
            ProjectShare.shared_with_user_id == user_id,
            ProjectShare.status == ShareStatus.ACTIVE
        )
    )
    
    share_result = await db.execute(share_query)
    share_data = share_result.first()
    
    if share_data:
        share, project = share_data
        
        # Check if share has expired
        if share.expires_at and share.expires_at < datetime.utcnow():
            return {"has_access": False}
        
        return {
            "has_access": True,
            "access_type": "shared",
            "project": project,
            "share": share
        }
    
    return {"has_access": False}


def _build_permission_filter(permission) -> str:
    """Build filter string based on sharing permission level"""
    if permission.value == 'limited':
        return "review_status != 'irrelevant'"
    elif permission.value == 'restricted':
        return "review_status = 'relevant'"
    else:
        return ""  # No filtering for full read access


# Legacy compatibility endpoint (deprecated)
@router.get("/search/ping")
async def legacy_ping(current_user: User = Depends(get_current_active_user)):
    """Legacy compatibility endpoint - deprecated"""
    return {
        "status": "deprecated", 
        "message": "Use project-specific search endpoints for secure multi-tenant access"
    }