"""
Smartproxy-enabled Common Crawl CDX API client using existing DECODO credentials.
Integrates with the configured PROXY_SERVER, PROXY_USERNAME, and PROXY_PASSWORD settings.
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
from requests.auth import HTTPProxyAuth
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


class SmartproxyCommonCrawlException(WaybackMachineException):
    """Exception for Smartproxy Common Crawl operations"""
    pass


class SmartproxyCommonCrawlService:
    """
    Smartproxy-enabled Common Crawl CDX API client using configured DECODO credentials.
    Automatically rotates through Smartproxy's residential IP pool to bypass Common Crawl IP blocks.
    """
    
    DEFAULT_TIMEOUT = 300  # Longer timeout for proxy connections
    DEFAULT_MAX_RETRIES = 3
    DEFAULT_PAGE_SIZE = 2000  # Conservative with proxy
    
    def __init__(self):
        self.timeout = settings.WAYBACK_MACHINE_TIMEOUT or self.DEFAULT_TIMEOUT
        self.max_retries = settings.WAYBACK_MACHINE_MAX_RETRIES or self.DEFAULT_MAX_RETRIES
        
        # Validate proxy configuration
        if not all([settings.PROXY_SERVER, settings.PROXY_USERNAME, settings.PROXY_PASSWORD]):
            raise SmartproxyCommonCrawlException(
                "Smartproxy credentials not configured. Please set PROXY_SERVER, PROXY_USERNAME, and PROXY_PASSWORD"
            )
        
        # Use existing circuit breaker
        self.circuit_breaker = get_wayback_machine_breaker()
        
        # Thread pool for executing synchronous cdx_toolkit operations
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="smartproxy_cc")
        
        # Configure HTTP session with Smartproxy
        self._setup_smartproxy_session()
        
        logger.info(f"Initialized SmartproxyCommonCrawlService with {settings.PROXY_SERVER}, "
                   f"username: {settings.PROXY_USERNAME}, {self.timeout}s timeout, {self.max_retries} max retries")
    
    def _setup_smartproxy_session(self):
        """Set up HTTP session with Smartproxy configuration"""
        self.http_session = requests.Session()
        
        # Configure retry strategy for proxy connections
        retry_strategy = Retry(
            total=3,
            status_forcelist=[429, 500, 502, 503, 504, 407],  # Include proxy auth errors
            backoff_factor=3,  # Longer backoff with proxy
            respect_retry_after_header=True,
            raise_on_status=False
        )
        
        # Configure HTTP adapter
        adapter = HTTPAdapter(
            max_retries=retry_strategy,
            pool_connections=5,
            pool_maxsize=10,
            pool_block=True
        )
        
        self.http_session.mount("http://", adapter)
        self.http_session.mount("https://", adapter)
        
        # Configure Smartproxy settings
        proxy_url = f"http://{settings.PROXY_USERNAME}:{settings.PROXY_PASSWORD}@{settings.PROXY_SERVER}"
        
        self.http_session.proxies = {
            'http': proxy_url,
            'https': proxy_url
        }
        
        # Set headers for Common Crawl
        self.http_session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'application/json,text/plain,*/*',
            'Accept-Encoding': 'gzip, deflate, br',
            'Accept-Language': 'en-US,en;q=0.9',
            'Connection': 'keep-alive',
            'Cache-Control': 'no-cache',
            'Pragma': 'no-cache'
        })
        
        logger.info(f"Configured Smartproxy session: {settings.PROXY_SERVER}")
    
    def _configure_cdx_client(self):
        """Configure cdx_toolkit client with Smartproxy session"""
        self.cdx_client = cdx_toolkit.CDXFetcher(source='cc')
        self.cdx_client.session = self.http_session  # Use Smartproxy session
        self.cdx_client.max_pages = 150  # Conservative with proxy
        self.cdx_client.max_seconds_for_timeout = self.timeout
    
    def _add_smartproxy_session_rotation(self):
        """Add session rotation for Smartproxy to get fresh IPs"""
        # Smartproxy automatically rotates IPs, but we can force rotation by updating session
        try:
            # Add session parameter for IP rotation (Smartproxy feature)
            current_headers = self.http_session.headers.copy()
            session_id = f"session-{random.randint(10000, 99999)}"
            
            # Update proxy URL with session for IP rotation
            proxy_url = f"http://{settings.PROXY_USERNAME}-session-{session_id}:{settings.PROXY_PASSWORD}@{settings.PROXY_SERVER}"
            
            self.http_session.proxies = {
                'http': proxy_url,
                'https': proxy_url
            }
            
            logger.info(f"Rotated Smartproxy session: {session_id}")
            
        except Exception as e:
            logger.warning(f"Session rotation failed: {e}")
    
    @retry(
        stop=stop_after_attempt(3),  # Fewer attempts with premium proxy
        wait=wait_exponential(multiplier=5, min=30, max=600),
        retry=retry_if_exception_type((
            SmartproxyCommonCrawlException,
            ConnectionError, 
            TimeoutError,
            MaxRetryError,
            NewConnectionError,
            ProxyError,
            RequestException
        )),
        before_sleep=before_sleep_log(logger, logging.INFO)
    )
    async def _fetch_records_with_smartproxy_retry(self, query_params: Dict, page_size: int,
                                                  max_pages: Optional[int] = None) -> List:
        """
        Fetch records with Smartproxy rotation and retry logic.
        """
        def _sync_fetch_with_smartproxy():
            try:
                # Configure client with Smartproxy session
                self._configure_cdx_client()
                
                # Add session rotation for fresh IP
                self._add_smartproxy_session_rotation()
                
                # Set pagination limits
                original_max_pages = self.cdx_client.max_pages
                if max_pages:
                    self.cdx_client.max_pages = min(max_pages, 150)
                
                records = []
                count = 0
                
                logger.debug(f"Fetching via Smartproxy: {query_params}")
                
                # Add initial delay to prevent immediate blocking
                time.sleep(random.uniform(8, 15))  # 8-15s initial delay
                
                try:
                    for record in self.cdx_client.iter(**query_params):
                        records.append(record)
                        count += 1
                        
                        if page_size and count >= page_size * (max_pages or 1):
                            break
                        
                        # Respectful delays with Smartproxy
                        if count % 100 == 0:
                            time.sleep(random.uniform(15, 25))  # 15-25s every 100 records
                        elif count % 25 == 0:
                            time.sleep(random.uniform(5, 10))   # 5-10s every 25 records
                        elif count % 5 == 0:
                            time.sleep(random.uniform(1, 3))    # 1-3s every 5 records
                            
                except (ConnectionError, TimeoutError, ProxyError) as conn_err:
                    logger.warning(f"Smartproxy connection error: {conn_err}")
                    if records:
                        logger.info(f"Returning {len(records)} partial records")
                    else:
                        raise SmartproxyCommonCrawlException(f"Smartproxy connection failed: {conn_err}") from conn_err
                
                # Restore settings
                self.cdx_client.max_pages = original_max_pages
                
                logger.info(f"Fetched {len(records)} records via Smartproxy")
                return records
                
            except Exception as e:
                error_str = str(e).lower()
                if any(keyword in error_str for keyword in ['proxy', 'connection', 'timeout', '407']):
                    raise SmartproxyCommonCrawlException(f"Smartproxy error: {e}") from e
                else:
                    raise SmartproxyCommonCrawlException(f"Fetch error: {e}") from e
        
        # Execute with circuit breaker protection
        try:
            loop = asyncio.get_event_loop()
            records = await loop.run_in_executor(self.executor, _sync_fetch_with_smartproxy)
            return records
            
        except Exception as e:
            error_str = str(e).lower()
            if "rate limit" in error_str or "429" in error_str:
                logger.warning("Rate limit detected - rotating Smartproxy session")
                self._add_smartproxy_session_rotation()
                await asyncio.sleep(180)  # Wait 3 minutes for rate limit
                raise SmartproxyCommonCrawlException(f"Rate limited: {e}")
            elif "blocked" in error_str or "403" in error_str:
                logger.warning("IP blocked detected - rotating Smartproxy session")
                self._add_smartproxy_session_rotation()
                raise SmartproxyCommonCrawlException(f"IP blocked: {e}")
            elif "407" in error_str or "proxy authentication" in error_str:
                logger.error("Smartproxy authentication failed - check credentials")
                raise SmartproxyCommonCrawlException(f"Proxy authentication error: {e}")
            else:
                raise SmartproxyCommonCrawlException(f"Smartproxy fetch error: {e}")
    
    async def fetch_cdx_records_simple(self, domain_name: str, from_date: str, to_date: str,
                                     match_type: str = "domain", url_path: Optional[str] = None,
                                     page_size: int = None, max_pages: Optional[int] = None,
                                     include_attachments: bool = True) -> Tuple[List[CDXRecord], Dict[str, int]]:
        """
        Simplified CDX fetch method with Smartproxy support.
        Compatible interface with CommonCrawlService.
        """
        if not page_size:
            page_size = self.DEFAULT_PAGE_SIZE
            
        logger.info(f"Starting Smartproxy Common Crawl fetch for {domain_name}")
        
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
            
            # Fetch with Smartproxy
            raw_records = await self._fetch_records_with_smartproxy_retry(
                query_params, page_size, max_pages
            )
            
            if not raw_records:
                logger.warning(f"No Smartproxy Common Crawl data found for {domain_name}")
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
            
            logger.info(f"Smartproxy Common Crawl fetch complete: {len(filtered_records)} records "
                       f"({static_assets_filtered} static assets filtered)")
            
            return filtered_records, stats
            
        except Exception as e:
            logger.error(f"Smartproxy Common Crawl fetch failed for {domain_name}: {e}")
            return [], stats
    
    async def __aenter__(self):
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        try:
            self.http_session.close()
        except Exception as e:
            logger.warning(f"Error closing Smartproxy HTTP session: {e}")
        self.executor.shutdown(wait=True)


# Test connectivity function
async def test_smartproxy_connection():
    """Test Smartproxy connectivity and IP rotation"""
    try:
        async with SmartproxyCommonCrawlService() as service:
            logger.info("Testing Smartproxy connection...")
            
            # Test basic connectivity
            test_url = "https://httpbin.org/ip"
            response = service.http_session.get(test_url, timeout=30)
            
            if response.status_code == 200:
                ip_info = response.json()
                logger.info(f"✅ Smartproxy connected successfully. Current IP: {ip_info.get('origin')}")
                return True
            else:
                logger.error(f"❌ Smartproxy connection test failed: HTTP {response.status_code}")
                return False
                
    except Exception as e:
        logger.error(f"❌ Smartproxy connection test error: {e}")
        return False


# Export for use in other modules
__all__ = [
    'SmartproxyCommonCrawlService',
    'SmartproxyCommonCrawlException',
    'test_smartproxy_connection'
]