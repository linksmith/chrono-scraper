"""
Enhanced Meilisearch service for shared pages architecture

Handles indexing and searching with multi-project support while maintaining
security boundaries and optimal search performance.
"""
import json
import logging
from datetime import datetime
from typing import List, Dict, Any, Optional, Set
from uuid import UUID

import meilisearch_python_async as meilisearch
from fastapi import Depends
from sqlmodel import Session, select
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.core.config import settings
from app.models.shared_pages import PageV2, ProjectPage, PageReviewStatus
from app.models.project import Project
from app.services.page_access_control import PageAccessControl, get_page_access_control

logger = logging.getLogger(__name__)


class SharedPageDocument:
    """Document structure for Meilisearch with multi-project support"""
    
    def __init__(self, page: PageV2, project_associations: List[ProjectPage]):
        self.id = str(page.id)
        self.url = page.url
        self.title = page.title or page.extracted_title or ""
        self.content = page.extracted_text or page.markdown_content or ""
        self.description = page.meta_description or ""
        self.author = page.author or ""
        self.language = page.language or ""
        self.timestamp = page.unix_timestamp
        self.capture_date = page.capture_date.isoformat() if page.capture_date else None
        self.created_at = page.created_at.isoformat()
        self.quality_score = float(page.quality_score) if page.quality_score else None
        self.word_count = page.word_count or 0
        self.character_count = page.character_count or 0
        
        # Multiple project associations
        self.project_ids = [pa.project_id for pa in project_associations]
        self.domain_ids = [pa.domain_id for pa in project_associations if pa.domain_id]
        
        # Aggregated metadata from all projects
        self.all_tags = self._collect_unique_tags(project_associations)
        self.is_starred_in_any = any(pa.is_starred for pa in project_associations)
        self.review_statuses = list(set(
            pa.review_status.value if isinstance(pa.review_status, PageReviewStatus) 
            else pa.review_status 
            for pa in project_associations 
            if pa.review_status
        ))
        self.categories = list(set(
            pa.page_category.value if hasattr(pa.page_category, 'value') 
            else pa.page_category
            for pa in project_associations 
            if pa.page_category
        ))
        self.priority_levels = list(set(
            pa.priority_level.value if hasattr(pa.priority_level, 'value')
            else pa.priority_level
            for pa in project_associations 
            if pa.priority_level
        ))
        
        # Statistics
        self.project_count = len(self.project_ids)
        self.is_shared = self.project_count > 1
    
    def _collect_unique_tags(self, associations: List[ProjectPage]) -> List[str]:
        """Collect unique tags from all project associations"""
        all_tags = set()
        for pa in associations:
            if pa.tags:
                all_tags.update(pa.tags)
        return list(all_tags)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for Meilisearch indexing"""
        return {
            "id": self.id,
            "url": self.url,
            "title": self.title,
            "content": self.content,
            "description": self.description,
            "author": self.author,
            "language": self.language,
            "timestamp": self.timestamp,
            "capture_date": self.capture_date,
            "created_at": self.created_at,
            "quality_score": self.quality_score,
            "word_count": self.word_count,
            "character_count": self.character_count,
            
            # Multi-project fields
            "project_ids": self.project_ids,
            "domain_ids": self.domain_ids,
            "tags": self.all_tags,
            "is_starred": self.is_starred_in_any,
            "review_statuses": self.review_statuses,
            "categories": self.categories,
            "priority_levels": self.priority_levels,
            
            # Sharing metadata
            "project_count": self.project_count,
            "is_shared": self.is_shared
        }


class SharedPagesMeilisearchService:
    """Enhanced Meilisearch service for shared pages architecture"""
    
    def __init__(self, db: AsyncSession, access_control: Optional[PageAccessControl] = None):
        self.db = db
        self.access_control = access_control
        
        # Initialize Meilisearch client
        self.client = meilisearch.Client(
            settings.MEILISEARCH_HOST,
            settings.MEILISEARCH_MASTER_KEY
        )
        self.index_name = "shared_pages"
        self.index = self.client.index(self.index_name)
        
        # Note: Index configuration will be done lazily on first search
        self._index_configured = False
    
    async def _configure_index(self):
        """Configure Meilisearch index for multi-project filtering"""
        if self._index_configured:
            return
            
        try:
            # Filterable attributes for security and functionality
            await self.index.update_filterable_attributes([
                "project_ids",
                "domain_ids", 
                "tags",
                "is_starred",
                "review_statuses",
                "categories",
                "priority_levels",
                "timestamp",
                "quality_score",
                "word_count",
                "language",
                "project_count",
                "is_shared",
                "capture_date"
            ])
            
            # Searchable attributes with proper ranking
            await self.index.update_searchable_attributes([
                "title",
                "content",
                "description",
                "author",
                "url",
                "tags"
            ])
            
            # Ranking rules for relevance
            await self.index.update_ranking_rules([
                "words",
                "typo", 
                "proximity",
                "attribute",
                "sort",
                "exactness",
                "quality_score:desc",
                "word_count:desc"
            ])
            
            # Sortable attributes
            await self.index.update_sortable_attributes([
                "timestamp",
                "created_at",
                "quality_score",
                "word_count",
                "project_count"
            ])
            
            self._index_configured = True
            logger.info(f"Configured Meilisearch index: {self.index_name}")
            
        except Exception as e:
            logger.error(f"Failed to configure Meilisearch index: {e}")
    
    async def index_page(self, page: PageV2, project_id: Optional[int] = None) -> None:
        """Index or update page with all project associations"""
        try:
            # Get all project associations for this page
            stmt = select(ProjectPage).where(ProjectPage.page_id == page.id)
            result = await self.db.execute(stmt)
            associations = result.scalars().all()
            
            if not associations:
                logger.warning(f"No project associations found for page {page.id}")
                return
            
            # Create enhanced document
            document = SharedPageDocument(page, associations)
            
            # Add or update in Meilisearch
            await self.index.add_documents([document.to_dict()])
            
            logger.debug(f"Indexed page {page.id} with {len(associations)} project associations")
            
        except Exception as e:
            logger.error(f"Failed to index page {page.id}: {e}")
            raise
    
    async def bulk_index_pages(self, page_ids: List[UUID]) -> Dict[str, Any]:
        """Bulk index multiple pages efficiently"""
        if not page_ids:
            return {"indexed": 0, "failed": 0}
        
        try:
            # Get pages with their associations in one query
            query = text("""
                SELECT 
                    p.id, p.url, p.title, p.extracted_title, p.extracted_text,
                    p.markdown_content, p.meta_description, p.author, p.language,
                    p.unix_timestamp, p.capture_date, p.created_at, p.quality_score,
                    p.word_count, p.character_count,
                    pp.project_id, pp.domain_id, pp.tags, pp.is_starred,
                    pp.review_status, pp.page_category, pp.priority_level
                FROM pages_v2 p
                JOIN project_pages pp ON p.id = pp.page_id
                WHERE p.id = ANY(:page_ids)
                ORDER BY p.id
            """)
            
            result = await self.db.execute(query, {"page_ids": [str(pid) for pid in page_ids]})
            rows = result.fetchall()
            
            # Group by page_id
            pages_data = {}
            for row in rows:
                page_id = row[0]
                if page_id not in pages_data:
                    pages_data[page_id] = {
                        "page_data": row[:15],  # Page fields
                        "associations": []
                    }
                
                # Add association data
                association_data = {
                    "project_id": row[15],
                    "domain_id": row[16],
                    "tags": row[17] or [],
                    "is_starred": row[18],
                    "review_status": row[19],
                    "page_category": row[20],
                    "priority_level": row[21]
                }
                pages_data[page_id]["associations"].append(association_data)
            
            # Create documents for bulk indexing
            documents = []
            for page_id, data in pages_data.items():
                try:
                    # Create PageV2 object from row data
                    page_row = data["page_data"]
                    page = PageV2(
                        id=UUID(page_row[0]),
                        url=page_row[1],
                        title=page_row[2],
                        extracted_title=page_row[3],
                        extracted_text=page_row[4],
                        markdown_content=page_row[5],
                        meta_description=page_row[6],
                        author=page_row[7],
                        language=page_row[8],
                        unix_timestamp=page_row[9],
                        capture_date=page_row[10],
                        created_at=page_row[11],
                        quality_score=page_row[12],
                        word_count=page_row[13],
                        character_count=page_row[14]
                    )
                    
                    # Create ProjectPage objects from association data
                    associations = []
                    for assoc_data in data["associations"]:
                        pp = ProjectPage(**assoc_data)
                        associations.append(pp)
                    
                    # Create document
                    document = SharedPageDocument(page, associations)
                    documents.append(document.to_dict())
                    
                except Exception as e:
                    logger.warning(f"Failed to prepare document for page {page_id}: {e}")
            
            # Bulk index in Meilisearch
            if documents:
                task_info = await self.index.add_documents(documents)
                logger.info(f"Bulk indexed {len(documents)} pages, task ID: {task_info.task_uid}")
            
            return {
                "indexed": len(documents),
                "failed": len(page_ids) - len(documents),
                "total_requested": len(page_ids)
            }
            
        except Exception as e:
            logger.error(f"Bulk indexing failed: {e}")
            return {"indexed": 0, "failed": len(page_ids), "error": str(e)}
    
    async def search_user_pages(
        self,
        user_id: int,
        query: str,
        project_id: Optional[int] = None,
        filters: Optional[Dict[str, Any]] = None,
        limit: int = 100,
        offset: int = 0,
        sort: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """Search pages with security filtering and project scoping"""
        try:
            # Get user's accessible projects
            if self.access_control:
                user_projects = await self._get_user_projects(user_id)
            else:
                # Fallback: query database directly
                user_projects = await self._get_user_projects_fallback(user_id)
            
            if not user_projects:
                return {
                    "hits": [],
                    "query": query,
                    "limit": limit,
                    "offset": offset,
                    "estimatedTotalHits": 0,
                    "processingTimeMs": 0
                }
            
            project_ids = [p.id for p in user_projects]
            
            # Build filter string for security
            if project_id and project_id in project_ids:
                # Search within specific project
                filter_str = f"project_ids = {project_id}"
            else:
                # Search across all user's projects
                filter_str = f"project_ids IN [{', '.join(map(str, project_ids))}]"
            
            # Add additional filters
            if filters:
                additional_filters = self._build_filter_string(filters)
                if additional_filters:
                    filter_str += f" AND {additional_filters}"
            
            # Prepare search options
            search_options = {
                "filter": filter_str,
                "limit": limit,
                "offset": offset,
                "attributes_to_retrieve": [
                    "id", "url", "title", "content", "description", "author",
                    "timestamp", "capture_date", "quality_score", "word_count",
                    "project_ids", "tags", "is_starred", "review_statuses",
                    "categories", "is_shared", "project_count"
                ],
                "attributes_to_highlight": ["title", "content", "description"],
                "highlight_pre_tag": "<mark>",
                "highlight_post_tag": "</mark>",
                "attributes_to_crop": ["content"],
                "crop_length": 200
            }
            
            # Add sorting
            if sort:
                search_options["sort"] = sort
            
            # Ensure index is configured
            await self._configure_index()
            
            # Execute search
            results = await self.index.search(query, **search_options)
            
            # Enhance results with project context
            enhanced_results = await self._enhance_search_results(
                results, user_id, project_ids
            )
            
            return enhanced_results
            
        except Exception as e:
            logger.error(f"Search failed for user {user_id}: {e}")
            raise
    
    async def update_page_project_association(
        self,
        page_id: UUID,
        project_id: int,
        operation: str = "add"
    ) -> None:
        """Update page-project association in search index"""
        try:
            # Get current document
            try:
                current_doc = await self.index.get_document(str(page_id))
            except Exception:
                # Document doesn't exist, need to index from scratch
                if operation == "add":
                    page = await self.db.get(PageV2, page_id)
                    if page:
                        await self.index_page(page, project_id)
                return
            
            # Update project associations
            project_ids = current_doc.get("project_ids", [])
            
            if operation == "add" and project_id not in project_ids:
                project_ids.append(project_id)
            elif operation == "remove" and project_id in project_ids:
                project_ids.remove(project_id)
            
            # If no projects left, remove document
            if not project_ids:
                await self.index.delete_document(str(page_id))
                logger.info(f"Removed page {page_id} from search index (no project associations)")
                return
            
            # Update document
            current_doc["project_ids"] = project_ids
            current_doc["project_count"] = len(project_ids)
            current_doc["is_shared"] = len(project_ids) > 1
            
            await self.index.add_documents([current_doc])
            logger.debug(f"Updated page {page_id} project associations in search index")
            
        except Exception as e:
            logger.error(f"Failed to update page-project association: {e}")
    
    async def remove_project_from_all_pages(self, project_id: int) -> None:
        """Remove project association from all pages when project is deleted"""
        try:
            # Search for all documents with this project
            search_results = await self.index.search(
                "",
                filter=f"project_ids = {project_id}",
                limit=10000,  # Large limit to get all
                attributes_to_retrieve=["id", "project_ids"]
            )
            
            documents_to_update = []
            documents_to_delete = []
            
            for doc in search_results.hits:
                project_ids = doc.get("project_ids", [])
                
                # Remove this project
                if project_id in project_ids:
                    project_ids.remove(project_id)
                
                if not project_ids:
                    # No more projects, delete document
                    documents_to_delete.append(doc["id"])
                else:
                    # Update document
                    doc["project_ids"] = project_ids
                    doc["project_count"] = len(project_ids)
                    doc["is_shared"] = len(project_ids) > 1
                    documents_to_update.append(doc)
            
            # Perform bulk operations
            if documents_to_update:
                await self.index.add_documents(documents_to_update)
                logger.info(f"Updated {len(documents_to_update)} documents after removing project {project_id}")
            
            if documents_to_delete:
                await self.index.delete_documents(documents_to_delete)
                logger.info(f"Deleted {len(documents_to_delete)} documents after removing project {project_id}")
                
        except Exception as e:
            logger.error(f"Failed to remove project {project_id} from search index: {e}")
    
    async def get_search_statistics(self, user_id: int) -> Dict[str, Any]:
        """Get search statistics for user's accessible pages"""
        try:
            user_projects = await self._get_user_projects(user_id)
            if not user_projects:
                return {"total_pages": 0, "by_project": {}}
            
            project_ids = [p.id for p in user_projects]
            filter_str = f"project_ids IN [{', '.join(map(str, project_ids))}]"
            
            # Get overall statistics
            stats_search = await self.index.search(
                "",
                filter=filter_str,
                limit=0,  # We only want the count
                facets=["project_ids", "is_shared", "review_statuses", "categories"]
            )
            
            return {
                "total_pages": stats_search.estimated_total_hits,
                "facet_distribution": getattr(stats_search, 'facet_distribution', {}),
                "processing_time_ms": stats_search.processing_time_ms
            }
            
        except Exception as e:
            logger.error(f"Failed to get search statistics: {e}")
            return {"error": str(e)}
    
    async def _get_user_projects(self, user_id: int) -> List[Project]:
        """Get user's projects with caching"""
        stmt = select(Project).where(Project.user_id == user_id)
        result = await self.db.execute(stmt)
        return result.scalars().all()
    
    async def _get_user_projects_fallback(self, user_id: int) -> List[Project]:
        """Fallback method to get user projects"""
        return await self._get_user_projects(user_id)
    
    def _build_filter_string(self, filters: Dict[str, Any]) -> str:
        """Build Meilisearch filter string from filters dict"""
        filter_parts = []
        
        if filters.get("is_starred"):
            filter_parts.append("is_starred = true")
        
        if filters.get("tags"):
            tag_filters = [f"tags = {tag}" for tag in filters["tags"]]
            filter_parts.append(f"({' OR '.join(tag_filters)})")
        
        if filters.get("review_statuses"):
            status_filters = [f"review_statuses = {status}" for status in filters["review_statuses"]]
            filter_parts.append(f"({' OR '.join(status_filters)})")
        
        if filters.get("categories"):
            cat_filters = [f"categories = {cat}" for cat in filters["categories"]]
            filter_parts.append(f"({' OR '.join(cat_filters)})")
        
        if filters.get("min_quality_score"):
            filter_parts.append(f"quality_score >= {filters['min_quality_score']}")
        
        if filters.get("min_word_count"):
            filter_parts.append(f"word_count >= {filters['min_word_count']}")
        
        if filters.get("date_range"):
            date_range = filters["date_range"]
            if date_range.get("start"):
                filter_parts.append(f"timestamp >= {date_range['start']}")
            if date_range.get("end"):
                filter_parts.append(f"timestamp <= {date_range['end']}")
        
        if filters.get("is_shared") is not None:
            filter_parts.append(f"is_shared = {str(filters['is_shared']).lower()}")
        
        return " AND ".join(filter_parts)
    
    async def _enhance_search_results(
        self,
        results: Dict[str, Any],
        user_id: int,
        user_project_ids: List[int]
    ) -> Dict[str, Any]:
        """Enhance search results with user-specific context"""
        enhanced_hits = []
        
        for hit in results.hits:
            # Add user context
            hit["user_has_access"] = True  # Already filtered by user's projects
            hit["accessible_projects"] = [
                pid for pid in hit.get("project_ids", []) 
                if pid in user_project_ids
            ]
            
            enhanced_hits.append(hit)
        
        # Return as dictionary for API compatibility
        return {
            "hits": enhanced_hits,
            "query": results.query,
            "processingTimeMs": results.processing_time_ms,
            "limit": results.limit,
            "offset": results.offset,
            "estimatedTotalHits": results.estimated_total_hits
        }


async def get_shared_pages_meilisearch_service(
    db: AsyncSession = Depends(get_db),
    access_control: Optional[PageAccessControl] = Depends(get_page_access_control)
) -> SharedPagesMeilisearchService:
    """Dependency injection for shared pages Meilisearch service"""
    return SharedPagesMeilisearchService(db, access_control)