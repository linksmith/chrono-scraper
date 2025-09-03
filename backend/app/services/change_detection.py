"""
Content change detection and diff tracking service
"""
import difflib
import hashlib
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from sqlmodel import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession
import logging

from app.models.project import Domain, Project
from app.models.shared_pages import PageV2 as Page

logger = logging.getLogger(__name__)


class ContentChange:
    """Container for content change information"""
    
    def __init__(
        self,
        page_id: int,
        change_type: str,
        old_content: Optional[str] = None,
        new_content: Optional[str] = None,
        diff: Optional[str] = None,
        similarity_score: Optional[float] = None,
        detected_at: Optional[datetime] = None
    ):
        self.page_id = page_id
        self.change_type = change_type  # 'new', 'modified', 'deleted'
        self.old_content = old_content
        self.new_content = new_content
        self.diff = diff
        self.similarity_score = similarity_score
        self.detected_at = detected_at or datetime.utcnow()


class ChangeDetectionService:
    """Service for detecting and tracking content changes"""
    
    @staticmethod
    def calculate_text_similarity(text1: str, text2: str) -> float:
        """
        Calculate similarity between two text strings using difflib
        Returns a score between 0.0 and 1.0
        """
        if not text1 and not text2:
            return 1.0
        if not text1 or not text2:
            return 0.0
        
        # Use SequenceMatcher for similarity
        matcher = difflib.SequenceMatcher(None, text1, text2)
        return matcher.ratio()
    
    @staticmethod
    def generate_content_diff(old_content: str, new_content: str, context_lines: int = 3) -> str:
        """
        Generate a unified diff between old and new content
        """
        old_lines = old_content.splitlines(keepends=True) if old_content else []
        new_lines = new_content.splitlines(keepends=True) if new_content else []
        
        diff = difflib.unified_diff(
            old_lines,
            new_lines,
            fromfile='old',
            tofile='new',
            n=context_lines
        )
        
        return ''.join(diff)
    
    @staticmethod
    def generate_html_diff(old_content: str, new_content: str) -> str:
        """
        Generate an HTML diff for visual comparison
        """
        old_lines = old_content.splitlines() if old_content else []
        new_lines = new_content.splitlines() if new_content else []
        
        differ = difflib.HtmlDiff(wrapcolumn=80)
        html_diff = differ.make_file(
            old_lines,
            new_lines,
            fromdesc='Previous Version',
            todesc='Current Version',
            context=True,
            numlines=3
        )
        
        return html_diff
    
    @staticmethod
    async def detect_page_changes(
        db: AsyncSession,
        page_id: int,
        new_content: str,
        new_title: Optional[str] = None,
        similarity_threshold: float = 0.95
    ) -> Optional[ContentChange]:
        """
        Detect changes in a page's content compared to its previous version
        """
        # Get the current page
        page_result = await db.execute(select(Page).where(Page.id == page_id))
        page = page_result.scalar_one_or_none()
        
        if not page:
            return None
        
        old_content = page.extracted_text or ""
        
        # Calculate content hash for new content
        new_content_hash = hashlib.sha256(new_content.encode('utf-8')).hexdigest()
        
        # Check if content is identical
        if page.content_hash == new_content_hash:
            return None  # No change detected
        
        # Calculate similarity
        similarity = ChangeDetectionService.calculate_text_similarity(old_content, new_content)
        
        # Determine change type
        if not old_content and new_content:
            change_type = "new"
        elif old_content and not new_content:
            change_type = "deleted"
        elif similarity < similarity_threshold:
            change_type = "modified"
        else:
            change_type = "minor_update"
        
        # Generate diff if content changed significantly
        diff = None
        if change_type in ["modified", "minor_update"] and old_content != new_content:
            diff = ChangeDetectionService.generate_content_diff(old_content, new_content)
        
        return ContentChange(
            page_id=page_id,
            change_type=change_type,
            old_content=old_content,
            new_content=new_content,
            diff=diff,
            similarity_score=similarity,
            detected_at=datetime.utcnow()
        )
    
    @staticmethod
    async def get_domain_changes(
        db: AsyncSession,
        domain_id: int,
        days: int = 30,
        user_id: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Get recent changes for all pages in a domain
        """
        since_date = datetime.utcnow() - timedelta(days=days)
        
        # Get pages with recent changes (based on scraped_at timestamp)
        query = (
            select(Page, Domain, Project)
            .join(Domain, Page.domain_id == Domain.id)
            .join(Project, Domain.project_id == Project.id)
            .where(
                and_(
                    Page.domain_id == domain_id,
                    Page.scraped_at >= since_date
                )
            )
        )
        
        if user_id:
            query = query.where(Project.user_id == user_id)
        
        query = query.order_by(Page.scraped_at.desc())
        
        result = await db.execute(query)
        rows = result.all()
        
        changes = []
        for page, domain, project in rows:
            # For now, we'll detect changes by comparing with potential previous versions
            # In a real implementation, you'd store page versions or change history
            changes.append({
                "page_id": page.id,
                "url": page.original_url,
                "title": page.extracted_title,
                "scraped_at": page.scraped_at.isoformat() if page.scraped_at else None,
                "word_count": page.word_count,
                "character_count": page.character_count,
                "content_hash": page.content_hash,
                "change_type": "unknown",  # Would be determined by actual change detection
                "domain_name": domain.domain_name,
                "project_name": project.name
            })
        
        return changes
    
    @staticmethod
    async def get_change_statistics(
        db: AsyncSession,
        project_id: Optional[int] = None,
        domain_id: Optional[int] = None,
        days: int = 30,
        user_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Get change statistics for projects or domains
        """
        since_date = datetime.utcnow() - timedelta(days=days)
        
        # Base query
        query = select(Page).join(Domain).join(Project)
        
        # Apply filters
        conditions = [Page.scraped_at >= since_date]
        
        if user_id:
            conditions.append(Project.user_id == user_id)
        if project_id:
            conditions.append(Project.id == project_id)
        if domain_id:
            conditions.append(Domain.id == domain_id)
        
        query = query.where(and_(*conditions))
        
        # Get total pages scraped
        total_result = await db.execute(select(func.count()).select_from(query.subquery()))
        total_scraped = total_result.scalar() or 0
        
        # Get pages by day
        daily_query = (
            select(
                func.date(Page.scraped_at).label('date'),
                func.count().label('count')
            )
            .select_from(query.subquery())
            .group_by(func.date(Page.scraped_at))
            .order_by(func.date(Page.scraped_at))
        )
        
        daily_result = await db.execute(daily_query)
        daily_stats = [
            {"date": row.date.isoformat(), "count": row.count}
            for row in daily_result.all()
        ]
        
        # Get unique content hashes (to estimate duplicate detection)
        unique_hashes_result = await db.execute(
            select(func.count(func.distinct(Page.content_hash)))
            .select_from(query.where(Page.content_hash.is_not(None)).subquery())
        )
        unique_content = unique_hashes_result.scalar() or 0
        
        # Estimate duplicates
        duplicates = max(0, total_scraped - unique_content)
        
        return {
            "period_days": days,
            "total_pages_scraped": total_scraped,
            "unique_content_pages": unique_content,
            "estimated_duplicates": duplicates,
            "duplicate_rate": (duplicates / total_scraped * 100) if total_scraped > 0 else 0,
            "daily_stats": daily_stats,
            "generated_at": datetime.utcnow().isoformat()
        }
    
    @staticmethod
    async def find_duplicate_content(
        db: AsyncSession,
        project_id: Optional[int] = None,
        user_id: Optional[int] = None,
        min_word_count: int = 50
    ) -> List[Dict[str, Any]]:
        """
        Find pages with duplicate content based on content hash
        """
        # Find content hashes that appear more than once
        subquery = (
            select(Page.content_hash, func.count().label('count'))
            .join(Domain)
            .join(Project)
            .where(
                and_(
                    Page.content_hash.is_not(None),
                    Page.word_count >= min_word_count
                )
            )
        )
        
        if user_id:
            subquery = subquery.where(Project.user_id == user_id)
        if project_id:
            subquery = subquery.where(Project.id == project_id)
        
        subquery = (
            subquery
            .group_by(Page.content_hash)
            .having(func.count() > 1)
            .subquery()
        )
        
        # Get the actual pages with duplicate content
        duplicate_query = (
            select(Page, Domain, Project)
            .join(Domain, Page.domain_id == Domain.id)
            .join(Project, Domain.project_id == Project.id)
            .join(subquery, Page.content_hash == subquery.c.content_hash)
            .order_by(Page.content_hash, Page.scraped_at.desc())
        )
        
        result = await db.execute(duplicate_query)
        rows = result.all()
        
        # Group by content hash
        duplicates = {}
        for page, domain, project in rows:
            hash_key = page.content_hash
            if hash_key not in duplicates:
                duplicates[hash_key] = {
                    "content_hash": hash_key,
                    "pages": []
                }
            
            duplicates[hash_key]["pages"].append({
                "id": page.id,
                "url": page.original_url,
                "title": page.extracted_title,
                "word_count": page.word_count,
                "scraped_at": page.scraped_at.isoformat() if page.scraped_at else None,
                "domain_name": domain.domain_name,
                "project_name": project.name
            })
        
        return list(duplicates.values())
    
    @staticmethod
    async def get_content_evolution(
        db: AsyncSession,
        url: str,
        project_id: Optional[int] = None,
        user_id: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Get the evolution of content for a specific URL over time
        """
        # Get all pages for this URL
        query = (
            select(Page, Domain, Project)
            .join(Domain, Page.domain_id == Domain.id)
            .join(Project, Domain.project_id == Project.id)
            .where(Page.original_url == url)
        )
        
        if user_id:
            query = query.where(Project.user_id == user_id)
        if project_id:
            query = query.where(Project.id == project_id)
        
        query = query.order_by(Page.capture_date.asc())
        
        result = await db.execute(query)
        rows = result.all()
        
        if not rows:
            return []
        
        evolution = []
        previous_content = None
        previous_hash = None
        
        for page, domain, project in rows:
            current_content = page.extracted_text or ""
            current_hash = page.content_hash
            
            # Calculate changes from previous version
            similarity = 1.0
            change_type = "new"
            
            if previous_content is not None:
                similarity = ChangeDetectionService.calculate_text_similarity(
                    previous_content, current_content
                )
                
                if previous_hash == current_hash:
                    change_type = "unchanged"
                elif similarity > 0.9:
                    change_type = "minor_change"
                elif similarity > 0.7:
                    change_type = "moderate_change"
                else:
                    change_type = "major_change"
            
            evolution.append({
                "page_id": page.id,
                "capture_date": page.capture_date.isoformat() if page.capture_date else None,
                "scraped_at": page.scraped_at.isoformat() if page.scraped_at else None,
                "title": page.extracted_title,
                "word_count": page.word_count,
                "character_count": page.character_count,
                "content_hash": current_hash,
                "change_type": change_type,
                "similarity_to_previous": similarity,
                "domain_name": domain.domain_name,
                "project_name": project.name
            })
            
            previous_content = current_content
            previous_hash = current_hash
        
        return evolution
    
    @staticmethod
    async def detect_content_patterns(
        db: AsyncSession,
        project_id: int,
        user_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Analyze content patterns and changes across a project
        """
        # Get all pages in the project
        query = (
            select(Page, Domain)
            .join(Domain, Page.domain_id == Domain.id)
            .join(Project, Domain.project_id == Project.id)
            .where(Project.id == project_id)
        )
        
        if user_id:
            query = query.where(Project.user_id == user_id)
        
        result = await db.execute(query)
        rows = result.all()
        
        if not rows:
            return {"patterns": [], "summary": {}}
        
        # Analyze patterns
        word_counts = []
        languages = {}
        content_types = {}
        domains = {}
        authors = {}
        
        for page, domain in rows:
            if page.word_count:
                word_counts.append(page.word_count)
            
            if page.language:
                languages[page.language] = languages.get(page.language, 0) + 1
            
            if page.content_type:
                content_types[page.content_type] = content_types.get(page.content_type, 0) + 1
            
            domains[domain.domain_name] = domains.get(domain.domain_name, 0) + 1
            
            if page.author:
                authors[page.author] = authors.get(page.author, 0) + 1
        
        # Calculate statistics
        word_count_stats = {}
        if word_counts:
            word_counts.sort()
            word_count_stats = {
                "min": min(word_counts),
                "max": max(word_counts),
                "mean": sum(word_counts) // len(word_counts),
                "median": word_counts[len(word_counts) // 2]
            }
        
        return {
            "total_pages": len(rows),
            "word_count_stats": word_count_stats,
            "top_languages": sorted(languages.items(), key=lambda x: x[1], reverse=True)[:10],
            "top_content_types": sorted(content_types.items(), key=lambda x: x[1], reverse=True)[:10],
            "domains": sorted(domains.items(), key=lambda x: x[1], reverse=True),
            "top_authors": sorted(authors.items(), key=lambda x: x[1], reverse=True)[:10],
            "analysis_date": datetime.utcnow().isoformat()
        }