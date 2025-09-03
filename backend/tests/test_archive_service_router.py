"""
Integration tests for ArchiveServiceRouter functionality.

Tests cover:
- Fallback scenarios (Wayback Machine 522 error → Common Crawl fallback)
- Source selection based on project configuration 
- Circuit breaker behavior and recovery
- Performance metrics collection and reporting
- Configuration handling for different archive_config scenarios
- Routing logic for HYBRID, WAYBACK_MACHINE, and COMMON_CRAWL modes
"""
import asyncio
import pytest
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from datetime import datetime
from typing import List, Dict, Any

from app.services.archive_service_router import (
    ArchiveServiceRouter,
    RoutingConfig,
    ArchiveSourceConfig,
    FallbackStrategy,
    ArchiveQueryMetrics,
    ArchiveSourceMetrics,
    ArchiveServiceRouterException,
    AllSourcesFailedException,
    WaybackMachineStrategy,
    CommonCrawlStrategy,
    query_archive_unified,
    create_routing_config_from_project
)
from app.models.project import ArchiveSource
from app.services.wayback_machine import CDXRecord, CDXAPIException
from app.services.common_crawl_service import CommonCrawlException, CommonCrawlAPIException
from app.services.circuit_breaker import CircuitBreakerOpenException


class TestArchiveServiceRouter:
    """Test suite for ArchiveServiceRouter class"""

    @pytest.fixture
    def routing_config(self):
        """Create a test routing configuration"""
        return RoutingConfig(
            fallback_strategy=FallbackStrategy.CIRCUIT_BREAKER,
            fallback_delay_seconds=1.0,
            exponential_backoff=True,
            max_fallback_delay=10.0,
            wayback_config=ArchiveSourceConfig(
                enabled=True,
                timeout_seconds=60,
                max_retries=3,
                page_size=1000,
                priority=1
            ),
            common_crawl_config=ArchiveSourceConfig(
                enabled=True,
                timeout_seconds=120,
                max_retries=5,
                page_size=5000,
                priority=2
            )
        )

    @pytest.fixture
    def router(self, routing_config):
        """Create an ArchiveServiceRouter instance"""
        return ArchiveServiceRouter(routing_config)

    @pytest.fixture
    def mock_cdx_records(self):
        """Create mock CDX records for testing"""
        return [
            CDXRecord(
                timestamp="20240101120000",
                original_url="https://example.com/page1",
                mime_type="text/html",
                status_code="200",
                digest="sha1:DIGEST1",
                length="5000"
            ),
            CDXRecord(
                timestamp="20240101130000", 
                original_url="https://example.com/page2",
                mime_type="text/html",
                status_code="200",
                digest="sha1:DIGEST2",
                length="3000"
            )
        ]

    def test_router_initialization(self, router):
        """Test router initialization with proper circuit breakers and strategies"""
        assert router.config is not None
        assert router.wayback_breaker is not None
        assert router.common_crawl_breaker is not None
        assert "wayback_machine" in router.strategies
        assert "common_crawl" in router.strategies
        assert len(router.source_metrics) == 2

    def test_determine_source_order_wayback_only(self, router):
        """Test source ordering for Wayback Machine only"""
        order = router._determine_source_order(ArchiveSource.WAYBACK_MACHINE)
        assert order == ["wayback_machine"]

    def test_determine_source_order_common_crawl_only(self, router):
        """Test source ordering for Common Crawl only"""
        order = router._determine_source_order(ArchiveSource.COMMON_CRAWL)
        assert order == ["common_crawl"]

    def test_determine_source_order_hybrid_mode(self, router):
        """Test source ordering for hybrid mode (priority-based)"""
        order = router._determine_source_order(ArchiveSource.HYBRID)
        # Should be ordered by priority (Wayback Machine first, then Common Crawl)
        assert order == ["wayback_machine", "common_crawl"]

    def test_should_attempt_fallback_immediate_strategy(self, router):
        """Test fallback decision with immediate strategy"""
        router.config.fallback_strategy = FallbackStrategy.IMMEDIATE
        strategy = router.strategies["wayback_machine"]
        
        # Should always attempt fallback with immediate strategy
        assert router._should_attempt_fallback(
            Exception("Any error"), strategy, fallback_available=True
        ) == True
        
        # Should not fallback if no fallback available
        assert router._should_attempt_fallback(
            Exception("Any error"), strategy, fallback_available=False
        ) == False

    def test_should_attempt_fallback_retry_then_fallback_strategy(self, router):
        """Test fallback decision with retry then fallback strategy"""
        router.config.fallback_strategy = FallbackStrategy.RETRY_THEN_FALLBACK
        strategy = router.strategies["wayback_machine"]
        
        # Should fallback on non-retriable error
        non_retriable_error = CDXAPIException("401 Unauthorized")
        assert router._should_attempt_fallback(
            non_retriable_error, strategy, fallback_available=True
        ) == True
        
        # Should fallback on circuit breaker open
        cb_error = CircuitBreakerOpenException("Circuit breaker open")
        assert router._should_attempt_fallback(
            cb_error, strategy, fallback_available=True
        ) == True
        
        # Should not fallback on retriable error
        retriable_error = CDXAPIException("522 Connection timeout") 
        assert router._should_attempt_fallback(
            retriable_error, strategy, fallback_available=True
        ) == False

    def test_should_attempt_fallback_circuit_breaker_strategy(self, router):
        """Test fallback decision with circuit breaker strategy"""
        router.config.fallback_strategy = FallbackStrategy.CIRCUIT_BREAKER
        strategy = router.strategies["wayback_machine"]
        
        # Should only fallback on circuit breaker open
        cb_error = CircuitBreakerOpenException("Circuit breaker open")
        assert router._should_attempt_fallback(
            cb_error, strategy, fallback_available=True
        ) == True
        
        # Should not fallback on other errors
        other_error = CDXAPIException("Some API error")
        assert router._should_attempt_fallback(
            other_error, strategy, fallback_available=True
        ) == False

    @pytest.mark.asyncio
    async def test_query_archive_wayback_success(self, router, mock_cdx_records):
        """Test successful query using Wayback Machine"""
        with patch.object(router.strategies["wayback_machine"], 'query_archive') as mock_wayback:
            mock_wayback.return_value = (mock_cdx_records, {"fetched_pages": 1})
            
            records, stats = await router.query_archive(
                domain="example.com",
                from_date="20240101", 
                to_date="20241231",
                project_config={"archive_source": ArchiveSource.WAYBACK_MACHINE}
            )
            
            assert len(records) == 2
            assert records == mock_cdx_records
            assert stats["successful_source"] == "wayback_machine"
            assert stats["fallback_used"] == False
            
            mock_wayback.assert_called_once()

    @pytest.mark.asyncio
    async def test_query_archive_common_crawl_success(self, router, mock_cdx_records):
        """Test successful query using Common Crawl"""
        with patch.object(router.strategies["common_crawl"], 'query_archive') as mock_cc:
            mock_cc.return_value = (mock_cdx_records, {"fetched_pages": 1})
            
            records, stats = await router.query_archive(
                domain="example.com",
                from_date="20240101",
                to_date="20241231", 
                project_config={"archive_source": ArchiveSource.COMMON_CRAWL}
            )
            
            assert len(records) == 2
            assert records == mock_cdx_records
            assert stats["successful_source"] == "common_crawl"
            assert stats["fallback_used"] == False
            
            mock_cc.assert_called_once()

    @pytest.mark.asyncio
    async def test_fallback_522_error_scenario(self, router, mock_cdx_records):
        """Test fallback from Wayback Machine 522 error to Common Crawl"""
        router.config.fallback_strategy = FallbackStrategy.IMMEDIATE
        
        wayback_522_error = CDXAPIException("522 Connection timed out")
        
        with patch.object(router.strategies["wayback_machine"], 'query_archive') as mock_wayback, \
             patch.object(router.strategies["common_crawl"], 'query_archive') as mock_cc:
            
            # Wayback Machine fails with 522
            mock_wayback.side_effect = wayback_522_error
            # Common Crawl succeeds
            mock_cc.return_value = (mock_cdx_records, {"fetched_pages": 1})
            
            records, stats = await router.query_archive(
                domain="example.com",
                from_date="20240101",
                to_date="20241231",
                project_config={"archive_source": ArchiveSource.HYBRID}
            )
            
            assert len(records) == 2
            assert records == mock_cdx_records
            assert stats["successful_source"] == "common_crawl"
            assert stats["fallback_used"] == True
            assert len(stats["attempts"]) == 2
            
            # First attempt should be Wayback Machine (failed)
            assert stats["attempts"][0]["source"] == "wayback_machine"
            assert stats["attempts"][0]["success"] == False
            
            # Second attempt should be Common Crawl (succeeded)
            assert stats["attempts"][1]["source"] == "common_crawl"
            assert stats["attempts"][1]["success"] == True
            
            mock_wayback.assert_called_once()
            mock_cc.assert_called_once()

    @pytest.mark.asyncio 
    async def test_fallback_with_exponential_backoff(self, router, mock_cdx_records):
        """Test fallback with exponential backoff delay"""
        router.config.fallback_strategy = FallbackStrategy.IMMEDIATE
        router.config.exponential_backoff = True
        router.config.fallback_delay_seconds = 0.1  # Short delay for testing
        router.config.max_fallback_delay = 0.5
        
        # Create a three-source scenario (add a third mock source for testing)
        router.config.wayback_config.priority = 1
        router.config.common_crawl_config.priority = 2
        
        wayback_error = CDXAPIException("503 Service unavailable")
        cc_error = CommonCrawlAPIException("Rate limit exceeded")
        
        with patch.object(router.strategies["wayback_machine"], 'query_archive') as mock_wayback, \
             patch.object(router.strategies["common_crawl"], 'query_archive') as mock_cc:
            
            # Both sources fail initially
            mock_wayback.side_effect = wayback_error
            mock_cc.side_effect = cc_error
            
            start_time = asyncio.get_event_loop().time()
            
            with pytest.raises(AllSourcesFailedException):
                await router.query_archive(
                    domain="example.com",
                    from_date="20240101",
                    to_date="20241231",
                    project_config={"archive_source": ArchiveSource.HYBRID}
                )
            
            end_time = asyncio.get_event_loop().time()
            
            # Should have waited for fallback delay
            assert (end_time - start_time) >= 0.1  # At least the initial delay
            
            mock_wayback.assert_called_once()
            mock_cc.assert_called_once()

    @pytest.mark.asyncio
    async def test_all_sources_failed_exception(self, router):
        """Test AllSourcesFailedException when all sources fail"""
        wayback_error = CDXAPIException("Wayback Machine unavailable")
        cc_error = CommonCrawlAPIException("Common Crawl unavailable")
        
        with patch.object(router.strategies["wayback_machine"], 'query_archive') as mock_wayback, \
             patch.object(router.strategies["common_crawl"], 'query_archive') as mock_cc:
            
            mock_wayback.side_effect = wayback_error
            mock_cc.side_effect = cc_error
            
            with pytest.raises(AllSourcesFailedException) as exc_info:
                await router.query_archive(
                    domain="example.com",
                    from_date="20240101",
                    to_date="20241231",
                    project_config={"archive_source": ArchiveSource.HYBRID}
                )
            
            assert "All configured archive sources failed" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_fallback_disabled_single_source(self, router, mock_cdx_records):
        """Test behavior when fallback is disabled"""
        wayback_error = CDXAPIException("522 Connection timed out")
        
        with patch.object(router.strategies["wayback_machine"], 'query_archive') as mock_wayback, \
             patch.object(router.strategies["common_crawl"], 'query_archive') as mock_cc:
            
            mock_wayback.side_effect = wayback_error
            
            with pytest.raises(AllSourcesFailedException):
                await router.query_archive(
                    domain="example.com", 
                    from_date="20240101",
                    to_date="20241231",
                    project_config={
                        "archive_source": ArchiveSource.WAYBACK_MACHINE,
                        "fallback_enabled": False
                    }
                )
            
            mock_wayback.assert_called_once()
            mock_cc.assert_not_called()  # Should not attempt fallback

    def test_apply_project_config(self, router):
        """Test applying project-specific configuration"""
        archive_config = {
            "wayback_machine": {
                "timeout_seconds": 90,
                "page_size": 2000,
                "max_pages": 10
            },
            "common_crawl": {
                "timeout_seconds": 180,
                "page_size": 3000,
                "max_retries": 8
            },
            "fallback_strategy": "immediate",
            "fallback_delay_seconds": 2.0
        }
        
        router._apply_project_config(archive_config)
        
        # Check Wayback Machine config
        assert router.config.wayback_config.timeout_seconds == 90
        assert router.config.wayback_config.page_size == 2000
        assert router.config.wayback_config.max_pages == 10
        
        # Check Common Crawl config  
        assert router.config.common_crawl_config.timeout_seconds == 180
        assert router.config.common_crawl_config.page_size == 3000
        assert router.config.common_crawl_config.max_retries == 8
        
        # Check routing config
        assert router.config.fallback_strategy == FallbackStrategy.IMMEDIATE
        assert router.config.fallback_delay_seconds == 2.0

    def test_performance_metrics_tracking(self, router):
        """Test performance metrics collection and tracking"""
        # Initial state
        initial_metrics = router.get_performance_metrics()
        assert initial_metrics["overall"]["total_queries"] == 0
        
        # Create mock query metrics
        wb_metrics = ArchiveQueryMetrics(source="wayback_machine", start_time=1000.0)
        wb_metrics.mark_success(records_count=10, pages_count=2)
        
        cc_metrics = ArchiveQueryMetrics(source="common_crawl", start_time=1001.0) 
        cc_metrics.mark_failure("timeout", "Request timed out")
        
        # Update source metrics
        router.source_metrics["wayback_machine"].update_from_query(wb_metrics)
        router.source_metrics["common_crawl"].update_from_query(cc_metrics)
        
        # Get updated metrics
        metrics = router.get_performance_metrics()
        
        assert metrics["overall"]["total_queries"] == 2
        assert metrics["sources"]["wayback_machine"]["successful_queries"] == 1
        assert metrics["sources"]["wayback_machine"]["total_records"] == 10
        assert metrics["sources"]["wayback_machine"]["success_rate"] == 100.0
        
        assert metrics["sources"]["common_crawl"]["failed_queries"] == 1
        assert metrics["sources"]["common_crawl"]["success_rate"] == 0.0
        assert "timeout" in metrics["sources"]["common_crawl"]["error_counts"]

    def test_health_status_reporting(self, router):
        """Test health status reporting"""
        # Mock circuit breaker states
        router.wayback_breaker.get_status = Mock(return_value={"state": "closed"})
        router.common_crawl_breaker.get_status = Mock(return_value={"state": "open"})
        
        # Set success rates
        router.source_metrics["wayback_machine"].successful_queries = 90
        router.source_metrics["wayback_machine"].total_queries = 100
        router.source_metrics["common_crawl"].successful_queries = 60
        router.source_metrics["common_crawl"].total_queries = 100
        
        health = router.get_health_status()
        
        assert health["overall_status"] == "degraded"  # Mixed health
        assert health["sources"]["wayback_machine"]["healthy"] == True  # >80% success + closed CB
        assert health["sources"]["common_crawl"]["healthy"] == False  # Open CB
        assert health["sources"]["wayback_machine"]["success_rate"] == 90.0
        assert health["sources"]["common_crawl"]["success_rate"] == 60.0

    def test_reset_metrics(self, router):
        """Test metrics reset functionality"""
        # Add some metrics
        wb_metrics = ArchiveQueryMetrics(source="wayback_machine", start_time=1000.0)
        wb_metrics.mark_success(records_count=5)
        router.source_metrics["wayback_machine"].update_from_query(wb_metrics)
        router._add_to_query_history(wb_metrics)
        
        # Verify metrics exist
        assert router.source_metrics["wayback_machine"].total_queries > 0
        assert len(router.query_history) > 0
        
        # Reset metrics
        router.reset_metrics()
        
        # Verify reset
        assert router.source_metrics["wayback_machine"].total_queries == 0
        assert len(router.query_history) == 0

    @pytest.mark.asyncio
    async def test_circuit_breaker_open_fallback(self, router, mock_cdx_records):
        """Test fallback when circuit breaker is open"""
        router.config.fallback_strategy = FallbackStrategy.CIRCUIT_BREAKER
        
        # Mock circuit breaker open exception
        cb_open_error = CircuitBreakerOpenException("Wayback Machine circuit breaker is open")
        
        with patch.object(router.strategies["wayback_machine"], 'query_archive') as mock_wayback, \
             patch.object(router.strategies["common_crawl"], 'query_archive') as mock_cc:
            
            mock_wayback.side_effect = cb_open_error
            mock_cc.return_value = (mock_cdx_records, {"fetched_pages": 1})
            
            records, stats = await router.query_archive(
                domain="example.com",
                from_date="20240101",
                to_date="20241231",
                project_config={"archive_source": ArchiveSource.HYBRID}
            )
            
            assert len(records) == 2
            assert stats["successful_source"] == "common_crawl"
            assert stats["fallback_used"] == True

    @pytest.mark.asyncio
    async def test_query_history_tracking(self, router, mock_cdx_records):
        """Test query history tracking and limit enforcement"""
        # Mock successful queries to track history
        with patch.object(router.strategies["wayback_machine"], 'query_archive') as mock_wayback:
            mock_wayback.return_value = (mock_cdx_records, {"fetched_pages": 1})
            
            # Execute multiple queries
            for i in range(5):
                await router.query_archive(
                    domain=f"example{i}.com",
                    from_date="20240101",
                    to_date="20241231",
                    project_config={"archive_source": ArchiveSource.WAYBACK_MACHINE}
                )
            
            # Check query history
            assert len(router.query_history) == 5
            
            # Test history limit (set low for testing)
            router.max_query_history = 3
            
            # Add more queries
            for i in range(5, 8):
                await router.query_archive(
                    domain=f"example{i}.com",
                    from_date="20240101", 
                    to_date="20241231",
                    project_config={"archive_source": ArchiveSource.WAYBACK_MACHINE}
                )
            
            # Should keep only the most recent queries
            assert len(router.query_history) == 3


class TestArchiveSourceStrategies:
    """Test suite for individual archive source strategies"""

    @pytest.fixture
    def wayback_strategy(self):
        """Create a Wayback Machine strategy for testing"""
        config = ArchiveSourceConfig(page_size=1000, max_pages=5)
        breaker = Mock()
        return WaybackMachineStrategy(config, breaker)

    @pytest.fixture  
    def common_crawl_strategy(self):
        """Create a Common Crawl strategy for testing"""
        config = ArchiveSourceConfig(page_size=2000, max_pages=10)
        breaker = Mock()
        return CommonCrawlStrategy(config, breaker)

    def test_wayback_strategy_error_classification(self, wayback_strategy):
        """Test Wayback Machine error type classification"""
        # Test 522 error
        error_522 = CDXAPIException("522 Connection timed out")
        assert wayback_strategy.get_error_type(error_522) == "wayback_522_timeout"
        assert wayback_strategy.is_retriable_error(error_522) == True
        
        # Test 503 error
        error_503 = CDXAPIException("503 Service unavailable")
        assert wayback_strategy.get_error_type(error_503) == "wayback_503_unavailable"
        assert wayback_strategy.is_retriable_error(error_503) == True
        
        # Test timeout error
        timeout_error = TimeoutError("Request timed out")
        assert wayback_strategy.get_error_type(timeout_error) == "wayback_timeout"
        assert wayback_strategy.is_retriable_error(timeout_error) == True
        
        # Test non-retriable error
        auth_error = CDXAPIException("401 Unauthorized")
        assert wayback_strategy.get_error_type(auth_error) == "wayback_api_error"
        assert wayback_strategy.is_retriable_error(auth_error) == False

    def test_common_crawl_strategy_error_classification(self, common_crawl_strategy):
        """Test Common Crawl error type classification"""
        # Test rate limit error
        rate_limit_error = CommonCrawlAPIException("Rate limit exceeded")
        assert common_crawl_strategy.get_error_type(rate_limit_error) == "common_crawl_rate_limit"
        assert common_crawl_strategy.is_retriable_error(rate_limit_error) == True
        
        # Test timeout error
        timeout_error = CommonCrawlAPIException("Request timed out")
        assert common_crawl_strategy.get_error_type(timeout_error) == "common_crawl_timeout"
        assert common_crawl_strategy.is_retriable_error(timeout_error) == True
        
        # Test connection error
        conn_error = ConnectionError("Connection failed")
        assert common_crawl_strategy.get_error_type(conn_error) == "common_crawl_connection_error"
        assert common_crawl_strategy.is_retriable_error(conn_error) == True

    @pytest.mark.asyncio
    async def test_wayback_strategy_query_execution(self, wayback_strategy):
        """Test Wayback Machine strategy query execution"""
        mock_records = [
            CDXRecord(timestamp="20240101120000", original_url="https://example.com/page1",
                     mime_type="text/html", status_code="200", digest="sha1:TEST1", length="1000")
        ]
        
        with patch('app.services.archive_service_router.CDXAPIClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client
            mock_client.fetch_cdx_records_simple.return_value = (mock_records, {"fetched_pages": 1})
            
            # Mock circuit breaker
            wayback_strategy.circuit_breaker.execute = AsyncMock(
                return_value=(mock_records, {"fetched_pages": 1})
            )
            
            records, stats = await wayback_strategy.query_archive(
                domain="example.com",
                from_date="20240101",
                to_date="20241231"
            )
            
            assert len(records) == 1
            assert records[0].original_url == "https://example.com/page1"

    @pytest.mark.asyncio
    async def test_common_crawl_strategy_query_execution(self, common_crawl_strategy):
        """Test Common Crawl strategy query execution"""
        mock_records = [
            CDXRecord(timestamp="20240101120000", original_url="https://example.com/page2",
                     mime_type="text/html", status_code="200", digest="sha1:TEST2", length="2000")
        ]
        
        with patch('app.services.archive_service_router.CommonCrawlService') as mock_service_class:
            mock_service = AsyncMock()
            mock_service_class.return_value.__aenter__.return_value = mock_service
            mock_service.fetch_cdx_records_simple.return_value = (mock_records, {"fetched_pages": 1})
            
            # Mock circuit breaker
            common_crawl_strategy.circuit_breaker.execute = AsyncMock(
                return_value=(mock_records, {"fetched_pages": 1})
            )
            
            records, stats = await common_crawl_strategy.query_archive(
                domain="example.com",
                from_date="20240101",
                to_date="20241231"
            )
            
            assert len(records) == 1
            assert records[0].original_url == "https://example.com/page2"


class TestConvenienceFunctions:
    """Test suite for convenience functions"""

    @pytest.mark.asyncio
    async def test_query_archive_unified_function(self, mock_cdx_records):
        """Test unified archive query convenience function"""
        with patch('app.services.archive_service_router.ArchiveServiceRouter') as mock_router_class:
            mock_router = Mock()
            mock_router_class.return_value = mock_router
            mock_router.query_archive = AsyncMock(return_value=(mock_cdx_records, {"total": 2}))
            
            records, stats = await query_archive_unified(
                domain="example.com",
                from_date="20240101",
                to_date="20241231",
                project_config={"archive_source": ArchiveSource.HYBRID}
            )
            
            assert len(records) == 2
            assert stats["total"] == 2
            
            mock_router.query_archive.assert_called_once_with(
                domain="example.com",
                from_date="20240101", 
                to_date="20241231",
                project_config={"archive_source": ArchiveSource.HYBRID},
                match_type="domain",
                url_path=None
            )

    def test_create_routing_config_from_project(self):
        """Test creating routing config from project settings"""
        archive_config = {
            "wayback_machine": {
                "timeout_seconds": 120,
                "page_size": 1000
            },
            "common_crawl": {
                "timeout_seconds": 180,
                "max_retries": 8
            },
            "fallback_strategy": "immediate",
            "fallback_delay_seconds": 3.0
        }
        
        config = create_routing_config_from_project(
            archive_source=ArchiveSource.HYBRID,
            fallback_enabled=True,
            archive_config=archive_config
        )
        
        assert config.wayback_config.timeout_seconds == 120
        assert config.wayback_config.page_size == 1000
        assert config.common_crawl_config.timeout_seconds == 180
        assert config.common_crawl_config.max_retries == 8
        assert config.fallback_strategy == FallbackStrategy.IMMEDIATE
        assert config.fallback_delay_seconds == 3.0

    def test_create_routing_config_fallback_disabled(self):
        """Test routing config creation with fallback disabled"""
        config = create_routing_config_from_project(
            archive_source=ArchiveSource.WAYBACK_MACHINE,
            fallback_enabled=False
        )
        
        # Wayback Machine should be enabled, Common Crawl should be disabled
        assert config.wayback_config.enabled == True
        assert config.common_crawl_config.enabled == False

    def test_create_routing_config_invalid_fallback_strategy(self):
        """Test handling of invalid fallback strategy"""
        archive_config = {
            "fallback_strategy": "invalid_strategy"  # Invalid
        }
        
        config = create_routing_config_from_project(
            archive_source=ArchiveSource.HYBRID,
            fallback_enabled=True,
            archive_config=archive_config
        )
        
        # Should use default fallback strategy
        assert config.fallback_strategy == FallbackStrategy.CIRCUIT_BREAKER


class TestArchiveQueryMetrics:
    """Test suite for ArchiveQueryMetrics class"""

    def test_query_metrics_initialization(self):
        """Test query metrics initialization"""
        start_time = 1000.0
        metrics = ArchiveQueryMetrics(source="wayback_machine", start_time=start_time)
        
        assert metrics.source == "wayback_machine"
        assert metrics.start_time == start_time
        assert metrics.end_time is None
        assert metrics.success == False
        assert metrics.duration_seconds == 0.0

    def test_mark_success(self):
        """Test marking query as successful"""
        start_time = 1000.0
        metrics = ArchiveQueryMetrics(source="test_source", start_time=start_time)
        
        with patch('time.time', return_value=1005.0):
            metrics.mark_success(records_count=10, pages_count=2)
        
        assert metrics.success == True
        assert metrics.records_retrieved == 10
        assert metrics.pages_fetched == 2
        assert metrics.end_time == 1005.0
        assert metrics.duration_seconds == 5.0

    def test_mark_failure(self):
        """Test marking query as failed"""
        start_time = 1000.0
        metrics = ArchiveQueryMetrics(source="test_source", start_time=start_time)
        
        with patch('time.time', return_value=1003.0):
            metrics.mark_failure("timeout", "Request timed out")
        
        assert metrics.success == False
        assert metrics.error_type == "timeout"
        assert metrics.error_message == "Request timed out"
        assert metrics.end_time == 1003.0
        assert metrics.duration_seconds == 3.0


class TestArchiveSourceMetrics:
    """Test suite for ArchiveSourceMetrics class"""

    def test_source_metrics_initialization(self):
        """Test source metrics initialization"""
        metrics = ArchiveSourceMetrics("wayback_machine")
        
        assert metrics.source_name == "wayback_machine"
        assert metrics.total_queries == 0
        assert metrics.successful_queries == 0
        assert metrics.failed_queries == 0
        assert metrics.success_rate == 0.0
        assert metrics.is_healthy == False

    def test_update_from_successful_query(self):
        """Test updating metrics from successful query"""
        metrics = ArchiveSourceMetrics("test_source")
        
        query_metrics = ArchiveQueryMetrics(source="test_source", start_time=1000.0)
        query_metrics.mark_success(records_count=5, pages_count=1)
        
        with patch('app.services.archive_service_router.datetime') as mock_datetime:
            mock_now = datetime(2024, 1, 1, 12, 0, 0)
            mock_datetime.now.return_value = mock_now
            
            metrics.update_from_query(query_metrics)
        
        assert metrics.total_queries == 1
        assert metrics.successful_queries == 1
        assert metrics.failed_queries == 0
        assert metrics.total_records == 5
        assert metrics.success_rate == 100.0
        assert metrics.is_healthy == True
        assert metrics.last_success_time == mock_now

    def test_update_from_failed_query(self):
        """Test updating metrics from failed query"""
        metrics = ArchiveSourceMetrics("test_source")
        
        query_metrics = ArchiveQueryMetrics(source="test_source", start_time=1000.0)
        query_metrics.mark_failure("timeout", "Request timed out")
        
        with patch('app.services.archive_service_router.datetime') as mock_datetime:
            mock_now = datetime(2024, 1, 1, 12, 0, 0)
            mock_datetime.now.return_value = mock_now
            
            metrics.update_from_query(query_metrics)
        
        assert metrics.total_queries == 1
        assert metrics.successful_queries == 0
        assert metrics.failed_queries == 1
        assert metrics.success_rate == 0.0
        assert metrics.is_healthy == False
        assert metrics.last_failure_time == mock_now
        assert metrics.error_counts["timeout"] == 1

    def test_exponential_moving_average(self):
        """Test exponential moving average calculation for response time"""
        metrics = ArchiveSourceMetrics("test_source")
        
        # First query - should set initial average
        query1 = ArchiveQueryMetrics(source="test_source", start_time=1000.0)
        query1.mark_success()
        query1.end_time = 1005.0  # 5 second duration
        metrics.update_from_query(query1)
        
        assert metrics.avg_response_time == 5.0
        
        # Second query - should use exponential moving average
        query2 = ArchiveQueryMetrics(source="test_source", start_time=1010.0)
        query2.mark_success()
        query2.end_time = 1015.0  # 5 second duration
        metrics.update_from_query(query2)
        
        # EMA formula: alpha * new_value + (1 - alpha) * old_value
        # 0.2 * 5.0 + 0.8 * 5.0 = 5.0
        assert metrics.avg_response_time == 5.0


@pytest.mark.performance
class TestRouterPerformance:
    """Test suite for router performance characteristics"""

    @pytest.mark.asyncio
    async def test_concurrent_queries(self):
        """Test handling multiple concurrent queries"""
        async def mock_query(*args, **kwargs):
            await asyncio.sleep(0.01)  # Small delay
            return [], {"total": 0}
        
        with patch('app.services.archive_service_router.ArchiveServiceRouter.query_archive', mock_query):
            router = ArchiveServiceRouter()
            
            # Execute multiple concurrent queries
            tasks = []
            for i in range(10):
                task = router.query_archive(
                    domain=f"example{i}.com",
                    from_date="20240101",
                    to_date="20241231"
                )
                tasks.append(task)
            
            start_time = asyncio.get_event_loop().time()
            results = await asyncio.gather(*tasks)
            end_time = asyncio.get_event_loop().time()
            
            # Should complete within reasonable time (concurrent execution)
            assert (end_time - start_time) < 0.5  # Much less than 10 * 0.01 = 0.1s
            assert len(results) == 10

    @pytest.mark.asyncio 
    async def test_fallback_performance_impact(self):
        """Test performance impact of fallback scenarios"""
        router = ArchiveServiceRouter()
        router.config.fallback_strategy = FallbackStrategy.IMMEDIATE
        router.config.fallback_delay_seconds = 0.01  # Minimal delay
        
        mock_records = [CDXRecord(timestamp="20240101120000", original_url="https://example.com",
                                 mime_type="text/html", status_code="200", digest="sha1:TEST", length="1000")]
        
        with patch.object(router.strategies["wayback_machine"], 'query_archive') as mock_wayback, \
             patch.object(router.strategies["common_crawl"], 'query_archive') as mock_cc:
            
            # Wayback fails, Common Crawl succeeds
            mock_wayback.side_effect = CDXAPIException("522 timeout")
            mock_cc.return_value = (mock_records, {"fetched_pages": 1})
            
            start_time = asyncio.get_event_loop().time()
            
            records, stats = await router.query_archive(
                domain="example.com",
                from_date="20240101",
                to_date="20241231",
                project_config={"archive_source": ArchiveSource.HYBRID}
            )
            
            end_time = asyncio.get_event_loop().time()
            
            # Should complete quickly despite fallback
            assert (end_time - start_time) < 0.1
            assert len(records) == 1
            assert stats["fallback_used"] == True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])