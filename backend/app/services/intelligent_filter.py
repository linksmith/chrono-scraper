"""
Intelligent filtering service for CDX records with digest-based change detection
"""
import logging
import re
from typing import List, Dict, Set, Tuple, Optional
from datetime import datetime, timedelta

from sqlmodel import Session, select
from sqlalchemy import create_engine
from ..models.scraping import ScrapePage
from ..core.config import settings
from .wayback_machine import CDXRecord

logger = logging.getLogger(__name__)


class IntelligentContentFilter:
    """
    Advanced filtering system that only scrapes interesting and changed content
    """
    
    # Enhanced list page patterns from Django project
    ENHANCED_LIST_PATTERNS = [
        # Blog and news lists
        r'/blog/?$', r'/posts/?$', r'/news/?$', r'/articles/?$',
        r'/blog/page/\d+', r'/posts/page/\d+', r'/news/page/\d+',
        r'/blog/\d{4}/?$', r'/posts/\d{4}/?$',
        
        # Category and archive pages
        r'/category/', r'/tag/', r'/archive/', r'/archives/',
        r'/\d{4}/?$', r'/\d{4}/\d{2}/?$', r'/\d{4}/\d{2}/\d{2}/?$',  # Date archives
        r'/year/\d{4}', r'/month/\d{2}', r'/date/',
        
        # Index and overview pages
        r'/index\.html?$', r'/sitemap', r'/overview', r'/home/?$',
        r'/all-posts', r'/all-articles', r'/post-list', r'/article-list',
        
        # Pagination patterns
        r'/page/\d+', r'/p/\d+', r'\?page=\d+', r'&page=\d+',
        r'/\d+/?$',  # URLs ending in just a number
        r'\?p=\d+', r'&p=\d+',
        
        # Search and filter pages
        r'/search/', r'\?search=', r'\?filter=', r'\?sort=',
        r'\?category=', r'\?tag=', r'\?author=', r'\?q=',
        
        # Feed and API endpoints
        r'/feed/?$', r'/rss/?$', r'/atom/?$', r'/xml/?$',
        r'/api/', r'\.xml$', r'\.json$', r'\.rss$',
        
        # Common CMS and admin areas
        r'/wp-admin/', r'/admin/', r'/dashboard/', r'/login',
        r'/categories/?$', r'/tags/?$', r'/authors/?$',
        r'/wp-content/', r'/wp-includes/',
        
        # Social media and sharing
        r'/share', r'/facebook', r'/twitter', r'/linkedin',
        r'/social/', r'/widget/', r'/embed',
        
        # Directory listing patterns
        r'/directory/', r'/listing/', r'/browse/',
        r'/list\.', r'listing\.', r'directory\.',
        
        # Comment and discussion pages
        r'/comments/', r'/discussion/', r'/forum/',
        r'/reply/', r'/thread/', r'\.php$',
        
        # Calendar and event pages
        r'/calendar/', r'/events/', r'/schedule/',
        r'/\d{4}/\d{2}/?$', r'/event\.php',
    ]
    
    # High-value URL patterns that should be prioritized
    HIGH_VALUE_PATTERNS = [
        r'/research/', r'/report/', r'/paper/', r'/publication/',
        r'/document/', r'/study/', r'/analysis/', r'/whitepaper/',
        r'/press-release/', r'/news/\d{4}/', r'/article/',
        r'/content/', r'/resources/', r'/library/',
        r'/policy/', r'/statement/', r'/announcement/',
        r'/guide/', r'/manual/', r'/documentation/',
        r'/download/', r'/pdf/', r'\.pdf$',
    ]
    
    # File extensions to skip (images, styles, scripts)
    SKIP_EXTENSIONS = [
        '.css', '.js', '.jpg', '.jpeg', '.png', '.gif', '.svg',
        '.ico', '.woff', '.woff2', '.ttf', '.eot',
        '.mp3', '.mp4', '.avi', '.mov', '.wmv', '.flv',
        '.zip', '.tar', '.gz', '.rar', '.exe', '.dmg'
    ]
    
    # Attachment extensions (more comprehensive for double-checking)
    ATTACHMENT_EXTENSIONS = {
        '.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx',
        '.odt', '.ods', '.odp', '.rtf', '.txt',
        '.zip', '.rar', '.7z', '.tar', '.gz', '.bz2',
        '.mp3', '.mp4', '.avi', '.mov', '.wmv', '.flv', '.wav', '.ogg',
        '.exe', '.dmg', '.deb', '.rpm', '.msi', '.iso'
    }
    
    def __init__(self):
        # Create database connection if available
        self.engine = None
        try:
            if hasattr(settings, 'DATABASE_URL'):
                self.engine = create_engine(settings.DATABASE_URL)
        except:
            # Will work without database in test mode
            pass
    
    async def get_existing_digests(self, domain_name: str, 
                                 days_back: int = 30,
                                 domain_id: Optional[int] = None,
                                 url_prefix: Optional[str] = None) -> Set[str]:
        """
        Get digest hashes for pages already scraped from this domain
        
        Args:
            domain_name: Domain name to check
            days_back: How many days back to look for existing digests
            
        Returns:
            Set of digest hashes already processed
        """
        cutoff_date = datetime.utcnow() - timedelta(days=days_back)
        
        if not self.engine:
            logger.warning("No database connection available, returning empty digest set")
            return set()
        
        with Session(bind=self.engine) as session:
            # Query existing scrape pages scoped to this target when possible
            if domain_id is not None:
                stmt = (
                    select(ScrapePage.digest_hash)
                    .where(
                        ScrapePage.domain_id == domain_id,
                        ScrapePage.created_at >= cutoff_date,
                        ScrapePage.digest_hash.isnot(None),
                        ScrapePage.status == 'completed'
                    )
                )
            elif url_prefix:
                stmt = (
                    select(ScrapePage.digest_hash)
                    .where(
                        ScrapePage.original_url.like(f"{url_prefix}%"),
                        ScrapePage.created_at >= cutoff_date,
                        ScrapePage.digest_hash.isnot(None),
                        ScrapePage.status == 'completed'
                    )
                )
            else:
                stmt = (
                    select(ScrapePage.digest_hash)
                    .where(
                        ScrapePage.original_url.like(f"%{domain_name}%"),
                        ScrapePage.created_at >= cutoff_date,
                        ScrapePage.digest_hash.isnot(None),
                        ScrapePage.status == 'completed'
                    )
                )
            
            results = session.exec(stmt).all()
            existing_digests = set(results)
            
            logger.info(f"Found {len(existing_digests)} existing digests for {domain_name}"
                        + (f" (scoped by domain_id={domain_id})" if domain_id is not None else "")
                        + (" (scoped by prefix)" if (domain_id is None and url_prefix) else ""))
            return existing_digests
    
    def is_list_page(self, url: str) -> bool:
        """
        Enhanced list page detection with comprehensive patterns
        
        Args:
            url: URL to check
            
        Returns:
            True if URL appears to be a list/index page
        """
        url_lower = url.lower()
        
        # Check against enhanced patterns
        for pattern in self.ENHANCED_LIST_PATTERNS:
            if re.search(pattern, url_lower):
                logger.debug(f"List page pattern '{pattern}' matched: {url}")
                return True
        
        # Check for unwanted file extensions
        for ext in self.SKIP_EXTENSIONS:
            if url_lower.endswith(ext):
                logger.debug(f"Skipping file extension {ext}: {url}")
                return True
        
        # Additional heuristics
        # Very short paths are often index pages
        path_parts = url.split('/')
        if len(path_parts) <= 4 and not any(part for part in path_parts if len(part) > 8):
            logger.debug(f"Short path heuristic matched: {url}")
            return True
        
        # URLs with many query parameters are often filters/searches
        if '?' in url and url.count('&') > 3:
            logger.debug(f"Many query parameters heuristic matched: {url}")
            return True
        
        # URLs with common dynamic parameters
        dynamic_params = ['id=', 'uid=', 'page=', 'offset=', 'limit=', 'sort=']
        query_part = url.split('?', 1)[1] if '?' in url else ''
        if any(param in query_part for param in dynamic_params):
            logger.debug(f"Dynamic parameter detected: {url}")
            return True
        
        return False
    
    def _is_attachment_url(self, url: str) -> bool:
        """
        Check if URL appears to be an attachment based on file extension
        
        Args:
            url: URL to check
            
        Returns:
            True if URL appears to be an attachment file
        """
        url_lower = url.lower()
        # Extract the path part (before query parameters and fragments)
        path_part = url_lower.split('?')[0].split('#')[0]
        
        # Check if it ends with any attachment extension
        for ext in self.ATTACHMENT_EXTENSIONS:
            if path_part.endswith(ext):
                return True
        return False
    
    def is_high_value_content(self, url: str, length: int = 0, include_attachments: bool = True) -> bool:
        """
        Determine if content is likely to be high-value
        
        Args:
            url: URL to evaluate
            length: Content length in bytes
            include_attachments: Whether to consider PDFs as high-value
            
        Returns:
            True if content appears to be high-value
        """
        url_lower = url.lower()
        
        # Check for high-value patterns
        for pattern in self.HIGH_VALUE_PATTERNS:
            if re.search(pattern, url_lower):
                logger.debug(f"High-value pattern '{pattern}' matched: {url}")
                return True
        
        # Large content is often valuable (articles, documents)
        if length > 5000:  # 5KB+
            logger.debug(f"Large content detected ({length} bytes): {url}")
            return True
        
        # PDF files are often documents (only if attachments are enabled)
        if include_attachments and url_lower.endswith('.pdf'):
            logger.debug(f"PDF document detected: {url}")
            return True
        
        # Academic/government domains
        domain_patterns = ['.edu/', '.gov/', '.org/', '.ac.']
        if any(pattern in url_lower for pattern in domain_patterns):
            logger.debug(f"Academic/government domain detected: {url}")
            return True
        
        return False
    
    def filter_records_intelligent(self, 
                                 records: List[CDXRecord],
                                 existing_digests: Set[str],
                                 prioritize_changes: bool = True,
                                 include_attachments: bool = True) -> Tuple[List[CDXRecord], Dict[str, int]]:
        """
        Apply intelligent filtering to CDX records
        
        Args:
            records: List of CDX records to filter
            existing_digests: Set of already-processed digest hashes
            prioritize_changes: Whether to prioritize content that has changed
            include_attachments: Whether to include PDF attachments in filtering
            
        Returns:
            Tuple of (filtered_records, filter_stats)
        """
        filter_stats = {
            'total_input': len(records),
            'list_pages_filtered': 0,
            'already_processed': 0,
            'file_extensions_filtered': 0,
            'high_value_prioritized': 0,
            'final_output': 0
        }
        
        filtered_records = []
        high_value_records = []
        
        for record in records:
            len(filtered_records) + len(high_value_records)
            
            # Skip list pages and unwanted content
            if self.is_list_page(record.original_url):
                filter_stats['list_pages_filtered'] += 1
                continue
            
            # Skip if we've already processed this exact content (same digest)
            if prioritize_changes and record.digest in existing_digests:
                filter_stats['already_processed'] += 1
                logger.debug(f"Skipping already processed content: {record.original_url}")
                continue
                
            # Skip attachment URLs if attachments are disabled
            if not include_attachments and self._is_attachment_url(record.original_url):
                filter_stats['list_pages_filtered'] += 1  # Using existing counter for simplicity
                logger.debug(f"Skipping attachment URL (attachments disabled): {record.original_url}")
                continue
            
            # Categorize as high-value or regular
            if self.is_high_value_content(record.original_url, record.content_length_bytes, include_attachments):
                high_value_records.append(record)
                filter_stats['high_value_prioritized'] += 1
            else:
                filtered_records.append(record)
        
        # Combine high-value first, then regular records
        final_records = high_value_records + filtered_records
        filter_stats['final_output'] = len(final_records)
        
        # Log filtering results
        logger.info(
            f"Intelligent filtering complete: "
            f"{filter_stats['total_input']} input -> {filter_stats['final_output']} output "
            f"(list: -{filter_stats['list_pages_filtered']}, "
            f"processed: -{filter_stats['already_processed']}, "
            f"high-value: +{filter_stats['high_value_prioritized']})"
        )
        
        return final_records, filter_stats
    
    def get_scraping_priority(self, record: CDXRecord, include_attachments: bool = True) -> int:
        """
        Calculate scraping priority for a record (higher = more important)
        
        Args:
            record: CDX record to evaluate
            include_attachments: Whether to give PDFs priority boost
            
        Returns:
            Priority score (1-10)
        """
        priority = 5  # Base priority
        
        # High-value content gets priority boost
        if self.is_high_value_content(record.original_url, record.content_length_bytes, include_attachments):
            priority += 3
        
        # Recent content gets priority boost
        try:
            capture_date = record.capture_date
            days_old = (datetime.utcnow() - capture_date).days
            if days_old < 30:
                priority += 2
            elif days_old < 90:
                priority += 1
        except:
            pass
        
        # Large content is often more valuable
        if record.content_length_bytes > 10000:  # 10KB+
            priority += 1
        elif record.content_length_bytes > 50000:  # 50KB+
            priority += 2
        
        # PDF documents get priority (only if attachments are enabled)
        if include_attachments and record.mime_type == 'application/pdf':
            priority += 2
        
        return min(priority, 10)


# Global instance
_intelligent_filter = None

def get_intelligent_filter() -> IntelligentContentFilter:
    """Get global intelligent filter instance"""
    global _intelligent_filter
    if _intelligent_filter is None:
        _intelligent_filter = IntelligentContentFilter()
    return _intelligent_filter