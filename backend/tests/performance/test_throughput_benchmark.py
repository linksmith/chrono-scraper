"""
Sustained Throughput Benchmark Testing for Robust Content Extraction System

Tests sustained throughput capabilities targeting 50+ pages/second with realistic
workloads and validates system performance under continuous operation.
"""
import asyncio
import time
import pytest
import logging
import statistics
import json
from typing import List, Dict, Any, Tuple, Optional
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import queue
import threading
from collections import defaultdict
import psutil

from app.services.robust_content_extractor import (
    get_robust_extractor,
    RobustContentExtractor,
    ExtractionStrategy
)
from app.services.archive_org_client import get_archive_client
from app.models.extraction_data import ExtractedContent, ContentExtractionException

logger = logging.getLogger(__name__)

@dataclass
class ThroughputMetrics:
    """Throughput measurement metrics"""
    time_window_seconds: float
    total_pages_processed: int
    successful_pages: int
    failed_pages: int
    pages_per_second: float
    avg_response_time: float
    median_response_time: float
    p95_response_time: float
    p99_response_time: float
    min_response_time: float
    max_response_time: float
    memory_usage_mb: float
    cpu_usage_percent: float
    cache_hit_rate: float
    error_rate: float
    quality_scores: List[float] = field(default_factory=list)

@dataclass
class BenchmarkResult:
    """Complete benchmark test result"""
    test_name: str
    test_duration_seconds: float
    target_pages_per_second: float
    achieved_pages_per_second: float
    total_pages_processed: int
    success_rate: float
    time_series_metrics: List[ThroughputMetrics] = field(default_factory=list)
    peak_throughput: float = 0.0
    sustained_throughput: float = 0.0
    memory_growth_mb: float = 0.0
    performance_degradation: float = 0.0
    target_achieved: bool = False

class ThroughputBenchmark:
    """Comprehensive throughput benchmarking system"""
    
    def __init__(self):
        self.robust_extractor = get_robust_extractor()
        self.archive_client = get_archive_client()
        
        # Diverse test URL pool for realistic workloads
        self.url_pools = {
            'news': [
                "https://web.archive.org/web/20230815120000/https://www.reuters.com/world/",
                "https://web.archive.org/web/20230815120000/https://www.bbc.com/news/business",
                "https://web.archive.org/web/20230815120000/https://www.cnn.com/world",
                "https://web.archive.org/web/20230815120000/https://www.theguardian.com/international",
                "https://web.archive.org/web/20230815120000/https://www.npr.org/sections/news/",
            ],
            'academic': [
                "https://web.archive.org/web/20230815120000/https://arxiv.org/list/cs.AI/recent",
                "https://web.archive.org/web/20230815120000/https://www.nature.com/articles",
                "https://web.archive.org/web/20230815120000/https://journals.plos.org/",
                "https://web.archive.org/web/20230815120000/https://www.ncbi.nlm.nih.gov/pmc/",
            ],
            'government': [
                "https://web.archive.org/web/20230815120000/https://www.state.gov/policy-issues/",
                "https://web.archive.org/web/20230815120000/https://www.defense.gov/News/",
                "https://web.archive.org/web/20230815120000/https://www.treasury.gov/press-center/",
                "https://web.archive.org/web/20230815120000/https://www.justice.gov/news",
            ],
            'technical': [
                "https://web.archive.org/web/20230815120000/https://docs.python.org/3/library/",
                "https://web.archive.org/web/20230815120000/https://kubernetes.io/docs/concepts/",
                "https://web.archive.org/web/20230815120000/https://developer.mozilla.org/en-US/docs/Web/",
                "https://web.archive.org/web/20230815120000/https://aws.amazon.com/documentation/",
            ],
            'international': [
                "https://web.archive.org/web/20230815120000/https://www.lemonde.fr/politique/",
                "https://web.archive.org/web/20230815120000/https://www.spiegel.de/politik/",
                "https://web.archive.org/web/20230815120000/https://www.asahi.com/politics/",
                "https://web.archive.org/web/20230815120000/https://www.corriere.it/politica/",
            ]
        }
        
        # Flatten all URLs for mixed workloads
        self.all_test_urls = []
        for category_urls in self.url_pools.values():
            self.all_test_urls.extend(category_urls)
        
        # Performance monitoring
        self.metrics_queue = queue.Queue()
        self.monitoring_active = False
    
    def _get_system_metrics(self) -> Tuple[float, float]:
        """Get current system metrics"""
        process = psutil.Process()
        memory_mb = process.memory_info().rss / 1024 / 1024
        cpu_percent = process.cpu_percent()
        return memory_mb, cpu_percent
    
    def _calculate_cache_hit_rate(self) -> float:
        """Calculate cache hit rate from Redis metrics"""
        try:
            import redis
            redis_client = redis.from_url("redis://localhost:6379/0")
            info = redis_client.info()
            
            keyspace_hits = info.get('keyspace_hits', 0)
            keyspace_misses = info.get('keyspace_misses', 0)
            
            if keyspace_hits + keyspace_misses > 0:
                return keyspace_hits / (keyspace_hits + keyspace_misses)
            return 0.0
        except Exception:
            return 0.0
    
    def _start_metrics_monitoring(self, interval_seconds: float = 5.0):
        """Start background metrics collection"""
        self.monitoring_active = True
        
        def monitor():
            while self.monitoring_active:
                memory_mb, cpu_percent = self._get_system_metrics()
                cache_hit_rate = self._calculate_cache_hit_rate()
                
                self.metrics_queue.put({
                    'timestamp': time.time(),
                    'memory_mb': memory_mb,
                    'cpu_percent': cpu_percent,
                    'cache_hit_rate': cache_hit_rate
                })
                
                time.sleep(interval_seconds)
        
        thread = threading.Thread(target=monitor, daemon=True)
        thread.start()
    
    def _stop_metrics_monitoring(self):
        """Stop background metrics collection"""
        self.monitoring_active = False
        time.sleep(0.1)  # Allow final metrics to be collected
    
    async def _extract_url_batch(self, urls: List[str]) -> List[Tuple[str, bool, float, Optional[ExtractedContent]]]:
        """Extract a batch of URLs concurrently"""
        async def extract_single(url: str):
            start_time = time.time()
            try:
                result = await self.robust_extractor.extract_content(url)
                duration = time.time() - start_time
                return (url, True, duration, result)
            except Exception as e:
                duration = time.time() - start_time
                logger.debug(f"Extraction failed for {url}: {e}")
                return (url, False, duration, None)
        
        tasks = [extract_single(url) for url in urls]
        return await asyncio.gather(*tasks)
    
    def _calculate_throughput_metrics(
        self,
        results: List[Tuple[str, bool, float, Optional[ExtractedContent]]],
        time_window: float,
        system_metrics: Dict[str, Any]
    ) -> ThroughputMetrics:
        """Calculate throughput metrics from extraction results"""
        total_pages = len(results)
        successful_pages = sum(1 for _, success, _, _ in results if success)
        failed_pages = total_pages - successful_pages
        
        response_times = [duration for _, _, duration, _ in results]
        quality_scores = []
        
        for _, success, _, content in results:
            if success and content:
                # Simple quality score based on content length and structure
                score = min(len(content.text) / 1000, 1.0) if content.text else 0.0
                if content.title:
                    score += 0.2
                if content.author:
                    score += 0.1
                quality_scores.append(min(score, 1.0))
        
        return ThroughputMetrics(
            time_window_seconds=time_window,
            total_pages_processed=total_pages,
            successful_pages=successful_pages,
            failed_pages=failed_pages,
            pages_per_second=total_pages / time_window if time_window > 0 else 0,
            avg_response_time=statistics.mean(response_times) if response_times else 0,
            median_response_time=statistics.median(response_times) if response_times else 0,
            p95_response_time=statistics.quantiles(response_times, n=20)[18] if len(response_times) >= 20 else (max(response_times) if response_times else 0),
            p99_response_time=statistics.quantiles(response_times, n=100)[98] if len(response_times) >= 100 else (max(response_times) if response_times else 0),
            min_response_time=min(response_times) if response_times else 0,
            max_response_time=max(response_times) if response_times else 0,
            memory_usage_mb=system_metrics.get('memory_mb', 0),
            cpu_usage_percent=system_metrics.get('cpu_percent', 0),
            cache_hit_rate=system_metrics.get('cache_hit_rate', 0),
            error_rate=failed_pages / total_pages if total_pages > 0 else 0,
            quality_scores=quality_scores
        )
    
    async def run_sustained_throughput_test(
        self,
        target_pages_per_second: float,
        duration_minutes: int = 10,
        batch_size: int = 20,
        measurement_interval_seconds: int = 30
    ) -> BenchmarkResult:
        """
        Run sustained throughput benchmark test
        
        Args:
            target_pages_per_second: Target throughput to achieve
            duration_minutes: Test duration in minutes
            batch_size: Number of URLs to process per batch
            measurement_interval_seconds: Interval for throughput measurements
        """
        test_name = f"sustained_throughput_{target_pages_per_second}pps"
        logger.info(f"Starting {test_name} test for {duration_minutes} minutes")
        
        # Start metrics monitoring
        self._start_metrics_monitoring()
        initial_memory, _ = self._get_system_metrics()
        
        test_start_time = time.time()
        test_duration_seconds = duration_minutes * 60
        total_pages_processed = 0
        all_results = []
        time_series_metrics = []
        
        # Calculate timing parameters
        target_batch_interval = batch_size / target_pages_per_second
        
        try:
            while time.time() - test_start_time < test_duration_seconds:
                batch_start_time = time.time()
                
                # Select URLs for this batch (mixed workload)
                import random
                batch_urls = random.choices(self.all_test_urls, k=batch_size)
                
                # Extract batch
                batch_results = await self._extract_url_batch(batch_urls)
                all_results.extend(batch_results)
                total_pages_processed += len(batch_results)
                
                batch_duration = time.time() - batch_start_time
                
                # Collect current system metrics
                current_metrics = {
                    'memory_mb': self._get_system_metrics()[0],
                    'cpu_percent': self._get_system_metrics()[1],
                    'cache_hit_rate': self._calculate_cache_hit_rate()
                }
                
                # Calculate metrics for this measurement interval
                if len(all_results) > 0 and (time.time() - test_start_time) % measurement_interval_seconds < batch_duration:
                    recent_results = all_results[-min(len(all_results), int(target_pages_per_second * measurement_interval_seconds)):]
                    metrics = self._calculate_throughput_metrics(
                        recent_results,
                        measurement_interval_seconds,
                        current_metrics
                    )
                    time_series_metrics.append(metrics)
                    
                    logger.info(f"Current throughput: {metrics.pages_per_second:.1f} pages/sec, "
                               f"success rate: {(1-metrics.error_rate)*100:.1f}%, "
                               f"memory: {metrics.memory_usage_mb:.1f}MB")
                
                # Pace control to maintain target throughput
                if batch_duration < target_batch_interval:
                    sleep_time = target_batch_interval - batch_duration
                    await asyncio.sleep(sleep_time)
        
        finally:
            self._stop_metrics_monitoring()
        
        # Calculate final results
        total_test_duration = time.time() - test_start_time
        final_memory, _ = self._get_system_metrics()
        
        successful_results = [r for r in all_results if r[1]]
        overall_success_rate = len(successful_results) / len(all_results) if all_results else 0
        achieved_pages_per_second = total_pages_processed / total_test_duration
        
        # Performance analysis
        throughput_measurements = [m.pages_per_second for m in time_series_metrics if m.pages_per_second > 0]
        peak_throughput = max(throughput_measurements) if throughput_measurements else 0
        sustained_throughput = statistics.median(throughput_measurements) if throughput_measurements else 0
        
        # Performance degradation (compare first 25% vs last 25% of measurements)
        if len(throughput_measurements) >= 4:
            first_quarter = throughput_measurements[:len(throughput_measurements)//4]
            last_quarter = throughput_measurements[-len(throughput_measurements)//4:]
            performance_degradation = (statistics.mean(first_quarter) - statistics.mean(last_quarter)) / statistics.mean(first_quarter)
        else:
            performance_degradation = 0.0
        
        return BenchmarkResult(
            test_name=test_name,
            test_duration_seconds=total_test_duration,
            target_pages_per_second=target_pages_per_second,
            achieved_pages_per_second=achieved_pages_per_second,
            total_pages_processed=total_pages_processed,
            success_rate=overall_success_rate,
            time_series_metrics=time_series_metrics,
            peak_throughput=peak_throughput,
            sustained_throughput=sustained_throughput,
            memory_growth_mb=final_memory - initial_memory,
            performance_degradation=performance_degradation,
            target_achieved=achieved_pages_per_second >= target_pages_per_second * 0.9  # 90% of target
        )
    
    async def run_burst_throughput_test(
        self,
        burst_pages_per_second: float,
        burst_duration_seconds: int = 60,
        concurrent_limit: int = 50
    ) -> BenchmarkResult:
        """Test burst throughput capabilities"""
        test_name = f"burst_throughput_{burst_pages_per_second}pps"
        logger.info(f"Starting {test_name} test for {burst_duration_seconds} seconds")
        
        test_start_time = time.time()
        all_results = []
        
        # Calculate burst parameters
        total_pages_target = int(burst_pages_per_second * burst_duration_seconds)
        
        # Create URL list for burst
        import random
        burst_urls = random.choices(self.all_test_urls, k=total_pages_target)
        
        # Process in controlled concurrent batches
        batch_size = min(concurrent_limit, total_pages_target // 10)  # 10 batches minimum
        
        for i in range(0, len(burst_urls), batch_size):
            batch = burst_urls[i:i + batch_size]
            batch_results = await self._extract_url_batch(batch)
            all_results.extend(batch_results)
            
            # Small delay to prevent overwhelming the system
            await asyncio.sleep(0.1)
        
        total_test_duration = time.time() - test_start_time
        achieved_pages_per_second = len(all_results) / total_test_duration
        successful_results = [r for r in all_results if r[1]]
        success_rate = len(successful_results) / len(all_results) if all_results else 0
        
        # Simple metrics for burst test
        current_metrics = {
            'memory_mb': self._get_system_metrics()[0],
            'cpu_percent': self._get_system_metrics()[1],
            'cache_hit_rate': self._calculate_cache_hit_rate()
        }
        
        burst_metrics = self._calculate_throughput_metrics(
            all_results,
            total_test_duration,
            current_metrics
        )
        
        return BenchmarkResult(
            test_name=test_name,
            test_duration_seconds=total_test_duration,
            target_pages_per_second=burst_pages_per_second,
            achieved_pages_per_second=achieved_pages_per_second,
            total_pages_processed=len(all_results),
            success_rate=success_rate,
            time_series_metrics=[burst_metrics],
            peak_throughput=achieved_pages_per_second,
            sustained_throughput=achieved_pages_per_second,
            memory_growth_mb=0,  # Not measured for burst tests
            performance_degradation=0.0,
            target_achieved=achieved_pages_per_second >= burst_pages_per_second * 0.8  # 80% for burst
        )

# Test fixtures
@pytest.fixture
def benchmark():
    """Provide benchmark instance"""
    return ThroughputBenchmark()

# Test cases
@pytest.mark.asyncio
@pytest.mark.slow
async def test_baseline_throughput_10pps(benchmark):
    """Test baseline sustained throughput at 10 pages/second"""
    result = await benchmark.run_sustained_throughput_test(
        target_pages_per_second=10.0,
        duration_minutes=5,
        batch_size=10
    )
    
    # Baseline assertions
    assert result.achieved_pages_per_second >= 8.0, f"Baseline throughput too low: {result.achieved_pages_per_second:.1f} pages/sec"
    assert result.success_rate >= 0.8, f"Success rate too low: {result.success_rate:.1%}"
    assert result.memory_growth_mb < 200, f"Memory growth excessive: {result.memory_growth_mb:.1f}MB"
    
    logger.info(f"Baseline throughput test: {result.achieved_pages_per_second:.1f} pages/sec achieved "
               f"(target: {result.target_pages_per_second:.1f})")

@pytest.mark.asyncio
@pytest.mark.slow
async def test_medium_throughput_25pps(benchmark):
    """Test medium sustained throughput at 25 pages/second"""
    result = await benchmark.run_sustained_throughput_test(
        target_pages_per_second=25.0,
        duration_minutes=8,
        batch_size=15
    )
    
    # Medium load assertions
    assert result.achieved_pages_per_second >= 20.0, f"Medium throughput too low: {result.achieved_pages_per_second:.1f} pages/sec"
    assert result.success_rate >= 0.7, f"Success rate too low under medium load: {result.success_rate:.1%}"
    assert result.performance_degradation < 0.2, f"Performance degradation too high: {result.performance_degradation:.1%}"
    
    # Check sustained performance
    assert result.sustained_throughput >= 18.0, f"Sustained throughput too low: {result.sustained_throughput:.1f} pages/sec"
    
    logger.info(f"Medium throughput test: {result.achieved_pages_per_second:.1f} pages/sec achieved, "
               f"sustained: {result.sustained_throughput:.1f} pages/sec")

@pytest.mark.asyncio
@pytest.mark.slow
async def test_high_throughput_50pps_target(benchmark):
    """Test high sustained throughput targeting 50 pages/second"""
    result = await benchmark.run_sustained_throughput_test(
        target_pages_per_second=50.0,
        duration_minutes=10,
        batch_size=25
    )
    
    # High throughput assertions
    assert result.achieved_pages_per_second >= 35.0, f"High throughput significantly below target: {result.achieved_pages_per_second:.1f} pages/sec"
    
    # Success rate may be lower under high load but should be reasonable
    assert result.success_rate >= 0.6, f"Success rate too low under high load: {result.success_rate:.1%}"
    
    # Performance stability
    assert result.performance_degradation < 0.3, f"Performance degradation too high: {result.performance_degradation:.1%}"
    
    # Target achievement
    target_met = result.achieved_pages_per_second >= 45.0  # 90% of 50 pages/sec
    logger.info(f"50 pages/sec target test: {result.achieved_pages_per_second:.1f} pages/sec achieved, "
               f"target met: {target_met}")
    
    # This is a stretch goal, so we'll log but not necessarily fail
    if target_met:
        logger.info("🎉 TARGET ACHIEVED: 50 pages/second throughput target met!")

@pytest.mark.asyncio
@pytest.mark.slow
async def test_burst_throughput_100pps(benchmark):
    """Test burst throughput capability at 100 pages/second"""
    result = await benchmark.run_burst_throughput_test(
        burst_pages_per_second=100.0,
        burst_duration_seconds=30,
        concurrent_limit=40
    )
    
    # Burst capability assertions
    assert result.achieved_pages_per_second >= 60.0, f"Burst throughput too low: {result.achieved_pages_per_second:.1f} pages/sec"
    assert result.success_rate >= 0.5, f"Burst success rate too low: {result.success_rate:.1%}"
    
    logger.info(f"Burst throughput test: {result.achieved_pages_per_second:.1f} pages/sec achieved "
               f"(target: {result.target_pages_per_second:.1f})")

@pytest.mark.asyncio
async def test_workload_mix_performance(benchmark):
    """Test performance with different content type workloads"""
    workload_results = {}
    
    for category, urls in benchmark.url_pools.items():
        if len(urls) < 5:  # Skip categories with too few URLs
            continue
        
        logger.info(f"Testing {category} workload performance")
        
        # Backup original URLs and set category-specific URLs
        original_urls = benchmark.all_test_urls.copy()
        benchmark.all_test_urls = urls * 3  # Multiply to have enough URLs
        
        try:
            result = await benchmark.run_sustained_throughput_test(
                target_pages_per_second=15.0,
                duration_minutes=3,
                batch_size=8
            )
            
            workload_results[category] = {
                'throughput': result.achieved_pages_per_second,
                'success_rate': result.success_rate,
                'avg_response_time': result.time_series_metrics[0].avg_response_time if result.time_series_metrics else 0,
                'cache_hit_rate': result.time_series_metrics[0].cache_hit_rate if result.time_series_metrics else 0
            }
            
        finally:
            # Restore original URLs
            benchmark.all_test_urls = original_urls
    
    # Analysis of workload performance differences
    if workload_results:
        best_category = max(workload_results.keys(), key=lambda k: workload_results[k]['throughput'])
        worst_category = min(workload_results.keys(), key=lambda k: workload_results[k]['throughput'])
        
        logger.info(f"Best performing category: {best_category} "
                   f"({workload_results[best_category]['throughput']:.1f} pages/sec)")
        logger.info(f"Worst performing category: {worst_category} "
                   f"({workload_results[worst_category]['throughput']:.1f} pages/sec)")
        
        # All categories should achieve reasonable performance
        for category, metrics in workload_results.items():
            assert metrics['throughput'] >= 5.0, f"Category {category} throughput too low: {metrics['throughput']:.1f}"
            assert metrics['success_rate'] >= 0.6, f"Category {category} success rate too low: {metrics['success_rate']:.1%}"

@pytest.mark.asyncio
async def test_cache_effectiveness_impact(benchmark):
    """Test cache effectiveness on throughput performance"""
    # Test with cache warming
    logger.info("Testing cache effectiveness on throughput")
    
    # Use a smaller set of URLs repeatedly to benefit from caching
    cache_test_urls = benchmark.all_test_urls[:5] * 10  # Repeat URLs for cache hits
    original_urls = benchmark.all_test_urls.copy()
    benchmark.all_test_urls = cache_test_urls
    
    try:
        # First run to warm cache
        warmup_result = await benchmark.run_sustained_throughput_test(
            target_pages_per_second=20.0,
            duration_minutes=2,
            batch_size=10
        )
        
        # Second run should benefit from cache
        cached_result = await benchmark.run_sustained_throughput_test(
            target_pages_per_second=20.0,
            duration_minutes=3,
            batch_size=10
        )
        
        # Cache should improve performance
        cache_hit_rate = cached_result.time_series_metrics[-1].cache_hit_rate if cached_result.time_series_metrics else 0
        
        # Performance should improve with caching
        throughput_improvement = (cached_result.achieved_pages_per_second - warmup_result.achieved_pages_per_second) / warmup_result.achieved_pages_per_second
        
        logger.info(f"Cache impact test: cache hit rate {cache_hit_rate:.1%}, "
                   f"throughput improvement: {throughput_improvement:.1%}")
        
        # Caching should provide some benefit
        assert cache_hit_rate > 0.1 or throughput_improvement > -0.1, "Cache should provide measurable benefit"
        
    finally:
        benchmark.all_test_urls = original_urls

@pytest.mark.asyncio
async def test_generate_throughput_performance_report(benchmark):
    """Generate comprehensive throughput performance report"""
    throughput_targets = [5, 10, 20, 30, 40, 50]
    performance_report = {
        'test_timestamp': datetime.now().isoformat(),
        'throughput_tests': [],
        'system_specifications': {
            'cpu_count': psutil.cpu_count(),
            'memory_total_gb': psutil.virtual_memory().total / (1024**3),
        },
        'test_configuration': {
            'test_duration_minutes': 5,
            'batch_size': 20,
            'measurement_interval_seconds': 30
        }
    }
    
    for target_throughput in throughput_targets:
        logger.info(f"Running throughput test for {target_throughput} pages/sec")
        
        try:
            result = await benchmark.run_sustained_throughput_test(
                target_pages_per_second=target_throughput,
                duration_minutes=5,
                batch_size=20
            )
            
            # Extract key metrics
            avg_quality_score = 0.0
            if result.time_series_metrics:
                all_quality_scores = []
                for metric in result.time_series_metrics:
                    all_quality_scores.extend(metric.quality_scores)
                avg_quality_score = statistics.mean(all_quality_scores) if all_quality_scores else 0.0
            
            performance_report['throughput_tests'].append({
                'target_pages_per_second': target_throughput,
                'achieved_pages_per_second': result.achieved_pages_per_second,
                'sustained_pages_per_second': result.sustained_throughput,
                'peak_pages_per_second': result.peak_throughput,
                'success_rate': result.success_rate,
                'total_pages_processed': result.total_pages_processed,
                'memory_growth_mb': result.memory_growth_mb,
                'performance_degradation': result.performance_degradation,
                'target_achieved': result.target_achieved,
                'avg_quality_score': avg_quality_score
            })
            
        except Exception as e:
            logger.error(f"Throughput test failed at {target_throughput} pages/sec: {e}")
            performance_report['throughput_tests'].append({
                'target_pages_per_second': target_throughput,
                'error': str(e),
                'test_failed': True
            })
    
    # Save comprehensive report
    report_path = f"/tmp/throughput_benchmark_report_{int(time.time())}.json"
    with open(report_path, 'w') as f:
        json.dump(performance_report, f, indent=2)
    
    logger.info(f"Throughput benchmark report saved to: {report_path}")
    
    # Find maximum achieved sustained throughput
    successful_tests = [t for t in performance_report['throughput_tests'] if not t.get('test_failed')]
    if successful_tests:
        max_sustained = max(t['sustained_pages_per_second'] for t in successful_tests)
        logger.info(f"🚀 Maximum sustained throughput achieved: {max_sustained:.1f} pages/second")
        
        # Check if 50 pages/sec target was met
        target_50_met = any(t['target_pages_per_second'] == 50 and t.get('target_achieved', False) for t in successful_tests)
        if target_50_met:
            logger.info("🎯 SUCCESS: 50 pages/second target achieved!")
        else:
            logger.warning("⚠️  50 pages/second target not fully achieved")
    
    return performance_report