"""
Advanced search and filtering service
"""
import re
from datetime import datetime, date
from typing import Dict, Any, List, Optional, Union
from sqlmodel import select, and_, or_, func, cast, String
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
import logging

from app.models.project import Project, Domain, Page
from app.models.library import StarredItem, ItemType
from app.models.user import User
from app.services.meilisearch_service import MeilisearchService

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
        keywords: Optional[List[str]] = None,
        exclude_keywords: Optional[List[str]] = None,
        sort_by: str = "scraped_at",
        sort_order: str = "desc",
        page: int = 1,
        per_page: int = 20
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
        self.keywords = keywords or []
        self.exclude_keywords = exclude_keywords or []
        self.sort_by = sort_by
        self.sort_order = sort_order
        self.page = max(1, page)
        self.per_page = min(100, max(1, per_page))


class AdvancedSearchService:
    """Service for advanced search and filtering capabilities"""
    
    @staticmethod
    async def search_pages(
        db: AsyncSession,
        filters: SearchFilters,
        user_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Perform advanced search on pages with multiple filters
        """
        # Base query with joins
        query = (
            select(Page, Domain, Project, StarredItem.id)
            .join(Domain, Page.domain_id == Domain.id)
            .join(Project, Domain.project_id == Project.id)
            .outerjoin(
                StarredItem,
                and_(
                    StarredItem.page_id == Page.id,
                    StarredItem.user_id == user_id if user_id is not None else (StarredItem.user_id == Page.id - Page.id),
                    StarredItem.item_type == ItemType.PAGE,
                )
            )
        )
        
        # User access control
        if user_id:
            query = query.where(Project.user_id == user_id)
        
        # Apply filters
        conditions = []
        
        # Text search in extracted content
        if filters.query:
            search_terms = filters.query.split()
            for term in search_terms:
                conditions.append(
                    or_(
                        Page.extracted_text.ilike(f"%{term}%"),
                        Page.extracted_title.ilike(f"%{term}%"),
                        Page.meta_description.ilike(f"%{term}%")
                    )
                )
        
        # Project filter
        if filters.projects:
            conditions.append(Project.id.in_(filters.projects))
        
        # Domain filter
        if filters.domains:
            domain_conditions = []
            for domain in filters.domains:
                if '*' in domain or '?' in domain:
                    # Wildcard support
                    pattern = domain.replace('*', '%').replace('?', '_')
                    domain_conditions.append(Domain.domain_name.like(pattern))
                else:
                    domain_conditions.append(Domain.domain_name == domain)
            conditions.append(or_(*domain_conditions))
        
        # Date range filter
        if filters.date_from:
            conditions.append(Page.capture_date >= datetime.combine(filters.date_from, datetime.min.time()))
        if filters.date_to:
            conditions.append(Page.capture_date <= datetime.combine(filters.date_to, datetime.max.time()))
        
        # Content type filter
        if filters.content_types:
            content_conditions = []
            for content_type in filters.content_types:
                content_conditions.append(Page.content_type.ilike(f"%{content_type}%"))
            conditions.append(or_(*content_conditions))
        
        # Language filter
        if filters.languages:
            conditions.append(Page.language.in_(filters.languages))
        
        # Word count filters
        if filters.word_count_min is not None:
            conditions.append(Page.word_count >= filters.word_count_min)
        if filters.word_count_max is not None:
            conditions.append(Page.word_count <= filters.word_count_max)
        
        # Metadata presence filters
        if filters.has_title is not None:
            if filters.has_title:
                conditions.append(Page.extracted_title.is_not(None))
                conditions.append(Page.extracted_title != "")
            else:
                conditions.append(
                    or_(Page.extracted_title.is_(None), Page.extracted_title == "")
                )
        
        if filters.has_author is not None:
            if filters.has_author:
                conditions.append(Page.author.is_not(None))
                conditions.append(Page.author != "")
            else:
                conditions.append(
                    or_(Page.author.is_(None), Page.author == "")
                )
        
        # Status code filter
        if filters.status_codes:
            conditions.append(Page.status_code.in_(filters.status_codes))
        
        # Keyword inclusion filter
        if filters.keywords:
            for keyword in filters.keywords:
                conditions.append(
                    or_(
                        Page.extracted_text.ilike(f"%{keyword}%"),
                        Page.meta_keywords.ilike(f"%{keyword}%")
                    )
                )
        
        # Keyword exclusion filter
        if filters.exclude_keywords:
            for keyword in filters.exclude_keywords:
                conditions.append(
                    and_(
                        or_(Page.extracted_text.is_(None), ~Page.extracted_text.ilike(f"%{keyword}%")),
                        or_(Page.meta_keywords.is_(None), ~Page.meta_keywords.ilike(f"%{keyword}%"))
                    )
                )
        
        # Apply all conditions
        if conditions:
            query = query.where(and_(*conditions))
        
        # Get total count
        count_query = select(func.count()).select_from(query.subquery())
        total_result = await db.execute(count_query)
        total = total_result.scalar() or 0
        
        # Apply sorting
        sort_column = getattr(Page, filters.sort_by, Page.scraped_at)
        if filters.sort_order.lower() == 'asc':
            query = query.order_by(sort_column.asc())
        else:
            query = query.order_by(sort_column.desc())
        
        # Apply pagination
        offset = (filters.page - 1) * filters.per_page
        query = query.offset(offset).limit(filters.per_page)
        
        # Execute query
        result = await db.execute(query)
        rows = result.all()
        
        # Helper to build a snippet around first matched query term
        def build_match_snippet(text: Optional[str], query: Optional[str], max_length: int = 200) -> Optional[str]:
            if not text:
                return None
            if not query:
                # Fallback to leading preview
                if len(text) > max_length:
                    return text[:max_length] + "..."
                return text
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
                # No match found; fallback to leading preview
                if len(text) > max_length:
                    return text[:max_length] + "..."
                return text
            # Center snippet around the first match
            context = max_length
            start = max(0, first_index - context // 3)
            end = min(len(text), first_index + match_len + (2 * context) // 3)
            snippet = text[start:end].strip()
            if start > 0:
                snippet = "..." + snippet
            if end < len(text):
                snippet = snippet + "..."
            return snippet

        # Format results
        pages = []
        for page, domain, project, star_id in rows:
            snippet = build_match_snippet(page.extracted_text, filters.query, 200)
            pages.append({
                "id": page.id,
                "original_url": page.original_url,
                "wayback_url": page.wayback_url,
                "title": page.extracted_title or page.title,
                "content_preview": snippet,
                "word_count": page.word_count,
                "character_count": page.character_count,
                "capture_date": page.capture_date.isoformat() if page.capture_date else None,
                "scraped_at": page.scraped_at.isoformat() if page.scraped_at else None,
                "status_code": page.status_code,
                "content_type": page.content_type,
                "language": page.language,
                "author": page.author,
                "meta_description": page.meta_description,
                "is_starred": bool(star_id),
                "domain": {
                    "id": domain.id,
                    "domain_name": domain.domain_name
                },
                "project": {
                    "id": project.id,
                    "name": project.name
                }
            })
        
        # Calculate pagination info
        total_pages = (total + filters.per_page - 1) // filters.per_page
        has_next = filters.page < total_pages
        has_prev = filters.page > 1
        
        return {
            "pages": pages,
            "pagination": {
                "total": total,
                "page": filters.page,
                "per_page": filters.per_page,
                "total_pages": total_pages,
                "has_next": has_next,
                "has_prev": has_prev
            },
            "filters_applied": filters.__dict__
        }
    
    @staticmethod
    async def get_search_facets(
        db: AsyncSession,
        user_id: Optional[int] = None,
        project_ids: Optional[List[int]] = None
    ) -> Dict[str, Any]:
        """
        Get available facet values for search filters
        """
        # Base query for user's accessible pages
        base_query = (
            select(Page)
            .join(Domain, Page.domain_id == Domain.id)
            .join(Project, Domain.project_id == Project.id)
        )
        
        if user_id:
            base_query = base_query.where(Project.user_id == user_id)
        
        if project_ids:
            base_query = base_query.where(Project.id.in_(project_ids))
        
        # Get content types
        content_types_query = (
            select(Page.content_type, func.count().label('count'))
            .select_from(base_query.subquery())
            .where(Page.content_type.is_not(None))
            .group_by(Page.content_type)
            .order_by(func.count().desc())
        )
        content_types_result = await db.execute(content_types_query)
        content_types = [{"value": ct, "count": count} for ct, count in content_types_result.all()]
        
        # Get languages
        languages_query = (
            select(Page.language, func.count().label('count'))
            .select_from(base_query.subquery())
            .where(Page.language.is_not(None))
            .group_by(Page.language)
            .order_by(func.count().desc())
        )
        languages_result = await db.execute(languages_query)
        languages = [{"value": lang, "count": count} for lang, count in languages_result.all()]
        
        # Get status codes
        status_codes_query = (
            select(Page.status_code, func.count().label('count'))
            .select_from(base_query.subquery())
            .where(Page.status_code.is_not(None))
            .group_by(Page.status_code)
            .order_by(Page.status_code)
        )
        status_codes_result = await db.execute(status_codes_query)
        status_codes = [{"value": sc, "count": count} for sc, count in status_codes_result.all()]
        
        # Get domains - directly query with joins
        domains_query = (
            select(Domain.domain_name, func.count().label('count'))
            .select_from(Page)
            .join(Domain, Page.domain_id == Domain.id)
            .join(Project, Domain.project_id == Project.id)
        )
        if user_id:
            domains_query = domains_query.where(Project.user_id == user_id)
        if project_ids:
            domains_query = domains_query.where(Project.id.in_(project_ids))
        
        domains_query = domains_query.group_by(Domain.domain_name).order_by(Domain.domain_name)
        domains_result = await db.execute(domains_query)
        domains = [{"value": domain, "count": count} for domain, count in domains_result.all()]
        
        # Get projects - directly query with joins
        projects_query = (
            select(Project.id, Project.name, func.count().label('count'))
            .select_from(Page)
            .join(Domain, Page.domain_id == Domain.id)
            .join(Project, Domain.project_id == Project.id)
        )
        if user_id:
            projects_query = projects_query.where(Project.user_id == user_id)
        if project_ids:
            projects_query = projects_query.where(Project.id.in_(project_ids))
        
        projects_query = projects_query.group_by(Project.id, Project.name).order_by(Project.name)
        projects_result = await db.execute(projects_query)
        projects = [{"value": proj_id, "label": name, "count": count} for proj_id, name, count in projects_result.all()]
        
        # Get date ranges
        date_range_query = (
            select(
                func.min(Page.capture_date).label('min_date'),
                func.max(Page.capture_date).label('max_date'),
                func.count().label('total')
            )
            .select_from(base_query.subquery())
            .where(Page.capture_date.is_not(None))
        )
        date_range_result = await db.execute(date_range_query)
        date_range = date_range_result.first()
        
        # Get word count statistics
        word_count_query = (
            select(
                func.min(Page.word_count).label('min_words'),
                func.max(Page.word_count).label('max_words'),
                func.avg(Page.word_count).label('avg_words')
            )
            .select_from(base_query.subquery())
            .where(Page.word_count.is_not(None))
        )
        word_count_result = await db.execute(word_count_query)
        word_count_stats = word_count_result.first()
        
        return {
            "content_types": content_types,
            "languages": languages,
            "status_codes": status_codes,
            "domains": domains,
            "projects": projects,
            "date_range": {
                "min": date_range.min_date.isoformat() if date_range and date_range.min_date else None,
                "max": date_range.max_date.isoformat() if date_range and date_range.max_date else None,
                "total": date_range.total if date_range else 0
            },
            "word_count": {
                "min": int(word_count_stats.min_words) if word_count_stats and word_count_stats.min_words else 0,
                "max": int(word_count_stats.max_words) if word_count_stats and word_count_stats.max_words else 0,
                "avg": int(word_count_stats.avg_words) if word_count_stats and word_count_stats.avg_words else 0
            }
        }
    
    @staticmethod
    async def get_similar_pages(
        db: AsyncSession,
        page_id: int,
        user_id: Optional[int] = None,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Find pages similar to the given page based on content hash and metadata
        """
        # Get the reference page
        page_query = (
            select(Page, Domain, Project)
            .join(Domain)
            .join(Project)
            .where(Page.id == page_id)
        )
        
        if user_id:
            page_query = page_query.where(Project.user_id == user_id)
        
        page_result = await db.execute(page_query)
        page_row = page_result.first()
        
        if not page_row:
            return []
        
        page, domain, project = page_row
        
        # Find similar pages
        similar_query = (
            select(Page, Domain, Project)
            .join(Domain, Page.domain_id == Domain.id)
            .join(Project, Domain.project_id == Project.id)
            .where(Page.id != page_id)
        )
        
        if user_id:
            similar_query = similar_query.where(Project.user_id == user_id)
        
        # Similarity conditions (ordered by priority)
        conditions = []
        
        # Same content hash (exact duplicates)
        if page.content_hash:
            conditions.append((Page.content_hash == page.content_hash, 100))
        
        # Same domain
        conditions.append((Page.domain_id == page.domain_id, 50))
        
        # Similar word count (within 20%)
        if page.word_count and page.word_count > 0:
            word_count_margin = max(50, int(page.word_count * 0.2))
            conditions.append((
                and_(
                    Page.word_count >= page.word_count - word_count_margin,
                    Page.word_count <= page.word_count + word_count_margin
                ), 30
            ))
        
        # Same content type
        if page.content_type:
            conditions.append((Page.content_type == page.content_type, 20))
        
        # Same language
        if page.language:
            conditions.append((Page.language == page.language, 15))
        
        # Same author
        if page.author:
            conditions.append((Page.author == page.author, 10))
        
        # Build query with similarity scoring
        case_conditions = []
        for condition, score in conditions:
            case_conditions.append((condition, score))
        
        # Create similarity score using CASE statements
        similarity_score = func.coalesce(
            func.sum(
                func.case(
                    *[
                        (cond, score) for cond, score in case_conditions
                    ],
                    else_=0
                )
            ),
            0
        ).label('similarity_score')
        
        similar_query = (
            similar_query
            .add_columns(similarity_score)
            .group_by(Page.id, Domain.id, Project.id)
            .having(similarity_score > 0)
            .order_by(similarity_score.desc())
            .limit(limit)
        )
        
        result = await db.execute(similar_query)
        rows = result.all()
        
        similar_pages = []
        for row in rows:
            sim_page, sim_domain, sim_project, score = row
            similar_pages.append({
                "id": sim_page.id,
                "original_url": sim_page.original_url,
                "title": sim_page.extracted_title or sim_page.title,
                "content_preview": (sim_page.extracted_text or "")[:150] + "..." if sim_page.extracted_text and len(sim_page.extracted_text) > 150 else sim_page.extracted_text,
                "word_count": sim_page.word_count,
                "capture_date": sim_page.capture_date.isoformat() if sim_page.capture_date else None,
                "domain_name": sim_domain.domain_name,
                "project_name": sim_project.name,
                "similarity_score": float(score)
            })
        
        return similar_pages
    
    @staticmethod
    async def create_saved_search(
        db: AsyncSession,
        user_id: int,
        name: str,
        filters: SearchFilters,
        description: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Save a search query for later use
        """
        # This would require a SavedSearch model - placeholder for now
        saved_search = {
            "id": 1,  # Would be generated
            "user_id": user_id,
            "name": name,
            "description": description,
            "filters": filters.__dict__,
            "created_at": datetime.utcnow().isoformat()
        }
        
        logger.info(f"Saved search '{name}' for user {user_id}")
        return saved_search
    
    @staticmethod
    def parse_search_query(query: str) -> Dict[str, Any]:
        """
        Parse advanced search query with operators
        
        Supports syntax like:
        - title:"exact phrase"
        - domain:example.com
        - wordcount:100..500
        - date:2023-01-01..2023-12-31
        - -exclude
        """
        parsed = {
            "text": [],
            "title": [],
            "domain": [],
            "wordcount": None,
            "date": None,
            "exclude": []
        }
        
        # Extract quoted phrases
        phrase_pattern = r'"([^"]*)"'
        phrases = re.findall(phrase_pattern, query)
        query_without_phrases = re.sub(phrase_pattern, '', query)
        
        # Extract field searches
        field_pattern = r'(\w+):([^\s]+)'
        field_matches = re.findall(field_pattern, query_without_phrases)
        
        for field, value in field_matches:
            field = field.lower()
            if field == 'title':
                parsed["title"].append(value)
            elif field == 'domain':
                parsed["domain"].append(value)
            elif field == 'wordcount':
                if '..' in value:
                    min_val, max_val = value.split('..')
                    parsed["wordcount"] = {
                        "min": int(min_val) if min_val else None,
                        "max": int(max_val) if max_val else None
                    }
                else:
                    parsed["wordcount"] = {"exact": int(value)}
            elif field == 'date':
                if '..' in value:
                    from_date, to_date = value.split('..')
                    parsed["date"] = {
                        "from": from_date if from_date else None,
                        "to": to_date if to_date else None
                    }
        
        # Remove field searches from query
        query_without_fields = re.sub(field_pattern, '', query_without_phrases)
        
        # Extract exclusions
        exclude_pattern = r'-(\w+)'
        exclusions = re.findall(exclude_pattern, query_without_fields)
        parsed["exclude"] = exclusions
        
        # Remove exclusions from query
        query_clean = re.sub(exclude_pattern, '', query_without_fields)
        
        # Add remaining terms as text search
        remaining_terms = query_clean.strip().split()
        parsed["text"].extend(remaining_terms)
        parsed["text"].extend(phrases)
        
        return parsed