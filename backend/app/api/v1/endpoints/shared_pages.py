"""
API endpoints for shared pages architecture with enhanced security and functionality
"""
from typing import Any, List, Optional, Dict
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status, Query, Body
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime
import logging

from app.api.deps import get_db, get_current_approved_user
from app.models.user import User
from app.models.shared_pages import (
    PageV2, PageV2Read, PageV2ReadWithProjects, ProjectPage, ProjectPageRead, ProjectPageUpdate,
    PageReviewStatus, PageCategory, PagePriority, ProcessingStats
)
from app.models.project import Project
from app.services.page_access_control import PageAccessControl, PageAccessControlMiddleware, get_page_access_control
from app.services.shared_pages_meilisearch import SharedPagesMeilisearchService, get_shared_pages_meilisearch_service
from app.services.cdx_deduplication_service import EnhancedCDXService, get_cdx_service

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/{page_id}", response_model=PageV2ReadWithProjects)
async def get_shared_page(
    *,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_approved_user),
    access_control: PageAccessControl = Depends(get_page_access_control),
    page_id: UUID
) -> PageV2ReadWithProjects:
    """
    Get shared page details with project associations
    
    Security: Only returns page if user has access through project ownership
    """
    # Verify access
    middleware = PageAccessControlMiddleware(access_control)
    await middleware.validate_page_access(current_user.id, page_id, "read")
    
    # Get page with all project associations user has access to
    from sqlmodel import select
    
    # Get the page
    page = await db.get(PageV2, page_id)
    if not page:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Page not found"
        )
    
    # Get user's project associations for this page
    user_associations = await access_control.get_user_page_associations(
        current_user.id, [page_id]
    )
    
    # Create response with filtered associations
    page_dict = page.model_dump()
    page_dict["project_associations"] = [
        ProjectPageRead.model_validate(assoc) for assoc in user_associations
    ]
    
    return PageV2ReadWithProjects(**page_dict)


@router.get("", response_model=List[PageV2Read])
async def list_user_pages(
    *,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_approved_user),
    access_control: PageAccessControl = Depends(get_page_access_control),
    project_id: Optional[int] = Query(None, description="Filter by project ID"),
    limit: int = Query(100, le=1000, description="Number of pages to return"),
    offset: int = Query(0, ge=0, description="Offset for pagination")
) -> List[PageV2Read]:
    """
    List pages accessible to the user with optional project filtering
    
    Security: Only returns pages from user's projects
    """
    # Get accessible page IDs
    accessible_page_ids = await access_control.get_user_accessible_pages(
        current_user.id, project_id=project_id
    )
    
    if not accessible_page_ids:
        return []
    
    # Paginate accessible pages
    paginated_ids = accessible_page_ids[offset:offset + limit]
    
    # Get page details
    from sqlmodel import select
    
    stmt = select(PageV2).where(PageV2.id.in_(paginated_ids))
    result = await db.execute(stmt)
    pages = result.scalars().all()
    
    return [PageV2Read.model_validate(page) for page in pages]


@router.get("/projects/{project_id}/pages", response_model=List[PageV2Read])
async def get_project_pages(
    *,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_approved_user),
    access_control: PageAccessControl = Depends(get_page_access_control),
    project_id: int,
    limit: int = Query(100, le=1000),
    offset: int = Query(0, ge=0)
) -> List[PageV2Read]:
    """
    Get pages for a specific project with security validation
    
    Security: Verifies user owns the project
    """
    # Verify project ownership
    project = await db.get(Project, project_id)
    if not project or project.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied to project"
        )
    
    # Get project pages
    page_ids = await access_control.get_project_pages_for_user(
        current_user.id, project_id, limit, offset
    )
    
    if not page_ids:
        return []
    
    # Get page details
    from sqlmodel import select
    
    stmt = select(PageV2).where(PageV2.id.in_(page_ids))
    result = await db.execute(stmt)
    pages = result.scalars().all()
    
    return [PageV2Read.model_validate(page) for page in pages]


@router.post("/search", response_model=Dict[str, Any])
async def search_shared_pages(
    *,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_approved_user),
    access_control: PageAccessControl = Depends(get_page_access_control),
    meilisearch_service: SharedPagesMeilisearchService = Depends(get_shared_pages_meilisearch_service),
    search_request: Dict[str, Any] = Body(...)
) -> Dict[str, Any]:
    """
    Search shared pages with comprehensive filtering and security
    
    Security: Results filtered by user's project access
    """
    query = search_request.get("query", "")
    project_id = search_request.get("project_id")
    filters = search_request.get("filters", {})
    limit = min(search_request.get("limit", 100), 1000)
    offset = max(search_request.get("offset", 0), 0)
    sort = search_request.get("sort")
    
    # Execute secure search
    try:
        results = await meilisearch_service.search_user_pages(
            user_id=current_user.id,
            query=query,
            project_id=project_id,
            filters=filters,
            limit=limit,
            offset=offset,
            sort=sort
        )
        
        return {
            "success": True,
            "data": results,
            "query": query,
            "filters_applied": filters,
            "user_id": current_user.id,
            "project_id": project_id
        }
        
    except Exception as e:
        logger.error(f"Search failed for user {current_user.id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Search failed"
        )


@router.put("/{page_id}/associations/{project_id}", response_model=Dict[str, Any])
async def update_page_project_association(
    *,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_approved_user),
    access_control: PageAccessControl = Depends(get_page_access_control),
    meilisearch_service: SharedPagesMeilisearchService = Depends(get_shared_pages_meilisearch_service),
    page_id: UUID,
    project_id: int,
    update_data: ProjectPageUpdate = Body(...)
) -> Dict[str, Any]:
    """
    Update project-page association metadata (tags, notes, review status, etc.)
    
    Security: Verifies user owns the project and has access to the page
    """
    # Verify project ownership
    project = await db.get(Project, project_id)
    if not project or project.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied to project"
        )
    
    # Verify page access
    middleware = PageAccessControlMiddleware(access_control)
    await middleware.validate_page_access(current_user.id, page_id, "write")
    
    # Get the association
    from sqlmodel import select
    
    stmt = select(ProjectPage).where(
        ProjectPage.project_id == project_id,
        ProjectPage.page_id == page_id
    )
    result = await db.execute(stmt)
    association = result.scalar_one_or_none()
    
    if not association:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Page-project association not found"
        )
    
    # Update association
    update_dict = update_data.dict(exclude_unset=True)
    for field, value in update_dict.items():
        setattr(association, field, value)
    
    # Add review tracking
    if any(field in update_dict for field in ["review_status", "page_category", "priority_level"]):
        association.reviewed_by = current_user.id
        association.reviewed_at = datetime.utcnow()
    
    await db.commit()
    await db.refresh(association)
    
    # Update search index
    try:
        await meilisearch_service.index_page(
            await db.get(PageV2, page_id), project_id
        )
    except Exception as e:
        logger.warning(f"Failed to update search index: {e}")
    
    # Invalidate caches
    await access_control.invalidate_project_cache(project_id)
    
    return {
        "success": True,
        "message": "Association updated successfully",
        "page_id": str(page_id),
        "project_id": project_id,
        "updated_fields": list(update_dict.keys())
    }


@router.post("/bulk-actions", response_model=Dict[str, Any])
async def bulk_page_actions(
    *,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_approved_user),
    access_control: PageAccessControl = Depends(get_page_access_control),
    meilisearch_service: SharedPagesMeilisearchService = Depends(get_shared_pages_meilisearch_service),
    bulk_request: Dict[str, Any] = Body(...)
) -> Dict[str, Any]:
    """
    Perform bulk actions on multiple pages with security validation
    
    Security: Only operates on pages user has access to
    """
    page_ids = [UUID(pid) for pid in bulk_request.get("page_ids", [])]
    action = bulk_request.get("action")
    project_id = bulk_request.get("project_id")
    action_data = bulk_request.get("data", {})
    
    if not page_ids or not action:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="page_ids and action are required"
        )
    
    # Verify project ownership if specified
    if project_id:
        project = await db.get(Project, project_id)
        if not project or project.user_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to project"
            )
    
    # Validate bulk access
    middleware = PageAccessControlMiddleware(access_control)
    accessible_pages = await middleware.validate_bulk_page_access(
        current_user.id, page_ids, "write"
    )
    
    if not accessible_pages:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No accessible pages in the requested set"
        )
    
    # Perform bulk action
    from sqlmodel import select
    
    updated_count = 0
    failed_count = 0
    
    try:
        if action == "update_review_status":
            review_status = action_data.get("review_status")
            if not review_status:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="review_status required for this action"
                )
            
            # Get associations to update
            stmt = select(ProjectPage).where(
                ProjectPage.page_id.in_(accessible_pages),
                ProjectPage.project_id == project_id if project_id else True
            )
            result = await db.execute(stmt)
            associations = result.scalars().all()
            
            # Update associations
            for assoc in associations:
                assoc.review_status = PageReviewStatus(review_status)
                assoc.reviewed_by = current_user.id
                assoc.reviewed_at = datetime.utcnow()
                updated_count += 1
        
        elif action == "add_tags":
            tags_to_add = action_data.get("tags", [])
            if not tags_to_add:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="tags required for add_tags action"
                )
            
            stmt = select(ProjectPage).where(
                ProjectPage.page_id.in_(accessible_pages),
                ProjectPage.project_id == project_id if project_id else True
            )
            result = await db.execute(stmt)
            associations = result.scalars().all()
            
            for assoc in associations:
                current_tags = set(assoc.tags or [])
                current_tags.update(tags_to_add)
                assoc.tags = list(current_tags)
                updated_count += 1
        
        elif action == "set_priority":
            priority = action_data.get("priority_level")
            if not priority:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="priority_level required for this action"
                )
            
            stmt = select(ProjectPage).where(
                ProjectPage.page_id.in_(accessible_pages),
                ProjectPage.project_id == project_id if project_id else True
            )
            result = await db.execute(stmt)
            associations = result.scalars().all()
            
            for assoc in associations:
                assoc.priority_level = PagePriority(priority)
                assoc.reviewed_by = current_user.id
                assoc.reviewed_at = datetime.utcnow()
                updated_count += 1
        
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unsupported action: {action}"
            )
        
        await db.commit()
        
        # Update search index for affected pages
        if updated_count > 0:
            try:
                await meilisearch_service.bulk_index_pages(accessible_pages)
            except Exception as e:
                logger.warning(f"Failed to update search index: {e}")
        
        # Invalidate caches
        if project_id:
            await access_control.invalidate_project_cache(project_id)
        else:
            await access_control.invalidate_user_cache(current_user.id)
        
        return {
            "success": True,
            "message": f"Bulk {action} completed",
            "updated_count": updated_count,
            "failed_count": failed_count,
            "total_requested": len(page_ids),
            "accessible_pages": len(accessible_pages),
            "action": action
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Bulk action failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Bulk action failed"
        )


@router.get("/statistics/sharing", response_model=Dict[str, Any])
async def get_sharing_statistics(
    *,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_approved_user),
    access_control: PageAccessControl = Depends(get_page_access_control),
    meilisearch_service: SharedPagesMeilisearchService = Depends(get_shared_pages_meilisearch_service)
) -> Dict[str, Any]:
    """
    Get comprehensive statistics about page sharing for the user
    """
    try:
        # Get sharing statistics
        sharing_stats = await access_control.get_shared_pages_statistics(current_user.id)
        
        # Get search statistics
        search_stats = await meilisearch_service.get_search_statistics(current_user.id)
        
        return {
            "success": True,
            "data": {
                "sharing": sharing_stats,
                "search": search_stats,
                "user_id": current_user.id,
                "generated_at": datetime.utcnow().isoformat()
            }
        }
        
    except Exception as e:
        logger.error(f"Failed to get sharing statistics: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve statistics"
        )


@router.post("/projects/{project_id}/process-cdx", response_model=Dict[str, Any])
async def process_cdx_for_project(
    *,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_approved_user),
    cdx_service: EnhancedCDXService = Depends(get_cdx_service),
    project_id: int,
    cdx_request: Dict[str, Any] = Body(...)
) -> Dict[str, Any]:
    """
    Process CDX records for a project with deduplication
    
    This endpoint allows manual CDX processing for testing and recovery scenarios
    """
    # Verify project ownership
    project = await db.get(Project, project_id)
    if not project or project.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied to project"
        )
    
    cdx_records_data = cdx_request.get("cdx_records", [])
    domain_id = cdx_request.get("domain_id")
    
    if not cdx_records_data or not domain_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="cdx_records and domain_id are required"
        )
    
    # Convert to CDX records
    from app.services.cdx_deduplication_service import CDXRecord
    
    cdx_records = []
    for record_data in cdx_records_data:
        cdx_records.append(CDXRecord(
            url=record_data["url"],
            timestamp=record_data["timestamp"],
            wayback_url=record_data.get("wayback_url")
        ))
    
    try:
        # Process with deduplication
        stats = await cdx_service.process_cdx_results(
            cdx_records, project_id, domain_id
        )
        
        return {
            "success": True,
            "message": "CDX processing completed",
            "stats": stats.dict(),
            "project_id": project_id,
            "domain_id": domain_id,
            "records_processed": len(cdx_records)
        }
        
    except Exception as e:
        logger.error(f"CDX processing failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="CDX processing failed"
        )


@router.delete("/{page_id}/associations/{project_id}")
async def remove_page_from_project(
    *,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_approved_user),
    access_control: PageAccessControl = Depends(get_page_access_control),
    meilisearch_service: SharedPagesMeilisearchService = Depends(get_shared_pages_meilisearch_service),
    page_id: UUID,
    project_id: int
) -> Dict[str, Any]:
    """
    Remove page association from a project
    
    Security: Only removes if user owns the project
    Note: Page is only deleted from database if no other projects reference it
    """
    # Verify project ownership
    project = await db.get(Project, project_id)
    if not project or project.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied to project"
        )
    
    # Get and delete the association
    from sqlmodel import select, PageV2
    
    stmt = select(ProjectPage).where(
        ProjectPage.project_id == project_id,
        ProjectPage.page_id == page_id
    )
    result = await db.execute(stmt)
    association = result.scalar_one_or_none()
    
    if not association:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Page-project association not found"
        )
    
    # Remove the association
    await db.delete(association)
    
    # Check if page has other associations
    remaining_stmt = select(ProjectPage).where(ProjectPage.page_id == page_id)
    remaining_result = await db.execute(remaining_stmt)
    remaining_associations = remaining_result.scalars().all()
    
    page_deleted = False
    if not remaining_associations:
        # No other associations, delete the page
        page = await db.get(PageV2, page_id)
        if page:
            await db.delete(page)
            page_deleted = True
    
    await db.commit()
    
    # Update search index
    try:
        if page_deleted:
            # Remove from search index entirely
            meilisearch_service.index.delete_document(str(page_id))
        else:
            # Update to remove this project association
            await meilisearch_service.update_page_project_association(
                page_id, project_id, "remove"
            )
    except Exception as e:
        logger.warning(f"Failed to update search index: {e}")
    
    # Invalidate caches
    await access_control.invalidate_project_cache(project_id)
    
    return {
        "success": True,
        "message": "Page removed from project" + (" and deleted" if page_deleted else ""),
        "page_id": str(page_id),
        "project_id": project_id,
        "page_deleted": page_deleted,
        "remaining_associations": len(remaining_associations)
    }