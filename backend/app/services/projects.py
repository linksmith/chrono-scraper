"""
Project management services
"""
from typing import List, Optional
from datetime import datetime
from sqlmodel import select, and_, func, desc, case, distinct
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project import (
    Project, 
    ProjectCreate, 
    ProjectUpdate,
    ProjectReadWithStats,
    ProjectStatus,
    Domain,
    DomainCreate,
    DomainUpdate,
    DomainStatus,
    MatchType,
    ScrapeSession,
    ScrapeSessionStatus
)
from app.tasks.celery_app import celery_app
import ast
from app.services.meilisearch_service import MeilisearchService
from app.models.library import StarredItem
from app.core.cache import cache_project_stats, cache_invalidate


class ProjectService:
    """Service for project operations"""
    
    @staticmethod
    @cache_invalidate(["project_stats"])
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
        
        # Create Meilisearch index with dedicated security key
        if project.process_documents:
            try:
                # Create index with master key (admin operation)
                await MeilisearchService.create_project_index(project)
                
                # Create dedicated project search key for security isolation
                from app.services.meilisearch_key_manager import meilisearch_key_manager
                key_data = await meilisearch_key_manager.create_project_key(project)
                
                # Store key information in project
                project.index_search_key = key_data['key']
                project.index_search_key_uid = key_data['uid']
                project.key_created_at = datetime.utcnow()
                project.status = ProjectStatus.INDEXED
                
                # Create audit record for the key (only if table exists)
                try:
                    from sqlalchemy import text as _sql_text
                    result = await db.execute(_sql_text(
                        "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'meilisearch_keys')"
                    ))
                    if result.scalar():
                        from app.models.meilisearch_audit import MeilisearchKey, MeilisearchKeyType
                        audit_record = MeilisearchKey(
                            project_id=project.id,
                            key_uid=key_data['uid'],
                            key_type=MeilisearchKeyType.PROJECT_OWNER,
                            key_name=f"project_owner_{project.id}",
                            key_description=f"Owner search key for project: {project.name}",
                            actions=["search", "documents.get"],
                            indexes=[f"project_{project.id}"]
                        )
                        db.add(audit_record)
                    else:
                        print("Meilisearch audit table not found; skipping audit record")
                except Exception as _audit_err:
                    print(f"Warning: skipping audit record due to error: {_audit_err}")

            except Exception as e:
                # Log error but use fallback keys to allow scraping to proceed
                import logging
                logger = logging.getLogger(__name__)
                logger.error(f"Failed to create secure Meilisearch setup for project {project.id}: {e}")

                # Use mock keys as fallback to allow scraping to proceed
                project.index_search_key = f"fallback_key_{project.id}"
                project.index_search_key_uid = f"fallback_uid_{project.id}"
                project.key_created_at = datetime.utcnow()

            # Always set project status to INDEXED to allow scraping to proceed
            project.status = ProjectStatus.INDEXED
            await db.commit()
            await db.refresh(project)
        
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
    @cache_project_stats
    async def get_projects_with_stats(
        db: AsyncSession,
        user_id: Optional[int] = None,
        skip: int = 0,
        limit: int = 100
    ) -> List[ProjectReadWithStats]:
        """Get projects with statistics - optimized with transaction safety"""
        try:
            # Import models
            from app.models.scraping import ScrapePage, ScrapePageStatus
            
            # Use ScrapePage for accurate page counting
            base_query = select(
                Project,
                func.count(distinct(Domain.id)).label('domain_count'),
                func.coalesce(func.count(distinct(ScrapePage.id)), 0).label('total_pages'),
                func.coalesce(func.count(distinct(case(
                    (ScrapePage.status == ScrapePageStatus.COMPLETED, ScrapePage.id),
                    else_=None
                ))), 0).label('scraped_pages'),
                func.max(ScrapePage.completed_at).label('last_scraped')
            ).select_from(Project)\
             .outerjoin(Domain, Domain.project_id == Project.id)\
             .outerjoin(ScrapePage, ScrapePage.domain_id == Domain.id)
            
            # Apply user filter if provided
            if user_id is not None:
                base_query = base_query.where(Project.user_id == user_id)
            
            # Group by project for aggregation
            base_query = base_query.group_by(Project.id)
            
            # Order by created_at desc and apply pagination
            base_query = base_query.order_by(desc(Project.created_at)).offset(skip).limit(limit)
            
            result = await db.execute(base_query)
            rows = result.all()
            
            projects_with_stats = []
            for row in rows:
                project = row[0]  # Project object
                stats = {
                    "domain_count": int(row.domain_count or 0),
                    "total_pages": int(row.total_pages or 0),
                    "scraped_pages": int(row.scraped_pages or 0),
                    "last_scraped": row.last_scraped
                }
                
                # Convert project to dict and merge with stats
                project_dict = project.model_dump()
                project_dict.update(stats)
                projects_with_stats.append(ProjectReadWithStats(**project_dict))
            
            return projects_with_stats
            
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Failed to get projects with stats: {e}")
            # Return projects without stats as ultimate fallback
            projects = await ProjectService.get_projects(db, user_id, skip, limit)
            return [
                ProjectReadWithStats(
                    **project.model_dump(),
                    domain_count=0,
                    total_pages=0,
                    scraped_pages=0,
                    last_scraped=None
                ) for project in projects
            ]
    
    @staticmethod
    async def get_project_stats(db: AsyncSession, project_id: int) -> dict:
        """Get project statistics using actual page counts"""
        # Count domains
        domain_count_result = await db.execute(
            select(func.count(Domain.id)).where(Domain.project_id == project_id)
        )
        domain_count = domain_count_result.scalar() or 0
        
        # Count actual pages from ScrapePage table
        from app.models.scraping import ScrapePage, ScrapePageStatus
        
        # Count total pages
        total_pages_result = await db.execute(
            select(func.count(ScrapePage.id))
            .join(Domain, ScrapePage.domain_id == Domain.id)
            .where(Domain.project_id == project_id)
        )
        total_pages = total_pages_result.scalar() or 0
        
        # Count completed pages
        completed_pages_result = await db.execute(
            select(func.count(ScrapePage.id))
            .join(Domain, ScrapePage.domain_id == Domain.id)
            .where(
                and_(
                    Domain.project_id == project_id,
                    ScrapePage.status == ScrapePageStatus.COMPLETED
                )
            )
        )
        completed_pages = completed_pages_result.scalar() or 0
        
        # Get last scraped timestamp
        last_scraped_result = await db.execute(
            select(func.max(ScrapePage.completed_at))
            .join(Domain, ScrapePage.domain_id == Domain.id)
            .where(
                and_(
                    Domain.project_id == project_id,
                    ScrapePage.status == ScrapePageStatus.COMPLETED
                )
            )
        )
        last_scraped = last_scraped_result.scalar()
        
        # Update domain counters to match reality
        await ProjectService._sync_domain_counters(db, project_id)
        
        # Update project status based on current state
        await ProjectService._update_project_status_based_on_state(db, project_id)
        
        return {
            "domain_count": domain_count,
            "total_pages": int(total_pages),
            "scraped_pages": int(completed_pages), 
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
        """Delete project and all related data with proper task stopping and deadlock handling"""
        project = await ProjectService.get_project_by_id(db, project_id, user_id)
        if not project:
            return False
        
        # STEP 1: Stop all Celery tasks FIRST (before any database operations)
        print(f"Stopping background tasks for project {project_id}...")
        await ProjectService._stop_project_tasks(db, project_id)
        
        # STEP 2: Delete Meilisearch index
        try:
            await MeilisearchService.delete_project_index(project)
        except Exception as e:
            print(f"Failed to delete Meilisearch index for project {project.id}: {e}")
        
        # STEP 3: Delete project with deadlock retry mechanism
        return await ProjectService._delete_project_with_retry(db, project, project_id)

    @staticmethod
    async def _stop_project_tasks(db: AsyncSession, project_id: int):
        """Stop all running Celery tasks for a project"""
        import asyncio
        from app.models.project import Domain  # ScrapeSession and ScrapeSessionStatus are already imported at top
        
        try:
            # Get domain IDs for this project
            domain_ids_result = await db.execute(
                select(Domain.id).where(Domain.project_id == project_id)
            )
            domain_ids = {did for (did,) in domain_ids_result.all()}

            # Cancel external batch jobs and mark sessions as cancelled
            sessions_result = await db.execute(
                select(ScrapeSession).where(ScrapeSession.project_id == project_id)
            )
            sessions = sessions_result.scalars().all()
            now = datetime.utcnow()
            
            revoked_tasks = []
            for s in sessions:
                # Cancel external Firecrawl batches
                try:
                    if getattr(s, "external_batch_id", None):
                        from app.services.firecrawl_v2_client import FirecrawlV2Client
                        FirecrawlV2Client().cancel_batch(s.external_batch_id)
                        print(f"Cancelled Firecrawl batch {s.external_batch_id}")
                except Exception:
                    pass
                
                s.status = ScrapeSessionStatus.CANCELLED
                s.completed_at = s.completed_at or now
                s.error_message = (s.error_message or "").strip() or "Cancelled due to project deletion"

            # Revoke Celery tasks
            def _extract_args(arg_str: str):
                try:
                    val = ast.literal_eval(arg_str)
                    return val if isinstance(val, tuple) else (val,)
                except Exception:
                    return ()

            def _revoke_matching_tasks(tasks_dict: dict | None):
                if not tasks_dict:
                    return
                for worker, tasks in tasks_dict.items():
                    for t in tasks:
                        name = t.get("name") or t.get("type") or ""
                        args_str = t.get("args") or ""
                        task_id = t.get("id") or t.get("request", {}).get("id")
                        args_tuple = _extract_args(args_str) if isinstance(args_str, str) else ()

                        should_kill = False
                        # Check for project-related tasks
                        if name.endswith("firecrawl_scraping.scrape_domain_with_firecrawl"):
                            if len(args_tuple) >= 1 and args_tuple[0] in domain_ids:
                                should_kill = True
                        elif name.startswith(("app.tasks.project_tasks", "app.tasks.index_tasks")):
                            if len(args_tuple) >= 1 and args_tuple[0] == project_id:
                                should_kill = True

                        if should_kill and task_id:
                            try:
                                celery_app.control.revoke(task_id, terminate=True)
                                revoked_tasks.append((task_id, name))
                                print(f"Revoked task {task_id} ({name})")
                            except Exception as e:
                                print(f"Failed to revoke task {task_id}: {e}")

            try:
                inspect = celery_app.control.inspect()
                _revoke_matching_tasks(getattr(inspect, "active")())
                _revoke_matching_tasks(getattr(inspect, "scheduled")())
                _revoke_matching_tasks(getattr(inspect, "reserved")())
                
                if revoked_tasks:
                    print(f"Revoked {len(revoked_tasks)} tasks, waiting for them to stop...")
                    # Wait for tasks to actually stop
                    await asyncio.sleep(3)
            except Exception as e:
                print(f"Failed to inspect/revoke tasks: {e}")

            # Commit session cancellations
            await db.commit()
            print(f"Successfully stopped {len(sessions)} scrape sessions")
            
        except Exception as e:
            print(f"Warning: failed to stop background processes for project {project_id}: {e}")
            # Continue with deletion anyway
            await db.rollback()

    @staticmethod
    async def _delete_project_with_retry(db: AsyncSession, project, project_id: int, max_retries: int = 3) -> bool:
        """Delete project with deadlock retry mechanism"""
        import asyncio
        from sqlalchemy.exc import DBAPIError
        from sqlalchemy import text
        from app.models.project import Domain
        from app.models.meilisearch_audit import MeilisearchKey
        from app.models.sharing import ProjectShare
        from app.models.entities import ExtractedEntity
        from app.models.project import ScrapeSession

        for attempt in range(max_retries):
            try:
                print(f"Attempting project deletion (attempt {attempt + 1}/{max_retries})...")

                # Start new transaction for this attempt
                if attempt > 0:
                    await db.rollback()
                    await db.begin()

                # STEP 1: Delete Meilisearch keys associated with this project
                try:
                    # Check if table exists before trying to delete
                    result = await db.execute(text("SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'meilisearch_keys')"))
                    table_exists = result.scalar()

                    if table_exists:
                        await db.execute(
                            MeilisearchKey.__table__.delete().where(
                                MeilisearchKey.project_id == project_id
                            )
                        )
                        print(f"Deleted Meilisearch keys for project {project_id}")
                    else:
                        print("Meilisearch keys table doesn't exist, skipping...")
                except Exception as e:
                    print(f"Warning: Failed to delete Meilisearch keys for project {project_id}: {e}")
                    # Rollback transaction on any database error to prevent subsequent operations from failing
                    await db.rollback()
                    if attempt < max_retries - 1:
                        await db.begin()
                        continue
                    else:
                        raise

                # STEP 2: Delete project shares
                try:
                    # Check if table exists
                    result = await db.execute(text("SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'project_shares')"))
                    table_exists = result.scalar()

                    if table_exists:
                        await db.execute(
                            ProjectShare.__table__.delete().where(
                                ProjectShare.project_id == project_id
                            )
                        )
                        print(f"Deleted project shares for project {project_id}")
                    else:
                        print("Project shares table doesn't exist, skipping...")
                except Exception as e:
                    print(f"Warning: Failed to delete project shares for project {project_id}: {e}")
                    # Rollback transaction on any database error to prevent subsequent operations from failing
                    await db.rollback()
                    if attempt < max_retries - 1:
                        await db.begin()
                        continue
                    else:
                        raise

                # STEP 3: Delete extracted entities
                try:
                    # Check if table exists
                    result = await db.execute(text("SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'extracted_entities')"))
                    table_exists = result.scalar()

                    if table_exists:
                        await db.execute(
                            ExtractedEntity.__table__.delete().where(
                                ExtractedEntity.project_id == project_id
                            )
                        )
                        print(f"Deleted extracted entities for project {project_id}")
                    else:
                        print("Extracted entities table doesn't exist, skipping...")
                except Exception as e:
                    print(f"Warning: Failed to delete extracted entities for project {project_id}: {e}")
                    # Rollback transaction on any database error to prevent subsequent operations from failing
                    await db.rollback()
                    if attempt < max_retries - 1:
                        await db.begin()
                        continue
                    else:
                        raise

                # STEP 4: Delete scrape pages and related data first
                try:
                    from app.models.scraping import ScrapePage, CDXResumeState
                    # Check if tables exist
                    result = await db.execute(text("SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'cdx_resume_states')"))
                    cdx_exists = result.scalar()

                    result = await db.execute(text("SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'scrape_pages')"))
                    scrape_pages_exists = result.scalar()

                    # Delete CDX resume states first (they reference domains)
                    if cdx_exists:
                        await db.execute(
                            CDXResumeState.__table__.delete().where(
                                CDXResumeState.domain_id.in_(
                                    select(Domain.id).where(Domain.project_id == project_id)
                                )
                            )
                        )
                        print(f"Deleted CDX resume states for project {project_id}")

                    # Delete scrape pages
                    if scrape_pages_exists:
                        await db.execute(
                            ScrapePage.__table__.delete().where(
                                ScrapePage.domain_id.in_(
                                    select(Domain.id).where(Domain.project_id == project_id)
                                )
                            )
                        )
                        print(f"Deleted scrape pages for project {project_id}")
                except Exception as e:
                    print(f"Warning: Failed to delete scrape pages for project {project_id}: {e}")
                    # Rollback transaction on any database error to prevent subsequent operations from failing
                    await db.rollback()
                    if attempt < max_retries - 1:
                        await db.begin()
                        continue
                    else:
                        raise

                # STEP 5: Delete scrape sessions (now safe since scrape_pages are deleted)
                try:
                    await db.execute(
                        ScrapeSession.__table__.delete().where(
                            ScrapeSession.project_id == project_id
                        )
                    )
                    print(f"Deleted scrape sessions for project {project_id}")
                except Exception as e:
                    print(f"Warning: Failed to delete scrape sessions for project {project_id}: {e}")
                    # Rollback transaction on any database error to prevent subsequent operations from failing
                    await db.rollback()
                    if attempt < max_retries - 1:
                        await db.begin()
                        continue
                    else:
                        raise

                # STEP 6: Legacy Page table removal - no longer exists
                print(f"Skipping legacy pages deletion (table removed) for project {project_id}")

                # STEP 7: Delete domains associated with this project (now safe since pages are deleted)
                try:
                    await db.execute(
                        Domain.__table__.delete().where(
                            Domain.project_id == project_id
                        )
                    )
                    print(f"Deleted domains for project {project_id}")
                except Exception as e:
                    print(f"Warning: Failed to delete domains for project {project_id}: {e}")
                    # Rollback transaction on any database error to prevent subsequent operations from failing
                    await db.rollback()
                    if attempt < max_retries - 1:
                        await db.begin()
                        continue
                    else:
                        raise

                # STEP 8: Delete any remaining starred items for this project
                # Note: Page-level starred items are automatically CASCADE deleted when pages are deleted
                # This step only handles project-level starred items and any orphaned records
                try:
                    await db.execute(
                        StarredItem.__table__.delete().where(
                            StarredItem.project_id == project_id
                        )
                    )
                    print(f"Deleted starred items for project {project_id}")
                except Exception as e:
                    print(f"Warning: Failed to delete starred items for project {project_id}: {e}")
                    # Rollback transaction on any database error to prevent subsequent operations from failing
                    await db.rollback()
                    if attempt < max_retries - 1:
                        await db.begin()
                        continue
                    else:
                        raise

                # STEP 9: Delete the project (cascading deletes handle remaining related data)
                try:
                    await db.delete(project)
                    await db.commit()
                    print(f"Successfully deleted project {project_id}")
                    return True
                except Exception as e:
                    print(f"Warning: Failed to delete project {project_id}: {e}")
                    # Rollback transaction on any database error
                    await db.rollback()
                    # Don't retry final project deletion to avoid infinite loops
                    raise

            except DBAPIError as e:
                error_msg = str(e.orig) if hasattr(e, 'orig') else str(e)
                
                # Check if it's a deadlock
                if "deadlock detected" in error_msg.lower():
                    print(f"Deadlock detected on attempt {attempt + 1}, retrying in {2 ** attempt} seconds...")
                    await db.rollback()
                    if attempt < max_retries - 1:
                        await asyncio.sleep(2 ** attempt)  # Exponential backoff
                        continue
                    else:
                        print(f"Failed to delete project after {max_retries} attempts due to persistent deadlocks")
                        raise
                
                # Check for foreign key constraint violations
                elif "violates foreign key constraint" in error_msg.lower():
                    print(f"Foreign key constraint violation on attempt {attempt + 1}: {error_msg}")
                    await db.rollback()
                    if attempt < max_retries - 1:
                        # Wait a bit longer for tasks to fully stop
                        await asyncio.sleep(5)
                        continue
                    else:
                        print("Failed to delete project due to persistent foreign key constraints")
                        raise
                
                else:
                    # Other database errors - don't retry
                    print(f"Non-retryable database error: {error_msg}")
                    await db.rollback()
                    raise
                    
            except Exception as e:
                print(f"Unexpected error during project deletion: {e}")
                await db.rollback()
                raise
        
        return False
    
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
        """Synchronize domain counters with actual page counts - with transaction safety"""
        try:
            # Import shared pages models
            from sqlmodel import func
            from app.models.shared_pages import PageV2, ProjectPage
            
            # Get all domains for the project
            domains_result = await db.execute(
                select(Domain).where(Domain.project_id == project_id)
            )
            domains = domains_result.scalars().all()
            
            if not domains:
                return  # No domains to sync
            
            for domain in domains:
                try:
                    # Count pages for this domain using ScrapePage
                    from app.models.scraping import ScrapePage, ScrapePageStatus
                    
                    # Count total pages for this domain
                    total_pages_result = await db.execute(
                        select(func.count(ScrapePage.id))
                        .where(ScrapePage.domain_id == domain.id)
                    )
                    actual_total = total_pages_result.scalar() or 0
                    
                    # Count completed pages for this domain
                    completed_pages_result = await db.execute(
                        select(func.count(ScrapePage.id))
                        .where(
                            and_(
                                ScrapePage.domain_id == domain.id,
                                ScrapePage.status == ScrapePageStatus.COMPLETED
                            )
                        )
                    )
                    actual_completed = completed_pages_result.scalar() or 0
                    
                    # Count failed pages for this domain
                    failed_pages_result = await db.execute(
                        select(func.count(ScrapePage.id))
                        .where(
                            and_(
                                ScrapePage.domain_id == domain.id,
                                ScrapePage.status == ScrapePageStatus.FAILED
                            )
                        )
                    )
                    actual_failed = failed_pages_result.scalar() or 0
                    
                    # Update domain counters
                    domain.total_pages = actual_total
                    domain.scraped_pages = actual_completed
                    domain.failed_pages = actual_failed
                    
                    # Update domain status based on actual state
                    if actual_total == 0:
                        domain.status = DomainStatus.ACTIVE  # Default to active if no pages yet
                    elif actual_completed == actual_total:
                        domain.status = DomainStatus.COMPLETED  # All pages completed
                    elif actual_failed > 0:
                        domain.status = DomainStatus.ERROR  # Some pages failed
                    else:
                        domain.status = DomainStatus.ACTIVE  # Still processing
                        
                except Exception as e:
                    import logging
                    logger = logging.getLogger(__name__)
                    logger.warning(f"Failed to sync counters for domain {domain.id}: {e}")
                    continue
            
            # Commit changes
            await db.commit()
            
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Failed to sync domain counters for project {project_id}: {e}")
            await db.rollback()
            raise
    
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
            project.status = ProjectStatus.NO_INDEX
            await db.commit()
            return
        
        # Legacy Page model removed - use domain stats as proxy
        total_pages = sum(domain.total_pages for domain in domains)
        processed_pages = sum(domain.scraped_pages for domain in domains)
        
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
        
        # Check if an identical domain/target already exists for this project
        # For prefix targets, uniqueness includes match_type and url_path
        if domain_create.match_type == MatchType.PREFIX and domain_create.url_path:
            existing_domain_query = select(Domain).where(
                and_(
                    Domain.project_id == project_id,
                    Domain.domain_name == domain_create.domain_name,
                    Domain.match_type == MatchType.PREFIX,
                    Domain.url_path == domain_create.url_path
                )
            )
        else:
            existing_domain_query = select(Domain).where(
                and_(
                    Domain.project_id == project_id,
                    Domain.domain_name == domain_create.domain_name,
                    Domain.match_type == (domain_create.match_type or MatchType.DOMAIN)
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
        
        # Normalize domain_name when a full URL is accidentally provided
        try:
            raw_domain = domain_data.get("domain_name") or ""
            if raw_domain and (raw_domain.startswith("http://") or raw_domain.startswith("https://") or "/" in raw_domain):
                from urllib.parse import urlparse
                parsed = urlparse(raw_domain if raw_domain.startswith(("http://", "https://")) else f"https://{raw_domain}")
                if parsed.hostname:
                    domain_data["domain_name"] = parsed.hostname.lower().lstrip("www.")
        except Exception:
            pass
        
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
        
        # Determine match_type
        # If a specific URL/path is provided and match_type is PREFIX, honor it
        if domain_create.url_path and domain_create.match_type == MatchType.PREFIX:
            domain_data["match_type"] = MatchType.PREFIX
        else:
            # Otherwise, derive from include_subdomains flag
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


# Legacy PageService class removed - functionality moved to shared pages system


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