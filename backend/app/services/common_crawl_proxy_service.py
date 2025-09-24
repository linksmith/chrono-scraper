"""
Proxy-enabled Common Crawl CDX API client for overcoming IP blocks.
This service rotates through proxy servers to avoid 24-hour IP bans from Common Crawl.
"""
import asyncio
import logging
import time
import random
from typing import List, Dict, Tuple, Optional
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
from requests.exceptions import ConnectionError, RequestException, ProxyError

from ..core.config import settings
from ..services.circuit_breaker import get_wayback_machine_breaker
from ..services.wayback_machine import (
    CDXRecord, WaybackMachineException, StaticAssetFilter
)

logger = logging.getLogger(__name__)


class ProxyRotationException(WaybackMachineException):
    """Exception for proxy rotation issues"""
    pass


class CommonCrawlProxyService:
    """
    Proxy-enabled Common Crawl CDX API client that rotates through proxy servers
    to avoid IP blocking while maintaining the same interface as CommonCrawlService.
    """
    
    DEFAULT_TIMEOUT = 300  # Longer timeout for proxy connections
    DEFAULT_MAX_RETRIES = 3
    DEFAULT_PAGE_SIZE = 2000  # Smaller batches with proxy
    
    # Sample proxy list - replace with your proxy service
    PROXY_LIST = [
        # Free proxy examples (not recommended for production)
        # {'http': 'http://proxy1:port', 'https': 'https://proxy1:port'},
        # {'http': 'http://proxy2:port', 'https': 'https://proxy2:port'},
        
        # For production, use a proxy service like:
        # Infatica, Bright Data, Webshare, etc.
        # Format: {'http': 'http://user:pass@proxy:port', 'https': 'https://user:pass@proxy:port'}
    ]
    
    def __init__(self, proxy_list: Optional[List[Dict[str, str]]] = None):
        self.timeout = settings.WAYBACK_MACHINE_TIMEOUT or self.DEFAULT_TIMEOUT
        self.max_retries = settings.WAYBACK_MACHINE_MAX_RETRIES or self.DEFAULT_MAX_RETRIES
        
        # Proxy configuration
        self.proxy_list = proxy_list or self._build_proxies_from_settings() or self.PROXY_LIST
        self.current_proxy_index = 0
        self.failed_proxies = set()  # Track failed proxies
        
        # Use existing circuit breaker
        self.circuit_breaker = get_wayback_machine_breaker()
        
        # Thread pool for executing synchronous cdx_toolkit operations
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="cc_proxy")
        
        # Configure HTTP session with proxy support
        self._setup_proxy_session()
        
        logger.info(f"Initialized CommonCrawlProxyService with {len(self.proxy_list)} proxies, "
                   f"{self.timeout}s timeout, {self.max_retries} max retries")
    
    def _setup_proxy_session(self):
        """Set up HTTP session with proxy rotation capabilities"""
        self.http_session = requests.Session()
        
        # Configure retry strategy for proxy connections
        retry_strategy = Retry(
            total=3,  # Fewer retries with proxy
            status_forcelist=[429, 500, 502, 503, 504],
            backoff_factor=2,
            respect_retry_after_header=True,
            raise_on_status=False
        )
        
        # Configure HTTP adapter
        adapter = HTTPAdapter(
            max_retries=retry_strategy,
            pool_connections=5,   # Smaller pool for proxy
            pool_maxsize=10,
            pool_block=True
        )
        
        self.http_session.mount("http://", adapter)
        self.http_session.mount("https://", adapter)
        
        # Set headers
        self.http_session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'application/json',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive'
        })
        
        # Set initial proxy
        self._rotate_proxy()
        
        logger.info("Configured HTTP session with proxy support")

    def _build_proxies_from_settings(self) -> List[Dict[str, str]]:
        """Build a basic rotating proxy list from configured credentials if available"""
        proxies: List[Dict[str, str]] = []
        try:
            # Prefer DECODO (Smartproxy) credentials if present
            if settings.DECODO_USERNAME and settings.DECODO_PASSWORD and settings.DECODO_ENDPOINT:
                host = settings.DECODO_ENDPOINT
                port = settings.DECODO_PORT_RESIDENTIAL or 10001
                user = settings.DECODO_USERNAME
                pwd = settings.DECODO_PASSWORD
                proxy_url = f"http://{user}:{pwd}@{host}:{port}"
                proxies.append({'http': proxy_url, 'https': proxy_url})
            # Fallback to generic proxy server credentials
            elif settings.PROXY_SERVER and settings.PROXY_USERNAME and settings.PROXY_PASSWORD:
                server = settings.PROXY_SERVER
                if not server.startswith('http'):
                    server = f"http://{server}"
                # Normalize to host:port
                server_host = server.replace('http://','').replace('https://','')
                proxy_url = f"http://{settings.PROXY_USERNAME}:{settings.PROXY_PASSWORD}@{server_host}"
                proxies.append({'http': proxy_url, 'https': proxy_url})
        except Exception as e:
            logger.warning(f"Failed to build proxies from settings: {e}")
        return proxies
    
    def _rotate_proxy(self) -> bool:
        """
        Rotate to the next available proxy.
        
        Returns:
            True if a proxy was set, False if no proxies available
        """
        if not self.proxy_list:
            logger.warning("No proxy list provided - using direct connection")
            return False
        
        available_proxies = [
            (i, proxy) for i, proxy in enumerate(self.proxy_list) 
            if i not in self.failed_proxies
        ]
        
        if not available_proxies:
            logger.error("All proxies have failed - resetting failed proxy list")
            self.failed_proxies.clear()
            available_proxies = [(i, proxy) for i, proxy in enumerate(self.proxy_list)]
        
        # Select random proxy from available ones
        self.current_proxy_index, current_proxy = random.choice(available_proxies)
        self.http_session.proxies.update(current_proxy)
        
        logger.info(f"Rotated to proxy {self.current_proxy_index + 1}/{len(self.proxy_list)}")
        return True
    
    def _mark_proxy_failed(self):
        """Mark current proxy as failed and rotate to next one"""
        self.failed_proxies.add(self.current_proxy_index)
        logger.warning(f"Marked proxy {self.current_proxy_index + 1} as failed")
        self._rotate_proxy()
    
    def _configure_cdx_client(self):
        """Configure cdx_toolkit client with current proxy session"""
        self.cdx_client = cdx_toolkit.CDXFetcher(source='cc')
        self.cdx_client.session = self.http_session  # Use proxy session
        self.cdx_client.max_pages = 200  # Conservative with proxy
        self.cdx_client.max_seconds_for_timeout = self.timeout
    
    @retry(
        stop=stop_after_attempt(3),  # Fewer attempts with proxy rotation
        wait=wait_exponential(multiplier=5, min=30, max=600),  # Longer backoff
        retry=retry_if_exception_type((
            ProxyRotationException,
            ConnectionError, 
            TimeoutError,
            MaxRetryError,
            NewConnectionError,
            RequestException
        )),
        before_sleep=before_sleep_log(logger, logging.INFO)
    )
    async def _fetch_records_with_proxy_retry(self, query_params: Dict, page_size: int,
                                            max_pages: Optional[int] = None) -> List:
        """
        Fetch records with proxy rotation and retry logic.
        """
        def _sync_fetch_with_proxy():
            try:
                # Configure client with current proxy
                self._configure_cdx_client()
                
                # Set pagination limits
                original_max_pages = self.cdx_client.max_pages
                if max_pages:
                    self.cdx_client.max_pages = min(max_pages, 200)
                
                records = []
                count = 0
                
                logger.debug(f"Fetching with proxy {self.current_proxy_index + 1}: {query_params}")
                
                # Add delay to prevent immediate blocking
                time.sleep(random.uniform(5, 15))  # Random delay 5-15s
                
                try:
                    for record in self.cdx_client.iter(**query_params):
                        records.append(record)
                        count += 1
                        
                        if page_size and count >= page_size * (max_pages or 1):
                            break
                        
                        # Respectful delays with randomization
                        if count % 50 == 0:
                            time.sleep(random.uniform(10, 20))  # 10-20s every 50 records
                        elif count % 10 == 0:
                            time.sleep(random.uniform(2, 5))   # 2-5s every 10 records
                            
                except (ConnectionError, TimeoutError, ProxyError) as conn_err:
                    logger.warning(f"Connection error with proxy: {conn_err}")
                    self._mark_proxy_failed()
                    if records:
                        logger.info(f"Returning {len(records)} partial records")
                    else:
                        raise ProxyRotationException(f"Proxy connection failed: {conn_err}") from conn_err
                
                # Restore settings
                self.cdx_client.max_pages = original_max_pages
                
                logger.info(f"Fetched {len(records)} records via proxy")
                return records
                
            except Exception as e:
                error_str = str(e).lower()
                if any(keyword in error_str for keyword in ['proxy', 'connection', 'timeout']):
                    self._mark_proxy_failed()
                    raise ProxyRotationException(f"Proxy error: {e}") from e
                else:
                    raise ProxyRotationException(f"Fetch error: {e}") from e
        
        # Execute with circuit breaker protection
        try:
            loop = asyncio.get_event_loop()
            records = await loop.run_in_executor(self.executor, _sync_fetch_with_proxy)
            return records
            
        except Exception as e:
            error_str = str(e).lower()
            if "rate limit" in error_str or "429" in error_str:
                logger.warning("Rate limit detected - rotating proxy and retrying")
                self._rotate_proxy()
                await asyncio.sleep(120)  # Wait 2 minutes for rate limit
                raise ProxyRotationException(f"Rate limited: {e}")
            elif "blocked" in error_str or "403" in error_str:
                logger.warning("IP blocked detected - rotating proxy")
                self._rotate_proxy()
                raise ProxyRotationException(f"IP blocked: {e}")
            else:
                raise ProxyRotationException(f"Proxy fetch error: {e}")
    
    async def fetch_cdx_records_simple(self, domain_name: str, from_date: str, to_date: str,
                                     match_type: str = "domain", url_path: Optional[str] = None,
                                     page_size: int = None, max_pages: Optional[int] = None,
                                     include_attachments: bool = True) -> Tuple[List[CDXRecord], Dict[str, int]]:
        """
        Simplified CDX fetch method with proxy rotation support.
        Compatible interface with CommonCrawlService.
        """
        if not page_size:
            page_size = self.DEFAULT_PAGE_SIZE
            
        logger.info(f"Starting proxy Common Crawl fetch for {domain_name}")
        
        stats = {
            "total_pages": 0,
            "fetched_pages": 0,
            "total_records": 0,
            "final_count": 0
        }
        
        try:
            # Build query parameters (reuse logic from CommonCrawlService)
            from .common_crawl_service import CommonCrawlService
            temp_service = CommonCrawlService()
            query_params = temp_service._build_common_crawl_query(
                domain_name, from_date, to_date, match_type, url_path, include_attachments
            )
            
            # Fetch with proxy rotation
            raw_records = await self._fetch_records_with_proxy_retry(
                query_params, page_size, max_pages
            )
            
            if not raw_records:
                logger.warning(f"No proxy Common Crawl data found for {domain_name}")
                return [], stats
            
            # Convert records (reuse conversion logic)
            converted_records = []
            for record in raw_records:
                try:
                    cdx_record = temp_service._convert_cdx_toolkit_record(record)
                    converted_records.append(cdx_record)
                except Exception as e:
                    logger.debug(f"Skipped invalid record: {e}")
                    continue
            
            # Apply filtering
            filtered_records, static_assets_filtered = StaticAssetFilter.filter_static_assets(
                converted_records
            )
            
            stats.update({
                "total_pages": 1,
                "fetched_pages": 1,
                "total_records": len(converted_records),
                "final_count": len(filtered_records)
            })
            
            logger.info(f"Proxy Common Crawl fetch complete: {len(filtered_records)} records "
                       f"({static_assets_filtered} static assets filtered)")
            
            return filtered_records, stats
            
        except Exception as e:
            logger.error(f"Proxy Common Crawl fetch failed for {domain_name}: {e}")
            return [], stats
    
    async def __aenter__(self):
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        try:
            self.http_session.close()
        except Exception as e:
            logger.warning(f"Error closing proxy HTTP session: {e}")
        self.executor.shutdown(wait=True)


# Export for use in other modules
__all__ = [
    'CommonCrawlProxyService',
    'ProxyRotationException'
]