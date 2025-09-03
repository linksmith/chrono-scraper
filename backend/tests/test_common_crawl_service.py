"""
Unit tests for CommonCrawlService functionality.

Tests cover:
- Basic CDX record retrieval
- Error handling (rate limiting, timeouts, API failures)
- Data format validation
- Filtering integration
- Async patterns
- Circuit breaker integration
"""
import asyncio
import pytest
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from datetime import datetime
from typing import List, Dict

from app.services.common_crawl_service import (
    CommonCrawlService,
    CommonCrawlException,
    CommonCrawlAPIException,
    fetch_common_crawl_pages_simple,
    get_common_crawl_page_count
)
from app.services.wayback_machine import CDXRecord
from app.services.circuit_breaker import CircuitBreakerOpenException


class TestCommonCrawlService:
    """Test suite for CommonCrawlService class"""

    @pytest.fixture
    def service(self):
        """Create a CommonCrawlService instance for testing"""
        return CommonCrawlService()

    @pytest.fixture
    def mock_cdx_record(self):
        """Create a mock CDX record from cdx_toolkit"""
        mock_record = Mock()
        mock_record.timestamp = "20240101120000"
        mock_record.url = "https://example.com/test-page"
        mock_record.mimetype = "text/html"
        mock_record.status = "200"
        mock_record.digest = "sha1:ABCDEF1234567890"
        mock_record.length = "5000"
        return mock_record

    @pytest.fixture
    def mock_cdx_records(self, mock_cdx_record):
        """Create a list of mock CDX records"""
        records = []
        for i in range(10):
            record = Mock()
            record.timestamp = f"2024010112{i:04d}00"
            record.url = f"https://example.com/page-{i}"
            record.mimetype = "text/html"
            record.status = "200"
            record.digest = f"sha1:DIGEST{i:010d}"
            record.length = str(1000 + i * 100)
            records.append(record)
        return records

    def test_service_initialization(self, service):
        """Test CommonCrawlService initialization"""
        assert service.timeout == CommonCrawlService.DEFAULT_TIMEOUT
        assert service.max_retries == CommonCrawlService.DEFAULT_MAX_RETRIES
        assert service.circuit_breaker is not None
        assert service.executor is not None
        assert service.cdx_client is not None

    def test_convert_cdx_toolkit_record_success(self, service, mock_cdx_record):
        """Test successful conversion of cdx_toolkit record"""
        result = service._convert_cdx_toolkit_record(mock_cdx_record)
        
        assert isinstance(result, CDXRecord)
        assert result.timestamp == "20240101120000"
        assert result.original_url == "https://example.com/test-page"
        assert result.mime_type == "text/html"
        assert result.status_code == "200"
        assert result.digest == "sha1:ABCDEF1234567890"
        assert result.length == "5000"

    def test_convert_cdx_toolkit_record_missing_fields(self, service):
        """Test conversion with missing fields returns minimal record"""
        mock_record = Mock()
        mock_record.timestamp = "20240101120000"
        mock_record.url = "https://example.com/test"
        # Missing other fields

        result = service._convert_cdx_toolkit_record(mock_record)
        
        assert isinstance(result, CDXRecord)
        assert result.timestamp == "20240101120000"
        assert result.original_url == "https://example.com/test"
        assert result.mime_type == "text/html"  # Default
        assert result.status_code == "200"  # Default
        assert result.digest == ""  # Default
        assert result.length == "0"  # Default

    def test_convert_cdx_toolkit_record_exception(self, service):
        """Test conversion handles exceptions gracefully"""
        mock_record = Mock()
        mock_record.timestamp = None  # Invalid timestamp to trigger exception
        
        result = service._convert_cdx_toolkit_record(mock_record)
        
        # Should return minimal record
        assert isinstance(result, CDXRecord)
        assert result.timestamp == "20240101000000"  # Default fallback

    def test_build_common_crawl_query_domain_match(self, service):
        """Test building query for domain matching"""
        query = service._build_common_crawl_query(
            domain_name="example.com",
            from_date="20240101",
            to_date="20241231",
            match_type="domain",
            include_attachments=True
        )
        
        expected = {
            'url': '*.example.com/*',
            'from_ts': '20240101',
            'to_ts': '20241231',
            'match_type': 'glob',
            'mime': ['text/html', 'application/pdf'],
            'status': 200,
            'collapse': 'digest'
        }
        assert query == expected

    def test_build_common_crawl_query_prefix_match(self, service):
        """Test building query for prefix matching"""
        query = service._build_common_crawl_query(
            domain_name="example.com",
            from_date="20240101", 
            to_date="20241231",
            match_type="prefix",
            url_path="https://example.com/blog/",
            include_attachments=False
        )
        
        expected = {
            'url': 'https://example.com/blog/',
            'from_ts': '20240101',
            'to_ts': '20241231',
            'match_type': 'prefix',
            'mime': ['text/html'],
            'status': 200,
            'collapse': 'digest'
        }
        assert query == expected

    def test_build_common_crawl_query_exact_match(self, service):
        """Test building query for exact URL matching"""
        query = service._build_common_crawl_query(
            domain_name="https://example.com/specific-page",
            from_date="20240101",
            to_date="20241231",
            match_type="exact",
            include_attachments=True
        )
        
        expected = {
            'url': 'https://example.com/specific-page',
            'from_ts': '20240101',
            'to_ts': '20241231',
            'match_type': 'prefix',  # URLs are treated as prefix
            'mime': ['text/html', 'application/pdf'],
            'status': 200,
            'collapse': 'digest'
        }
        assert query == expected

    @pytest.mark.asyncio
    async def test_fetch_records_with_retry_success(self, service, mock_cdx_records):
        """Test successful record fetching with retry mechanism"""
        query_params = {
            'url': '*.example.com/*',
            'from_ts': '20240101',
            'to_ts': '20241231',
            'match_type': 'glob'
        }

        def mock_iter(**kwargs):
            return iter(mock_cdx_records)

        service.cdx_client.iter = mock_iter
        
        result = await service._fetch_records_with_retry(query_params, 5000, max_pages=1)
        
        assert len(result) == 10
        assert result == mock_cdx_records

    @pytest.mark.asyncio
    async def test_fetch_records_with_retry_exception(self, service):
        """Test retry mechanism handles exceptions"""
        query_params = {'url': '*.example.com/*'}

        def mock_iter(**kwargs):
            raise ConnectionError("Connection failed")

        service.cdx_client.iter = mock_iter
        
        with pytest.raises(CommonCrawlAPIException) as exc_info:
            await service._fetch_records_with_retry(query_params, 5000, max_pages=1)
        
        assert "Common Crawl fetch failed" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_fetch_records_timeout_handling(self, service):
        """Test timeout error handling"""
        query_params = {'url': '*.example.com/*'}

        def mock_iter(**kwargs):
            raise TimeoutError("Request timed out")

        service.cdx_client.iter = mock_iter
        
        with pytest.raises(CommonCrawlAPIException) as exc_info:
            await service._fetch_records_with_retry(query_params, 5000, max_pages=1)
        
        assert "Common Crawl timeout" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_fetch_records_rate_limit_handling(self, service):
        """Test rate limit error handling"""
        query_params = {'url': '*.example.com/*'}

        def mock_iter(**kwargs):
            raise Exception("HTTP 503: Rate limit exceeded")

        service.cdx_client.iter = mock_iter
        
        with pytest.raises(CommonCrawlAPIException) as exc_info:
            await service._fetch_records_with_retry(query_params, 5000, max_pages=1)
        
        assert "Common Crawl rate limited" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_get_page_count_success(self, service, mock_cdx_records):
        """Test successful page count estimation"""
        def mock_iter(**kwargs):
            # Return first 100 records to simulate full page
            return iter(mock_cdx_records + [Mock() for _ in range(90)])  # Total 100

        service.cdx_client.iter = mock_iter
        
        result = await service.get_page_count(
            domain_name="example.com",
            from_date="20240101", 
            to_date="20241231"
        )
        
        assert result == 10  # Conservative estimate for domains with data

    @pytest.mark.asyncio
    async def test_get_page_count_no_data(self, service):
        """Test page count when no data available"""
        def mock_iter(**kwargs):
            return iter([])

        service.cdx_client.iter = mock_iter
        
        result = await service.get_page_count(
            domain_name="nonexistent.com",
            from_date="20240101",
            to_date="20241231"
        )
        
        assert result == 0

    @pytest.mark.asyncio
    async def test_get_page_count_exception(self, service):
        """Test page count estimation handles exceptions"""
        def mock_iter(**kwargs):
            raise Exception("API Error")

        service.cdx_client.iter = mock_iter
        
        result = await service.get_page_count(
            domain_name="error.com",
            from_date="20240101",
            to_date="20241231"
        )
        
        assert result == 0

    @pytest.mark.asyncio
    async def test_fetch_cdx_records_simple_success(self, service, mock_cdx_records):
        """Test simplified CDX record fetching"""
        def mock_iter(**kwargs):
            return iter(mock_cdx_records)

        service.cdx_client.iter = mock_iter
        
        records, stats = await service.fetch_cdx_records_simple(
            domain_name="example.com",
            from_date="20240101",
            to_date="20241231"
        )
        
        assert len(records) > 0  # After static asset filtering
        assert isinstance(records[0], CDXRecord)
        assert stats["total_pages"] == 1
        assert stats["fetched_pages"] == 1
        assert stats["total_records"] == 10
        assert stats["final_count"] > 0

    @pytest.mark.asyncio
    async def test_fetch_cdx_records_simple_no_data(self, service):
        """Test simplified fetch when no data available"""
        def mock_iter(**kwargs):
            return iter([])

        service.cdx_client.iter = mock_iter
        
        records, stats = await service.fetch_cdx_records_simple(
            domain_name="empty.com",
            from_date="20240101",
            to_date="20241231"
        )
        
        assert len(records) == 0
        assert stats["final_count"] == 0

    @pytest.mark.asyncio
    async def test_fetch_cdx_records_simple_exception(self, service):
        """Test simplified fetch handles exceptions gracefully"""
        def mock_iter(**kwargs):
            raise Exception("Network error")

        service.cdx_client.iter = mock_iter
        
        records, stats = await service.fetch_cdx_records_simple(
            domain_name="error.com",
            from_date="20240101",
            to_date="20241231"
        )
        
        assert len(records) == 0
        assert stats["final_count"] == 0

    @pytest.mark.asyncio
    async def test_fetch_cdx_records_full_filtering(self, service, mock_cdx_records):
        """Test full CDX record fetching with comprehensive filtering"""
        # Add varied record types for filtering tests
        mixed_records = mock_cdx_records.copy()
        
        # Add small file (should be filtered)
        small_record = Mock()
        small_record.timestamp = "20240101130000"
        small_record.url = "https://example.com/small-file"
        small_record.mimetype = "text/html"
        small_record.status = "200"
        small_record.digest = "sha1:SMALLFILE"
        small_record.length = "500"  # Below min_size
        mixed_records.append(small_record)
        
        # Add PDF attachment
        pdf_record = Mock()
        pdf_record.timestamp = "20240101140000"
        pdf_record.url = "https://example.com/document.pdf"
        pdf_record.mimetype = "application/pdf"
        pdf_record.status = "200"
        pdf_record.digest = "sha1:PDFFILE"
        pdf_record.length = "50000"
        mixed_records.append(pdf_record)

        def mock_iter(**kwargs):
            return iter(mixed_records)

        service.cdx_client.iter = mock_iter
        
        records, stats = await service.fetch_cdx_records(
            domain_name="example.com",
            from_date="20240101",
            to_date="20241231",
            min_size=1000,
            max_size=1000000,
            filter_list_pages=True,
            include_attachments=True
        )
        
        assert len(records) > 0
        assert stats["size_filtered"] >= 1  # Small file filtered
        assert stats["final_count"] == len(records)
        
        # Verify filtering stats are populated
        expected_keys = [
            "total_pages", "fetched_pages", "total_records",
            "static_assets_filtered", "size_filtered", 
            "attachment_filtered", "list_filtered", 
            "duplicate_filtered", "final_count"
        ]
        for key in expected_keys:
            assert key in stats

    @pytest.mark.asyncio
    async def test_context_manager_protocol(self):
        """Test async context manager protocol"""
        async with CommonCrawlService() as service:
            assert service is not None
            assert service.executor is not None

    @pytest.mark.asyncio
    async def test_circuit_breaker_integration(self, service):
        """Test circuit breaker integration"""
        # Mock circuit breaker to be open
        service.circuit_breaker.state = "open"
        
        def mock_iter(**kwargs):
            raise CircuitBreakerOpenException("Circuit breaker is open")

        service.cdx_client.iter = mock_iter
        
        with pytest.raises(CommonCrawlAPIException):
            await service._fetch_records_with_retry({'url': '*.example.com/*'}, 5000)


class TestConvenienceFunctions:
    """Test suite for convenience functions"""

    @pytest.mark.asyncio
    async def test_fetch_common_crawl_pages_simple(self):
        """Test simple page fetching convenience function"""
        with patch('app.services.common_crawl_service.CommonCrawlService') as mock_service_class:
            mock_service = AsyncMock()
            mock_service_class.return_value.__aenter__.return_value = mock_service
            
            mock_records = [
                CDXRecord(
                    timestamp="20240101120000",
                    original_url="https://example.com/page1",
                    mime_type="text/html",
                    status_code="200",
                    digest="sha1:DIGEST1",
                    length="5000"
                )
            ]
            
            mock_service.fetch_cdx_records_simple.return_value = (mock_records, {"final_count": 1})
            
            result = await fetch_common_crawl_pages_simple(
                domain_name="example.com",
                from_date="20240101",
                to_date="20241231"
            )
            
            assert len(result) == 1
            assert result[0].original_url == "https://example.com/page1"
            
            mock_service.fetch_cdx_records_simple.assert_called_once_with(
                domain_name="example.com",
                from_date="20240101",
                to_date="20241231",
                match_type="domain",
                url_path=None,
                max_pages=None,
                include_attachments=True
            )

    @pytest.mark.asyncio
    async def test_get_common_crawl_page_count_function(self):
        """Test page count convenience function"""
        with patch('app.services.common_crawl_service.CommonCrawlService') as mock_service_class:
            mock_service = AsyncMock()
            mock_service_class.return_value.__aenter__.return_value = mock_service
            mock_service.get_page_count.return_value = 42
            
            result = await get_common_crawl_page_count(
                domain_name="example.com",
                from_date="20240101",
                to_date="20241231"
            )
            
            assert result == 42
            mock_service.get_page_count.assert_called_once_with(
                "example.com", "20240101", "20241231", "domain", None, 200
            )


class TestErrorClassification:
    """Test suite for error classification and handling"""

    def test_common_crawl_exception_hierarchy(self):
        """Test exception class hierarchy"""
        base_exc = CommonCrawlException("Base error")
        api_exc = CommonCrawlAPIException("API error")
        
        assert isinstance(api_exc, CommonCrawlException)
        assert str(base_exc) == "Base error"
        assert str(api_exc) == "API error"

    def test_exception_error_handling_patterns(self):
        """Test various error patterns that should be handled"""
        timeout_errors = [
            "timeout",
            "Request timed out", 
            "Connection timeout",
            "Read timeout"
        ]
        
        rate_limit_errors = [
            "rate limit exceeded",
            "HTTP 503: Rate limit", 
            "Too many requests",
            "Rate limiting in effect"
        ]
        
        # Test that these patterns would be correctly identified
        # (This would be part of the actual error handling logic)
        for error in timeout_errors:
            assert "timeout" in error.lower()
        
        for error in rate_limit_errors:
            assert "rate limit" in error.lower() or "503" in error


@pytest.mark.asyncio
class TestAsyncPatterns:
    """Test suite for async/await patterns and concurrency"""

    async def test_concurrent_requests(self):
        """Test handling multiple concurrent requests"""
        async def mock_fetch(domain, *args, **kwargs):
            await asyncio.sleep(0.1)  # Simulate network delay
            return [], {"final_count": 0}
        
        with patch('app.services.common_crawl_service.CommonCrawlService.fetch_cdx_records_simple', mock_fetch):
            tasks = []
            for i in range(5):
                task = fetch_common_crawl_pages_simple(
                    f"domain{i}.com", "20240101", "20241231"
                )
                tasks.append(task)
            
            results = await asyncio.gather(*tasks)
            assert len(results) == 5
            for result in results:
                assert isinstance(result, list)

    async def test_timeout_handling_in_async_context(self):
        """Test timeout handling in async operations"""
        async def slow_operation():
            await asyncio.sleep(10)  # Very slow operation
            return []
        
        with patch('app.services.common_crawl_service.CommonCrawlService._fetch_records_with_retry', slow_operation):
            try:
                # Should timeout before completing
                await asyncio.wait_for(
                    fetch_common_crawl_pages_simple("slow.com", "20240101", "20241231"),
                    timeout=0.1
                )
                assert False, "Should have timed out"
            except asyncio.TimeoutError:
                pass  # Expected


@pytest.mark.performance
class TestPerformanceCharacteristics:
    """Test suite for performance-related functionality"""

    @pytest.mark.asyncio
    async def test_large_result_set_handling(self):
        """Test handling of large result sets"""
        # Create a large number of mock records
        large_record_set = []
        for i in range(10000):
            record = Mock()
            record.timestamp = f"2024010{i%10}120000"
            record.url = f"https://example.com/page-{i}"
            record.mimetype = "text/html"
            record.status = "200"
            record.digest = f"sha1:DIGEST{i:010d}"
            record.length = "2000"
            large_record_set.append(record)

        service = CommonCrawlService()
        
        def mock_iter(**kwargs):
            return iter(large_record_set)

        service.cdx_client.iter = mock_iter
        
        start_time = asyncio.get_event_loop().time()
        records, stats = await service.fetch_cdx_records_simple(
            domain_name="large.com",
            from_date="20240101",
            to_date="20241231"
        )
        end_time = asyncio.get_event_loop().time()
        
        # Should complete within reasonable time
        assert (end_time - start_time) < 5.0  # 5 seconds max
        assert len(records) > 0
        assert stats["total_records"] == 10000

    def test_memory_usage_with_large_datasets(self):
        """Test memory usage characteristics"""
        service = CommonCrawlService()
        
        # Test that service doesn't hold onto large amounts of data
        import gc
        initial_objects = len(gc.get_objects())
        
        # Create and process many records
        for _ in range(1000):
            mock_record = Mock()
            mock_record.timestamp = "20240101120000"
            mock_record.url = "https://example.com/test"
            mock_record.mimetype = "text/html"
            mock_record.status = "200" 
            mock_record.digest = "sha1:TEST"
            mock_record.length = "1000"
            
            # Convert record (this should not accumulate memory)
            service._convert_cdx_toolkit_record(mock_record)
        
        gc.collect()
        final_objects = len(gc.get_objects())
        
        # Should not have significant memory leak
        object_increase = final_objects - initial_objects
        assert object_increase < 100  # Allow some overhead but not excessive


if __name__ == "__main__":
    pytest.main([__file__, "-v"])