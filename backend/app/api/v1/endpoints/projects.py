"""
Project management endpoints
"""
from typing import Any, List, Optional, Dict
from fastapi import APIRouter, Depends, HTTPException, status, Query, Body
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime
import logging

from app.api.deps import get_db, get_current_approved_user, require_permission
from app.models.user import User
from app.models.project import (
    ProjectCreate, 
    ProjectCreateSimplified,
    ProjectUpdate, 
    ProjectRead,
    ProjectReadWithStats,
    ProjectStatus,
    DomainCreate,
    DomainUpdate,
    DomainRead
)
from app.models.rbac import PermissionType
from app.services.projects import ProjectService, DomainService, PageService, ScrapeSessionService
from app.services.meilisearch_service import MeilisearchService
from app.services.langextract_service import langextract_service
from app.services.openrouter_service import openrouter_service

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
    Create new project (full specification)
    """
    project = await ProjectService.create_project(
        db, project_in, current_user.id
    )
    return project


@router.post("/create-with-domains", response_model=ProjectRead)
async def create_project_with_domains(
    *,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(PermissionType.PROJECT_CREATE)),
    project_in: ProjectCreateSimplified = Body(...),
    domains: List[str] = Body(...)
) -> ProjectRead:
    """
    Create new project with LLM-generated name and description based on domains
    """
    try:
        # Generate project name and description using OpenRouter
        name_desc = await openrouter_service.generate_project_name_description(domains)
        
        # Create full project data
        project_data = ProjectCreate(
            name=name_desc.name,
            description=name_desc.description,
            process_documents=project_in.process_documents,
            enable_attachment_download=project_in.enable_attachment_download,
            langextract_enabled=project_in.langextract_enabled,
            langextract_provider=project_in.langextract_provider,
            langextract_model=project_in.langextract_model,
            langextract_estimated_cost_per_1k=project_in.langextract_estimated_cost_per_1k
        )
        
        # Create project
        project = await ProjectService.create_project(
            db, project_data, current_user.id
        )
        
        # Create domains for the project
        from app.models.project import DomainCreate
        for domain_name in domains:
            domain_create = DomainCreate(domain_name=domain_name)
            await DomainService.create_domain(
                db, domain_create, project.id, current_user.id
            )
        
        return project
        
    except Exception as e:
        logger.error(f"Error creating project with domains: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create project: {str(e)}"
        )


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


@router.get("/{project_id}/pages")
async def get_project_pages(
    *,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_approved_user),
    project_id: int,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    search: Optional[str] = Query(None)
) -> List[Dict[str, Any]]:
    """
    Get pages for a project
    """
    pages = await PageService.get_project_pages(
        db, project_id, current_user.id, skip, limit, search
    )

    # Helper to build a snippet around first matched query term
    def build_match_snippet(text: Optional[str], query: Optional[str], max_length: int = 200) -> Optional[str]:
        if not text:
            return None
        if not query:
            return text[:max_length] + "..." if len(text) > max_length else text
        lowered_text = text.lower()
        terms = [t for t in query.split() if t]
        first_index = -1
        match_len = 0
        for term in terms:
            idx = lowered_text.find(term.lower())
            if idx != -1 and (first_index == -1 or idx < first_index):
                first_index = idx
                match_len = len(term)
        if first_index == -1:
            return text[:max_length] + "..." if len(text) > max_length else text
        context = max_length
        start = max(0, first_index - context // 3)
        end = min(len(text), first_index + match_len + (2 * context) // 3)
        snippet = text[start:end].strip()
        if start > 0:
            snippet = "..." + snippet
        if end < len(text):
            snippet = snippet + "..."
        return snippet

    # Convert to dict format for JSON response including snippet and metadata
    response_pages: List[Dict[str, Any]] = []
    for page in pages:
        snippet = build_match_snippet(page.extracted_text, search, 200)
        response_pages.append({
            "id": page.id,
            "url": page.original_url,
            "title": page.title or page.extracted_title,
            "content_type": page.content_type,
            "word_count": page.word_count,
            "content_preview": snippet,
            "capture_date": page.capture_date.isoformat() if getattr(page, 'capture_date', None) else None,
            "scraped_at": page.scraped_at.isoformat() if getattr(page, 'scraped_at', None) else None,
            "status_code": page.status_code,
            "language": page.language,
            "author": page.author,
            "meta_description": page.meta_description,
            "review_status": page.review_status,
            "page_category": page.page_category,
            "priority_level": page.priority_level,
            "tags": page.tags or [],
            "reviewed_at": page.reviewed_at.isoformat() if getattr(page, 'reviewed_at', None) else None,
            "processed": page.processed,
            "indexed": page.indexed,
            "error_message": page.error_message
        })

    return response_pages


@router.get("/{project_id}/stats")
async def get_project_stats(
    *,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_approved_user),
    project_id: int
) -> Dict[str, Any]:
    """
    Get detailed project statistics
    """
    # Verify project ownership
    project = await ProjectService.get_project_by_id(
        db, project_id, current_user.id
    )
    
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found"
        )
    
    # Get basic stats from existing service
    basic_stats = await ProjectService.get_project_stats(db, project_id)
    
    # Get detailed page stats
    page_stats = await PageService.get_project_page_stats(db, project_id)
    
    # Combine stats
    combined_stats = {**basic_stats, **page_stats}
    
    # Add additional computed fields
    combined_stats["total_domains"] = combined_stats.get("domain_count", 0)
    combined_stats["active_sessions"] = 0  # TODO: implement active sessions count
    
    return combined_stats


@router.get("/{project_id}/sessions")
async def get_project_sessions(
    *,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_approved_user),
    project_id: int,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000)
) -> List[Dict[str, Any]]:
    """
    Get scrape sessions for a project
    """
    sessions = await ScrapeSessionService.get_project_sessions(
        db, project_id, current_user.id, skip, limit
    )
    
    # Convert to dict format for JSON response
    return [
        {
            "id": session.id,
            "name": session.session_name,
            "status": session.status,
            "total_urls": session.total_urls,
            "completed_urls": session.completed_urls,
            "failed_urls": session.failed_urls,
            "started_at": session.started_at,
            "completed_at": session.completed_at,
            "created_at": session.created_at,
            "progress": (session.completed_urls / session.total_urls) if session.total_urls > 0 else 0.0,
            "pages_scraped": session.completed_urls,
            "duration": (
                (session.completed_at - session.started_at).total_seconds() 
                if session.started_at and session.completed_at 
                else None
            ),
            "error_message": session.error_message
        }
        for session in sessions
    ]


@router.post("/{project_id}/scrape")
async def start_project_scraping(
    *,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_approved_user),
    project_id: int
) -> Dict[str, Any]:
    """
    Start scraping for a project
    """
    # Verify project ownership
    project = await ProjectService.get_project_by_id(
        db, project_id, current_user.id
    )
    
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found"
        )
    
    # Create a new scrape session
    session = await ScrapeSessionService.create_scrape_session(
        db, project_id, current_user.id
    )
    
    if not session:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create scrape session"
        )
    
    # Update project status to indexing
    await ProjectService.update_project_status(
        db, project_id, ProjectStatus.INDEXING, current_user.id
    )
    
    # Get project domains to scrape
    domains = await DomainService.get_project_domains(
        db, project_id, current_user.id, skip=0, limit=1000
    )
    
    if not domains:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No domains configured for this project. Please add domains before starting scraping."
        )
    
    # Import working Firecrawl scraping tasks
    from app.tasks.firecrawl_scraping import scrape_domain_with_firecrawl
    
    # Start scraping tasks for each domain
    tasks_started = 0
    for domain in domains:
        # Only scrape active domains
        if domain.status == "active":
            # Use the working Firecrawl scraping task
            scrape_domain_with_firecrawl.delay(domain.id, session.id)
            tasks_started += 1
    
    if tasks_started == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No active domains found to scrape."
        )
    
    return {
        "message": f"Scraping started successfully for {tasks_started} domains",
        "session_id": session.id,
        "domains_queued": tasks_started,
        "project_status": ProjectStatus.INDEXING.value
    }


@router.post("/{project_id}/pause")
async def pause_project_scraping(
    *,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_approved_user),
    project_id: int
) -> Dict[str, Any]:
    """
    Pause scraping for a project
    """
    # Verify project ownership
    project = await ProjectService.get_project_by_id(
        db, project_id, current_user.id
    )
    
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found"
        )
    
    # Update project status to paused
    await ProjectService.update_project_status(
        db, project_id, ProjectStatus.PAUSED, current_user.id
    )
    
    # TODO: Add logic to actually pause running scraping tasks
    # For now, just update the status
    
    return {
        "message": "Scraping paused successfully",
        "project_status": ProjectStatus.PAUSED.value
    }


@router.post("/{project_id}/resume")
async def resume_project_scraping(
    *,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_approved_user),
    project_id: int
) -> Dict[str, Any]:
    """
    Resume scraping for a paused project
    """
    # Verify project ownership
    project = await ProjectService.get_project_by_id(
        db, project_id, current_user.id
    )
    
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found"
        )
    
    # Update project status to indexing (resume)
    await ProjectService.update_project_status(
        db, project_id, ProjectStatus.INDEXING, current_user.id
    )
    
    # TODO: Add logic to actually resume scraping tasks
    # For now, just update the status
    
    return {
        "message": "Scraping resumed successfully",
        "project_status": ProjectStatus.INDEXING.value
    }


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


@router.post("/{project_id}/retry-failed")
async def retry_failed_pages(
    *,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_approved_user),
    project_id: int
) -> Dict[str, Any]:
    """
    Retry all failed pages for a project
    """
    # Verify project ownership
    project = await ProjectService.get_project(db, project_id, current_user.id)
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found"
        )
    
    try:
        from app.models.scraping import ScrapePage, ScrapePageStatus
        from app.models.project import ScrapeSession, ScrapeSessionStatus
        from sqlmodel import select
        
        # Get the latest scrape session for this project
        session_result = await db.execute(
            select(ScrapeSession)
            .where(ScrapeSession.project_id == project_id)
            .order_by(ScrapeSession.created_at.desc())
            .limit(1)
        )
        session = session_result.scalar_one_or_none()
        
        if not session:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No scraping session found for this project"
            )
        
        # Get all failed pages for this session
        failed_pages_result = await db.execute(
            select(ScrapePage)
            .where(
                ScrapePage.scrape_session_id == session.id,
                ScrapePage.status == ScrapePageStatus.FAILED
            )
        )
        failed_pages = failed_pages_result.scalars().all()
        
        if not failed_pages:
            return {
                "message": "No failed pages found to retry",
                "pages_to_retry": 0,
                "session_id": session.id
            }
        
        # Reset failed pages to pending status
        retry_count = 0
        for page in failed_pages:
            page.status = ScrapePageStatus.PENDING
            page.error_message = None
            page.error_type = None
            page.retry_count += 1
            page.last_attempt_at = None
            retry_count += 1
        
        await db.commit()
        
        # Import and queue retry tasks
        from app.tasks.scraping_simple import process_page_content
        
        # Queue individual page processing tasks
        for page in failed_pages:
            process_page_content.delay(page.id)
        
        # Broadcast retry started event
        from app.services.websocket_service import broadcast_session_stats_sync
        
        broadcast_session_stats_sync({
            "scrape_session_id": session.id,
            "total_urls": session.total_urls or 0,
            "pending_urls": retry_count,
            "in_progress_urls": 0,
            "completed_urls": session.completed_urls or 0,
            "failed_urls": 0,  # Reset since we're retrying
            "skipped_urls": 0,
            "progress_percentage": ((session.completed_urls or 0) / (session.total_urls or 1)) * 100,
            "active_domains": 1,
            "completed_domains": 0,
            "failed_domains": 0,
            "performance_metrics": {
                "retry_operation": True,
                "pages_queued_for_retry": retry_count
            }
        })
        
        return {
            "message": f"Successfully queued {retry_count} failed pages for retry",
            "pages_to_retry": retry_count,
            "session_id": session.id,
            "status": "retry_queued"
        }
        
    except Exception as e:
        logger.error(f"Error retrying failed pages for project {project_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retry pages: {str(e)}"
        )


@router.post("/{project_id}/pages/{page_id}/retry")
async def retry_single_page(
    *,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_approved_user),
    project_id: int,
    page_id: int
) -> Dict[str, Any]:
    """
    Retry a single failed page
    """
    # Verify project ownership
    project = await ProjectService.get_project(db, project_id, current_user.id)
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found"
        )
    
    try:
        from app.models.scraping import ScrapePage, ScrapePageStatus
        from sqlmodel import select
        
        # Get the specific page
        page_result = await db.execute(
            select(ScrapePage)
            .where(ScrapePage.id == page_id)
        )
        page = page_result.scalar_one_or_none()
        
        if not page:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Page not found"
            )
        
        # Verify the page belongs to this project
        if page.domain_id:
            from app.models.project import Domain
            domain_result = await db.execute(
                select(Domain).where(Domain.id == page.domain_id)
            )
            domain = domain_result.scalar_one_or_none()
            if not domain or domain.project_id != project_id:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Page not found in this project"
                )
        
        # Reset page status for retry
        page.status = ScrapePageStatus.PENDING
        page.error_message = None
        page.error_type = None
        page.retry_count += 1
        page.last_attempt_at = None
        
        await db.commit()
        
        # Queue the page for processing
        from app.tasks.scraping_simple import process_page_content
        process_page_content.delay(page.id)
        
        # Broadcast page retry event
        from app.services.websocket_service import broadcast_page_progress_sync
        
        broadcast_page_progress_sync({
            "scrape_session_id": page.scrape_session_id or 0,
            "scrape_page_id": page.id,
            "domain_id": page.domain_id or 0,
            "domain_name": domain.domain_name if 'domain' in locals() else "unknown",
            "page_url": page.original_url,
            "wayback_url": page.wayback_url or "",
            "status": ScrapePageStatus.PENDING,
            "processing_stage": "retry_queued",
            "stage_progress": 0.0,
            "retry_count": page.retry_count
        })
        
        return {
            "message": "Page successfully queued for retry",
            "page_id": page.id,
            "page_url": page.original_url,
            "retry_count": page.retry_count,
            "status": "retry_queued"
        }
        
    except Exception as e:
        logger.error(f"Error retrying page {page_id} for project {project_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retry page: {str(e)}"
        )


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