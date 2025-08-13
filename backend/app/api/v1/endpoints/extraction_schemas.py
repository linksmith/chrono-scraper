"""
Content extraction schemas API endpoints
"""
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from app.api.deps import get_current_user, get_db
from app.models.user import User
from app.models.project import Page
from app.models.extraction_schemas import (
    ContentExtractionSchema,
    ContentExtraction,
    ExtractionTemplate,
    ExtractionJob,
    ContentExtractionSchemaCreate,
    ContentExtractionSchemaUpdate,
    ContentExtractionSchemaRead,
    ContentExtractionCreate,
    ContentExtractionRead,
    ExtractionTemplateCreate,
    ExtractionTemplateRead,
    ExtractionJobCreate,
    ExtractionJobRead,
    SchemaType,
    ExtractionStatus,
    ExtractionMethod
)
from app.services.extraction_service import extraction_service

router = APIRouter()


# Pydantic models for request/response
class ExtractContentRequest(BaseModel):
    page_id: int
    schema_id: int
    content: Optional[str] = None


class CreateTemplateRequest(BaseModel):
    schema_id: int
    name: str
    description: str
    category: str
    use_cases: List[str] = []
    supported_domains: List[str] = []
    tags: List[str] = []


class BatchExtractionRequest(BaseModel):
    schema_id: int
    page_filters: Dict[str, Any] = {}
    batch_size: int = 10
    auto_validate: bool = False


# Content Extraction Schema endpoints
@router.post("/schemas", response_model=ContentExtractionSchemaRead)
async def create_extraction_schema(
    schema_data: ContentExtractionSchemaCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Create a new content extraction schema"""
    try:
        # Check if user has advanced extraction feature
        from app.services.plan_service import plan_service
        plan = await plan_service.get_or_create_plan(db, current_user)
        
        if not plan.advanced_extraction:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Advanced extraction not available in your plan"
            )
        
        schema = await extraction_service.create_schema(
            db=db,
            user=current_user,
            name=schema_data.name,
            description=schema_data.description,
            schema_type=schema_data.schema_type,
            field_definitions=schema_data.field_definitions,
            extraction_method=schema_data.extraction_method,
            extraction_rules=schema_data.extraction_rules,
            css_selectors=schema_data.css_selectors,
            xpath_selectors=schema_data.xpath_selectors,
            llm_prompt_template=schema_data.llm_prompt_template,
            llm_model=schema_data.llm_model,
            validation_rules=schema_data.validation_rules,
            confidence_threshold=schema_data.confidence_threshold
        )
        
        return ContentExtractionSchemaRead(
            id=schema.id,
            user_id=schema.user_id,
            name=schema.name,
            description=schema.description,
            schema_type=schema.schema_type,
            field_definitions=schema.field_definitions,
            extraction_method=schema.extraction_method,
            extraction_rules=schema.extraction_rules,
            css_selectors=schema.css_selectors,
            xpath_selectors=schema.xpath_selectors,
            llm_prompt_template=schema.llm_prompt_template,
            llm_model=schema.llm_model,
            validation_rules=schema.validation_rules,
            confidence_threshold=schema.confidence_threshold,
            is_active=schema.is_active,
            is_public=schema.is_public,
            usage_count=schema.usage_count,
            success_rate=schema.success_rate,
            avg_confidence=schema.avg_confidence,
            version=schema.version,
            created_at=schema.created_at,
            updated_at=schema.updated_at
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create extraction schema: {str(e)}"
        )


@router.get("/schemas", response_model=List[ContentExtractionSchemaRead])
async def get_extraction_schemas(
    schema_type: Optional[SchemaType] = Query(None),
    is_active: bool = Query(True),
    limit: int = Query(50, le=200),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get user's content extraction schemas"""
    try:
        schemas = await extraction_service.get_user_schemas(
            db, current_user, schema_type, is_active, limit, offset
        )
        
        return [
            ContentExtractionSchemaRead(
                id=schema.id,
                user_id=schema.user_id,
                name=schema.name,
                description=schema.description,
                schema_type=schema.schema_type,
                field_definitions=schema.field_definitions,
                extraction_method=schema.extraction_method,
                extraction_rules=schema.extraction_rules,
                css_selectors=schema.css_selectors,
                xpath_selectors=schema.xpath_selectors,
                llm_prompt_template=schema.llm_prompt_template,
                llm_model=schema.llm_model,
                validation_rules=schema.validation_rules,
                confidence_threshold=schema.confidence_threshold,
                is_active=schema.is_active,
                is_public=schema.is_public,
                usage_count=schema.usage_count,
                success_rate=schema.success_rate,
                avg_confidence=schema.avg_confidence,
                version=schema.version,
                created_at=schema.created_at,
                updated_at=schema.updated_at
            )
            for schema in schemas
        ]
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get extraction schemas: {str(e)}"
        )


@router.get("/schemas/public", response_model=List[ContentExtractionSchemaRead])
async def get_public_schemas(
    schema_type: Optional[SchemaType] = Query(None),
    limit: int = Query(50, le=200),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get public content extraction schemas"""
    try:
        schemas = await extraction_service.get_public_schemas(
            db, schema_type, limit, offset
        )
        
        return [
            ContentExtractionSchemaRead(
                id=schema.id,
                user_id=schema.user_id,
                name=schema.name,
                description=schema.description,
                schema_type=schema.schema_type,
                field_definitions=schema.field_definitions,
                extraction_method=schema.extraction_method,
                extraction_rules=schema.extraction_rules,
                css_selectors=schema.css_selectors,
                xpath_selectors=schema.xpath_selectors,
                llm_prompt_template=schema.llm_prompt_template,
                llm_model=schema.llm_model,
                validation_rules=schema.validation_rules,
                confidence_threshold=schema.confidence_threshold,
                is_active=schema.is_active,
                is_public=schema.is_public,
                usage_count=schema.usage_count,
                success_rate=schema.success_rate,
                avg_confidence=schema.avg_confidence,
                version=schema.version,
                created_at=schema.created_at,
                updated_at=schema.updated_at
            )
            for schema in schemas
        ]
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get public schemas: {str(e)}"
        )


@router.put("/schemas/{schema_id}", response_model=ContentExtractionSchemaRead)
async def update_extraction_schema(
    schema_id: int,
    schema_update: ContentExtractionSchemaUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Update a content extraction schema"""
    try:
        # Convert Pydantic model to dict, excluding None values
        updates = schema_update.dict(exclude_unset=True)
        
        schema = await extraction_service.update_schema(
            db, current_user, schema_id, updates
        )
        
        if not schema:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Extraction schema not found"
            )
        
        return ContentExtractionSchemaRead(
            id=schema.id,
            user_id=schema.user_id,
            name=schema.name,
            description=schema.description,
            schema_type=schema.schema_type,
            field_definitions=schema.field_definitions,
            extraction_method=schema.extraction_method,
            extraction_rules=schema.extraction_rules,
            css_selectors=schema.css_selectors,
            xpath_selectors=schema.xpath_selectors,
            llm_prompt_template=schema.llm_prompt_template,
            llm_model=schema.llm_model,
            validation_rules=schema.validation_rules,
            confidence_threshold=schema.confidence_threshold,
            is_active=schema.is_active,
            is_public=schema.is_public,
            usage_count=schema.usage_count,
            success_rate=schema.success_rate,
            avg_confidence=schema.avg_confidence,
            version=schema.version,
            created_at=schema.created_at,
            updated_at=schema.updated_at
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update extraction schema: {str(e)}"
        )


# Content Extraction endpoints
@router.post("/extract", response_model=ContentExtractionRead)
async def extract_content(
    request: ExtractContentRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Extract structured content from a page using a schema"""
    try:
        # Check if user has advanced extraction feature
        from app.services.plan_service import plan_service
        plan = await plan_service.get_or_create_plan(db, current_user)
        
        if not plan.advanced_extraction:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Advanced extraction not available in your plan"
            )
        
        # Get page and schema
        from sqlmodel import select
        
        page_result = await db.execute(select(Page).where(Page.id == request.page_id))
        page = page_result.scalar_one_or_none()
        
        if not page:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Page not found"
            )
        
        schema_result = await db.execute(
            select(ContentExtractionSchema).where(ContentExtractionSchema.id == request.schema_id)
        )
        schema = schema_result.scalar_one_or_none()
        
        if not schema:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Extraction schema not found"
            )
        
        # Perform extraction
        extraction = await extraction_service.extract_content_with_schema(
            db, current_user, page, schema, request.content
        )
        
        # Record usage
        await plan_service.record_usage(
            db, current_user, "content_extracted", count=1
        )
        
        return ContentExtractionRead(
            id=extraction.id,
            page_id=extraction.page_id,
            schema_id=extraction.schema_id,
            user_id=extraction.user_id,
            status=extraction.status,
            extraction_method=extraction.extraction_method,
            extracted_data=extraction.extracted_data,
            extraction_metadata=extraction.extraction_metadata,
            confidence_score=extraction.confidence_score,
            completeness_score=extraction.completeness_score,
            validation_score=extraction.validation_score,
            extraction_time_ms=extraction.extraction_time_ms,
            tokens_used=extraction.tokens_used,
            model_version=extraction.model_version,
            requires_review=extraction.requires_review,
            is_validated=extraction.is_validated,
            validation_notes=extraction.validation_notes,
            extracted_at=extraction.extracted_at,
            updated_at=extraction.updated_at
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to extract content: {str(e)}"
        )


@router.get("/extractions", response_model=List[ContentExtractionRead])
async def get_content_extractions(
    schema_id: Optional[int] = Query(None),
    page_id: Optional[int] = Query(None),
    status_filter: Optional[ExtractionStatus] = Query(None),
    limit: int = Query(50, le=200),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get user's content extractions"""
    try:
        from sqlmodel import select, and_
        
        query = select(ContentExtraction).where(
            ContentExtraction.user_id == current_user.id
        )
        
        if schema_id:
            query = query.where(ContentExtraction.schema_id == schema_id)
        
        if page_id:
            query = query.where(ContentExtraction.page_id == page_id)
        
        if status_filter:
            query = query.where(ContentExtraction.status == status_filter)
        
        query = query.order_by(ContentExtraction.extracted_at.desc())
        query = query.limit(limit).offset(offset)
        
        result = await db.execute(query)
        extractions = result.scalars().all()
        
        return [
            ContentExtractionRead(
                id=extraction.id,
                page_id=extraction.page_id,
                schema_id=extraction.schema_id,
                user_id=extraction.user_id,
                status=extraction.status,
                extraction_method=extraction.extraction_method,
                extracted_data=extraction.extracted_data,
                extraction_metadata=extraction.extraction_metadata,
                confidence_score=extraction.confidence_score,
                completeness_score=extraction.completeness_score,
                validation_score=extraction.validation_score,
                extraction_time_ms=extraction.extraction_time_ms,
                tokens_used=extraction.tokens_used,
                model_version=extraction.model_version,
                requires_review=extraction.requires_review,
                is_validated=extraction.is_validated,
                validation_notes=extraction.validation_notes,
                extracted_at=extraction.extracted_at,
                updated_at=extraction.updated_at
            )
            for extraction in extractions
        ]
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get content extractions: {str(e)}"
        )


@router.post("/extractions/{extraction_id}/validate")
async def validate_extraction(
    extraction_id: int,
    is_valid: bool = True,
    validation_notes: str = "",
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Validate a content extraction"""
    try:
        from sqlmodel import select
        from datetime import datetime
        
        result = await db.execute(
            select(ContentExtraction).where(
                ContentExtraction.id == extraction_id,
                ContentExtraction.user_id == current_user.id
            )
        )
        extraction = result.scalar_one_or_none()
        
        if not extraction:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Content extraction not found"
            )
        
        extraction.is_validated = is_valid
        extraction.validation_notes = validation_notes
        extraction.validated_by_user_id = current_user.id
        extraction.validated_at = datetime.utcnow()
        extraction.status = ExtractionStatus.VALIDATED if is_valid else ExtractionStatus.DISPUTED
        
        await db.commit()
        
        return {
            "extraction_id": extraction_id,
            "is_validated": is_valid,
            "message": f"Extraction {'validated' if is_valid else 'disputed'} successfully"
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to validate extraction: {str(e)}"
        )


# Template endpoints
@router.post("/templates", response_model=ExtractionTemplateRead)
async def create_extraction_template(
    request: CreateTemplateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Create a reusable extraction template from a schema"""
    try:
        from sqlmodel import select
        
        # Get schema
        result = await db.execute(
            select(ContentExtractionSchema).where(
                ContentExtractionSchema.id == request.schema_id,
                ContentExtractionSchema.user_id == current_user.id
            )
        )
        schema = result.scalar_one_or_none()
        
        if not schema:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Extraction schema not found"
            )
        
        template = await extraction_service.create_template_from_schema(
            db, current_user, schema, request.name, request.description,
            request.category, request.use_cases, request.supported_domains, request.tags
        )
        
        return ExtractionTemplateRead(
            id=template.id,
            created_by_user_id=template.created_by_user_id,
            schema_id=template.schema_id,
            name=template.name,
            description=template.description,
            category=template.category,
            template_config=template.template_config,
            example_data=template.example_data,
            use_cases=template.use_cases,
            supported_domains=template.supported_domains,
            tags=template.tags,
            is_public=template.is_public,
            is_featured=template.is_featured,
            download_count=template.download_count,
            rating=template.rating,
            created_at=template.created_at,
            updated_at=template.updated_at
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create extraction template: {str(e)}"
        )


@router.get("/templates", response_model=List[ExtractionTemplateRead])
async def get_extraction_templates(
    category: Optional[str] = Query(None),
    tags: Optional[List[str]] = Query(None),
    is_featured: bool = Query(False),
    limit: int = Query(50, le=200),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get available extraction templates"""
    try:
        templates = await extraction_service.get_templates(
            db, category, tags, is_featured, limit, offset
        )
        
        return [
            ExtractionTemplateRead(
                id=template.id,
                created_by_user_id=template.created_by_user_id,
                schema_id=template.schema_id,
                name=template.name,
                description=template.description,
                category=template.category,
                template_config=template.template_config,
                example_data=template.example_data,
                use_cases=template.use_cases,
                supported_domains=template.supported_domains,
                tags=template.tags,
                is_public=template.is_public,
                is_featured=template.is_featured,
                download_count=template.download_count,
                rating=template.rating,
                created_at=template.created_at,
                updated_at=template.updated_at
            )
            for template in templates
        ]
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get extraction templates: {str(e)}"
        )


@router.get("/schema-types", response_model=List[Dict[str, str]])
async def get_schema_types():
    """Get available schema types"""
    return [
        {"value": schema_type.value, "label": schema_type.value.replace("_", " ").title()}
        for schema_type in SchemaType
    ]


@router.get("/extraction-methods", response_model=List[Dict[str, str]])
async def get_extraction_methods():
    """Get available extraction methods"""
    return [
        {"value": method.value, "label": method.value.replace("_", " ").title()}
        for method in ExtractionMethod
    ]


@router.get("/stats", response_model=Dict[str, Any])
async def get_extraction_stats(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get extraction statistics for user"""
    try:
        from sqlmodel import select, func
        
        # Count schemas by type
        schema_counts = {}
        for schema_type in SchemaType:
            result = await db.execute(
                select(func.count()).where(
                    and_(
                        ContentExtractionSchema.user_id == current_user.id,
                        ContentExtractionSchema.schema_type == schema_type,
                        ContentExtractionSchema.is_active == True
                    )
                )
            )
            schema_counts[schema_type.value] = result.scalar() or 0
        
        # Count extractions by status
        extraction_counts = {}
        for status in ExtractionStatus:
            result = await db.execute(
                select(func.count()).where(
                    and_(
                        ContentExtraction.user_id == current_user.id,
                        ContentExtraction.status == status
                    )
                )
            )
            extraction_counts[status.value] = result.scalar() or 0
        
        # Get average confidence score
        result = await db.execute(
            select(func.avg(ContentExtraction.confidence_score)).where(
                and_(
                    ContentExtraction.user_id == current_user.id,
                    ContentExtraction.status == ExtractionStatus.COMPLETED
                )
            )
        )
        avg_confidence = result.scalar() or 0.0
        
        # Get most used schema
        result = await db.execute(
            select(ContentExtractionSchema.name, func.count(ContentExtraction.id).label('usage_count')).
            join(ContentExtraction).
            where(ContentExtractionSchema.user_id == current_user.id).
            group_by(ContentExtractionSchema.id, ContentExtractionSchema.name).
            order_by(func.count(ContentExtraction.id).desc()).
            limit(1)
        )
        most_used = result.first()
        
        return {
            "schemas_by_type": schema_counts,
            "extractions_by_status": extraction_counts,
            "total_schemas": sum(schema_counts.values()),
            "total_extractions": sum(extraction_counts.values()),
            "avg_confidence": float(avg_confidence),
            "most_used_schema": {
                "name": most_used[0] if most_used else None,
                "usage_count": most_used[1] if most_used else 0
            }
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get extraction stats: {str(e)}"
        )