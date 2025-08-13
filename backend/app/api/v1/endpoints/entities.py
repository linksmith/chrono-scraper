"""
Entity extraction and linking API endpoints
"""
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from app.api.deps import get_current_user, get_db
from app.models.user import User
from app.models.entities import EntityType, EntityStatus
from app.services.entity_extraction import entity_extraction_service

router = APIRouter()


# Pydantic models for request/response
class ExtractEntitiesRequest(BaseModel):
    text: str
    extraction_method: str = "hybrid"  # hybrid, nlp, pattern


class EntityResponse(BaseModel):
    id: int
    entity_type: EntityType
    primary_name: str
    normalized_name: str
    aliases: List[str]
    description: str
    status: EntityStatus
    confidence_score: float
    occurrence_count: int
    attributes: Dict[str, Any]
    first_seen: str
    last_seen: str


class ExtractedEntityResponse(BaseModel):
    id: int
    entity_type: EntityType
    text: str
    normalized_text: str
    start_position: Optional[int]
    end_position: Optional[int]
    context: Optional[str]
    extraction_confidence: float
    linking_confidence: Optional[float]
    canonical_entity_id: Optional[int]
    extracted_at: str


@router.post("/extract", response_model=List[Dict[str, Any]])
async def extract_entities_from_text(
    request: ExtractEntitiesRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Extract entities from text"""
    try:
        # Check if user has entity extraction feature
        from app.services.plan_service import plan_service
        plan = await plan_service.get_or_create_plan(db, current_user)
        
        if not plan.entity_extraction:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Entity extraction not available in your plan"
            )
        
        entities = await entity_extraction_service.extract_entities_from_text(
            request.text, request.extraction_method
        )
        
        # Record usage
        await plan_service.record_usage(
            db, current_user, "entity_extracted", count=len(entities)
        )
        
        return entities
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to extract entities: {str(e)}"
        )


@router.post("/pages/{page_id}/extract")
async def extract_entities_from_page(
    page_id: int,
    extraction_method: str = "hybrid",
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Extract entities from a specific page"""
    try:
        # Check if user has entity extraction feature
        from app.services.plan_service import plan_service
        plan = await plan_service.get_or_create_plan(db, current_user)
        
        if not plan.entity_extraction:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Entity extraction not available in your plan"
            )
        
        # Get page
        from sqlmodel import select
        from app.models.project import Page
        
        result = await db.execute(select(Page).where(Page.id == page_id))
        page = result.scalar_one_or_none()
        
        if not page:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Page not found"
            )
        
        # Check if user owns the page (through project)
        # This is a simplified check - you might want to add proper authorization
        
        # Extract text content from page
        text_content = ""
        if hasattr(page, 'extracted_text') and page.extracted_text:
            text_content = page.extracted_text
        elif hasattr(page, 'content') and page.content:
            text_content = page.content
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Page has no extractable text content"
            )
        
        # Extract and store entities
        extracted_entities = await entity_extraction_service.extract_and_store_entities(
            db, page, text_content, current_user
        )
        
        return {
            "page_id": page_id,
            "entities_extracted": len(extracted_entities),
            "entities": [
                {
                    "id": entity.id,
                    "entity_type": entity.entity_type,
                    "text": entity.text,
                    "confidence": entity.extraction_confidence,
                    "canonical_entity_id": entity.canonical_entity_id,
                }
                for entity in extracted_entities
            ]
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to extract entities from page: {str(e)}"
        )


@router.get("/canonical", response_model=List[EntityResponse])
async def get_canonical_entities(
    entity_type: Optional[EntityType] = Query(None),
    search: Optional[str] = Query(None),
    status_filter: Optional[EntityStatus] = Query(None),
    limit: int = Query(50, le=200),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get canonical entities with filtering"""
    try:
        from sqlmodel import select, or_
        from app.models.entities import CanonicalEntity
        
        query = select(CanonicalEntity)
        
        if entity_type:
            query = query.where(CanonicalEntity.entity_type == entity_type)
        
        if status_filter:
            query = query.where(CanonicalEntity.status == status_filter)
        
        if search:
            search_filter = or_(
                CanonicalEntity.primary_name.contains(search),
                CanonicalEntity.normalized_name.contains(search.lower()),
                CanonicalEntity.description.contains(search)
            )
            query = query.where(search_filter)
        
        query = query.order_by(CanonicalEntity.occurrence_count.desc())
        query = query.limit(limit).offset(offset)
        
        result = await db.execute(query)
        entities = result.scalars().all()
        
        return [
            EntityResponse(
                id=entity.id,
                entity_type=entity.entity_type,
                primary_name=entity.primary_name,
                normalized_name=entity.normalized_name,
                aliases=entity.aliases,
                description=entity.description,
                status=entity.status,
                confidence_score=entity.confidence_score,
                occurrence_count=entity.occurrence_count,
                attributes=entity.attributes,
                first_seen=entity.first_seen.isoformat(),
                last_seen=entity.last_seen.isoformat(),
            )
            for entity in entities
        ]
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get canonical entities: {str(e)}"
        )


@router.get("/canonical/{entity_id}", response_model=EntityResponse)
async def get_canonical_entity(
    entity_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get a specific canonical entity"""
    try:
        from sqlmodel import select
        from app.models.entities import CanonicalEntity
        
        result = await db.execute(
            select(CanonicalEntity).where(CanonicalEntity.id == entity_id)
        )
        entity = result.scalar_one_or_none()
        
        if not entity:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Entity not found"
            )
        
        return EntityResponse(
            id=entity.id,
            entity_type=entity.entity_type,
            primary_name=entity.primary_name,
            normalized_name=entity.normalized_name,
            aliases=entity.aliases,
            description=entity.description,
            status=entity.status,
            confidence_score=entity.confidence_score,
            occurrence_count=entity.occurrence_count,
            attributes=entity.attributes,
            first_seen=entity.first_seen.isoformat(),
            last_seen=entity.last_seen.isoformat(),
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get canonical entity: {str(e)}"
        )


@router.get("/canonical/{entity_id}/mentions", response_model=List[Dict[str, Any]])
async def get_entity_mentions(
    entity_id: int,
    limit: int = Query(50, le=200),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get mentions of a specific entity"""
    try:
        mentions = await entity_extraction_service.get_entity_mentions(
            db, entity_id, limit
        )
        return mentions
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get entity mentions: {str(e)}"
        )


@router.get("/canonical/{entity_id}/relationships", response_model=List[Dict[str, Any]])
async def get_entity_relationships(
    entity_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get relationships for a specific entity"""
    try:
        relationships = await entity_extraction_service.get_entity_relationships(
            db, entity_id
        )
        return relationships
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get entity relationships: {str(e)}"
        )


@router.get("/pages/{page_id}/entities", response_model=List[ExtractedEntityResponse])
async def get_page_entities(
    page_id: int,
    entity_type: Optional[EntityType] = Query(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get entities extracted from a specific page"""
    try:
        from sqlmodel import select
        from app.models.entities import ExtractedEntity
        
        query = select(ExtractedEntity).where(ExtractedEntity.page_id == page_id)
        
        if entity_type:
            query = query.where(ExtractedEntity.entity_type == entity_type)
        
        query = query.order_by(ExtractedEntity.extraction_confidence.desc())
        
        result = await db.execute(query)
        entities = result.scalars().all()
        
        return [
            ExtractedEntityResponse(
                id=entity.id,
                entity_type=entity.entity_type,
                text=entity.text,
                normalized_text=entity.normalized_text,
                start_position=entity.start_position,
                end_position=entity.end_position,
                context=entity.context,
                extraction_confidence=entity.extraction_confidence,
                linking_confidence=entity.linking_confidence,
                canonical_entity_id=entity.canonical_entity_id,
                extracted_at=entity.extracted_at.isoformat(),
            )
            for entity in entities
        ]
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get page entities: {str(e)}"
        )


@router.post("/canonical/{entity_id}/verify")
async def verify_entity(
    entity_id: int,
    verified: bool = True,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Verify or dispute a canonical entity"""
    try:
        from sqlmodel import select
        from app.models.entities import CanonicalEntity
        
        result = await db.execute(
            select(CanonicalEntity).where(CanonicalEntity.id == entity_id)
        )
        entity = result.scalar_one_or_none()
        
        if not entity:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Entity not found"
            )
        
        # Update entity status
        if verified:
            entity.status = EntityStatus.VERIFIED
            entity.verified_by_user_id = current_user.id
            entity.verified_at = datetime.utcnow()
        else:
            entity.status = EntityStatus.DISPUTED
        
        entity.updated_at = datetime.utcnow()
        await db.commit()
        
        return {
            "entity_id": entity_id,
            "status": entity.status,
            "message": f"Entity {'verified' if verified else 'disputed'} successfully"
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to verify entity: {str(e)}"
        )


@router.get("/stats", response_model=Dict[str, Any])
async def get_entity_stats(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get entity extraction statistics"""
    try:
        from sqlmodel import select, func
        from app.models.entities import CanonicalEntity, ExtractedEntity
        
        # Count canonical entities by type
        canonical_counts = {}
        for entity_type in EntityType:
            result = await db.execute(
                select(func.count()).where(
                    CanonicalEntity.entity_type == entity_type
                )
            )
            canonical_counts[entity_type.value] = result.scalar() or 0
        
        # Count extracted entities by type
        extracted_counts = {}
        for entity_type in EntityType:
            result = await db.execute(
                select(func.count()).where(
                    ExtractedEntity.entity_type == entity_type
                )
            )
            extracted_counts[entity_type.value] = result.scalar() or 0
        
        # Get top entities by occurrence
        result = await db.execute(
            select(CanonicalEntity).order_by(
                CanonicalEntity.occurrence_count.desc()
            ).limit(10)
        )
        top_entities = result.scalars().all()
        
        return {
            "canonical_entities": canonical_counts,
            "extracted_entities": extracted_counts,
            "total_canonical": sum(canonical_counts.values()),
            "total_extracted": sum(extracted_counts.values()),
            "top_entities": [
                {
                    "id": entity.id,
                    "name": entity.primary_name,
                    "type": entity.entity_type,
                    "occurrence_count": entity.occurrence_count,
                }
                for entity in top_entities
            ]
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get entity stats: {str(e)}"
        )