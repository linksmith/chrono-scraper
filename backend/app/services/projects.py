"""
Project management services
"""
from typing import List, Optional
from datetime import datetime, timedelta
from sqlmodel import select, and_, or_, func, desc, cast, String
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
    DomainStatus,
    MatchType,
    Page,
    PageRead,
    PageReadWithStarring,
    PageReview,
    PageBulkAction,
    TagSuggestion,
    PageReviewStatus,
    PageCategory,
    PagePriority,
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
        """Get project statistics using actual page counts"""
        # Count domains
        domain_count_result = await db.execute(
            select(func.count(Domain.id)).where(Domain.project_id == project_id)
        )
        domain_count = domain_count_result.scalar() or 0
        
        # Count actual pages from the pages table through domains
        actual_pages_result = await db.execute(
            select(func.count(Page.id))
            .join(Domain)
            .where(Domain.project_id == project_id)
        )
        actual_pages = actual_pages_result.scalar() or 0
        
        # Count processed/indexed pages
        processed_pages_result = await db.execute(
            select(func.count(Page.id))
            .join(Domain)
            .where(
                Domain.project_id == project_id,
                Page.processed == True,
                Page.indexed == True
            )
        )
        processed_pages = processed_pages_result.scalar() or 0
        
        # Get last scraped date from actual pages
        last_scraped_result = await db.execute(
            select(func.max(Page.scraped_at))
            .join(Domain)
            .where(Domain.project_id == project_id)
        )
        last_scraped = last_scraped_result.scalar()
        
        # Update domain counters to match reality
        await ProjectService._sync_domain_counters(db, project_id)
        
        # Update project status based on current state
        await ProjectService._update_project_status_based_on_state(db, project_id)
        
        return {
            "domain_count": domain_count,
            "total_pages": int(actual_pages),
            "scraped_pages": int(processed_pages), 
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
    
    @staticmethod
    async def _sync_domain_counters(db: AsyncSession, project_id: int):
        """Synchronize domain counters with actual page counts"""
        # Get all domains for the project
        domains_result = await db.execute(
            select(Domain).where(Domain.project_id == project_id)
        )
        domains = domains_result.scalars().all()
        
        for domain in domains:
            # Count actual pages for this domain
            total_pages_result = await db.execute(
                select(func.count(Page.id)).where(Page.domain_id == domain.id)
            )
            actual_total = total_pages_result.scalar() or 0
            
            # Count processed pages for this domain
            processed_pages_result = await db.execute(
                select(func.count(Page.id)).where(
                    Page.domain_id == domain.id,
                    Page.processed == True,
                    Page.indexed == True
                )
            )
            actual_processed = processed_pages_result.scalar() or 0
            
            # Count failed pages
            failed_pages_result = await db.execute(
                select(func.count(Page.id)).where(
                    Page.domain_id == domain.id,
                    Page.error_message.isnot(None)
                )
            )
            actual_failed = failed_pages_result.scalar() or 0
            
            # Update domain counters
            domain.total_pages = actual_total
            domain.scraped_pages = actual_processed
            domain.failed_pages = actual_failed
            
            # Update domain status based on actual state
            if actual_total == 0:
                domain.status = DomainStatus.ACTIVE  # Default to active if no pages yet
            elif actual_failed > 0 and actual_processed == 0:
                domain.status = DomainStatus.ERROR
            elif actual_processed > 0:
                if actual_processed == actual_total:
                    domain.status = DomainStatus.COMPLETED
                else:
                    domain.status = DomainStatus.ACTIVE
            else:
                domain.status = DomainStatus.ACTIVE
        
        await db.commit()
    
    @staticmethod
    async def _update_project_status_based_on_state(db: AsyncSession, project_id: int):
        """Update project status based on current domain and page states"""
        # Get the project
        project_result = await db.execute(
            select(Project).where(Project.id == project_id)
        )
        project = project_result.scalar_one_or_none()
        if not project:
            return
        
        # Get domain statuses
        domains_result = await db.execute(
            select(Domain).where(Domain.project_id == project_id)
        )
        domains = domains_result.scalars().all()
        
        if not domains:
            project.status = ProjectStatus.DRAFT
            await db.commit()
            return
        
        # Count pages
        total_pages_result = await db.execute(
            select(func.count(Page.id))
            .join(Domain)
            .where(Domain.project_id == project_id)
        )
        total_pages = total_pages_result.scalar() or 0
        
        processed_pages_result = await db.execute(
            select(func.count(Page.id))
            .join(Domain)
            .where(
                Domain.project_id == project_id,
                Page.processed == True,
                Page.indexed == True
            )
        )
        processed_pages = processed_pages_result.scalar() or 0
        
        # Determine new project status
        domain_statuses = [domain.status for domain in domains]
        
        if total_pages == 0:
            # No pages scraped yet
            project.status = ProjectStatus.NO_INDEX
        elif processed_pages == total_pages and all(status == DomainStatus.COMPLETED for status in domain_statuses):
            # All pages processed and all domains completed
            project.status = ProjectStatus.INDEXED
        elif processed_pages > 0:
            # Some pages processed - project is active/completed indexing 
            project.status = ProjectStatus.INDEXED
        elif any(status == DomainStatus.ERROR for status in domain_statuses):
            # At least one domain has errors
            project.status = ProjectStatus.ERROR
        else:
            # Default to indexing if unclear
            project.status = ProjectStatus.INDEXING
        
        await db.commit()


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
        
        # Check if domain already exists for this project
        existing_domain_query = select(Domain).where(
            and_(
                Domain.project_id == project_id,
                Domain.domain_name == domain_create.domain_name
            )
        )
        result = await db.execute(existing_domain_query)
        existing_domain = result.scalar_one_or_none()
        
        if existing_domain:
            # Domain already exists, return the existing one instead of creating duplicate
            print(f"Domain {domain_create.domain_name} already exists for project {project_id}, returning existing domain")
            return existing_domain
        
        domain_data = domain_create.model_dump(exclude={"include_subdomains", "exclude_patterns", "include_patterns"})
        domain_data["project_id"] = project_id
        
        # Handle date range conversion (from_date and to_date are already in the model)
        if domain_create.from_date:
            try:
                domain_data["from_date"] = datetime.strptime(domain_create.from_date, "%Y-%m-%d")
            except ValueError:
                pass  # Invalid date format, skip
        
        if domain_create.to_date:
            try:
                domain_data["to_date"] = datetime.strptime(domain_create.to_date, "%Y-%m-%d")
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
        search: Optional[str] = None,
        starred_only: bool = False,
        tags: Optional[List[str]] = None,
        review_status: Optional[List[str]] = None
    ) -> List[Page]:
        """Get pages for a project with filtering support"""
        # Verify project ownership
        project = await ProjectService.get_project_by_id(db, project_id, user_id)
        if not project:
            return []
        
        # Base query: Get pages through domains
        query = (
            select(Page)
            .join(Domain)
            .where(Domain.project_id == project_id)
        )
        
        # Apply starred filter if requested
        if starred_only:
            from app.models.library import StarredItem, ItemType
            query = query.join(
                StarredItem,
                and_(
                    StarredItem.page_id == Page.id,
                    StarredItem.user_id == user_id,
                    StarredItem.item_type == ItemType.PAGE
                )
            )
        
        # Apply tags filter (DB-agnostic): try JSON contains and fallback to string pattern match
        if tags and len(tags) > 0:
            for tag in tags:
                query = query.where(
                    or_(
                        Page.tags.contains([tag]),
                        cast(Page.tags, String).ilike(f'%"{tag}"%')
                    )
                )
        
        # Apply review status filter
        if review_status and len(review_status) > 0:
            # Convert string values to enum values if needed
            from app.models.project import PageReviewStatus
            status_filters = []
            for status in review_status:
                if status.lower() == 'relevant':
                    status_filters.append(PageReviewStatus.RELEVANT)
                elif status.lower() == 'irrelevant':
                    status_filters.append(PageReviewStatus.IRRELEVANT)
            
            if status_filters:
                query = query.where(Page.review_status.in_(status_filters))
        
        # Search filter
        if search:
            query = query.where(
                Page.title.ilike(f"%{search}%") |
                Page.original_url.ilike(f"%{search}%") |
                Page.extracted_text.ilike(f"%{search}%")
            )
        
        # Order by scraped_at desc and apply pagination
        query = query.order_by(desc(Page.scraped_at)).offset(skip).limit(limit)
        
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
    
    @staticmethod
    async def get_page_by_id(
        db: AsyncSession,
        page_id: int,
        user_id: int
    ) -> Optional[Page]:
        """Get page by ID with user access verification"""
        query = (
            select(Page)
            .join(Domain)
            .join(Project)
            .where(and_(Page.id == page_id, Project.user_id == user_id))
        )
        
        result = await db.execute(query)
        return result.scalar_one_or_none()
    
    @staticmethod
    async def get_page_with_starring(
        db: AsyncSession,
        page_id: int,
        user_id: int
    ) -> Optional[PageReadWithStarring]:
        """Get page with starring information"""
        page = await PageService.get_page_by_id(db, page_id, user_id)
        if not page:
            return None
        
        # Check if user has starred this page
        from app.models.library import StarredItem, ItemType
        starred_query = select(StarredItem).where(
            and_(
                StarredItem.user_id == user_id,
                StarredItem.item_type == ItemType.PAGE,
                StarredItem.page_id == page_id
            )
        )
        starred_result = await db.execute(starred_query)
        starred_item = starred_result.scalar_one_or_none()
        
        # Convert to PageReadWithStarring
        page_dict = page.model_dump()
        page_dict.update({
            "user_starred": starred_item is not None,
            "user_star_tags": starred_item.tags if starred_item else [],
            "user_star_notes": starred_item.personal_note if starred_item else ""
        })
        
        return PageReadWithStarring(**page_dict)
    
    @staticmethod
    async def review_page(
        db: AsyncSession,
        page_id: int,
        user_id: int,
        review_data: PageReview
    ) -> Optional[Page]:
        """Review a page with status, category, and notes"""
        page = await PageService.get_page_by_id(db, page_id, user_id)
        if not page:
            return None
        
        # Update page with review data
        update_data = review_data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            if hasattr(page, field) and value is not None:
                setattr(page, field, value)
        
        # Set review tracking fields
        page.reviewed_by = user_id
        page.reviewed_at = datetime.utcnow()
        
        await db.commit()
        await db.refresh(page)
        return page
    
    @staticmethod
    async def update_page_tags(
        db: AsyncSession,
        page_id: int,
        user_id: int,
        tags: List[str]
    ) -> Optional[Page]:
        """Update page tags"""
        page = await PageService.get_page_by_id(db, page_id, user_id)
        if not page:
            return None
        
        page.tags = tags
        await db.commit()
        await db.refresh(page)
        return page
    
    @staticmethod
    async def bulk_page_action(
        db: AsyncSession,
        user_id: int,
        bulk_action: PageBulkAction
    ) -> dict:
        """Perform bulk actions on multiple pages"""
        # Verify user has access to all pages
        pages_query = (
            select(Page)
            .join(Domain)
            .join(Project)
            .where(and_(
                Page.id.in_(bulk_action.page_ids),
                Project.user_id == user_id
            ))
        )
        result = await db.execute(pages_query)
        pages = result.scalars().all()
        
        if len(pages) != len(bulk_action.page_ids):
            return {
                "success": False,
                "message": "Some pages not found or access denied",
                "processed": 0
            }
        
        processed = 0
        
        for page in pages:
            if bulk_action.action == "mark_irrelevant":
                page.review_status = PageReviewStatus.IRRELEVANT
                page.reviewed_by = user_id
                page.reviewed_at = datetime.utcnow()
                processed += 1
            
            elif bulk_action.action == "mark_relevant":
                page.review_status = PageReviewStatus.RELEVANT
                page.reviewed_by = user_id
                page.reviewed_at = datetime.utcnow()
                processed += 1
            
            elif bulk_action.action == "set_category" and bulk_action.page_category:
                page.page_category = bulk_action.page_category
                page.reviewed_by = user_id
                page.reviewed_at = datetime.utcnow()
                processed += 1
            
            elif bulk_action.action == "add_tags" and bulk_action.tags:
                current_tags = set(page.tags or [])
                new_tags = set(bulk_action.tags)
                page.tags = list(current_tags | new_tags)
                processed += 1
            
            elif bulk_action.action == "remove_tags" and bulk_action.tags:
                current_tags = set(page.tags or [])
                remove_tags = set(bulk_action.tags)
                page.tags = list(current_tags - remove_tags)
                processed += 1
            
            elif bulk_action.action == "set_priority" and bulk_action.priority_level:
                page.priority_level = bulk_action.priority_level
                page.reviewed_by = user_id
                page.reviewed_at = datetime.utcnow()
                processed += 1
        
        await db.commit()
        
        return {
            "success": True,
            "message": f"Bulk action '{bulk_action.action}' completed",
            "processed": processed
        }
    
    @staticmethod
    async def get_pages_for_review(
        db: AsyncSession,
        user_id: int,
        project_id: Optional[int] = None,
        review_status: Optional[PageReviewStatus] = None,
        priority_level: Optional[PagePriority] = None,
        page_category: Optional[PageCategory] = None,
        skip: int = 0,
        limit: int = 100,
        exclude_irrelevant: bool = True
    ) -> dict:
        """Get pages for review with filtering"""
        query = (
            select(Page)
            .join(Domain)
            .join(Project)
            .where(Project.user_id == user_id)
        )
        
        # Apply filters
        if project_id:
            query = query.where(Project.id == project_id)
        
        if review_status:
            query = query.where(Page.review_status == review_status)
        elif exclude_irrelevant:
            query = query.where(Page.review_status != PageReviewStatus.IRRELEVANT)
        
        if priority_level:
            query = query.where(Page.priority_level == priority_level)
        
        if page_category:
            query = query.where(Page.page_category == page_category)
        
        # Order by priority and created date
        query = query.order_by(
            Page.priority_level.desc(),
            Page.created_at.desc()
        )
        
        # Get total count
        count_query = select(func.count()).select_from(query.subquery())
        count_result = await db.execute(count_query)
        total = count_result.scalar()
        
        # Apply pagination
        query = query.offset(skip).limit(limit)
        result = await db.execute(query)
        pages = result.scalars().all()
        
        return {
            "items": [
                {
                    "id": page.id,
                    "title": page.title or page.extracted_title,
                    "url": page.original_url,
                    "review_status": page.review_status,
                    "page_category": page.page_category,
                    "priority_level": page.priority_level,
                    "tags": page.tags,
                    "word_count": page.word_count,
                    "content_snippet": page.extracted_text[:200] if page.extracted_text else "",
                    "scraped_at": page.scraped_at,
                    "reviewed_at": page.reviewed_at
                }
                for page in pages
            ],
            "total": total,
            "skip": skip,
            "limit": limit
        }
    
    @staticmethod
    async def get_tag_suggestions(
        db: AsyncSession,
        user_id: int,
        query: Optional[str] = None,
        page_id: Optional[int] = None,
        limit: int = 20
    ) -> List[TagSuggestion]:
        """Get tag suggestions based on user's existing tags and content"""
        # Get user's existing tags from their pages
        tags_query = (
            select(Page.tags)
            .join(Domain)
            .join(Project)
            .where(and_(
                Project.user_id == user_id,
                Page.tags.isnot(None)
            ))
        )
        
        result = await db.execute(tags_query)
        # Sanitize and normalize tags to ensure they are strings
        all_tags: list[str] = []
        for tag_list in result.scalars():
            if not tag_list:
                continue
            for raw_tag in tag_list:
                if raw_tag is None:
                    continue
                try:
                    tag_str = str(raw_tag).strip()
                except Exception:
                    continue
                if not tag_str:
                    continue
                all_tags.append(tag_str)
        
        # Count tag frequencies
        tag_counts: dict[str, int] = {}
        for tag in all_tags:
            tag_counts[tag] = tag_counts.get(tag, 0) + 1
        
        # Filter by query if provided
        if query:
            filtered_tags = {
                tag: count for tag, count in tag_counts.items()
                if query.lower() in tag.lower()
            }
        else:
            filtered_tags = tag_counts
        
        # Sort by frequency and limit
        sorted_tags = sorted(
            filtered_tags.items(),
            key=lambda x: x[1],
            reverse=True
        )[:limit]
        
        suggestions = [
            TagSuggestion(
                tag=tag,
                frequency=count,
                confidence=min(count / 10.0, 1.0)  # Simple confidence scoring
            )
            for tag, count in sorted_tags
        ]
        
        return suggestions
    
    @staticmethod
    async def get_page_analytics(
        db: AsyncSession,
        user_id: int,
        project_id: Optional[int] = None,
        days: int = 30
    ) -> dict:
        """Get page review analytics"""
        base_query = (
            select(Page)
            .join(Domain)
            .join(Project)
            .where(Project.user_id == user_id)
        )
        
        if project_id:
            base_query = base_query.where(Project.id == project_id)
        
        # Count by review status
        status_counts = {}
        for status in PageReviewStatus:
            count_query = base_query.where(Page.review_status == status)
            count_result = await db.execute(select(func.count()).select_from(count_query.subquery()))
            status_counts[status.value] = count_result.scalar() or 0
        
        # Count by category
        category_counts = {}
        for category in PageCategory:
            count_query = base_query.where(Page.page_category == category)
            count_result = await db.execute(select(func.count()).select_from(count_query.subquery()))
            category_counts[category.value] = count_result.scalar() or 0
        
        # Recent review activity
        recent_cutoff = datetime.utcnow() - timedelta(days=days)
        recent_query = base_query.where(Page.reviewed_at >= recent_cutoff)
        recent_result = await db.execute(select(func.count()).select_from(recent_query.subquery()))
        recent_reviews = recent_result.scalar() or 0
        
        return {
            "review_status_counts": status_counts,
            "category_counts": category_counts,
            "recent_reviews": recent_reviews,
            "period_days": days
        }
    
    @staticmethod
    async def get_page_content(
        db: AsyncSession,
        page_id: int,
        user_id: int,
        format: str = "markdown"
    ) -> Optional[dict]:
        """Get page content in different formats"""
        from app.models.scraping import ScrapePage
        from sqlmodel import select
        
        page = await PageService.get_page_by_id(db, page_id, user_id)
        if not page:
            return None
        
        content_data = {
            "page_id": page.id,
            "title": page.title or page.extracted_title,
            "url": page.original_url,
            "wayback_url": page.wayback_url,
            "format": format
        }
        
        # Try to get markdown content from ScrapePage if format is markdown
        content = page.extracted_text
        if format == "markdown":
            # Try to find matching ScrapePage by wayback_url and domain_id
            stmt = select(ScrapePage).where(
                ScrapePage.wayback_url == page.wayback_url,
                ScrapePage.domain_id == page.domain_id
            ).limit(1)
            result = await db.execute(stmt)
            scrape_page = result.scalar_one_or_none()
            
            if scrape_page and scrape_page.markdown_content:
                content = scrape_page.markdown_content
            else:
                # Fallback to extracted_text
                content = page.extracted_text
        
        content_data["content"] = content
        
        content_data.update({
            "word_count": page.word_count,
            "character_count": page.character_count,
            "language": page.language,
            "author": page.author,
            "published_date": page.published_date,
            "meta_description": page.meta_description,
            # Helpful metadata for the viewer
            "capture_date": page.capture_date,
            "unix_timestamp": page.unix_timestamp,
            # Some schemas use scraped_at; include defensively if available
            "scraped_at": getattr(page, "scraped_at", None)
        })
        
        return content_data
    
    @staticmethod
    async def mark_as_duplicate(
        db: AsyncSession,
        page_id: int,
        duplicate_of_page_id: int,
        user_id: int
    ) -> bool:
        """Mark page as duplicate of another page"""
        # Verify both pages exist and user has access
        page = await PageService.get_page_by_id(db, page_id, user_id)
        duplicate_page = await PageService.get_page_by_id(db, duplicate_of_page_id, user_id)
        
        if not page or not duplicate_page:
            return False
        
        page.is_duplicate = True
        page.duplicate_of_page_id = duplicate_of_page_id
        page.review_status = PageReviewStatus.DUPLICATE
        page.reviewed_by = user_id
        page.reviewed_at = datetime.utcnow()
        
        await db.commit()
        return True


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