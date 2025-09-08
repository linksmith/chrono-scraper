"""
Enhanced Archive Service Router with comprehensive fallback strategies.
Extends the original router to include proxy-enabled Common Crawl, direct index processing,
and Internet Archive fallback for maximum reliability.
"""
import asyncio
import logging
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass

from .archive_service_router import (
    ArchiveServiceRouter, ArchiveSourceConfig, RoutingConfig,
    ArchiveSource, AllSourcesFailedException
)
from .archive_strategies_extended import (
    CommonCrawlProxyStrategy,
    CommonCrawlDirectStrategy,
    InternetArchiveStrategy,
    SmartproxyCommonCrawlStrategy
)
from .circuit_breaker import circuit_registry, CircuitBreakerConfig
from .wayback_machine import CDXRecord

logger = logging.getLogger(__name__)


@dataclass
class EnhancedRoutingConfig(RoutingConfig):
    """Enhanced routing configuration with new strategy options"""
    
    # Proxy configuration
    enable_proxy_fallback: bool = True
    enable_smartproxy_fallback: bool = True  # Use configured Smartproxy credentials
    proxy_list: Optional[List[Dict[str, str]]] = None
    
    # Direct processing configuration  
    enable_direct_fallback: bool = True
    direct_cache_dir: Optional[str] = None
    
    # Internet Archive configuration
    enable_ia_fallback: bool = True
    
    # Enhanced fallback strategy
    enhanced_fallback_enabled: bool = True
    max_fallback_attempts: int = 5
    # Hard cap (seconds) per strategy attempt to prevent long internal retries from blocking fallback
    per_strategy_timeout_seconds: float = 75.0


class EnhancedArchiveServiceRouter(ArchiveServiceRouter):
    """
    Enhanced archive service router with comprehensive fallback strategies.
    
    Fallback Order:
    1. Wayback Machine (original)
    2. Common Crawl (original) 
    3. **Smartproxy Common Crawl** (uses your configured DECODO credentials)
    4. Common Crawl with Generic Proxy Rotation
    5. Direct Common Crawl Index Processing
    6. Internet Archive (additional fallback)
    
    This provides maximum resilience against API blocks and service outages.
    """
    
    def __init__(self, enhanced_config: Optional[EnhancedRoutingConfig] = None):
        # Initialize base router with standard config
        base_config = RoutingConfig()
        if enhanced_config:
            # Copy base settings
            for field_name, field_def in RoutingConfig.__dataclass_fields__.items():
                if hasattr(enhanced_config, field_name):
                    setattr(base_config, field_name, getattr(enhanced_config, field_name))
        
        super().__init__(base_config)
        
        # Store enhanced config
        self.enhanced_config = enhanced_config or EnhancedRoutingConfig()
        
        # Initialize enhanced strategies
        self._init_enhanced_strategies()
        
        logger.info("Initialized EnhancedArchiveServiceRouter with comprehensive fallback")
    
    def _init_enhanced_strategies(self):
        """Initialize the new fallback strategies"""
        
        # Add circuit breakers for new strategies
        if self.enhanced_config.enable_smartproxy_fallback:
            smartproxy_config = CircuitBreakerConfig(
                failure_threshold=3,
                success_threshold=2,
                timeout_seconds=180,  # Longer timeout for proxy
                max_timeout_seconds=900,
                exponential_backoff=True
            )
            self.smartproxy_breaker = circuit_registry.get_breaker("smartproxy_common_crawl", smartproxy_config)
        
        if self.enhanced_config.enable_proxy_fallback:
            proxy_config = CircuitBreakerConfig(
                failure_threshold=3,
                success_threshold=2,
                timeout_seconds=120,
                max_timeout_seconds=600,
                exponential_backoff=True
            )
            self.proxy_breaker = circuit_registry.get_breaker("common_crawl_proxy", proxy_config)
        
        if self.enhanced_config.enable_direct_fallback:
            direct_config = CircuitBreakerConfig(
                failure_threshold=2,  # Direct processing is more reliable
                success_threshold=1,
                timeout_seconds=300,  # Longer timeout for processing
                max_timeout_seconds=1200,
                exponential_backoff=True
            )
            self.direct_breaker = circuit_registry.get_breaker("common_crawl_direct", direct_config)
        
        if self.enhanced_config.enable_ia_fallback:
            ia_config = CircuitBreakerConfig(
                failure_threshold=3,
                success_threshold=2,
                timeout_seconds=60,
                max_timeout_seconds=300,
                exponential_backoff=True
            )
            self.ia_breaker = circuit_registry.get_breaker("internet_archive", ia_config)
        
        # Add new strategies to the strategies dict
        enhanced_strategies = {}
        
        if self.enhanced_config.enable_smartproxy_fallback:
            enhanced_strategies["smartproxy_common_crawl"] = SmartproxyCommonCrawlStrategy(
                ArchiveSourceConfig(page_size=2000, max_pages=3),  # Conservative with Smartproxy
                self.smartproxy_breaker
            )
        
        if self.enhanced_config.enable_proxy_fallback:
            enhanced_strategies["common_crawl_proxy"] = CommonCrawlProxyStrategy(
                ArchiveSourceConfig(page_size=2000, max_pages=3),  # Conservative with proxy
                self.proxy_breaker,
                proxy_list=self.enhanced_config.proxy_list
            )
        
        if self.enhanced_config.enable_direct_fallback:
            enhanced_strategies["common_crawl_direct"] = CommonCrawlDirectStrategy(
                ArchiveSourceConfig(page_size=5000, max_pages=3),  # Direct can handle more
                self.direct_breaker,
                cache_dir=self.enhanced_config.direct_cache_dir
            )
        
        if self.enhanced_config.enable_ia_fallback:
            enhanced_strategies["internet_archive"] = InternetArchiveStrategy(
                ArchiveSourceConfig(page_size=3000, max_pages=5),  # IA is stable
                self.ia_breaker
            )
        
        # Update strategies dictionary
        self.strategies.update(enhanced_strategies)
        
        # Update metrics tracking
        for strategy_name in enhanced_strategies.keys():
            from .archive_service_router import ArchiveSourceMetrics
            self.source_metrics[strategy_name] = ArchiveSourceMetrics(strategy_name)
        
        logger.info(f"Added {len(enhanced_strategies)} enhanced fallback strategies")
    
    def _determine_enhanced_source_order(self, archive_source: ArchiveSource) -> List[str]:
        """
        Determine comprehensive source order with enhanced fallbacks.
        """
        # Start with original source order
        sources = self._determine_source_order(archive_source)
        
        if not self.enhanced_config.enhanced_fallback_enabled:
            return sources
        
        # Add enhanced fallback strategies
        enhanced_sources = []
        
        # For Common Crawl projects, add proxy and direct fallbacks
        if archive_source in [ArchiveSource.COMMON_CRAWL, ArchiveSource.HYBRID]:
            if self.enhanced_config.enable_smartproxy_fallback:
                enhanced_sources.append("smartproxy_common_crawl")  # First proxy choice
            if self.enhanced_config.enable_proxy_fallback:
                enhanced_sources.append("common_crawl_proxy")       # Generic proxy fallback
            if self.enhanced_config.enable_direct_fallback:
                enhanced_sources.append("common_crawl_direct")      # Direct processing
        
        # Always add Internet Archive as final fallback if enabled
        if self.enhanced_config.enable_ia_fallback:
            enhanced_sources.append("internet_archive")
        
        # Combine original and enhanced sources, removing duplicates
        final_sources = sources + [s for s in enhanced_sources if s not in sources]
        
        logger.info(f"Enhanced source order: {final_sources}")
        return final_sources
    
    async def query_archive_unified(
        self,
        domain: str,
        from_date: str,
        to_date: str,
        archive_source: ArchiveSource = ArchiveSource.HYBRID,
        match_type: str = "domain",
        url_path: Optional[str] = None
    ) -> Tuple[List[CDXRecord], Dict[str, any]]:
        """
        Enhanced unified query method with comprehensive fallback logic.
        """
        # Get enhanced source order
        source_order = self._determine_enhanced_source_order(archive_source)
        
        # Limit attempts based on configuration
        max_attempts = min(len(source_order), self.enhanced_config.max_fallback_attempts)
        source_order = source_order[:max_attempts]
        
        query_start = asyncio.get_event_loop().time()
        attempts = []
        
        logger.info(f"Starting enhanced archive query for {domain} "
                   f"with {len(source_order)} fallback strategies")
        
        for attempt, source_name in enumerate(source_order, 1):
            if source_name not in self.strategies:
                logger.warning(f"Strategy {source_name} not available, skipping")
                continue
            
            strategy = self.strategies[source_name]
            attempt_start = asyncio.get_event_loop().time()
            
            logger.info(f"Attempt {attempt}/{len(source_order)}: Trying {source_name}")
            
            try:
                # Execute query with strategy under a strict timeout so fallbacks are timely
                timeout_seconds = float(getattr(self.enhanced_config, 'per_strategy_timeout_seconds', 75.0) or 75.0)
                records, filter_stats = await asyncio.wait_for(
                    strategy.query_archive(domain, from_date, to_date, match_type, url_path),
                    timeout=timeout_seconds
                )
                
                # Calculate metrics
                duration = asyncio.get_event_loop().time() - attempt_start
                
                # Update metrics
                self.source_metrics[source_name].record_success(duration)
                
                # Record attempt info
                attempts.append({
                    "source": source_name,
                    "success": True,
                    "duration": duration,
                    "records": len(records)
                })
                
                # Success! Return results
                total_duration = asyncio.get_event_loop().time() - query_start
                
                result_stats = {
                    "successful_source": source_name,
                    "total_duration": total_duration,
                    "attempts": attempts,
                    "total_records": len(records),
                    "final_count": filter_stats.get("final_count", len(records)),
                    "fallback_used": attempt > 1,
                    "primary_source": source_order[0]
                }
                result_stats.update(filter_stats)
                
                logger.info(f"Enhanced query successful via {source_name} "
                           f"after {attempt} attempts: {len(records)} records")
                
                return records, result_stats
                
            except asyncio.TimeoutError as e:
                duration = asyncio.get_event_loop().time() - attempt_start
                # Treat as timeout for classification
                error_type = "strategy_timeout"
                self.source_metrics[source_name].record_failure(duration, error_type)
                attempts.append({
                    "source": source_name,
                    "success": False,
                    "duration": duration,
                    "error": "Timed out",
                    "error_type": error_type
                })
                logger.warning(f"Strategy {source_name} timed out after {timeout_seconds}s")
                if attempt < len(source_order):
                    await asyncio.sleep(1)
                continue
            except Exception as e:
                duration = asyncio.get_event_loop().time() - attempt_start
                error_type = strategy.get_error_type(e)
                
                # Update metrics
                self.source_metrics[source_name].record_failure(duration, error_type)
                
                # Record attempt info
                attempts.append({
                    "source": source_name,
                    "success": False,
                    "duration": duration,
                    "error": str(e),
                    "error_type": error_type
                })
                
                logger.warning(f"Strategy {source_name} failed: {e}")
                
                # If this error is not retriable, skip remaining attempts for this strategy type
                if not strategy.is_retriable_error(e):
                    logger.info(f"Non-retriable error from {source_name}, continuing to next strategy")
                
                # Short delay between attempts
                if attempt < len(source_order):
                    await asyncio.sleep(1)
        
        # All strategies failed
        total_duration = asyncio.get_event_loop().time() - query_start
        
        logger.error(f"All {len(source_order)} enhanced strategies failed for {domain}")
        
        raise AllSourcesFailedException(
            f"All {len(source_order)} archive sources failed for domain {domain}",
            attempts
        )
    
    def get_enhanced_status(self) -> Dict[str, any]:
        """Get comprehensive status including enhanced strategies"""
        base_status = super().get_health_status()
        
        # Add enhanced strategy status
        enhanced_sources = {}
        
        for source_name in ["smartproxy_common_crawl", "common_crawl_proxy", "common_crawl_direct", "internet_archive"]:
            if source_name in self.strategies:
                circuit_breaker = getattr(self, f"{source_name.split('_')[0]}_breaker", None)
                if source_name == "smartproxy_common_crawl":
                    circuit_breaker = getattr(self, "smartproxy_breaker", None)
                elif source_name == "common_crawl_proxy":
                    circuit_breaker = getattr(self, "proxy_breaker", None)
                elif source_name == "common_crawl_direct":
                    circuit_breaker = getattr(self, "direct_breaker", None)
                elif source_name == "internet_archive":
                    circuit_breaker = getattr(self, "ia_breaker", None)
                
                cb_status = circuit_breaker.get_status() if circuit_breaker else {"state": "unknown"}
                metrics = self.source_metrics.get(source_name)
                
                enhanced_sources[source_name] = {
                    "healthy": cb_status.get("state") != "open" and (metrics.is_healthy if metrics else True),
                    "circuit_breaker_state": cb_status.get("state"),
                    "success_rate": round(metrics.success_rate, 2) if metrics else 0.0,
                    "last_success": (metrics.last_success_time.isoformat() if metrics and metrics.last_success_time else None)
                }
        
        # Combine with base status
        if "sources" not in base_status:
            base_status["sources"] = {}
        
        base_status["sources"].update(enhanced_sources)
        base_status["enhanced_fallback_enabled"] = self.enhanced_config.enhanced_fallback_enabled
        base_status["total_strategies"] = len(self.strategies)
        
        return base_status


# Convenience function for creating enhanced router
def create_enhanced_routing_config_from_project(project) -> EnhancedRoutingConfig:
    """Create enhanced routing configuration from project settings"""
    from .archive_service_router import create_routing_config_from_project
    
    # Extract project-level archive routing inputs for the base config
    # Accept both enum and string for archive_source
    if isinstance(getattr(project, 'archive_source', None), str):
        archive_source_value = project.archive_source
    else:
        try:
            archive_source_value = project.archive_source.value
        except Exception:
            archive_source_value = "wayback"

    fallback_enabled = getattr(project, 'fallback_enabled', True)
    archive_config = getattr(project, 'archive_config', {}) or {}

    # Get base config using the correct signature
    base_config = create_routing_config_from_project(
        archive_source=archive_source_value,
        fallback_enabled=fallback_enabled,
        archive_config=archive_config
    )
    
    # Create enhanced config
    enhanced_config = EnhancedRoutingConfig()
    
    # Copy base settings
    for field_name in RoutingConfig.__dataclass_fields__.keys():
        if hasattr(base_config, field_name):
            setattr(enhanced_config, field_name, getattr(base_config, field_name))
    
    # Add enhanced settings based on project configuration
    archive_config = getattr(project, 'archive_config', {}) or {}
    
    # Enable Smartproxy fallback for Common Crawl projects (prioritized)
    enhanced_config.enable_smartproxy_fallback = (
        project.archive_source in ['common_crawl', 'hybrid'] and
        archive_config.get('enable_smartproxy_fallback', True)
    )
    
    # Enable generic proxy fallback for Common Crawl projects
    enhanced_config.enable_proxy_fallback = (
        project.archive_source in ['common_crawl', 'hybrid'] and
        archive_config.get('enable_proxy_fallback', False)  # Disabled by default if Smartproxy is available
    )
    
    # Enable direct processing for all projects
    enhanced_config.enable_direct_fallback = archive_config.get('enable_direct_fallback', True)
    
    # Enable Internet Archive for all projects
    enhanced_config.enable_ia_fallback = archive_config.get('enable_ia_fallback', True)
    
    # Enhanced fallback is enabled by default
    enhanced_config.enhanced_fallback_enabled = archive_config.get('enhanced_fallback_enabled', True)
    
    return enhanced_config


# Export enhanced router for use
__all__ = [
    'EnhancedArchiveServiceRouter',
    'EnhancedRoutingConfig',
    'create_enhanced_routing_config_from_project'
]