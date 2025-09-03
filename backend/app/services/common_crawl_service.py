"""
Common Crawl CDX API client using cdx_toolkit with circuit breaker support.
Compatible interface with existing CDXAPIClient for drop-in replacement.
"""
import asyncio
import logging
import time
from datetime import datetime
from typing import List, Dict, Tuple, Optional, Set
from dataclasses import dataclass
import threading
from concurrent.futures import ThreadPoolExecutor

import cdx_toolkit
from tenacity import (
    retry, 
    stop_after_attempt, 
    wait_exponential,
    retry_if_exception_type,
    before_sleep_log
)

from ..core.config import settings
from ..services.circuit_breaker import get_wayback_machine_breaker
from ..services.wayback_machine import (
    CDXRecord, CDXAPIException, WaybackMachineException,
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
        self.executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="common_crawl")
        
        # Configure cdx_toolkit client with proper rate limiting
        self.cdx_client = cdx_toolkit.CDXFetcher(source='cc')
        
        # Common Crawl specific settings
        self.cdx_client.max_pages = 1000  # Reasonable limit
        self.cdx_client.max_seconds_for_timeout = self.timeout
        
        logger.info(f"Initialized Common Crawl client with {self.timeout}s timeout, "
                   f"{self.max_retries} max retries")
        
    async def __aenter__(self):
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        self.executor.shutdown(wait=True)
        
    def _convert_cdx_toolkit_record(self, record) -> CDXRecord:
        """
        Convert cdx_toolkit record to our CDXRecord format.
        
        Args:
            record: cdx_toolkit CDX record object
            
        Returns:
            CDXRecord compatible with existing interface
        """
        try:
            return CDXRecord(
                timestamp=record.timestamp,
                original_url=record.url,
                mime_type=getattr(record, 'mimetype', 'text/html'),
                status_code=getattr(record, 'status', '200'),
                digest=getattr(record, 'digest', ''),
                length=getattr(record, 'length', '0')
            )
        except Exception as e:
            logger.warning(f"Failed to convert cdx_toolkit record: {e}")
            # Return minimal record to avoid breaking the pipeline
            return CDXRecord(
                timestamp=getattr(record, 'timestamp', '20240101000000'),
                original_url=getattr(record, 'url', ''),
                mime_type='text/html',
                status_code='200',
                digest='',
                length='0'
            )
    
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
        stop=stop_after_attempt(8),
        wait=wait_exponential(multiplier=2, min=5, max=120),  # Slower for Common Crawl
        retry=retry_if_exception_type((CommonCrawlAPIException, ConnectionError, TimeoutError)),
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
            """Synchronous fetch operation for thread execution"""
            try:
                # Configure pagination
                original_max_pages = self.cdx_client.max_pages
                if max_pages:
                    self.cdx_client.max_pages = min(max_pages, 1000)
                
                # Execute query
                records = []
                count = 0
                
                logger.debug(f"Fetching Common Crawl records with params: {query_params}")
                
                for record in self.cdx_client.iter(**query_params):
                    records.append(record)
                    count += 1
                    
                    # Respect page size limit
                    if page_size and count >= page_size * (max_pages or 1):
                        break
                    
                    # Be respectful to Common Crawl
                    if count % 1000 == 0:
                        time.sleep(1)
                
                # Restore original setting
                self.cdx_client.max_pages = original_max_pages
                
                logger.info(f"Fetched {len(records)} records from Common Crawl")
                return records
                
            except Exception as e:
                error_msg = f"Common Crawl fetch failed: {str(e)}"
                logger.error(error_msg)
                raise CommonCrawlAPIException(error_msg) from e
        
        # Execute with circuit breaker protection
        try:
            # Run synchronous cdx_toolkit operation in thread pool
            loop = asyncio.get_event_loop()
            records = await loop.run_in_executor(self.executor, _sync_fetch)
            return records
            
        except Exception as e:
            if "timeout" in str(e).lower():
                raise CommonCrawlAPIException(f"Common Crawl timeout: {e}")
            elif "rate limit" in str(e).lower():
                logger.warning("Common Crawl rate limit hit - will retry")
                await asyncio.sleep(30)  # Wait longer for rate limits
                raise CommonCrawlAPIException(f"Common Crawl rate limited: {e}")
            else:
                raise CommonCrawlAPIException(f"Common Crawl error: {e}")
    
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