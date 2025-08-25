"""
Advanced search endpoints
"""
from datetime import date
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_current_approved_user
from app.models.user import User
from app.services.advanced_search import AdvancedSearchService, SearchFilters

router = APIRouter()


@router.get("/pages")
async def search_pages(
    q: Optional[str] = Query(None, description="Search query"),
    projects: Optional[str] = Query(None, description="Comma-separated project IDs"),
    domains: Optional[str] = Query(None, description="Comma-separated domain names"),
    date_from: Optional[date] = Query(None, description="Filter from date"),
    date_to: Optional[date] = Query(None, description="Filter to date"),
    content_types: Optional[str] = Query(None, description="Comma-separated content types"),
    languages: Optional[str] = Query(None, description="Comma-separated language codes"),
    word_count_min: Optional[int] = Query(None, ge=0, description="Minimum word count"),
    word_count_max: Optional[int] = Query(None, ge=0, description="Maximum word count"),
    has_title: Optional[bool] = Query(None, description="Filter pages with/without title"),
    has_author: Optional[bool] = Query(None, description="Filter pages with/without author"),
    status_codes: Optional[str] = Query(None, description="Comma-separated HTTP status codes"),
    keywords: Optional[str] = Query(None, description="Comma-separated required keywords"),
    exclude_keywords: Optional[str] = Query(None, description="Comma-separated excluded keywords"),
    # Parity with project pages
    starred_only: bool = Query(False, description="Filter to only starred pages"),
    tags: Optional[str] = Query(None, description="Comma-separated tags"),
    review_status: Optional[str] = Query(None, description="Comma-separated review statuses (relevant, irrelevant, unreviewed, needs_review, duplicate)"),
    sort_by: str = Query("scraped_at", description="Sort field"),
    sort_order: str = Query("desc", pattern="^(asc|desc)$", description="Sort order"),
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(20, ge=1, le=100, description="Items per page"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_approved_user)
) -> Dict[str, Any]:
    """
    Advanced search for pages with multiple filters
    """
    # Parse comma-separated parameters
    def parse_csv_param(param: Optional[str]) -> List[str]:
        return [item.strip() for item in param.split(",")] if param else []
    
    def parse_csv_int_param(param: Optional[str]) -> List[int]:
        if not param:
            return []
        try:
            return [int(item.strip()) for item in param.split(",")]
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid integer values in parameter"
            )
    
    # Create search filters
    filters = SearchFilters(
        query=q,
        projects=parse_csv_int_param(projects),
        domains=parse_csv_param(domains),
        date_from=date_from,
        date_to=date_to,
        content_types=parse_csv_param(content_types),
        languages=parse_csv_param(languages),
        word_count_min=word_count_min,
        word_count_max=word_count_max,
        has_title=has_title,
        has_author=has_author,
        status_codes=parse_csv_int_param(status_codes),
        keywords=parse_csv_param(keywords),
        exclude_keywords=parse_csv_param(exclude_keywords),
        starred_only=starred_only,
        tags=parse_csv_param(tags),
        review_status=parse_csv_param(review_status),
        sort_by=sort_by,
        sort_order=sort_order,
        page=page,
        per_page=per_page
    )
    
    # Perform search
    try:
        results = await AdvancedSearchService.search_pages(
            db=db,
            filters=filters,
            user_id=current_user.id
        )
        return results
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Search failed: {str(e)}"
        )


@router.get("/facets")
async def get_search_facets(
    project_ids: Optional[str] = Query(None, description="Comma-separated project IDs to limit facets"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_approved_user)
) -> Dict[str, Any]:
    """
    Get available facet values for search filters
    """
    def parse_csv_int_param(param: Optional[str]) -> List[int]:
        if not param:
            return []
        try:
            return [int(item.strip()) for item in param.split(",")]
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid project IDs"
            )
    
    project_id_list = parse_csv_int_param(project_ids) if project_ids else None
    
    try:
        facets = await AdvancedSearchService.get_search_facets(
            db=db,
            user_id=current_user.id,
            project_ids=project_id_list
        )
        return facets
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get facets: {str(e)}"
        )


@router.get("/pages/{page_id}/similar")
async def get_similar_pages(
    page_id: int,
    limit: int = Query(10, ge=1, le=50, description="Maximum number of similar pages"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_approved_user)
) -> List[Dict[str, Any]]:
    """
    Find pages similar to the given page
    """
    try:
        similar_pages = await AdvancedSearchService.get_similar_pages(
            db=db,
            page_id=page_id,
            user_id=current_user.id,
            limit=limit
        )
        return similar_pages
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to find similar pages: {str(e)}"
        )


@router.post("/query/parse")
async def parse_search_query(
    query_data: Dict[str, str],
    current_user: User = Depends(get_current_approved_user)
) -> Dict[str, Any]:
    """
    Parse advanced search query syntax
    """
    query = query_data.get("query", "")
    
    if not query:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Query is required"
        )
    
    try:
        parsed = AdvancedSearchService.parse_search_query(query)
        return {
            "original_query": query,
            "parsed": parsed
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to parse query: {str(e)}"
        )


@router.post("/saved")
async def save_search(
    search_data: Dict[str, Any],
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_approved_user)
) -> Dict[str, Any]:
    """
    Save a search query for later use
    """
    name = search_data.get("name")
    description = search_data.get("description")
    filters_data = search_data.get("filters", {})
    
    if not name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Search name is required"
        )
    
    try:
        # Convert filters_data to SearchFilters object
        filters = SearchFilters(**filters_data)
        
        saved_search = await AdvancedSearchService.create_saved_search(
            db=db,
            user_id=current_user.id,
            name=name,
            filters=filters,
            description=description
        )
        
        return saved_search
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to save search: {str(e)}"
        )


@router.get("/export")
async def export_search_results(
    format: str = Query("json", pattern="^(json|csv|xlsx)$", description="Export format"),
    q: Optional[str] = Query(None, description="Search query"),
    projects: Optional[str] = Query(None, description="Comma-separated project IDs"),
    domains: Optional[str] = Query(None, description="Comma-separated domain names"),
    date_from: Optional[date] = Query(None, description="Filter from date"),
    date_to: Optional[date] = Query(None, description="Filter to date"),
    max_results: int = Query(1000, ge=1, le=10000, description="Maximum results to export"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_approved_user)
) -> Dict[str, Any]:
    """
    Export search results in various formats
    """
    # Parse parameters
    def parse_csv_param(param: Optional[str]) -> List[str]:
        return [item.strip() for item in param.split(",")] if param else []
    
    def parse_csv_int_param(param: Optional[str]) -> List[int]:
        if not param:
            return []
        try:
            return [int(item.strip()) for item in param.split(",")]
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid integer values in parameter"
            )
    
    # Create search filters for export
    filters = SearchFilters(
        query=q,
        projects=parse_csv_int_param(projects),
        domains=parse_csv_param(domains),
        date_from=date_from,
        date_to=date_to,
        per_page=max_results,
        page=1
    )
    
    try:
        # Get search results
        results = await AdvancedSearchService.search_pages(
            db=db,
            filters=filters,
            user_id=current_user.id
        )
        
        # For now, return JSON format
        # TODO: Implement CSV and XLSX export
        if format == "json":
            return {
                "format": format,
                "total_exported": len(results["pages"]),
                "data": results["pages"],
                "exported_at": "2024-01-01T00:00:00Z"  # Would use actual timestamp
            }
        else:
            raise HTTPException(
                status_code=status.HTTP_501_NOT_IMPLEMENTED,
                detail=f"Export format '{format}' not yet implemented"
            )
            
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Export failed: {str(e)}"
        )