"""
Enhanced Filtering System API endpoints for scrape page management
"""
import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_current_approved_user
from app.models.user import User
from app.models.scrape_page_api import (
    ScrapePageQueryParams,
    ScrapePageListResponse,
    ScrapePageDetail,
    ScrapePageStatistics,
    ScrapePageAnalytics,
    ManualProcessingRequest,
    ManualProcessingResponse,
    ScrapePageFilterBy,
    ScrapePageSortBy,
    SortOrder,
    BulkManualProcessingRequest,
    BulkOperationResult,
    BulkOperationPreview
)
from app.services.scrape_page_service import ScrapePageService

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get(
    "/{project_id}/scrape-pages",
    response_model=ScrapePageListResponse,
    summary="List scrape pages with advanced filtering",
    description="Get paginated list of scrape pages for a project with comprehensive filtering and sorting options"
)
async def list_scrape_pages(
    project_id: int,
    # Pagination
    page: int = Query(default=1, ge=1, description="Page number"),
    limit: int = Query(default=50, ge=1, le=500, description="Items per page"),
    
    # Basic filtering
    filter_by: ScrapePageFilterBy = Query(
        default=ScrapePageFilterBy.ALL, 
        description="Filter by status category"
    ),
    
    # Sorting
    sort_by: ScrapePageSortBy = Query(
        default=ScrapePageSortBy.CREATED_AT, 
        description="Sort by field"
    ),
    order: SortOrder = Query(default=SortOrder.DESC, description="Sort order"),
    
    # Advanced filters
    domain_id: Optional[int] = Query(default=None, description="Filter by domain ID"),
    scrape_session_id: Optional[int] = Query(default=None, description="Filter by scrape session ID"),
    priority_min: Optional[int] = Query(default=None, ge=0, le=10, description="Minimum priority score"),
    priority_max: Optional[int] = Query(default=None, ge=0, le=10, description="Maximum priority score"),
    confidence_min: Optional[float] = Query(default=None, ge=0.0, le=1.0, description="Minimum filter confidence"),
    confidence_max: Optional[float] = Query(default=None, ge=0.0, le=1.0, description="Maximum filter confidence"),
    
    # Content filters
    has_content: Optional[bool] = Query(default=None, description="Filter by presence of extracted content"),
    is_pdf: Optional[bool] = Query(default=None, description="Filter by PDF status"),
    is_duplicate: Optional[bool] = Query(default=None, description="Filter by duplicate status"),
    is_list_page: Optional[bool] = Query(default=None, description="Filter by list page status"),
    
    # Date range filters (ISO format)
    created_after: Optional[str] = Query(default=None, description="Created after date (ISO format)"),
    created_before: Optional[str] = Query(default=None, description="Created before date (ISO format)"),
    completed_after: Optional[str] = Query(default=None, description="Completed after date (ISO format)"),
    completed_before: Optional[str] = Query(default=None, description="Completed before date (ISO format)"),
    
    # Text search
    search_query: Optional[str] = Query(default=None, max_length=500, description="Search in title, URL, or content"),
    
    # Manual processing filters
    can_be_manually_processed: Optional[bool] = Query(default=None, description="Filter by manual processing eligibility"),
    is_manually_overridden: Optional[bool] = Query(default=None, description="Filter by manual override status"),
    
    # Dependencies
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_approved_user)
) -> ScrapePageListResponse:
    """
    List scrape pages with advanced filtering and pagination.
    
    Supports comprehensive filtering by:
    - Status categories (pending, completed, failed, filtered, etc.)
    - Priority scores and confidence levels
    - Content characteristics (PDF, duplicates, list pages)
    - Date ranges for creation and completion
    - Text search across titles, URLs, and content
    - Manual processing status
    
    Results are paginated and can be sorted by various fields.
    """
    
    try:
        # Parse date strings if provided
        from datetime import datetime
        
        parsed_created_after = None
        parsed_created_before = None
        parsed_completed_after = None
        parsed_completed_before = None
        
        if created_after:
            try:
                parsed_created_after = datetime.fromisoformat(created_after.replace('Z', '+00:00'))
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid created_after date format. Use ISO format."
                )
        
        if created_before:
            try:
                parsed_created_before = datetime.fromisoformat(created_before.replace('Z', '+00:00'))
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid created_before date format. Use ISO format."
                )
        
        if completed_after:
            try:
                parsed_completed_after = datetime.fromisoformat(completed_after.replace('Z', '+00:00'))
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid completed_after date format. Use ISO format."
                )
        
        if completed_before:
            try:
                parsed_completed_before = datetime.fromisoformat(completed_before.replace('Z', '+00:00'))
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid completed_before date format. Use ISO format."
                )
        
        # Create query parameters object
        query_params = ScrapePageQueryParams(
            page=page,
            limit=limit,
            filter_by=filter_by,
            sort_by=sort_by,
            order=order,
            domain_id=domain_id,
            scrape_session_id=scrape_session_id,
            priority_min=priority_min,
            priority_max=priority_max,
            confidence_min=confidence_min,
            confidence_max=confidence_max,
            has_content=has_content,
            is_pdf=is_pdf,
            is_duplicate=is_duplicate,
            is_list_page=is_list_page,
            created_after=parsed_created_after,
            created_before=parsed_created_before,
            completed_after=parsed_completed_after,
            completed_before=parsed_completed_before,
            search_query=search_query,
            can_be_manually_processed=can_be_manually_processed,
            is_manually_overridden=is_manually_overridden
        )
        
        # Get scrape pages from service
        result = await ScrapePageService.get_project_scrape_pages(
            db=db,
            project_id=project_id,
            user_id=current_user.id,
            query_params=query_params
        )
        
        return result
        
    except ValueError as e:
        logger.warning(f"Invalid request for project {project_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Failed to list scrape pages for project {project_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve scrape pages"
        )


@router.get(
    "/{project_id}/scrape-pages/{page_id}",
    response_model=ScrapePageDetail,
    summary="Get scrape page details",
    description="Get detailed information for a specific scrape page including content and processing metadata"
)
async def get_scrape_page_detail(
    project_id: int,
    page_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_approved_user)
) -> ScrapePageDetail:
    """
    Get detailed information for a specific scrape page.
    
    Returns comprehensive details including:
    - Full extracted content and metadata
    - Processing performance metrics
    - Filter decision details
    - Error information if applicable
    - Relationship information
    """
    
    try:
        scrape_page = await ScrapePageService.get_scrape_page_detail(
            db=db,
            project_id=project_id,
            page_id=page_id,
            user_id=current_user.id
        )
        
        if not scrape_page:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Scrape page not found"
            )
        
        return scrape_page
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get scrape page {page_id} detail: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve scrape page details"
        )


@router.post(
    "/{project_id}/scrape-pages/manual-processing/mark",
    response_model=ManualProcessingResponse,
    summary="Mark pages for manual processing",
    description="Mark filtered scrape pages for manual review and potential processing override"
)
async def mark_pages_for_manual_processing(
    project_id: int,
    request: ManualProcessingRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_approved_user)
) -> ManualProcessingResponse:
    """
    Mark scrape pages for manual processing.
    
    This endpoint allows users to override filtering decisions by marking
    filtered pages for manual review. Pages marked for manual processing
    can then be processed using the process endpoint.
    
    Request body should contain:
    - page_ids: List of scrape page IDs to mark
    - reason: Optional reason for manual processing
    - priority_override: Optional priority score override
    - force_reprocess: Whether to reprocess already completed pages
    """
    
    try:
        if not request.page_ids:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="At least one page ID must be provided"
            )
        
        result = await ScrapePageService.mark_pages_for_manual_processing(
            db=db,
            project_id=project_id,
            user_id=current_user.id,
            request=request
        )
        
        return result
        
    except ValueError as e:
        logger.warning(f"Invalid manual processing request for project {project_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Failed to mark pages for manual processing in project {project_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to mark pages for manual processing"
        )


@router.post(
    "/{project_id}/scrape-pages/manual-processing/process",
    response_model=ManualProcessingResponse,
    summary="Process manually marked pages",
    description="Start processing pages that have been marked for manual review"
)
async def process_manually_marked_pages(
    project_id: int,
    request: ManualProcessingRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_approved_user)
) -> ManualProcessingResponse:
    """
    Process manually marked pages by queuing them for scraping.
    
    This endpoint starts the actual processing of pages that have been
    marked for manual review. It queues the pages for scraping using
    the Celery task system.
    
    Request body should contain:
    - page_ids: List of scrape page IDs to process
    - reason: Optional reason for processing
    - force_reprocess: Whether to reprocess already completed pages
    """
    
    try:
        if not request.page_ids:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="At least one page ID must be provided"
            )
        
        result = await ScrapePageService.process_manually_marked_pages(
            db=db,
            project_id=project_id,
            user_id=current_user.id,
            request=request
        )
        
        return result
        
    except ValueError as e:
        logger.warning(f"Invalid manual processing request for project {project_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Failed to process manually marked pages in project {project_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to process manually marked pages"
        )


@router.get(
    "/{project_id}/scrape-pages/analytics/statistics",
    response_model=ScrapePageStatistics,
    summary="Get scrape page statistics",
    description="Get comprehensive statistics about scrape pages in a project"
)
async def get_scrape_page_statistics(
    project_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_approved_user)
) -> ScrapePageStatistics:
    """
    Get comprehensive statistics for scrape pages in a project.
    
    Returns detailed metrics including:
    - Total pages and status distribution
    - Filter effectiveness metrics
    - Performance and quality statistics
    - Manual processing statistics
    - Time-based trends
    """
    
    try:
        statistics = await ScrapePageService.get_scrape_page_statistics(
            db=db,
            project_id=project_id,
            user_id=current_user.id
        )
        
        return statistics
        
    except ValueError as e:
        logger.warning(f"Invalid statistics request for project {project_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Failed to get scrape page statistics for project {project_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve scrape page statistics"
        )


@router.get(
    "/{project_id}/scrape-pages/analytics/comprehensive",
    response_model=ScrapePageAnalytics,
    summary="Get comprehensive scrape page analytics",
    description="Get detailed analytics including time series data and domain performance"
)
async def get_scrape_page_analytics(
    project_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_approved_user)
) -> ScrapePageAnalytics:
    """
    Get comprehensive analytics for scrape pages in a project.
    
    Returns detailed analytics including:
    - Basic statistics and filter analysis
    - Time series data for the last 30 days
    - Domain-specific performance metrics
    - Filtering effectiveness analysis
    """
    
    try:
        analytics = await ScrapePageService.get_scrape_page_analytics(
            db=db,
            project_id=project_id,
            user_id=current_user.id
        )
        
        return analytics
        
    except ValueError as e:
        logger.warning(f"Invalid analytics request for project {project_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Failed to get scrape page analytics for project {project_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve scrape page analytics"
        )


# Health check endpoint for the scrape pages service
@router.get(
    "/health",
    summary="Health check for scrape pages service",
    description="Check if the scrape pages service is operational"
)
async def health_check() -> JSONResponse:
    """
    Health check endpoint for the scrape pages service.
    """
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "status": "healthy",
            "service": "scrape_pages",
            "timestamp": "2024-01-01T00:00:00Z"  # This would be dynamic in real implementation
        }
    )


@router.post(
    "/{project_id}/scrape-pages/manual-processing/bulk/preview",
    response_model=BulkOperationPreview,
    summary="Preview bulk operation on scrape pages",
    description="Preview what pages would be affected by a bulk operation without executing it"
)
async def preview_bulk_operation(
    project_id: int,
    request: BulkManualProcessingRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_approved_user)
) -> BulkOperationPreview:
    """
    Preview the effects of a bulk operation on scrape pages.
    
    This endpoint allows you to see what pages would be affected by a bulk operation
    without actually executing it. It provides:
    - Total number of pages that would be affected
    - Breakdown by status and domain
    - Sample pages that would be affected
    - Warnings about potential issues
    - Estimated processing time
    
    Use this endpoint before executing bulk operations to ensure you're targeting
    the correct pages and understand the scope of the operation.
    """
    
    try:
        preview = await ScrapePageService.preview_bulk_operation(
            db=db,
            project_id=project_id,
            user_id=current_user.id,
            request=request
        )
        
        return preview
        
    except ValueError as e:
        logger.warning(f"Invalid bulk operation preview request for project {project_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Failed to preview bulk operation for project {project_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to preview bulk operation"
        )


@router.post(
    "/{project_id}/scrape-pages/manual-processing/bulk",
    response_model=BulkOperationResult,
    summary="Execute bulk operation on scrape pages",
    description="Execute bulk operations on scrape pages based on filters with progress tracking"
)
async def execute_bulk_operation(
    project_id: int,
    request: BulkManualProcessingRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_approved_user)
) -> BulkOperationResult:
    """
    Execute bulk operations on scrape pages.
    
    This endpoint allows you to perform bulk operations on multiple scrape pages
    at once based on filter criteria. Supported operations:
    
    - **mark_for_processing**: Mark filtered pages for manual review
    - **approve_all**: Approve pages awaiting manual review for processing
    - **skip_all**: Skip pages and mark them as skipped
    - **retry**: Retry failed pages by resetting their status
    - **reset_status**: Reset pages to a specific status
    - **update_priority**: Update priority scores for pages
    - **delete**: Delete pages (destructive operation)
    
    **Safety Features:**
    - Maximum page limits to prevent performance issues
    - Dry-run mode to preview operations
    - Batch processing for large operations
    - Progress tracking and WebSocket notifications
    - Transaction safety with rollback on errors
    
    **Request Parameters:**
    - `filters`: Same filtering options as the list endpoint
    - `action`: The operation to perform
    - `max_pages`: Maximum number of pages to process (safety limit)
    - `dry_run`: Preview mode without making actual changes
    - `batch_size`: Number of pages to process per batch
    - `reason`: Optional reason for audit trails
    - `priority_override`: New priority score (for relevant actions)
    - `force_reprocess`: Whether to reprocess completed pages
    
    **Response:**
    - Operation ID for tracking
    - Success/failure counts
    - List of affected page IDs
    - Task IDs for queued processing jobs
    - Timing information
    """
    
    try:
        # Validate request
        if not request.filters:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Filters must be provided for bulk operations"
            )
        
        # Execute the bulk operation
        result = await ScrapePageService.execute_bulk_operation(
            db=db,
            project_id=project_id,
            user_id=current_user.id,
            request=request
        )
        
        return result
        
    except ValueError as e:
        logger.warning(f"Invalid bulk operation request for project {project_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Failed to execute bulk operation for project {project_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to execute bulk operation"
        )