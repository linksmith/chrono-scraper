"""
Resource Monitoring and Memory Management Testing for Robust Extraction System

Monitors memory usage, CPU utilization, and system resource consumption during
sustained extraction operations to detect memory leaks and performance bottlenecks.
"""
import asyncio
import time
import pytest
import logging
import psutil
import gc
import threading
from typing import List, Dict, Any, Tuple, Optional
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import json
import statistics
import redis

from app.services.robust_content_extractor import (
    get_robust_extractor,
    RobustContentExtractor,
    CIRCUIT_BREAKERS
)
from app.models.extraction_data import ExtractedContent, ContentExtractionException

logger = logging.getLogger(__name__)

@dataclass
class ResourceSnapshot:
    """Single point-in-time resource measurement"""
    timestamp: float
    memory_rss_mb: float
    memory_vms_mb: float
    memory_percent: float
    cpu_percent: float
    threads_count: int
    open_files_count: int
    connections_count: int
    redis_memory_mb: float = 0.0
    redis_connected_clients: int = 0
    extraction_cache_size: int = 0

@dataclass
class ResourceMonitoringResult:
    """Complete resource monitoring test result"""
    test_name: str
    test_duration_seconds: float
    total_extractions: int
    successful_extractions: int
    snapshots: List[ResourceSnapshot] = field(default_factory=list)
    memory_leak_detected: bool = False
    peak_memory_mb: float = 0.0
    avg_memory_mb: float = 0.0
    memory_growth_rate_mb_per_hour: float = 0.0
    peak_cpu_percent: float = 0.0
    avg_cpu_percent: float = 0.0
    peak_threads: int = 0
    peak_open_files: int = 0
    redis_memory_growth_mb: float = 0.0
    gc_collections_triggered: int = 0
    performance_degradation: float = 0.0

class ResourceMonitor:
    """Advanced system resource monitoring for extraction operations"""
    
    def __init__(self):
        self.robust_extractor = get_robust_extractor()
        self.process = psutil.Process()
        self.monitoring_active = False
        self.snapshots: List[ResourceSnapshot] = []
        self.monitoring_interval = 2.0  # seconds
        self.redis_client = None
        
        try:
            self.redis_client = redis.from_url("redis://localhost:6379/0")
        except Exception as e:
            logger.warning(f"Could not connect to Redis for monitoring: {e}")
    
    def _get_redis_metrics(self) -> Tuple[float, int]:
        """Get Redis memory usage and connection count"""
        if not self.redis_client:
            return 0.0, 0
        
        try:
            info = self.redis_client.info()
            memory_mb = info.get('used_memory', 0) / (1024 * 1024)
            clients = info.get('connected_clients', 0)
            return memory_mb, clients
        except Exception:
            return 0.0, 0
    
    def _get_extraction_cache_size(self) -> int:
        """Get current extraction cache size"""
        if not self.redis_client:
            return 0
        
        try:
            # Count keys matching the extraction cache prefix
            pattern = "robust_extraction:*"
            keys = self.redis_client.keys(pattern)
            return len(keys)
        except Exception:
            return 0
    
    def _take_resource_snapshot(self) -> ResourceSnapshot:
        """Take a complete system resource snapshot"""
        try:
            # Process memory info
            memory_info = self.process.memory_info()
            memory_percent = self.process.memory_percent()
            
            # CPU usage
            cpu_percent = self.process.cpu_percent()
            
            # Thread and file handle count
            threads_count = self.process.num_threads()
            
            try:
                open_files_count = len(self.process.open_files())
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                open_files_count = 0
            
            try:
                connections_count = len(self.process.connections())
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                connections_count = 0
            
            # Redis metrics
            redis_memory_mb, redis_clients = self._get_redis_metrics()
            cache_size = self._get_extraction_cache_size()
            
            return ResourceSnapshot(
                timestamp=time.time(),
                memory_rss_mb=memory_info.rss / (1024 * 1024),
                memory_vms_mb=memory_info.vms / (1024 * 1024),
                memory_percent=memory_percent,
                cpu_percent=cpu_percent,
                threads_count=threads_count,
                open_files_count=open_files_count,
                connections_count=connections_count,
                redis_memory_mb=redis_memory_mb,
                redis_connected_clients=redis_clients,
                extraction_cache_size=cache_size
            )
        except Exception as e:
            logger.error(f"Failed to take resource snapshot: {e}")
            # Return minimal snapshot with current time
            return ResourceSnapshot(
                timestamp=time.time(),
                memory_rss_mb=0.0,
                memory_vms_mb=0.0,
                memory_percent=0.0,
                cpu_percent=0.0,
                threads_count=0,
                open_files_count=0,
                connections_count=0
            )
    
    def start_monitoring(self):
        """Start background resource monitoring"""
        self.monitoring_active = True
        self.snapshots = []
        
        def monitor_loop():
            while self.monitoring_active:
                snapshot = self._take_resource_snapshot()
                self.snapshots.append(snapshot)
                time.sleep(self.monitoring_interval)
        
        self.monitor_thread = threading.Thread(target=monitor_loop, daemon=True)
        self.monitor_thread.start()
        logger.info("Resource monitoring started")
    
    def stop_monitoring(self) -> List[ResourceSnapshot]:
        """Stop monitoring and return collected snapshots"""
        self.monitoring_active = False
        if hasattr(self, 'monitor_thread'):
            self.monitor_thread.join(timeout=5.0)
        
        logger.info(f"Resource monitoring stopped. Collected {len(self.snapshots)} snapshots")
        return self.snapshots.copy()
    
    def _analyze_memory_leak(self, snapshots: List[ResourceSnapshot]) -> Tuple[bool, float]:
        """Analyze snapshots for memory leak patterns"""
        if len(snapshots) < 10:  # Need sufficient data points
            return False, 0.0
        
        # Calculate memory trend over time
        times = [s.timestamp for s in snapshots]
        memories = [s.memory_rss_mb for s in snapshots]
        
        # Simple linear regression to detect trend
        n = len(times)
        sum_t = sum(times)
        sum_m = sum(memories)
        sum_tm = sum(t * m for t, m in zip(times, memories))
        sum_t2 = sum(t * t for t in times)
        
        # Calculate slope (memory growth rate)
        slope = (n * sum_tm - sum_t * sum_m) / (n * sum_t2 - sum_t * sum_t)
        
        # Convert to MB per hour
        growth_rate_mb_per_hour = slope * 3600
        
        # Detect significant memory leak (>50MB/hour growth)
        leak_detected = growth_rate_mb_per_hour > 50.0
        
        return leak_detected, growth_rate_mb_per_hour
    
    def _calculate_performance_degradation(self, snapshots: List[ResourceSnapshot]) -> float:
        """Calculate performance degradation over time"""
        if len(snapshots) < 10:
            return 0.0
        
        # Compare first 25% vs last 25% of CPU usage
        quarter = len(snapshots) // 4
        if quarter < 2:
            return 0.0
        
        first_quarter_cpu = [s.cpu_percent for s in snapshots[:quarter]]
        last_quarter_cpu = [s.cpu_percent for s in snapshots[-quarter:]]
        
        first_avg = statistics.mean(first_quarter_cpu)
        last_avg = statistics.mean(last_quarter_cpu)
        
        if first_avg > 0:
            return (last_avg - first_avg) / first_avg
        return 0.0
    
    async def run_memory_stress_test(
        self,
        duration_minutes: int = 15,
        concurrent_extractions: int = 12,
        force_gc_interval: int = 60
    ) -> ResourceMonitoringResult:
        """Run memory stress test with sustained extractions"""
        test_name = f"memory_stress_{concurrent_extractions}concurrent"
        logger.info(f"Starting {test_name} test for {duration_minutes} minutes")
        
        # Start monitoring
        self.start_monitoring()
        initial_snapshot = self._take_resource_snapshot()
        
        test_start_time = time.time()
        test_duration_seconds = duration_minutes * 60
        total_extractions = 0
        successful_extractions = 0
        gc_collections = 0
        
        # Test URLs for sustained load
        test_urls = [
            "https://web.archive.org/web/20230815120000/https://www.reuters.com/world/",
            "https://web.archive.org/web/20230815120000/https://www.bbc.com/news/business",
            "https://web.archive.org/web/20230815120000/https://www.nature.com/articles",
            "https://web.archive.org/web/20230815120000/https://arxiv.org/list/cs.AI/recent",
            "https://web.archive.org/web/20230815120000/https://docs.python.org/3/library/",
        ] * 5  # Repeat for variety
        
        async def extraction_worker(worker_id: int):
            """Worker coroutine for continuous extraction"""
            nonlocal total_extractions, successful_extractions
            
            import random
            worker_extractions = 0
            
            while time.time() - test_start_time < test_duration_seconds:
                try:
                    url = random.choice(test_urls)
                    result = await self.robust_extractor.extract_content(url)
                    successful_extractions += 1
                    worker_extractions += 1
                except Exception as e:
                    logger.debug(f"Worker {worker_id} extraction failed: {e}")
                finally:
                    total_extractions += 1
                
                # Small delay to prevent overwhelming
                await asyncio.sleep(0.5)
            
            logger.debug(f"Worker {worker_id} completed {worker_extractions} extractions")
        
        # Start extraction workers
        workers = [
            asyncio.create_task(extraction_worker(i))
            for i in range(concurrent_extractions)
        ]
        
        # Periodic garbage collection
        async def gc_scheduler():
            nonlocal gc_collections
            while time.time() - test_start_time < test_duration_seconds:
                await asyncio.sleep(force_gc_interval)
                gc.collect()
                gc_collections += 1
                logger.debug(f"Forced garbage collection #{gc_collections}")
        
        gc_task = asyncio.create_task(gc_scheduler())
        
        # Run test
        try:
            await asyncio.gather(*workers, gc_task, return_exceptions=True)
        finally:
            # Stop monitoring
            snapshots = self.stop_monitoring()
        
        total_test_duration = time.time() - test_start_time
        
        # Analyze results
        memory_leak_detected, growth_rate = self._analyze_memory_leak(snapshots)
        performance_degradation = self._calculate_performance_degradation(snapshots)
        
        # Calculate metrics
        memory_values = [s.memory_rss_mb for s in snapshots if s.memory_rss_mb > 0]
        cpu_values = [s.cpu_percent for s in snapshots if s.cpu_percent > 0]
        
        peak_memory = max(memory_values) if memory_values else 0
        avg_memory = statistics.mean(memory_values) if memory_values else 0
        peak_cpu = max(cpu_values) if cpu_values else 0
        avg_cpu = statistics.mean(cpu_values) if cpu_values else 0
        
        peak_threads = max(s.threads_count for s in snapshots)
        peak_files = max(s.open_files_count for s in snapshots)
        
        # Redis memory growth
        redis_growth = 0.0
        if snapshots:
            initial_redis = snapshots[0].redis_memory_mb
            final_redis = snapshots[-1].redis_memory_mb
            redis_growth = final_redis - initial_redis
        
        return ResourceMonitoringResult(
            test_name=test_name,
            test_duration_seconds=total_test_duration,
            total_extractions=total_extractions,
            successful_extractions=successful_extractions,
            snapshots=snapshots,
            memory_leak_detected=memory_leak_detected,
            peak_memory_mb=peak_memory,
            avg_memory_mb=avg_memory,
            memory_growth_rate_mb_per_hour=growth_rate,
            peak_cpu_percent=peak_cpu,
            avg_cpu_percent=avg_cpu,
            peak_threads=peak_threads,
            peak_open_files=peak_files,
            redis_memory_growth_mb=redis_growth,
            gc_collections_triggered=gc_collections,
            performance_degradation=performance_degradation
        )
    
    async def run_resource_limit_test(
        self,
        memory_limit_mb: int = 1500,
        duration_minutes: int = 10
    ) -> ResourceMonitoringResult:
        """Test behavior under resource constraints"""
        test_name = f"resource_limit_{memory_limit_mb}mb"
        logger.info(f"Starting {test_name} test with {memory_limit_mb}MB memory target")
        
        self.start_monitoring()
        
        test_start_time = time.time()
        test_duration_seconds = duration_minutes * 60
        total_extractions = 0
        successful_extractions = 0
        
        # Use larger batch sizes to increase memory pressure
        test_urls = [
            "https://web.archive.org/web/20230815120000/https://en.wikipedia.org/wiki/Main_Page",
            "https://web.archive.org/web/20230815120000/https://www.theguardian.com/",
            "https://web.archive.org/web/20230815120000/https://www.nytimes.com/",
            "https://web.archive.org/web/20230815120000/https://stackoverflow.com/",
        ] * 10
        
        try:
            while time.time() - test_start_time < test_duration_seconds:
                current_memory = self.process.memory_info().rss / (1024 * 1024)
                
                if current_memory > memory_limit_mb:
                    logger.warning(f"Memory limit exceeded: {current_memory:.1f}MB > {memory_limit_mb}MB")
                    # Force garbage collection
                    gc.collect()
                    await asyncio.sleep(2)
                    continue
                
                # Process URLs in batches
                import random
                batch_size = min(8, len(test_urls))
                batch_urls = random.choices(test_urls, k=batch_size)
                
                batch_tasks = []
                for url in batch_urls:
                    task = asyncio.create_task(self._extract_with_monitoring(url))
                    batch_tasks.append(task)
                
                batch_results = await asyncio.gather(*batch_tasks, return_exceptions=True)
                
                # Count results
                for result in batch_results:
                    total_extractions += 1
                    if not isinstance(result, Exception):
                        successful_extractions += 1
                
                # Brief pause between batches
                await asyncio.sleep(1)
        
        finally:
            snapshots = self.stop_monitoring()
        
        total_test_duration = time.time() - test_start_time
        
        # Check if memory limit was respected
        peak_memory = max(s.memory_rss_mb for s in snapshots) if snapshots else 0
        memory_limit_exceeded = peak_memory > memory_limit_mb * 1.1  # 10% tolerance
        
        memory_leak_detected, growth_rate = self._analyze_memory_leak(snapshots)
        
        return ResourceMonitoringResult(
            test_name=test_name,
            test_duration_seconds=total_test_duration,
            total_extractions=total_extractions,
            successful_extractions=successful_extractions,
            snapshots=snapshots,
            memory_leak_detected=memory_leak_detected,
            peak_memory_mb=peak_memory,
            avg_memory_mb=statistics.mean([s.memory_rss_mb for s in snapshots]) if snapshots else 0,
            memory_growth_rate_mb_per_hour=growth_rate,
            peak_cpu_percent=max(s.cpu_percent for s in snapshots) if snapshots else 0,
            avg_cpu_percent=statistics.mean([s.cpu_percent for s in snapshots]) if snapshots else 0,
            peak_threads=max(s.threads_count for s in snapshots) if snapshots else 0,
            peak_open_files=max(s.open_files_count for s in snapshots) if snapshots else 0,
            redis_memory_growth_mb=0.0,
            gc_collections_triggered=0,
            performance_degradation=self._calculate_performance_degradation(snapshots)
        )
    
    async def _extract_with_monitoring(self, url: str) -> Optional[ExtractedContent]:
        """Extract URL with basic error handling for monitoring tests"""
        try:
            return await self.robust_extractor.extract_content(url)
        except Exception as e:
            logger.debug(f"Extraction failed for monitoring test: {e}")
            return None

# Test fixtures
@pytest.fixture
def resource_monitor():
    """Provide resource monitor instance"""
    return ResourceMonitor()

# Test cases
@pytest.mark.asyncio
@pytest.mark.slow
async def test_baseline_resource_usage(resource_monitor):
    """Test baseline resource usage with light load"""
    result = await resource_monitor.run_memory_stress_test(
        duration_minutes=5,
        concurrent_extractions=3,
        force_gc_interval=30
    )
    
    # Baseline resource assertions
    assert not result.memory_leak_detected, f"Memory leak detected in baseline test: {result.memory_growth_rate_mb_per_hour:.1f} MB/hour"
    assert result.peak_memory_mb < 800, f"Peak memory too high for baseline: {result.peak_memory_mb:.1f}MB"
    assert result.avg_cpu_percent < 60, f"Average CPU too high: {result.avg_cpu_percent:.1f}%"
    assert result.successful_extractions > 0, "Should complete some extractions"
    
    success_rate = result.successful_extractions / result.total_extractions if result.total_extractions > 0 else 0
    assert success_rate >= 0.8, f"Success rate too low: {success_rate:.1%}"
    
    logger.info(f"Baseline resource test: {result.peak_memory_mb:.1f}MB peak, "
               f"growth rate: {result.memory_growth_rate_mb_per_hour:.1f} MB/hour")

@pytest.mark.asyncio
@pytest.mark.slow
async def test_sustained_memory_usage(resource_monitor):
    """Test memory usage during sustained extraction operations"""
    result = await resource_monitor.run_memory_stress_test(
        duration_minutes=12,
        concurrent_extractions=8,
        force_gc_interval=45
    )
    
    # Sustained operation assertions
    assert not result.memory_leak_detected, f"Memory leak detected: {result.memory_growth_rate_mb_per_hour:.1f} MB/hour"
    assert result.peak_memory_mb < 1200, f"Peak memory too high: {result.peak_memory_mb:.1f}MB"
    assert result.memory_growth_rate_mb_per_hour < 100, f"Memory growth rate too high: {result.memory_growth_rate_mb_per_hour:.1f} MB/hour"
    
    # Performance should remain stable
    assert abs(result.performance_degradation) < 0.3, f"Performance degradation too high: {result.performance_degradation:.1%}"
    
    # Resource utilization should be reasonable
    assert result.peak_threads < 50, f"Too many threads created: {result.peak_threads}"
    assert result.peak_open_files < 200, f"Too many open files: {result.peak_open_files}"
    
    logger.info(f"Sustained memory test: {result.peak_memory_mb:.1f}MB peak, "
               f"threads: {result.peak_threads}, files: {result.peak_open_files}")

@pytest.mark.asyncio
@pytest.mark.slow
async def test_high_concurrency_resource_usage(resource_monitor):
    """Test resource usage under high concurrency load"""
    result = await resource_monitor.run_memory_stress_test(
        duration_minutes=10,
        concurrent_extractions=15,
        force_gc_interval=30
    )
    
    # High concurrency assertions
    assert result.peak_memory_mb < 1800, f"Peak memory excessive under high load: {result.peak_memory_mb:.1f}MB"
    assert result.memory_growth_rate_mb_per_hour < 150, f"Memory growth too rapid: {result.memory_growth_rate_mb_per_hour:.1f} MB/hour"
    
    # System should remain responsive
    assert result.avg_cpu_percent < 85, f"CPU utilization too high: {result.avg_cpu_percent:.1f}%"
    assert result.peak_threads < 80, f"Thread count excessive: {result.peak_threads}"
    
    # Should complete reasonable number of extractions
    extractions_per_minute = result.total_extractions / (result.test_duration_seconds / 60)
    assert extractions_per_minute >= 10, f"Extraction rate too low: {extractions_per_minute:.1f}/min"
    
    logger.info(f"High concurrency test: {result.peak_memory_mb:.1f}MB peak, "
               f"{extractions_per_minute:.1f} extractions/min")

@pytest.mark.asyncio
async def test_memory_constraint_compliance(resource_monitor):
    """Test behavior under memory constraints"""
    memory_limit_mb = 1000
    result = await resource_monitor.run_resource_limit_test(
        memory_limit_mb=memory_limit_mb,
        duration_minutes=8
    )
    
    # Memory constraint assertions
    memory_exceeded = result.peak_memory_mb > memory_limit_mb * 1.1  # 10% tolerance
    assert not memory_exceeded, f"Memory limit exceeded: {result.peak_memory_mb:.1f}MB > {memory_limit_mb * 1.1:.1f}MB"
    
    # Should still complete some work within constraints
    assert result.successful_extractions > 0, "Should complete some extractions under memory constraints"
    
    success_rate = result.successful_extractions / result.total_extractions if result.total_extractions > 0 else 0
    logger.info(f"Memory constraint test: {result.peak_memory_mb:.1f}MB peak (limit: {memory_limit_mb}MB), "
               f"success rate: {success_rate:.1%}")

@pytest.mark.asyncio
async def test_redis_memory_growth(resource_monitor):
    """Test Redis memory usage and cache growth"""
    result = await resource_monitor.run_memory_stress_test(
        duration_minutes=8,
        concurrent_extractions=10,
        force_gc_interval=60
    )
    
    # Redis should not grow excessively
    assert abs(result.redis_memory_growth_mb) < 200, f"Redis memory growth excessive: {result.redis_memory_growth_mb:.1f}MB"
    
    # Check cache effectiveness
    if result.snapshots:
        final_cache_size = result.snapshots[-1].extraction_cache_size
        logger.info(f"Redis cache utilization: {final_cache_size} cached extractions, "
                   f"memory growth: {result.redis_memory_growth_mb:.1f}MB")

@pytest.mark.asyncio
async def test_garbage_collection_effectiveness(resource_monitor):
    """Test garbage collection effectiveness in preventing memory leaks"""
    # Run test with frequent GC
    frequent_gc_result = await resource_monitor.run_memory_stress_test(
        duration_minutes=6,
        concurrent_extractions=8,
        force_gc_interval=20  # Frequent GC
    )
    
    # Run test with infrequent GC
    infrequent_gc_result = await resource_monitor.run_memory_stress_test(
        duration_minutes=6,
        concurrent_extractions=8,
        force_gc_interval=120  # Infrequent GC
    )
    
    # Frequent GC should result in better memory management
    gc_improvement = infrequent_gc_result.peak_memory_mb - frequent_gc_result.peak_memory_mb
    
    logger.info(f"GC effectiveness test: frequent GC peak {frequent_gc_result.peak_memory_mb:.1f}MB, "
               f"infrequent GC peak {infrequent_gc_result.peak_memory_mb:.1f}MB, "
               f"improvement: {gc_improvement:.1f}MB")
    
    # Frequent GC should show better memory characteristics
    assert frequent_gc_result.memory_growth_rate_mb_per_hour <= infrequent_gc_result.memory_growth_rate_mb_per_hour + 20, \
           "Frequent GC should improve memory growth rate"

@pytest.mark.asyncio
async def test_long_running_stability(resource_monitor):
    """Test long-running stability and resource management"""
    result = await resource_monitor.run_memory_stress_test(
        duration_minutes=20,  # Extended test
        concurrent_extractions=6,
        force_gc_interval=90
    )
    
    # Long-running stability assertions
    assert not result.memory_leak_detected, f"Memory leak in long-running test: {result.memory_growth_rate_mb_per_hour:.1f} MB/hour"
    assert result.memory_growth_rate_mb_per_hour < 75, f"Memory growth unsustainable: {result.memory_growth_rate_mb_per_hour:.1f} MB/hour"
    
    # Performance should remain stable over time
    assert abs(result.performance_degradation) < 0.25, f"Performance degraded over time: {result.performance_degradation:.1%}"
    
    # Should maintain reasonable throughput
    throughput = result.successful_extractions / (result.test_duration_seconds / 60)
    assert throughput >= 5, f"Throughput degraded in long test: {throughput:.1f} extractions/min"
    
    logger.info(f"Long-running stability: {result.test_duration_seconds/60:.1f} minutes, "
               f"memory growth: {result.memory_growth_rate_mb_per_hour:.1f} MB/hour, "
               f"throughput: {throughput:.1f}/min")

@pytest.mark.asyncio
async def test_generate_resource_monitoring_report(resource_monitor):
    """Generate comprehensive resource monitoring report"""
    test_configurations = [
        {"concurrent": 3, "duration": 4, "name": "light_load"},
        {"concurrent": 8, "duration": 6, "name": "medium_load"},
        {"concurrent": 12, "duration": 8, "name": "heavy_load"},
        {"concurrent": 15, "duration": 5, "name": "stress_load"}
    ]
    
    monitoring_report = {
        'test_timestamp': datetime.now().isoformat(),
        'system_specifications': {
            'cpu_count': psutil.cpu_count(),
            'memory_total_gb': psutil.virtual_memory().total / (1024**3),
            'platform': psutil.platform.platform(),
        },
        'test_results': []
    }
    
    for config in test_configurations:
        logger.info(f"Running resource monitoring test: {config['name']}")
        
        try:
            result = await resource_monitor.run_memory_stress_test(
                duration_minutes=config['duration'],
                concurrent_extractions=config['concurrent'],
                force_gc_interval=45
            )
            
            # Calculate additional metrics
            success_rate = result.successful_extractions / result.total_extractions if result.total_extractions > 0 else 0
            throughput_per_minute = result.successful_extractions / (result.test_duration_seconds / 60)
            
            monitoring_report['test_results'].append({
                'test_configuration': config,
                'peak_memory_mb': result.peak_memory_mb,
                'avg_memory_mb': result.avg_memory_mb,
                'memory_growth_rate_mb_per_hour': result.memory_growth_rate_mb_per_hour,
                'memory_leak_detected': result.memory_leak_detected,
                'peak_cpu_percent': result.peak_cpu_percent,
                'avg_cpu_percent': result.avg_cpu_percent,
                'peak_threads': result.peak_threads,
                'peak_open_files': result.peak_open_files,
                'total_extractions': result.total_extractions,
                'successful_extractions': result.successful_extractions,
                'success_rate': success_rate,
                'throughput_per_minute': throughput_per_minute,
                'performance_degradation': result.performance_degradation,
                'redis_memory_growth_mb': result.redis_memory_growth_mb,
                'gc_collections_triggered': result.gc_collections_triggered
            })
            
        except Exception as e:
            logger.error(f"Resource monitoring test failed for {config['name']}: {e}")
            monitoring_report['test_results'].append({
                'test_configuration': config,
                'error': str(e),
                'test_failed': True
            })
    
    # Save report
    report_path = f"/tmp/resource_monitoring_report_{int(time.time())}.json"
    with open(report_path, 'w') as f:
        json.dump(monitoring_report, f, indent=2)
    
    logger.info(f"Resource monitoring report saved to: {report_path}")
    
    # Analyze results
    successful_tests = [r for r in monitoring_report['test_results'] if not r.get('test_failed')]
    if successful_tests:
        max_memory = max(r['peak_memory_mb'] for r in successful_tests)
        any_leaks = any(r['memory_leak_detected'] for r in successful_tests)
        
        logger.info(f"📊 Resource monitoring summary:")
        logger.info(f"   Peak memory usage: {max_memory:.1f}MB")
        logger.info(f"   Memory leaks detected: {any_leaks}")
        logger.info(f"   Tests completed successfully: {len(successful_tests)}/{len(test_configurations)}")
    
    return monitoring_report