"""
Common Crawl CDX API client using cdx_toolkit with circuit breaker support.
Compatible interface with existing CDXAPIClient for drop-in replacement.
"""
import asyncio
import logging
import time
import random
import gzip
import io
from typing import List, Dict, Tuple, Optional, Set
from concurrent.futures import ThreadPoolExecutor

import cdx_toolkit
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from tenacity import (
    retry, 
    stop_after_attempt, 
    wait_exponential,
    retry_if_exception_type,
    before_sleep_log
)
from urllib3.exceptions import MaxRetryError, NewConnectionError
from requests.exceptions import ConnectionError, RequestException

from ..core.config import settings
from ..services.circuit_breaker import get_wayback_machine_breaker
from ..services.wayback_machine import (
    CDXRecord, WaybackMachineException,
    ListPageFilter, ContentSizeFilter, StaticAssetFilter, 
    AttachmentFilter, DuplicateFilter
)

logger = logging.getLogger(__name__)


class CommonCrawlException(WaybackMachineException):
    """Base exception for Common Crawl API errors"""
    pass


class CommonCrawlAPIException(CommonCrawlException):
    """Common Crawl API specific exceptions"""
    pass


class CommonCrawlService:
    """
    Common Crawl CDX API client using cdx_toolkit with interface compatibility
    to CDXAPIClient from wayback_machine.py
    """
    
    DEFAULT_TIMEOUT = 180  # seconds - longer for Common Crawl
    DEFAULT_MAX_RETRIES = 5
    DEFAULT_PAGE_SIZE = 5000
    
    def __init__(self):
        self.timeout = settings.WAYBACK_MACHINE_TIMEOUT or self.DEFAULT_TIMEOUT
        self.max_retries = settings.WAYBACK_MACHINE_MAX_RETRIES or self.DEFAULT_MAX_RETRIES
        
        # Use existing circuit breaker with Common Crawl specific config
        self.circuit_breaker = get_wayback_machine_breaker()
        
        # Thread pool for executing synchronous cdx_toolkit operations
        self.executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="common_crawl")
        
        # Configure robust HTTP session for cdx_toolkit
        self._setup_robust_http_session()
        
        # Configure cdx_toolkit client with proper rate limiting
        self.cdx_client = cdx_toolkit.CDXFetcher(source='cc')
        self.cdx_client.session = self.http_session  # Use our robust session
        
        # Common Crawl specific settings with conservative limits
        self.cdx_client.max_pages = 500  # More conservative limit
        self.cdx_client.max_seconds_for_timeout = self.timeout
        
        logger.info(f"Initialized Common Crawl client with {self.timeout}s timeout, "
                   f"{self.max_retries} max retries, robust connection handling")
    
    def _setup_robust_http_session(self):
        """Set up HTTP session with SmartProxy integration (verified working method)"""
        self.http_session = requests.Session()
        
        # Validate SmartProxy configuration
        if not all([settings.PROXY_SERVER, settings.PROXY_USERNAME, settings.PROXY_PASSWORD]):
            raise CommonCrawlException(
                "SmartProxy credentials not configured. Please set PROXY_SERVER, PROXY_USERNAME, and PROXY_PASSWORD"
            )
        
        # Configure retry strategy for proxy connections
        retry_strategy = Retry(
            total=3,  # Fewer retries with proxy
            status_forcelist=[429, 500, 502, 503, 504, 407],  # Include proxy auth errors
            backoff_factor=3,  # Longer backoff with proxy
            respect_retry_after_header=True,
            raise_on_status=False
        )
        
        # Configure HTTP adapter
        adapter = HTTPAdapter(
            max_retries=retry_strategy,
            pool_connections=5,  # Smaller pool for proxy
            pool_maxsize=10,
            pool_block=True
        )
        
        self.http_session.mount("http://", adapter)
        self.http_session.mount("https://", adapter)
        
        # Configure SmartProxy (verified working method from tests)
        proxy_url = f"http://{settings.PROXY_USERNAME}:{settings.PROXY_PASSWORD}@{settings.PROXY_SERVER.replace('http://', '')}"
        
        self.http_session.proxies = {
            'http': proxy_url,
            'https': proxy_url
        }
        
        # Set headers for Common Crawl (verified working configuration)
        self.http_session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'application/json,text/plain,*/*',
            'Accept-Encoding': 'gzip, deflate, br',
            'Accept-Language': 'en-US,en;q=0.9',
            'Connection': 'keep-alive',
            'Cache-Control': 'no-cache',
            'Pragma': 'no-cache'
        })
        
        logger.info(f"Configured SmartProxy session: {settings.PROXY_SERVER}")
    
    async def fetch_html_content(self, record) -> Optional[str]:
        """
        Fetch actual HTML content for a CDX record using SmartProxy (verified working method).
        This method retrieves the actual HTML content from Common Crawl's S3 WARC files.
        
        Args:
            record: CDX record containing filename, offset, and length
            
        Returns:
            HTML content string or None if failed
        """
        try:
            # Use existing SmartProxy session (already configured)
            # Check if record has required fields
            if not hasattr(record, 'filename') or not hasattr(record, 'offset') or not hasattr(record, 'length'):
                logger.debug("Record missing required fields for HTML retrieval")
                return None
                
            s3_url = f"https://data.commoncrawl.org/{record.filename}"
            offset = int(record.offset)
            length = int(record.length)
            
            headers = {'Range': f'bytes={offset}-{offset+length-1}'}
            
            # Add small delay to be respectful
            await asyncio.sleep(random.uniform(0.5, 2.0))
            
            # Fetch WARC data using SmartProxy session
            def _sync_fetch_html():
                response = self.http_session.get(s3_url, headers=headers, timeout=30)
                return response
            
            # Execute in thread pool to avoid blocking
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(self.executor, _sync_fetch_html)
            
            if response.status_code in [200, 206]:
                # Extract HTML from WARC
                warc_data = response.content
                
                # Try to decompress if gzipped
                try:
                    with gzip.GzipFile(fileobj=io.BytesIO(warc_data)) as gz:
                        decompressed = gz.read()
                except:
                    decompressed = warc_data
                
                # Convert to string and find HTML
                content_str = decompressed.decode('utf-8', errors='ignore')
                
                # Find HTML start (multiple patterns)
                html_start = content_str.find('<!DOCTYPE')
                if html_start == -1:
                    html_start = content_str.find('<!doctype')
                if html_start == -1:
                    html_start = content_str.find('<html')
                if html_start == -1:
                    html_start = content_str.find('<HTML')
                
                if html_start != -1:
                    html_content = content_str[html_start:]
                    
                    # Find HTML end
                    html_end = html_content.find('</html>')
                    if html_end == -1:
                        html_end = html_content.find('</HTML>')
                    
                    if html_end != -1:
                        html_content = html_content[:html_end + 7]
                    
                    logger.debug(f"Successfully extracted HTML content ({len(html_content)} chars)")
                    return html_content
                else:
                    logger.debug("No HTML start tag found in WARC content")
            else:
                logger.debug(f"Failed to fetch WARC data: HTTP {response.status_code}")
                
            return None
            
        except Exception as e:
            logger.debug(f"Failed to fetch HTML via SmartProxy: {e}")
            return None
        
    async def __aenter__(self):
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        try:
            self.http_session.close()
        except Exception as e:
            logger.warning(f"Error closing HTTP session: {e}")
        self.executor.shutdown(wait=True)
        
    def _convert_cdx_toolkit_record(self, record) -> CDXRecord:
        """
        Convert cdx_toolkit record to our CDXRecord format.
        
        Args:
            record: cdx_toolkit CaptureObject or similar record
            
        Returns:
            CDXRecord compatible with existing interface
        """
        try:
            # cdx_toolkit CaptureObject uses different attribute names
            # timestamp -> ts, other attributes may vary
            timestamp = getattr(record, 'ts', None) or getattr(record, 'timestamp', '20240101000000')
            original_url = getattr(record, 'url', getattr(record, 'original', ''))
            
            return CDXRecord(
                timestamp=timestamp,
                original_url=original_url,
                mime_type=getattr(record, 'mimetype', 'text/html'),
                status_code=str(getattr(record, 'status', '200')),
                digest=getattr(record, 'digest', ''),
                length=str(getattr(record, 'length', '0'))
            )
        except Exception as e:
            logger.debug(f"Skipped invalid cdx_toolkit record: {e}")
            # Return None instead of broken record
            return None
    
    def _build_common_crawl_query(self, domain_name: str, from_date: str, to_date: str,
                                match_type: str = "domain", url_path: Optional[str] = None,
                                include_attachments: bool = True) -> Dict:
        """
        Build Common Crawl query parameters.
        
        Args:
            domain_name: Domain to query
            from_date: Start date (YYYYMMDD format)
            to_date: End date (YYYYMMDD format) 
            match_type: Match type (domain, prefix, exact)
            url_path: URL path for prefix matching
            include_attachments: Include PDF files
            
        Returns:
            Query parameters dict for cdx_toolkit
        """
        # Determine query URL based on match type
        if domain_name.startswith(('http://', 'https://')):
            query_url = domain_name
            cdx_match_type = "prefix"
        elif match_type == "prefix" and url_path:
            query_url = url_path
            cdx_match_type = "prefix"
        elif match_type in ["exact", "prefix"]:
            query_url = domain_name
            cdx_match_type = match_type
        else:
            # Domain matching - use wildcard pattern
            query_url = f"*.{domain_name}/*"
            cdx_match_type = "glob"
        
        # Build MIME type filter
        if include_attachments:
            mime_filter = ['text/html', 'application/pdf']
        else:
            mime_filter = ['text/html']
        
        query_params = {
            'url': query_url,
            'from_ts': from_date,
            'to_ts': to_date,
            'match_type': cdx_match_type,
            'mime': mime_filter,
            'status': 200,  # Only successful responses
            'collapse': 'digest',  # Deduplicate by content hash
        }
        
        logger.info(f"Built Common Crawl query: {query_params}")
        return query_params
    
    @retry(
        stop=stop_after_attempt(5),  # Fewer total attempts
        wait=wait_exponential(multiplier=3, min=10, max=300),  # Longer backoff for Common Crawl
        retry=retry_if_exception_type((
            CommonCrawlAPIException, 
            ConnectionError, 
            TimeoutError,
            MaxRetryError,
            NewConnectionError,
            RequestException
        )),
        before_sleep=before_sleep_log(logger, logging.INFO)
    )
    async def _fetch_records_with_retry(self, query_params: Dict, page_size: int,
                                      max_pages: Optional[int] = None) -> List:
        """
        Fetch records from Common Crawl with retry logic and circuit breaker protection.
        
        Args:
            query_params: Query parameters for cdx_toolkit
            page_size: Records per page
            max_pages: Maximum pages to fetch
            
        Returns:
            List of cdx_toolkit records
            
        Raises:
            CommonCrawlAPIException: On API errors
        """
        def _sync_fetch():
            """Synchronous fetch operation for thread execution using SmartProxy (verified working method)"""
            try:
                # Configure pagination with conservative limits
                original_max_pages = self.cdx_client.max_pages
                if max_pages:
                    self.cdx_client.max_pages = min(max_pages, 150)  # Conservative limit with proxy
                
                # Execute query with rate limiting (verified working delays)
                records = []
                count = 0
                
                logger.debug(f"Fetching Common Crawl records via SmartProxy: {query_params}")
                
                # Add initial delay to prevent immediate rate limiting (verified working)
                time.sleep(random.uniform(8, 15))  # 8-15s initial delay like in tests
                
                try:
                    for record in self.cdx_client.iter(**query_params):
                        records.append(record)
                        count += 1
                        
                        # Respect page size limit
                        if page_size and count >= page_size * (max_pages or 1):
                            break
                        
                        # Respectful delays with SmartProxy (verified working pattern)
                        if count % 100 == 0:
                            time.sleep(random.uniform(15, 25))  # 15-25s every 100 records
                        elif count % 25 == 0:
                            time.sleep(random.uniform(5, 10))   # 5-10s every 25 records
                        elif count % 5 == 0:
                            time.sleep(random.uniform(1, 3))    # 1-3s every 5 records
                            
                except (ConnectionError, TimeoutError, MaxRetryError, NewConnectionError) as conn_err:
                    logger.warning(f"Connection error during CDX iteration: {conn_err}")
                    if records:  # Return partial results if we got some data
                        logger.info(f"Returning {len(records)} partial records due to connection error")
                    else:
                        raise CommonCrawlAPIException(f"Connection failed: {conn_err}") from conn_err
                
                # Restore original setting
                self.cdx_client.max_pages = original_max_pages
                
                logger.info(f"Fetched {len(records)} records from Common Crawl")
                return records
                
            except Exception as e:
                # Enhanced error classification for SmartProxy + Common Crawl
                error_str = str(e).lower()
                if 'remote end closed connection' in error_str or 'connection aborted' in error_str:
                    raise CommonCrawlAPIException(f"Common Crawl connection closed unexpectedly: {e}") from e
                elif 'timeout' in error_str:
                    raise CommonCrawlAPIException(f"Common Crawl request timeout: {e}") from e
                elif 'rate limit' in error_str or '429' in error_str:
                    raise CommonCrawlAPIException(f"Common Crawl rate limit exceeded: {e}") from e
                elif '407' in error_str or 'proxy authentication' in error_str:
                    raise CommonCrawlAPIException(f"SmartProxy authentication failed: {e}") from e
                elif 'proxy' in error_str and ('error' in error_str or 'failed' in error_str):
                    raise CommonCrawlAPIException(f"SmartProxy connection error: {e}") from e
                else:
                    error_msg = f"Common Crawl fetch failed via SmartProxy: {str(e)}"
                    logger.error(error_msg)
                    raise CommonCrawlAPIException(error_msg) from e
        
        # Execute with circuit breaker protection
        try:
            # Run synchronous cdx_toolkit operation in thread pool
            loop = asyncio.get_event_loop()
            records = await loop.run_in_executor(self.executor, _sync_fetch)
            return records
            
        except Exception as e:
            error_str = str(e).lower()
            if "timeout" in error_str:
                raise CommonCrawlAPIException(f"Common Crawl timeout via SmartProxy: {e}")
            elif "rate limit" in error_str or "429" in error_str:
                logger.warning("Common Crawl rate limit hit via SmartProxy - will retry with longer backoff")
                await asyncio.sleep(180)  # Wait longer for rate limits with proxy
                raise CommonCrawlAPIException(f"Common Crawl rate limited via SmartProxy: {e}")
            elif "407" in error_str or "proxy authentication" in error_str:
                logger.error("SmartProxy authentication failed - check credentials")
                raise CommonCrawlAPIException(f"SmartProxy authentication error: {e}")
            elif "connection" in error_str and "closed" in error_str:
                logger.warning("Common Crawl connection closed via SmartProxy - will retry")
                await asyncio.sleep(15)  # Longer delay for proxy connection issues
                raise CommonCrawlAPIException(f"Common Crawl connection closed via SmartProxy: {e}")
            elif "proxy" in error_str and ("error" in error_str or "failed" in error_str):
                logger.warning("SmartProxy connection error - will retry")
                await asyncio.sleep(20)  # Delay for proxy issues
                raise CommonCrawlAPIException(f"SmartProxy connection error: {e}")
            else:
                raise CommonCrawlAPIException(f"Common Crawl error via SmartProxy: {e}")
    
    async def get_page_count(self, domain_name: str, from_date: str, to_date: str,
                           match_type: str = "domain", url_path: Optional[str] = None,
                           min_size: int = 1000, include_attachments: bool = True) -> int:
        """
        Get estimated number of CDX pages available for a query.
        Note: Common Crawl doesn't provide exact page counts, so this is an estimate.
        
        Returns:
            Estimated number of pages available, or 0 if query fails
        """
        try:
            query_params = self._build_common_crawl_query(
                domain_name, from_date, to_date, match_type, url_path, include_attachments
            )
            
            # Fetch small sample to estimate total
            sample_records = await self._fetch_records_with_retry(
                query_params, page_size=100, max_pages=1
            )
            
            if not sample_records:
                return 0
            
            # Rough estimate: assume full pages if we got 100 records in first page
            estimated_pages = max(1, len(sample_records) // 100)
            if len(sample_records) >= 100:
                estimated_pages = 10  # Conservative estimate for domains with data
            
            logger.info(f"Common Crawl estimated {estimated_pages} pages for {domain_name}")
            return estimated_pages
            
        except Exception as e:
            logger.error(f"Error estimating Common Crawl page count for {domain_name}: {e}")
            return 0
    
    async def fetch_cdx_records_simple(self, domain_name: str, from_date: str, to_date: str,
                                     match_type: str = "domain", url_path: Optional[str] = None,
                                     page_size: int = None, max_pages: Optional[int] = None,
                                     include_attachments: bool = True) -> Tuple[List[CDXRecord], Dict[str, int]]:
        """
        Simplified CDX fetch method compatible with wayback_machine.py interface.
        
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
            page_size = self.DEFAULT_PAGE_SIZE
            
        logger.info(f"Starting Common Crawl fetch for {domain_name} from {from_date} to {to_date}")
        
        stats = {
            "total_pages": 0,
            "fetched_pages": 0,
            "total_records": 0,
            "final_count": 0
        }
        
        try:
            # Build query parameters
            query_params = self._build_common_crawl_query(
                domain_name, from_date, to_date, match_type, url_path, include_attachments
            )
            
            # Fetch raw records from Common Crawl
            raw_records = await self._fetch_records_with_retry(
                query_params, page_size, max_pages
            )
            
            if not raw_records:
                logger.warning(f"No Common Crawl data found for {domain_name}")
                return [], stats
            
            # Convert to CDXRecord format
            converted_records = []
            for record in raw_records:
                try:
                    cdx_record = self._convert_cdx_toolkit_record(record)
                    if cdx_record is not None:  # Handle None returns from conversion
                        converted_records.append(cdx_record)
                except Exception as e:
                    logger.debug(f"Skipped invalid record: {e}")
                    continue
            
            # Apply static asset pre-filtering
            filtered_records, static_assets_filtered = StaticAssetFilter.filter_static_assets(
                converted_records
            )
            
            stats.update({
                "total_pages": 1,  # Common Crawl doesn't use pagination like Wayback
                "fetched_pages": 1,
                "total_records": len(converted_records),
                "final_count": len(filtered_records)
            })
            
            logger.info(f"Common Crawl fetch complete: {len(filtered_records)} records "
                       f"({static_assets_filtered} static assets filtered)")
            
            return filtered_records, stats
            
        except Exception as e:
            logger.error(f"Common Crawl fetch failed for {domain_name}: {e}")
            return [], stats
    
    async def fetch_cdx_records(self, domain_name: str, from_date: str, to_date: str,
                              match_type: str = "domain", url_path: Optional[str] = None,
                              min_size: int = 1000, max_size: int = 10 * 1024 * 1024,
                              page_size: int = None, max_pages: Optional[int] = None,
                              existing_digests: Optional[Set[str]] = None,
                              filter_list_pages: bool = True,
                              use_resume_key: bool = False,  # Not supported by Common Crawl
                              include_attachments: bool = True) -> Tuple[List[CDXRecord], Dict[str, int]]:
        """
        Fetch CDX records with comprehensive filtering (full compatibility method).
        
        Returns:
            Tuple of (filtered_records, filter_stats)
        """
        if not page_size:
            page_size = self.DEFAULT_PAGE_SIZE
        
        logger.info(f"Fetching Common Crawl records for {domain_name} with full filtering")
        
        # Get simple records first
        all_records, basic_stats = await self.fetch_cdx_records_simple(
            domain_name, from_date, to_date, match_type, url_path, 
            page_size, max_pages, include_attachments
        )
        
        filter_stats = {
            "total_pages": basic_stats["total_pages"],
            "fetched_pages": basic_stats["fetched_pages"], 
            "total_records": basic_stats["total_records"],
            "static_assets_filtered": basic_stats["total_records"] - basic_stats["final_count"],
            "size_filtered": 0,
            "attachment_filtered": 0,
            "list_filtered": 0,
            "duplicate_filtered": 0,
            "final_count": 0
        }
        
        if not all_records:
            return [], filter_stats
        
        # Apply additional filters (same as wayback_machine.py)
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
            f"Common Crawl filtering complete for {domain_name}: "
            f"{filter_stats['total_records']} total -> {filter_stats['final_count']} final "
            f"(static: -{filter_stats['static_assets_filtered']}, "
            f"size: -{filter_stats['size_filtered']}, "
            f"list: -{filter_stats['list_filtered']}, "
            f"duplicates: -{filter_stats['duplicate_filtered']})"
        )
        
        return filtered_records, filter_stats


# Convenience functions for backward compatibility
async def get_common_crawl_page_count(domain_name: str, from_date: str, to_date: str,
                                    match_type: str = "domain", url_path: Optional[str] = None,
                                    min_size: int = 200) -> int:
    """Get Common Crawl page count estimate - convenience function"""
    async with CommonCrawlService() as client:
        return await client.get_page_count(domain_name, from_date, to_date, match_type, url_path, min_size)


async def fetch_common_crawl_pages(domain_name: str, from_date: str, to_date: str,
                                 match_type: str = "domain", url_path: Optional[str] = None,
                                 min_size: int = 200, max_pages: Optional[int] = None) -> List[CDXRecord]:
    """Fetch Common Crawl pages - convenience function (uses full filtering method)"""
    async with CommonCrawlService() as client:
        records, stats = await client.fetch_cdx_records(
            domain_name, from_date, to_date, match_type, url_path,
            min_size=min_size, max_pages=max_pages
        )
        return records


async def fetch_common_crawl_pages_simple(domain_name: str, from_date: str, to_date: str,
                                        match_type: str = "domain", url_path: Optional[str] = None,
                                        max_pages: Optional[int] = None, 
                                        include_attachments: bool = True) -> List[CDXRecord]:
    """
    Fetch Common Crawl pages using simplified approach (RECOMMENDED)
    
    Args:
        domain_name: Domain to query (e.g., 'example.com')
        from_date: Start date in YYYYMMDD format (e.g., '20200101')
        to_date: End date in YYYYMMDD format (e.g., '20250902')
        match_type: Match type - 'domain', 'prefix', or 'exact'
        url_path: URL path for prefix matching
        max_pages: Maximum pages to fetch (None = all available)
        include_attachments: Include PDF files in results
        
    Returns:
        List of CDXRecord objects
    """
    async with CommonCrawlService() as client:
        records, stats = await client.fetch_cdx_records_simple(
            domain_name, from_date, to_date, match_type, url_path,
            max_pages=max_pages, include_attachments=include_attachments
        )
        return records


# Circuit breaker integration for Common Crawl
def get_common_crawl_breaker():
    """Get circuit breaker for Common Crawl with appropriate settings"""
    from ..services.circuit_breaker import CircuitBreakerConfig, circuit_registry
    
    config = CircuitBreakerConfig(
        failure_threshold=5,
        success_threshold=3,
        timeout_seconds=120,  # Longer timeout for Common Crawl
        max_timeout_seconds=900,  # 15 minutes max
        exponential_backoff=True,
        sliding_window_size=10
    )
    return circuit_registry.get_breaker("common_crawl", config)


# Export public interface compatible with wayback_machine.py
__all__ = [
    'CommonCrawlService',
    'CommonCrawlException', 
    'CommonCrawlAPIException',
    'get_common_crawl_page_count',
    'fetch_common_crawl_pages',
    'fetch_common_crawl_pages_simple',
    'get_common_crawl_breaker'
]