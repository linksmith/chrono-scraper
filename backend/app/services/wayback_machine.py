"""
Wayback Machine CDX API client with robust retry logic and filtering
"""
import asyncio
import re
import logging
from datetime import datetime
from typing import List, Dict, Tuple, Optional, Set, Union
from dataclasses import dataclass

import httpx
from tenacity import (
    retry, 
    stop_after_attempt, 
    wait_exponential,
    retry_if_exception_type,
    before_sleep_log
)

from ..core.config import settings
from ..models.project import ArchiveSource

logger = logging.getLogger(__name__)


class WaybackMachineException(Exception):
    """Base exception for Wayback Machine API errors"""
    pass


class CDXAPIException(WaybackMachineException):
    """CDX API specific exceptions"""
    pass


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
            return f"https://web.archive.org/web/{self.timestamp}if_/{self.original_url}"
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


class CDXAPIClient:
    """
    Robust CDX API client with retry logic, filtering, and digest-based change detection
    """
    
    BASE_URL = "https://web.archive.org/cdx/search/cdx"
    DEFAULT_TIMEOUT = 60  # seconds
    DEFAULT_MAX_RETRIES = 5
    DEFAULT_PAGE_SIZE = 5000  # Increased for better efficiency
    
    def __init__(self):
        self.timeout = settings.WAYBACK_MACHINE_TIMEOUT or self.DEFAULT_TIMEOUT
        self.max_retries = settings.WAYBACK_MACHINE_MAX_RETRIES or self.DEFAULT_MAX_RETRIES
        
        # Configure proxy settings if available
        proxy_settings = {}
        proxy_server = getattr(settings, 'PROXY_SERVER', None)
        proxy_username = getattr(settings, 'PROXY_USERNAME', None)
        proxy_password = getattr(settings, 'PROXY_PASSWORD', None)
        
        if proxy_server:
            if proxy_username and proxy_password:
                # Authenticated proxy
                proxy_url = f"http://{proxy_username}:{proxy_password}@{proxy_server.replace('http://', '')}"
            else:
                # Unauthenticated proxy
                proxy_url = proxy_server if proxy_server.startswith('http') else f"http://{proxy_server}"
            
            proxy_settings = {
                "http://": proxy_url,
                "https://": proxy_url
            }
            logger.info(f"CDX API client configured with proxy: {proxy_server}")
        
        # Create HTTP client with connection pooling and proxy support
        client_kwargs = {
            "timeout": httpx.Timeout(self.timeout),
            "limits": httpx.Limits(max_keepalive_connections=10, max_connections=50),
            "headers": {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'
            }
        }
        
        if proxy_settings:
            # httpx uses a single proxy string, not a dict like requests
            proxy_url = proxy_settings.get("http://") or proxy_settings.get("https://")
            client_kwargs["proxy"] = proxy_url
        
        self.client = httpx.AsyncClient(**client_kwargs)
        
        logger.info(f"Initialized CDX API client with {self.timeout}s timeout, {self.max_retries} max retries")
    
    async def __aenter__(self):
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.client.aclose()
    
    @retry(
        stop=stop_after_attempt(8),  # Increased for Archive.org timeout resilience
        wait=wait_exponential(multiplier=1.5, min=3, max=45),  # Faster initial retry for 522 errors
        retry=retry_if_exception_type((httpx.TimeoutException, httpx.ConnectError, CDXAPIException)),
        before_sleep=before_sleep_log(logger, logging.INFO)  # Reduce log noise for expected retries
    )
    async def _make_request(self, url: str) -> str:
        """Make HTTP request with retry logic"""
        try:
            response = await self.client.get(url)
            
            # Handle rate limiting
            if response.status_code == 429:
                retry_after = int(response.headers.get('Retry-After', 60))
                logger.warning(f"Rate limited by CDX API, waiting {retry_after}s")
                await asyncio.sleep(retry_after)
                raise CDXAPIException(f"Rate limited: {response.status_code}")
            
            # Handle server errors with specific handling for 522 timeouts
            if response.status_code >= 500:
                if response.status_code == 522:
                    logger.warning(f"Archive.org connection timeout (522) for {url} - will retry")
                    raise CDXAPIException(f"Archive.org timeout (522) - retrying")
                elif response.status_code == 503:
                    logger.warning(f"Archive.org service unavailable (503) for {url} - will retry")
                    raise CDXAPIException(f"Archive.org service unavailable (503) - retrying")
                else:
                    logger.error(f"Archive.org server error {response.status_code} for {url}")
                    raise CDXAPIException(f"Server error: {response.status_code}")
            
            # Handle client errors
            if response.status_code >= 400:
                logger.error(f"Client error {response.status_code}: {response.text}")
                raise CDXAPIException(f"Client error: {response.status_code}")
            
            return response.text
            
        except httpx.TimeoutException:
            logger.error(f"Timeout requesting CDX API: {url}")
            raise
        except httpx.ConnectError:
            logger.error(f"Connection error requesting CDX API: {url}")
            raise
    
    def _build_cdx_url_simple(self, domain_name: str, from_date: str, to_date: str,
                           match_type: str = "domain", url_path: Optional[str] = None,
                           page_size: int = None, page_num: Optional[int] = None,
                           include_attachments: bool = True) -> str:
        """
        Build simplified CDX API URL following the user's preferred approach
        
        This method creates queries like:
        https://web.archive.org/cdx/search/cdx?url=domain.com&from=20200101&to=20250902
        &output=json&collapse=digest&matchType=domain&fl=timestamp,original,mimetype,statuscode,digest,length
        &filter=statuscode:200&filter=mimetype:text/html&pageSize=5000&page=0
        """
        
        # Determine query URL and match type
        if domain_name.startswith(('http://', 'https://')):
            query_url = domain_name
            cdx_match_type = "prefix"
        elif match_type == "prefix" and url_path:
            query_url = url_path
            cdx_match_type = "prefix"
        else:
            query_url = domain_name
            cdx_match_type = match_type
        
        # Simple, reliable MIME type filter
        if include_attachments:
            mimetype_filter = 'mimetype:text/html|application/pdf'
        else:
            mimetype_filter = 'mimetype:text/html'
        
        # Build base parameters (clean and simple like user's example)
        params = {
            'url': query_url,
            'from': from_date,
            'to': to_date,
            'output': 'json',
            'collapse': 'digest',  # Efficient deduplication at CDX level
            'matchType': cdx_match_type,
            'fl': 'timestamp,original,mimetype,statuscode,digest,length',
            'filter': ['statuscode:200', mimetype_filter]
        }
        
        # Add pagination
        if page_size:
            params['pageSize'] = str(page_size)
        else:
            params['pageSize'] = '5000'  # Default like user's example
        
        if page_num is not None:
            params['page'] = str(page_num)
        
        # Build URL cleanly
        url_parts = [f"{self.BASE_URL}?"]
        
        # Add single-value parameters
        for key, value in params.items():
            if key != 'filter':
                url_parts.append(f"&{key}={value}")
        
        # Add filter parameters (can be multiple)
        for filter_val in params['filter']:
            url_parts.append(f"&filter={filter_val}")
        
        final_url = ''.join(url_parts).replace('?&', '?', 1)  # Fix first &
        
        logger.info(f"Built simple CDX URL: {final_url}")
        return final_url

    def _build_cdx_url(self, domain_name: str, from_date: str, to_date: str,
                      match_type: str = "domain", url_path: Optional[str] = None,
                      min_size: int = 1000, max_size: int = 10 * 1024 * 1024, 
                      page_size: int = None, page_num: Optional[int] = None, 
                      resume_key: Optional[str] = None, show_num_pages: bool = False,
                      include_attachments: bool = True) -> str:
        """Build CDX API URL with all parameters"""
        
        # Determine query URL and match type based on input
        # If domain_name contains a full URL (has protocol), extract appropriately
        if domain_name.startswith(('http://', 'https://')):
            # Full URL provided - use prefix matching with the full URL
            query_url = domain_name
            cdx_match_type = "prefix"
            logger.info(f"Full URL detected: using prefix match with {query_url}")
        elif match_type == "prefix" and url_path:
            # Explicit prefix matching with url_path
            query_url = url_path
            cdx_match_type = "prefix"
            logger.info(f"Prefix match requested: using url_path {query_url}")
        elif match_type in ["exact", "prefix", "regex"]:
            # Use the domain name with the specified match type
            query_url = domain_name
            cdx_match_type = match_type
            logger.info(f"{match_type.capitalize()} match: using {match_type} {query_url}")
        else:
            # Domain-only matching (default behavior)
            query_url = domain_name
            cdx_match_type = "domain"
            logger.info(f"Domain match: using domain {query_url}")
        
        logger.info(f"Building CDX URL: matchType={cdx_match_type}, query_url={query_url}")
        
        # Build mimetype filter based on attachment setting and static asset exclusion
        if include_attachments:
            mimetype_filter = 'mimetype:text/html|application/pdf'
            logger.info(f"Including PDF attachments for target: {query_url}")
        else:
            mimetype_filter = 'mimetype:text/html'
            logger.info(f"Excluding PDF attachments for target: {query_url}")
        
        # Base parameters
        params = {
            'url': query_url,
            'from': from_date,
            'to': to_date,
            'output': 'json',
            'collapse': 'digest',
            'matchType': cdx_match_type,
            'fl': 'timestamp,original,mimetype,statuscode,digest,length',
            'filter': ['statuscode:200', mimetype_filter]
        }
        
        # Add static asset MIME type exclusions to reduce CDX bandwidth
        # Note: CDX API has limited support for complex exclusions, but we can try
        static_mime_exclusions = [
            '!mimetype:image/*',
            '!mimetype:application/javascript',
            '!mimetype:text/javascript',
            '!mimetype:text/css',
            '!mimetype:audio/*',
            '!mimetype:video/*'
        ]
        
        # Add static asset exclusions (these will be attempted but may not all work)
        for exclusion in static_mime_exclusions:
            params['filter'].append(exclusion)
        
        logger.info("CDX query includes static asset MIME exclusions to reduce bandwidth")
        
        # Add enhanced size filtering (1KB - 10MB)
        if min_size > 0 and max_size > 0:
            params['filter'].append(f'length:[{min_size} TO {max_size}]')
        elif min_size > 0:
            params['filter'].append(f'length:{min_size}-')
        
        # Add pagination
        if page_size:
            params['pageSize'] = str(page_size)
        
        if page_num is not None:
            params['page'] = str(page_num)
        
        if resume_key:
            params['resumeKey'] = resume_key
        
        if show_num_pages:
            params['showNumPages'] = 'true'
        
        # Build URL
        url_parts = [self.BASE_URL + '?']
        for key, value in params.items():
            if key == 'filter' and isinstance(value, list):
                for filter_val in value:
                    url_parts.append(f'&filter={filter_val}')
            else:
                url_parts.append(f'&{key}={value}')
        
        return ''.join(url_parts).replace('&', '&', 1)  # Fix first &
    
    async def get_page_count(self, domain_name: str, from_date: str, to_date: str,
                           match_type: str = "domain", url_path: Optional[str] = None,
                           min_size: int = 1000, include_attachments: bool = True) -> int:
        """
        Get total number of CDX pages available for a query.
        
        Returns:
            Total number of pages available, or 0 if query fails
        """
        url = self._build_cdx_url(
            domain_name, from_date, to_date, match_type, url_path,
            min_size=min_size, show_num_pages=True, include_attachments=include_attachments
        )
        
        try:
            response_text = await self._make_request(url)
            
            # Try to parse as page count number
            try:
                page_count = int(response_text.strip())
                logger.info(f"CDX query for {domain_name} has {page_count} pages available")
                return page_count
            except ValueError:
                # If we get JSON data instead, estimate from sample
                if response_text.strip().startswith('['):
                    logger.info(f"CDX API returned data instead of page count for {domain_name}")
                    return 1  # At least one page exists
                else:
                    logger.warning(f"Could not parse page count for {domain_name}: {response_text[:100]}")
                    return 1
            
        except Exception as e:
            logger.error(f"Error getting page count for {domain_name}: {str(e)}")
            return 0
    
    def _parse_cdx_response(self, response_text: str) -> Tuple[List[CDXRecord], int]:
        """Parse CDX API JSON response into CDXRecord objects with static asset pre-filtering"""
        if not response_text.strip():
            return [], 0
        
        try:
            import json
            response_data = json.loads(response_text)
            
            if not isinstance(response_data, list) or len(response_data) < 2:
                return [], 0
            
            # Skip header row if present
            data_rows = response_data[1:] if response_data[0][0] == "timestamp" else response_data
            
            # Parse all records first using the factory method for consistency
            raw_records = []
            for row in data_rows:
                if len(row) >= 6:
                    try:
                        raw_records.append(CDXRecord.from_wayback_response(row))
                    except ValueError as e:
                        logger.warning(f"Skipping invalid CDX record: {e}")
                        continue
            
            # Apply static asset pre-filtering before returning
            # This prevents static assets from ever creating database entries
            filtered_records, static_assets_filtered = StaticAssetFilter.filter_static_assets(raw_records)
            
            if static_assets_filtered > 0:
                logger.info(f"CDX parsing pre-filter eliminated {static_assets_filtered} static assets "
                           f"from {len(raw_records)} raw records")
            
            return filtered_records, static_assets_filtered
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse CDX JSON response: {e}")
            return [], 0
        except Exception as e:
            logger.error(f"Unexpected error parsing CDX response: {e}")
            return [], 0
    
    async def fetch_cdx_records_simple(self, domain_name: str, from_date: str, to_date: str,
                                     match_type: str = "domain", url_path: Optional[str] = None,
                                     page_size: int = None, max_pages: Optional[int] = None,
                                     include_attachments: bool = True) -> Tuple[List[CDXRecord], Dict[str, int]]:
        """
        Simplified CDX fetch method that matches the user's preferred approach.
        
        Uses clean CDX queries with digest collapse for efficient deduplication.
        Minimal post-processing since CDX API handles most filtering.
        
        Args:
            domain_name: Domain to query
            from_date: Start date (YYYYMMDD format)
            to_date: End date (YYYYMMDD format) 
            match_type: CDX match type (domain, prefix, exact)
            url_path: URL path for prefix matching
            page_size: Records per page (default: 5000)
            max_pages: Maximum pages to fetch
            include_attachments: Include PDF files
            
        Returns:
            Tuple of (records, stats)
        """
        if not page_size:
            page_size = 5000  # Default like user's example
            
        logger.info(f"Starting simple CDX fetch for {domain_name} from {from_date} to {to_date}")
        
        all_records = []
        stats = {
            "total_pages": 0,
            "fetched_pages": 0,
            "total_records": 0,
            "final_count": 0
        }
        
        # First, get total available pages
        try:
            # Build URL for page count check
            count_url = self._build_cdx_url_simple(
                domain_name, from_date, to_date, match_type, url_path,
                page_size=page_size, page_num=None, include_attachments=include_attachments
            )
            count_url += "&showNumPages=true"
            
            response_text = await self._make_request(count_url)
            
            try:
                total_pages = int(response_text.strip())
                stats["total_pages"] = total_pages
                logger.info(f"CDX query has {total_pages} pages available")
            except ValueError:
                # If we get data instead of page count, assume 1 page
                total_pages = 1 if response_text.strip() else 0
                stats["total_pages"] = total_pages
                
        except Exception as e:
            logger.error(f"Error getting page count: {e}")
            return [], stats
            
        if total_pages == 0:
            logger.warning(f"No CDX data found for {domain_name}")
            return [], stats
            
        # Determine how many pages to fetch
        pages_to_fetch = min(max_pages or total_pages, total_pages)
        logger.info(f"Fetching {pages_to_fetch} pages out of {total_pages} available")
        
        # Fetch pages
        for page_num in range(pages_to_fetch):
            try:
                url = self._build_cdx_url_simple(
                    domain_name, from_date, to_date, match_type, url_path,
                    page_size=page_size, page_num=page_num, include_attachments=include_attachments
                )
                
                logger.debug(f"Fetching CDX page {page_num + 1}/{pages_to_fetch}: {url}")
                
                response_text = await self._make_request(url)
                page_records, _ = self._parse_cdx_response(response_text)
                
                if page_records:
                    all_records.extend(page_records)
                    stats["fetched_pages"] += 1
                    logger.info(f"Page {page_num + 1}: Retrieved {len(page_records)} records")
                else:
                    logger.warning(f"Page {page_num + 1}: No records returned")
                
                # Be respectful to the CDX API
                if pages_to_fetch > 1:
                    await asyncio.sleep(0.5)
                    
            except Exception as e:
                logger.error(f"Error fetching CDX page {page_num + 1}: {e}")
                continue
        
        stats["total_records"] = len(all_records)
        stats["final_count"] = len(all_records)
        
        logger.info(f"Simple CDX fetch complete: {stats['total_records']} records from {stats['fetched_pages']} pages")
        
        return all_records, stats

    async def fetch_cdx_records(self, domain_name: str, from_date: str, to_date: str,
                              match_type: str = "domain", url_path: Optional[str] = None,
                              min_size: int = 1000, max_size: int = 10 * 1024 * 1024,
                              page_size: int = None, max_pages: Optional[int] = None,
                              existing_digests: Optional[Set[str]] = None,
                              filter_list_pages: bool = True,
                              use_resume_key: bool = True,
                              include_attachments: bool = True) -> Tuple[List[CDXRecord], Dict[str, int]]:
        """
        Fetch CDX records with comprehensive filtering.
        
        Returns:
            Tuple of (filtered_records, filter_stats)
        """
        if not page_size:
            page_size = self.DEFAULT_PAGE_SIZE
        
        # Get total pages available
        total_pages = await self.get_page_count(
            domain_name, from_date, to_date, match_type, url_path, min_size, include_attachments
        )
        
        # For very large domains (>50 pages), enable resume key support
        current_resume_key = None if not use_resume_key or total_pages <= 50 else ""
        
        if total_pages == 0:
            logger.warning(f"No CDX data found for {domain_name} from {from_date} to {to_date}")
            return [], {"total_pages": 0, "fetched_pages": 0}
        
        # Determine pages to fetch
        pages_to_fetch = min(max_pages or total_pages, total_pages)
        logger.info(f"Fetching {pages_to_fetch} CDX pages for {domain_name} (total: {total_pages})")
        
        all_records = []
        filter_stats = {
            "total_pages": total_pages,
            "fetched_pages": 0,
            "total_records": 0,
            "static_assets_filtered": 0,  # New metric for database savings
            "size_filtered": 0,
            "attachment_filtered": 0,
            "list_filtered": 0,
            "duplicate_filtered": 0,
            "final_count": 0
        }
        
        # Fetch pages sequentially with resume key support
        for page_num in range(pages_to_fetch):
            url = self._build_cdx_url(
                domain_name, from_date, to_date, match_type, url_path,
                min_size=min_size, max_size=max_size, page_size=page_size, 
                page_num=page_num, resume_key=current_resume_key if page_num == 0 else None,
                include_attachments=include_attachments
            )
            
            try:
                response_text = await self._make_request(url)
                page_records, page_static_assets_filtered = self._parse_cdx_response(response_text)
                all_records.extend(page_records)
                filter_stats["fetched_pages"] += 1
                filter_stats["static_assets_filtered"] += page_static_assets_filtered
                
                logger.debug(f"Fetched page {page_num + 1}/{pages_to_fetch}: {len(page_records)} records "
                           f"({page_static_assets_filtered} static assets pre-filtered)")
                
                # For large domains, add delay to be respectful
                if total_pages > 100:
                    await asyncio.sleep(0.5)
                
            except Exception as e:
                logger.error(f"Error fetching CDX page {page_num} for {domain_name}: {e}")
                continue
        
        filter_stats["total_records"] = len(all_records)
        
        # Apply filters
        filtered_records = all_records
        
        # 1. Size filtering
        filtered_records, size_filtered = ContentSizeFilter.filter_by_size(
            filtered_records, min_size, max_size
        )
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
        
        # Calculate database savings from static asset pre-filtering
        total_potential_db_entries = filter_stats['total_records'] + filter_stats['static_assets_filtered']
        if filter_stats['static_assets_filtered'] > 0:
            savings_percentage = (filter_stats['static_assets_filtered'] / total_potential_db_entries) * 100
            logger.info(
                f"Database optimization: Static asset pre-filtering prevented "
                f"{filter_stats['static_assets_filtered']} database entries "
                f"({savings_percentage:.1f}% reduction in potential DB bloat)"
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