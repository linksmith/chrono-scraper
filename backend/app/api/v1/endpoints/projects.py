"""
Project management endpoints
"""
from typing import Any, List, Optional, Dict
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime
import logging

from app.api.deps import get_db, get_current_approved_user, require_permission
from app.models.user import User
from app.models.project import (
    ProjectCreate, 
    ProjectUpdate, 
    ProjectRead,
    ProjectReadWithStats,
    ProjectStatus,
    DomainCreate,
    DomainUpdate,
    DomainRead
)
from app.models.rbac import PermissionType
from app.services.projects import ProjectService, DomainService
from app.services.meilisearch_service import MeilisearchService
from app.services.langextract_service import langextract_service

logger = logging.getLogger(__name__)
router = APIRouter()


@router.put("/{project_id}", response_model=ProjectRead)
async def update_project(
    *,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_approved_user),
    project_id: int,
    project_in: ProjectUpdate
) -> ProjectRead:
    """
    Update project
    """
    project = await ProjectService.update_project(
        db, project_id, project_in, current_user.id
    )
    
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found"
        )
    
    return project


@router.delete("/{project_id}")
async def delete_project(
    *,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_approved_user),
    project_id: int
) -> dict:
    """
    Delete project
    """
    success = await ProjectService.delete_project(
        db, project_id, current_user.id
    )
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found"
        )
    
    return {"message": "Project deleted successfully"}


@router.patch("/{project_id}/status")
async def update_project_status(
    *,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_approved_user),
    project_id: int,
    status: ProjectStatus
) -> ProjectRead:
    """
    Update project status
    """
    project = await ProjectService.update_project_status(
        db, project_id, status, current_user.id
    )
    
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found"
        )
    
    return project


@router.get("/", response_model=List[ProjectReadWithStats])
async def read_projects(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_approved_user),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    search: Optional[str] = Query(None)
) -> List[ProjectReadWithStats]:
    """
    Retrieve user's projects with statistics
    """
    projects = await ProjectService.get_projects_with_stats(
        db, user_id=current_user.id, skip=skip, limit=limit
    )
    return projects


@router.post("/", response_model=ProjectRead)
async def create_project(
    *,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(PermissionType.PROJECT_CREATE)),
    project_in: ProjectCreate
) -> ProjectRead:
    """
    Create new project
    """
    project = await ProjectService.create_project(
        db, project_in, current_user.id
    )
    return project


@router.get("/{project_id}", response_model=ProjectReadWithStats)
async def read_project(
    *,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_approved_user),
    project_id: int
) -> ProjectReadWithStats:
    """
    Get project by ID with statistics
    """
    project = await ProjectService.get_project_by_id(
        db, project_id, current_user.id
    )
    
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found"
        )
    
    # Get project statistics
    stats = await ProjectService.get_project_stats(db, project_id)
    
    project_dict = project.model_dump()
    project_dict.update(stats)
    
    return ProjectReadWithStats(**project_dict)


@router.put("/{project_id}", response_model=ProjectRead)
async def update_project(
    *,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_approved_user),
    project_id: int,
    project_in: ProjectUpdate
) -> ProjectRead:
    """
    Update project
    """
    project = await ProjectService.update_project(
        db, project_id, project_in, current_user.id
    )
    
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found"
        )
    
    return project


@router.delete("/{project_id}")
async def delete_project(
    *,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_approved_user),
    project_id: int
) -> dict:
    """
    Delete project
    """
    success = await ProjectService.delete_project(
        db, project_id, current_user.id
    )
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found"
        )
    
    return {"message": "Project deleted successfully"}


@router.patch("/{project_id}/status")
async def update_project_status(
    *,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_approved_user),
    project_id: int,
    status: ProjectStatus
) -> ProjectRead:
    """
    Update project status
    """
    project = await ProjectService.update_project_status(
        db, project_id, status, current_user.id
    )
    
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found"
        )
    
    return project


# Domain endpoints
@router.get("/{project_id}/domains", response_model=List[DomainRead])
async def get_project_domains(
    *,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_approved_user),
    project_id: int,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000)
) -> List[DomainRead]:
    """
    Get domains for a project
    """
    domains = await DomainService.get_project_domains(
        db, project_id, current_user.id, skip, limit
    )
    return domains


@router.post("/{project_id}/domains", response_model=DomainRead)
async def create_project_domain(
    *,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(PermissionType.DOMAIN_CREATE)),
    project_id: int,
    domain_in: DomainCreate
) -> DomainRead:
    """
    Create domain for project
    """
    domain = await DomainService.create_domain(
        db, domain_in, project_id, current_user.id
    )
    
    if not domain:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found"
        )
    
    return domain


@router.put("/{project_id}/domains/{domain_id}", response_model=DomainRead)
async def update_project_domain(
    *,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_approved_user),
    project_id: int,
    domain_id: int,
    domain_in: DomainUpdate
) -> DomainRead:
    """
    Update domain
    """
    domain = await DomainService.update_domain(
        db, domain_id, domain_in, current_user.id
    )
    
    if not domain:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Domain not found"
        )
    
    return domain


@router.delete("/{project_id}/domains/{domain_id}")
async def delete_project_domain(
    *,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_approved_user),
    project_id: int,
    domain_id: int
) -> dict:
    """
    Delete domain
    """
    success = await DomainService.delete_domain(
        db, domain_id, current_user.id
    )
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Domain not found"
        )
    
    return {"message": "Domain deleted successfully"}


# Meilisearch endpoints
@router.get("/{project_id}/search")
async def search_project(
    *,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_approved_user),
    project_id: int,
    q: str = Query(..., description="Search query"),
    filters: Optional[str] = Query(None, description="Search filters"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0)
) -> dict:
    """
    Search project documents
    """
    project = await ProjectService.get_project_by_id(
        db, project_id, current_user.id
    )
    
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found"
        )
    
    try:
        results = await MeilisearchService.search(
            project, q, filters, None, limit, offset
        )
        return results
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Search failed: {str(e)}"
        )


@router.get("/{project_id}/index/stats")
async def get_project_index_stats(
    *,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_approved_user),
    project_id: int
) -> dict:
    """
    Get project index statistics
    """
    project = await ProjectService.get_project_by_id(
        db, project_id, current_user.id
    )
    
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found"
        )
    
    stats = await MeilisearchService.get_index_stats(project)
    return stats


@router.post("/{project_id}/index/rebuild")
async def rebuild_project_index(
    *,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(PermissionType.PROJECT_MANAGE)),
    project_id: int
) -> dict:
    """
    Rebuild project index
    """
    project = await ProjectService.get_project_by_id(
        db, project_id, current_user.id
    )
    
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found"
        )
    
    success = await MeilisearchService.rebuild_index(project)
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to rebuild index"
        )
    
    return {"message": "Index rebuild initiated"}


# LangExtract endpoints
@router.get("/langextract/models")
async def get_langextract_models(
    current_user: User = Depends(get_current_approved_user)
) -> List[Dict[str, Any]]:
    """
    Get available LangExtract models with cost estimates
    """
    models = await langextract_service.get_available_models()
    return models


@router.post("/langextract/cost-estimate")
async def estimate_langextract_cost(
    *,
    current_user: User = Depends(get_current_approved_user),
    model_id: str,
    domains: List[str],
    estimated_pages: Optional[int] = None
) -> Dict[str, Any]:
    """
    Calculate cost estimate for LangExtract processing
    """
    # If no page count provided, estimate from domains
    if estimated_pages is None:
        estimated_pages = await langextract_service.estimate_pages_from_domains(domains)
    
    cost_estimate = await langextract_service.calculate_project_cost(
        model_id, estimated_pages
    )
    
    if not cost_estimate:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid model ID or unable to calculate cost"
        )
    
    return cost_estimate


@router.post("/cost-estimation")
async def estimate_project_costs(
    *,
    current_user: User = Depends(get_current_approved_user),
    domain_name: str,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    extraction_enabled: bool = False,
    model_name: Optional[str] = None,
    match_type: str = "domain",
    url_path: Optional[str] = None
) -> Dict[str, Any]:
    """
    Comprehensive project cost estimation with CDX integration and caching
    
    Args:
        domain_name: Domain to scrape (e.g., "example.com")
        from_date: Start date in YYYYMMDD format (optional)
        to_date: End date in YYYYMMDD format (optional)
        extraction_enabled: Whether extraction is enabled (optional)
        model_name: OpenRouter model to use (optional)
        match_type: Type of matching ("domain" or "prefix")
        url_path: Optional URL path filter
    """
    if not domain_name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="domain_name is required"
        )
    
    # Validate date formats if provided
    if from_date and not _is_valid_date_format(from_date):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="from_date must be in YYYYMMDD format"
        )
    
    if to_date and not _is_valid_date_format(to_date):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="to_date must be in YYYYMMDD format"
        )
    
    try:
        # Get comprehensive cost estimation
        estimate = await langextract_service.estimate_project_costs(
            domain_name=domain_name,
            from_date=from_date,
            to_date=to_date,
            extraction_enabled=extraction_enabled,
            model_name=model_name,
            match_type=match_type,
            url_path=url_path
        )
        
        # Add request metadata
        estimate['request_info'] = {
            'user_id': current_user.id,
            'user_email': current_user.email,
            'request_timestamp': estimate.get('last_updated')
        }
        
        return estimate
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error in cost estimation: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error during cost estimation"
        )


@router.post("/validate-domain")
async def validate_domain(
    *,
    current_user: User = Depends(get_current_approved_user),
    domain_name: str,
    quick_check: bool = True
) -> Dict[str, Any]:
    """
    Validate a domain name and check if it has archived data
    
    Args:
        domain_name: Domain to validate
        quick_check: If True, only check last year of data
    """
    if not domain_name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="domain_name is required"
        )
    
    try:
        result = await langextract_service.validate_domain(domain_name, quick_check)
        return result
        
    except Exception as e:
        logger.error(f"Error validating domain: {str(e)}")
        return {
            'domain_name': domain_name,
            'is_valid': False,
            'error': 'Unable to validate domain'
        }


@router.get("/pricing-info")
async def get_pricing_info(
    current_user: User = Depends(get_current_approved_user)
) -> Dict[str, Any]:
    """
    Get current pricing information for OpenRouter models and processing estimates
    """
    return {
        'openrouter_models': await langextract_service.get_available_models(),
        'processing_estimates': langextract_service.PROCESSING_TIME_ESTIMATES,
        'cache_settings': langextract_service.CACHE_SETTINGS,
        'last_updated': datetime.now().isoformat()
    }


def _is_valid_date_format(date_string: str) -> bool:
    """Validate YYYYMMDD date format"""
    if not isinstance(date_string, str) or len(date_string) != 8:
        return False
    
    try:
        int(date_string)
        # Basic range validation
        year = int(date_string[:4])
        month = int(date_string[4:6])
        day = int(date_string[6:8])
        
        return (1990 <= year <= 2030 and 
                1 <= month <= 12 and 
                1 <= day <= 31)
    except ValueError:
        return False