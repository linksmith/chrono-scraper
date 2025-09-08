"""
ArchiveServiceRouter - Intelligent routing between archive sources with comprehensive fallback logic.

This module provides a unified interface for querying CDX data from multiple archive sources
(Wayback Machine, Common Crawl) with intelligent routing, fallback mechanisms, and performance
monitoring based on project configuration.

Key Features:
- Unified interface that abstracts archive source selection
- Intelligent routing based on project configuration and preferences
- Automatic fallback when primary source fails (522 errors, timeouts, rate limits)
- Circuit breaker integration for resilience
- Performance monitoring and success rate tracking
- Project-level configuration support for source-specific settings
"""

import asyncio
import logging
import time
from datetime import datetime, timedelta
from typing import List, Dict, Tuple, Optional, Set, Any, Union
from dataclasses import dataclass, field
from enum import Enum
from abc import ABC, abstractmethod

from ..core.config import settings
from ..models.project import ArchiveSource
from ..services.circuit_breaker import (
    CircuitBreaker, 
    CircuitBreakerConfig, 
    CircuitBreakerOpenException,
    get_wayback_machine_breaker,
    circuit_registry
)
from ..services.wayback_machine import (
    CDXAPIClient, 
    CDXRecord, 
    CDXAPIException, 
    WaybackMachineException
)
from ..services.common_crawl_service import (
    CommonCrawlService,
    CommonCrawlException,
    CommonCrawlAPIException
)

logger = logging.getLogger(__name__)


class ArchiveServiceRouterException(Exception):
    """Base exception for archive service router errors"""
    pass


class AllSourcesFailedException(ArchiveServiceRouterException):
    """Exception raised when all configured archive sources have failed"""
    pass


class FallbackStrategy(str, Enum):
    """Strategies for handling fallback between archive sources"""
    IMMEDIATE = "immediate"        # Immediate fallback on first error
    RETRY_THEN_FALLBACK = "retry_then_fallback"  # Retry primary, then fallback
    CIRCUIT_BREAKER = "circuit_breaker"  # Use circuit breaker to control fallback
    

@dataclass
class ArchiveSourceConfig:
    """Configuration for individual archive sources"""
    enabled: bool = True
    timeout_seconds: int = 120
    max_retries: int = 3
    page_size: int = 5000
    max_pages: Optional[int] = None
    include_attachments: bool = True
    priority: int = 1  # Lower numbers = higher priority
    # Source-specific settings
    custom_settings: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RoutingConfig:
    """Configuration for archive source routing behavior"""
    fallback_strategy: FallbackStrategy = FallbackStrategy.CIRCUIT_BREAKER
    fallback_delay_seconds: float = 1.0
    exponential_backoff: bool = True
    max_fallback_delay: float = 30.0
    
    # Source configurations
    wayback_config: ArchiveSourceConfig = field(default_factory=ArchiveSourceConfig)
    common_crawl_config: ArchiveSourceConfig = field(default_factory=ArchiveSourceConfig)
    
    def __post_init__(self):
        """Set default priorities for sources"""
        if self.wayback_config.priority == self.common_crawl_config.priority:
            # Default: Wayback Machine has higher priority
            self.wayback_config.priority = 1
            self.common_crawl_config.priority = 2


@dataclass 
class ArchiveQueryMetrics:
    """Metrics for archive query performance tracking"""
    source: str
    start_time: float
    end_time: Optional[float] = None
    success: bool = False
    error_type: Optional[str] = None
    error_message: Optional[str] = None
    records_retrieved: int = 0
    pages_fetched: int = 0
    fallback_used: bool = False
    
    @property
    def duration_seconds(self) -> float:
        """Calculate query duration in seconds"""
        if self.end_time is None:
            return 0.0
        return self.end_time - self.start_time
    
    def mark_success(self, records_count: int = 0, pages_count: int = 0):
        """Mark query as successful"""
        self.end_time = time.time()
        self.success = True
        self.records_retrieved = records_count
        self.pages_fetched = pages_count
    
    def mark_failure(self, error_type: str, error_message: str = ""):
        """Mark query as failed"""
        self.end_time = time.time()
        self.success = False
        self.error_type = error_type
        self.error_message = error_message


@dataclass
class ArchiveSourceMetrics:
    """Aggregate metrics for an archive source"""
    source_name: str
    total_queries: int = 0
    successful_queries: int = 0
    failed_queries: int = 0
    total_records: int = 0
    avg_response_time: float = 0.0
    last_success_time: Optional[datetime] = None
    last_failure_time: Optional[datetime] = None
    
    # Error type tracking
    error_counts: Dict[str, int] = field(default_factory=dict)
    
    def update_from_query(self, query_metrics: ArchiveQueryMetrics):
        """Update aggregate metrics from a query result"""
        self.total_queries += 1
        
        if query_metrics.success:
            self.successful_queries += 1
            self.total_records += query_metrics.records_retrieved
            self.last_success_time = datetime.now()
            
            # Update rolling average response time
            if self.total_queries == 1:
                self.avg_response_time = query_metrics.duration_seconds
            else:
                # Exponential moving average with alpha=0.2
                alpha = 0.2
                self.avg_response_time = (alpha * query_metrics.duration_seconds + 
                                        (1 - alpha) * self.avg_response_time)
        else:
            self.failed_queries += 1
            self.last_failure_time = datetime.now()
            
            if query_metrics.error_type:
                self.error_counts[query_metrics.error_type] = (
                    self.error_counts.get(query_metrics.error_type, 0) + 1
                )
    
    @property
    def success_rate(self) -> float:
        """Calculate success rate percentage"""
        if self.total_queries == 0:
            return 0.0
        return (self.successful_queries / self.total_queries) * 100.0
    
    @property
    def is_healthy(self) -> bool:
        """Check if source is considered healthy (>80% success rate)"""
        return self.success_rate >= 80.0


class ArchiveSourceStrategy(ABC):
    """Abstract base class for archive source strategies"""
    
    def __init__(self, config: ArchiveSourceConfig, circuit_breaker: CircuitBreaker):
        self.config = config
        self.circuit_breaker = circuit_breaker
        self.source_name = self.__class__.__name__.replace('Strategy', '').lower()
    
    @abstractmethod
    async def query_archive(
        self,
        domain: str,
        from_date: str, 
        to_date: str,
        match_type: str = "domain",
        url_path: Optional[str] = None
    ) -> Tuple[List[CDXRecord], Dict[str, int]]:
        """Query the archive source for CDX records"""
        pass
    
    @abstractmethod
    def is_retriable_error(self, error: Exception) -> bool:
        """Determine if an error is retriable"""
        pass
    
    @abstractmethod
    def get_error_type(self, error: Exception) -> str:
        """Get error type classification for metrics"""
        pass


class WaybackMachineStrategy(ArchiveSourceStrategy):
    """Strategy for Wayback Machine CDX API"""
    
    def __init__(self, config: ArchiveSourceConfig, circuit_breaker: CircuitBreaker):
        super().__init__(config, circuit_breaker)
        self.source_name = "wayback_machine"
    
    async def query_archive(
        self,
        domain: str,
        from_date: str,
        to_date: str, 
        match_type: str = "domain",
        url_path: Optional[str] = None
    ) -> Tuple[List[CDXRecord], Dict[str, int]]:
        """Query Wayback Machine CDX API"""
        
        async def _execute_query():
            async with CDXAPIClient() as client:
                return await client.fetch_cdx_records_simple(
                    domain_name=domain,
                    from_date=from_date,
                    to_date=to_date,
                    match_type=match_type,
                    url_path=url_path,
                    page_size=self.config.page_size,
                    max_pages=self.config.max_pages,
                    include_attachments=self.config.include_attachments
                )
        
        return await self.circuit_breaker.execute(_execute_query)
    
    def is_retriable_error(self, error: Exception) -> bool:
        """Check if Wayback Machine error is retriable"""
        if isinstance(error, CDXAPIException):
            error_msg = str(error).lower()
            return any(retriable in error_msg for retriable in [
                "522", "timeout", "connection", "503", "502"
            ])
        return isinstance(error, (TimeoutError, ConnectionError))
    
    def get_error_type(self, error: Exception) -> str:
        """Classify Wayback Machine errors"""
        if isinstance(error, CDXAPIException):
            error_msg = str(error).lower()
            if "522" in error_msg:
                return "wayback_522_timeout"
            elif "503" in error_msg:
                return "wayback_503_unavailable"
            elif "timeout" in error_msg:
                return "wayback_timeout"
            elif "rate limit" in error_msg:
                return "wayback_rate_limit"
            else:
                return "wayback_api_error"
        elif isinstance(error, TimeoutError):
            return "wayback_timeout"
        elif isinstance(error, ConnectionError):
            return "wayback_connection_error"
        else:
            return "wayback_unknown_error"


class CommonCrawlStrategy(ArchiveSourceStrategy):
    """Strategy for Common Crawl CDX API"""
    
    def __init__(self, config: ArchiveSourceConfig, circuit_breaker: CircuitBreaker):
        super().__init__(config, circuit_breaker)
        self.source_name = "common_crawl"
    
    async def query_archive(
        self,
        domain: str,
        from_date: str,
        to_date: str,
        match_type: str = "domain", 
        url_path: Optional[str] = None
    ) -> Tuple[List[CDXRecord], Dict[str, int]]:
        """Query Common Crawl CDX API"""
        
        async def _execute_query():
            async with CommonCrawlService() as service:
                return await service.fetch_cdx_records_simple(
                    domain_name=domain,
                    from_date=from_date,
                    to_date=to_date,
                    match_type=match_type,
                    url_path=url_path,
                    page_size=self.config.page_size,
                    max_pages=self.config.max_pages,
                    include_attachments=self.config.include_attachments
                )
        
        return await self.circuit_breaker.execute(_execute_query)
    
    def is_retriable_error(self, error: Exception) -> bool:
        """Check if Common Crawl error is retriable (including SmartProxy issues)"""
        if isinstance(error, (CommonCrawlException, CommonCrawlAPIException)):
            error_msg = str(error).lower()
            # Don't retry proxy authentication errors - these need manual fix
            if "407" in error_msg or "proxy authentication" in error_msg:
                return False
            # Retry other proxy and connection issues
            return any(retriable in error_msg for retriable in [
                "rate limit", "timeout", "connection", "503", "502", "proxy error", "smartproxy"
            ])
        return isinstance(error, (TimeoutError, ConnectionError))
    
    def get_error_type(self, error: Exception) -> str:
        """Classify Common Crawl errors including SmartProxy-related issues"""
        if isinstance(error, (CommonCrawlException, CommonCrawlAPIException)):
            error_msg = str(error).lower()
            if "rate limit" in error_msg:
                return "common_crawl_rate_limit"
            elif "timeout" in error_msg:
                return "common_crawl_timeout"
            elif "407" in error_msg or "proxy authentication" in error_msg:
                return "common_crawl_proxy_auth_error"
            elif "smartproxy" in error_msg or ("proxy" in error_msg and ("error" in error_msg or "failed" in error_msg)):
                return "common_crawl_proxy_error"
            elif "connection" in error_msg:
                return "common_crawl_connection_error"
            else:
                return "common_crawl_api_error"
        elif isinstance(error, TimeoutError):
            return "common_crawl_timeout"
        elif isinstance(error, ConnectionError):
            return "common_crawl_connection_error"
        else:
            return "common_crawl_unknown_error"


class ArchiveServiceRouter:
    """
    Intelligent router for archive services with fallback logic.
    Provides unified interface to CDX data from multiple sources.
    
    This router intelligently selects archive sources based on project configuration,
    implements comprehensive fallback logic for handling failures, and tracks performance
    metrics to optimize future routing decisions.
    
    Key Features:
    - Unified query interface abstracting source selection
    - Intelligent routing based on project configuration
    - Automatic fallback with exponential backoff
    - Circuit breaker integration for resilience
    - Performance monitoring and success rate tracking
    - Configuration support for source-specific settings
    """
    
    def __init__(self, routing_config: Optional[RoutingConfig] = None):
        """
        Initialize the ArchiveServiceRouter.
        
        Args:
            routing_config: Optional routing configuration. If None, uses defaults.
        """
        self.config = routing_config or RoutingConfig()
        
        # Initialize circuit breakers for each source
        self._init_circuit_breakers()
        
        # Initialize source strategies  
        self._init_source_strategies()
        
        # Metrics tracking
        self.source_metrics: Dict[str, ArchiveSourceMetrics] = {
            "wayback_machine": ArchiveSourceMetrics("wayback_machine"),
            "common_crawl": ArchiveSourceMetrics("common_crawl")
        }
        
        # Query history for analysis
        self.query_history: List[ArchiveQueryMetrics] = []
        self.max_query_history = 1000  # Keep last 1000 queries
        
        logger.info(f"Initialized ArchiveServiceRouter with fallback strategy: {self.config.fallback_strategy}")
    
    def _init_circuit_breakers(self):
        """Initialize circuit breakers for each archive source"""
        
        # Wayback Machine circuit breaker (reuse existing)
        self.wayback_breaker = get_wayback_machine_breaker()
        
        # Common Crawl circuit breaker (new)
        cc_config = CircuitBreakerConfig(
            failure_threshold=5,
            success_threshold=3, 
            timeout_seconds=90,  # Longer timeout for Common Crawl
            max_timeout_seconds=600,
            exponential_backoff=True,
            sliding_window_size=10
        )
        self.common_crawl_breaker = circuit_registry.get_breaker("common_crawl", cc_config)
        
        logger.info("Initialized circuit breakers for archive sources")
    
    def _init_source_strategies(self):
        """Initialize source strategy instances"""
        self.strategies: Dict[str, ArchiveSourceStrategy] = {
            "wayback_machine": WaybackMachineStrategy(
                self.config.wayback_config, 
                self.wayback_breaker
            ),
            "common_crawl": CommonCrawlStrategy(
                self.config.common_crawl_config,
                self.common_crawl_breaker
            )
        }
        
        logger.info("Initialized archive source strategies")
    
    def _determine_source_order(self, archive_source: ArchiveSource) -> List[str]:
        """
        Determine the order of sources to try based on archive source configuration.
        
        Args:
            archive_source: The archive source preference from project config
            
        Returns:
            List of source names in priority order
        """
        if archive_source == ArchiveSource.WAYBACK_MACHINE:
            return ["wayback_machine"]
        
        elif archive_source == ArchiveSource.COMMON_CRAWL:
            return ["common_crawl"]
        
        elif archive_source == ArchiveSource.HYBRID:
            # Determine order based on priority and health
            sources = []
            
            # Add Wayback Machine
            if self.config.wayback_config.enabled:
                sources.append(("wayback_machine", self.config.wayback_config.priority))
            
            # Add Common Crawl
            if self.config.common_crawl_config.enabled:
                sources.append(("common_crawl", self.config.common_crawl_config.priority))
            
            # Sort by priority (lower number = higher priority), then by health
            sources.sort(key=lambda x: (
                x[1],  # Priority
                -self.source_metrics[x[0]].success_rate  # Success rate (higher is better)
            ))
            
            return [source[0] for source in sources]
        
        else:
            # Default to Wayback Machine
            logger.warning(f"Unknown archive source: {archive_source}, defaulting to Wayback Machine")
            return ["wayback_machine"]
    
    def _should_attempt_fallback(
        self, 
        error: Exception, 
        strategy: ArchiveSourceStrategy,
        fallback_available: bool
    ) -> bool:
        """
        Determine if fallback should be attempted based on error and strategy.
        
        Args:
            error: The error that occurred
            strategy: The strategy that failed
            fallback_available: Whether fallback sources are available
            
        Returns:
            True if fallback should be attempted
        """
        if not fallback_available:
            return False
        
        # Check fallback strategy
        if self.config.fallback_strategy == FallbackStrategy.IMMEDIATE:
            return True
        
        elif self.config.fallback_strategy == FallbackStrategy.RETRY_THEN_FALLBACK:
            # Only fallback on non-retriable errors or circuit breaker open
            return (not strategy.is_retriable_error(error) or 
                   isinstance(error, CircuitBreakerOpenException))
        
        elif self.config.fallback_strategy == FallbackStrategy.CIRCUIT_BREAKER:
            # Let circuit breaker control fallback behavior
            return isinstance(error, CircuitBreakerOpenException)
        
        return False
    
    async def _execute_query_with_fallback(
        self,
        source_order: List[str],
        domain: str,
        from_date: str,
        to_date: str,
        match_type: str,
        url_path: Optional[str]
    ) -> Tuple[List[CDXRecord], Dict[str, Any]]:
        """
        Execute query with fallback logic across multiple sources.
        
        Returns:
            Tuple of (records, comprehensive_stats)
        """
        last_error = None
        fallback_delay = self.config.fallback_delay_seconds
        
        # Track all attempts for comprehensive stats
        attempt_stats = {
            "attempts": [],
            "primary_source": source_order[0] if source_order else "none",
            "successful_source": None,
            "fallback_used": False,
            "total_duration": 0.0
        }
        
        query_start_time = time.time()
        
        for i, source_name in enumerate(source_order):
            is_primary = (i == 0)
            is_fallback = not is_primary
            
            # Initialize query metrics
            query_metrics = ArchiveQueryMetrics(
                source=source_name,
                start_time=time.time(),
                fallback_used=is_fallback
            )
            
            try:
                logger.info(f"Querying {source_name} for domain {domain} "
                           f"({'primary' if is_primary else 'fallback'})")
                
                strategy = self.strategies[source_name]
                records, source_stats = await strategy.query_archive(
                    domain=domain,
                    from_date=from_date,
                    to_date=to_date,
                    match_type=match_type,
                    url_path=url_path
                )
                
                # Success!
                query_metrics.mark_success(
                    records_count=len(records),
                    pages_count=source_stats.get('fetched_pages', 0)
                )
                
                # Update aggregate metrics
                self.source_metrics[source_name].update_from_query(query_metrics)
                
                # Add to query history
                self._add_to_query_history(query_metrics)
                
                # Update attempt stats
                attempt_stats["successful_source"] = source_name
                attempt_stats["fallback_used"] = is_fallback
                attempt_stats["total_duration"] = time.time() - query_start_time
                attempt_stats["attempts"].append({
                    "source": source_name,
                    "success": True,
                    "duration": query_metrics.duration_seconds,
                    "records": len(records)
                })
                
                # Combine source stats with attempt stats
                combined_stats = {**source_stats, **attempt_stats}
                
                logger.info(f"Successfully retrieved {len(records)} records from {source_name} "
                           f"in {query_metrics.duration_seconds:.2f}s")
                
                return records, combined_stats
                
            except Exception as error:
                last_error = error
                error_type = strategy.get_error_type(error)
                
                query_metrics.mark_failure(error_type, str(error))
                
                # Update aggregate metrics
                self.source_metrics[source_name].update_from_query(query_metrics)
                
                # Add to query history
                self._add_to_query_history(query_metrics)
                
                # Add to attempt stats
                attempt_stats["attempts"].append({
                    "source": source_name,
                    "success": False,
                    "error_type": error_type,
                    "error": str(error),
                    "duration": query_metrics.duration_seconds
                })
                
                logger.warning(f"Query failed for {source_name}: {error_type} - {error}")
                
                # Check if we should try fallback
                remaining_sources = source_order[i + 1:]
                should_fallback = self._should_attempt_fallback(
                    error, strategy, bool(remaining_sources)
                )
                
                if should_fallback and remaining_sources:
                    logger.info(f"Attempting fallback to {remaining_sources[0]} after {fallback_delay}s delay")
                    
                    # Apply fallback delay
                    await asyncio.sleep(fallback_delay)
                    
                    # Exponential backoff for next fallback (if any)
                    if self.config.exponential_backoff:
                        fallback_delay = min(
                            fallback_delay * 2,
                            self.config.max_fallback_delay
                        )
                    
                    continue  # Try next source
                else:
                    logger.error(f"Not attempting fallback from {source_name}: "
                               f"should_fallback={should_fallback}, "
                               f"remaining_sources={len(remaining_sources)}")
                    break  # No more fallback options
        
        # All sources failed
        attempt_stats["total_duration"] = time.time() - query_start_time
        
        error_message = f"All configured archive sources failed. Last error: {last_error}"
        logger.error(error_message)
        
        # Return empty results with comprehensive error stats
        failed_stats = {
            "error": error_message,
            "total_records": 0,
            "final_count": 0,
            **attempt_stats
        }
        
        raise AllSourcesFailedException(error_message)
    
    def _add_to_query_history(self, query_metrics: ArchiveQueryMetrics):
        """Add query metrics to history, maintaining max size"""
        self.query_history.append(query_metrics)
        
        # Keep only the most recent queries
        if len(self.query_history) > self.max_query_history:
            self.query_history = self.query_history[-self.max_query_history:]
    
    async def query_archive(
        self,
        domain: str,
        from_date: str,
        to_date: str,
        project_config: Optional[Dict[str, Any]] = None,
        match_type: str = "domain",
        url_path: Optional[str] = None
    ) -> Tuple[List[CDXRecord], Dict[str, Any]]:
        """
        Query archive sources with intelligent routing and fallback logic.
        
        This is the main entry point for archive queries. It intelligently selects
        archive sources based on project configuration, implements fallback logic,
        and tracks performance metrics.
        
        Args:
            domain: Domain to query (e.g., 'example.com')
            from_date: Start date in YYYYMMDD format
            to_date: End date in YYYYMMDD format  
            project_config: Project configuration containing archive preferences
            match_type: CDX match type ('domain', 'prefix', 'exact')
            url_path: URL path for prefix matching
            
        Returns:
            Tuple of (CDX records, comprehensive stats dictionary)
            
        Raises:
            AllSourcesFailedException: When all configured sources fail
            ArchiveServiceRouterException: For other router-specific errors
        """
        
        # Extract archive configuration from project config
        archive_source = ArchiveSource.WAYBACK_MACHINE  # Default
        fallback_enabled = True  # Default
        archive_config = {}  # Default
        
        if project_config:
            archive_source = project_config.get('archive_source', ArchiveSource.WAYBACK_MACHINE)
            fallback_enabled = project_config.get('fallback_enabled', True)
            archive_config = project_config.get('archive_config', {})
        
        # Apply project-specific archive configuration to routing config
        self._apply_project_config(archive_config)
        
        # Determine source execution order
        source_order = self._determine_source_order(archive_source)
        
        # If fallback is disabled, only use primary source
        if not fallback_enabled:
            source_order = source_order[:1]
        
        if not source_order:
            raise ArchiveServiceRouterException("No enabled archive sources configured")
        
        logger.info(f"Archive query for {domain} using source order: {source_order}")
        
        try:
            return await self._execute_query_with_fallback(
                source_order=source_order,
                domain=domain,
                from_date=from_date,
                to_date=to_date,
                match_type=match_type,
                url_path=url_path
            )
        except AllSourcesFailedException:
            # Re-raise as-is
            raise
        except Exception as error:
            # Wrap unexpected errors
            error_message = f"Unexpected error in archive query: {error}"
            logger.error(error_message)
            raise ArchiveServiceRouterException(error_message) from error
    
    def _apply_project_config(self, archive_config: Dict[str, Any]):
        """
        Apply project-specific configuration to routing config.
        
        Args:
            archive_config: Project's archive configuration
        """
        if not archive_config:
            return
        
        # Apply Wayback Machine specific config
        wayback_config = archive_config.get('wayback_machine', {})
        if wayback_config:
            if 'timeout_seconds' in wayback_config:
                self.config.wayback_config.timeout_seconds = wayback_config['timeout_seconds']
            if 'max_retries' in wayback_config:
                self.config.wayback_config.max_retries = wayback_config['max_retries']
            if 'page_size' in wayback_config:
                self.config.wayback_config.page_size = wayback_config['page_size']
            if 'max_pages' in wayback_config:
                self.config.wayback_config.max_pages = wayback_config['max_pages']
        
        # Apply Common Crawl specific config
        common_crawl_config = archive_config.get('common_crawl', {})
        if common_crawl_config:
            if 'timeout_seconds' in common_crawl_config:
                self.config.common_crawl_config.timeout_seconds = common_crawl_config['timeout_seconds']
            if 'max_retries' in common_crawl_config:
                self.config.common_crawl_config.max_retries = common_crawl_config['max_retries']
            if 'page_size' in common_crawl_config:
                self.config.common_crawl_config.page_size = common_crawl_config['page_size']
            if 'max_pages' in common_crawl_config:
                self.config.common_crawl_config.max_pages = common_crawl_config['max_pages']
        
        # Apply routing-level config
        if 'fallback_strategy' in archive_config:
            try:
                self.config.fallback_strategy = FallbackStrategy(archive_config['fallback_strategy'])
            except ValueError:
                logger.warning(f"Invalid fallback strategy: {archive_config['fallback_strategy']}")
        
        if 'fallback_delay_seconds' in archive_config:
            self.config.fallback_delay_seconds = archive_config['fallback_delay_seconds']
    
    def get_performance_metrics(self) -> Dict[str, Any]:
        """
        Get comprehensive performance metrics for all archive sources.
        
        Returns:
            Dictionary containing detailed performance metrics
        """
        metrics = {
            "sources": {},
            "overall": {
                "total_queries": sum(m.total_queries for m in self.source_metrics.values()),
                "avg_success_rate": 0.0,
                "query_history_size": len(self.query_history)
            },
            "circuit_breakers": {
                "wayback_machine": self.wayback_breaker.get_status(),
                "common_crawl": self.common_crawl_breaker.get_status()
            },
            "config": {
                "fallback_strategy": self.config.fallback_strategy.value,
                "fallback_delay_seconds": self.config.fallback_delay_seconds,
                "exponential_backoff": self.config.exponential_backoff
            }
        }
        
        # Add source-specific metrics
        total_success_rate = 0.0
        active_sources = 0
        
        for source_name, source_metrics in self.source_metrics.items():
            metrics["sources"][source_name] = {
                "total_queries": source_metrics.total_queries,
                "successful_queries": source_metrics.successful_queries,
                "failed_queries": source_metrics.failed_queries,
                "success_rate": round(source_metrics.success_rate, 2),
                "avg_response_time": round(source_metrics.avg_response_time, 3),
                "total_records": source_metrics.total_records,
                "is_healthy": source_metrics.is_healthy,
                "last_success_time": (source_metrics.last_success_time.isoformat() 
                                    if source_metrics.last_success_time else None),
                "last_failure_time": (source_metrics.last_failure_time.isoformat()
                                    if source_metrics.last_failure_time else None),
                "error_counts": dict(source_metrics.error_counts)
            }
            
            if source_metrics.total_queries > 0:
                total_success_rate += source_metrics.success_rate
                active_sources += 1
        
        # Calculate overall success rate
        if active_sources > 0:
            metrics["overall"]["avg_success_rate"] = round(total_success_rate / active_sources, 2)
        
        return metrics
    
    def get_health_status(self) -> Dict[str, Any]:
        """
        Get health status of the archive service router.
        
        Returns:
            Health status including source health and circuit breaker states
        """
        wayback_status = self.wayback_breaker.get_status()
        common_crawl_status = self.common_crawl_breaker.get_status()
        
        # Determine overall health
        wayback_healthy = (wayback_status["state"] != "open" and 
                          self.source_metrics["wayback_machine"].is_healthy)
        common_crawl_healthy = (common_crawl_status["state"] != "open" and 
                               self.source_metrics["common_crawl"].is_healthy)
        
        if wayback_healthy and common_crawl_healthy:
            overall_status = "healthy"
        elif wayback_healthy or common_crawl_healthy:
            overall_status = "degraded"
        else:
            overall_status = "unhealthy"
        
        return {
            "overall_status": overall_status,
            "sources": {
                "wayback_machine": {
                    "healthy": wayback_healthy,
                    "circuit_breaker_state": wayback_status["state"],
                    "success_rate": round(self.source_metrics["wayback_machine"].success_rate, 2),
                    "last_success": (self.source_metrics["wayback_machine"].last_success_time.isoformat()
                                   if self.source_metrics["wayback_machine"].last_success_time else None)
                },
                "common_crawl": {
                    "healthy": common_crawl_healthy,
                    "circuit_breaker_state": common_crawl_status["state"],
                    "success_rate": round(self.source_metrics["common_crawl"].success_rate, 2),
                    "last_success": (self.source_metrics["common_crawl"].last_success_time.isoformat()
                                   if self.source_metrics["common_crawl"].last_success_time else None)
                }
            },
            "timestamp": datetime.now().isoformat()
        }
    
    def reset_metrics(self):
        """Reset all performance metrics and query history"""
        self.source_metrics = {
            "wayback_machine": ArchiveSourceMetrics("wayback_machine"),
            "common_crawl": ArchiveSourceMetrics("common_crawl")
        }
        self.query_history.clear()
        logger.info("Archive service router metrics have been reset")


# Convenience functions for backward compatibility and easy integration

async def query_archive_unified(
    domain: str,
    from_date: str, 
    to_date: str,
    project_config: Optional[Dict[str, Any]] = None,
    match_type: str = "domain",
    url_path: Optional[str] = None,
    routing_config: Optional[RoutingConfig] = None
) -> Tuple[List[CDXRecord], Dict[str, Any]]:
    """
    Convenience function for unified archive querying with intelligent routing.
    
    This function creates a temporary ArchiveServiceRouter instance and executes
    a query with the provided configuration. Useful for one-off queries.
    
    Args:
        domain: Domain to query
        from_date: Start date (YYYYMMDD)
        to_date: End date (YYYYMMDD)
        project_config: Project configuration with archive preferences
        match_type: CDX match type
        url_path: URL path for prefix matching
        routing_config: Optional routing configuration
        
    Returns:
        Tuple of (CDX records, stats)
    """
    router = ArchiveServiceRouter(routing_config)
    return await router.query_archive(
        domain=domain,
        from_date=from_date,
        to_date=to_date,
        project_config=project_config,
        match_type=match_type,
        url_path=url_path
    )


def create_routing_config_from_project(
    archive_source: ArchiveSource,
    fallback_enabled: bool = True,
    archive_config: Optional[Dict[str, Any]] = None
) -> RoutingConfig:
    """
    Create a RoutingConfig from project-level archive settings.
    
    Args:
        archive_source: Primary archive source preference
        fallback_enabled: Whether fallback is enabled
        archive_config: Archive-specific configuration
        
    Returns:
        RoutingConfig instance
    """
    config = RoutingConfig()
    
    # Apply archive-specific configuration
    if archive_config:
        # Wayback Machine config
        wayback_settings = archive_config.get('wayback_machine', {})
        for key, value in wayback_settings.items():
            if hasattr(config.wayback_config, key):
                setattr(config.wayback_config, key, value)
        
        # Common Crawl config
        cc_settings = archive_config.get('common_crawl', {})
        for key, value in cc_settings.items():
            if hasattr(config.common_crawl_config, key):
                setattr(config.common_crawl_config, key, value)
        
        # Routing config
        if 'fallback_strategy' in archive_config:
            try:
                config.fallback_strategy = FallbackStrategy(archive_config['fallback_strategy'])
            except ValueError:
                pass
        
        if 'fallback_delay_seconds' in archive_config:
            config.fallback_delay_seconds = archive_config['fallback_delay_seconds']
    
    # Disable fallback sources if not enabled
    if not fallback_enabled:
        if archive_source == ArchiveSource.WAYBACK_MACHINE:
            config.common_crawl_config.enabled = False
        elif archive_source == ArchiveSource.COMMON_CRAWL:
            config.wayback_config.enabled = False
        # For HYBRID mode, keep both enabled
    
    return config


# Export public interface
__all__ = [
    'ArchiveServiceRouter',
    'RoutingConfig',
    'ArchiveSourceConfig', 
    'FallbackStrategy',
    'ArchiveQueryMetrics',
    'ArchiveSourceMetrics',
    'ArchiveServiceRouterException',
    'AllSourcesFailedException',
    'query_archive_unified',
    'create_routing_config_from_project'
]