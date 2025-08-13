"""
Project management services
"""
from typing import List, Optional
from datetime import datetime
from sqlmodel import select, and_, func, desc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.project import (
    Project, 
    ProjectCreate, 
    ProjectUpdate,
    ProjectRead,
    ProjectReadWithStats,
    ProjectStatus,
    Domain,
    DomainCreate,
    DomainUpdate,
    DomainRead,
    Page,
    ScrapeSession,
    ScrapeSessionStatus
)
from app.models.user import User
from app.services.meilisearch_service import MeilisearchService


class ProjectService:
    """Service for project operations"""
    
    @staticmethod
    async def create_project(
        db: AsyncSession, 
        project_create: ProjectCreate, 
        user_id: int
    ) -> Project:
        """Create a new project"""
        project_data = project_create.model_dump()
        project_data["user_id"] = user_id
        
        project = Project(**project_data)
        db.add(project)
        await db.commit()
        await db.refresh(project)
        
        # Create Meilisearch index for the project
        if project.process_documents:
            try:
                await MeilisearchService.create_project_index(project)
            except Exception as e:
                # Log error but don't fail project creation
                print(f"Failed to create Meilisearch index for project {project.id}: {e}")
        
        return project
    
    @staticmethod
    async def get_project_by_id(
        db: AsyncSession, 
        project_id: int, 
        user_id: Optional[int] = None
    ) -> Optional[Project]:
        """Get project by ID"""
        query = select(Project).where(Project.id == project_id)
        
        # If user_id is provided, check ownership
        if user_id is not None:
            query = query.where(Project.user_id == user_id)
        
        result = await db.execute(query)
        return result.scalar_one_or_none()
    
    @staticmethod
    async def get_projects(
        db: AsyncSession,
        user_id: Optional[int] = None,
        skip: int = 0,
        limit: int = 100,
        search: Optional[str] = None
    ) -> List[Project]:
        """Get projects with optional filtering"""
        query = select(Project)
        
        # Filter by user if provided
        if user_id is not None:
            query = query.where(Project.user_id == user_id)
        
        # Search filter
        if search:
            query = query.where(
                Project.name.ilike(f"%{search}%") |
                Project.description.ilike(f"%{search}%")
            )
        
        # Order by created_at desc and apply pagination
        query = query.order_by(desc(Project.created_at)).offset(skip).limit(limit)
        
        result = await db.execute(query)
        return result.scalars().all()
    
    @staticmethod
    async def get_projects_with_stats(
        db: AsyncSession,
        user_id: Optional[int] = None,
        skip: int = 0,
        limit: int = 100
    ) -> List[ProjectReadWithStats]:
        """Get projects with statistics"""
        projects = await ProjectService.get_projects(db, user_id, skip, limit)
        projects_with_stats = []
        
        for project in projects:
            stats = await ProjectService.get_project_stats(db, project.id)
            project_dict = project.model_dump()
            project_dict.update(stats)
            projects_with_stats.append(ProjectReadWithStats(**project_dict))
        
        return projects_with_stats
    
    @staticmethod
    async def get_project_stats(db: AsyncSession, project_id: int) -> dict:
        """Get project statistics"""
        # Count domains
        domain_count_result = await db.execute(
            select(func.count(Domain.id)).where(Domain.project_id == project_id)
        )
        domain_count = domain_count_result.scalar() or 0
        
        # Count total pages
        total_pages_result = await db.execute(
            select(func.sum(Domain.total_pages))
            .where(Domain.project_id == project_id)
        )
        total_pages = total_pages_result.scalar() or 0
        
        # Count scraped pages
        scraped_pages_result = await db.execute(
            select(func.sum(Domain.scraped_pages))
            .where(Domain.project_id == project_id)
        )
        scraped_pages = scraped_pages_result.scalar() or 0
        
        # Get last scraped date
        last_scraped_result = await db.execute(
            select(func.max(Domain.last_scraped))
            .where(Domain.project_id == project_id)
        )
        last_scraped = last_scraped_result.scalar()
        
        return {
            "domain_count": domain_count,
            "total_pages": int(total_pages),
            "scraped_pages": int(scraped_pages),
            "last_scraped": last_scraped
        }
    
    @staticmethod
    async def update_project(
        db: AsyncSession, 
        project_id: int, 
        project_update: ProjectUpdate,
        user_id: int
    ) -> Optional[Project]:
        """Update project"""
        project = await ProjectService.get_project_by_id(db, project_id, user_id)
        if not project:
            return None
        
        # Update fields
        update_data = project_update.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(project, field, value)
        
        await db.commit()
        await db.refresh(project)
        
        # Update Meilisearch index if needed
        if "process_documents" in update_data:
            try:
                if project.process_documents:
                    await MeilisearchService.create_project_index(project)
                else:
                    await MeilisearchService.delete_project_index(project)
            except Exception as e:
                print(f"Failed to update Meilisearch index for project {project.id}: {e}")
        
        return project
    
    @staticmethod
    async def delete_project(
        db: AsyncSession, 
        project_id: int, 
        user_id: int
    ) -> bool:
        """Delete project and all related data"""
        project = await ProjectService.get_project_by_id(db, project_id, user_id)
        if not project:
            return False
        
        # Delete Meilisearch index
        try:
            await MeilisearchService.delete_project_index(project)
        except Exception as e:
            print(f"Failed to delete Meilisearch index for project {project.id}: {e}")
        
        # Delete project (cascading deletes will handle related data)
        await db.delete(project)
        await db.commit()
        
        return True
    
    @staticmethod
    async def update_project_status(
        db: AsyncSession,
        project_id: int,
        status: ProjectStatus,
        user_id: int
    ) -> Optional[Project]:
        """Update project status"""
        project = await ProjectService.get_project_by_id(db, project_id, user_id)
        if not project:
            return None
        
        project.status = status
        await db.commit()
        await db.refresh(project)
        
        return project


class DomainService:
    """Service for domain operations"""
    
    @staticmethod
    async def create_domain(
        db: AsyncSession,
        domain_create: DomainCreate,
        project_id: int,
        user_id: int
    ) -> Optional[Domain]:
        """Create a new domain"""
        from datetime import datetime
        
        # Verify project ownership
        project = await ProjectService.get_project_by_id(db, project_id, user_id)
        if not project:
            return None
        
        domain_data = domain_create.model_dump(exclude={"date_range_start", "date_range_end", "include_subdomains", "exclude_patterns", "include_patterns"})
        domain_data["project_id"] = project_id
        
        # Handle date range conversion
        if domain_create.date_range_start:
            try:
                domain_data["from_date"] = datetime.strptime(domain_create.date_range_start, "%Y-%m-%d")
            except ValueError:
                pass  # Invalid date format, skip
        
        if domain_create.date_range_end:
            try:
                domain_data["to_date"] = datetime.strptime(domain_create.date_range_end, "%Y-%m-%d")
            except ValueError:
                pass  # Invalid date format, skip
        
        # Handle subdomain inclusion in match_type
        if domain_create.include_subdomains:
            domain_data["match_type"] = MatchType.DOMAIN
        else:
            domain_data["match_type"] = MatchType.EXACT
        
        # Note: exclude_patterns and include_patterns would typically be stored
        # in a separate table or as JSON, but for now we'll skip them
        # They can be added to a separate DomainFilters table later
        
        domain = Domain(**domain_data)
        db.add(domain)
        await db.commit()
        await db.refresh(domain)
        
        return domain
    
    @staticmethod
    async def get_domain_by_id(
        db: AsyncSession,
        domain_id: int,
        user_id: Optional[int] = None
    ) -> Optional[Domain]:
        """Get domain by ID"""
        query = select(Domain).where(Domain.id == domain_id)
        
        # If user_id provided, verify project ownership
        if user_id is not None:
            query = query.join(Project).where(Project.user_id == user_id)
        
        result = await db.execute(query)
        return result.scalar_one_or_none()
    
    @staticmethod
    async def get_project_domains(
        db: AsyncSession,
        project_id: int,
        user_id: int,
        skip: int = 0,
        limit: int = 100
    ) -> List[Domain]:
        """Get domains for a project"""
        # Verify project ownership
        project = await ProjectService.get_project_by_id(db, project_id, user_id)
        if not project:
            return []
        
        query = (
            select(Domain)
            .where(Domain.project_id == project_id)
            .order_by(desc(Domain.created_at))
            .offset(skip)
            .limit(limit)
        )
        
        result = await db.execute(query)
        return result.scalars().all()
    
    @staticmethod
    async def update_domain(
        db: AsyncSession,
        domain_id: int,
        domain_update: DomainUpdate,
        user_id: int
    ) -> Optional[Domain]:
        """Update domain"""
        domain = await DomainService.get_domain_by_id(db, domain_id, user_id)
        if not domain:
            return None
        
        # Update fields
        update_data = domain_update.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(domain, field, value)
        
        await db.commit()
        await db.refresh(domain)
        
        return domain
    
    @staticmethod
    async def delete_domain(
        db: AsyncSession,
        domain_id: int,
        user_id: int
    ) -> bool:
        """Delete domain"""
        domain = await DomainService.get_domain_by_id(db, domain_id, user_id)
        if not domain:
            return False
        
        await db.delete(domain)
        await db.commit()
        
        return True
    
    @staticmethod
    async def bulk_update_domains(
        db: AsyncSession,
        project_id: int,
        domain_updates: List[dict],
        user_id: int
    ) -> bool:
        """Bulk update domains"""
        # Verify project ownership
        project = await ProjectService.get_project_by_id(db, project_id, user_id)
        if not project:
            return False
        
        for update in domain_updates:
            domain_id = update.get("id")
            if not domain_id:
                continue
            
            domain = await DomainService.get_domain_by_id(db, domain_id, user_id)
            if domain and domain.project_id == project_id:
                for field, value in update.items():
                    if field != "id" and hasattr(domain, field):
                        setattr(domain, field, value)
        
        await db.commit()
        return True


class PageService:
    """Service for page operations"""
    
    @staticmethod
    async def get_project_pages(
        db: AsyncSession,
        project_id: int,
        user_id: int,
        skip: int = 0,
        limit: int = 100,
        search: Optional[str] = None
    ) -> List[Page]:
        """Get pages for a project"""
        # Verify project ownership
        project = await ProjectService.get_project_by_id(db, project_id, user_id)
        if not project:
            return []
        
        # Get pages through domains
        query = (
            select(Page)
            .join(Domain)
            .where(Domain.project_id == project_id)
            .order_by(desc(Page.scraped_at))
        )
        
        # Search filter
        if search:
            query = query.where(
                Page.title.ilike(f"%{search}%") |
                Page.original_url.ilike(f"%{search}%") |
                Page.extracted_text.ilike(f"%{search}%")
            )
        
        query = query.offset(skip).limit(limit)
        result = await db.execute(query)
        return result.scalars().all()
    
    @staticmethod
    async def get_project_page_stats(db: AsyncSession, project_id: int) -> dict:
        """Get detailed page statistics for a project"""
        # Count total pages
        total_pages_result = await db.execute(
            select(func.count(Page.id))
            .join(Domain)
            .where(Domain.project_id == project_id)
        )
        total_pages = total_pages_result.scalar() or 0
        
        # Count indexed pages
        indexed_pages_result = await db.execute(
            select(func.count(Page.id))
            .join(Domain)
            .where(and_(Domain.project_id == project_id, Page.indexed == True))
        )
        indexed_pages = indexed_pages_result.scalar() or 0
        
        # Count failed pages
        failed_pages_result = await db.execute(
            select(func.count(Page.id))
            .join(Domain)
            .where(and_(Domain.project_id == project_id, Page.error_message.isnot(None)))
        )
        failed_pages = failed_pages_result.scalar() or 0
        
        # Get storage used (sum of content_length)
        storage_result = await db.execute(
            select(func.sum(Page.content_length))
            .join(Domain)
            .where(Domain.project_id == project_id)
        )
        storage_used = storage_result.scalar() or 0
        
        # Calculate success rate
        success_rate = (indexed_pages / total_pages) if total_pages > 0 else 0.0
        
        return {
            "total_pages": total_pages,
            "indexed_pages": indexed_pages,
            "failed_pages": failed_pages,
            "storage_used": int(storage_used),
            "success_rate": success_rate
        }


class ScrapeSessionService:
    """Service for scrape session operations"""
    
    @staticmethod
    async def get_project_sessions(
        db: AsyncSession,
        project_id: int,
        user_id: int,
        skip: int = 0,
        limit: int = 100
    ) -> List[ScrapeSession]:
        """Get scrape sessions for a project"""
        # Verify project ownership
        project = await ProjectService.get_project_by_id(db, project_id, user_id)
        if not project:
            return []
        
        query = (
            select(ScrapeSession)
            .where(ScrapeSession.project_id == project_id)
            .order_by(desc(ScrapeSession.created_at))
            .offset(skip)
            .limit(limit)
        )
        
        result = await db.execute(query)
        return result.scalars().all()
    
    @staticmethod
    async def create_scrape_session(
        db: AsyncSession,
        project_id: int,
        user_id: int,
        session_name: Optional[str] = None
    ) -> Optional[ScrapeSession]:
        """Create a new scrape session"""
        # Verify project ownership
        project = await ProjectService.get_project_by_id(db, project_id, user_id)
        if not project:
            return None
        
        session = ScrapeSession(
            project_id=project_id,
            session_name=session_name or f"Scrape Session - {datetime.utcnow().strftime('%Y-%m-%d %H:%M')}",
            status=ScrapeSessionStatus.PENDING
        )
        
        db.add(session)
        await db.commit()
        await db.refresh(session)
        
        return session