"""
User library API endpoints for starred items, saved searches, and collections
"""
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from app.core.deps import get_current_user, get_db
from app.models.user import User
from app.models.library import ItemType, AlertFrequency
from app.services.library_service import library_service

router = APIRouter()


# Pydantic models for request/response
class StarItemRequest(BaseModel):
    item_type: ItemType
    item_id: int
    note: str = ""
    tags: List[str] = []
    folder: str = ""


class SaveSearchRequest(BaseModel):
    name: str
    query_text: str
    filters: Dict[str, Any] = {}
    sort_options: Dict[str, Any] = {}
    description: str = ""
    folder: str = ""
    tags: List[str] = []
    enable_alerts: bool = False
    alert_frequency: AlertFrequency = AlertFrequency.DAILY


class CreateCollectionRequest(BaseModel):
    name: str
    description: str = ""
    collection_type: str = "general"
    parent_collection_id: Optional[int] = None


class AddToCollectionRequest(BaseModel):
    item_type: ItemType
    item_id: int


# Starred Items endpoints
@router.post("/starred")
async def star_item(
    request: StarItemRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Star an item for the user"""
    try:
        starred_item = await library_service.star_item(
            db, current_user, request.item_type, request.item_id,
            request.note, request.tags, request.folder
        )
        
        return {
            "id": starred_item.id,
            "item_type": starred_item.item_type,
            "item_id": starred_item.item_id,
            "message": "Item starred successfully"
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to star item: {str(e)}"
        )


@router.delete("/starred/{item_type}/{item_id}")
async def unstar_item(
    item_type: ItemType,
    item_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Remove star from an item"""
    try:
        success = await library_service.unstar_item(db, current_user, item_type, item_id)
        
        if success:
            return {"message": "Item unstarred successfully"}
        else:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Starred item not found"
            )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to unstar item: {str(e)}"
        )


@router.get("/starred", response_model=List[Dict[str, Any]])
async def get_starred_items(
    item_type: Optional[ItemType] = Query(None),
    folder: Optional[str] = Query(None),
    tags: Optional[List[str]] = Query(None),
    limit: int = Query(50, le=100),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get user's starred items with filtering"""
    try:
        starred_items = await library_service.get_starred_items(
            db, current_user, item_type, folder, tags, limit, offset
        )
        return starred_items
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get starred items: {str(e)}"
        )


# Saved Searches endpoints
@router.post("/searches")
async def save_search(
    request: SaveSearchRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Save a search query"""
    try:
        saved_search = await library_service.save_search(
            db, current_user, request.name, request.query_text,
            request.filters, request.sort_options, request.description,
            request.folder, request.tags, request.enable_alerts, request.alert_frequency
        )
        
        return {
            "id": saved_search.id,
            "name": saved_search.name,
            "query_text": saved_search.query_text,
            "share_token": saved_search.share_token,
            "message": "Search saved successfully"
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to save search: {str(e)}"
        )


@router.get("/searches", response_model=List[Dict[str, Any]])
async def get_saved_searches(
    folder: Optional[str] = Query(None),
    tags: Optional[List[str]] = Query(None),
    limit: int = Query(50, le=100),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get user's saved searches"""
    try:
        searches = await library_service.get_saved_searches(
            db, current_user, folder, tags, limit, offset
        )
        
        return [
            {
                "id": search.id,
                "name": search.name,
                "description": search.description,
                "query_text": search.query_text,
                "filters": search.filters,
                "sort_options": search.sort_options,
                "folder": search.folder,
                "tags": search.tags,
                "enable_alerts": search.enable_alerts,
                "alert_frequency": search.alert_frequency,
                "last_result_count": search.last_result_count,
                "last_executed": search.last_executed,
                "execution_count": search.execution_count,
                "created_at": search.created_at,
                "updated_at": search.updated_at,
            }
            for search in searches
        ]
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get saved searches: {str(e)}"
        )


@router.post("/searches/{search_id}/execute")
async def execute_saved_search(
    search_id: int,
    result_count: int = 0,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Execute a saved search and record the execution"""
    try:
        saved_search = await library_service.execute_saved_search(
            db, current_user, search_id, result_count
        )
        
        if not saved_search:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Saved search not found"
            )
        
        return {
            "id": saved_search.id,
            "name": saved_search.name,
            "query_text": saved_search.query_text,
            "filters": saved_search.filters,
            "execution_count": saved_search.execution_count,
            "last_executed": saved_search.last_executed,
            "last_result_count": saved_search.last_result_count,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to execute saved search: {str(e)}"
        )


@router.delete("/searches/{search_id}")
async def delete_saved_search(
    search_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Delete a saved search"""
    try:
        from sqlmodel import select
        from app.models.library import SavedSearch
        
        result = await db.execute(
            select(SavedSearch).where(
                SavedSearch.id == search_id,
                SavedSearch.user_id == current_user.id
            )
        )
        saved_search = result.scalar_one_or_none()
        
        if not saved_search:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Saved search not found"
            )
        
        await db.delete(saved_search)
        await db.commit()
        
        return {"message": "Saved search deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete saved search: {str(e)}"
        )


# Search History endpoints
@router.get("/search-history", response_model=List[Dict[str, Any]])
async def get_search_history(
    project_id: Optional[int] = Query(None),
    days: int = Query(30, le=365),
    limit: int = Query(100, le=500),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get user's search history"""
    try:
        history = await library_service.get_search_history(
            db, current_user, project_id, days, limit
        )
        
        return [
            {
                "id": entry.id,
                "query_text": entry.query_text,
                "filters": entry.filters,
                "result_count": entry.result_count,
                "execution_time_ms": entry.execution_time_ms,
                "project_id": entry.project_id,
                "saved_search_id": entry.saved_search_id,
                "created_at": entry.created_at,
            }
            for entry in history
        ]
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get search history: {str(e)}"
        )


@router.post("/search-history")
async def record_search(
    query_text: str,
    filters: Dict[str, Any] = {},
    result_count: int = 0,
    project_id: Optional[int] = None,
    execution_time_ms: Optional[int] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Record a search in user's history"""
    try:
        search_history = await library_service.record_search_history(
            db, current_user, query_text, filters, result_count,
            project_id, execution_time_ms=execution_time_ms
        )
        
        return {
            "id": search_history.id,
            "message": "Search recorded in history"
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to record search: {str(e)}"
        )


# Search Suggestions endpoints
@router.get("/search-suggestions", response_model=List[Dict[str, Any]])
async def get_search_suggestions(
    query_prefix: str = Query(""),
    limit: int = Query(10, le=20),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get search suggestions for user"""
    try:
        suggestions = await library_service.get_search_suggestions(
            db, current_user, query_prefix, limit
        )
        
        return [
            {
                "id": suggestion.id,
                "suggestion_text": suggestion.suggestion_text,
                "display_text": suggestion.display_text,
                "suggestion_type": suggestion.suggestion_type,
                "score": suggestion.score,
                "frequency": suggestion.frequency,
                "last_used": suggestion.last_used,
            }
            for suggestion in suggestions
        ]
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get search suggestions: {str(e)}"
        )


# Collections endpoints
@router.post("/collections")
async def create_collection(
    request: CreateCollectionRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Create a new collection"""
    try:
        collection = await library_service.create_collection(
            db, current_user, request.name, request.description,
            request.collection_type, request.parent_collection_id
        )
        
        return {
            "id": collection.id,
            "name": collection.name,
            "description": collection.description,
            "collection_type": collection.collection_type,
            "share_token": collection.share_token,
            "message": "Collection created successfully"
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create collection: {str(e)}"
        )


@router.get("/collections", response_model=List[Dict[str, Any]])
async def get_collections(
    collection_type: Optional[str] = Query(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get user's collections"""
    try:
        collections = await library_service.get_user_collections(
            db, current_user, collection_type
        )
        
        return [
            {
                "id": collection.id,
                "name": collection.name,
                "description": collection.description,
                "collection_type": collection.collection_type,
                "item_count": collection.item_count,
                "items": collection.items,
                "parent_collection_id": collection.parent_collection_id,
                "is_public": collection.is_public,
                "created_at": collection.created_at,
                "updated_at": collection.updated_at,
            }
            for collection in collections
        ]
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get collections: {str(e)}"
        )


@router.post("/collections/{collection_id}/items")
async def add_item_to_collection(
    collection_id: int,
    request: AddToCollectionRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Add an item to a collection"""
    try:
        success = await library_service.add_item_to_collection(
            db, current_user, collection_id, request.item_type, request.item_id
        )
        
        if success:
            return {"message": "Item added to collection successfully"}
        else:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Collection not found"
            )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to add item to collection: {str(e)}"
        )


# Library Stats endpoint
@router.get("/stats", response_model=Dict[str, Any])
async def get_library_stats(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get library statistics for user"""
    try:
        stats = await library_service.get_library_stats(db, current_user)
        return stats
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get library stats: {str(e)}"
        )