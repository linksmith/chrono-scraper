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
from app.services.library import LibraryService

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/{page_id}", response_model=PageReadWithStarring)
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


@router.post("/{page_id}/star")
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


@router.post("/{page_id}/review", response_model=PageRead)
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
    
    return page


@router.post("/{page_id}/tags")
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
    page_id: Optional[int] = Query(None),
    limit: int = Query(20, ge=1, le=100)
) -> List[TagSuggestion]:
    """
    Get tag suggestions based on query and/or page content
    """
    suggestions = await PageService.get_tag_suggestions(
        db, current_user.id, query, page_id, limit
    )
    
    return suggestions


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


@router.get("/{page_id}/content")
async def get_page_content(
    *,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_approved_user),
    page_id: int,
    format: str = Query("markdown", regex="^(html|markdown|text)$")
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


@router.post("/{page_id}/duplicate")
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