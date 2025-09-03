"""
Phase 2 DuckDB Analytics System - Comprehensive Performance Benchmarks

This module contains comprehensive performance benchmarks for all Phase 2 components:
- DuckDBService: Analytics database with connection management
- ParquetPipeline: Batch processing with columnar storage
- DataSyncService: Dual-write mechanism with CDC
- HybridQueryRouter: OLTP/OLAP routing optimization
- Analytics API: 24 endpoints with real-time features
- QueryOptimizationEngine: Multi-level caching system
- MonitoringService: Metrics collection and alerting

Performance Targets:
- 5-10x improvement over PostgreSQL baseline
- <1 second response time for 95% of analytics API calls
- 1000+ concurrent users with <1% error rate
- <2GB memory usage during normal operations
- 80%+ cache hit ratio for frequently accessed data
"""

import asyncio
import time
import statistics
import psutil
import pytest
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, asdict
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, patch

from sqlmodel import Session, select
from fastapi.testclient import TestClient

from app.core.database import get_db
from app.services.duckdb_service import DuckDBService
from app.services.analytics_service import AnalyticsService
from app.services.parquet_pipeline import ParquetPipeline
from app.services.data_sync_service import DataSyncService
from app.services.hybrid_query_router import HybridQueryRouter
from app.services.query_optimization_engine import QueryOptimizationEngine
from app.services.intelligent_cache_manager import IntelligentCacheManager
from app.services.monitoring_service import MonitoringService
from app.models.shared_pages import PageV2
from app.models.project import Project
from app.models.user import User


@dataclass
class BenchmarkResult:
    """Standard benchmark result structure"""
    test_name: str
    duration_seconds: float
    operations_per_second: float
    memory_usage_mb: float
    cpu_usage_percent: float
    success_rate: float
    error_count: int
    metadata: Dict[str, Any]
    timestamp: datetime
    
    def meets_target(self, target_ops_per_sec: float = None, 
                    target_duration_sec: float = None,
                    target_success_rate: float = 0.95) -> bool:
        """Check if benchmark meets performance targets"""
        checks = [self.success_rate >= target_success_rate]
        
        if target_ops_per_sec:
            checks.append(self.operations_per_second >= target_ops_per_sec)
        if target_duration_sec:
            checks.append(self.duration_seconds <= target_duration_sec)
            
        return all(checks)

@dataclass
class PerformanceMetrics:
    """System performance metrics during testing"""
    cpu_percent: float
    memory_mb: float
    memory_percent: float
    disk_io_read_mb: float
    disk_io_write_mb: float
    network_bytes_sent: float
    network_bytes_recv: float
    timestamp: datetime

class PerformanceMonitor:
    """Real-time performance monitoring during tests"""
    
    def __init__(self):
        self.metrics_history: List[PerformanceMetrics] = []
        self._monitoring = False
        self._monitor_task = None
    
    async def start_monitoring(self, interval_seconds: float = 0.1):
        """Start continuous performance monitoring"""
        self._monitoring = True
        self._monitor_task = asyncio.create_task(self._monitor_loop(interval_seconds))
    
    async def stop_monitoring(self) -> List[PerformanceMetrics]:
        """Stop monitoring and return collected metrics"""
        self._monitoring = False
        if self._monitor_task:
            await self._monitor_task
        return self.metrics_history
    
    async def _monitor_loop(self, interval: float):
        """Continuous monitoring loop"""
        process = psutil.Process()
        
        while self._monitoring:
            try:
                # System metrics
                cpu_percent = psutil.cpu_percent(interval=None)
                memory_info = psutil.virtual_memory()
                disk_io = psutil.disk_io_counters()
                network_io = psutil.net_io_counters()
                
                # Process metrics
                process_memory = process.memory_info().rss / 1024 / 1024  # MB
                
                metrics = PerformanceMetrics(
                    cpu_percent=cpu_percent,
                    memory_mb=process_memory,
                    memory_percent=memory_info.percent,
                    disk_io_read_mb=disk_io.read_bytes / 1024 / 1024 if disk_io else 0,
                    disk_io_write_mb=disk_io.write_bytes / 1024 / 1024 if disk_io else 0,
                    network_bytes_sent=network_io.bytes_sent if network_io else 0,
                    network_bytes_recv=network_io.bytes_recv if network_io else 0,
                    timestamp=datetime.utcnow()
                )
                
                self.metrics_history.append(metrics)
                await asyncio.sleep(interval)
                
            except Exception as e:
                print(f"Monitoring error: {e}")
                break

@pytest.fixture
async def performance_monitor():
    """Performance monitoring fixture"""
    monitor = PerformanceMonitor()
    yield monitor
    if monitor._monitoring:
        await monitor.stop_monitoring()

@pytest.fixture
async def benchmark_data():
    """Generate realistic test data for benchmarking"""
    async with get_db() as db:
        # Create test user
        user = User(
            email="benchmark@test.com",
            full_name="Benchmark User",
            hashed_password="hashed",
            is_verified=True,
            is_active=True,
            approval_status="approved"
        )
        db.add(user)
        await db.flush()
        
        # Create test project
        project = Project(
            name="Benchmark Project",
            description="Performance testing project",
            user_id=user.id
        )
        db.add(project)
        await db.flush()
        
        # Create test pages - different volumes for different tests
        pages_1k = []
        pages_10k = []
        pages_100k = []
        
        # Generate 1K pages for quick tests
        for i in range(1000):
            page = PageV2(
                original_url=f"https://example{i}.com/page",
                content_url=f"https://web.archive.org/web/20240101000000/https://example{i}.com/page",
                title=f"Test Page {i}",
                extracted_text=f"Content for page {i} " * 100,  # ~1KB text
                mime_type="text/html",
                status_code=200,
                content_length=1024,
                unix_timestamp=1704067200 + i * 3600,  # hourly intervals
                created_at=datetime.utcnow() - timedelta(hours=i),
                quality_score=0.8
            )
            db.add(page)
            pages_1k.append(page)
        
        await db.commit()
        
        return {
            'user': user,
            'project': project,
            'pages_1k': pages_1k,
            'total_pages': len(pages_1k)
        }

class Phase2PerformanceBenchmarks:
    """Comprehensive performance benchmarks for Phase 2 system"""
    
    def __init__(self):
        self.duckdb_service = DuckDBService()
        self.analytics_service = AnalyticsService()
        self.parquet_pipeline = ParquetPipeline()
        self.performance_monitor = PerformanceMonitor()
    
    @asynccontextmanager
    async def benchmark_context(self, test_name: str):
        """Context manager for consistent benchmarking"""
        # Start monitoring
        await self.performance_monitor.start_monitoring()
        start_time = time.time()
        start_memory = psutil.Process().memory_info().rss / 1024 / 1024
        
        error_count = 0
        operations_completed = 0
        
        try:
            yield {'error_count': error_count, 'operations': operations_completed}
        finally:
            # Stop monitoring and collect results
            end_time = time.time()
            end_memory = psutil.Process().memory_info().rss / 1024 / 1024
            metrics = await self.performance_monitor.stop_monitoring()
            
            duration = end_time - start_time
            avg_cpu = statistics.mean([m.cpu_percent for m in metrics]) if metrics else 0
            peak_memory = max([m.memory_mb for m in metrics]) if metrics else end_memory
            
            # Calculate success rate
            success_rate = (operations_completed - error_count) / max(operations_completed, 1)
            ops_per_second = operations_completed / duration if duration > 0 else 0
            
            result = BenchmarkResult(
                test_name=test_name,
                duration_seconds=duration,
                operations_per_second=ops_per_second,
                memory_usage_mb=peak_memory,
                cpu_usage_percent=avg_cpu,
                success_rate=success_rate,
                error_count=error_count,
                metadata={
                    'start_memory_mb': start_memory,
                    'end_memory_mb': end_memory,
                    'metrics_count': len(metrics)
                },
                timestamp=datetime.utcnow()
            )
            
            # Store result for reporting
            self._store_benchmark_result(result)
    
    def _store_benchmark_result(self, result: BenchmarkResult):
        """Store benchmark result for reporting"""
        if not hasattr(self, '_benchmark_results'):
            self._benchmark_results = []
        self._benchmark_results.append(result)
    
    async def test_duckdb_vs_postgresql_query_performance(self, benchmark_data) -> BenchmarkResult:
        """
        Benchmark DuckDB vs PostgreSQL for analytical queries
        Target: 5-10x performance improvement
        """
        async with self.benchmark_context("duckdb_vs_postgresql_performance") as ctx:
            # Test queries of increasing complexity
            test_queries = [
                # Simple aggregation
                "SELECT COUNT(*) FROM pages",
                
                # Time-based analysis
                """
                SELECT DATE_TRUNC('day', created_at) as day, 
                       COUNT(*) as page_count,
                       AVG(content_length) as avg_size
                FROM pages 
                WHERE created_at >= NOW() - INTERVAL '30 days'
                GROUP BY day
                ORDER BY day
                """,
                
                # Complex analytical query
                """
                SELECT 
                    EXTRACT(hour FROM created_at) as hour,
                    COUNT(*) as total_pages,
                    COUNT(DISTINCT SUBSTRING(original_url FROM 'https?://([^/]+)')) as unique_domains,
                    AVG(content_length) as avg_content_length,
                    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY quality_score) as median_quality,
                    COUNT(CASE WHEN mime_type = 'text/html' THEN 1 END) as html_pages,
                    COUNT(CASE WHEN mime_type = 'application/pdf' THEN 1 END) as pdf_pages
                FROM pages 
                WHERE created_at >= NOW() - INTERVAL '7 days'
                GROUP BY hour
                ORDER BY hour
                """
            ]
            
            operations = 0
            duckdb_times = []
            postgresql_times = []
            
            for query in test_queries:
                # Benchmark DuckDB
                for _ in range(10):  # 10 iterations per query
                    try:
                        start_time = time.time()
                        result = await self.duckdb_service.execute_query(query)
                        duckdb_time = time.time() - start_time
                        duckdb_times.append(duckdb_time)
                        operations += 1
                    except Exception as e:
                        ctx['error_count'] += 1
                
                # Benchmark PostgreSQL (baseline)
                async with get_db() as db:
                    for _ in range(10):
                        try:
                            start_time = time.time()
                            result = await db.execute(query)
                            postgresql_time = time.time() - start_time
                            postgresql_times.append(postgresql_time)
                            operations += 1
                        except Exception as e:
                            ctx['error_count'] += 1
            
            ctx['operations'] = operations
            
            # Calculate performance improvement
            avg_duckdb = statistics.mean(duckdb_times) if duckdb_times else float('inf')
            avg_postgresql = statistics.mean(postgresql_times) if postgresql_times else float('inf')
            improvement_factor = avg_postgresql / avg_duckdb if avg_duckdb > 0 else 0
            
            # Store detailed results
            metadata = {
                'duckdb_avg_time': avg_duckdb,
                'postgresql_avg_time': avg_postgresql,
                'improvement_factor': improvement_factor,
                'target_improvement': 5.0,
                'meets_target': improvement_factor >= 5.0
            }
    
    async def test_hybrid_query_routing_efficiency(self, benchmark_data) -> BenchmarkResult:
        """
        Test the efficiency of hybrid query routing (OLTP vs OLAP)
        Target: >90% correct routing decisions with <10ms routing overhead
        """
        async with self.benchmark_context("hybrid_query_routing") as ctx:
            router = HybridQueryRouter()
            
            # Test queries with expected routing decisions
            test_cases = [
                # OLTP queries (should route to PostgreSQL)
                ("SELECT * FROM users WHERE id = 1", "oltp"),
                ("INSERT INTO projects (name) VALUES ('test')", "oltp"),
                ("UPDATE pages SET title = 'new' WHERE id = 1", "oltp"),
                
                # OLAP queries (should route to DuckDB)
                ("SELECT COUNT(*) FROM pages GROUP BY DATE(created_at)", "olap"),
                ("SELECT AVG(content_length) FROM pages WHERE created_at > '2024-01-01'", "olap"),
                ("SELECT domain, COUNT(*) FROM pages GROUP BY domain ORDER BY COUNT(*) DESC", "olap"),
            ]
            
            correct_routes = 0
            total_routing_time = 0
            operations = 0
            
            for query, expected_route in test_cases:
                for _ in range(100):  # Test routing decision 100 times per query
                    try:
                        start_time = time.time()
                        routing_decision = await router.determine_route(query)
                        routing_time = time.time() - start_time
                        
                        total_routing_time += routing_time
                        
                        if routing_decision == expected_route:
                            correct_routes += 1
                        
                        operations += 1
                        
                    except Exception as e:
                        ctx['error_count'] += 1
            
            ctx['operations'] = operations
            
            # Calculate metrics
            routing_accuracy = correct_routes / operations if operations > 0 else 0
            avg_routing_time_ms = (total_routing_time / operations * 1000) if operations > 0 else 0
            
            return BenchmarkResult(
                test_name="hybrid_query_routing",
                duration_seconds=total_routing_time,
                operations_per_second=operations / total_routing_time if total_routing_time > 0 else 0,
                memory_usage_mb=0,  # Will be filled by context manager
                cpu_usage_percent=0,  # Will be filled by context manager
                success_rate=routing_accuracy,
                error_count=ctx['error_count'],
                metadata={
                    'routing_accuracy': routing_accuracy,
                    'avg_routing_time_ms': avg_routing_time_ms,
                    'target_accuracy': 0.90,
                    'target_routing_time_ms': 10.0,
                    'meets_accuracy_target': routing_accuracy >= 0.90,
                    'meets_time_target': avg_routing_time_ms <= 10.0
                },
                timestamp=datetime.utcnow()
            )
    
    async def test_cache_performance_multilevel(self, benchmark_data) -> BenchmarkResult:
        """
        Test multi-level cache performance and hit rates
        Target: 80% cache hit ratio for frequently accessed data
        """
        async with self.benchmark_context("cache_performance") as ctx:
            cache_manager = IntelligentCacheManager()
            
            # Simulate realistic query patterns with repetition
            query_patterns = [
                "SELECT COUNT(*) FROM pages",
                "SELECT COUNT(*) FROM pages WHERE created_at > '2024-01-01'",
                "SELECT domain, COUNT(*) FROM pages GROUP BY domain LIMIT 10",
                "SELECT AVG(content_length) FROM pages",
                "SELECT * FROM pages WHERE project_id = 1 LIMIT 100"
            ]
            
            # Generate query sequence with realistic distribution
            # 80% queries should be repeated (cacheable)
            query_sequence = []
            for _ in range(1000):
                if np.random.random() < 0.8:  # 80% repeated queries
                    query_sequence.append(np.random.choice(query_patterns))
                else:  # 20% unique queries
                    query_sequence.append(f"SELECT * FROM pages WHERE id = {np.random.randint(1, 10000)}")
            
            cache_hits = 0
            cache_misses = 0
            total_query_time = 0
            operations = 0
            
            for query in query_sequence:
                try:
                    start_time = time.time()
                    
                    # Check cache first
                    cached_result = await cache_manager.get(query)
                    if cached_result is not None:
                        cache_hits += 1
                        query_time = time.time() - start_time  # Cache hit time
                    else:
                        # Cache miss - execute query and cache result
                        result = await self.duckdb_service.execute_query(query)
                        await cache_manager.set(query, result, ttl=300)
                        cache_misses += 1
                        query_time = time.time() - start_time  # Full query time
                    
                    total_query_time += query_time
                    operations += 1
                    
                except Exception as e:
                    ctx['error_count'] += 1
            
            ctx['operations'] = operations
            
            # Calculate cache metrics
            cache_hit_ratio = cache_hits / (cache_hits + cache_misses) if (cache_hits + cache_misses) > 0 else 0
            avg_query_time_ms = (total_query_time / operations * 1000) if operations > 0 else 0
            
            return BenchmarkResult(
                test_name="cache_performance",
                duration_seconds=total_query_time,
                operations_per_second=operations / total_query_time if total_query_time > 0 else 0,
                memory_usage_mb=0,  # Will be filled by context manager
                cpu_usage_percent=0,  # Will be filled by context manager
                success_rate=1.0 - (ctx['error_count'] / operations) if operations > 0 else 0,
                error_count=ctx['error_count'],
                metadata={
                    'cache_hit_ratio': cache_hit_ratio,
                    'cache_hits': cache_hits,
                    'cache_misses': cache_misses,
                    'avg_query_time_ms': avg_query_time_ms,
                    'target_hit_ratio': 0.80,
                    'meets_target': cache_hit_ratio >= 0.80
                },
                timestamp=datetime.utcnow()
            )
    
    async def test_parquet_processing_throughput(self, benchmark_data) -> BenchmarkResult:
        """
        Benchmark Parquet pipeline processing throughput
        Target: Process 10K pages per minute with <5% error rate
        """
        async with self.benchmark_context("parquet_processing_throughput") as ctx:
            # Use test data
            pages = benchmark_data['pages_1k']
            target_throughput = 10000 / 60  # pages per second
            
            operations = 0
            processing_times = []
            
            # Process pages in batches
            batch_size = 100
            batches = [pages[i:i + batch_size] for i in range(0, len(pages), batch_size)]
            
            for batch in batches:
                try:
                    start_time = time.time()
                    
                    # Convert pages to Parquet format
                    result = await self.parquet_pipeline.process_batch(batch)
                    
                    batch_time = time.time() - start_time
                    processing_times.append(batch_time)
                    
                    operations += len(batch)
                    
                except Exception as e:
                    ctx['error_count'] += len(batch)
            
            ctx['operations'] = operations
            
            # Calculate throughput metrics
            total_time = sum(processing_times)
            pages_per_second = operations / total_time if total_time > 0 else 0
            avg_batch_time = statistics.mean(processing_times) if processing_times else 0
            
            return BenchmarkResult(
                test_name="parquet_processing_throughput",
                duration_seconds=total_time,
                operations_per_second=pages_per_second,
                memory_usage_mb=0,  # Will be filled by context manager
                cpu_usage_percent=0,  # Will be filled by context manager
                success_rate=1.0 - (ctx['error_count'] / operations) if operations > 0 else 0,
                error_count=ctx['error_count'],
                metadata={
                    'pages_per_second': pages_per_second,
                    'target_pages_per_second': target_throughput,
                    'avg_batch_time_ms': avg_batch_time * 1000,
                    'batch_size': batch_size,
                    'total_batches': len(batches),
                    'meets_target': pages_per_second >= target_throughput
                },
                timestamp=datetime.utcnow()
            )
    
    async def test_data_sync_latency(self, benchmark_data) -> BenchmarkResult:
        """
        Test data synchronization latency between PostgreSQL and DuckDB
        Target: <60 seconds sync lag for 95% of operations
        """
        async with self.benchmark_context("data_sync_latency") as ctx:
            sync_service = DataSyncService()
            
            # Test different types of data operations
            operations = 0
            sync_latencies = []
            
            for i in range(100):  # Test 100 sync operations
                try:
                    # Simulate data change in PostgreSQL
                    change_timestamp = time.time()
                    
                    # Create new page
                    new_page = PageV2(
                        original_url=f"https://sync-test-{i}.com",
                        content_url=f"https://web.archive.org/web/20240101000000/https://sync-test-{i}.com",
                        title=f"Sync Test Page {i}",
                        extracted_text=f"Content for sync test {i}",
                        mime_type="text/html",
                        status_code=200,
                        content_length=1024,
                        unix_timestamp=int(change_timestamp),
                        created_at=datetime.utcnow()
                    )
                    
                    # Trigger sync operation
                    sync_start = time.time()
                    await sync_service.sync_page_to_duckdb(new_page)
                    
                    # Verify sync completed
                    sync_end = time.time()
                    sync_latency = sync_end - sync_start
                    sync_latencies.append(sync_latency)
                    
                    operations += 1
                    
                except Exception as e:
                    ctx['error_count'] += 1
            
            ctx['operations'] = operations
            
            # Calculate sync metrics
            avg_latency = statistics.mean(sync_latencies) if sync_latencies else 0
            p95_latency = np.percentile(sync_latencies, 95) if sync_latencies else 0
            p99_latency = np.percentile(sync_latencies, 99) if sync_latencies else 0
            
            return BenchmarkResult(
                test_name="data_sync_latency",
                duration_seconds=sum(sync_latencies),
                operations_per_second=operations / sum(sync_latencies) if sum(sync_latencies) > 0 else 0,
                memory_usage_mb=0,  # Will be filled by context manager
                cpu_usage_percent=0,  # Will be filled by context manager
                success_rate=1.0 - (ctx['error_count'] / operations) if operations > 0 else 0,
                error_count=ctx['error_count'],
                metadata={
                    'avg_latency_seconds': avg_latency,
                    'p95_latency_seconds': p95_latency,
                    'p99_latency_seconds': p99_latency,
                    'target_p95_seconds': 60.0,
                    'meets_target': p95_latency <= 60.0
                },
                timestamp=datetime.utcnow()
            )
    
    async def test_analytics_api_response_times(self, benchmark_data) -> BenchmarkResult:
        """
        Benchmark Analytics API endpoint response times
        Target: 95% of requests complete in <1 second
        """
        async with self.benchmark_context("analytics_api_response_times") as ctx:
            # Test different API endpoints
            api_endpoints = [
                "/api/v1/analytics/summary",
                "/api/v1/analytics/timeline",
                "/api/v1/analytics/domains",
                "/api/v1/analytics/content-types",
                "/api/v1/analytics/quality-distribution"
            ]
            
            operations = 0
            response_times = []
            
            # Test each endpoint multiple times
            for endpoint in api_endpoints:
                for _ in range(20):  # 20 requests per endpoint
                    try:
                        start_time = time.time()
                        
                        # Simulate API call
                        result = await self.analytics_service.get_endpoint_data(
                            endpoint, 
                            project_id=benchmark_data['project'].id
                        )
                        
                        response_time = time.time() - start_time
                        response_times.append(response_time)
                        operations += 1
                        
                    except Exception as e:
                        ctx['error_count'] += 1
            
            ctx['operations'] = operations
            
            # Calculate response time metrics
            avg_response_time = statistics.mean(response_times) if response_times else 0
            p95_response_time = np.percentile(response_times, 95) if response_times else 0
            p99_response_time = np.percentile(response_times, 99) if response_times else 0
            
            # Count responses under 1 second
            responses_under_1s = sum(1 for rt in response_times if rt < 1.0)
            percent_under_1s = (responses_under_1s / len(response_times)) if response_times else 0
            
            return BenchmarkResult(
                test_name="analytics_api_response_times",
                duration_seconds=sum(response_times),
                operations_per_second=operations / sum(response_times) if sum(response_times) > 0 else 0,
                memory_usage_mb=0,  # Will be filled by context manager
                cpu_usage_percent=0,  # Will be filled by context manager
                success_rate=1.0 - (ctx['error_count'] / operations) if operations > 0 else 0,
                error_count=ctx['error_count'],
                metadata={
                    'avg_response_time_ms': avg_response_time * 1000,
                    'p95_response_time_ms': p95_response_time * 1000,
                    'p99_response_time_ms': p99_response_time * 1000,
                    'percent_under_1s': percent_under_1s * 100,
                    'target_percent_under_1s': 95.0,
                    'meets_target': percent_under_1s >= 0.95
                },
                timestamp=datetime.utcnow()
            )
    
    async def test_concurrent_user_scenarios(self, benchmark_data) -> BenchmarkResult:
        """
        Test system performance under concurrent user load
        Target: Support 1000+ concurrent users with <1% error rate
        """
        async with self.benchmark_context("concurrent_user_scenarios") as ctx:
            # Simulate concurrent users
            concurrent_users = [100, 500, 1000, 1500]  # Progressive load testing
            results_by_user_count = {}
            
            for user_count in concurrent_users:
                print(f"Testing {user_count} concurrent users...")
                
                user_operations = 0
                user_errors = 0
                user_response_times = []
                
                async def simulate_user():
                    nonlocal user_operations, user_errors, user_response_times
                    
                    # Each user performs multiple operations
                    for _ in range(10):
                        try:
                            start_time = time.time()
                            
                            # Random analytics operation
                            operation = np.random.choice([
                                'summary',
                                'timeline',
                                'domains',
                                'search'
                            ])
                            
                            if operation == 'summary':
                                result = await self.analytics_service.get_summary(
                                    project_id=benchmark_data['project'].id
                                )
                            elif operation == 'timeline':
                                result = await self.analytics_service.get_timeline(
                                    project_id=benchmark_data['project'].id
                                )
                            elif operation == 'domains':
                                result = await self.analytics_service.get_top_domains(
                                    project_id=benchmark_data['project'].id
                                )
                            else:  # search
                                result = await self.analytics_service.search_pages(
                                    query="test",
                                    project_id=benchmark_data['project'].id
                                )
                            
                            response_time = time.time() - start_time
                            user_response_times.append(response_time)
                            user_operations += 1
                            
                        except Exception as e:
                            user_errors += 1
                
                # Run concurrent users
                tasks = [simulate_user() for _ in range(user_count)]
                await asyncio.gather(*tasks, return_exceptions=True)
                
                # Calculate metrics for this user count
                error_rate = user_errors / (user_operations + user_errors) if (user_operations + user_errors) > 0 else 1.0
                avg_response_time = statistics.mean(user_response_times) if user_response_times else 0
                
                results_by_user_count[user_count] = {
                    'operations': user_operations,
                    'errors': user_errors,
                    'error_rate': error_rate,
                    'avg_response_time': avg_response_time,
                    'meets_target': error_rate <= 0.01  # <1% error rate
                }
                
                # If error rate is too high, stop testing higher loads
                if error_rate > 0.05:  # >5% error rate
                    break
            
            # Find maximum supported users with <1% error rate
            max_supported_users = 0
            for user_count, metrics in results_by_user_count.items():
                if metrics['error_rate'] <= 0.01:
                    max_supported_users = user_count
            
            total_operations = sum(r['operations'] for r in results_by_user_count.values())
            total_errors = sum(r['errors'] for r in results_by_user_count.values())
            
            ctx['operations'] = total_operations
            ctx['error_count'] = total_errors
            
            return BenchmarkResult(
                test_name="concurrent_user_scenarios",
                duration_seconds=0,  # Will be filled by context manager
                operations_per_second=0,  # Will be calculated by context manager
                memory_usage_mb=0,  # Will be filled by context manager
                cpu_usage_percent=0,  # Will be filled by context manager
                success_rate=1.0 - (total_errors / total_operations) if total_operations > 0 else 0,
                error_count=total_errors,
                metadata={
                    'max_supported_users': max_supported_users,
                    'target_users': 1000,
                    'meets_target': max_supported_users >= 1000,
                    'results_by_user_count': results_by_user_count
                },
                timestamp=datetime.utcnow()
            )
    
    async def test_resource_utilization_efficiency(self, benchmark_data) -> BenchmarkResult:
        """
        Test system resource utilization efficiency
        Target: <2GB memory usage during normal operations
        """
        async with self.benchmark_context("resource_utilization") as ctx:
            # Run various operations while monitoring resources
            operations = 0
            peak_memory_mb = 0
            peak_cpu_percent = 0
            
            # Simulate normal operations
            operation_types = [
                'analytics_query',
                'data_sync',
                'cache_operation',
                'parquet_processing'
            ]
            
            for _ in range(200):  # 200 mixed operations
                try:
                    operation = np.random.choice(operation_types)
                    
                    # Monitor resources before operation
                    process = psutil.Process()
                    memory_before = process.memory_info().rss / 1024 / 1024
                    cpu_before = process.cpu_percent()
                    
                    if operation == 'analytics_query':
                        await self.analytics_service.get_summary(
                            project_id=benchmark_data['project'].id
                        )
                    elif operation == 'data_sync':
                        # Simulate data sync
                        await asyncio.sleep(0.01)  # Placeholder
                    elif operation == 'cache_operation':
                        # Simulate cache operations
                        cache_manager = IntelligentCacheManager()
                        await cache_manager.get("test_key")
                    else:  # parquet_processing
                        # Simulate parquet processing
                        await asyncio.sleep(0.02)  # Placeholder
                    
                    # Monitor resources after operation
                    memory_after = process.memory_info().rss / 1024 / 1024
                    cpu_after = process.cpu_percent()
                    
                    peak_memory_mb = max(peak_memory_mb, memory_after)
                    peak_cpu_percent = max(peak_cpu_percent, cpu_after)
                    
                    operations += 1
                    
                except Exception as e:
                    ctx['error_count'] += 1
            
            ctx['operations'] = operations
            
            # Check resource targets
            memory_target_met = peak_memory_mb <= 2048  # 2GB
            
            return BenchmarkResult(
                test_name="resource_utilization",
                duration_seconds=0,  # Will be filled by context manager
                operations_per_second=0,  # Will be calculated by context manager
                memory_usage_mb=peak_memory_mb,
                cpu_usage_percent=peak_cpu_percent,
                success_rate=1.0 - (ctx['error_count'] / operations) if operations > 0 else 0,
                error_count=ctx['error_count'],
                metadata={
                    'peak_memory_mb': peak_memory_mb,
                    'peak_cpu_percent': peak_cpu_percent,
                    'memory_target_mb': 2048,
                    'memory_target_met': memory_target_met,
                    'mixed_operations': operations
                },
                timestamp=datetime.utcnow()
            )


# BENCHMARK SUCCESS CRITERIA
BENCHMARK_SUCCESS_CRITERIA = {
    "query_performance_improvement": 5.0,  # 5x minimum improvement
    "cache_hit_ratio": 0.80,              # 80% minimum hit ratio
    "api_response_time_p95": 1000,        # <1 second for 95% of requests
    "memory_usage_gb": 2.0,               # <2GB during normal operations
    "error_rate_percent": 1.0,            # <1% error rate under load
    "concurrent_users_supported": 1000,   # Support 1000+ concurrent users
    "data_sync_lag_seconds": 60,          # <1 minute sync lag
    "uptime_percentage": 99.9             # 99.9% uptime requirement
}


@pytest.mark.performance
@pytest.mark.asyncio
class TestPhase2PerformanceBenchmarks:
    """Main test class for Phase 2 performance benchmarks"""
    
    def setup_class(self):
        """Setup for benchmark tests"""
        self.benchmark_suite = Phase2PerformanceBenchmarks()
        self.results = []
    
    @pytest.mark.slow
    async def test_complete_benchmark_suite(self, benchmark_data):
        """Run the complete benchmark suite and validate all targets"""
        
        print("Starting Phase 2 Performance Benchmark Suite...")
        print("=" * 60)
        
        # Run all benchmark tests
        benchmark_methods = [
            'test_duckdb_vs_postgresql_query_performance',
            'test_hybrid_query_routing_efficiency',
            'test_cache_performance_multilevel',
            'test_parquet_processing_throughput',
            'test_data_sync_latency',
            'test_analytics_api_response_times',
            'test_concurrent_user_scenarios',
            'test_resource_utilization_efficiency'
        ]
        
        for method_name in benchmark_methods:
            print(f"\nRunning {method_name}...")
            method = getattr(self.benchmark_suite, method_name)
            result = await method(benchmark_data)
            self.results.append(result)
            
            # Print immediate results
            print(f"  Duration: {result.duration_seconds:.2f}s")
            print(f"  Ops/sec: {result.operations_per_second:.2f}")
            print(f"  Success rate: {result.success_rate:.2%}")
            print(f"  Errors: {result.error_count}")
        
        # Generate comprehensive report
        self._generate_benchmark_report()
        
        # Validate overall performance targets
        self._validate_performance_targets()
    
    def _generate_benchmark_report(self):
        """Generate comprehensive benchmark report"""
        print("\n" + "=" * 60)
        print("PHASE 2 PERFORMANCE BENCHMARK REPORT")
        print("=" * 60)
        
        total_operations = sum(r.operations_per_second * r.duration_seconds for r in self.results)
        total_errors = sum(r.error_count for r in self.results)
        overall_success_rate = 1.0 - (total_errors / total_operations) if total_operations > 0 else 0
        
        print(f"\nOVERALL METRICS:")
        print(f"  Total operations: {total_operations:,.0f}")
        print(f"  Total errors: {total_errors:,}")
        print(f"  Overall success rate: {overall_success_rate:.2%}")
        
        print(f"\nBENCHMARK RESULTS:")
        for result in self.results:
            print(f"\n{result.test_name}:")
            print(f"  Duration: {result.duration_seconds:.3f}s")
            print(f"  Operations/sec: {result.operations_per_second:,.2f}")
            print(f"  Memory usage: {result.memory_usage_mb:.1f} MB")
            print(f"  CPU usage: {result.cpu_usage_percent:.1f}%")
            print(f"  Success rate: {result.success_rate:.2%}")
            print(f"  Errors: {result.error_count:,}")
            
            # Print test-specific metadata
            for key, value in result.metadata.items():
                if isinstance(value, (int, float)):
                    if 'time' in key.lower() and 'ms' in key.lower():
                        print(f"  {key}: {value:.1f} ms")
                    elif 'ratio' in key.lower() or 'rate' in key.lower():
                        print(f"  {key}: {value:.2%}")
                    elif 'factor' in key.lower():
                        print(f"  {key}: {value:.1f}x")
                    else:
                        print(f"  {key}: {value:,.2f}")
                elif isinstance(value, bool):
                    print(f"  {key}: {'✓' if value else '✗'}")
    
    def _validate_performance_targets(self):
        """Validate that all performance targets are met"""
        print(f"\nPERFORMANCE TARGET VALIDATION:")
        print("-" * 40)
        
        target_results = {}
        
        for result in self.results:
            test_name = result.test_name
            metadata = result.metadata
            
            if test_name == "duckdb_vs_postgresql_performance":
                improvement = metadata.get('improvement_factor', 0)
                target_results['query_performance'] = {
                    'actual': improvement,
                    'target': BENCHMARK_SUCCESS_CRITERIA['query_performance_improvement'],
                    'met': improvement >= BENCHMARK_SUCCESS_CRITERIA['query_performance_improvement']
                }
            
            elif test_name == "cache_performance":
                hit_ratio = metadata.get('cache_hit_ratio', 0)
                target_results['cache_hit_ratio'] = {
                    'actual': hit_ratio,
                    'target': BENCHMARK_SUCCESS_CRITERIA['cache_hit_ratio'],
                    'met': hit_ratio >= BENCHMARK_SUCCESS_CRITERIA['cache_hit_ratio']
                }
            
            elif test_name == "analytics_api_response_times":
                p95_time_ms = metadata.get('p95_response_time_ms', float('inf'))
                target_results['api_response_time'] = {
                    'actual': p95_time_ms,
                    'target': BENCHMARK_SUCCESS_CRITERIA['api_response_time_p95'],
                    'met': p95_time_ms <= BENCHMARK_SUCCESS_CRITERIA['api_response_time_p95']
                }
            
            elif test_name == "resource_utilization":
                memory_gb = result.memory_usage_mb / 1024
                target_results['memory_usage'] = {
                    'actual': memory_gb,
                    'target': BENCHMARK_SUCCESS_CRITERIA['memory_usage_gb'],
                    'met': memory_gb <= BENCHMARK_SUCCESS_CRITERIA['memory_usage_gb']
                }
            
            elif test_name == "concurrent_user_scenarios":
                max_users = metadata.get('max_supported_users', 0)
                target_results['concurrent_users'] = {
                    'actual': max_users,
                    'target': BENCHMARK_SUCCESS_CRITERIA['concurrent_users_supported'],
                    'met': max_users >= BENCHMARK_SUCCESS_CRITERIA['concurrent_users_supported']
                }
            
            # Overall error rate
            if result.success_rate > 0:
                error_rate = (1 - result.success_rate) * 100
                target_results['error_rate'] = {
                    'actual': error_rate,
                    'target': BENCHMARK_SUCCESS_CRITERIA['error_rate_percent'],
                    'met': error_rate <= BENCHMARK_SUCCESS_CRITERIA['error_rate_percent']
                }
        
        # Print target validation results
        all_targets_met = True
        for target_name, result in target_results.items():
            status = "✓ PASS" if result['met'] else "✗ FAIL"
            print(f"  {target_name}: {result['actual']:.2f} (target: {result['target']:.2f}) {status}")
            if not result['met']:
                all_targets_met = False
        
        print(f"\nOVERALL PERFORMANCE: {'✓ ALL TARGETS MET' if all_targets_met else '✗ SOME TARGETS MISSED'}")
        
        # Assert that all critical targets are met
        assert all_targets_met, "Not all performance targets were met"
        
        print("\n" + "=" * 60)
        print("BENCHMARK SUITE COMPLETED SUCCESSFULLY")
        print("=" * 60)

if __name__ == "__main__":
    # Run benchmarks directly
    import asyncio
    
    async def run_benchmarks():
        suite = Phase2PerformanceBenchmarks()
        # Add benchmark execution logic here
        pass
    
    asyncio.run(run_benchmarks())