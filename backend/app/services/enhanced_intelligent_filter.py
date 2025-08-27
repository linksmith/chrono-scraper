"""
Enhanced intelligent filtering service with individual reason tracking
"""
import logging
import re
from typing import List, Dict, Set, Tuple, Optional, Any
from datetime import datetime, timedelta
from dataclasses import dataclass
from enum import Enum

from sqlmodel import Session, select
from sqlalchemy import create_engine
from ..models.scraping import ScrapePage, ScrapePageStatus
from ..core.config import settings
from .wayback_machine import CDXRecord

logger = logging.getLogger(__name__)


class FilterReason(str, Enum):
    """Enumeration of filtering reasons for individual tracking"""
    # Content inclusion reasons
    HIGH_VALUE_RESEARCH = "high_value_research"
    HIGH_VALUE_DOCUMENT = "high_value_document"
    HIGH_VALUE_ACADEMIC = "high_value_academic"
    HIGH_VALUE_GOVERNMENT = "high_value_government"
    HIGH_VALUE_LARGE_CONTENT = "high_value_large_content"
    PASSED_ALL_FILTERS = "passed_all_filters"
    
    # Content exclusion reasons
    LIST_PAGE_BLOG = "list_page_blog"
    LIST_PAGE_CATEGORY = "list_page_category"
    LIST_PAGE_PAGINATION = "list_page_pagination"
    LIST_PAGE_ARCHIVE = "list_page_archive"
    LIST_PAGE_INDEX = "list_page_index"
    LIST_PAGE_SEARCH = "list_page_search"
    LIST_PAGE_FEED = "list_page_feed"
    LIST_PAGE_ADMIN = "list_page_admin"
    LIST_PAGE_HEURISTIC = "list_page_heuristic"
    
    ALREADY_PROCESSED_DIGEST = "already_processed_digest"
    ALREADY_PROCESSED_URL = "already_processed_url"
    
    ATTACHMENT_PDF_DISABLED = "attachment_pdf_disabled"
    ATTACHMENT_DOC_DISABLED = "attachment_doc_disabled"
    ATTACHMENT_OTHER_DISABLED = "attachment_other_disabled"
    
    SIZE_TOO_SMALL = "size_too_small"
    SIZE_TOO_LARGE = "size_too_large"
    
    FILE_EXTENSION_CSS = "file_extension_css"
    FILE_EXTENSION_JS = "file_extension_js"
    FILE_EXTENSION_IMAGE = "file_extension_image"
    FILE_EXTENSION_MEDIA = "file_extension_media"
    FILE_EXTENSION_ARCHIVE = "file_extension_archive"


@dataclass
class FilterDecision:
    """Container for detailed filtering decision"""
    status: ScrapePageStatus
    reason: FilterReason
    confidence: float  # 0.0 to 1.0
    matched_pattern: Optional[str] = None
    specific_reason: str = ""
    filter_details: Dict[str, Any] = None
    can_be_manually_processed: bool = True
    priority_score: int = 5
    related_page_id: Optional[int] = None
    
    def __post_init__(self):
        if self.filter_details is None:
            self.filter_details = {}


class EnhancedIntelligentContentFilter:
    """
    Enhanced filtering system that captures individual reasons for every filtering decision.
    
    Note: Static web assets (JS, CSS, images, fonts, etc.) are pre-filtered at the CDX 
    parsing level in wayback_machine.py to prevent them from ever creating database entries.
    This filter focuses on content-level decisions for legitimate web pages.
    """
    
    # Categorized list page patterns with specific identifiers
    LIST_PATTERNS = {
        'blog': [
            r'/blog/?$', r'/posts/?$', r'/news/?$', r'/articles/?$',
            r'/blog/page/\d+', r'/posts/page/\d+', r'/news/page/\d+',
            r'/blog/\d{4}/?$', r'/posts/\d{4}/?$',
        ],
        'category': [
            r'/category/', r'/tag/', r'/topic/', r'/subject/',
            r'/categories/?$', r'/tags/?$', r'/topics/?$',
        ],
        'pagination': [
            r'/page/\d+', r'/p/\d+', r'\?page=\d+', r'&page=\d+',
            r'/\d+/?$',  # URLs ending in just a number
            r'\?p=\d+', r'&p=\d+', r'/pages/',
        ],
        'archive': [
            r'/archive/', r'/archives/',
            r'/\d{4}/?$', r'/\d{4}/\d{2}/?$', r'/\d{4}/\d{2}/\d{2}/?$',
            r'/year/\d{4}', r'/month/\d{2}', r'/date/',
        ],
        'index': [
            r'/index\.html?$', r'/sitemap', r'/overview', r'/home/?$',
            r'/all-posts', r'/all-articles', r'/post-list', r'/article-list',
            r'/directory/', r'/listing/', r'/browse/',
        ],
        'search': [
            r'/search/', r'\?search=', r'\?filter=', r'\?sort=',
            r'\?category=', r'\?tag=', r'\?author=', r'\?q=',
        ],
        'feed': [
            r'/feed/?$', r'/rss/?$', r'/atom/?$', r'/xml/?$',
            r'/api/', r'\.xml$', r'\.json$', r'\.rss$',
        ],
        'admin': [
            r'/wp-admin/', r'/admin/', r'/dashboard/', r'/login',
            r'/wp-content/', r'/wp-includes/',
        ]
    }
    
    # High-value URL patterns with specific categories
    HIGH_VALUE_PATTERNS = {
        'research': [
            r'/research/', r'/study/', r'/analysis/', r'/report/',
            r'/whitepaper/', r'/publication/', r'/paper/',
        ],
        'document': [
            r'/document/', r'/documentation/', r'/manual/', r'/guide/',
            r'/resources/', r'/library/', r'/download/',
        ],
        'academic': [
            r'/journal/', r'/thesis/', r'/dissertation/', r'/proceedings/',
            r'/conference/', r'/symposium/', r'/workshop/',
        ],
        'government': [
            r'/policy/', r'/statement/', r'/announcement/', r'/press-release/',
            r'/regulation/', r'/law/', r'/bill/', r'/act/',
        ]
    }
    
    # File extensions that should never be shown
    NEVER_SHOW_EXTENSIONS = {
        'css': ['.css'],
        'js': ['.js', '.javascript'],
        'image': ['.jpg', '.jpeg', '.png', '.gif', '.svg', '.webp', '.ico'],
        'media': ['.mp3', '.mp4', '.avi', '.mov', '.wmv', '.flv', '.wav', '.ogg'],
        'archive': ['.zip', '.tar', '.gz', '.rar', '.7z', '.bz2']
    }
    
    # Attachment extensions (can be manually enabled)
    ATTACHMENT_EXTENSIONS = {
        'pdf': ['.pdf'],
        'doc': ['.doc', '.docx', '.odt', '.rtf'],
        'other': ['.xls', '.xlsx', '.ods', '.ppt', '.pptx', '.odp', '.txt']
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
            domain_id: Optional domain ID for scoping
            url_prefix: Optional URL prefix for scoping
            
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
                        ScrapePage.status == ScrapePageStatus.COMPLETED
                    )
                )
            elif url_prefix:
                stmt = (
                    select(ScrapePage.digest_hash)
                    .where(
                        ScrapePage.original_url.like(f"{url_prefix}%"),
                        ScrapePage.created_at >= cutoff_date,
                        ScrapePage.digest_hash.isnot(None),
                        ScrapePage.status == ScrapePageStatus.COMPLETED
                    )
                )
            else:
                stmt = (
                    select(ScrapePage.digest_hash)
                    .where(
                        ScrapePage.original_url.like(f"%{domain_name}%"),
                        ScrapePage.created_at >= cutoff_date,
                        ScrapePage.digest_hash.isnot(None),
                        ScrapePage.status == ScrapePageStatus.COMPLETED
                    )
                )
            
            results = session.exec(stmt).all()
            existing_digests = set(results)
            
            logger.info(f"Found {len(existing_digests)} existing digests for {domain_name}"
                        + (f" (scoped by domain_id={domain_id})" if domain_id is not None else "")
                        + (f" (scoped by prefix)" if (domain_id is None and url_prefix) else ""))
            return existing_digests

    def _check_never_show_extensions(self, url: str) -> Optional[FilterDecision]:
        """Check if URL has extensions that should never be shown"""
        url_lower = url.lower()
        path_part = url_lower.split('?')[0].split('#')[0]
        
        for category, extensions in self.NEVER_SHOW_EXTENSIONS.items():
            for ext in extensions:
                if path_part.endswith(ext):
                    return FilterDecision(
                        status=ScrapePageStatus.FILTERED_FILE_EXTENSION,
                        reason=getattr(FilterReason, f'FILE_EXTENSION_{category.upper()}'),
                        confidence=1.0,
                        matched_pattern=f"{ext}$",
                        specific_reason=f"File extension {ext} filtered - {category} files not processed",
                        filter_details={
                            "filter_type": "file_extension",
                            "extension": ext,
                            "extension_category": category,
                            "never_show": True
                        },
                        can_be_manually_processed=False  # These are never processed
                    )
        return None

    def _check_list_page_patterns(self, url: str) -> Optional[FilterDecision]:
        """Check URL against list page patterns with specific categorization"""
        url_lower = url.lower()
        
        for category, patterns in self.LIST_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, url_lower):
                    reason_enum = getattr(FilterReason, f'LIST_PAGE_{category.upper()}')
                    
                    # Create specific reason based on category and pattern
                    specific_reasons = {
                        'blog': f"Blog listing page detected - Pattern: {pattern}",
                        'category': f"Category/tag listing page detected - Pattern: {pattern}",
                        'pagination': f"Pagination page detected - Pattern: {pattern}",
                        'archive': f"Archive/date listing page detected - Pattern: {pattern}",
                        'index': f"Index/overview page detected - Pattern: {pattern}",
                        'search': f"Search/filter page detected - Pattern: {pattern}",
                        'feed': f"RSS/API feed detected - Pattern: {pattern}",
                        'admin': f"Admin/system page detected - Pattern: {pattern}"
                    }
                    
                    return FilterDecision(
                        status=ScrapePageStatus.FILTERED_LIST_PAGE,
                        reason=reason_enum,
                        confidence=0.9,  # High confidence for pattern matches
                        matched_pattern=pattern,
                        specific_reason=specific_reasons[category],
                        filter_details={
                            "filter_type": "list_page_detection",
                            "list_category": category,
                            "matched_pattern": pattern,
                            "detection_method": "regex_pattern",
                            "confidence_factors": [
                                f"URL matches {category} pattern: {pattern}",
                                "Pattern in curated list of navigation pages"
                            ]
                        },
                        can_be_manually_processed=True
                    )
        
        # Heuristic checks for list pages not caught by patterns
        return self._check_list_page_heuristics(url)

    def _check_list_page_heuristics(self, url: str) -> Optional[FilterDecision]:
        """Heuristic checks for list pages not caught by explicit patterns"""
        url_lower = url.lower()
        path_parts = url.split('/')
        
        heuristic_checks = []
        
        # Very short paths are often index pages
        if len(path_parts) <= 4 and not any(part for part in path_parts if len(part) > 8):
            heuristic_checks.append("Short path structure suggests index page")
        
        # URLs with many query parameters are often filters/searches
        if '?' in url and url.count('&') > 3:
            heuristic_checks.append("Multiple query parameters suggest filtering interface")
        
        # URLs with common dynamic parameters
        dynamic_params = ['id=', 'uid=', 'page=', 'offset=', 'limit=', 'sort=']
        query_part = url.split('?', 1)[1] if '?' in url else ''
        matched_params = [param for param in dynamic_params if param in query_part]
        
        if matched_params:
            heuristic_checks.append(f"Dynamic parameters detected: {', '.join(matched_params)}")
        
        if heuristic_checks:
            return FilterDecision(
                status=ScrapePageStatus.FILTERED_LIST_PAGE,
                reason=FilterReason.LIST_PAGE_HEURISTIC,
                confidence=0.7,  # Lower confidence for heuristics
                matched_pattern="heuristic_analysis",
                specific_reason=f"List page detected via heuristics: {'; '.join(heuristic_checks)}",
                filter_details={
                    "filter_type": "list_page_detection",
                    "list_category": "heuristic",
                    "detection_method": "heuristic_analysis",
                    "heuristic_factors": heuristic_checks,
                    "confidence_note": "Lower confidence - heuristic detection"
                },
                can_be_manually_processed=True
            )
        
        return None

    def _check_already_processed(self, record: CDXRecord, 
                                existing_digests: Set[str]) -> Optional[FilterDecision]:
        """Check if content has already been processed"""
        if hasattr(record, 'digest') and record.digest in existing_digests:
            return FilterDecision(
                status=ScrapePageStatus.FILTERED_ALREADY_PROCESSED,
                reason=FilterReason.ALREADY_PROCESSED_DIGEST,
                confidence=1.0,
                matched_pattern=f"digest:{record.digest[:8]}...",
                specific_reason=f"Content with digest {record.digest[:8]}... already processed",
                filter_details={
                    "filter_type": "duplicate_content",
                    "digest_hash": record.digest,
                    "detection_method": "digest_comparison",
                    "duplicate_type": "identical_content",
                    "processing_note": "Exact content already exists in database"
                },
                can_be_manually_processed=False  # No point processing identical content
            )
        return None

    def _check_attachment_filtering(self, url: str, 
                                  include_attachments: bool) -> Optional[FilterDecision]:
        """Check attachment filtering with specific file type identification"""
        if include_attachments:
            return None  # Attachments are enabled, don't filter
        
        url_lower = url.lower()
        path_part = url_lower.split('?')[0].split('#')[0]
        
        for category, extensions in self.ATTACHMENT_EXTENSIONS.items():
            for ext in extensions:
                if path_part.endswith(ext):
                    reason_enum = getattr(FilterReason, f'ATTACHMENT_{category.upper()}_DISABLED')
                    
                    return FilterDecision(
                        status=ScrapePageStatus.FILTERED_ATTACHMENT_DISABLED,
                        reason=reason_enum,
                        confidence=1.0,
                        matched_pattern=f"{ext}$",
                        specific_reason=f"{ext.upper()} attachment excluded - Project attachments disabled",
                        filter_details={
                            "filter_type": "attachment_filtering",
                            "file_type": ext,
                            "file_category": category,
                            "project_setting": "enable_attachment_download=False",
                            "manual_override_available": True
                        },
                        can_be_manually_processed=True  # Can be enabled by user
                    )
        return None

    def _check_size_filtering(self, record: CDXRecord, 
                            min_size: int = 1000, 
                            max_size: int = 10 * 1024 * 1024) -> Optional[FilterDecision]:
        """Check content size filtering"""
        if record.content_length_bytes is None:
            return None
        
        if record.content_length_bytes < min_size:
            return FilterDecision(
                status=ScrapePageStatus.FILTERED_SIZE_TOO_SMALL,
                reason=FilterReason.SIZE_TOO_SMALL,
                confidence=1.0,
                matched_pattern=f"<{min_size}bytes",
                specific_reason=f"Content size {record.content_length_bytes} bytes below minimum threshold ({min_size} bytes)",
                filter_details={
                    "filter_type": "size_filtering",
                    "content_size": record.content_length_bytes,
                    "minimum_threshold": min_size,
                    "size_category": "too_small",
                    "filter_rationale": "Very small content often lacks substance"
                },
                can_be_manually_processed=True
            )
        
        if record.content_length_bytes > max_size:
            return FilterDecision(
                status=ScrapePageStatus.FILTERED_SIZE_TOO_LARGE,
                reason=FilterReason.SIZE_TOO_LARGE,
                confidence=1.0,
                matched_pattern=f">{max_size}bytes",
                specific_reason=f"Content size {record.content_length_bytes} bytes exceeds maximum threshold ({max_size} bytes)",
                filter_details={
                    "filter_type": "size_filtering",
                    "content_size": record.content_length_bytes,
                    "maximum_threshold": max_size,
                    "size_category": "too_large",
                    "filter_rationale": "Extremely large content may be multimedia or corrupted"
                },
                can_be_manually_processed=True
            )
        
        return None

    def _check_high_value_content(self, url: str, content_length: int, 
                                include_attachments: bool) -> Optional[FilterDecision]:
        """Check for high-value content with specific categorization"""
        url_lower = url.lower()
        
        # Check high-value patterns
        for category, patterns in self.HIGH_VALUE_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, url_lower):
                    reason_enum = getattr(FilterReason, f'HIGH_VALUE_{category.upper()}')
                    
                    priority_scores = {
                        'research': 9,
                        'document': 8, 
                        'academic': 9,
                        'government': 8
                    }
                    
                    return FilterDecision(
                        status=ScrapePageStatus.PENDING,
                        reason=reason_enum,
                        confidence=0.9,
                        matched_pattern=pattern,
                        specific_reason=f"High-value {category} content detected - Pattern: {pattern}",
                        filter_details={
                            "filter_type": "high_value_detection",
                            "value_category": category,
                            "matched_pattern": pattern,
                            "priority_indicators": [
                                f"URL contains {category} pattern: {pattern}",
                                f"Content classified as high-value {category}"
                            ]
                        },
                        priority_score=priority_scores[category]
                    )
        
        # Large content is often valuable
        if content_length > 5000:  # 5KB+
            return FilterDecision(
                status=ScrapePageStatus.PENDING,
                reason=FilterReason.HIGH_VALUE_LARGE_CONTENT,
                confidence=0.8,
                matched_pattern=f">{content_length}bytes",
                specific_reason=f"Large content detected ({content_length} bytes) - Likely substantial article or document",
                filter_details={
                    "filter_type": "high_value_detection",
                    "value_category": "large_content",
                    "content_size": content_length,
                    "priority_indicators": [
                        f"Content size {content_length} bytes indicates substantial content",
                        "Large content typically contains more valuable information"
                    ]
                },
                priority_score=7
            )
        
        # Academic/government domains
        domain_patterns = ['.edu/', '.gov/', '.org/', '.ac.']
        if any(pattern in url_lower for pattern in domain_patterns):
            matched_pattern = next(pattern for pattern in domain_patterns if pattern in url_lower)
            return FilterDecision(
                status=ScrapePageStatus.PENDING,
                reason=FilterReason.HIGH_VALUE_ACADEMIC if '.edu' in matched_pattern or '.ac.' in matched_pattern else FilterReason.HIGH_VALUE_GOVERNMENT,
                confidence=0.85,
                matched_pattern=matched_pattern,
                specific_reason=f"Academic/government domain detected - {matched_pattern} domain",
                filter_details={
                    "filter_type": "high_value_detection",
                    "value_category": "institutional_domain",
                    "domain_type": matched_pattern,
                    "priority_indicators": [
                        f"Domain contains {matched_pattern} - institutional content",
                        "Educational/government content typically high quality"
                    ]
                },
                priority_score=8
            )
        
        return None

    def make_filtering_decision(self, record: CDXRecord, 
                              existing_digests: Set[str],
                              include_attachments: bool = True) -> FilterDecision:
        """
        Make a comprehensive filtering decision with individual reason tracking
        
        Args:
            record: CDX record to evaluate
            existing_digests: Set of already-processed digest hashes
            include_attachments: Whether to include PDF and other attachments
            
        Returns:
            FilterDecision with detailed reasoning
        """
        
        # 1. Check for file extensions that should never be shown
        decision = self._check_never_show_extensions(record.original_url)
        if decision:
            return decision
        
        # 2. Check for list page patterns
        decision = self._check_list_page_patterns(record.original_url)
        if decision:
            return decision
        
        # 3. Check if already processed
        decision = self._check_already_processed(record, existing_digests)
        if decision:
            return decision
        
        # 4. Check attachment filtering
        decision = self._check_attachment_filtering(record.original_url, include_attachments)
        if decision:
            return decision
        
        # 5. Check size filtering
        decision = self._check_size_filtering(record)
        if decision:
            return decision
        
        # 6. Check for high-value content (these get processed with high priority)
        decision = self._check_high_value_content(
            record.original_url, 
            record.content_length_bytes or 0, 
            include_attachments
        )
        if decision:
            return decision
        
        # 7. Default: passed all filters
        return FilterDecision(
            status=ScrapePageStatus.PENDING,
            reason=FilterReason.PASSED_ALL_FILTERS,
            confidence=0.6,
            specific_reason="Passed all filtering rules - Regular content for processing",
            filter_details={
                "filter_type": "inclusion",
                "filter_result": "passed_all_filters",
                "content_classification": "regular",
                "processing_priority": "normal"
            },
            priority_score=5
        )

    def filter_records_with_individual_reasons(self, 
                                             records: List[CDXRecord],
                                             existing_digests: Set[str],
                                             include_attachments: bool = True) -> Tuple[List[Tuple[CDXRecord, FilterDecision]], Dict[str, int]]:
        """
        Filter CDX records with individual reason tracking for each record
        
        Args:
            records: List of CDX records to filter
            existing_digests: Set of already-processed digest hashes
            include_attachments: Whether to include PDF attachments in filtering
            
        Returns:
            Tuple of (records_with_decisions, filter_statistics)
        """
        results = []
        stats = {
            'total_input': len(records),
            'never_show_filtered': 0,
            'list_pages_filtered': 0,
            'already_processed_filtered': 0,
            'attachments_filtered': 0,
            'size_filtered': 0,
            'high_value_prioritized': 0,
            'regular_content': 0,
            'total_excluded': 0,
            'total_included': 0
        }
        
        for record in records:
            decision = self.make_filtering_decision(record, existing_digests, include_attachments)
            results.append((record, decision))
            
            # Update statistics
            if decision.status == ScrapePageStatus.FILTERED_FILE_EXTENSION:
                stats['never_show_filtered'] += 1
                stats['total_excluded'] += 1
            elif decision.status == ScrapePageStatus.FILTERED_LIST_PAGE:
                stats['list_pages_filtered'] += 1
                stats['total_excluded'] += 1
            elif decision.status == ScrapePageStatus.FILTERED_ALREADY_PROCESSED:
                stats['already_processed_filtered'] += 1
                stats['total_excluded'] += 1
            elif decision.status == ScrapePageStatus.FILTERED_ATTACHMENT_DISABLED:
                stats['attachments_filtered'] += 1
                stats['total_excluded'] += 1
            elif decision.status in [ScrapePageStatus.FILTERED_SIZE_TOO_SMALL, ScrapePageStatus.FILTERED_SIZE_TOO_LARGE]:
                stats['size_filtered'] += 1
                stats['total_excluded'] += 1
            elif decision.reason in [FilterReason.HIGH_VALUE_RESEARCH, FilterReason.HIGH_VALUE_DOCUMENT, 
                                   FilterReason.HIGH_VALUE_ACADEMIC, FilterReason.HIGH_VALUE_GOVERNMENT,
                                   FilterReason.HIGH_VALUE_LARGE_CONTENT]:
                stats['high_value_prioritized'] += 1
                stats['total_included'] += 1
            else:
                stats['regular_content'] += 1
                stats['total_included'] += 1
        
        logger.info(
            f"Enhanced filtering complete: {stats['total_input']} input -> "
            f"{stats['total_included']} included ({stats['high_value_prioritized']} high-value), "
            f"{stats['total_excluded']} excluded (detailed breakdown available)"
        )
        
        return results, stats


# Global instance
_enhanced_filter = None

def get_enhanced_intelligent_filter() -> EnhancedIntelligentContentFilter:
    """Get global enhanced intelligent filter instance"""
    global _enhanced_filter
    if _enhanced_filter is None:
        _enhanced_filter = EnhancedIntelligentContentFilter()
    return _enhanced_filter