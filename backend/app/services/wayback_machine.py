"""
Wayback Machine CDX API client with robust retry logic and filtering
"""
import asyncio
import re
import logging
import time
from datetime import datetime, timedelta
from typing import List, Dict, Tuple, Optional, Any, Set
from dataclasses import dataclass
from enum import Enum

import httpx
from tenacity import (
    retry, 
    stop_after_attempt, 
    wait_exponential,
    retry_if_exception_type,
    before_sleep_log
)

from ..core.config import settings
from ..models.scraping import CDXResumeState, CDXResumeStatus

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
    """CDX record data structure"""
    timestamp: str
    original_url: str
    mime_type: str
    status_code: str
    digest: str
    length: str
    
    @property
    def wayback_url(self) -> str:
        """Generate Wayback Machine URL"""
        return f"https://web.archive.org/web/{self.timestamp}/{self.original_url}"
    
    @property
    def content_url(self) -> str:
        """Generate raw content URL"""
        return f"https://web.archive.org/web/{self.timestamp}if_/{self.original_url}"
    
    @property
    def content_length_bytes(self) -> int:
        """Get content length as integer"""
        try:
            return int(self.length) if self.length and self.length.isdigit() else 0
        except (ValueError, AttributeError):
            return 0
    
    @property
    def capture_date(self) -> datetime:
        """Parse timestamp to datetime"""
        try:
            return datetime.strptime(self.timestamp, "%Y%m%d%H%M%S")
        except ValueError:
            # Fallback for shorter timestamps
            timestamp_padded = self.timestamp.ljust(14, '0')
            return datetime.strptime(timestamp_padded, "%Y%m%d%H%M%S")


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
        
        # Create HTTP client with connection pooling
        self.client = httpx.AsyncClient(
            timeout=httpx.Timeout(self.timeout),
            limits=httpx.Limits(max_keepalive_connections=10, max_connections=50),
            headers={
                'User-Agent': 'Mozilla/5.0 (compatible; ChronoScraper/2.0; +https://chronoscraper.com)'
            }
        )
        
        logger.info(f"Initialized CDX API client with {self.timeout}s timeout, {self.max_retries} max retries")
    
    async def __aenter__(self):
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.client.aclose()
    
    @retry(
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=2, min=5, max=60),
        retry=retry_if_exception_type((httpx.TimeoutException, httpx.ConnectError, CDXAPIException)),
        before_sleep=before_sleep_log(logger, logging.WARNING)
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
            
            # Handle server errors
            if response.status_code >= 500:
                raise CDXAPIException(f"Server error: {response.status_code}")
            
            # Handle client errors
            if response.status_code >= 400:
                logger.error(f"Client error {response.status_code}: {response.text}")
                raise CDXAPIException(f"Client error: {response.status_code}")
            
            return response.text
            
        except httpx.TimeoutException as e:
            logger.error(f"Timeout requesting CDX API: {url}")
            raise
        except httpx.ConnectError as e:
            logger.error(f"Connection error requesting CDX API: {url}")
            raise
    
    def _build_cdx_url(self, domain_name: str, from_date: str, to_date: str,
                      match_type: str = "domain", url_path: Optional[str] = None,
                      min_size: int = 1000, max_size: int = 10 * 1024 * 1024, 
                      page_size: int = None, page_num: Optional[int] = None, 
                      resume_key: Optional[str] = None, show_num_pages: bool = False,
                      include_attachments: bool = True) -> str:
        """Build CDX API URL with all parameters"""
        
        # Determine query URL and match type
        if match_type == "prefix" and url_path:
            query_url = url_path
            cdx_match_type = "prefix"
        else:
            query_url = domain_name
            cdx_match_type = "domain"
        
        logger.info(f"Building CDX URL: matchType={cdx_match_type}, query_url={query_url}")
        
        # Build mimetype filter based on attachment setting
        if include_attachments:
            mimetype_filter = 'mimetype:text/html|application/pdf'
            logger.info(f"Including PDF attachments for domain: {domain_name}")
        else:
            mimetype_filter = 'mimetype:text/html'
            logger.info(f"Excluding PDF attachments for domain: {domain_name}")
        
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
    
    def _parse_cdx_response(self, response_text: str) -> List[CDXRecord]:
        """Parse CDX API JSON response into CDXRecord objects"""
        if not response_text.strip():
            return []
        
        try:
            import json
            response_data = json.loads(response_text)
            
            if not isinstance(response_data, list) or len(response_data) < 2:
                return []
            
            # Skip header row if present
            data_rows = response_data[1:] if response_data[0][0] == "timestamp" else response_data
            
            records = []
            for row in data_rows:
                if len(row) >= 6:
                    records.append(CDXRecord(
                        timestamp=row[0],
                        original_url=row[1],
                        mime_type=row[2],
                        status_code=row[3],
                        digest=row[4],
                        length=row[5]
                    ))
            
            return records
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse CDX JSON response: {e}")
            return []
        except Exception as e:
            logger.error(f"Unexpected error parsing CDX response: {e}")
            return []
    
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
                page_records = self._parse_cdx_response(response_text)
                all_records.extend(page_records)
                filter_stats["fetched_pages"] += 1
                
                logger.debug(f"Fetched page {page_num + 1}/{pages_to_fetch}: {len(page_records)} records")
                
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
            f"(size: -{filter_stats['size_filtered']}, "
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
    """Fetch CDX pages - convenience function"""
    async with CDXAPIClient() as client:
        records, stats = await client.fetch_cdx_records(
            domain_name, from_date, to_date, match_type, url_path,
            min_size=min_size, max_pages=max_pages
        )
        return records