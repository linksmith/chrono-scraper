"""
Page management endpoints for starring, tagging, and review operations
"""
from typing import Any, List, Optional, Dict
from fastapi import APIRouter, Depends, HTTPException, status, Query, Body
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime
import logging

from app.api.deps import get_db, get_current_approved_user
from app.models.user import User
from app.models.project import (
    PageRead,
    PageReadWithStarring,
    PageReview,
    PageBulkAction,
    TagSuggestion,
    PageReviewStatus,
    PageCategory,
    PagePriority
)
from app.models.library import StarredItem, ItemType
from app.services.projects import PageService
from app.services.library_service import LibraryService
from app.services.meilisearch_service import meilisearch_service

logger = logging.getLogger(__name__)
router = APIRouter()


async def sync_page_to_index(page_id: int, db: AsyncSession, force_immediate: bool = False) -> bool:
    """
    Queue page synchronization to Meilisearch index (batch processing)
    
    Args:
        page_id: ID of the page to sync
        db: Database session
        force_immediate: If True, sync immediately instead of queuing (for critical operations)
    """
    try:
        # Get the page with domain information to determine project
        from sqlmodel import select
        from app.models.project import Page, Domain, Project
        from app.services.batch_sync_manager import batch_sync_manager, SyncOperation
        
        query = (
            select(Page, Project)
            .join(Domain, Page.domain_id == Domain.id)
            .join(Project, Domain.project_id == Project.id)
            .where(Page.id == page_id)
        )
        result = await db.execute(query)
        page_project = result.first()
        
        if not page_project:
            logger.warning(f"Page {page_id} not found for sync")
            return False
            
        page, project = page_project
        
        if force_immediate:
            # Immediate sync (for critical operations) - use legacy method
            from app.services.meilisearch_service import meilisearch_service
            
            # Prepare optimized document using MeilisearchService
            async with meilisearch_service as ms:
                document = ms._prepare_document(page)
                index_name = f"project_{project.id}"
                await ms.add_documents_batch(index_name, [document])
                
            logger.debug(f"Immediately synced page {page_id} to search index")
            return True
        else:
            # Queue for batch processing
            from app.services.meilisearch_service import meilisearch_service
            
            async with meilisearch_service as ms:
                # Prepare optimized document
                document = ms._prepare_document(page)
                
                # Queue the sync operation
                async with batch_sync_manager as bsm:
                    success = await bsm.queue_sync_operation(
                        page_id=page_id,
                        operation=SyncOperation.UPDATE,  # Default to update
                        project_id=project.id,
                        data=document
                    )
                    
                    if success:
                        logger.debug(f"Queued page {page_id} for batch sync")
                        return True
                    else:
                        # Fallback to immediate sync if queuing fails
                        logger.warning(f"Failed to queue page {page_id}, falling back to immediate sync")
                        await ms.add_documents_batch(f"project_{project.id}", [document])
                        return True
        
    except Exception as e:
        logger.error(f"Failed to sync page {page_id} to search index: {str(e)}")
        return False


async def queue_page_index(page_id: int, db: AsyncSession, operation: str = "update") -> bool:
    """
    Queue a page for indexing with specific operation type
    
    Args:
        page_id: ID of the page
        db: Database session  
        operation: Type of operation ("index", "update", "delete")
    """
    from app.services.batch_sync_manager import batch_sync_manager, SyncOperation
    
    try:
        # Map string to enum
        operation_map = {
            "index": SyncOperation.INDEX,
            "update": SyncOperation.UPDATE, 
            "delete": SyncOperation.DELETE
        }
        sync_op = operation_map.get(operation, SyncOperation.UPDATE)
        
        if sync_op == SyncOperation.DELETE:
            # For deletes, we only need page_id and project info
            from sqlmodel import select
            from app.models.project import Page, Domain, Project
            
            query = (
                select(Project)
                .join(Domain, Domain.project_id == Project.id)
                .join(Page, Page.domain_id == Domain.id)
                .where(Page.id == page_id)
            )
            result = await db.execute(query)
            project = result.scalar_one_or_none()
            
            if not project:
                logger.warning(f"Project not found for page {page_id} deletion")
                return False
            
            # Queue delete operation
            async with batch_sync_manager as bsm:
                return await bsm.queue_sync_operation(
                    page_id=page_id,
                    operation=sync_op,
                    project_id=project.id,
                    data={"id": f"page_{page_id}"}  # Only need document ID for deletion
                )
        else:
            # For index/update operations, use the main sync function
            return await sync_page_to_index(page_id, db, force_immediate=False)
            
    except Exception as e:
        logger.error(f"Failed to queue page {page_id} for {operation}: {str(e)}")
        return False


@router.get("/{page_id:int}", response_model=PageReadWithStarring)
async def get_page(
    *,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_approved_user),
    page_id: int
) -> PageReadWithStarring:
    """
    Get page details with starring information
    """
    page = await PageService.get_page_with_starring(
        db, page_id, current_user.id
    )
    
    if not page:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Page not found"
        )
    
    return page


@router.post("/{page_id:int}/star")
async def star_page(
    *,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_approved_user),
    page_id: int,
    star_data: Dict[str, Any] = Body(default={})
) -> Dict[str, Any]:
    """
    Star or unstar a page with optional tags and notes
    """
    tags = star_data.get("tags", [])
    personal_note = star_data.get("personal_note", "")
    folder = star_data.get("folder", "")
    
    # Check if page exists and user has access
    page = await PageService.get_page_by_id(db, page_id, current_user.id)
    if not page:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Page not found"
        )
    
    # Toggle star status
    starred_item = await LibraryService.toggle_star(
        db,
        user_id=current_user.id,
        item_type=ItemType.PAGE,
        item_id=page_id,
        page_id=page_id,
        tags=tags,
        personal_note=personal_note,
        folder=folder
    )
    
    # Synchronize to search index
    await sync_page_to_index(page_id, db)
    
    if starred_item:
        return {
            "starred": True,
            "message": "Page starred successfully",
            "star_id": starred_item.id
        }
    else:
        return {
            "starred": False,
            "message": "Page unstarred successfully"
        }


@router.post("/{page_id:int}/review", response_model=PageRead)
async def review_page(
    *,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_approved_user),
    page_id: int,
    review_data: PageReview
) -> PageRead:
    """
    Review a page with status, category, and notes
    """
    page = await PageService.review_page(
        db, page_id, current_user.id, review_data
    )
    
    if not page:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Page not found"
        )
    
    # Synchronize to search index
    await sync_page_to_index(page_id, db)
    
    return page


@router.post("/{page_id:int}/tags")
async def update_page_tags(
    *,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_approved_user),
    page_id: int,
    tags_data: Dict[str, List[str]] = Body(...)
) -> Dict[str, Any]:
    """
    Update page tags
    """
    tags = tags_data.get("tags", [])
    
    page = await PageService.update_page_tags(
        db, page_id, current_user.id, tags
    )
    
    if not page:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Page not found"
        )
    
    # Synchronize to search index
    await sync_page_to_index(page_id, db)
    
    return {
        "message": "Tags updated successfully",
        "tags": page.tags
    }


@router.post("/bulk-actions")
async def bulk_page_actions(
    *,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_approved_user),
    bulk_action: PageBulkAction
) -> Dict[str, Any]:
    """
    Perform bulk actions on multiple pages
    """
    if not bulk_action.page_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No page IDs provided"
        )
    
    result = await PageService.bulk_page_action(
        db, current_user.id, bulk_action
    )
    
    # Synchronize all affected pages to search index
    if result.get("success"):
        for page_id in bulk_action.page_ids:
            await sync_page_to_index(page_id, db)
    
    return result


@router.get("/starred")
async def get_starred_pages(
    *,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_approved_user),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    tags: Optional[List[str]] = Query(None),
    folder: Optional[str] = Query(None),
    search: Optional[str] = Query(None)
) -> Dict[str, Any]:
    """
    Get user's starred pages with filtering
    """
    starred_pages = await LibraryService.get_starred_items(
        db,
        user_id=current_user.id,
        item_type=ItemType.PAGE,
        skip=skip,
        limit=limit,
        tags=tags,
        folder=folder,
        search=search
    )
    
    return starred_pages


@router.get("/for-review")
async def get_pages_for_review(
    *,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_approved_user),
    project_id: Optional[int] = Query(None),
    review_status: Optional[PageReviewStatus] = Query(PageReviewStatus.UNREVIEWED),
    priority_level: Optional[PagePriority] = Query(None),
    page_category: Optional[PageCategory] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    exclude_irrelevant: bool = Query(True)
) -> Dict[str, Any]:
    """
    Get pages that need review with filtering options
    """
    pages = await PageService.get_pages_for_review(
        db,
        user_id=current_user.id,
        project_id=project_id,
        review_status=review_status,
        priority_level=priority_level,
        page_category=page_category,
        skip=skip,
        limit=limit,
        exclude_irrelevant=exclude_irrelevant
    )
    
    return pages


@router.get("/tag-suggestions")
async def get_tag_suggestions(
    *,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_approved_user),
    query: Optional[str] = Query(None),
    page_id: Optional[str] = Query(None),
    limit: Optional[str] = Query(None)
) -> List[Dict[str, Any]]:
    """
    Get tag suggestions based on query and/or page content
    """
    # Safely parse optional params to avoid request validation 422s
    safe_page_id: Optional[int] = None
    if page_id is not None and str(page_id).strip() != "":
        try:
            safe_page_id = int(str(page_id))
        except Exception:
            safe_page_id = None

    safe_limit: int = 20
    if limit is not None and str(limit).strip() != "":
        try:
            safe_limit = int(str(limit))
        except Exception:
            safe_limit = 20
    # Enforce bounds
    safe_limit = max(1, min(safe_limit, 100))

    suggestions = await PageService.get_tag_suggestions(
        db, current_user.id, query, safe_page_id, safe_limit
    )

    # Return as plain dicts to avoid response model validation edge cases
    return [
        {
            "tag": s.tag,
            "frequency": s.frequency,
            "category": getattr(s, "category", None),
            "confidence": s.confidence,
        }
        for s in suggestions
    ]


@router.get("/analytics")
async def get_page_analytics(
    *,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_approved_user),
    project_id: Optional[int] = Query(None),
    days: int = Query(30, ge=1, le=365)
) -> Dict[str, Any]:
    """
    Get page review analytics and statistics
    """
    analytics = await PageService.get_page_analytics(
        db, current_user.id, project_id, days
    )
    
    return analytics


@router.get("/{page_id:int}/content")
async def get_page_content(
    *,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_approved_user),
    page_id: int,
    format: str = Query("markdown", pattern="^(html|markdown|text)$")
) -> Dict[str, Any]:
    """
    Get page content in different formats
    """
    content = await PageService.get_page_content(
        db, page_id, current_user.id, format
    )
    
    if not content:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Page not found or no content available"
        )
    
    return content


@router.post("/{page_id:int}/duplicate")
async def mark_as_duplicate(
    *,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_approved_user),
    page_id: int,
    duplicate_data: Dict[str, int] = Body(...)
) -> Dict[str, Any]:
    """
    Mark page as duplicate of another page
    """
    duplicate_of_page_id = duplicate_data.get("duplicate_of_page_id")
    
    if not duplicate_of_page_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="duplicate_of_page_id is required"
        )
    
    result = await PageService.mark_as_duplicate(
        db, page_id, duplicate_of_page_id, current_user.id
    )
    
    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Page not found or invalid duplicate reference"
        )
    
    return {
        "message": "Page marked as duplicate successfully",
        "duplicate_of_page_id": duplicate_of_page_id
    }