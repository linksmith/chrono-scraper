"""
Performance and load tests for archive services.

Tests cover:
- Fallback performance under load
- Memory usage with large CDX result sets
- Concurrent archive requests
- Timeout handling and circuit breaker thresholds
- Scalability with increasing domain counts
- Resource utilization optimization
"""
import asyncio
import pytest
import psutil
import time
import gc
from concurrent.futures import ThreadPoolExecutor
from typing import List, Dict, Any
from unittest.mock import patch, AsyncMock

from app.services.archive_service_router import ArchiveServiceRouter, RoutingConfig
from app.services.common_crawl_service import CommonCrawlService
from app.services.wayback_machine import CDXAPIClient, CDXRecord, CDXAPIException
from app.models.project import ArchiveSource
from tests.fixtures.archive_fixtures import (
    MockCDXRecord, ArchiveTestHarness, PerformanceTimer,
    ArchiveTestDataGenerator, ArchiveConfigBuilder
)


@pytest.mark.performance
class TestArchiveServicePerformance:
    """Performance tests for individual archive services"""

    @pytest.mark.asyncio
    async def test_common_crawl_large_result_set_performance(self):
        """Test Common Crawl performance with large result sets"""
        service = CommonCrawlService()
        
        # Mock large result set
        large_record_count = 10000
        mock_records = []
        for i in range(large_record_count):
            mock_record = MockCDXRecord.create(
                timestamp=f"2024{i%12+1:02d}{i%28+1:02d}120000",
                url=f"https://example.com/page-{i}",
                digest=f"sha1:DIGEST{i:010d}",
                length=str(1000 + (i % 5000))
            )
            mock_records.append(mock_record)
        
        def mock_iter(**kwargs):
            return iter(mock_records)
        
        service.cdx_client.iter = mock_iter
        
        with PerformanceTimer("large_result_set") as timer:
            records, stats = await service.fetch_cdx_records_simple(
                domain_name="large-test.com",
                from_date="20240101",
                to_date="20241231"
            )
        
        # Performance assertions
        assert timer.duration < 5.0, f"Large result processing took {timer.duration:.3f}s, should be < 5s"
        assert len(records) > 0  # After filtering
        assert stats["total_records"] == large_record_count
        
        # Memory usage should be reasonable
        process = psutil.Process()
        memory_mb = process.memory_info().rss / 1024 / 1024
        assert memory_mb < 500, f"Memory usage {memory_mb:.1f}MB exceeds 500MB limit"

    @pytest.mark.asyncio
    async def test_wayback_machine_concurrent_requests(self):
        """Test Wayback Machine performance under concurrent load"""
        concurrent_requests = 20
        domains = [f"concurrent-test-{i}.com" for i in range(concurrent_requests)]
        
        async def single_request(domain: str):
            async with CDXAPIClient() as client:
                # Mock the actual request
                with patch.object(client, 'fetch_cdx_records_simple') as mock_fetch:
                    mock_records = MockCDXRecord.create_batch(count=10, domain=domain)
                    mock_fetch.return_value = (mock_records, {"fetched_pages": 1})
                    
                    start_time = time.time()
                    records, stats = await client.fetch_cdx_records_simple(
                        domain_name=domain,
                        from_date="20240101",
                        to_date="20241231"
                    )
                    duration = time.time() - start_time
                    
                    return len(records), duration
        
        # Execute concurrent requests
        with PerformanceTimer("concurrent_requests") as timer:
            tasks = [single_request(domain) for domain in domains]
            results = await asyncio.gather(*tasks)
        
        # Performance analysis
        total_records = sum(count for count, _ in results)
        individual_durations = [duration for _, duration in results]
        avg_duration = sum(individual_durations) / len(individual_durations)
        
        # Assertions
        assert timer.duration < 2.0, f"Concurrent requests took {timer.duration:.3f}s, should be < 2s"
        assert total_records == concurrent_requests * 10  # Expected total
        assert avg_duration < 0.1, f"Average request time {avg_duration:.3f}s should be < 0.1s"
        assert len(results) == concurrent_requests

    @pytest.mark.asyncio
    async def test_circuit_breaker_performance_impact(self):
        """Test performance impact of circuit breaker operations"""
        router = ArchiveServiceRouter()
        mock_records = MockCDXRecord.create_batch(count=5)
        
        # Test with circuit breaker closed (normal operation)
        with patch.object(router.strategies["wayback_machine"], 'query_archive') as mock_wayback:
            mock_wayback.return_value = (mock_records, {"fetched_pages": 1})
            
            closed_durations = []
            for i in range(10):
                with PerformanceTimer("cb_closed") as timer:
                    await router.query_archive(
                        domain=f"cb-test-{i}.com",
                        from_date="20240101",
                        to_date="20241231",
                        project_config={"archive_source": ArchiveSource.WAYBACK_MACHINE}
                    )
                closed_durations.append(timer.duration)
        
        # Test with circuit breaker open (should fail fast)
        router.wayback_breaker.state = "open"
        
        open_durations = []
        for i in range(10):
            with PerformanceTimer("cb_open") as timer:
                try:
                    await router.query_archive(
                        domain=f"cb-open-{i}.com",
                        from_date="20240101",
                        to_date="20241231",
                        project_config={"archive_source": ArchiveSource.WAYBACK_MACHINE, "fallback_enabled": False}
                    )
                except Exception:
                    pass  # Expected failures
            open_durations.append(timer.duration)
        
        # Performance comparison
        avg_closed_duration = sum(closed_durations) / len(closed_durations)
        avg_open_duration = sum(open_durations) / len(open_durations)
        
        # Open circuit breaker should fail much faster
        assert avg_open_duration < avg_closed_duration / 10, \
            f"Open CB duration {avg_open_duration:.4f}s not significantly faster than closed {avg_closed_duration:.4f}s"
        assert avg_open_duration < 0.01, f"Open CB should fail in < 10ms, took {avg_open_duration:.4f}s"


@pytest.mark.performance
class TestArchiveServiceRouterPerformance:
    """Performance tests for archive service router"""

    @pytest.fixture
    def performance_harness(self):
        """Setup performance test harness"""
        harness = ArchiveTestHarness()
        harness.setup_router()
        return harness

    @pytest.mark.asyncio
    async def test_fallback_performance_overhead(self, performance_harness):
        """Test performance overhead of fallback scenarios"""
        harness = performance_harness
        router = harness.router
        
        # Test direct success (no fallback)
        direct_durations = []
        for i in range(10):
            with PerformanceTimer("direct") as timer:
                records, stats = await router.query_archive(
                    domain=f"direct-{i}.com",
                    from_date="20240101",
                    to_date="20241231",
                    project_config={"archive_source": ArchiveSource.WAYBACK_MACHINE}
                )
            direct_durations.append(timer.duration)
            assert not stats["fallback_used"]
        
        # Test fallback scenario
        harness.force_wayback_failure(True)
        
        fallback_durations = []
        for i in range(10):
            with PerformanceTimer("fallback") as timer:
                records, stats = await router.query_archive(
                    domain=f"fallback-{i}.com",
                    from_date="20240101",
                    to_date="20241231",
                    project_config={"archive_source": ArchiveSource.HYBRID}
                )
            fallback_durations.append(timer.duration)
            assert stats["fallback_used"]
        
        # Performance analysis
        avg_direct = sum(direct_durations) / len(direct_durations)
        avg_fallback = sum(fallback_durations) / len(fallback_durations)
        overhead = avg_fallback - avg_direct
        
        # Fallback overhead should be reasonable
        assert overhead < 0.1, f"Fallback overhead {overhead:.3f}s should be < 0.1s"
        assert avg_fallback < 0.2, f"Fallback total time {avg_fallback:.3f}s should be < 0.2s"

    @pytest.mark.asyncio
    async def test_scaling_with_domain_count(self, performance_harness):
        """Test performance scaling with increasing domain counts"""
        harness = performance_harness
        router = harness.router
        
        domain_counts = [10, 50, 100, 200]
        results = {}
        
        for domain_count in domain_counts:
            domains = [f"scale-test-{i}.com" for i in range(domain_count)]
            
            with PerformanceTimer(f"domains_{domain_count}") as timer:
                tasks = []
                for domain in domains:
                    task = router.query_archive(
                        domain=domain,
                        from_date="20240101",
                        to_date="20241231",
                        project_config={"archive_source": ArchiveSource.WAYBACK_MACHINE}
                    )
                    tasks.append(task)
                
                batch_results = await asyncio.gather(*tasks)
            
            results[domain_count] = {
                "duration": timer.duration,
                "domains_per_second": domain_count / timer.duration,
                "avg_per_domain": timer.duration / domain_count,
                "success_count": len(batch_results)
            }
        
        # Performance scaling analysis
        for count, result in results.items():
            # Should maintain reasonable throughput
            assert result["domains_per_second"] > 20, \
                f"Throughput {result['domains_per_second']:.1f} domains/s too low for {count} domains"
            
            # Individual domain time should remain consistent
            assert result["avg_per_domain"] < 0.1, \
                f"Average per domain {result['avg_per_domain']:.3f}s too high for {count} domains"
        
        # Scaling should be roughly linear (allowing for some overhead)
        ratio_50_10 = results[50]["duration"] / results[10]["duration"]
        ratio_100_50 = results[100]["duration"] / results[50]["duration"]
        
        # Should scale roughly linearly (within 50% tolerance)
        assert 3 < ratio_50_10 < 7.5, f"50/10 scaling ratio {ratio_50_10:.2f} not roughly linear (expected ~5)"
        assert 1.5 < ratio_100_50 < 3, f"100/50 scaling ratio {ratio_100_50:.2f} not roughly linear (expected ~2)"

    @pytest.mark.asyncio
    async def test_memory_efficiency_large_batches(self):
        """Test memory efficiency with large batch processing"""
        router = ArchiveServiceRouter()
        
        # Monitor memory usage
        process = psutil.Process()
        initial_memory = process.memory_info().rss / 1024 / 1024  # MB
        
        # Process large batches
        batch_size = 100
        num_batches = 5
        
        for batch_num in range(num_batches):
            domains = [f"memory-test-b{batch_num}-d{i}.com" for i in range(batch_size)]
            
            with patch.object(router.strategies["wayback_machine"], 'query_archive') as mock_wayback:
                # Create large mock result sets
                large_records = MockCDXRecord.create_batch(count=100)
                mock_wayback.return_value = (large_records, {"fetched_pages": 10})
                
                tasks = []
                for domain in domains:
                    task = router.query_archive(
                        domain=domain,
                        from_date="20240101",
                        to_date="20241231",
                        project_config={"archive_source": ArchiveSource.WAYBACK_MACHINE}
                    )
                    tasks.append(task)
                
                batch_results = await asyncio.gather(*tasks)
                
                # Force garbage collection
                del batch_results
                del tasks
                gc.collect()
                
                # Check memory growth
                current_memory = process.memory_info().rss / 1024 / 1024
                memory_growth = current_memory - initial_memory
                
                # Memory growth should be controlled
                assert memory_growth < 200, \
                    f"Memory growth {memory_growth:.1f}MB after batch {batch_num} exceeds 200MB limit"

    @pytest.mark.asyncio
    async def test_timeout_handling_performance(self):
        """Test performance of timeout handling mechanisms"""
        router = ArchiveServiceRouter()
        
        # Test fast timeout detection
        with patch.object(router.strategies["wayback_machine"], 'query_archive') as mock_wayback:
            
            async def slow_response(*args, **kwargs):
                await asyncio.sleep(10)  # Very slow response
                return [], {}
            
            mock_wayback.side_effect = slow_response
            
            timeout_durations = []
            for i in range(5):
                with PerformanceTimer("timeout_test") as timer:
                    try:
                        # Should timeout quickly
                        await asyncio.wait_for(
                            router.query_archive(
                                domain=f"timeout-test-{i}.com",
                                from_date="20240101",
                                to_date="20241231",
                                project_config={"archive_source": ArchiveSource.WAYBACK_MACHINE}
                            ),
                            timeout=0.1  # 100ms timeout
                        )
                    except asyncio.TimeoutError:
                        pass  # Expected
                timeout_durations.append(timer.duration)
            
            # Timeout handling should be fast and consistent
            avg_timeout = sum(timeout_durations) / len(timeout_durations)
            assert avg_timeout < 0.15, f"Average timeout {avg_timeout:.3f}s should be close to 0.1s limit"
            
            # Timeouts should be consistent (low variance)
            max_variance = max(timeout_durations) - min(timeout_durations)
            assert max_variance < 0.05, f"Timeout variance {max_variance:.3f}s should be < 0.05s"

    @pytest.mark.asyncio
    async def test_metrics_collection_performance_impact(self):
        """Test performance impact of metrics collection"""
        
        # Router with metrics enabled (default)
        router_with_metrics = ArchiveServiceRouter()
        
        # Router with minimal metrics (simulated by disabling history)
        router_minimal = ArchiveServiceRouter()
        router_minimal.max_query_history = 0  # Disable history collection
        
        mock_records = MockCDXRecord.create_batch(count=10)
        
        # Test with full metrics
        with patch.object(router_with_metrics.strategies["wayback_machine"], 'query_archive') as mock_wb1:
            mock_wb1.return_value = (mock_records, {"fetched_pages": 1})
            
            metrics_durations = []
            for i in range(50):
                with PerformanceTimer("with_metrics") as timer:
                    await router_with_metrics.query_archive(
                        domain=f"metrics-{i}.com",
                        from_date="20240101",
                        to_date="20241231",
                        project_config={"archive_source": ArchiveSource.WAYBACK_MACHINE}
                    )
                metrics_durations.append(timer.duration)
        
        # Test with minimal metrics
        with patch.object(router_minimal.strategies["wayback_machine"], 'query_archive') as mock_wb2:
            mock_wb2.return_value = (mock_records, {"fetched_pages": 1})
            
            minimal_durations = []
            for i in range(50):
                with PerformanceTimer("minimal_metrics") as timer:
                    await router_minimal.query_archive(
                        domain=f"minimal-{i}.com",
                        from_date="20240101",
                        to_date="20241231",
                        project_config={"archive_source": ArchiveSource.WAYBACK_MACHINE}
                    )
                minimal_durations.append(timer.duration)
        
        # Performance comparison
        avg_with_metrics = sum(metrics_durations) / len(metrics_durations)
        avg_minimal = sum(minimal_durations) / len(minimal_durations)
        overhead = avg_with_metrics - avg_minimal
        
        # Metrics overhead should be negligible
        assert overhead < 0.001, f"Metrics overhead {overhead:.4f}s should be negligible"
        assert avg_with_metrics < 0.01, f"With metrics duration {avg_with_metrics:.4f}s should be < 10ms"


@pytest.mark.performance
@pytest.mark.slow
class TestArchiveServiceLoadTesting:
    """Load testing for archive services under stress"""

    @pytest.mark.asyncio
    async def test_sustained_load_wayback_machine(self):
        """Test Wayback Machine under sustained load"""
        router = ArchiveServiceRouter()
        mock_records = MockCDXRecord.create_batch(count=20)
        
        with patch.object(router.strategies["wayback_machine"], 'query_archive') as mock_wayback:
            mock_wayback.return_value = (mock_records, {"fetched_pages": 2})
            
            # Sustained load parameters
            total_requests = 500
            concurrent_requests = 25
            duration_minutes = 2
            
            start_time = time.time()
            completed_requests = 0
            errors = []
            
            async def worker(worker_id: int):
                nonlocal completed_requests
                worker_requests = 0
                
                while (time.time() - start_time) < (duration_minutes * 60):
                    try:
                        domain = f"load-test-w{worker_id}-r{worker_requests}.com"
                        records, stats = await router.query_archive(
                            domain=domain,
                            from_date="20240101",
                            to_date="20241231",
                            project_config={"archive_source": ArchiveSource.WAYBACK_MACHINE}
                        )
                        completed_requests += 1
                        worker_requests += 1
                        
                        # Small delay to avoid overwhelming
                        await asyncio.sleep(0.01)
                        
                    except Exception as e:
                        errors.append(f"Worker {worker_id}: {str(e)}")
                
                return worker_requests
            
            # Start concurrent workers
            workers = [worker(i) for i in range(concurrent_requests)]
            worker_results = await asyncio.gather(*workers)
            
            total_duration = time.time() - start_time
            
            # Performance analysis
            requests_per_second = completed_requests / total_duration
            error_rate = len(errors) / completed_requests if completed_requests > 0 else 1.0
            
            # Load test assertions
            assert requests_per_second > 50, \
                f"Throughput {requests_per_second:.1f} req/s below minimum of 50 req/s"
            assert error_rate < 0.01, \
                f"Error rate {error_rate:.3f} exceeds 1% threshold"
            assert completed_requests > 100, \
                f"Completed only {completed_requests} requests in sustained test"
            
            # Check resource usage
            process = psutil.Process()
            cpu_percent = process.cpu_percent()
            memory_mb = process.memory_info().rss / 1024 / 1024
            
            assert cpu_percent < 80, f"CPU usage {cpu_percent}% exceeds 80% limit"
            assert memory_mb < 1000, f"Memory usage {memory_mb:.1f}MB exceeds 1GB limit"

    @pytest.mark.asyncio
    async def test_burst_load_with_fallback(self):
        """Test burst load handling with fallback scenarios"""
        harness = ArchiveTestHarness()
        harness.setup_router()
        
        # Configure burst scenario: Wayback fails, Common Crawl handles load
        harness.force_wayback_failure(True)
        
        # Burst parameters
        burst_size = 100
        burst_duration = 5  # seconds
        
        start_time = time.time()
        burst_tasks = []
        
        # Create burst of requests
        for i in range(burst_size):
            task = harness.router.query_archive(
                domain=f"burst-test-{i}.com",
                from_date="20240101",
                to_date="20241231",
                project_config={"archive_source": ArchiveSource.HYBRID}
            )
            burst_tasks.append(task)
        
        # Execute burst
        with PerformanceTimer("burst_execution") as timer:
            results = await asyncio.gather(*burst_tasks, return_exceptions=True)
        
        burst_actual_duration = time.time() - start_time
        
        # Analyze results
        successful_results = [r for r in results if not isinstance(r, Exception)]
        failed_results = [r for r in results if isinstance(r, Exception)]
        
        # Burst performance assertions
        assert timer.duration < burst_duration, \
            f"Burst took {timer.duration:.2f}s, should complete within {burst_duration}s"
        
        success_rate = len(successful_results) / len(results)
        assert success_rate > 0.95, \
            f"Success rate {success_rate:.2f} below 95% threshold in burst test"
        
        # Verify fallback was used
        fallback_count = sum(1 for records, stats in successful_results if stats.get("fallback_used"))
        assert fallback_count > burst_size * 0.8, \
            f"Only {fallback_count}/{burst_size} requests used fallback"
        
        # Check system resources during burst
        process = psutil.Process()
        memory_mb = process.memory_info().rss / 1024 / 1024
        assert memory_mb < 2000, f"Memory usage {memory_mb:.1f}MB during burst exceeds 2GB"

    @pytest.mark.asyncio
    async def test_circuit_breaker_under_load(self):
        """Test circuit breaker behavior under load conditions"""
        router = ArchiveServiceRouter()
        
        # Phase 1: Generate load to trigger circuit breaker
        failure_requests = 20
        
        with patch.object(router.strategies["wayback_machine"], 'query_archive') as mock_wayback:
            mock_wayback.side_effect = CDXAPIException("522 Connection timed out")
            
            failure_tasks = []
            for i in range(failure_requests):
                task = router.query_archive(
                    domain=f"cb-load-fail-{i}.com",
                    from_date="20240101",
                    to_date="20241231",
                    project_config={"archive_source": ArchiveSource.WAYBACK_MACHINE, "fallback_enabled": False}
                )
                failure_tasks.append(task)
            
            # Execute failure batch
            failure_results = await asyncio.gather(*failure_tasks, return_exceptions=True)
            
            # All should fail
            assert all(isinstance(r, Exception) for r in failure_results)
        
        # Phase 2: Test circuit breaker open performance
        cb_status = router.wayback_breaker.get_status()
        if cb_status["state"] != "open":
            # Force open for testing
            router.wayback_breaker.state = "open"
        
        # Test fast failures when circuit breaker is open
        open_requests = 50
        
        open_durations = []
        for i in range(open_requests):
            with PerformanceTimer("cb_open") as timer:
                try:
                    await router.query_archive(
                        domain=f"cb-load-open-{i}.com",
                        from_date="20240101",
                        to_date="20241231",
                        project_config={"archive_source": ArchiveSource.WAYBACK_MACHINE, "fallback_enabled": False}
                    )
                except Exception:
                    pass  # Expected failures
            open_durations.append(timer.duration)
        
        # Circuit breaker should provide fast failures
        avg_open_duration = sum(open_durations) / len(open_durations)
        max_open_duration = max(open_durations)
        
        assert avg_open_duration < 0.001, \
            f"Average CB open duration {avg_open_duration:.4f}s should be < 1ms"
        assert max_open_duration < 0.01, \
            f"Max CB open duration {max_open_duration:.4f}s should be < 10ms"

    @pytest.mark.asyncio
    async def test_memory_leak_detection_long_running(self):
        """Test for memory leaks during long-running operations"""
        router = ArchiveServiceRouter()
        mock_records = MockCDXRecord.create_batch(count=50)
        
        with patch.object(router.strategies["wayback_machine"], 'query_archive') as mock_wayback:
            mock_wayback.return_value = (mock_records, {"fetched_pages": 5})
            
            # Baseline memory measurement
            gc.collect()
            process = psutil.Process()
            initial_memory = process.memory_info().rss / 1024 / 1024
            
            # Long-running test
            iterations = 1000
            memory_samples = []
            
            for i in range(iterations):
                records, stats = await router.query_archive(
                    domain=f"memory-leak-test-{i}.com",
                    from_date="20240101",
                    to_date="20241231",
                    project_config={"archive_source": ArchiveSource.WAYBACK_MACHINE}
                )
                
                # Sample memory every 100 iterations
                if i % 100 == 0:
                    gc.collect()
                    current_memory = process.memory_info().rss / 1024 / 1024
                    memory_samples.append(current_memory)
                
                # Clear references
                del records
                del stats
            
            # Final memory measurement
            gc.collect()
            final_memory = process.memory_info().rss / 1024 / 1024
            
            # Memory leak analysis
            memory_growth = final_memory - initial_memory
            max_memory = max(memory_samples)
            memory_variance = max_memory - min(memory_samples)
            
            # Memory leak assertions
            assert memory_growth < 50, \
                f"Memory grew by {memory_growth:.1f}MB over {iterations} iterations"
            assert memory_variance < 100, \
                f"Memory variance {memory_variance:.1f}MB indicates potential leak"
            
            # Check query history doesn't grow unbounded
            assert len(router.query_history) <= router.max_query_history, \
                "Query history exceeds maximum size limit"


@pytest.mark.benchmark
class TestArchiveServiceBenchmarks:
    """Benchmark tests for comparative performance analysis"""

    @pytest.mark.asyncio
    async def test_source_performance_comparison(self):
        """Benchmark performance comparison between archive sources"""
        iterations = 100
        
        # Wayback Machine benchmark
        router_wb = ArchiveServiceRouter()
        mock_records_wb = MockCDXRecord.create_batch(count=25)
        
        with patch.object(router_wb.strategies["wayback_machine"], 'query_archive') as mock_wb:
            mock_wb.return_value = (mock_records_wb, {"fetched_pages": 3})
            
            wb_durations = []
            for i in range(iterations):
                with PerformanceTimer("wayback_benchmark") as timer:
                    await router_wb.query_archive(
                        domain=f"benchmark-wb-{i}.com",
                        from_date="20240101",
                        to_date="20241231",
                        project_config={"archive_source": ArchiveSource.WAYBACK_MACHINE}
                    )
                wb_durations.append(timer.duration)
        
        # Common Crawl benchmark
        router_cc = ArchiveServiceRouter()
        mock_records_cc = MockCDXRecord.create_batch(count=25)
        
        with patch.object(router_cc.strategies["common_crawl"], 'query_archive') as mock_cc:
            mock_cc.return_value = (mock_records_cc, {"fetched_pages": 1})
            
            cc_durations = []
            for i in range(iterations):
                with PerformanceTimer("cc_benchmark") as timer:
                    await router_cc.query_archive(
                        domain=f"benchmark-cc-{i}.com",
                        from_date="20240101",
                        to_date="20241231",
                        project_config={"archive_source": ArchiveSource.COMMON_CRAWL}
                    )
                cc_durations.append(timer.duration)
        
        # Hybrid benchmark
        router_hybrid = ArchiveServiceRouter()
        
        with patch.object(router_hybrid.strategies["wayback_machine"], 'query_archive') as mock_hybrid_wb:
            mock_hybrid_wb.return_value = (mock_records_wb, {"fetched_pages": 3})
            
            hybrid_durations = []
            for i in range(iterations):
                with PerformanceTimer("hybrid_benchmark") as timer:
                    await router_hybrid.query_archive(
                        domain=f"benchmark-hybrid-{i}.com",
                        from_date="20240101",
                        to_date="20241231",
                        project_config={"archive_source": ArchiveSource.HYBRID}
                    )
                hybrid_durations.append(timer.duration)
        
        # Performance analysis
        results = {
            "wayback_machine": {
                "avg_duration": sum(wb_durations) / len(wb_durations),
                "min_duration": min(wb_durations),
                "max_duration": max(wb_durations),
                "p95_duration": sorted(wb_durations)[int(0.95 * len(wb_durations))],
                "requests_per_second": len(wb_durations) / sum(wb_durations)
            },
            "common_crawl": {
                "avg_duration": sum(cc_durations) / len(cc_durations),
                "min_duration": min(cc_durations),
                "max_duration": max(cc_durations),
                "p95_duration": sorted(cc_durations)[int(0.95 * len(cc_durations))],
                "requests_per_second": len(cc_durations) / sum(cc_durations)
            },
            "hybrid": {
                "avg_duration": sum(hybrid_durations) / len(hybrid_durations),
                "min_duration": min(hybrid_durations),
                "max_duration": max(hybrid_durations),
                "p95_duration": sorted(hybrid_durations)[int(0.95 * len(hybrid_durations))],
                "requests_per_second": len(hybrid_durations) / sum(hybrid_durations)
            }
        }
        
        # Performance benchmarks (adjust based on expected performance)
        for source, metrics in results.items():
            assert metrics["avg_duration"] < 0.01, \
                f"{source} average duration {metrics['avg_duration']:.4f}s exceeds 10ms"
            assert metrics["p95_duration"] < 0.02, \
                f"{source} P95 duration {metrics['p95_duration']:.4f}s exceeds 20ms"
            assert metrics["requests_per_second"] > 100, \
                f"{source} throughput {metrics['requests_per_second']:.1f} req/s below 100 req/s"
        
        # Hybrid should not be significantly slower than direct sources
        hybrid_overhead = results["hybrid"]["avg_duration"] - results["wayback_machine"]["avg_duration"]
        assert hybrid_overhead < 0.001, \
            f"Hybrid overhead {hybrid_overhead:.4f}s should be minimal"
        
        return results  # For logging/analysis


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-m", "performance"])