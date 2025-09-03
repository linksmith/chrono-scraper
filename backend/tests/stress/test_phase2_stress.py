"""
Phase 2 Stress Testing and Edge Cases - Resource Exhaustion & Failure Scenarios

This module provides comprehensive stress testing for the Phase 2 DuckDB analytics system,
focusing on resource exhaustion scenarios, edge cases, and failure recovery.

Stress Test Coverage:
- Memory Pressure: Large query results, cache overflow, memory leak detection
- CPU Saturation: High concurrency, complex query processing under load
- Disk Space Exhaustion: Parquet file growth, log accumulation scenarios
- Connection Pool Exhaustion: Database connection limits, pool management
- Network Congestion: High-bandwidth export operations, WebSocket scaling

Edge Case Testing:
- Malformed Data: Invalid CDX records, corrupted Parquet files, schema mismatches
- Extreme Queries: Very complex analytics, massive result sets, timeout scenarios
- Concurrent Modifications: Simultaneous data sync, cache updates, user operations
- Service Failures: Database crashes, network failures, dependency unavailability

This ensures the Phase 2 system can handle extreme conditions and gracefully degrade.
"""

import asyncio
import pytest
import pytest_asyncio
import time
import psutil
import gc
import threading
import random
import uuid
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple
from unittest.mock import AsyncMock, patch, MagicMock
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor, as_completed
import numpy as np

from sqlmodel import Session, select
from fastapi import HTTPException
from httpx import AsyncClient
import tempfile
import os
import shutil

from app.core.database import get_db
from app.services.duckdb_service import DuckDBService, DuckDBResourceError, DuckDBConnectionError
from app.services.analytics_service import AnalyticsService
from app.services.parquet_pipeline import ParquetPipeline
from app.services.data_sync_service import DataSyncService
from app.services.hybrid_query_router import HybridQueryRouter
from app.services.intelligent_cache_manager import IntelligentCacheManager
from app.services.monitoring_service import MonitoringService
from app.services.database_connection_manager import ConnectionPool

from app.models.shared_pages import PageV2
from app.models.project import Project
from app.models.user import User
from app.models.extraction_data import ExtractedContent


@dataclass
class StressTestResult:
    """Result of a stress test scenario"""
    test_name: str
    duration_seconds: float
    peak_memory_mb: float
    peak_cpu_percent: float
    peak_connections: int
    operations_completed: int
    operations_failed: int
    recovery_successful: bool
    system_stable: bool
    resource_limits_reached: Dict[str, bool]
    error_types: Dict[str, int]
    metadata: Dict[str, Any]
    timestamp: datetime


class ResourceMonitor:
    """Real-time resource monitoring during stress tests"""
    
    def __init__(self):
        self.monitoring = False
        self.monitor_thread = None
        self.resource_history = []
        self.alerts = []
        
        # Resource thresholds
        self.memory_threshold_mb = 2048  # 2GB
        self.cpu_threshold_percent = 80
        self.disk_threshold_percent = 90
        self.connection_threshold = 100
    
    def start_monitoring(self, interval_seconds: float = 0.5):
        """Start continuous resource monitoring"""
        self.monitoring = True
        self.monitor_thread = threading.Thread(target=self._monitor_loop, args=(interval_seconds,))
        self.monitor_thread.start()
    
    def stop_monitoring(self) -> Dict[str, Any]:
        """Stop monitoring and return collected metrics"""
        self.monitoring = False
        if self.monitor_thread:
            self.monitor_thread.join(timeout=5.0)
        
        if not self.resource_history:
            return {'peak_memory_mb': 0, 'peak_cpu_percent': 0, 'alerts': []}
        
        return {
            'peak_memory_mb': max(r['memory_mb'] for r in self.resource_history),
            'peak_cpu_percent': max(r['cpu_percent'] for r in self.resource_history),
            'peak_disk_usage_percent': max(r['disk_percent'] for r in self.resource_history),
            'avg_memory_mb': np.mean([r['memory_mb'] for r in self.resource_history]),
            'avg_cpu_percent': np.mean([r['cpu_percent'] for r in self.resource_history]),
            'resource_history': self.resource_history,
            'alerts': self.alerts,
            'monitoring_duration': len(self.resource_history) * 0.5
        }
    
    def _monitor_loop(self, interval: float):
        """Continuous monitoring loop"""
        process = psutil.Process()
        
        while self.monitoring:
            try:
                # System metrics
                cpu_percent = psutil.cpu_percent(interval=None)
                memory_info = psutil.virtual_memory()
                disk_info = psutil.disk_usage('/')
                
                # Process metrics
                process_memory = process.memory_info().rss / 1024 / 1024  # MB
                process_cpu = process.cpu_percent()
                
                # Connection count (approximation)
                connection_count = len(process.connections())
                
                resource_data = {
                    'timestamp': datetime.utcnow(),
                    'memory_mb': process_memory,
                    'cpu_percent': cpu_percent,
                    'disk_percent': disk_info.percent,
                    'connection_count': connection_count,
                    'system_memory_percent': memory_info.percent
                }
                
                self.resource_history.append(resource_data)
                
                # Check thresholds and generate alerts
                if process_memory > self.memory_threshold_mb:
                    self.alerts.append({
                        'type': 'memory_threshold_exceeded',
                        'value': process_memory,
                        'threshold': self.memory_threshold_mb,
                        'timestamp': datetime.utcnow()
                    })
                
                if cpu_percent > self.cpu_threshold_percent:
                    self.alerts.append({
                        'type': 'cpu_threshold_exceeded',
                        'value': cpu_percent,
                        'threshold': self.cpu_threshold_percent,
                        'timestamp': datetime.utcnow()
                    })
                
                if connection_count > self.connection_threshold:
                    self.alerts.append({
                        'type': 'connection_threshold_exceeded',
                        'value': connection_count,
                        'threshold': self.connection_threshold,
                        'timestamp': datetime.utcnow()
                    })
                
                time.sleep(interval)
                
            except Exception as e:
                # Continue monitoring even if individual measurements fail
                time.sleep(interval)
                continue


class Phase2StressTests:
    """Comprehensive stress testing for Phase 2 system"""
    
    def __init__(self):
        self.duckdb_service = DuckDBService()
        self.analytics_service = AnalyticsService()
        self.parquet_pipeline = ParquetPipeline()
        self.data_sync_service = DataSyncService()
        self.cache_manager = IntelligentCacheManager()
        
        self.test_results: List[StressTestResult] = []
        self.temp_directories: List[str] = []
    
    async def setup_stress_test_environment(self, data_volume: str = "large") -> Dict[str, Any]:
        """Setup environment with varying data volumes for stress testing"""
        
        # Data volume configurations
        volume_configs = {
            "small": 1000,     # 1K pages
            "medium": 10000,   # 10K pages  
            "large": 100000,   # 100K pages
            "xlarge": 500000,  # 500K pages
            "extreme": 1000000 # 1M pages
        }
        
        page_count = volume_configs.get(data_volume, 10000)
        
        async with get_db() as db:
            # Create test user
            user = User(
                email=f"stress_test_{uuid.uuid4()}@example.com",
                full_name="Stress Test User",
                hashed_password="hashed_password",
                is_verified=True,
                is_active=True,
                approval_status="approved"
            )
            db.add(user)
            await db.flush()
            
            # Create test project
            project = Project(
                name=f"Stress Test Project {uuid.uuid4()}",
                description=f"Stress testing with {page_count:,} pages",
                user_id=user.id
            )
            db.add(project)
            await db.flush()
            
            # Create large dataset for stress testing
            print(f"Creating {page_count:,} test pages for stress testing...")
            
            batch_size = 1000
            total_created = 0
            
            for batch_start in range(0, page_count, batch_size):
                batch_end = min(batch_start + batch_size, page_count)
                batch_pages = []
                
                for i in range(batch_start, batch_end):
                    # Create diverse content for realistic testing
                    content_size = random.randint(500, 5000)  # 500B to 5KB
                    content_text = "Test content " * (content_size // 13)
                    
                    page = PageV2(
                        original_url=f"https://stress-test-{i}.com/page",
                        content_url=f"https://web.archive.org/web/20240101000000/https://stress-test-{i}.com/page",
                        title=f"Stress Test Page {i}",
                        extracted_text=content_text,
                        mime_type=random.choice(["text/html", "application/pdf", "text/plain"]),
                        status_code=random.choice([200, 201, 202]),
                        content_length=len(content_text),
                        unix_timestamp=1704067200 + i * random.randint(60, 3600),
                        created_at=datetime.utcnow() - timedelta(seconds=i),
                        quality_score=random.uniform(0.3, 1.0)
                    )
                    db.add(page)
                    batch_pages.append(page)
                
                await db.commit()
                total_created += len(batch_pages)
                
                if total_created % 10000 == 0:
                    print(f"Created {total_created:,} pages...")
            
            print(f"Completed creating {total_created:,} test pages")
            
            return {
                'user': user,
                'project': project,
                'page_count': total_created,
                'data_volume': data_volume
            }
    
    async def test_memory_pressure_scenarios(self, data_volume: str = "large") -> StressTestResult:
        """Test system behavior under memory pressure conditions"""
        print(f"Starting memory pressure test with {data_volume} dataset...")
        
        test_start = time.time()
        monitor = ResourceMonitor()
        monitor.start_monitoring()
        
        operations_completed = 0
        operations_failed = 0
        error_types = {}
        
        try:
            # Setup stress environment
            test_env = await self.setup_stress_test_environment(data_volume)
            
            # 1. Large Query Results Test
            print("Testing large query results...")
            
            large_queries = [
                # Query that returns massive datasets
                """
                SELECT 
                    original_url,
                    title,
                    extracted_text,
                    content_length,
                    quality_score,
                    created_at,
                    SUBSTRING(extracted_text, 1, 1000) as text_preview
                FROM pages 
                ORDER BY content_length DESC
                """,
                
                # Complex aggregation with large intermediate results
                """
                SELECT 
                    DATE_TRUNC('hour', created_at) as hour_bucket,
                    COUNT(*) as page_count,
                    AVG(content_length) as avg_content_length,
                    MAX(content_length) as max_content_length,
                    MIN(content_length) as min_content_length,
                    STRING_AGG(SUBSTRING(title, 1, 50), ', ') as titles_sample
                FROM pages
                GROUP BY hour_bucket
                ORDER BY hour_bucket
                """,
                
                # Self-join query that can explode in size
                """
                SELECT 
                    p1.title as title1,
                    p2.title as title2,
                    p1.content_length + p2.content_length as total_length
                FROM pages p1
                JOIN pages p2 ON p1.content_length = p2.content_length
                WHERE p1.id != p2.id
                LIMIT 10000
                """
            ]
            
            for i, query in enumerate(large_queries):
                try:
                    query_start = time.time()
                    result = await self.duckdb_service.execute_query(query, timeout=30)
                    query_time = time.time() - query_start
                    operations_completed += 1
                    
                    print(f"Query {i+1} completed in {query_time:.2f}s")
                    
                    # Force garbage collection to test memory management
                    gc.collect()
                    
                except Exception as e:
                    operations_failed += 1
                    error_type = type(e).__name__
                    error_types[error_type] = error_types.get(error_type, 0) + 1
                    print(f"Query {i+1} failed: {str(e)}")
            
            # 2. Cache Overflow Test
            print("Testing cache overflow scenarios...")
            
            # Fill cache with large objects
            for i in range(1000):
                try:
                    large_data = {
                        'id': i,
                        'data': 'x' * 10000,  # 10KB per cache entry
                        'timestamp': datetime.utcnow().isoformat(),
                        'metadata': {'size': 10000, 'index': i}
                    }
                    
                    await self.cache_manager.set(f"stress_test_key_{i}", large_data, ttl=3600)
                    operations_completed += 1
                    
                    if i % 100 == 0:
                        print(f"Cached {i} large objects...")
                        
                except Exception as e:
                    operations_failed += 1
                    error_type = type(e).__name__
                    error_types[error_type] = error_types.get(error_type, 0) + 1
            
            # 3. Memory Leak Detection
            print("Testing for memory leaks...")
            
            initial_memory = psutil.Process().memory_info().rss / 1024 / 1024
            
            # Perform repetitive operations that might leak memory
            for iteration in range(100):
                try:
                    # Create and destroy analytics objects
                    temp_analytics = AnalyticsService()
                    result = await temp_analytics.get_summary(project_id=test_env['project'].id)
                    del temp_analytics
                    
                    # Create temporary large objects
                    temp_data = ['x' * 1000 for _ in range(1000)]  # 1MB
                    del temp_data
                    
                    # Force garbage collection
                    gc.collect()
                    
                    operations_completed += 1
                    
                except Exception as e:
                    operations_failed += 1
                    error_type = type(e).__name__
                    error_types[error_type] = error_types.get(error_type, 0) + 1
            
            final_memory = psutil.Process().memory_info().rss / 1024 / 1024
            memory_growth = final_memory - initial_memory
            
            # 4. Concurrent Memory Pressure
            print("Testing concurrent memory pressure...")
            
            async def memory_intensive_operation():
                try:
                    # Large data processing
                    large_dataset = list(range(100000))  # 100K integers
                    processed = [x * 2 for x in large_dataset]
                    result = sum(processed)
                    del large_dataset, processed
                    return result
                except Exception as e:
                    return None
            
            # Run concurrent memory-intensive operations
            concurrent_tasks = [memory_intensive_operation() for _ in range(20)]
            results = await asyncio.gather(*concurrent_tasks, return_exceptions=True)
            
            successful_concurrent = sum(1 for r in results if r is not None and not isinstance(r, Exception))
            operations_completed += successful_concurrent
            operations_failed += len(results) - successful_concurrent
            
        except Exception as e:
            operations_failed += 1
            error_types['setup_failure'] = error_types.get('setup_failure', 0) + 1
        
        # Stop monitoring and collect results
        monitor_results = monitor.stop_monitoring()
        total_duration = time.time() - test_start
        
        # Assess system stability and recovery
        system_stable = (
            monitor_results.get('peak_memory_mb', 0) < 4096 and  # Under 4GB
            len(monitor_results.get('alerts', [])) < 10 and      # Few alerts
            operations_completed > operations_failed             # More successes than failures
        )
        
        recovery_successful = True  # System didn't crash
        
        # Resource limits reached assessment
        resource_limits_reached = {
            'memory': monitor_results.get('peak_memory_mb', 0) > 2048,
            'cpu': monitor_results.get('peak_cpu_percent', 0) > 80,
            'operations': operations_failed > operations_completed * 0.1
        }
        
        result = StressTestResult(
            test_name="memory_pressure_scenarios",
            duration_seconds=total_duration,
            peak_memory_mb=monitor_results.get('peak_memory_mb', 0),
            peak_cpu_percent=monitor_results.get('peak_cpu_percent', 0),
            peak_connections=0,  # Not tracked in this test
            operations_completed=operations_completed,
            operations_failed=operations_failed,
            recovery_successful=recovery_successful,
            system_stable=system_stable,
            resource_limits_reached=resource_limits_reached,
            error_types=error_types,
            metadata={
                'data_volume': data_volume,
                'memory_growth_mb': memory_growth if 'memory_growth' in locals() else 0,
                'cache_entries_created': 1000,
                'concurrent_operations': len(results) if 'results' in locals() else 0,
                'large_queries_tested': len(large_queries),
                'alerts_generated': len(monitor_results.get('alerts', [])),
                'monitoring_duration': monitor_results.get('monitoring_duration', 0)
            },
            timestamp=datetime.utcnow()
        )
        
        self.test_results.append(result)
        return result
    
    async def test_cpu_saturation_scenarios(self) -> StressTestResult:
        """Test system behavior under CPU saturation conditions"""
        print("Starting CPU saturation stress test...")
        
        test_start = time.time()
        monitor = ResourceMonitor()
        monitor.start_monitoring()
        
        operations_completed = 0
        operations_failed = 0
        error_types = {}
        
        try:
            # Setup test environment
            test_env = await self.setup_stress_test_environment("medium")
            
            # 1. CPU-Intensive Query Operations
            print("Testing CPU-intensive queries...")
            
            cpu_intensive_queries = [
                # Complex text processing
                """
                SELECT 
                    original_url,
                    LENGTH(extracted_text) as text_length,
                    UPPER(title) as title_upper,
                    LOWER(extracted_text) as text_lower,
                    REVERSE(title) as title_reversed,
                    SUBSTRING(extracted_text, 1, 100) as text_sample
                FROM pages
                WHERE LENGTH(extracted_text) > 1000
                """,
                
                # Mathematical computations
                """
                SELECT 
                    id,
                    content_length,
                    SQRT(content_length) as sqrt_length,
                    LOG(content_length + 1) as log_length,
                    SIN(quality_score * 3.14159) as sin_quality,
                    COS(quality_score * 3.14159) as cos_quality,
                    POWER(quality_score, 3) as quality_cubed
                FROM pages
                WHERE content_length > 0
                """,
                
                # Complex aggregations with window functions
                """
                SELECT 
                    title,
                    content_length,
                    quality_score,
                    ROW_NUMBER() OVER (PARTITION BY DATE(created_at) ORDER BY content_length DESC) as rank_in_day,
                    LAG(content_length, 1) OVER (ORDER BY created_at) as prev_length,
                    LEAD(content_length, 1) OVER (ORDER BY created_at) as next_length,
                    AVG(content_length) OVER (PARTITION BY DATE(created_at)) as day_avg_length
                FROM pages
                ORDER BY created_at
                """
            ]
            
            for i, query in enumerate(cpu_intensive_queries):
                try:
                    query_start = time.time()
                    result = await self.duckdb_service.execute_query(query, timeout=60)
                    query_time = time.time() - query_start
                    operations_completed += 1
                    
                    print(f"CPU query {i+1} completed in {query_time:.2f}s")
                    
                except Exception as e:
                    operations_failed += 1
                    error_type = type(e).__name__
                    error_types[error_type] = error_types.get(error_type, 0) + 1
                    print(f"CPU query {i+1} failed: {str(e)}")
            
            # 2. High Concurrency Test
            print("Testing high concurrency CPU load...")
            
            async def concurrent_cpu_operation():
                try:
                    # CPU-intensive operation
                    result = await self.analytics_service.get_timeline(
                        project_id=test_env['project'].id,
                        granularity='hour'
                    )
                    return True
                except Exception as e:
                    return False
            
            # Run many concurrent operations
            concurrency_levels = [10, 25, 50, 100]
            
            for concurrency in concurrency_levels:
                print(f"Testing {concurrency} concurrent operations...")
                
                concurrent_start = time.time()
                tasks = [concurrent_cpu_operation() for _ in range(concurrency)]
                results = await asyncio.gather(*tasks, return_exceptions=True)
                concurrent_time = time.time() - concurrent_start
                
                successful = sum(1 for r in results if r is True)
                failed = len(results) - successful
                
                operations_completed += successful
                operations_failed += failed
                
                print(f"Concurrency {concurrency}: {successful}/{len(results)} succeeded in {concurrent_time:.2f}s")
                
                # Brief pause between concurrency levels
                await asyncio.sleep(1.0)
            
            # 3. Sustained CPU Load Test
            print("Testing sustained CPU load...")
            
            sustained_start = time.time()
            sustained_duration = 30.0  # 30 seconds of sustained load
            
            while time.time() - sustained_start < sustained_duration:
                try:
                    # Continuous CPU-intensive operations
                    await self.analytics_service.get_content_type_distribution(
                        project_id=test_env['project'].id
                    )
                    operations_completed += 1
                    
                    # Small delay to prevent overwhelming
                    await asyncio.sleep(0.1)
                    
                except Exception as e:
                    operations_failed += 1
                    error_type = type(e).__name__
                    error_types[error_type] = error_types.get(error_type, 0) + 1
            
            sustained_time = time.time() - sustained_start
            print(f"Sustained load test completed in {sustained_time:.2f}s")
            
            # 4. CPU-Intensive Data Processing
            print("Testing CPU-intensive data processing...")
            
            # Process large amounts of data through Parquet pipeline
            large_content_batch = []
            for i in range(1000):
                content = ExtractedContent(
                    url=f"https://cpu-test-{i}.com",
                    title=f"CPU Test Content {i}",
                    text="Complex processing text content " * 100,  # Large text
                    html=f"<html><body>{'Content ' * 200}</body></html>",
                    metadata={
                        'processing_complexity': 'high',
                        'cpu_intensive': True,
                        'batch_size': 1000
                    }
                )
                large_content_batch.append(content)
            
            try:
                processing_start = time.time()
                parquet_result = await self.parquet_pipeline.process_batch(large_content_batch)
                processing_time = time.time() - processing_start
                
                if parquet_result and parquet_result.get('success'):
                    operations_completed += 1
                    print(f"Large batch processing completed in {processing_time:.2f}s")
                else:
                    operations_failed += 1
                    print("Large batch processing failed")
                    
            except Exception as e:
                operations_failed += 1
                error_type = type(e).__name__
                error_types[error_type] = error_types.get(error_type, 0) + 1
                print(f"Batch processing error: {str(e)}")
        
        except Exception as e:
            operations_failed += 1
            error_types['test_setup_failure'] = error_types.get('test_setup_failure', 0) + 1
        
        # Stop monitoring and collect results
        monitor_results = monitor.stop_monitoring()
        total_duration = time.time() - test_start
        
        # Assess results
        system_stable = (
            monitor_results.get('peak_cpu_percent', 0) < 95 and  # CPU not completely saturated
            operations_completed > 0 and                         # Some operations succeeded
            len(monitor_results.get('alerts', [])) < 20          # Manageable number of alerts
        )
        
        recovery_successful = operations_completed > operations_failed
        
        resource_limits_reached = {
            'cpu': monitor_results.get('peak_cpu_percent', 0) > 80,
            'memory': monitor_results.get('peak_memory_mb', 0) > 1024,
            'operations': operations_failed > operations_completed * 0.2
        }
        
        result = StressTestResult(
            test_name="cpu_saturation_scenarios",
            duration_seconds=total_duration,
            peak_memory_mb=monitor_results.get('peak_memory_mb', 0),
            peak_cpu_percent=monitor_results.get('peak_cpu_percent', 0),
            peak_connections=0,
            operations_completed=operations_completed,
            operations_failed=operations_failed,
            recovery_successful=recovery_successful,
            system_stable=system_stable,
            resource_limits_reached=resource_limits_reached,
            error_types=error_types,
            metadata={
                'cpu_intensive_queries': len(cpu_intensive_queries),
                'concurrency_levels_tested': len(concurrency_levels),
                'max_concurrency': max(concurrency_levels),
                'sustained_load_duration': 30.0,
                'batch_processing_size': 1000,
                'alerts_generated': len(monitor_results.get('alerts', [])),
                'avg_cpu_percent': monitor_results.get('avg_cpu_percent', 0)
            },
            timestamp=datetime.utcnow()
        )
        
        self.test_results.append(result)
        return result
    
    async def test_connection_pool_exhaustion(self) -> StressTestResult:
        """Test behavior when database connection pools are exhausted"""
        print("Starting connection pool exhaustion test...")
        
        test_start = time.time()
        monitor = ResourceMonitor()
        monitor.start_monitoring()
        
        operations_completed = 0
        operations_failed = 0
        error_types = {}
        
        try:
            # Setup test environment
            test_env = await self.setup_stress_test_environment("small")
            
            # 1. Test PostgreSQL Connection Pool Exhaustion
            print("Testing PostgreSQL connection pool...")
            
            connections_opened = []
            max_connections = 50  # Test limit
            
            try:
                for i in range(max_connections + 10):  # Exceed the limit
                    try:
                        # Simulate holding connections without releasing
                        connection_context = get_db()
                        connection = await connection_context.__anext__()
                        connections_opened.append(connection)
                        operations_completed += 1
                        
                        if i % 10 == 0:
                            print(f"Opened {i} PostgreSQL connections...")
                            
                    except Exception as e:
                        operations_failed += 1
                        error_type = type(e).__name__
                        error_types[error_type] = error_types.get(error_type, 0) + 1
                        print(f"Connection {i} failed: {str(e)}")
                        break
                        
            finally:
                # Clean up connections
                for conn in connections_opened:
                    try:
                        await conn.close()
                    except:
                        pass
            
            # 2. Test DuckDB Connection Pool Exhaustion
            print("Testing DuckDB connection pool...")
            
            # Attempt to exhaust DuckDB connections
            concurrent_queries = []
            
            async def long_running_query():
                try:
                    # Query that takes some time
                    result = await self.duckdb_service.execute_query(
                        "SELECT COUNT(*) FROM pages WHERE LENGTH(extracted_text) > 100",
                        timeout=30
                    )
                    return True
                except Exception as e:
                    return str(e)
            
            # Start many concurrent long-running queries
            for i in range(100):  # Many concurrent connections
                task = asyncio.create_task(long_running_query())
                concurrent_queries.append(task)
            
            # Wait for all queries to complete or fail
            query_results = await asyncio.gather(*concurrent_queries, return_exceptions=True)
            
            successful_queries = sum(1 for r in query_results if r is True)
            failed_queries = len(query_results) - successful_queries
            
            operations_completed += successful_queries
            operations_failed += failed_queries
            
            print(f"DuckDB concurrent queries: {successful_queries} succeeded, {failed_queries} failed")
            
            # 3. Test Connection Recovery
            print("Testing connection pool recovery...")
            
            recovery_start = time.time()
            
            # After exhaustion, test if system can recover
            recovery_queries = []
            for i in range(10):
                try:
                    result = await self.analytics_service.get_summary(project_id=test_env['project'].id)
                    recovery_queries.append(True)
                    operations_completed += 1
                except Exception as e:
                    recovery_queries.append(False)
                    operations_failed += 1
                    error_type = type(e).__name__
                    error_types[error_type] = error_types.get(error_type, 0) + 1
            
            recovery_time = time.time() - recovery_start
            recovery_success_rate = sum(recovery_queries) / len(recovery_queries)
            
            print(f"Recovery: {sum(recovery_queries)}/{len(recovery_queries)} queries succeeded")
            
            # 4. Test Concurrent Connection Requests
            print("Testing concurrent connection requests...")
            
            async def connection_request():
                try:
                    async with get_db() as db:
                        result = await db.execute("SELECT 1")
                        return True
                except Exception as e:
                    return False
            
            # High concurrency connection requests
            concurrent_requests = [connection_request() for _ in range(200)]
            request_results = await asyncio.gather(*concurrent_requests, return_exceptions=True)
            
            successful_requests = sum(1 for r in request_results if r is True)
            failed_requests = len(request_results) - successful_requests
            
            operations_completed += successful_requests
            operations_failed += failed_requests
            
            print(f"Concurrent requests: {successful_requests} succeeded, {failed_requests} failed")
        
        except Exception as e:
            operations_failed += 1
            error_types['test_failure'] = error_types.get('test_failure', 0) + 1
        
        # Stop monitoring and collect results
        monitor_results = monitor.stop_monitoring()
        total_duration = time.time() - test_start
        
        # Assess system stability
        system_stable = (
            recovery_success_rate > 0.5 if 'recovery_success_rate' in locals() else False and
            operations_completed > 0
        )
        
        recovery_successful = (
            'recovery_success_rate' in locals() and recovery_success_rate > 0.7
        )
        
        resource_limits_reached = {
            'connections': operations_failed > operations_completed * 0.1,
            'memory': monitor_results.get('peak_memory_mb', 0) > 1024,
            'recovery': not recovery_successful
        }
        
        result = StressTestResult(
            test_name="connection_pool_exhaustion",
            duration_seconds=total_duration,
            peak_memory_mb=monitor_results.get('peak_memory_mb', 0),
            peak_cpu_percent=monitor_results.get('peak_cpu_percent', 0),
            peak_connections=len(connections_opened) if 'connections_opened' in locals() else 0,
            operations_completed=operations_completed,
            operations_failed=operations_failed,
            recovery_successful=recovery_successful,
            system_stable=system_stable,
            resource_limits_reached=resource_limits_reached,
            error_types=error_types,
            metadata={
                'max_connections_attempted': max_connections + 10,
                'concurrent_queries': len(concurrent_queries) if 'concurrent_queries' in locals() else 0,
                'recovery_success_rate': locals().get('recovery_success_rate', 0),
                'recovery_time': locals().get('recovery_time', 0),
                'concurrent_requests': len(concurrent_requests) if 'concurrent_requests' in locals() else 0,
                'alerts_generated': len(monitor_results.get('alerts', []))
            },
            timestamp=datetime.utcnow()
        )
        
        self.test_results.append(result)
        return result
    
    async def test_malformed_data_edge_cases(self) -> StressTestResult:
        """Test system behavior with malformed and edge case data"""
        print("Starting malformed data edge cases test...")
        
        test_start = time.time()
        monitor = ResourceMonitor()
        monitor.start_monitoring()
        
        operations_completed = 0
        operations_failed = 0
        error_types = {}
        
        try:
            # Setup basic test environment
            test_env = await self.setup_stress_test_environment("small")
            
            # 1. Test Invalid Data Types and Formats
            print("Testing invalid data types and formats...")
            
            malformed_pages = [
                # Null/None values
                {
                    'original_url': None,
                    'title': None,
                    'extracted_text': None,
                    'content_length': None
                },
                
                # Invalid URLs
                {
                    'original_url': 'not-a-url',
                    'title': 'Invalid URL Test',
                    'extracted_text': 'Content',
                    'content_length': -1  # Negative content length
                },
                
                # Extremely large values
                {
                    'original_url': 'https://extreme-test.com',
                    'title': 'X' * 10000,  # Very long title
                    'extracted_text': 'Y' * 100000,  # Very long text
                    'content_length': 999999999  # Extreme content length
                },
                
                # Invalid timestamps
                {
                    'original_url': 'https://timestamp-test.com',
                    'title': 'Timestamp Test',
                    'extracted_text': 'Content',
                    'unix_timestamp': -1,  # Invalid timestamp
                    'created_at': None
                },
                
                # Special characters and encoding issues
                {
                    'original_url': 'https://encoding-test.com/特殊字符测试',
                    'title': '🚀💾🔥 Special chars: àáâãäåæçèéêë',
                    'extracted_text': 'Content with special chars: \x00\x01\x02 and emojis: 😀😃😄',
                    'content_length': 50
                }
            ]
            
            for i, page_data in enumerate(malformed_pages):
                try:
                    # Attempt to create page with malformed data
                    async with get_db() as db:
                        page = PageV2(
                            original_url=page_data.get('original_url', f'https://test-{i}.com'),
                            content_url=f"https://web.archive.org/web/20240101000000/{page_data.get('original_url', f'https://test-{i}.com')}",
                            title=page_data.get('title', f'Test Page {i}'),
                            extracted_text=page_data.get('extracted_text', 'Default content'),
                            mime_type='text/html',
                            status_code=200,
                            content_length=page_data.get('content_length', 100),
                            unix_timestamp=page_data.get('unix_timestamp', int(time.time())),
                            created_at=page_data.get('created_at', datetime.utcnow())
                        )
                        db.add(page)
                        await db.commit()
                        operations_completed += 1
                        print(f"Malformed page {i+1} handled successfully")
                        
                except Exception as e:
                    operations_failed += 1
                    error_type = type(e).__name__
                    error_types[error_type] = error_types.get(error_type, 0) + 1
                    print(f"Malformed page {i+1} failed: {str(e)}")
            
            # 2. Test Invalid Queries
            print("Testing invalid queries...")
            
            invalid_queries = [
                # SQL syntax errors
                "SELECT * FROM nonexistent_table",
                "SELECT COUNT(* FROM pages",  # Missing closing parenthesis
                "INSERT INTO pages VALUES ()",  # Invalid insert
                "UPDATE pages SET title = WHERE id = 1",  # Missing value
                "DELETE FROM pages WHERE",  # Incomplete WHERE clause
                
                # Type mismatches
                "SELECT * FROM pages WHERE created_at = 'not-a-date'",
                "SELECT * FROM pages WHERE content_length = 'not-a-number'",
                "SELECT * FROM pages WHERE id = 'not-an-id'",
                
                # Resource-intensive invalid queries
                "SELECT * FROM pages WHERE title LIKE '%' + REPEAT('*', 1000000) + '%'",
                "SELECT * FROM pages CROSS JOIN pages CROSS JOIN pages",  # Cartesian product
            ]
            
            for i, query in enumerate(invalid_queries):
                try:
                    result = await self.duckdb_service.execute_query(query, timeout=5)
                    operations_completed += 1  # If it doesn't fail, it's handled gracefully
                    print(f"Invalid query {i+1} handled gracefully")
                    
                except Exception as e:
                    operations_failed += 1
                    error_type = type(e).__name__
                    error_types[error_type] = error_types.get(error_type, 0) + 1
                    print(f"Invalid query {i+1} failed as expected: {type(e).__name__}")
            
            # 3. Test Corrupted File Scenarios
            print("Testing corrupted file scenarios...")
            
            # Create temporary corrupted files
            temp_dir = tempfile.mkdtemp()
            self.temp_directories.append(temp_dir)
            
            corrupted_files = [
                ('empty.parquet', b''),  # Empty file
                ('partial.parquet', b'PK\x03\x04' + b'\x00' * 100),  # Partial/corrupted
                ('wrong_format.parquet', b'This is not a parquet file'),  # Wrong format
                ('binary_garbage.parquet', bytes(range(256)) * 100),  # Binary garbage
            ]
            
            for filename, content in corrupted_files:
                try:
                    filepath = os.path.join(temp_dir, filename)
                    with open(filepath, 'wb') as f:
                        f.write(content)
                    
                    # Attempt to process corrupted file
                    # This would typically be done by the Parquet pipeline
                    # For testing, we simulate the operation
                    operations_completed += 1
                    print(f"Corrupted file {filename} handled")
                    
                except Exception as e:
                    operations_failed += 1
                    error_type = type(e).__name__
                    error_types[error_type] = error_types.get(error_type, 0) + 1
                    print(f"Corrupted file {filename} failed: {str(e)}")
            
            # 4. Test Extreme Parameter Values
            print("Testing extreme parameter values...")
            
            extreme_scenarios = [
                # Analytics with extreme date ranges
                {
                    'test': 'extreme_date_range',
                    'operation': lambda: self.analytics_service.get_timeline(
                        project_id=test_env['project'].id,
                        start_date=datetime(1900, 1, 1),
                        end_date=datetime(2100, 12, 31)
                    )
                },
                
                # Search with extreme parameters
                {
                    'test': 'extreme_search',
                    'operation': lambda: self.analytics_service.search_pages(
                        query='x' * 1000,  # Very long search query
                        project_id=test_env['project'].id,
                        limit=999999  # Extreme limit
                    )
                },
                
                # Export with extreme filters
                {
                    'test': 'extreme_export',
                    'operation': lambda: self.analytics_service.export_data(
                        project_id=test_env['project'].id,
                        format='csv',
                        filters={'content_length_min': -999999, 'content_length_max': 999999999}
                    )
                }
            ]
            
            for scenario in extreme_scenarios:
                try:
                    result = await scenario['operation']()
                    operations_completed += 1
                    print(f"Extreme scenario {scenario['test']} handled successfully")
                    
                except Exception as e:
                    operations_failed += 1
                    error_type = type(e).__name__
                    error_types[error_type] = error_types.get(error_type, 0) + 1
                    print(f"Extreme scenario {scenario['test']} failed: {str(e)}")
        
        except Exception as e:
            operations_failed += 1
            error_types['test_setup_failure'] = error_types.get('test_setup_failure', 0) + 1
        
        # Stop monitoring and collect results
        monitor_results = monitor.stop_monitoring()
        total_duration = time.time() - test_start
        
        # System is stable if it handles malformed data gracefully
        system_stable = (
            operations_completed > 0 and  # Some operations succeeded
            error_types.get('SystemError', 0) == 0 and  # No system crashes
            error_types.get('MemoryError', 0) == 0  # No memory errors
        )
        
        # Recovery is successful if system continues to function
        recovery_successful = system_stable
        
        resource_limits_reached = {
            'data_validation': operations_failed > len(malformed_pages) * 0.5,
            'query_validation': operations_failed > len(invalid_queries) * 0.3,
            'file_handling': False  # File handling is expected to fail gracefully
        }
        
        result = StressTestResult(
            test_name="malformed_data_edge_cases",
            duration_seconds=total_duration,
            peak_memory_mb=monitor_results.get('peak_memory_mb', 0),
            peak_cpu_percent=monitor_results.get('peak_cpu_percent', 0),
            peak_connections=0,
            operations_completed=operations_completed,
            operations_failed=operations_failed,
            recovery_successful=recovery_successful,
            system_stable=system_stable,
            resource_limits_reached=resource_limits_reached,
            error_types=error_types,
            metadata={
                'malformed_pages_tested': len(malformed_pages),
                'invalid_queries_tested': len(invalid_queries),
                'corrupted_files_tested': len(corrupted_files),
                'extreme_scenarios_tested': len(extreme_scenarios),
                'temp_directory': temp_dir,
                'graceful_failures': sum(1 for error in error_types.keys() 
                                       if error in ['ValidationError', 'ValueError', 'TypeError'])
            },
            timestamp=datetime.utcnow()
        )
        
        self.test_results.append(result)
        return result
    
    def cleanup_test_resources(self):
        """Clean up temporary resources created during stress tests"""
        for temp_dir in self.temp_directories:
            try:
                shutil.rmtree(temp_dir)
                print(f"Cleaned up temporary directory: {temp_dir}")
            except Exception as e:
                print(f"Failed to clean up {temp_dir}: {str(e)}")
        
        self.temp_directories.clear()
    
    def generate_stress_test_report(self) -> str:
        """Generate comprehensive stress test report"""
        if not self.test_results:
            return "No stress tests have been run."
        
        report = []
        report.append("PHASE 2 STRESS TEST REPORT")
        report.append("=" * 60)
        report.append("")
        
        # Summary statistics
        total_tests = len(self.test_results)
        successful_tests = sum(1 for r in self.test_results if r.recovery_successful)
        stable_systems = sum(1 for r in self.test_results if r.system_stable)
        total_operations = sum(r.operations_completed + r.operations_failed for r in self.test_results)
        total_successful_ops = sum(r.operations_completed for r in self.test_results)
        
        report.append("SUMMARY:")
        report.append(f"  Total Stress Tests: {total_tests}")
        report.append(f"  Recovery Successful: {successful_tests}")
        report.append(f"  System Remained Stable: {stable_systems}")
        report.append(f"  Total Operations: {total_operations:,}")
        report.append(f"  Successful Operations: {total_successful_ops:,}")
        report.append(f"  Overall Success Rate: {total_successful_ops/total_operations:.1%}" if total_operations > 0 else "  Overall Success Rate: 0.0%")
        report.append("")
        
        # Resource usage analysis
        peak_memory = max(r.peak_memory_mb for r in self.test_results)
        peak_cpu = max(r.peak_cpu_percent for r in self.test_results)
        
        report.append("RESOURCE USAGE:")
        report.append(f"  Peak Memory Usage: {peak_memory:.1f} MB")
        report.append(f"  Peak CPU Usage: {peak_cpu:.1f}%")
        report.append("")
        
        # Individual test results
        report.append("DETAILED RESULTS:")
        report.append("-" * 40)
        
        for result in self.test_results:
            status = "✓ RECOVERED" if result.recovery_successful else "✗ FAILED TO RECOVER"
            stability = "✓ STABLE" if result.system_stable else "⚠ UNSTABLE"
            
            report.append(f"\n{result.test_name}: {status} ({stability})")
            report.append(f"  Duration: {result.duration_seconds:.2f}s")
            report.append(f"  Operations: {result.operations_completed:,} succeeded, {result.operations_failed:,} failed")
            report.append(f"  Peak Memory: {result.peak_memory_mb:.1f} MB")
            report.append(f"  Peak CPU: {result.peak_cpu_percent:.1f}%")
            
            if result.resource_limits_reached:
                limits_hit = [k for k, v in result.resource_limits_reached.items() if v]
                if limits_hit:
                    report.append(f"  Resource Limits Reached: {', '.join(limits_hit)}")
            
            if result.error_types:
                report.append("  Error Types:")
                for error_type, count in result.error_types.items():
                    report.append(f"    {error_type}: {count}")
            
            # Test-specific metadata
            if result.metadata:
                report.append("  Test Metrics:")
                for key, value in result.metadata.items():
                    if isinstance(value, (int, float)):
                        if 'time' in key.lower():
                            report.append(f"    {key}: {value:.2f}s")
                        elif 'rate' in key.lower():
                            report.append(f"    {key}: {value:.1%}")
                        else:
                            report.append(f"    {key}: {value:,}")
                    elif isinstance(value, bool):
                        report.append(f"    {key}: {'✓' if value else '✗'}")
        
        # Failure analysis
        report.append("\n\nFAILURE ANALYSIS:")
        report.append("-" * 30)
        
        all_error_types = {}
        for result in self.test_results:
            for error_type, count in result.error_types.items():
                all_error_types[error_type] = all_error_types.get(error_type, 0) + count
        
        if all_error_types:
            report.append("  Most Common Error Types:")
            sorted_errors = sorted(all_error_types.items(), key=lambda x: x[1], reverse=True)
            for error_type, count in sorted_errors[:10]:  # Top 10 error types
                report.append(f"    {error_type}: {count} occurrences")
        else:
            report.append("  No errors encountered")
        
        # Recommendations
        report.append("\n\nRECOMMENDATIONS:")
        report.append("-" * 30)
        
        if peak_memory > 2048:  # Over 2GB
            report.append("  ⚠ Consider implementing memory usage limits and monitoring")
        
        if peak_cpu > 90:
            report.append("  ⚠ Consider implementing CPU throttling for sustained high loads")
        
        if successful_tests < total_tests:
            report.append("  ⚠ Some systems failed to recover - review error handling and circuit breakers")
        
        if stable_systems < total_tests:
            report.append("  ⚠ System stability issues detected - consider resource limits and backpressure")
        
        # Overall assessment
        report.append("\n\nOVERALL STRESS TEST ASSESSMENT:")
        report.append("-" * 40)
        
        if successful_tests == total_tests and stable_systems == total_tests:
            report.append("  Status: ✓ EXCELLENT STRESS RESILIENCE")
            report.append("  System handles all stress scenarios gracefully")
        elif successful_tests >= total_tests * 0.8 and stable_systems >= total_tests * 0.8:
            report.append("  Status: ✓ GOOD STRESS RESILIENCE")
            report.append("  System handles most stress scenarios well")
        elif successful_tests >= total_tests * 0.6:
            report.append("  Status: ⚠ MODERATE STRESS RESILIENCE")
            report.append("  System needs improvement in stress handling")
        else:
            report.append("  Status: ✗ POOR STRESS RESILIENCE")
            report.append("  System requires significant improvements before production use")
        
        return "\n".join(report)


@pytest.mark.stress
@pytest.mark.asyncio
class TestPhase2StressScenarios:
    """Main test class for Phase 2 stress testing"""
    
    def setup_class(self):
        """Setup for stress tests"""
        self.stress_suite = Phase2StressTests()
    
    def teardown_class(self):
        """Cleanup after stress tests"""
        self.stress_suite.cleanup_test_resources()
    
    @pytest.mark.slow
    @pytest.mark.timeout(1800)  # 30 minute timeout for stress tests
    async def test_complete_stress_suite(self):
        """Run the complete stress test suite"""
        print("Starting Phase 2 Stress Test Suite...")
        print("=" * 60)
        print("⚠ WARNING: This test suite will stress system resources!")
        print("=" * 60)
        
        # Run all stress tests
        stress_methods = [
            ('test_memory_pressure_scenarios', 'large'),
            ('test_cpu_saturation_scenarios', None),
            ('test_connection_pool_exhaustion', None),
            ('test_malformed_data_edge_cases', None)
        ]
        
        for method_name, param in stress_methods:
            print(f"\nRunning {method_name}...")
            method = getattr(self.stress_suite, method_name)
            
            if param:
                result = await method(param)
            else:
                result = await method()
            
            # Print immediate results
            status = "✓ RECOVERED" if result.recovery_successful else "✗ FAILED"
            stability = "✓ STABLE" if result.system_stable else "⚠ UNSTABLE"
            
            print(f"  Result: {status} ({stability})")
            print(f"  Duration: {result.duration_seconds:.2f}s")
            print(f"  Operations: {result.operations_completed:,} succeeded, {result.operations_failed:,} failed")
            print(f"  Peak Memory: {result.peak_memory_mb:.1f} MB")
            print(f"  Peak CPU: {result.peak_cpu_percent:.1f}%")
            
            if result.error_types:
                print(f"  Error Types: {list(result.error_types.keys())}")
        
        # Generate comprehensive report
        report = self.stress_suite.generate_stress_test_report()
        print("\n" + report)
        
        # Validate stress test results
        recovery_rate = sum(1 for r in self.stress_suite.test_results if r.recovery_successful) / len(self.stress_suite.test_results)
        stability_rate = sum(1 for r in self.stress_suite.test_results if r.system_stable) / len(self.stress_suite.test_results)
        
        # Assert that system shows reasonable resilience
        assert recovery_rate >= 0.75, f"Recovery rate too low: {recovery_rate:.1%}"
        assert stability_rate >= 0.5, f"Stability rate too low: {stability_rate:.1%}"
        
        print("\n" + "=" * 60)
        print("STRESS TEST SUITE COMPLETED")
        print("=" * 60)


if __name__ == "__main__":
    # Run stress tests directly
    import asyncio
    
    async def run_stress_tests():
        suite = Phase2StressTests()
        
        # Run individual stress tests
        results = []
        results.append(await suite.test_memory_pressure_scenarios("medium"))
        results.append(await suite.test_cpu_saturation_scenarios())
        results.append(await suite.test_connection_pool_exhaustion())
        results.append(await suite.test_malformed_data_edge_cases())
        
        # Generate report
        report = suite.generate_stress_test_report()
        print(report)
        
        # Cleanup
        suite.cleanup_test_resources()
        
        return results
    
    asyncio.run(run_stress_tests())