"""
Extended archive strategies for enhanced reliability and fallback options.
Includes proxy-enabled Common Crawl and direct index processing strategies.
"""
import logging
from typing import List, Dict, Tuple, Optional

from .archive_service_router import ArchiveSourceStrategy, ArchiveSourceConfig
from .circuit_breaker import CircuitBreaker
from .wayback_machine import CDXRecord
from .common_crawl_proxy_service import CommonCrawlProxyService, ProxyRotationException
from .common_crawl_direct_service import CommonCrawlDirectService, DirectCommonCrawlException
from .smartproxy_common_crawl_service import SmartproxyCommonCrawlService, SmartproxyCommonCrawlException

logger = logging.getLogger(__name__)


class CommonCrawlProxyStrategy(ArchiveSourceStrategy):
    """Strategy for proxy-enabled Common Crawl CDX API access"""
    
    def __init__(self, config: ArchiveSourceConfig, circuit_breaker: CircuitBreaker, 
                 proxy_list: Optional[List[Dict[str, str]]] = None):
        super().__init__(config, circuit_breaker)
        self.source_name = "common_crawl_proxy"
        self.proxy_list = proxy_list
    
    async def query_archive(
        self,
        domain: str,
        from_date: str, 
        to_date: str,
        match_type: str = "domain",
        url_path: Optional[str] = None
    ) -> Tuple[List[CDXRecord], Dict[str, int]]:
        """Query Common Crawl via proxy rotation"""
        
        async def _execute_proxy_query():
            async with CommonCrawlProxyService(proxy_list=self.proxy_list) as service:
                return await service.fetch_cdx_records_simple(
                    domain, from_date, to_date, match_type, url_path,
                    page_size=self.config.page_size,
                    max_pages=self.config.max_pages
                )
        
        return await self.circuit_breaker.execute(_execute_proxy_query)
    
    def is_retriable_error(self, error: Exception) -> bool:
        """Determine if a proxy error is retriable"""
        if isinstance(error, ProxyRotationException):
            error_str = str(error).lower()
            # Proxy rotation errors are generally retriable
            return any(keyword in error_str for keyword in [
                'proxy', 'connection', 'timeout', 'rate limit', 'blocked'
            ])
        
        # Handle other common errors
        error_str = str(error).lower()
        non_retriable = ['invalid domain', 'malformed', 'authentication']
        return not any(keyword in error_str for keyword in non_retriable)
    
    def get_error_type(self, error: Exception) -> str:
        """Get error type classification for proxy strategy"""
        if isinstance(error, ProxyRotationException):
            error_str = str(error).lower()
            if 'rate limit' in error_str:
                return "proxy_rate_limit"
            elif 'blocked' in error_str or '403' in error_str:
                return "proxy_ip_blocked"
            elif 'proxy' in error_str:
                return "proxy_connection_error"
            elif 'timeout' in error_str:
                return "proxy_timeout"
            else:
                return "proxy_unknown_error"
        
        # Handle other error types
        error_str = str(error).lower()
        if 'timeout' in error_str:
            return "proxy_timeout"
        elif 'connection' in error_str:
            return "proxy_connection_error"
        else:
            return "proxy_unknown_error"


class CommonCrawlDirectStrategy(ArchiveSourceStrategy):
    """Strategy for direct Common Crawl index processing"""
    
    def __init__(self, config: ArchiveSourceConfig, circuit_breaker: CircuitBreaker,
                 cache_dir: Optional[str] = None):
        super().__init__(config, circuit_breaker)
        self.source_name = "common_crawl_direct"
        self.cache_dir = cache_dir
    
    async def query_archive(
        self,
        domain: str,
        from_date: str, 
        to_date: str,
        match_type: str = "domain",
        url_path: Optional[str] = None
    ) -> Tuple[List[CDXRecord], Dict[str, int]]:
        """Query Common Crawl via direct index processing"""
        
        async def _execute_direct_query():
            async with CommonCrawlDirectService(cache_dir=self.cache_dir) as service:
                return await service.fetch_cdx_records_simple(
                    domain, from_date, to_date, match_type, url_path,
                    page_size=self.config.page_size,
                    max_pages=self.config.max_pages
                )
        
        return await self.circuit_breaker.execute(_execute_direct_query)
    
    def is_retriable_error(self, error: Exception) -> bool:
        """Determine if a direct processing error is retriable"""
        if isinstance(error, DirectCommonCrawlException):
            error_str = str(error).lower()
            # Network and temporary errors are retriable
            retriable_keywords = ['download', 'network', 'timeout', 'temporary', 'connection']
            return any(keyword in error_str for keyword in retriable_keywords)
        
        # Handle other error types
        error_str = str(error).lower()
        non_retriable = ['disk space', 'permission denied', 'invalid format']
        return not any(keyword in error_str for keyword in non_retriable)
    
    def get_error_type(self, error: Exception) -> str:
        """Get error type classification for direct strategy"""
        if isinstance(error, DirectCommonCrawlException):
            error_str = str(error).lower()
            if 'download' in error_str:
                return "direct_download_error"
            elif 'processing' in error_str:
                return "direct_processing_error"
            elif 'timeout' in error_str:
                return "direct_timeout"
            elif 'disk' in error_str or 'space' in error_str:
                return "direct_disk_error"
            else:
                return "direct_unknown_error"
        
        # Handle other error types
        error_str = str(error).lower()
        if 'timeout' in error_str:
            return "direct_timeout"
        elif 'connection' in error_str:
            return "direct_connection_error"
        elif 'permission' in error_str:
            return "direct_permission_error"
        else:
            return "direct_unknown_error"


class InternetArchiveStrategy(ArchiveSourceStrategy):
    """Strategy for Internet Archive CDX API as fallback"""
    
    def __init__(self, config: ArchiveSourceConfig, circuit_breaker: CircuitBreaker):
        super().__init__(config, circuit_breaker)
        self.source_name = "internet_archive"
    
    async def query_archive(
        self,
        domain: str,
        from_date: str, 
        to_date: str,
        match_type: str = "domain",
        url_path: Optional[str] = None
    ) -> Tuple[List[CDXRecord], Dict[str, int]]:
        """Query Internet Archive CDX API"""
        
        async def _execute_ia_query():
            # Import existing wayback machine client
            from .wayback_machine import CDXAPIClient
            
            async with CDXAPIClient() as client:
                # Internet Archive uses the same interface as Wayback Machine
                return await client.fetch_cdx_records_simple(
                    domain, from_date, to_date, match_type, url_path,
                    page_size=self.config.page_size,
                    max_pages=self.config.max_pages
                )
        
        return await self.circuit_breaker.execute(_execute_ia_query)
    
    def is_retriable_error(self, error: Exception) -> bool:
        """Determine if an Internet Archive error is retriable"""
        from .wayback_machine import WaybackMachineException
        
        if isinstance(error, WaybackMachineException):
            error_str = str(error).lower()
            # Rate limits and temporary errors are retriable
            retriable_keywords = ['rate limit', 'timeout', 'temporary', 'service unavailable']
            return any(keyword in error_str for keyword in retriable_keywords)
        
        # Handle other error types
        error_str = str(error).lower()
        non_retriable = ['invalid domain', 'malformed', 'not found']
        return not any(keyword in error_str for keyword in non_retriable)
    
    def get_error_type(self, error: Exception) -> str:
        """Get error type classification for Internet Archive strategy"""
        from .wayback_machine import WaybackMachineException
        
        if isinstance(error, WaybackMachineException):
            error_str = str(error).lower()
            if 'rate limit' in error_str:
                return "ia_rate_limit"
            elif 'timeout' in error_str:
                return "ia_timeout"
            elif 'service unavailable' in error_str:
                return "ia_service_unavailable"
            else:
                return "ia_api_error"
        
        # Handle other error types
        error_str = str(error).lower()
        if 'timeout' in error_str:
            return "ia_timeout"
        elif 'connection' in error_str:
            return "ia_connection_error"
        else:
            return "ia_unknown_error"


class SmartproxyCommonCrawlStrategy(ArchiveSourceStrategy):
    """Strategy for Smartproxy-enabled Common Crawl CDX API access"""
    
    def __init__(self, config: ArchiveSourceConfig, circuit_breaker: CircuitBreaker):
        super().__init__(config, circuit_breaker)
        self.source_name = "smartproxy_common_crawl"
    
    async def query_archive(
        self,
        domain: str,
        from_date: str, 
        to_date: str,
        match_type: str = "domain",
        url_path: Optional[str] = None
    ) -> Tuple[List[CDXRecord], Dict[str, int]]:
        """Query Common Crawl via Smartproxy"""
        
        async def _execute_smartproxy_query():
            async with SmartproxyCommonCrawlService() as service:
                return await service.fetch_cdx_records_simple(
                    domain, from_date, to_date, match_type, url_path,
                    page_size=self.config.page_size,
                    max_pages=self.config.max_pages
                )
        
        return await self.circuit_breaker.execute(_execute_smartproxy_query)
    
    def is_retriable_error(self, error: Exception) -> bool:
        """Determine if a Smartproxy error is retriable"""
        if isinstance(error, SmartproxyCommonCrawlException):
            error_str = str(error).lower()
            # Authentication errors are not retriable, others are
            non_retriable = ['authentication', '407', 'invalid credentials', 'unauthorized']
            if any(keyword in error_str for keyword in non_retriable):
                return False
            
            # Rate limits and connection issues are retriable
            retriable_keywords = ['rate limit', 'connection', 'timeout', 'blocked', 'proxy']
            return any(keyword in error_str for keyword in retriable_keywords)
        
        # Handle other error types
        error_str = str(error).lower()
        non_retriable = ['authentication', 'credentials', 'unauthorized']
        return not any(keyword in error_str for keyword in non_retriable)
    
    def get_error_type(self, error: Exception) -> str:
        """Get error type classification for Smartproxy strategy"""
        if isinstance(error, SmartproxyCommonCrawlException):
            error_str = str(error).lower()
            if 'authentication' in error_str or '407' in error_str:
                return "smartproxy_auth_error"
            elif 'rate limit' in error_str:
                return "smartproxy_rate_limit"
            elif 'blocked' in error_str or '403' in error_str:
                return "smartproxy_ip_blocked"
            elif 'connection' in error_str:
                return "smartproxy_connection_error"
            elif 'timeout' in error_str:
                return "smartproxy_timeout"
            else:
                return "smartproxy_unknown_error"
        
        # Handle other error types
        error_str = str(error).lower()
        if 'timeout' in error_str:
            return "smartproxy_timeout"
        elif 'connection' in error_str:
            return "smartproxy_connection_error"
        else:
            return "smartproxy_unknown_error"


# Export strategies for use in router
__all__ = [
    'CommonCrawlProxyStrategy',
    'CommonCrawlDirectStrategy', 
    'InternetArchiveStrategy',
    'SmartproxyCommonCrawlStrategy'
]