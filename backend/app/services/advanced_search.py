"""
Advanced search and filtering service - DEPRECATED

TODO: URGENT - This entire service needs complete rewrite for shared pages architecture.
Currently provides stub implementations to prevent server startup errors.
Use app.services.shared_pages_meilisearch instead for proper shared pages search.
"""
import re
from datetime import datetime, date
from typing import Dict, Any, List, Optional
from sqlmodel import select, and_, or_, func, cast, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession
import logging

from app.models.project import Project, Domain
from app.models.shared_pages import PageV2, PageReviewStatus, ProjectPage
from app.models.library import StarredItem, ItemType

logger = logging.getLogger(__name__)


class SearchFilters:
    """Container for search filter parameters"""
    
    def __init__(
        self,
        query: Optional[str] = None,
        projects: Optional[List[int]] = None,
        domains: Optional[List[str]] = None,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
        content_types: Optional[List[str]] = None,
        languages: Optional[List[str]] = None,
        word_count_min: Optional[int] = None,
        word_count_max: Optional[int] = None,
        has_title: Optional[bool] = None,
        has_author: Optional[bool] = None,
        status_codes: Optional[List[int]] = None,
        starred: Optional[bool] = None,
        tags: Optional[List[str]] = None,
        review_statuses: Optional[List[str]] = None,
        include_keywords: Optional[List[str]] = None,
        exclude_keywords: Optional[List[str]] = None,
        sort_by: str = "scraped_at",
        sort_order: str = "desc",
        page: int = 1,
        page_size: int = 20,
        # Page management parity filters
        similar_to_page: Optional[str] = None,
        content_similarity_threshold: float = 0.8,
        include_facets: bool = True
    ):
        self.query = query
        self.projects = projects or []
        self.domains = domains or []
        self.date_from = date_from
        self.date_to = date_to
        self.content_types = content_types or []
        self.languages = languages or []
        self.word_count_min = word_count_min
        self.word_count_max = word_count_max
        self.has_title = has_title
        self.has_author = has_author
        self.status_codes = status_codes or []
        self.starred = starred
        self.tags = tags or []
        self.review_statuses = review_statuses or []
        self.include_keywords = include_keywords or []
        self.exclude_keywords = exclude_keywords or []
        self.sort_by = sort_by
        self.sort_order = sort_order
        self.page = max(1, page)
        self.page_size = min(max(1, page_size), 100)
        # Page management parity filters
        self.similar_to_page = similar_to_page
        self.content_similarity_threshold = content_similarity_threshold
        self.include_facets = include_facets


class AdvancedSearchService:
    """
    DEPRECATED: Advanced search service for legacy Page system
    
    This service has been replaced by shared_pages_meilisearch.py for the new
    shared pages architecture. Currently provides stub implementations only.
    """
    
    @staticmethod
    async def search_pages(
        db: AsyncSession,
        filters: SearchFilters,
        user_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        DEPRECATED: Returns empty results during migration to shared pages architecture
        """
        logger.warning("AdvancedSearchService.search_pages is deprecated - use shared_pages_meilisearch instead")
        
        return {
            "pages": [],
            "total": 0,
            "page": filters.page,
            "page_size": filters.page_size,
            "total_pages": 0,
            "facets": {} if filters.include_facets else None
        }

    @staticmethod
    async def get_search_facets(
        db: AsyncSession,
        filters: SearchFilters,
        user_id: Optional[int] = None
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        DEPRECATED: Returns empty facets during migration
        """
        logger.warning("AdvancedSearchService.get_search_facets is deprecated")
        
        return {
            "content_types": [],
            "languages": [],
            "status_codes": [],
            "domains": [],
            "projects": []
        }

    @staticmethod  
    async def get_similar_pages(
        db: AsyncSession,
        page_id: str,
        limit: int = 10,
        user_id: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        DEPRECATED: Returns empty list during migration
        """
        logger.warning("AdvancedSearchService.get_similar_pages is deprecated")
        return []

    @staticmethod
    async def create_saved_search(
        db: AsyncSession,
        user_id: int,
        name: str,
        filters: SearchFilters,
        alert_enabled: bool = False
    ) -> Dict[str, Any]:
        """
        DEPRECATED: Saved search creation disabled during migration
        """
        logger.warning("AdvancedSearchService.create_saved_search is deprecated")
        return {
            "error": "Saved search creation is temporarily disabled during migration to shared pages architecture"
        }

    @staticmethod
    def parse_search_query(query: str) -> Dict[str, Any]:
        """
        Basic search query parsing (simplified implementation)
        """
        if not query:
            return {
                "terms": [],
                "phrases": [],
                "exclude_terms": [],
                "site_filters": [],
                "date_filters": {}
            }
            
        terms = query.split()
        return {
            "terms": terms,
            "phrases": [],
            "exclude_terms": [],
            "site_filters": [],
            "date_filters": {}
        }