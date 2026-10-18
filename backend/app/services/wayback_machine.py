"""
Wayback Machine CDX API client with robust retry logic and filtering
"""
import hashlib
import json
import re
import logging
import zlib
from datetime import datetime, timedelta
from typing import Callable, List, Dict, Tuple, Optional, Set, Union
from dataclasses import dataclass

import httpx
from tenacity import (
    retry,
    stop_after_attempt,
    wait_random_exponential,
    retry_if_exception,
    before_sleep_log
)

from ..core.config import settings
from ..models.project import ArchiveSource
from . import egress_rotation as egress
from .archive_fetch_errors import (
    ArchiveConnectionError,
    ArchiveHTTPError,
    ArchiveRateLimited,
)
from .archive_rate_limiter import HostClass, get_archive_rate_limiter, parse_retry_after

logger = logging.getLogger(__name__)


class WaybackMachineException(Exception):
    """Base exception for Wayback Machine API errors"""
    pass


class CDXAPIException(WaybackMachineException):
    """CDX API specific exceptions"""
    pass


class CDXRateLimited(CDXAPIException, ArchiveRateLimited):
    """429/503 from the CDX API, or every exit is parked (``retry_after`` seconds)."""


class CDXConnectionError(CDXAPIException, ArchiveConnectionError):
    """Connection/timeout failure talking to the CDX API."""


class CDXHTTPError(CDXAPIException, ArchiveHTTPError):
    """Other HTTP failure from the CDX API (4xx is final; ``retryable`` is set for 5xx)."""


class PageFilteredException(WaybackMachineException):
    """Exception for pages filtered out by content rules"""
    pass


@dataclass
class CDXRecord:
    """
    CDX record data structure supporting multiple archive sources.
    
    Enhanced to support both Wayback Machine and Common Crawl archives while
    maintaining full backward compatibility with existing code.
    
    Features:
    - Multi-source support (Wayback Machine, Common Crawl)
    - Factory methods for different archive formats
    - Archive-agnostic URL generation
    - WARC file support for Common Crawl
    - Robust timestamp parsing (multiple formats)
    - Graceful error handling and fallbacks
    
    Backward Compatibility:
    - Existing direct construction continues to work
    - Legacy properties (wayback_url, content_url) maintained
    - Defaults to WAYBACK_MACHINE source when not specified
    
    Usage Examples:
        # Wayback Machine (existing usage)
        record = CDXRecord.from_wayback_response(cdx_row)
        print(record.wayback_url)  # Works as before
        
        # Common Crawl (new)
        record = CDXRecord.from_common_crawl_response(cc_data)
        print(record.archive_url)  # Works with any source
        
        # Archive-agnostic code
        if record.is_wayback_machine:
            url = record.wayback_url
        elif record.is_common_crawl and record.warc_filename:
            url = record.archive_url
    """
    timestamp: str
    original_url: str
    mime_type: str
    status_code: str
    digest: str
    length: str
    source: ArchiveSource = ArchiveSource.WAYBACK_MACHINE  # Default for backward compatibility
    warc_filename: Optional[str] = None  # For Common Crawl WARC file reference
    warc_offset: Optional[int] = None  # For Common Crawl WARC offset
    warc_length: Optional[int] = None  # For Common Crawl WARC record length
    
    @classmethod
    def from_wayback_response(cls, cdx_line: Union[str, List]) -> 'CDXRecord':
        """
        Create CDXRecord from Wayback Machine CDX API response.
        
        Args:
            cdx_line: Either tab-separated string or list of values from CDX API
            
        Returns:
            CDXRecord with WAYBACK_MACHINE source
        """
        if isinstance(cdx_line, str):
            # Parse tab-separated line
            fields = cdx_line.strip().split('\t')
        else:
            # Already a list (from JSON response)
            fields = cdx_line
            
        if len(fields) < 6:
            raise ValueError(f"Invalid CDX line: expected at least 6 fields, got {len(fields)}")
            
        return cls(
            timestamp=fields[0],
            original_url=fields[1],
            mime_type=fields[2],
            status_code=fields[3],
            digest=fields[4],
            length=fields[5],
            source=ArchiveSource.WAYBACK_MACHINE
        )
    
    @classmethod
    def from_common_crawl_response(cls, cdx_obj: Union[Dict, object]) -> 'CDXRecord':
        """
        Create CDXRecord from Common Crawl CDX response.
        
        Args:
            cdx_obj: Dictionary from Common Crawl API or cdx_toolkit object
            
        Returns:
            CDXRecord with COMMON_CRAWL source
        """
        if hasattr(cdx_obj, '__dict__'):
            # cdx_toolkit object - convert to dict
            data = {
                'timestamp': cdx_obj.timestamp,
                'url': cdx_obj.url,
                'mimetype': getattr(cdx_obj, 'mimetype', ''),
                'statuscode': getattr(cdx_obj, 'statuscode', ''),
                'digest': getattr(cdx_obj, 'digest', ''),
                'length': getattr(cdx_obj, 'length', ''),
                'filename': getattr(cdx_obj, 'filename', None),
                'offset': getattr(cdx_obj, 'offset', None),
                'warc_length': getattr(cdx_obj, 'warc_length', None)
            }
        else:
            # Dictionary format
            data = cdx_obj
            
        # Normalize field names (Common Crawl uses different naming)
        return cls(
            timestamp=str(data.get('timestamp', '')),
            original_url=data.get('url', data.get('original_url', '')),
            mime_type=data.get('mimetype', data.get('mime_type', '')),
            status_code=str(data.get('statuscode', data.get('status_code', ''))),
            digest=data.get('digest', ''),
            length=str(data.get('length', '')),
            source=ArchiveSource.COMMON_CRAWL,
            warc_filename=data.get('filename'),
            warc_offset=data.get('offset'),
            warc_length=data.get('warc_length')
        )
    
    @property
    def wayback_url(self) -> str:
        """Generate Wayback Machine URL (legacy property for backward compatibility)"""
        if self.source == ArchiveSource.WAYBACK_MACHINE:
            return f"https://web.archive.org/web/{self.timestamp}/{self.original_url}"
        else:
            # For non-Wayback sources, return the original URL with timestamp info
            logger.warning(f"wayback_url property called for {self.source.value} record")
            return f"{self.original_url} (archived {self.timestamp})"
    
    @property
    def content_url(self) -> str:
        """Generate raw content URL (legacy property for backward compatibility)"""
        if self.source == ArchiveSource.WAYBACK_MACHINE:
            return f"https://web.archive.org/web/{self.timestamp}id_/{self.original_url}"
        elif self.source == ArchiveSource.COMMON_CRAWL and self.warc_filename:
            # Generate Common Crawl WARC URL when possible
            return self._generate_common_crawl_warc_url()
        else:
            # Fallback - return original URL
            logger.warning(f"content_url property called for {self.source.value} record without WARC info")
            return self.original_url
    
    @property
    def archive_url(self) -> str:
        """Generate appropriate archive URL based on source"""
        if self.source == ArchiveSource.WAYBACK_MACHINE:
            return f"https://web.archive.org/web/{self.timestamp}/{self.original_url}"
        elif self.source == ArchiveSource.COMMON_CRAWL and self.warc_filename:
            return self._generate_common_crawl_warc_url()
        else:
            # Fallback to original URL with source info
            return f"{self.original_url} (from {self.source.value})"
    
    @property
    def is_wayback_machine(self) -> bool:
        """Check if this record is from Wayback Machine"""
        return self.source == ArchiveSource.WAYBACK_MACHINE
    
    @property
    def is_common_crawl(self) -> bool:
        """Check if this record is from Common Crawl"""
        return self.source == ArchiveSource.COMMON_CRAWL
    
    def _generate_common_crawl_warc_url(self) -> str:
        """Generate Common Crawl WARC file access URL"""
        if not self.warc_filename:
            logger.warning("Cannot generate WARC URL without filename")
            return self.original_url
            
        # Common Crawl WARC files are stored on S3
        # Format: https://data.commoncrawl.org/{warc_filename}
        base_url = "https://data.commoncrawl.org"
        
        # Handle different filename formats
        if self.warc_filename.startswith('crawl-data/'):
            # Full path already provided
            warc_url = f"{base_url}/{self.warc_filename}"
        else:
            # Assume it's just the filename
            warc_url = f"{base_url}/crawl-data/{self.warc_filename}"
            
        # Add offset and length parameters if available
        if self.warc_offset is not None and self.warc_length is not None:
            warc_url += f"?offset={self.warc_offset}&length={self.warc_length}"
            
        return warc_url
    
    @property
    def content_length_bytes(self) -> int:
        """Get content length as integer"""
        try:
            return int(self.length) if self.length and self.length.isdigit() else 0
        except (ValueError, AttributeError):
            return 0
    
    @property
    def capture_date(self) -> datetime:
        """Parse timestamp to datetime (handles both Wayback and Common Crawl formats)"""
        try:
            # Standard format: YYYYMMDDHHMMSS
            if len(self.timestamp) == 14:
                return datetime.strptime(self.timestamp, "%Y%m%d%H%M%S")
            # ISO format (some Common Crawl entries)
            elif 'T' in self.timestamp:
                # Try ISO format: YYYY-MM-DDTHH:MM:SSZ
                return datetime.fromisoformat(self.timestamp.replace('Z', '+00:00'))
            else:
                # Fallback for shorter timestamps (pad with zeros)
                timestamp_padded = self.timestamp.ljust(14, '0')
                return datetime.strptime(timestamp_padded, "%Y%m%d%H%M%S")
        except (ValueError, AttributeError) as e:
            logger.warning(f"Could not parse timestamp '{self.timestamp}': {e}")
            # Return epoch as fallback
            return datetime.fromtimestamp(0)


class ListPageFilter:
    """Filter for detecting and removing list/overview pages"""
    
    # Common list page URL patterns
    LIST_PAGE_PATTERNS = [
        # Blog and news lists
        r'/blog/?$', r'/posts/?$', r'/news/?$', r'/articles/?$',
        r'/blog/page/\d+', r'/posts/page/\d+', r'/news/page/\d+',
        
        # Category and archive pages
        r'/category/', r'/tag/', r'/archive/', r'/archives/',
        r'/\d{4}/?$', r'/\d{4}/\d{2}/?$', r'/\d{4}/\d{2}/\d{2}/?$',  # Date archives
        
        # Index and overview pages
        r'/index\.html?$', r'/sitemap', r'/overview',
        r'/all-posts', r'/all-articles', r'/post-list',
        
        # Pagination
        r'/page/\d+', r'/p/\d+', r'\?page=\d+', r'&page=\d+',
        r'/\d+/?$',  # URLs ending in just a number
        
        # Search and filter pages
        r'/search/', r'\?search=', r'\?filter=', r'\?sort=',
        r'\?category=', r'\?tag=', r'\?author=',
        
        # Feed and API endpoints
        r'/feed/?$', r'/rss/?$', r'/api/', r'\.xml$', r'\.json$',
        
        # Common CMS list pages
        r'/wp-admin/', r'/admin/', r'/dashboard/',
        r'/categories/?$', r'/tags/?$', r'/authors/?$',
    ]
    
    @classmethod
    def is_list_page(cls, url: str) -> bool:
        """
        Detect if URL is likely a list/overview page that changes frequently.
        
        Args:
            url: The URL to analyze
            
        Returns:
            True if URL appears to be a list page that should be filtered out
        """
        url_lower = url.lower()
        
        # Check against patterns
        for pattern in cls.LIST_PAGE_PATTERNS:
            if re.search(pattern, url_lower):
                logger.debug(f"List page pattern matched: {pattern} for {url}")
                return True
        
        # Additional heuristics
        # Very short paths are often index pages
        path_parts = url.split('/')
        if len(path_parts) <= 4 and not any(part for part in path_parts if len(part) > 10):
            logger.debug(f"Short path heuristic matched for {url}")
            return True
        
        # URLs with many query parameters are often filters/searches
        if '?' in url and url.count('&') > 2:
            logger.debug(f"Many query parameters heuristic matched for {url}")
            return True
        
        return False
    
    @classmethod
    def filter_records(cls, records: List[CDXRecord]) -> Tuple[List[CDXRecord], int]:
        """
        Filter out list pages from CDX records.
        
        Args:
            records: List of CDX records
            
        Returns:
            Tuple of (filtered_records, filtered_count)
        """
        filtered_records = []
        filtered_count = 0
        
        for record in records:
            if cls.is_list_page(record.original_url):
                filtered_count += 1
                logger.debug(f"Filtered list page: {record.original_url}")
                continue
            
            filtered_records.append(record)
        
        return filtered_records, filtered_count


class ContentSizeFilter:
    """Filter for removing pages that are too small or too large"""
    
    @classmethod
    def filter_by_size(cls, records: List[CDXRecord], min_size: int = 200, 
                      max_size: Optional[int] = None) -> Tuple[List[CDXRecord], int]:
        """
        Filter records by content size.
        
        Args:
            records: List of CDX records
            min_size: Minimum content size in bytes
            max_size: Maximum content size in bytes (None for no limit)
            
        Returns:
            Tuple of (filtered_records, filtered_count)
        """
        filtered_records = []
        filtered_count = 0
        
        for record in records:
            content_length = record.content_length_bytes
            
            # Skip if too small
            if content_length > 0 and content_length < min_size:
                filtered_count += 1
                logger.debug(f"Filtered small page ({content_length} bytes): {record.original_url}")
                continue
            
            # Skip if too large
            if max_size and content_length > max_size:
                filtered_count += 1
                logger.debug(f"Filtered large page ({content_length} bytes): {record.original_url}")
                continue
            
            filtered_records.append(record)
        
        return filtered_records, filtered_count


class StaticAssetFilter:
    """Filter for static web assets that should never create database entries"""
    
    # Comprehensive static asset extensions that should be filtered at CDX level
    STATIC_ASSET_EXTENSIONS = {
        # JavaScript and CSS
        '.js', '.jsx', '.ts', '.tsx', '.mjs', '.cjs',
        '.css', '.scss', '.sass', '.less', '.styl',
        
        # Images (all formats)
        '.jpg', '.jpeg', '.png', '.gif', '.svg', '.webp', '.ico', '.icon',
        '.bmp', '.tiff', '.tif', '.psd', '.eps', '.ai', '.raw', '.heic', '.avif',
        
        # Fonts
        '.woff', '.woff2', '.ttf', '.otf', '.eot',
        
        # Audio/Video
        '.mp3', '.mp4', '.avi', '.mov', '.wmv', '.flv', '.wav', '.ogg', '.m4a',
        '.mkv', '.webm', '.m4v', '.3gp', '.aac', '.flac',
        
        # Archives and executables
        '.zip', '.rar', '.7z', '.tar', '.gz', '.bz2', '.xz',
        '.exe', '.dmg', '.deb', '.rpm', '.msi', '.iso', '.app',
        
        # Data and config files
        '.xml', '.json', '.yaml', '.yml', '.toml', '.ini', '.conf', '.cfg',
        '.log', '.tmp', '.temp', '.bak', '.backup',
        
        # Development files
        '.map', '.min.js', '.min.css', '.bundle.js', '.bundle.css',
        '.source-map', '.d.ts'
    }
    
    # MIME types that should be filtered at CDX query level
    STATIC_ASSET_MIME_TYPES = {
        'image/*',
        'application/javascript',
        'application/x-javascript', 
        'text/javascript',
        'text/css',
        'font/*',
        'application/font-woff',
        'application/font-woff2',
        'application/vnd.ms-fontobject',
        'audio/*',
        'video/*',
        'application/zip',
        'application/x-rar-compressed',
        'application/octet-stream'  # Often used for binaries
    }
    
    @classmethod
    def is_static_asset(cls, url: str, mime_type: str = None) -> bool:
        """
        Determine if a URL represents a static asset that should never be processed.
        
        Args:
            url: The URL to check
            mime_type: Optional MIME type from CDX record
            
        Returns:
            True if this is a static asset that should be filtered out
        """
        # Check MIME type first (most reliable)
        if mime_type:
            mime_lower = mime_type.lower()
            for static_mime in cls.STATIC_ASSET_MIME_TYPES:
                if static_mime.endswith('*'):
                    if mime_lower.startswith(static_mime[:-1]):
                        return True
                elif mime_lower == static_mime:
                    return True
        
        # Check file extension
        url_lower = url.lower()
        # Extract the path part (before query parameters and fragments)
        path_part = url_lower.split('?')[0].split('#')[0]
        
        # Check if it ends with any static asset extension
        for ext in cls.STATIC_ASSET_EXTENSIONS:
            if path_part.endswith(ext):
                return True
        
        # Check for common static asset URL patterns
        static_patterns = [
            '/assets/', '/static/', '/public/', '/resources/',
            '/js/', '/css/', '/images/', '/img/', '/fonts/',
            '/media/', '/uploads/', '/files/', '/downloads/',
            '/_next/static/', '/webpack/', '/build/',
        ]
        
        for pattern in static_patterns:
            if pattern in url_lower:
                return True
        
        return False
    
    @classmethod 
    def filter_static_assets(cls, records: List[CDXRecord]) -> Tuple[List[CDXRecord], int]:
        """
        Filter out static assets from CDX records before any database operations.
        
        Args:
            records: List of CDX records
            
        Returns:
            Tuple of (filtered_records, static_assets_filtered_count)
        """
        filtered_records = []
        static_assets_filtered = 0
        
        for record in records:
            if cls.is_static_asset(record.original_url, record.mime_type):
                static_assets_filtered += 1
                logger.debug(f"Filtered static asset: {record.original_url} (mime: {record.mime_type})")
            else:
                filtered_records.append(record)
        
        if static_assets_filtered > 0:
            logger.info(f"Static asset pre-filter: {len(records)} -> {len(filtered_records)} records "
                       f"({static_assets_filtered} static assets filtered out)")
        
        return filtered_records, static_assets_filtered
    
    @classmethod
    def get_mime_type_exclusion_filter(cls) -> str:
        """
        Generate CDX API filter string to exclude static asset MIME types.
        
        Returns:
            String for CDX filter parameter
        """
        # CDX API doesn't support complex MIME type exclusions well,
        # so we focus on the most important ones to reduce bandwidth
        exclusions = [
            '!mimetype:image/*',
            '!mimetype:application/javascript',
            '!mimetype:text/javascript', 
            '!mimetype:text/css',
            '!mimetype:font/*',
            '!mimetype:audio/*',
            '!mimetype:video/*'
        ]
        return ' '.join(exclusions)


class AttachmentFilter:
    """Filter for attachment files based on URL extensions"""
    
    # Common attachment file extensions to filter out
    ATTACHMENT_EXTENSIONS = {
        # Document formats
        '.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx',
        '.odt', '.ods', '.odp', '.rtf', '.txt',
        # Archive formats  
        '.zip', '.rar', '.7z', '.tar', '.gz', '.bz2',
        # Image formats (some, not all - keep common web images for now)
        '.bmp', '.tiff', '.eps', '.ai', '.psd',
        # Audio/Video formats
        '.mp3', '.mp4', '.avi', '.mov', '.wmv', '.flv', '.wav', '.ogg',
        # Other binary formats
        '.exe', '.dmg', '.deb', '.rpm', '.msi', '.iso'
    }
    
    @classmethod
    def filter_by_extension(cls, records: List[CDXRecord], 
                          include_attachments: bool = True) -> Tuple[List[CDXRecord], int]:
        """
        Filter CDX records by file extension to exclude/include attachments
        
        Args:
            records: List of CDX records to filter
            include_attachments: Whether to include attachment files
            
        Returns:
            Tuple of (filtered_records, number_filtered_out)
        """
        if include_attachments:
            # No filtering needed if attachments are allowed
            return records, 0
            
        original_count = len(records)
        
        def is_attachment_url(url: str) -> bool:
            """Check if URL ends with an attachment extension"""
            url_lower = url.lower()
            # Extract the path part (before query parameters)
            path_part = url_lower.split('?')[0]
            # Remove fragment identifier
            path_part = path_part.split('#')[0]
            # Check if it ends with any attachment extension
            for ext in cls.ATTACHMENT_EXTENSIONS:
                if path_part.endswith(ext):
                    return True
            return False
        
        # Filter out records with attachment extensions
        filtered_records = []
        filtered_count = 0
        
        for record in records:
            if is_attachment_url(record.original_url):
                filtered_count += 1
                logger.debug(f"Filtered attachment URL: {record.original_url}")
            else:
                filtered_records.append(record)
        
        if filtered_count > 0:
            logger.info(f"Attachment extension filter: {original_count} -> {len(filtered_records)} records ({filtered_count} attachment URLs filtered out)")
        else:
            logger.debug(f"Attachment extension filter: no attachment URLs found in {original_count} records")
        
        return filtered_records, filtered_count


class DuplicateFilter:
    """Filter for removing duplicate pages"""
    
    @classmethod
    def filter_duplicates(cls, records: List[CDXRecord], 
                         existing_digests: Optional[Set[str]] = None) -> Tuple[List[CDXRecord], int]:
        """
        Filter duplicate records by digest hash.
        
        Args:
            records: List of CDX records
            existing_digests: Set of already processed digest hashes
            
        Returns:
            Tuple of (filtered_records, filtered_count)
        """
        if existing_digests is None:
            existing_digests = set()
        
        filtered_records = []
        filtered_count = 0
        seen_digests = existing_digests.copy()
        
        for record in records:
            if record.digest in seen_digests:
                filtered_count += 1
                logger.debug(f"Filtered duplicate: {record.original_url} (digest: {record.digest})")
                continue
            
            seen_digests.add(record.digest)
            filtered_records.append(record)
        
        return filtered_records, filtered_count


_TRANSIENT_STATUSES = {500, 502, 504, 520, 521, 522, 523, 524}  # retried with backoff (3 attempts)
_SPLIT_STATUSES = {503, 504, 522, 524}  # the query was too heavy: split the date window
_COLLAPSE_RE = re.compile(r"^(digest|urlkey|timestamp:([1-9]|1[0-4]))$")


def normalize_collapse(value: Optional[str] = None) -> str:
    """Validate a CDX collapse spec: ``digest``, ``urlkey`` or ``timestamp:N`` (N = 1..14)."""
    candidate = (value or settings.WAYBACK_CDX_COLLAPSE or "digest").strip().lower()
    if not _COLLAPSE_RE.match(candidate):
        raise ValueError(
            f"Invalid CDX collapse {candidate!r}: use 'digest', 'urlkey' or 'timestamp:N' (N 1-14)"
        )
    return candidate


def _transient(exc: Exception) -> Exception:
    """Mark an error as worth an immediate (backed-off) retry."""
    exc.transient = True  # type: ignore[attr-defined]
    return exc


def _is_transient(exc: BaseException) -> bool:
    return bool(getattr(exc, "transient", False))


def _pad_date(value: str, end: bool) -> datetime:
    """Parse a CDX date bound (YYYY, YYYYMM, YYYYMMDD or a full timestamp) to a day."""
    digits = re.sub(r"\D", "", value)
    if len(digits) >= 8:
        padded = digits[:8]
    elif len(digits) == 6:
        padded = digits + ("28" if end else "01")
    elif len(digits) == 4:
        padded = digits + ("1231" if end else "0101")
    else:
        raise ValueError(f"Unsupported CDX date bound {value!r}")
    return datetime.strptime(padded, "%Y%m%d")


@dataclass
class _PagingState:
    """Shared across a (possibly window-split) fetch: request budget and counters."""

    pages_left: Optional[int]
    pages_fetched: int = 0
    static_filtered: int = 0
    windows_split: int = 0


class CDXAPIClient:
    """
    CDX API client for the Wayback Machine.

    Plain httpx through the shared archive limiter (see archive_rate_limiter): each
    request takes a slot on one of a few paced exits. No browser fallback. Result
    pages are paged with ``limit`` + ``showResumeKey`` and cached in Redis by their
    full query URL. Failures raise typed errors (CDXRateLimited / CDXConnectionError /
    CDXHTTPError, which are both CDXAPIException and the matching ArchiveFetchError).
    """

    BASE_URL = "https://web.archive.org/cdx/search/cdx"
    DEFAULT_TIMEOUT = 60  # seconds, read timeout when WAYBACK_MACHINE_TIMEOUT is unset
    FIELDS = "timestamp,original,mimetype,statuscode,digest,length"

    @staticmethod
    def _get_stealth_headers() -> dict:
        """Get randomized browser headers to avoid detection."""
        from app.services.stealth_headers import get_stealth_headers
        return get_stealth_headers()

    def __init__(self):
        self.timeout = settings.WAYBACK_MACHINE_TIMEOUT or self.DEFAULT_TIMEOUT
        logger.info(
            f"Initialized CDX API client: {self.timeout}s read timeout, "
            f"page limit {settings.WAYBACK_CDX_PAGE_LIMIT}, collapse={settings.WAYBACK_CDX_COLLAPSE}"
        )

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        # HTTP clients are created per request (each goes out through its own exit).
        return None

    # ------------------------------------------------------------------ cache
    @staticmethod
    def _cache_key(url: str) -> str:
        return "cdx:page:" + hashlib.sha1(url.encode()).hexdigest()

    async def _cache_get(self, url: str) -> Optional[str]:
        if int(settings.WAYBACK_CDX_CACHE_TTL) <= 0:
            return None
        try:
            raw = await egress.get_redis(decode_responses=False).get(self._cache_key(url))
            if raw is None:
                return None
            logger.info(f"CDX cache hit: {url}")
            return zlib.decompress(raw).decode("utf-8")
        except Exception as exc:
            logger.debug(f"CDX cache read failed: {exc}")
            return None

    async def _cache_set(self, url: str, text: str) -> None:
        ttl = int(settings.WAYBACK_CDX_CACHE_TTL)
        if ttl <= 0:
            return
        try:
            await egress.get_redis(decode_responses=False).set(
                self._cache_key(url), zlib.compress(text.encode("utf-8")), ex=ttl
            )
        except Exception as exc:
            logger.debug(f"CDX cache write failed: {exc}")

    # ---------------------------------------------------------------- request
    async def _make_request(self, url: str) -> str:
        """
        GET one CDX URL through the limiter, cached by full URL.

        A 429/503 parks the exit and is raised as CDXRateLimited immediately (no
        rotate-on-block, no retry while parked); the pager above decides whether to
        split the window (503) and the caller re-queues. Pages already fetched stay
        in the Redis cache, so repeating the query resumes cheaply.
        """
        cached = await self._cache_get(url)
        if cached is not None:
            return cached
        text = await self._request_with_retry(url)
        await self._cache_set(url, text)
        return text

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_random_exponential(multiplier=2, max=30),  # full jitter
        retry=retry_if_exception(_is_transient),
        before_sleep=before_sleep_log(logger, logging.INFO),
        reraise=True,
    )
    async def _request_with_retry(self, url: str) -> str:
        """One limiter slot + one HTTP request; transient failures retried up to 3 attempts."""
        limiter = get_archive_rate_limiter()
        try:
            lease = await limiter.acquire(HostClass.WAYBACK_CDX)
        except ArchiveRateLimited as exc:
            # Limiter says parked/saturated: never retried here.
            raise CDXRateLimited(str(exc), url=url, retry_after=exc.retry_after) from exc
        except ArchiveConnectionError as exc:
            raise CDXConnectionError(str(exc), url=url) from exc
        try:
            return await self._send(url, lease)
        finally:
            await limiter.release(lease)

    async def _send(self, url: str, lease) -> str:
        timeout = httpx.Timeout(connect=10.0, read=float(self.timeout), write=15.0, pool=10.0)
        client_kwargs = {"proxy": lease.exit.proxy_url} if lease.exit.proxy_url else {}
        try:
            async with httpx.AsyncClient(
                timeout=timeout, headers=self._get_stealth_headers(), **client_kwargs
            ) as client:
                response = await client.get(url)
        except httpx.ReadTimeout as exc:
            # Slow heavy query (or a hung tunnel: the probe tells them apart). Don't hammer
            # it again, let the pager split the window.
            await lease.connection_failed(exc)
            err = CDXConnectionError(f"Timeout reading CDX response via exit {lease.exit.id}", url=url)
            err.timed_out = True
            raise err from exc
        except httpx.TransportError as exc:
            verdict = await lease.connection_failed(exc)
            raise _transient(
                CDXConnectionError(
                    f"Connection error ({type(exc).__name__}) via exit {lease.exit.id}: exit {verdict}",
                    url=url,
                )
            ) from exc

        status = response.status_code
        if status in (429, 503):
            retry_after = parse_retry_after(response.headers.get("Retry-After"))
            parked = await lease.rate_limited(retry_after)
            label = "Rate limited" if status == 429 else "Archive.org service unavailable"
            raise CDXRateLimited(
                f"{label}: {status} via exit {lease.exit.id}",
                url=url, status_code=status, retry_after=parked,
            )
        if status in _TRANSIENT_STATUSES:
            err = CDXHTTPError(f"Archive.org server error {status} (retrying)", url=url, status_code=status)
            err.retryable = True
            raise _transient(err)
        if status >= 400:
            raise CDXHTTPError(f"Client error: {status}", url=url, status_code=status)

        text = response.text
        if text.lstrip()[:1] not in ("[", "") and not text.strip().isdigit():
            err = CDXHTTPError(f"Unexpected CDX response: {text[:120]!r}", url=url, status_code=status)
            err.retryable = True
            raise _transient(err)
        await lease.success()
        return text

    # ------------------------------------------------------------- URL building
    @staticmethod
    def _resolve_target(domain_name: str, match_type: str, url_path: Optional[str],
                        log: bool = False) -> Tuple[str, str]:
        """Return (query url, CDX matchType) for the requested target."""
        if domain_name.startswith(('http://', 'https://')):
            result = (domain_name, "prefix")  # full URL: prefix match on that URL
            message = f"Full URL detected: using prefix match with {domain_name}"
        elif match_type == "prefix" and url_path:
            result = (url_path, "prefix")
            message = f"Prefix match requested: using url_path {url_path}"
        elif match_type in ("exact", "prefix", "regex"):
            result = (domain_name, match_type)
            message = f"{match_type.capitalize()} match: using {match_type} {domain_name}"
        else:
            result = (domain_name, "domain")
            message = f"Domain match: using domain {domain_name}"
        if log:
            logger.info(message)
        return result

    @staticmethod
    def _assemble(params: List[Tuple[str, str]]) -> str:
        """Join params into a query string unescaped (CDX filters rely on raw ``|``, ``:``)."""
        return CDXAPIClient.BASE_URL + "?" + "&".join(f"{key}={value}" for key, value in params)

    def _build_cdx_url_simple(self, domain_name: str, from_date: str, to_date: str,
                              match_type: str = "domain", url_path: Optional[str] = None,
                              include_attachments: bool = True,
                              collapse: Optional[str] = None, limit: Optional[int] = None,
                              resume_key: Optional[str] = None) -> str:
        """
        Build the simplified CDX query, e.g.
        https://web.archive.org/cdx/search/cdx?url=domain.com&from=20200101&to=20250902
        &output=json&collapse=digest&matchType=domain&fl=timestamp,original,mimetype,statuscode,digest,length
        &filter=statuscode:200&filter=mimetype:text/html&limit=5000&showResumeKey=true
        """
        query_url, cdx_match_type = self._resolve_target(domain_name, match_type, url_path)
        mimetype_filter = 'mimetype:text/html|application/pdf' if include_attachments else 'mimetype:text/html'
        params: List[Tuple[str, str]] = [
            ('url', query_url),
            ('from', from_date),
            ('to', to_date),
            ('output', 'json'),
            ('collapse', normalize_collapse(collapse)),
            ('matchType', cdx_match_type),
            ('fl', self.FIELDS),
            ('filter', 'statuscode:200'),
            ('filter', mimetype_filter),
            ('limit', str(int(limit or settings.WAYBACK_CDX_PAGE_LIMIT))),
            ('showResumeKey', 'true'),
        ]
        if resume_key:
            params.append(('resumeKey', resume_key))
        final_url = self._assemble(params)
        logger.info(f"Built simple CDX URL: {final_url}")
        return final_url

    def _build_cdx_url(self, domain_name: str, from_date: str, to_date: str,
                       match_type: str = "domain", url_path: Optional[str] = None,
                       min_size: int = 1000, max_size: int = 10 * 1024 * 1024,
                       resume_key: Optional[str] = None, show_num_pages: bool = False,
                       include_attachments: bool = True,
                       collapse: Optional[str] = None, limit: Optional[int] = None) -> str:
        """
        Build the CDX URL with static-asset exclusions and size filters.

        ``show_num_pages`` builds the plain-text page-count query (no output=json,
        which would return a row of nulls instead of the number).
        """
        query_url, cdx_match_type = self._resolve_target(domain_name, match_type, url_path, log=True)
        logger.info(f"Building CDX URL: matchType={cdx_match_type}, query_url={query_url}")

        if include_attachments:
            mimetype_filter = 'mimetype:text/html|application/pdf'
            logger.info(f"Including PDF attachments for target: {query_url}")
        else:
            mimetype_filter = 'mimetype:text/html'
            logger.info(f"Excluding PDF attachments for target: {query_url}")
        params: List[Tuple[str, str]] = [
            ('url', query_url),
            ('from', from_date),
            ('to', to_date),
        ]
        if not show_num_pages:
            params.append(('output', 'json'))
        params += [
            ('collapse', normalize_collapse(collapse)),
            ('matchType', cdx_match_type),
            ('fl', self.FIELDS),
            ('filter', 'statuscode:200'),
            ('filter', mimetype_filter),
        ]
        # Static asset exclusions reduce CDX bandwidth (the CDX API may ignore some).
        for exclusion in ('!mimetype:image/*', '!mimetype:application/javascript',
                          '!mimetype:text/javascript', '!mimetype:text/css',
                          '!mimetype:audio/*', '!mimetype:video/*'):
            params.append(('filter', exclusion))
        if min_size > 0 and max_size > 0:
            params.append(('filter', f'length:[{min_size} TO {max_size}]'))
        elif min_size > 0:
            params.append(('filter', f'length:{min_size}-'))

        if show_num_pages:
            params.append(('showNumPages', 'true'))
        else:
            params.append(('limit', str(int(limit or settings.WAYBACK_CDX_PAGE_LIMIT))))
            params.append(('showResumeKey', 'true'))
            if resume_key:
                params.append(('resumeKey', resume_key))
        return self._assemble(params)

    async def get_page_count(self, domain_name: str, from_date: str, to_date: str,
                             match_type: str = "domain", url_path: Optional[str] = None,
                             min_size: int = 1000, include_attachments: bool = True) -> int:
        """
        Estimated number of CDX pages for a query (used for cost estimates only;
        fetching pages through ``limit``/resume keys does not depend on it).

        Returns 0 if the query fails.
        """
        url = self._build_cdx_url(
            domain_name, from_date, to_date, match_type, url_path,
            min_size=min_size, show_num_pages=True, include_attachments=include_attachments
        )
        try:
            response_text = await self._make_request(url)
            try:
                page_count = int(response_text.strip())
                logger.info(f"CDX query for {domain_name} has {page_count} pages available")
                return page_count
            except ValueError:
                logger.warning(f"Could not parse page count for {domain_name}: {response_text[:100]}")
                return 1 if response_text.strip() else 0
        except Exception as e:
            logger.error(f"Error getting page count for {domain_name}: {str(e)}")
            return 0

    # ----------------------------------------------------------------- parsing
    @staticmethod
    def _split_resume_key(data: list) -> Tuple[list, Optional[str]]:
        """
        With showResumeKey=true the JSON ends with ``[], ["<resumeKey>"]`` when more
        results remain. Returns (rows without the trailer, resume key or None).
        """
        if len(data) >= 2 and data[-2] == [] and isinstance(data[-1], list) and len(data[-1]) == 1:
            return data[:-2], str(data[-1][0])
        return data, None

    def _parse_cdx_page(self, response_text: str) -> Tuple[List[CDXRecord], int, Optional[str]]:
        """Parse one CDX JSON page into (records, static assets filtered, resume key)."""
        if not response_text.strip():
            return [], 0, None
        try:
            data = json.loads(response_text)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse CDX JSON response: {e}")
            return [], 0, None
        if not isinstance(data, list):
            return [], 0, None

        data, resume_key = self._split_resume_key(data)
        if not data:
            return [], 0, resume_key
        data_rows = data[1:] if data[0] and data[0][0] == "timestamp" else data

        raw_records = []
        for row in data_rows:
            if len(row) >= 6:
                try:
                    raw_records.append(CDXRecord.from_wayback_response(row))
                except ValueError as e:
                    logger.warning(f"Skipping invalid CDX record: {e}")

        # Static assets never get database entries.
        filtered_records, static_assets_filtered = StaticAssetFilter.filter_static_assets(raw_records)
        if static_assets_filtered > 0:
            logger.info(f"CDX parsing pre-filter eliminated {static_assets_filtered} static assets "
                        f"from {len(raw_records)} raw records")
        return filtered_records, static_assets_filtered, resume_key

    def _parse_cdx_response(self, response_text: str) -> Tuple[List[CDXRecord], int]:
        """Parse a CDX JSON page into (records, static assets filtered)."""
        records, static_filtered, _resume_key = self._parse_cdx_page(response_text)
        return records, static_filtered

    # ------------------------------------------------------------------ paging
    @staticmethod
    def _should_split(exc: Exception) -> bool:
        return getattr(exc, "status_code", None) in _SPLIT_STATUSES or bool(getattr(exc, "timed_out", False))

    @staticmethod
    def _split_window(from_date: str, to_date: str) -> Optional[Tuple[Tuple[str, str], Tuple[str, str]]]:
        """Halve a date range; None when it is already a single day."""
        try:
            lo, hi = _pad_date(from_date, end=False), _pad_date(to_date, end=True)
        except ValueError:
            return None
        span = (hi - lo).days
        if span < 1:
            return None
        mid = lo + timedelta(days=span // 2)
        return (from_date, mid.strftime("%Y%m%d")), ((mid + timedelta(days=1)).strftime("%Y%m%d"), to_date)

    async def _fetch_window(self, build: Callable[[str, str, Optional[str]], str],
                            from_date: str, to_date: str, state: _PagingState,
                            depth: int = 0) -> List[CDXRecord]:
        """
        Page through one date window with resume keys. If the first request of a
        window 503/504s (heavy query), split the window in half (bounded depth) and
        fetch the halves instead. Later-page failures propagate; the Redis page
        cache makes a retry cheap.
        """
        records: List[CDXRecord] = []
        resume_key: Optional[str] = None
        while state.pages_left is None or state.pages_left > 0:
            url = build(from_date, to_date, resume_key)
            try:
                text = await self._make_request(url)
            except (CDXRateLimited, CDXConnectionError, CDXHTTPError) as exc:
                halves = self._split_window(from_date, to_date)
                if (resume_key is None and self._should_split(exc) and halves
                        and depth < int(settings.WAYBACK_CDX_SPLIT_MAX_DEPTH)):
                    state.windows_split += 1
                    logger.warning(
                        f"CDX query {from_date}-{to_date} failed ({exc}); splitting window "
                        f"(depth {depth + 1}/{settings.WAYBACK_CDX_SPLIT_MAX_DEPTH})"
                    )
                    for lo, hi in halves:
                        records.extend(await self._fetch_window(build, lo, hi, state, depth + 1))
                    return records
                raise

            page_records, static_filtered, resume_key = self._parse_cdx_page(text)
            records.extend(page_records)
            state.pages_fetched += 1
            state.static_filtered += static_filtered
            if state.pages_left is not None:
                state.pages_left -= 1
            logger.info(
                f"CDX page {state.pages_fetched}: {len(page_records)} records "
                f"({static_filtered} static assets pre-filtered), more={'yes' if resume_key else 'no'}"
            )
            if not resume_key:
                break
        return records

    async def fetch_cdx_records_simple(self, domain_name: str, from_date: str, to_date: str,
                                       match_type: str = "domain", url_path: Optional[str] = None,
                                       page_size: int = None, max_pages: Optional[int] = None,
                                       include_attachments: bool = True,
                                       collapse: Optional[str] = None) -> Tuple[List[CDXRecord], Dict[str, int]]:
        """
        Fetch CDX records with resume-key paging and CDX-level collapsing.

        Args:
            domain_name: Domain to query
            from_date: Start date (YYYYMMDD format)
            to_date: End date (YYYYMMDD format)
            match_type: CDX match type (domain, prefix, exact)
            url_path: URL path for prefix matching
            page_size: Rows per request (``limit``; default WAYBACK_CDX_PAGE_LIMIT)
            max_pages: Maximum requests (pages) to make
            include_attachments: Include PDF files
            collapse: ``digest`` | ``urlkey`` | ``timestamp:N`` (default WAYBACK_CDX_COLLAPSE)

        Returns:
            Tuple of (records, stats)

        Raises:
            ArchiveRateLimited / ArchiveConnectionError / ArchiveHTTPError (as the
            CDX* subclasses) when a page cannot be fetched; nothing is silently skipped.
        """
        collapse = normalize_collapse(collapse)
        limit = int(page_size or settings.WAYBACK_CDX_PAGE_LIMIT)
        logger.info(f"Starting CDX fetch for {domain_name} from {from_date} to {to_date} "
                    f"(collapse={collapse}, limit={limit})")

        def build(lo: str, hi: str, resume_key: Optional[str]) -> str:
            return self._build_cdx_url_simple(
                domain_name, lo, hi, match_type, url_path, include_attachments=include_attachments,
                collapse=collapse, limit=limit, resume_key=resume_key,
            )

        state = _PagingState(pages_left=max_pages)
        records = await self._fetch_window(build, from_date, to_date, state)
        stats = {
            "total_pages": state.pages_fetched,
            "fetched_pages": state.pages_fetched,
            "total_records": len(records),
            "final_count": len(records),
            "windows_split": state.windows_split,
        }
        logger.info(f"CDX fetch complete: {len(records)} records from {state.pages_fetched} pages")
        return records, stats

    async def fetch_cdx_records(self, domain_name: str, from_date: str, to_date: str,
                                match_type: str = "domain", url_path: Optional[str] = None,
                                min_size: int = 1000, max_size: int = 10 * 1024 * 1024,
                                page_size: int = None, max_pages: Optional[int] = None,
                                existing_digests: Optional[Set[str]] = None,
                                filter_list_pages: bool = True,
                                use_resume_key: bool = True,
                                include_attachments: bool = True,
                                collapse: Optional[str] = None) -> Tuple[List[CDXRecord], Dict[str, int]]:
        """
        Fetch CDX records with comprehensive filtering.

        ``use_resume_key`` is accepted for drop-in compatibility with the Common
        Crawl clients; resume-key paging is always used.

        Returns:
            Tuple of (filtered_records, filter_stats)
        """
        collapse = normalize_collapse(collapse)
        limit = int(page_size or settings.WAYBACK_CDX_PAGE_LIMIT)

        def build(lo: str, hi: str, resume_key: Optional[str]) -> str:
            return self._build_cdx_url(
                domain_name, lo, hi, match_type, url_path, min_size=min_size, max_size=max_size,
                resume_key=resume_key, include_attachments=include_attachments,
                collapse=collapse, limit=limit,
            )

        state = _PagingState(pages_left=max_pages)
        all_records = await self._fetch_window(build, from_date, to_date, state)
        if not all_records and state.pages_fetched <= 1:
            logger.warning(f"No CDX data found for {domain_name} from {from_date} to {to_date}")

        filter_stats = {
            "total_pages": state.pages_fetched,
            "fetched_pages": state.pages_fetched,
            "total_records": len(all_records),
            "static_assets_filtered": state.static_filtered,
            "size_filtered": 0,
            "attachment_filtered": 0,
            "list_filtered": 0,
            "duplicate_filtered": 0,
            "final_count": 0,
            "windows_split": state.windows_split,
        }

        # 1. Size filtering
        filtered_records, size_filtered = ContentSizeFilter.filter_by_size(all_records, min_size, max_size)
        filter_stats["size_filtered"] = size_filtered

        # 2. Attachment extension filtering
        filtered_records, attachment_filtered = AttachmentFilter.filter_by_extension(
            filtered_records, include_attachments
        )
        filter_stats["attachment_filtered"] = attachment_filtered

        # 3. List page filtering
        if filter_list_pages:
            filtered_records, list_filtered = ListPageFilter.filter_records(filtered_records)
            filter_stats["list_filtered"] = list_filtered

        # 4. Duplicate filtering
        filtered_records, duplicate_filtered = DuplicateFilter.filter_duplicates(
            filtered_records, existing_digests
        )
        filter_stats["duplicate_filtered"] = duplicate_filtered
        filter_stats["final_count"] = len(filtered_records)

        logger.info(
            f"CDX filtering complete for {domain_name}: "
            f"{filter_stats['total_records']} total -> {filter_stats['final_count']} final "
            f"(static assets: -{filter_stats['static_assets_filtered']}, "
            f"size: -{filter_stats['size_filtered']}, "
            f"list: -{filter_stats['list_filtered']}, "
            f"duplicates: -{filter_stats['duplicate_filtered']})"
        )
        return filtered_records, filter_stats


# Convenience functions for backward compatibility
async def get_cdx_page_count(domain_name: str, from_date: str, to_date: str,
                           match_type: str = "domain", url_path: Optional[str] = None,
                           min_size: int = 200) -> int:
    """Get CDX page count - convenience function"""
    async with CDXAPIClient() as client:
        return await client.get_page_count(domain_name, from_date, to_date, match_type, url_path, min_size)


async def fetch_cdx_pages(domain_name: str, from_date: str, to_date: str,
                        match_type: str = "domain", url_path: Optional[str] = None,
                        min_size: int = 200, max_pages: Optional[int] = None) -> List[CDXRecord]:
    """Fetch CDX pages - convenience function (uses legacy complex method)"""
    async with CDXAPIClient() as client:
        records, stats = await client.fetch_cdx_records(
            domain_name, from_date, to_date, match_type, url_path,
            min_size=min_size, max_pages=max_pages
        )
        return records


async def fetch_cdx_pages_simple(domain_name: str, from_date: str, to_date: str,
                               match_type: str = "domain", url_path: Optional[str] = None,
                               max_pages: Optional[int] = None, include_attachments: bool = True) -> List[CDXRecord]:
    """
    Fetch CDX pages using simplified approach (RECOMMENDED)
    
    This method produces queries like:
    https://web.archive.org/cdx/search/cdx?url=domain.com&from=20200101&to=20250902
    &output=json&collapse=digest&matchType=domain&fl=timestamp,original,mimetype,statuscode,digest,length
    &filter=statuscode:200&filter=mimetype:text/html&pageSize=5000&page=0
    
    Args:
        domain_name: Domain to query (e.g., 'example.com')
        from_date: Start date in YYYYMMDD format (e.g., '20200101')
        to_date: End date in YYYYMMDD format (e.g., '20250902')
        match_type: Match type - 'domain', 'prefix', or 'exact'
        url_path: URL path for prefix matching
        max_pages: Maximum pages to fetch (None = all pages)
        include_attachments: Include PDF files in results
        
    Returns:
        List of CDXRecord objects
    """
    async with CDXAPIClient() as client:
        records, stats = await client.fetch_cdx_records_simple(
            domain_name, from_date, to_date, match_type, url_path,
            max_pages=max_pages, include_attachments=include_attachments
        )
        return records