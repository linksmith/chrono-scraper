"""
Semantic search API endpoints
"""
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from sqlmodel.ext.asyncio.session import AsyncSession
from pydantic import BaseModel

from app.core.database import get_session
from app.api.deps import get_current_user, require_admin
from app.models.user import User
from app.services.semantic_search import semantic_search_service
import logging

logger = logging.getLogger(__name__)

router = APIRouter()


class SemanticSearchRequest(BaseModel):
    """Request model for semantic search"""
    query: str
    project_id: Optional[int] = None
    domain_ids: Optional[List[int]] = None
    limit: int = 20
    min_similarity: float = 0.5


class SemanticSearchResponse(BaseModel):
    """Response model for semantic search"""
    results: List[Dict[str, Any]]
    total_found: int
    query: str
    processing_time_ms: float


class EmbeddingUpdateRequest(BaseModel):
    """Request model for embedding updates"""
    project_id: Optional[int] = None
    domain_id: Optional[int] = None
    force_update: bool = False
    batch_size: int = 50


@router.post("/search", response_model=SemanticSearchResponse)
async def semantic_search(
    request: SemanticSearchRequest,
    db: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """
    Perform semantic search on page content using vector embeddings
    """
    import time
    start_time = time.time()
    
    try:
        # Validate query
        if not request.query.strip():
            raise HTTPException(status_code=400, detail="Query cannot be empty")
        
        if len(request.query) > 1000:
            raise HTTPException(status_code=400, detail="Query too long (max 1000 characters)")
        
        # Perform semantic search
        results = await semantic_search_service.semantic_search(
            db=db,
            query=request.query.strip(),
            project_id=request.project_id,
            domain_ids=request.domain_ids,
            limit=request.limit,
            min_similarity=request.min_similarity
        )
        
        processing_time = (time.time() - start_time) * 1000
        
        return SemanticSearchResponse(
            results=results,
            total_found=len(results),
            query=request.query.strip(),
            processing_time_ms=round(processing_time, 2)
        )
        
    except Exception as e:
        logger.error(f"Semantic search failed: {e}")
        raise HTTPException(status_code=500, detail="Semantic search failed")


@router.get("/similar/{page_id}")
async def find_similar_content(
    page_id: int,
    limit: int = Query(default=10, ge=1, le=50),
    min_similarity: float = Query(default=0.6, ge=0.0, le=1.0),
    db: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """
    Find content similar to a specific page
    """
    try:
        results = await semantic_search_service.find_similar_content(
            db=db,
            page_id=page_id,
            limit=limit,
            min_similarity=min_similarity
        )
        
        return {
            "page_id": page_id,
            "similar_content": results,
            "total_found": len(results)
        }
        
    except Exception as e:
        logger.error(f"Find similar content failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to find similar content")


@router.post("/embeddings/update")
async def update_embeddings(
    request: EmbeddingUpdateRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """
    Update embeddings for pages (runs in background)
    """
    try:
        # Start background task for embedding updates
        background_tasks.add_task(
            run_embedding_update,
            request.project_id,
            request.domain_id,
            request.batch_size,
            request.force_update
        )
        
        return {
            "message": "Embedding update started in background",
            "project_id": request.project_id,
            "domain_id": request.domain_id,
            "force_update": request.force_update
        }
        
    except Exception as e:
        logger.error(f"Failed to start embedding update: {e}")
        raise HTTPException(status_code=500, detail="Failed to start embedding update")


@router.get("/embeddings/stats")
async def get_embedding_statistics(
    project_id: Optional[int] = Query(default=None),
    db: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """
    Get embedding coverage statistics
    """
    try:
        stats = await semantic_search_service.get_embedding_statistics(
            db=db,
            project_id=project_id
        )
        
        return stats
        
    except Exception as e:
        logger.error(f"Failed to get embedding statistics: {e}")
        raise HTTPException(status_code=500, detail="Failed to get embedding statistics")


@router.post("/embeddings/page/{page_id}")
async def update_page_embedding(
    page_id: int,
    force_update: bool = Query(default=False),
    db: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """
    Update embedding for a specific page
    """
    try:
        success = await semantic_search_service.update_page_embedding(
            db=db,
            page_id=page_id,
            force_update=force_update
        )
        
        if success:
            return {
                "message": "Page embedding updated successfully",
                "page_id": page_id
            }
        else:
            raise HTTPException(status_code=404, detail="Page not found or update failed")
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update page embedding: {e}")
        raise HTTPException(status_code=500, detail="Failed to update page embedding")


async def run_embedding_update(
    project_id: Optional[int],
    domain_id: Optional[int],
    batch_size: int,
    force_update: bool
):
    """
    Background task to update embeddings
    """
    try:
        from app.core.database import get_session
        
        async with get_session() as db:
            stats = await semantic_search_service.batch_update_embeddings(
                db=db,
                project_id=project_id,
                domain_id=domain_id,
                batch_size=batch_size,
                force_update=force_update
            )
            
            logger.info(f"Embedding update completed: {stats}")
            
    except Exception as e:
        logger.error(f"Background embedding update failed: {e}")


@router.get("/model/info")
async def get_model_info(
    current_user: User = Depends(get_current_user)
):
    """
    Get information about the current embedding model
    """
    try:
        return {
            "model_name": semantic_search_service.embedding_model.model_name,
            "dimension": semantic_search_service.embedding_model.dimension,
            "similarity_threshold": semantic_search_service.similarity_threshold
        }
        
    except Exception as e:
        logger.error(f"Failed to get model info: {e}")
        raise HTTPException(status_code=500, detail="Failed to get model information")


@router.post("/model/reload")
async def reload_model(
    current_user: User = Depends(require_admin)
):
    """
    Reload the embedding model (admin only)
    """
    try:
        semantic_search_service.embedding_model.model = None
        semantic_search_service.embedding_model.load_model()
        
        return {
            "message": "Model reloaded successfully",
            "model_name": semantic_search_service.embedding_model.model_name,
            "dimension": semantic_search_service.embedding_model.dimension
        }
        
    except Exception as e:
        logger.error(f"Failed to reload model: {e}")
        raise HTTPException(status_code=500, detail="Failed to reload model")