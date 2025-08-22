"""
Page access control service for shared pages architecture

Ensures users can only access pages from their projects while maintaining
strict security boundaries in the many-to-many relationship model.
"""
import json
import logging
from typing import List, Optional, Set, Dict, Any
from uuid import UUID
from fastapi import Depends
from sqlmodel import Session, select, and_, or_
from sqlalchemy import text, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.models.shared_pages import PageV2, ProjectPage
from app.models.project import Project
from app.models.user import User

logger = logging.getLogger(__name__)


class PageAccessControl:
    """Security access control for shared pages"""
    
    def __init__(self, db: AsyncSession):
        self.db = db
        self._cache = {}  # Simple in-memory cache for now
    
    async def get_user_accessible_pages(
        self,
        user_id: int,
        page_ids: Optional[List[UUID]] = None,
        project_id: Optional[int] = None
    ) -> List[UUID]:
        """
        Get all page IDs accessible to a user
        
        Args:
            user_id: User ID to check access for
            page_ids: Optional list of specific page IDs to filter
            project_id: Optional project ID to limit scope
            
        Returns:
            List of accessible page IDs
        """
        # Check cache first if no specific filtering
        cache_key = f"user_accessible_pages:{user_id}"
        if not page_ids and not project_id and cache_key in self._cache:
            return self._cache[cache_key]
        
        # Build query for accessible pages
        query = text("""
            SELECT DISTINCT pp.page_id
            FROM project_pages pp
            JOIN projects p ON pp.project_id = p.id
            WHERE p.user_id = :user_id
        """)
        
        params = {"user_id": user_id}
        
        # Add optional filters
        if page_ids:
            page_ids_str = [str(pid) for pid in page_ids]
            query = text(str(query) + " AND pp.page_id = ANY(:page_ids)")
            params["page_ids"] = page_ids_str
        
        if project_id:
            query = text(str(query) + " AND pp.project_id = :project_id")
            params["project_id"] = project_id
        
        result = await self.db.execute(query, params)
        # Handle both string and UUID types from database
        page_ids_result = []
        for row in result.fetchall():
            page_id = row[0]
            if isinstance(page_id, str):
                page_ids_result.append(UUID(page_id))
            else:
                # Already a UUID object from asyncpg
                page_ids_result.append(page_id)
        
        # Cache result if it's a full user query
        if not page_ids and not project_id:
            self._cache[cache_key] = page_ids_result
        
        return page_ids_result
    
    async def can_user_access_page(
        self,
        user_id: int,
        page_id: UUID
    ) -> bool:
        """
        Check if user can access a specific page
        
        Args:
            user_id: User ID to check
            page_id: Page ID to check access for
            
        Returns:
            True if user has access, False otherwise
        """
        query = text("""
            SELECT EXISTS(
                SELECT 1 FROM project_pages pp
                JOIN projects p ON pp.project_id = p.id
                WHERE p.user_id = :user_id AND pp.page_id = :page_id
            )
        """)
        
        result = await self.db.execute(
            query,
            {"user_id": user_id, "page_id": str(page_id)}
        )
        return result.scalar()
    
    async def can_user_access_multiple_pages(
        self,
        user_id: int,
        page_ids: List[UUID]
    ) -> Dict[UUID, bool]:
        """
        Check access for multiple pages efficiently
        
        Args:
            user_id: User ID to check
            page_ids: List of page IDs to check
            
        Returns:
            Dictionary mapping page IDs to access permissions
        """
        if not page_ids:
            return {}
        
        accessible_pages = await self.get_user_accessible_pages(user_id, page_ids)
        accessible_set = set(accessible_pages)
        
        return {page_id: page_id in accessible_set for page_id in page_ids}
    
    async def filter_pages_for_user(
        self,
        user_id: int,
        page_ids: Optional[List[UUID]] = None
    ) -> List[UUID]:
        """
        Filter page IDs to only include those accessible to user
        
        Args:
            user_id: User ID to filter for
            page_ids: Optional list of page IDs to filter, if None returns all accessible
            
        Returns:
            List of accessible page IDs
        """
        return await self.get_user_accessible_pages(user_id, page_ids)
    
    async def get_user_projects_with_page_access(
        self,
        user_id: int,
        page_id: UUID
    ) -> List[int]:
        """
        Get all projects where user has access to a specific page
        
        Args:
            user_id: User ID
            page_id: Page ID to check
            
        Returns:
            List of project IDs where user has access to the page
        """
        query = text("""
            SELECT pp.project_id
            FROM project_pages pp
            JOIN projects p ON pp.project_id = p.id
            WHERE p.user_id = :user_id AND pp.page_id = :page_id
        """)
        
        result = await self.db.execute(
            query,
            {"user_id": user_id, "page_id": str(page_id)}
        )
        return [row[0] for row in result.fetchall()]
    
    async def get_project_pages_for_user(
        self,
        user_id: int,
        project_id: int,
        limit: Optional[int] = None,
        offset: Optional[int] = None
    ) -> List[UUID]:
        """
        Get pages for a specific project that the user owns
        
        Args:
            user_id: User ID
            project_id: Project ID
            limit: Optional limit for pagination
            offset: Optional offset for pagination
            
        Returns:
            List of page IDs for the project
        """
        # First verify user owns the project
        project = await self.db.get(Project, project_id)
        if not project or project.user_id != user_id:
            return []
        
        query = text("""
            SELECT pp.page_id
            FROM project_pages pp
            WHERE pp.project_id = :project_id
            ORDER BY pp.added_at DESC
        """)
        
        if limit:
            query = text(str(query) + f" LIMIT {limit}")
        if offset:
            query = text(str(query) + f" OFFSET {offset}")
        
        result = await self.db.execute(query, {"project_id": project_id})
        # Handle both string and UUID types from database
        page_ids_result = []
        for row in result.fetchall():
            page_id = row[0]
            if isinstance(page_id, str):
                page_ids_result.append(UUID(page_id))
            else:
                # Already a UUID object from asyncpg
                page_ids_result.append(page_id)
        return page_ids_result
    
    async def get_user_page_associations(
        self,
        user_id: int,
        page_ids: List[UUID]
    ) -> List[ProjectPage]:
        """
        Get ProjectPage associations for pages accessible to user
        
        Args:
            user_id: User ID
            page_ids: List of page IDs
            
        Returns:
            List of ProjectPage associations
        """
        if not page_ids:
            return []
        
        # Get accessible page IDs first
        accessible_pages = await self.get_user_accessible_pages(user_id, page_ids)
        
        if not accessible_pages:
            return []
        
        # Query ProjectPage associations
        stmt = (
            select(ProjectPage)
            .join(Project)
            .where(
                and_(
                    Project.user_id == user_id,
                    ProjectPage.page_id.in_(accessible_pages)
                )
            )
        )
        
        result = await self.db.execute(stmt)
        return result.scalars().all()
    
    async def validate_bulk_page_access(
        self,
        user_id: int,
        page_ids: List[UUID],
        operation: str = "read"
    ) -> Dict[str, Any]:
        """
        Validate bulk page access and return detailed results
        
        Args:
            user_id: User ID
            page_ids: List of page IDs to validate
            operation: Type of operation (read, write, delete)
            
        Returns:
            Dictionary with validation results
        """
        if not page_ids:
            return {
                "valid": True,
                "accessible_pages": [],
                "denied_pages": [],
                "total_requested": 0,
                "total_accessible": 0
            }
        
        accessible_pages = await self.get_user_accessible_pages(user_id, page_ids)
        accessible_set = set(accessible_pages)
        denied_pages = [pid for pid in page_ids if pid not in accessible_set]
        
        return {
            "valid": len(denied_pages) == 0,
            "accessible_pages": accessible_pages,
            "denied_pages": denied_pages,
            "total_requested": len(page_ids),
            "total_accessible": len(accessible_pages),
            "operation": operation
        }
    
    async def get_shared_pages_statistics(self, user_id: int) -> Dict[str, Any]:
        """
        Get statistics about shared pages for a user
        
        Args:
            user_id: User ID
            
        Returns:
            Dictionary with sharing statistics
        """
        query = text("""
            WITH user_pages AS (
                SELECT DISTINCT pp.page_id
                FROM project_pages pp
                JOIN projects p ON pp.project_id = p.id
                WHERE p.user_id = :user_id
            ),
            shared_pages AS (
                SELECT up.page_id, COUNT(DISTINCT pp.project_id) as project_count
                FROM user_pages up
                JOIN project_pages pp ON up.page_id = pp.page_id
                JOIN projects p ON pp.project_id = p.id
                WHERE p.user_id = :user_id
                GROUP BY up.page_id
                HAVING COUNT(DISTINCT pp.project_id) > 1
            )
            SELECT 
                COUNT(DISTINCT up.page_id) as total_pages,
                COUNT(DISTINCT sp.page_id) as shared_pages,
                COALESCE(AVG(sp.project_count), 0) as avg_projects_per_shared_page
            FROM user_pages up
            LEFT JOIN shared_pages sp ON up.page_id = sp.page_id
        """)
        
        result = await self.db.execute(query, {"user_id": user_id})
        row = result.fetchone()
        
        return {
            "total_pages": row[0] or 0,
            "shared_pages": row[1] or 0,
            "unique_pages": (row[0] or 0) - (row[1] or 0),
            "avg_projects_per_shared_page": float(row[2] or 0),
            "sharing_efficiency": round((row[1] or 0) / max(row[0] or 1, 1) * 100, 2)
        }
    
    async def invalidate_user_cache(self, user_id: int) -> None:
        """Invalidate all cached data for a user"""
        cache_key = f"user_accessible_pages:{user_id}"
        if cache_key in self._cache:
            del self._cache[cache_key]
    
    async def invalidate_project_cache(self, project_id: int) -> None:
        """Invalidate cached data for a project"""
        # Get project owner and invalidate their cache
        project = await self.db.get(Project, project_id)
        if project:
            await self.invalidate_user_cache(project.user_id)


class PageAccessControlMiddleware:
    """Middleware for automatic page access validation"""
    
    def __init__(self, access_control: PageAccessControl):
        self.access_control = access_control
    
    async def validate_page_access(
        self,
        user_id: int,
        page_id: UUID,
        operation: str = "read"
    ) -> bool:
        """
        Validate page access with logging
        
        Args:
            user_id: User ID
            page_id: Page ID
            operation: Operation type
            
        Returns:
            True if access is allowed
            
        Raises:
            PermissionError: If access is denied
        """
        has_access = await self.access_control.can_user_access_page(user_id, page_id)
        
        if not has_access:
            logger.warning(
                f"Access denied: user {user_id} attempted {operation} on page {page_id}"
            )
            raise PermissionError(f"Access denied to page {page_id}")
        
        logger.debug(f"Access granted: user {user_id} {operation} page {page_id}")
        return True
    
    async def validate_bulk_page_access(
        self,
        user_id: int,
        page_ids: List[UUID],
        operation: str = "read"
    ) -> List[UUID]:
        """
        Validate bulk page access and return accessible pages
        
        Args:
            user_id: User ID
            page_ids: List of page IDs
            operation: Operation type
            
        Returns:
            List of accessible page IDs
            
        Raises:
            PermissionError: If no pages are accessible
        """
        validation = await self.access_control.validate_bulk_page_access(
            user_id, page_ids, operation
        )
        
        if not validation["accessible_pages"]:
            logger.warning(
                f"Bulk access denied: user {user_id} attempted {operation} on "
                f"{len(page_ids)} pages, none accessible"
            )
            raise PermissionError("No accessible pages in the requested set")
        
        if validation["denied_pages"]:
            logger.info(
                f"Partial access: user {user_id} {operation} - "
                f"{len(validation['accessible_pages'])} allowed, "
                f"{len(validation['denied_pages'])} denied"
            )
        
        return validation["accessible_pages"]


async def get_page_access_control(db: AsyncSession = Depends(get_db)) -> PageAccessControl:
    """Dependency injection for page access control"""
    return PageAccessControl(db)