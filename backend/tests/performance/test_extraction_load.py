"""
Concurrent Extraction Load Testing for Robust Content Extraction System

Tests concurrent extraction handling up to 25 simultaneous requests and validates
circuit breaker behavior under stress conditions.
"""
import asyncio
import time
import pytest
import logging
import statistics
import psutil
import redis
from typing import List, Dict, Any, Tuple
from dataclasses import dataclass
from datetime import datetime, timedelta
import json
from unittest.mock import Mock, patch

from app.services.robust_content_extractor import (
    get_robust_extractor, 
    RobustContentExtractor,
    ExtractionStrategy,
    CIRCUIT_BREAKERS
)
from app.services.archive_org_client import get_archive_client
from app.models.extraction_data import ExtractedContent, ContentExtractionException

logger = logging.getLogger(__name__)

@dataclass
class LoadTestResult:
    """Results from a single load test run"""
    concurrent_requests: int
    successful_extractions: int
    failed_extractions: int
    total_duration: float
    avg_response_time: float
    median_response_time: float
    p95_response_time: float
    max_response_time: float
    min_response_time: float
    throughput_pages_per_second: float
    memory_usage_mb: float
    cpu_usage_percent: float
    circuit_breaker_trips: Dict[str, int]
    error_distribution: Dict[str, int]

@dataclass
class ExtractionResult:
    """Single extraction result with timing"""
    url: str
    success: bool
    duration: float
    error: str = None
    content_length: int = 0
    extraction_method: str = None

class ExtractionLoadTester:
    """Load tester for concurrent extractions"""
    
    def __init__(self):
        self.robust_extractor = get_robust_extractor()
        self.archive_client = get_archive_client()
        self.redis_client = redis.from_url("redis://localhost:6379/0")
        
        # Test URLs representing different content types and sizes
        self.test_urls = [
            # News articles
            "https://web.archive.org/web/20230615120000/https://www.reuters.com/business/",
            "https://web.archive.org/web/20230615120000/https://www.bbc.com/news/world",
            "https://web.archive.org/web/20230615120000/https://www.cnn.com/politics",
            
            # Academic/Research sites
            "https://web.archive.org/web/20230615120000/https://arxiv.org/abs/2301.00001",
            "https://web.archive.org/web/20230615120000/https://journals.nature.com/",
            "https://web.archive.org/web/20230615120000/https://www.ncbi.nlm.nih.gov/",
            
            # Government sites
            "https://web.archive.org/web/20230615120000/https://www.state.gov/",
            "https://web.archive.org/web/20230615120000/https://www.defense.gov/",
            "https://web.archive.org/web/20230615120000/https://www.cia.gov/",
            
            # Corporate sites
            "https://web.archive.org/web/20230615120000/https://www.microsoft.com/en-us/",
            "https://web.archive.org/web/20230615120000/https://www.google.com/about/",
            "https://web.archive.org/web/20230615120000/https://www.apple.com/newsroom/",
            
            # Technical documentation
            "https://web.archive.org/web/20230615120000/https://docs.python.org/3/",
            "https://web.archive.org/web/20230615120000/https://kubernetes.io/docs/",
            "https://web.archive.org/web/20230615120000/https://developer.mozilla.org/",
            
            # International content
            "https://web.archive.org/web/20230615120000/https://www.lemonde.fr/",
            "https://web.archive.org/web/20230615120000/https://www.spiegel.de/",
            "https://web.archive.org/web/20230615120000/https://www.asahi.com/",
            
            # Different content structures
            "https://web.archive.org/web/20230615120000/https://stackoverflow.com/questions",
            "https://web.archive.org/web/20230615120000/https://github.com/trending",
            "https://web.archive.org/web/20230615120000/https://www.reddit.com/r/technology",
        ]
    
    def _get_system_metrics(self) -> Tuple[float, float]:
        """Get current system memory and CPU usage"""
        process = psutil.Process()
        memory_mb = process.memory_info().rss / 1024 / 1024
        cpu_percent = process.cpu_percent()
        return memory_mb, cpu_percent
    
    def _get_circuit_breaker_states(self) -> Dict[str, Dict[str, Any]]:
        """Get circuit breaker states and failure counts"""
        states = {}
        for name, breaker in CIRCUIT_BREAKERS.items():
            try:
                states[name] = {
                    'state': breaker.current_state,
                    'failure_count': breaker.fail_counter,
                    'success_count': getattr(breaker, 'success_counter', 0)
                }
            except Exception as e:
                states[name] = {'error': str(e), 'state': 'unknown'}
        return states
    
    async def _extract_single_url(self, url: str) -> ExtractionResult:
        """Extract content from a single URL with timing"""
        start_time = time.time()
        
        try:
            result = await self.robust_extractor.extract_content(url)
            duration = time.time() - start_time
            
            return ExtractionResult(
                url=url,
                success=True,
                duration=duration,
                content_length=result.word_count,
                extraction_method=result.extraction_method
            )
        except Exception as e:
            duration = time.time() - start_time
            return ExtractionResult(
                url=url,
                success=False,
                duration=duration,
                error=str(e)
            )
    
    async def run_concurrent_load_test(self, concurrent_count: int, duration_seconds: int = 120) -> LoadTestResult:
        """
        Run concurrent extraction load test
        
        Args:
            concurrent_count: Number of concurrent extractions
            duration_seconds: Test duration in seconds
        """
        logger.info(f"Starting concurrent load test: {concurrent_count} concurrent requests for {duration_seconds}s")
        
        # Pre-test system state
        initial_memory, initial_cpu = self._get_system_metrics()
        initial_breaker_states = self._get_circuit_breaker_states()
        
        results: List[ExtractionResult] = []
        test_start_time = time.time()
        
        async def worker():
            """Worker coroutine for continuous extraction"""
            while time.time() - test_start_time < duration_seconds:
                # Select random URL for variety
                import random
                url = random.choice(self.test_urls)
                result = await self._extract_single_url(url)
                results.append(result)
        
        # Launch concurrent workers
        tasks = [asyncio.create_task(worker()) for _ in range(concurrent_count)]
        
        # Wait for test completion
        await asyncio.gather(*tasks, return_exceptions=True)
        
        total_test_duration = time.time() - test_start_time
        
        # Post-test system state
        final_memory, final_cpu = self._get_system_metrics()
        final_breaker_states = self._get_circuit_breaker_states()
        
        # Calculate metrics
        successful_results = [r for r in results if r.success]
        failed_results = [r for r in results if not r.success]
        
        if not results:
            raise ValueError("No extraction results collected")
        
        response_times = [r.duration for r in results]
        
        # Circuit breaker trip analysis
        breaker_trips = {}
        for name in CIRCUIT_BREAKERS.keys():
            initial_failures = initial_breaker_states.get(name, {}).get('failure_count', 0)
            final_failures = final_breaker_states.get(name, {}).get('failure_count', 0)
            breaker_trips[name] = final_failures - initial_failures
        
        # Error distribution analysis
        error_distribution = {}
        for result in failed_results:
            error_type = type(result.error).__name__ if hasattr(result.error, '__class__') else 'unknown'
            error_distribution[error_type] = error_distribution.get(error_type, 0) + 1
        
        return LoadTestResult(
            concurrent_requests=concurrent_count,
            successful_extractions=len(successful_results),
            failed_extractions=len(failed_results),
            total_duration=total_test_duration,
            avg_response_time=statistics.mean(response_times),
            median_response_time=statistics.median(response_times),
            p95_response_time=statistics.quantiles(response_times, n=20)[18] if len(response_times) >= 20 else max(response_times),
            max_response_time=max(response_times),
            min_response_time=min(response_times),
            throughput_pages_per_second=len(results) / total_test_duration,
            memory_usage_mb=final_memory,
            cpu_usage_percent=final_cpu,
            circuit_breaker_trips=breaker_trips,
            error_distribution=error_distribution
        )
    
    async def stress_test_circuit_breakers(self) -> Dict[str, Any]:
        """Test circuit breaker behavior under extreme load"""
        logger.info("Starting circuit breaker stress test")
        
        # Use invalid URLs to trigger failures
        failing_urls = [
            "https://web.archive.org/web/99999999999999/https://nonexistent-domain-12345.com/",
            "https://web.archive.org/web/20230615120000/https://this-will-definitely-fail.invalid/",
            "https://web.archive.org/web/20230615120000/https://timeout-test-url.example/very-long-path",
        ]
        
        initial_states = self._get_circuit_breaker_states()
        
        # Generate failures rapidly
        tasks = []
        for _ in range(50):  # 50 rapid failures
            for url in failing_urls:
                task = asyncio.create_task(self._extract_single_url(url))
                tasks.append(task)
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        final_states = self._get_circuit_breaker_states()
        
        # Analyze circuit breaker behavior
        breaker_analysis = {}
        for name in CIRCUIT_BREAKERS.keys():
            initial = initial_states.get(name, {})
            final = final_states.get(name, {})
            
            breaker_analysis[name] = {
                'initial_state': initial.get('state', 'unknown'),
                'final_state': final.get('state', 'unknown'),
                'failure_increase': final.get('failure_count', 0) - initial.get('failure_count', 0),
                'tripped': final.get('state') in ['open', 'half_open']
            }
        
        successful_failures = sum(1 for r in results if isinstance(r, ExtractionResult) and not r.success)
        exceptions = sum(1 for r in results if isinstance(r, Exception))
        
        return {
            'total_failure_attempts': len(results),
            'successful_failures': successful_failures,
            'exceptions': exceptions,
            'circuit_breaker_states': breaker_analysis,
            'any_breakers_tripped': any(analysis['tripped'] for analysis in breaker_analysis.values())
        }

# Test fixtures
@pytest.fixture
def load_tester():
    """Provide load tester instance"""
    return ExtractionLoadTester()

# Test cases
@pytest.mark.asyncio
@pytest.mark.slow
async def test_low_concurrency_baseline(load_tester):
    """Test baseline performance with low concurrency (5 concurrent)"""
    result = await load_tester.run_concurrent_load_test(
        concurrent_count=5,
        duration_seconds=60
    )
    
    # Baseline assertions
    assert result.successful_extractions > 0, "Should have successful extractions"
    assert result.throughput_pages_per_second > 0.5, f"Throughput too low: {result.throughput_pages_per_second:.2f} pages/sec"
    assert result.avg_response_time < 30.0, f"Average response time too high: {result.avg_response_time:.2f}s"
    assert result.memory_usage_mb < 1000, f"Memory usage too high: {result.memory_usage_mb:.1f}MB"
    
    logger.info(f"Baseline test results: {result.throughput_pages_per_second:.2f} pages/sec, "
               f"avg response: {result.avg_response_time:.2f}s")

@pytest.mark.asyncio
@pytest.mark.slow
async def test_medium_concurrency_performance(load_tester):
    """Test medium concurrency performance (10 concurrent)"""
    result = await load_tester.run_concurrent_load_test(
        concurrent_count=10,
        duration_seconds=90
    )
    
    # Performance assertions
    assert result.successful_extractions > 0, "Should have successful extractions"
    assert result.throughput_pages_per_second > 1.0, f"Throughput too low: {result.throughput_pages_per_second:.2f} pages/sec"
    assert result.avg_response_time < 45.0, f"Average response time too high: {result.avg_response_time:.2f}s"
    assert result.p95_response_time < 60.0, f"P95 response time too high: {result.p95_response_time:.2f}s"
    
    # Error rate should be reasonable
    error_rate = result.failed_extractions / (result.successful_extractions + result.failed_extractions)
    assert error_rate < 0.3, f"Error rate too high: {error_rate:.1%}"
    
    logger.info(f"Medium concurrency test results: {result.throughput_pages_per_second:.2f} pages/sec, "
               f"error rate: {error_rate:.1%}")

@pytest.mark.asyncio
@pytest.mark.slow
async def test_high_concurrency_load(load_tester):
    """Test high concurrency load (20 concurrent)"""
    result = await load_tester.run_concurrent_load_test(
        concurrent_count=20,
        duration_seconds=120
    )
    
    # High load assertions
    assert result.successful_extractions > 0, "Should have successful extractions"
    assert result.throughput_pages_per_second > 1.5, f"Throughput too low: {result.throughput_pages_per_second:.2f} pages/sec"
    
    # Should handle high load without complete failure
    error_rate = result.failed_extractions / (result.successful_extractions + result.failed_extractions)
    assert error_rate < 0.5, f"Error rate too high under load: {error_rate:.1%}"
    
    # Memory usage should be reasonable
    assert result.memory_usage_mb < 2000, f"Memory usage excessive: {result.memory_usage_mb:.1f}MB"
    
    logger.info(f"High concurrency test results: {result.throughput_pages_per_second:.2f} pages/sec, "
               f"memory: {result.memory_usage_mb:.1f}MB, error rate: {error_rate:.1%}")

@pytest.mark.asyncio
@pytest.mark.slow
async def test_maximum_concurrency_stress(load_tester):
    """Test maximum recommended concurrency (25 concurrent)"""
    result = await load_tester.run_concurrent_load_test(
        concurrent_count=25,
        duration_seconds=150
    )
    
    # Stress test assertions - more lenient for extreme load
    total_extractions = result.successful_extractions + result.failed_extractions
    assert total_extractions > 0, "Should complete some extractions"
    
    # Should maintain some level of throughput
    assert result.throughput_pages_per_second > 0.5, f"Throughput critically low: {result.throughput_pages_per_second:.2f} pages/sec"
    
    # System should remain responsive
    assert result.avg_response_time < 120.0, f"System unresponsive: {result.avg_response_time:.2f}s avg response"
    
    # Check for circuit breaker activation
    any_trips = any(trips > 0 for trips in result.circuit_breaker_trips.values())
    logger.info(f"Circuit breakers activated during stress test: {any_trips}")
    
    error_rate = result.failed_extractions / total_extractions if total_extractions > 0 else 1.0
    logger.info(f"Maximum concurrency test results: {result.throughput_pages_per_second:.2f} pages/sec, "
               f"error rate: {error_rate:.1%}, circuit breaker trips: {any_trips}")

@pytest.mark.asyncio
async def test_circuit_breaker_functionality(load_tester):
    """Test circuit breaker behavior under failure conditions"""
    stress_results = await load_tester.stress_test_circuit_breakers()
    
    # Circuit breakers should activate under high failure rate
    assert stress_results['any_breakers_tripped'], "Circuit breakers should trip under high failure rate"
    assert stress_results['successful_failures'] > 0, "Should record some failures before tripping"
    
    # Should have failure attempts
    assert stress_results['total_failure_attempts'] > 100, "Should have attempted many failures"
    
    logger.info(f"Circuit breaker test: {stress_results['total_failure_attempts']} attempts, "
               f"tripped: {stress_results['any_breakers_tripped']}")
    
    for name, analysis in stress_results['circuit_breaker_states'].items():
        logger.info(f"Breaker {name}: {analysis['initial_state']} -> {analysis['final_state']}, "
                   f"failures: +{analysis['failure_increase']}")

@pytest.mark.asyncio
async def test_memory_leak_detection(load_tester):
    """Test for memory leaks during sustained operation"""
    # Run multiple cycles to detect memory growth
    memory_measurements = []
    
    for cycle in range(3):
        logger.info(f"Memory leak test cycle {cycle + 1}/3")
        
        # Baseline measurement
        initial_memory, _ = load_tester._get_system_metrics()
        memory_measurements.append(initial_memory)
        
        # Run load test
        result = await load_tester.run_concurrent_load_test(
            concurrent_count=8,
            duration_seconds=45
        )
        
        # Post-test measurement
        final_memory, _ = load_tester._get_system_metrics()
        memory_measurements.append(final_memory)
        
        # Allow garbage collection
        import gc
        gc.collect()
        await asyncio.sleep(2)
    
    # Analyze memory growth trend
    memory_growth = memory_measurements[-1] - memory_measurements[0]
    avg_cycle_growth = memory_growth / len(range(3))
    
    # Memory growth should be reasonable
    assert memory_growth < 500, f"Excessive memory growth detected: {memory_growth:.1f}MB"
    assert avg_cycle_growth < 200, f"High average memory growth per cycle: {avg_cycle_growth:.1f}MB"
    
    logger.info(f"Memory leak test: Total growth {memory_growth:.1f}MB, "
               f"avg per cycle: {avg_cycle_growth:.1f}MB")

@pytest.mark.asyncio
async def test_archive_org_rate_limiting_compliance(load_tester):
    """Test Archive.org rate limiting compliance (15 requests/minute max)"""
    archive_client = load_tester.archive_client
    
    # Test URL from Archive.org
    test_url = "https://web.archive.org/web/20230615120000/https://www.example.com/"
    
    start_time = time.time()
    request_times = []
    
    # Make 10 requests and measure timing
    for i in range(10):
        request_start = time.time()
        try:
            await archive_client.fetch_content(test_url)
            request_times.append(time.time() - request_start)
        except Exception as e:
            logger.warning(f"Archive.org request {i+1} failed: {e}")
            request_times.append(0.0)  # Record failed attempt
    
    total_duration = time.time() - start_time
    
    # Calculate effective request rate
    completed_requests = sum(1 for t in request_times if t > 0)
    if completed_requests > 0:
        requests_per_minute = (completed_requests / total_duration) * 60
        
        # Should comply with 15 requests/minute limit
        assert requests_per_minute <= 16, f"Rate limiting not working: {requests_per_minute:.1f} req/min"
        
        # Should have reasonable spacing between requests (at least 3.5 seconds)
        if completed_requests > 1:
            avg_interval = total_duration / (completed_requests - 1)
            assert avg_interval >= 3.5, f"Request interval too short: {avg_interval:.1f}s"
    
    logger.info(f"Rate limiting test: {completed_requests} requests in {total_duration:.1f}s "
               f"({requests_per_minute:.1f} req/min)")

# Performance reporting
@pytest.mark.asyncio
async def test_generate_comprehensive_performance_report(load_tester):
    """Generate comprehensive performance report across different load levels"""
    concurrency_levels = [1, 5, 10, 15, 20, 25]
    performance_report = {
        'test_timestamp': datetime.now().isoformat(),
        'test_results': [],
        'system_info': {
            'cpu_count': psutil.cpu_count(),
            'memory_total_gb': psutil.virtual_memory().total / (1024**3),
        }
    }
    
    for concurrency in concurrency_levels:
        logger.info(f"Running performance test with {concurrency} concurrent extractions")
        
        try:
            result = await load_tester.run_concurrent_load_test(
                concurrent_count=concurrency,
                duration_seconds=60
            )
            
            # Convert result to dict for JSON serialization
            performance_report['test_results'].append({
                'concurrency_level': concurrency,
                'successful_extractions': result.successful_extractions,
                'failed_extractions': result.failed_extractions,
                'throughput_pages_per_second': result.throughput_pages_per_second,
                'avg_response_time': result.avg_response_time,
                'p95_response_time': result.p95_response_time,
                'memory_usage_mb': result.memory_usage_mb,
                'cpu_usage_percent': result.cpu_usage_percent,
                'circuit_breaker_trips': result.circuit_breaker_trips,
                'error_rate': result.failed_extractions / (result.successful_extractions + result.failed_extractions)
            })
            
        except Exception as e:
            logger.error(f"Performance test failed at concurrency {concurrency}: {e}")
            performance_report['test_results'].append({
                'concurrency_level': concurrency,
                'error': str(e),
                'test_failed': True
            })
    
    # Save report
    report_path = f"/tmp/extraction_performance_report_{int(time.time())}.json"
    with open(report_path, 'w') as f:
        json.dump(performance_report, f, indent=2)
    
    logger.info(f"Performance report saved to: {report_path}")
    
    # Basic assertions on overall performance
    successful_tests = [r for r in performance_report['test_results'] if not r.get('test_failed')]
    assert len(successful_tests) >= len(concurrency_levels) / 2, "More than half of tests should succeed"
    
    # Find peak throughput
    max_throughput = max(r['throughput_pages_per_second'] for r in successful_tests)
    logger.info(f"Peak throughput achieved: {max_throughput:.2f} pages/second")
    
    return performance_report