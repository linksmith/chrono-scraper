"""
Test fixtures and utilities for archive service testing.

This module provides:
- Mock archive service implementations
- Test data generators for CDX records
- Circuit breaker test utilities
- Performance testing helpers
- Archive configuration builders
"""
import asyncio
import pytest
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Generator
from unittest.mock import Mock, AsyncMock, MagicMock
import random
import string
import time

from app.services.wayback_machine import CDXRecord, CDXAPIException
from app.services.common_crawl_service import CommonCrawlException, CommonCrawlAPIException
from app.services.archive_service_router import (
    ArchiveServiceRouter,
    RoutingConfig,
    ArchiveSourceConfig,
    FallbackStrategy,
    ArchiveQueryMetrics,
    ArchiveSourceMetrics
)
from app.services.circuit_breaker import CircuitBreaker, CircuitBreakerConfig
from app.models.project import ArchiveSource, Project


class MockCDXRecord:
    """Factory for creating mock CDX records"""
    
    @staticmethod
    def create(
        timestamp: str = "20240101120000",
        url: str = "https://example.com/test",
        mime_type: str = "text/html",
        status_code: str = "200",
        digest: str = "sha1:TESTDIGEST",
        length: str = "1000"
    ) -> CDXRecord:
        """Create a single mock CDX record"""
        return CDXRecord(
            timestamp=timestamp,
            original_url=url,
            mime_type=mime_type,
            status_code=status_code,
            digest=digest,
            length=length
        )
    
    @staticmethod
    def create_batch(
        count: int = 10,
        domain: str = "example.com",
        date_range: Optional[tuple] = None
    ) -> List[CDXRecord]:
        """Create a batch of mock CDX records"""
        if date_range is None:
            start_date = datetime(2024, 1, 1)
            end_date = datetime(2024, 12, 31)
        else:
            start_date, end_date = date_range
        
        records = []
        for i in range(count):
            # Generate timestamp within date range
            time_diff = end_date - start_date
            random_days = random.randint(0, time_diff.days)
            record_date = start_date + timedelta(days=random_days)
            timestamp = record_date.strftime("%Y%m%d%H%M%S")
            
            # Generate URL
            url = f"https://{domain}/page-{i:04d}"
            
            # Generate digest
            digest_suffix = ''.join(random.choices(string.hexdigits.upper(), k=32))
            digest = f"sha1:{digest_suffix}"
            
            # Random content size
            length = str(random.randint(500, 50000))
            
            record = CDXRecord(
                timestamp=timestamp,
                original_url=url,
                mime_type="text/html",
                status_code="200",
                digest=digest,
                length=length
            )
            records.append(record)
        
        return sorted(records, key=lambda r: r.timestamp)
    
    @staticmethod
    def create_diverse_batch(count: int = 20) -> List[CDXRecord]:
        """Create a diverse batch with different content types and sizes"""
        records = []
        mime_types = ["text/html", "application/pdf", "text/plain", "application/json"]
        status_codes = ["200", "301", "302"]
        domains = ["example.com", "test.org", "demo.net"]
        
        for i in range(count):
            domain = random.choice(domains)
            mime_type = random.choice(mime_types)
            status_code = random.choice(status_codes)
            
            # Generate timestamp
            base_date = datetime(2024, 1, 1)
            random_days = random.randint(0, 365)
            record_date = base_date + timedelta(days=random_days)
            timestamp = record_date.strftime("%Y%m%d%H%M%S")
            
            # Generate URL based on content type
            if mime_type == "application/pdf":
                url = f"https://{domain}/document-{i}.pdf"
            elif mime_type == "application/json":
                url = f"https://{domain}/api/data-{i}.json"
            else:
                url = f"https://{domain}/page-{i}"
            
            # Size varies by content type
            if mime_type == "application/pdf":
                length = str(random.randint(50000, 500000))
            elif mime_type == "application/json":
                length = str(random.randint(100, 10000))
            else:
                length = str(random.randint(1000, 100000))
            
            digest = f"sha1:{''.join(random.choices(string.hexdigits.upper(), k=32))}"
            
            record = CDXRecord(
                timestamp=timestamp,
                original_url=url,
                mime_type=mime_type,
                status_code=status_code,
                digest=digest,
                length=length
            )
            records.append(record)
        
        return records


class MockArchiveService:
    """Mock implementation of archive services for testing"""
    
    def __init__(self, name: str, should_fail: bool = False, failure_rate: float = 0.0):
        self.name = name
        self.should_fail = should_fail
        self.failure_rate = failure_rate
        self.call_count = 0
        self.call_history = []
    
    async def fetch_cdx_records_simple(self, domain_name: str, from_date: str, to_date: str, **kwargs):
        """Mock CDX record fetching"""
        self.call_count += 1
        call_info = {
            "domain": domain_name,
            "from_date": from_date,
            "to_date": to_date,
            "kwargs": kwargs,
            "timestamp": datetime.now()
        }
        self.call_history.append(call_info)
        
        # Simulate failures
        if self.should_fail or (self.failure_rate > 0 and random.random() < self.failure_rate):
            if self.name == "wayback_machine":
                raise CDXAPIException("522 Connection timed out")
            else:
                raise CommonCrawlAPIException("Rate limit exceeded")
        
        # Return mock records
        records = MockCDXRecord.create_batch(count=random.randint(5, 15), domain=domain_name)
        stats = {
            "total_pages": 1,
            "fetched_pages": 1,
            "total_records": len(records),
            "final_count": len(records)
        }
        
        # Add small delay to simulate network
        await asyncio.sleep(0.01)
        
        return records, stats
    
    def reset(self):
        """Reset mock state"""
        self.call_count = 0
        self.call_history.clear()


class MockCircuitBreaker:
    """Mock circuit breaker for testing"""
    
    def __init__(self, name: str, initial_state: str = "closed"):
        self.name = name
        self.state = initial_state
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time = None
        self.last_success_time = None
        self.execute_calls = []
    
    async def execute(self, func):
        """Mock circuit breaker execution"""
        self.execute_calls.append({
            "func": func.__name__ if hasattr(func, '__name__') else str(func),
            "timestamp": datetime.now(),
            "state": self.state
        })
        
        if self.state == "open":
            from app.services.circuit_breaker import CircuitBreakerOpenException
            raise CircuitBreakerOpenException(f"Circuit breaker {self.name} is open")
        
        try:
            result = await func()
            self.success_count += 1
            self.last_success_time = datetime.now()
            
            # Transition to closed if in half-open
            if self.state == "half_open":
                self.state = "closed"
            
            return result
            
        except Exception as e:
            self.failure_count += 1
            self.last_failure_time = datetime.now()
            
            # Transition to open if too many failures
            if self.failure_count >= 5:
                self.state = "open"
            
            raise
    
    def get_status(self) -> Dict[str, Any]:
        """Get circuit breaker status"""
        return {
            "name": self.name,
            "state": self.state,
            "failure_count": self.failure_count,
            "success_count": self.success_count,
            "last_failure_time": self.last_failure_time.isoformat() if self.last_failure_time else None,
            "last_success_time": self.last_success_time.isoformat() if self.last_success_time else None
        }
    
    def force_state(self, state: str):
        """Force circuit breaker to specific state (for testing)"""
        self.state = state
    
    def reset(self):
        """Reset circuit breaker state"""
        self.state = "closed"
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time = None
        self.last_success_time = None
        self.execute_calls.clear()


class ArchiveConfigBuilder:
    """Builder for creating archive configurations"""
    
    def __init__(self):
        self.config = {}
    
    def wayback_machine(
        self,
        timeout_seconds: int = 60,
        page_size: int = 1000,
        max_pages: Optional[int] = None,
        max_retries: int = 3,
        priority: int = 1
    ):
        """Configure Wayback Machine settings"""
        self.config["wayback_machine"] = {
            "timeout_seconds": timeout_seconds,
            "page_size": page_size,
            "max_retries": max_retries,
            "priority": priority
        }
        if max_pages is not None:
            self.config["wayback_machine"]["max_pages"] = max_pages
        return self
    
    def common_crawl(
        self,
        timeout_seconds: int = 120,
        page_size: int = 5000,
        max_pages: Optional[int] = None,
        max_retries: int = 5,
        priority: int = 2
    ):
        """Configure Common Crawl settings"""
        self.config["common_crawl"] = {
            "timeout_seconds": timeout_seconds,
            "page_size": page_size,
            "max_retries": max_retries,
            "priority": priority
        }
        if max_pages is not None:
            self.config["common_crawl"]["max_pages"] = max_pages
        return self
    
    def fallback_strategy(self, strategy: str = "circuit_breaker"):
        """Configure fallback strategy"""
        self.config["fallback_strategy"] = strategy
        return self
    
    def fallback_delay(self, seconds: float = 1.0):
        """Configure fallback delay"""
        self.config["fallback_delay_seconds"] = seconds
        return self
    
    def exponential_backoff(self, enabled: bool = True, max_delay: float = 30.0):
        """Configure exponential backoff"""
        self.config["exponential_backoff"] = enabled
        self.config["max_fallback_delay"] = max_delay
        return self
    
    def custom_settings(self, source: str, **kwargs):
        """Add custom settings for a source"""
        if source not in self.config:
            self.config[source] = {}
        self.config[source]["custom_settings"] = kwargs
        return self
    
    def build(self) -> Dict[str, Any]:
        """Build the configuration dictionary"""
        return self.config.copy()


class PerformanceTimer:
    """Utility for measuring performance in tests"""
    
    def __init__(self, name: str):
        self.name = name
        self.start_time = None
        self.end_time = None
        self.measurements = []
    
    def __enter__(self):
        self.start_time = time.time()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.end_time = time.time()
        duration = self.end_time - self.start_time
        self.measurements.append(duration)
    
    @property
    def duration(self) -> float:
        """Get the last measurement duration"""
        if self.end_time and self.start_time:
            return self.end_time - self.start_time
        return 0.0
    
    @property
    def average_duration(self) -> float:
        """Get average duration across all measurements"""
        if not self.measurements:
            return 0.0
        return sum(self.measurements) / len(self.measurements)
    
    def reset(self):
        """Reset all measurements"""
        self.measurements.clear()
        self.start_time = None
        self.end_time = None


class ArchiveTestHarness:
    """Test harness for comprehensive archive service testing"""
    
    def __init__(self):
        self.mock_wayback = MockArchiveService("wayback_machine")
        self.mock_common_crawl = MockArchiveService("common_crawl")
        self.mock_wayback_breaker = MockCircuitBreaker("wayback_machine")
        self.mock_common_crawl_breaker = MockCircuitBreaker("common_crawl")
        self.router = None
    
    def setup_router(self, routing_config: Optional[RoutingConfig] = None):
        """Setup router with mock services"""
        if routing_config is None:
            routing_config = RoutingConfig()
        
        self.router = ArchiveServiceRouter(routing_config)
        
        # Replace real services with mocks
        self.router.strategies["wayback_machine"].query_archive = AsyncMock(
            side_effect=self._wayback_query_wrapper
        )
        self.router.strategies["common_crawl"].query_archive = AsyncMock(
            side_effect=self._common_crawl_query_wrapper
        )
        
        # Replace circuit breakers
        self.router.wayback_breaker = self.mock_wayback_breaker
        self.router.common_crawl_breaker = self.mock_common_crawl_breaker
    
    async def _wayback_query_wrapper(self, domain: str, from_date: str, to_date: str, **kwargs):
        """Wrapper for wayback mock service"""
        records, stats = await self.mock_wayback.fetch_cdx_records_simple(
            domain, from_date, to_date, **kwargs
        )
        return records, stats
    
    async def _common_crawl_query_wrapper(self, domain: str, from_date: str, to_date: str, **kwargs):
        """Wrapper for common crawl mock service"""
        records, stats = await self.mock_common_crawl.fetch_cdx_records_simple(
            domain, from_date, to_date, **kwargs
        )
        return records, stats
    
    def set_wayback_failure_rate(self, rate: float):
        """Set failure rate for Wayback Machine (0.0 to 1.0)"""
        self.mock_wayback.failure_rate = rate
    
    def set_common_crawl_failure_rate(self, rate: float):
        """Set failure rate for Common Crawl (0.0 to 1.0)"""
        self.mock_common_crawl.failure_rate = rate
    
    def force_wayback_failure(self, should_fail: bool = True):
        """Force Wayback Machine to always fail"""
        self.mock_wayback.should_fail = should_fail
    
    def force_common_crawl_failure(self, should_fail: bool = True):
        """Force Common Crawl to always fail"""
        self.mock_common_crawl.should_fail = should_fail
    
    def force_circuit_breaker_state(self, source: str, state: str):
        """Force circuit breaker to specific state"""
        if source == "wayback_machine":
            self.mock_wayback_breaker.force_state(state)
        elif source == "common_crawl":
            self.mock_common_crawl_breaker.force_state(state)
    
    def get_call_statistics(self) -> Dict[str, Any]:
        """Get statistics about service calls"""
        return {
            "wayback_machine": {
                "call_count": self.mock_wayback.call_count,
                "call_history": self.mock_wayback.call_history,
                "circuit_breaker": self.mock_wayback_breaker.get_status()
            },
            "common_crawl": {
                "call_count": self.mock_common_crawl.call_count,
                "call_history": self.mock_common_crawl.call_history,
                "circuit_breaker": self.mock_common_crawl_breaker.get_status()
            }
        }
    
    def reset_all(self):
        """Reset all mock states"""
        self.mock_wayback.reset()
        self.mock_common_crawl.reset()
        self.mock_wayback_breaker.reset()
        self.mock_common_crawl_breaker.reset()
        if self.router:
            self.router.reset_metrics()


# Pytest fixtures for use across test modules

@pytest.fixture
def mock_cdx_records():
    """Fixture providing mock CDX records"""
    return MockCDXRecord.create_batch(count=10)

@pytest.fixture
def diverse_cdx_records():
    """Fixture providing diverse mock CDX records"""
    return MockCDXRecord.create_diverse_batch(count=20)

@pytest.fixture
def archive_config_builder():
    """Fixture providing archive configuration builder"""
    return ArchiveConfigBuilder()

@pytest.fixture
def performance_timer():
    """Fixture providing performance timer"""
    def _create_timer(name: str = "test_timer"):
        return PerformanceTimer(name)
    return _create_timer

@pytest.fixture
def archive_test_harness():
    """Fixture providing comprehensive test harness"""
    harness = ArchiveTestHarness()
    yield harness
    harness.reset_all()

@pytest.fixture
def wayback_only_config():
    """Fixture providing Wayback Machine only configuration"""
    return ArchiveConfigBuilder().wayback_machine().build()

@pytest.fixture
def common_crawl_only_config():
    """Fixture providing Common Crawl only configuration"""
    return ArchiveConfigBuilder().common_crawl().build()

@pytest.fixture
def hybrid_config():
    """Fixture providing hybrid configuration"""
    return (ArchiveConfigBuilder()
            .wayback_machine(priority=1)
            .common_crawl(priority=2)
            .fallback_strategy("circuit_breaker")
            .fallback_delay(1.0)
            .build())

@pytest.fixture
def complex_archive_config():
    """Fixture providing complex archive configuration"""
    return (ArchiveConfigBuilder()
            .wayback_machine(
                timeout_seconds=90,
                page_size=2000,
                max_pages=20,
                priority=1
            )
            .common_crawl(
                timeout_seconds=150,
                page_size=5000,
                max_pages=50,
                priority=2
            )
            .fallback_strategy("retry_then_fallback")
            .fallback_delay(2.5)
            .exponential_backoff(True, max_delay=60.0)
            .custom_settings("wayback_machine", user_agent="TestBot/1.0", rate_limit=2)
            .custom_settings("common_crawl", collections=["CC-MAIN-2024-10"])
            .build())


class ArchiveTestDataGenerator:
    """Generator for creating test data scenarios"""
    
    @staticmethod
    def create_failure_scenarios():
        """Create various failure scenarios for testing"""
        return [
            {
                "name": "wayback_522_timeout",
                "wayback_error": CDXAPIException("522 Connection timed out"),
                "common_crawl_success": True,
                "expected_fallback": True
            },
            {
                "name": "wayback_503_unavailable",
                "wayback_error": CDXAPIException("503 Service unavailable"),
                "common_crawl_success": True,
                "expected_fallback": True
            },
            {
                "name": "common_crawl_rate_limit",
                "wayback_success": True,
                "common_crawl_error": CommonCrawlAPIException("Rate limit exceeded"),
                "expected_fallback": False  # Primary succeeds
            },
            {
                "name": "both_sources_fail",
                "wayback_error": CDXAPIException("522 Connection timed out"),
                "common_crawl_error": CommonCrawlAPIException("503 Service unavailable"),
                "expected_exception": True
            },
            {
                "name": "timeout_errors",
                "wayback_error": TimeoutError("Request timed out"),
                "common_crawl_success": True,
                "expected_fallback": True
            }
        ]
    
    @staticmethod
    def create_performance_scenarios():
        """Create performance testing scenarios"""
        return [
            {
                "name": "small_batch",
                "domain_count": 10,
                "records_per_domain": 5,
                "expected_max_duration": 1.0
            },
            {
                "name": "medium_batch", 
                "domain_count": 50,
                "records_per_domain": 20,
                "expected_max_duration": 5.0
            },
            {
                "name": "large_batch",
                "domain_count": 100,
                "records_per_domain": 50,
                "expected_max_duration": 10.0
            },
            {
                "name": "concurrent_queries",
                "concurrent_count": 20,
                "records_per_query": 10,
                "expected_max_duration": 2.0
            }
        ]
    
    @staticmethod
    def create_configuration_scenarios():
        """Create various configuration scenarios"""
        scenarios = []
        
        # Basic configurations
        for archive_source in [ArchiveSource.WAYBACK_MACHINE, ArchiveSource.COMMON_CRAWL, ArchiveSource.HYBRID]:
            for fallback_enabled in [True, False]:
                scenarios.append({
                    "name": f"{archive_source.value}_fallback_{fallback_enabled}",
                    "archive_source": archive_source,
                    "fallback_enabled": fallback_enabled,
                    "archive_config": {}
                })
        
        # Complex configurations
        for strategy in ["immediate", "retry_then_fallback", "circuit_breaker"]:
            scenarios.append({
                "name": f"hybrid_strategy_{strategy}",
                "archive_source": ArchiveSource.HYBRID,
                "fallback_enabled": True,
                "archive_config": {
                    "fallback_strategy": strategy,
                    "fallback_delay_seconds": 1.0,
                    "wayback_machine": {"priority": 1},
                    "common_crawl": {"priority": 2}
                }
            })
        
        return scenarios


# Utility functions for test assertions

def assert_cdx_record_format(record: CDXRecord):
    """Assert that a CDXRecord has the expected format"""
    assert hasattr(record, 'timestamp')
    assert hasattr(record, 'original_url')
    assert hasattr(record, 'mime_type')
    assert hasattr(record, 'status_code')
    assert hasattr(record, 'digest')
    assert hasattr(record, 'length')
    
    # Validate timestamp format
    assert len(record.timestamp) == 14
    assert record.timestamp.isdigit()
    
    # Validate URL format
    assert record.original_url.startswith(('http://', 'https://'))
    
    # Validate status code
    assert record.status_code.isdigit()
    assert 100 <= int(record.status_code) < 600

def assert_archive_stats_format(stats: Dict[str, Any]):
    """Assert that archive statistics have the expected format"""
    required_keys = ["total_records", "final_count"]
    for key in required_keys:
        assert key in stats, f"Missing required key: {key}"
        assert isinstance(stats[key], int), f"Key {key} should be integer"
        assert stats[key] >= 0, f"Key {key} should be non-negative"

def assert_fallback_behavior(stats: Dict[str, Any], expected_fallback: bool):
    """Assert fallback behavior matches expectations"""
    assert "fallback_used" in stats
    assert stats["fallback_used"] == expected_fallback
    
    if expected_fallback:
        assert "attempts" in stats
        assert len(stats["attempts"]) > 1
        assert any(not attempt["success"] for attempt in stats["attempts"][:-1])
        assert stats["attempts"][-1]["success"]  # Last attempt should succeed

def assert_performance_within_limits(duration: float, max_duration: float, operation: str):
    """Assert that operation completed within performance limits"""
    assert duration <= max_duration, f"{operation} took {duration:.3f}s, expected <= {max_duration}s"

def assert_archive_configuration_applied(router: ArchiveServiceRouter, expected_config: Dict[str, Any]):
    """Assert that archive configuration was properly applied to router"""
    if "wayback_machine" in expected_config:
        wb_config = expected_config["wayback_machine"]
        for key, value in wb_config.items():
            if hasattr(router.config.wayback_config, key):
                actual_value = getattr(router.config.wayback_config, key)
                assert actual_value == value, f"Wayback {key}: expected {value}, got {actual_value}"
    
    if "common_crawl" in expected_config:
        cc_config = expected_config["common_crawl"]
        for key, value in cc_config.items():
            if hasattr(router.config.common_crawl_config, key):
                actual_value = getattr(router.config.common_crawl_config, key)
                assert actual_value == value, f"Common Crawl {key}: expected {value}, got {actual_value}"


# Export all fixtures and utilities for use in test modules
__all__ = [
    'MockCDXRecord',
    'MockArchiveService', 
    'MockCircuitBreaker',
    'ArchiveConfigBuilder',
    'PerformanceTimer',
    'ArchiveTestHarness',
    'ArchiveTestDataGenerator',
    'assert_cdx_record_format',
    'assert_archive_stats_format',
    'assert_fallback_behavior',
    'assert_performance_within_limits',
    'assert_archive_configuration_applied'
]