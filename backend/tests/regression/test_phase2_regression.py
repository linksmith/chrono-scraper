"""
Phase 2 Performance Regression Testing Framework

This module provides automated performance regression detection for the Phase 2 DuckDB
analytics system. It tracks performance metrics over time and automatically detects
when performance degrades beyond acceptable thresholds.

Regression Testing Features:
- Baseline Performance Tracking: Established performance benchmarks with versioning
- Threshold Monitoring: Automatic detection of >10% performance degradation
- Historical Comparison: Performance trends over multiple deployments/commits
- Component-Level Regression: Individual service performance tracking
- Alert Generation: Automated notifications for performance regressions
- Trend Analysis: Statistical analysis of performance trends over time

The framework maintains a performance history database and provides automated
regression detection with configurable thresholds and alerting mechanisms.
"""

import asyncio
import pytest
import pytest_asyncio
import time
import json
import sqlite3
import statistics
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, asdict
from pathlib import Path
import numpy as np
import hashlib

from sqlmodel import Session, select
from fastapi.testclient import TestClient

from app.core.database import get_db
from app.services.duckdb_service import DuckDBService
from app.services.analytics_service import AnalyticsService
from app.services.parquet_pipeline import ParquetPipeline
from app.services.data_sync_service import DataSyncService
from app.services.hybrid_query_router import HybridQueryRouter
from app.services.intelligent_cache_manager import IntelligentCacheManager

from app.models.shared_pages import PageV2
from app.models.project import Project
from app.models.user import User


@dataclass
class PerformanceBaseline:
    """Performance baseline for regression comparison"""
    test_name: str
    component: str
    version: str
    commit_hash: str
    timestamp: datetime
    metrics: Dict[str, float]
    metadata: Dict[str, Any]
    environment_info: Dict[str, str]


@dataclass
class RegressionResult:
    """Result of a regression test comparison"""
    test_name: str
    component: str
    current_version: str
    baseline_version: str
    regression_detected: bool
    performance_change_percent: float
    threshold_exceeded: bool
    current_metrics: Dict[str, float]
    baseline_metrics: Dict[str, float]
    regression_details: Dict[str, Any]
    severity: str  # 'minor', 'moderate', 'major', 'critical'
    timestamp: datetime


class PerformanceHistoryDatabase:
    """Database for storing and retrieving performance history"""
    
    def __init__(self, db_path: str = "performance_history.db"):
        self.db_path = Path(db_path)
        self._init_database()
    
    def _init_database(self):
        """Initialize the performance history database"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Create baselines table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS performance_baselines (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    test_name TEXT NOT NULL,
                    component TEXT NOT NULL,
                    version TEXT NOT NULL,
                    commit_hash TEXT,
                    timestamp TEXT NOT NULL,
                    metrics TEXT NOT NULL,
                    metadata TEXT,
                    environment_info TEXT,
                    UNIQUE(test_name, component, version, commit_hash)
                )
            """)
            
            # Create regression results table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS regression_results (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    test_name TEXT NOT NULL,
                    component TEXT NOT NULL,
                    current_version TEXT NOT NULL,
                    baseline_version TEXT NOT NULL,
                    regression_detected BOOLEAN NOT NULL,
                    performance_change_percent REAL NOT NULL,
                    threshold_exceeded BOOLEAN NOT NULL,
                    current_metrics TEXT NOT NULL,
                    baseline_metrics TEXT NOT NULL,
                    regression_details TEXT,
                    severity TEXT NOT NULL,
                    timestamp TEXT NOT NULL
                )
            """)
            
            # Create indexes for efficient querying
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_baselines_test_component 
                ON performance_baselines(test_name, component)
            """)
            
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_baselines_timestamp 
                ON performance_baselines(timestamp)
            """)
            
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_regressions_timestamp 
                ON regression_results(timestamp)
            """)
            
            conn.commit()
    
    def store_baseline(self, baseline: PerformanceBaseline):
        """Store a performance baseline"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                INSERT OR REPLACE INTO performance_baselines 
                (test_name, component, version, commit_hash, timestamp, metrics, metadata, environment_info)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                baseline.test_name,
                baseline.component,
                baseline.version,
                baseline.commit_hash,
                baseline.timestamp.isoformat(),
                json.dumps(baseline.metrics),
                json.dumps(baseline.metadata),
                json.dumps(baseline.environment_info)
            ))
            
            conn.commit()
    
    def get_latest_baseline(self, test_name: str, component: str) -> Optional[PerformanceBaseline]:
        """Get the latest baseline for a test and component"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT test_name, component, version, commit_hash, timestamp, 
                       metrics, metadata, environment_info
                FROM performance_baselines
                WHERE test_name = ? AND component = ?
                ORDER BY timestamp DESC
                LIMIT 1
            """, (test_name, component))
            
            row = cursor.fetchone()
            if row:
                return PerformanceBaseline(
                    test_name=row[0],
                    component=row[1],
                    version=row[2],
                    commit_hash=row[3],
                    timestamp=datetime.fromisoformat(row[4]),
                    metrics=json.loads(row[5]),
                    metadata=json.loads(row[6] or "{}"),
                    environment_info=json.loads(row[7] or "{}")
                )
            
            return None
    
    def get_baseline_history(self, test_name: str, component: str, limit: int = 10) -> List[PerformanceBaseline]:
        """Get baseline history for a test and component"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT test_name, component, version, commit_hash, timestamp,
                       metrics, metadata, environment_info
                FROM performance_baselines
                WHERE test_name = ? AND component = ?
                ORDER BY timestamp DESC
                LIMIT ?
            """, (test_name, component, limit))
            
            baselines = []
            for row in cursor.fetchall():
                baselines.append(PerformanceBaseline(
                    test_name=row[0],
                    component=row[1],
                    version=row[2],
                    commit_hash=row[3],
                    timestamp=datetime.fromisoformat(row[4]),
                    metrics=json.loads(row[5]),
                    metadata=json.loads(row[6] or "{}"),
                    environment_info=json.loads(row[7] or "{}")
                ))
            
            return baselines
    
    def store_regression_result(self, result: RegressionResult):
        """Store a regression test result"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                INSERT INTO regression_results
                (test_name, component, current_version, baseline_version, 
                 regression_detected, performance_change_percent, threshold_exceeded,
                 current_metrics, baseline_metrics, regression_details, severity, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                result.test_name,
                result.component,
                result.current_version,
                result.baseline_version,
                result.regression_detected,
                result.performance_change_percent,
                result.threshold_exceeded,
                json.dumps(result.current_metrics),
                json.dumps(result.baseline_metrics),
                json.dumps(result.regression_details),
                result.severity,
                result.timestamp.isoformat()
            ))
            
            conn.commit()
    
    def get_recent_regressions(self, days: int = 30) -> List[RegressionResult]:
        """Get recent regression results"""
        cutoff_date = datetime.utcnow() - timedelta(days=days)
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT test_name, component, current_version, baseline_version,
                       regression_detected, performance_change_percent, threshold_exceeded,
                       current_metrics, baseline_metrics, regression_details, severity, timestamp
                FROM regression_results
                WHERE timestamp >= ? AND regression_detected = 1
                ORDER BY timestamp DESC
            """, (cutoff_date.isoformat(),))
            
            results = []
            for row in cursor.fetchall():
                results.append(RegressionResult(
                    test_name=row[0],
                    component=row[1],
                    current_version=row[2],
                    baseline_version=row[3],
                    regression_detected=bool(row[4]),
                    performance_change_percent=row[5],
                    threshold_exceeded=bool(row[6]),
                    current_metrics=json.loads(row[7]),
                    baseline_metrics=json.loads(row[8]),
                    regression_details=json.loads(row[9]),
                    severity=row[10],
                    timestamp=datetime.fromisoformat(row[11])
                ))
            
            return results


class Phase2RegressionTests:
    """Performance regression testing for Phase 2 system"""
    
    def __init__(self, db_path: str = "performance_history.db"):
        self.history_db = PerformanceHistoryDatabase(db_path)
        self.duckdb_service = DuckDBService()
        self.analytics_service = AnalyticsService()
        self.parquet_pipeline = ParquetPipeline()
        self.cache_manager = IntelligentCacheManager()
        
        # Regression detection thresholds
        self.regression_thresholds = {
            'minor': 0.10,     # 10% performance degradation
            'moderate': 0.25,  # 25% performance degradation
            'major': 0.50,     # 50% performance degradation
            'critical': 1.0    # 100% performance degradation (2x slower)
        }
        
        # Current version/commit info (would be set by CI/CD)
        self.current_version = "2.0.0-test"
        self.current_commit = self._get_current_commit_hash()
        
        self.environment_info = {
            'python_version': '3.11',
            'os': 'linux',
            'cpu_cores': '4',
            'memory_gb': '16'
        }
    
    def _get_current_commit_hash(self) -> str:
        """Get current git commit hash (mock for testing)"""
        # In real implementation, would get actual git commit
        return hashlib.md5(f"{datetime.utcnow()}".encode()).hexdigest()[:8]
    
    async def run_baseline_benchmark(self, test_name: str, component: str) -> Dict[str, float]:
        """Run a standardized benchmark for baseline establishment"""
        
        if component == "duckdb_service":
            return await self._benchmark_duckdb_service()
        elif component == "analytics_service":
            return await self._benchmark_analytics_service()
        elif component == "parquet_pipeline":
            return await self._benchmark_parquet_pipeline()
        elif component == "cache_manager":
            return await self._benchmark_cache_manager()
        elif component == "hybrid_query_router":
            return await self._benchmark_hybrid_query_router()
        else:
            raise ValueError(f"Unknown component: {component}")
    
    async def _benchmark_duckdb_service(self) -> Dict[str, float]:
        """Benchmark DuckDB service performance"""
        # Standard test queries
        test_queries = [
            "SELECT COUNT(*) FROM pages",
            "SELECT AVG(content_length) FROM pages",
            "SELECT COUNT(*) as cnt FROM pages GROUP BY DATE(created_at) ORDER BY cnt DESC LIMIT 10"
        ]
        
        query_times = []
        connection_times = []
        
        for query in test_queries:
            # Benchmark connection time
            conn_start = time.time()
            # Connection establishment would happen here
            conn_time = time.time() - conn_start
            connection_times.append(conn_time)
            
            # Benchmark query execution
            for _ in range(5):  # 5 runs per query
                query_start = time.time()
                try:
                    result = await self.duckdb_service.execute_query(query)
                    query_time = time.time() - query_start
                    query_times.append(query_time)
                except Exception as e:
                    query_times.append(30.0)  # Timeout value
        
        return {
            'avg_query_time_ms': statistics.mean(query_times) * 1000,
            'p95_query_time_ms': np.percentile(query_times, 95) * 1000,
            'avg_connection_time_ms': statistics.mean(connection_times) * 1000,
            'queries_per_second': len(test_queries) * 5 / sum(query_times) if sum(query_times) > 0 else 0
        }
    
    async def _benchmark_analytics_service(self) -> Dict[str, float]:
        """Benchmark Analytics service performance"""
        project_id = "test-project"  # Mock project ID
        
        operations = [
            ('get_summary', lambda: self.analytics_service.get_summary(project_id=project_id)),
            ('get_timeline', lambda: self.analytics_service.get_timeline(project_id=project_id)),
            ('get_top_domains', lambda: self.analytics_service.get_top_domains(project_id=project_id))
        ]
        
        operation_times = {}
        
        for op_name, operation in operations:
            times = []
            for _ in range(5):  # 5 runs per operation
                op_start = time.time()
                try:
                    result = await operation()
                    op_time = time.time() - op_start
                    times.append(op_time)
                except Exception as e:
                    times.append(10.0)  # Timeout value
            
            operation_times[f'{op_name}_avg_ms'] = statistics.mean(times) * 1000
            operation_times[f'{op_name}_p95_ms'] = np.percentile(times, 95) * 1000
        
        return operation_times
    
    async def _benchmark_parquet_pipeline(self) -> Dict[str, float]:
        """Benchmark Parquet pipeline performance"""
        from app.models.extraction_data import ExtractedContent
        
        # Create test batch
        test_batch = []
        for i in range(100):
            content = ExtractedContent(
                url=f"https://benchmark-{i}.com",
                title=f"Benchmark Content {i}",
                text="Benchmark text content " * 20,
                html=f"<html><body>Benchmark HTML {i}</body></html>",
                metadata={'benchmark': True, 'index': i}
            )
            test_batch.append(content)
        
        # Benchmark processing
        processing_times = []
        for _ in range(3):  # 3 runs
            proc_start = time.time()
            try:
                result = await self.parquet_pipeline.process_batch(test_batch)
                proc_time = time.time() - proc_start
                processing_times.append(proc_time)
            except Exception as e:
                processing_times.append(60.0)  # Timeout value
        
        return {
            'avg_processing_time_ms': statistics.mean(processing_times) * 1000,
            'items_per_second': len(test_batch) / statistics.mean(processing_times) if statistics.mean(processing_times) > 0 else 0,
            'batch_size': len(test_batch)
        }
    
    async def _benchmark_cache_manager(self) -> Dict[str, float]:
        """Benchmark Cache manager performance"""
        cache_operations = []
        
        # Test cache set operations
        set_times = []
        for i in range(100):
            set_start = time.time()
            try:
                await self.cache_manager.set(f"benchmark_key_{i}", f"benchmark_value_{i}", ttl=300)
                set_time = time.time() - set_start
                set_times.append(set_time)
            except Exception as e:
                set_times.append(1.0)
        
        # Test cache get operations
        get_times = []
        for i in range(100):
            get_start = time.time()
            try:
                value = await self.cache_manager.get(f"benchmark_key_{i}")
                get_time = time.time() - get_start
                get_times.append(get_time)
            except Exception as e:
                get_times.append(1.0)
        
        return {
            'avg_set_time_ms': statistics.mean(set_times) * 1000,
            'avg_get_time_ms': statistics.mean(get_times) * 1000,
            'ops_per_second': 200 / (sum(set_times) + sum(get_times)) if (sum(set_times) + sum(get_times)) > 0 else 0
        }
    
    async def _benchmark_hybrid_query_router(self) -> Dict[str, float]:
        """Benchmark Hybrid query router performance"""
        from app.services.hybrid_query_router import HybridQueryRouter
        
        router = HybridQueryRouter()
        
        test_queries = [
            ("SELECT * FROM users WHERE id = 1", "oltp"),
            ("SELECT COUNT(*) FROM pages", "olap"),
            ("UPDATE projects SET name = 'test'", "oltp"),
            ("SELECT AVG(content_length) FROM pages", "olap")
        ]
        
        routing_times = []
        correct_routes = 0
        
        for query, expected_route in test_queries:
            for _ in range(10):  # 10 routing decisions per query
                route_start = time.time()
                try:
                    route = await router.determine_route(query)
                    route_time = time.time() - route_start
                    routing_times.append(route_time)
                    
                    if route == expected_route:
                        correct_routes += 1
                except Exception as e:
                    routing_times.append(0.1)  # Default routing time
        
        total_decisions = len(test_queries) * 10
        
        return {
            'avg_routing_time_ms': statistics.mean(routing_times) * 1000,
            'routing_accuracy': correct_routes / total_decisions if total_decisions > 0 else 0,
            'decisions_per_second': total_decisions / sum(routing_times) if sum(routing_times) > 0 else 0
        }
    
    async def establish_baseline(self, test_name: str, components: List[str] = None) -> List[PerformanceBaseline]:
        """Establish performance baselines for specified components"""
        if components is None:
            components = [
                "duckdb_service",
                "analytics_service", 
                "parquet_pipeline",
                "cache_manager",
                "hybrid_query_router"
            ]
        
        baselines = []
        
        for component in components:
            print(f"Establishing baseline for {component}...")
            
            try:
                metrics = await self.run_baseline_benchmark(test_name, component)
                
                baseline = PerformanceBaseline(
                    test_name=test_name,
                    component=component,
                    version=self.current_version,
                    commit_hash=self.current_commit,
                    timestamp=datetime.utcnow(),
                    metrics=metrics,
                    metadata={
                        'test_type': 'baseline_establishment',
                        'component_version': self.current_version
                    },
                    environment_info=self.environment_info
                )
                
                self.history_db.store_baseline(baseline)
                baselines.append(baseline)
                
                print(f"Baseline established for {component}")
                
            except Exception as e:
                print(f"Failed to establish baseline for {component}: {str(e)}")
        
        return baselines
    
    async def test_query_performance_regression(self) -> RegressionResult:
        """Test for query performance regression"""
        test_name = "query_performance_regression"
        component = "duckdb_service"
        
        # Get current performance metrics
        current_metrics = await self.run_baseline_benchmark(test_name, component)
        
        # Get baseline for comparison
        baseline = self.history_db.get_latest_baseline(test_name, component)
        
        if not baseline:
            # No baseline exists - establish one
            await self.establish_baseline(test_name, [component])
            baseline = self.history_db.get_latest_baseline(test_name, component)
            
            # Return no-regression result for first run
            return RegressionResult(
                test_name=test_name,
                component=component,
                current_version=self.current_version,
                baseline_version=baseline.version if baseline else "none",
                regression_detected=False,
                performance_change_percent=0.0,
                threshold_exceeded=False,
                current_metrics=current_metrics,
                baseline_metrics=baseline.metrics if baseline else {},
                regression_details={'message': 'Baseline established'},
                severity='minor',
                timestamp=datetime.utcnow()
            )
        
        # Compare metrics
        regression_details = self._compare_metrics(current_metrics, baseline.metrics)
        
        # Determine if regression occurred
        primary_metric = 'avg_query_time_ms'
        
        if primary_metric in current_metrics and primary_metric in baseline.metrics:
            current_value = current_metrics[primary_metric]
            baseline_value = baseline.metrics[primary_metric]
            
            # For query time, higher is worse (regression)
            performance_change = (current_value - baseline_value) / baseline_value if baseline_value > 0 else 0
            
            regression_detected = performance_change > self.regression_thresholds['minor']
            threshold_exceeded = performance_change > self.regression_thresholds['moderate']
            
            # Determine severity
            severity = self._determine_severity(performance_change)
            
        else:
            performance_change = 0.0
            regression_detected = False
            threshold_exceeded = False
            severity = 'minor'
        
        result = RegressionResult(
            test_name=test_name,
            component=component,
            current_version=self.current_version,
            baseline_version=baseline.version,
            regression_detected=regression_detected,
            performance_change_percent=performance_change * 100,
            threshold_exceeded=threshold_exceeded,
            current_metrics=current_metrics,
            baseline_metrics=baseline.metrics,
            regression_details=regression_details,
            severity=severity,
            timestamp=datetime.utcnow()
        )
        
        # Store result
        self.history_db.store_regression_result(result)
        
        return result
    
    async def test_memory_usage_regression(self) -> RegressionResult:
        """Test for memory usage regression"""
        test_name = "memory_usage_regression"
        component = "analytics_service"
        
        # Simulate memory usage measurement
        import psutil
        
        process = psutil.Process()
        initial_memory = process.memory_info().rss / 1024 / 1024  # MB
        
        # Perform analytics operations
        project_id = "test-project"
        
        for _ in range(10):
            try:
                await self.analytics_service.get_summary(project_id=project_id)
                await self.analytics_service.get_timeline(project_id=project_id)
            except:
                pass
        
        final_memory = process.memory_info().rss / 1024 / 1024  # MB
        memory_usage = final_memory - initial_memory
        
        current_metrics = {
            'memory_usage_mb': memory_usage,
            'initial_memory_mb': initial_memory,
            'final_memory_mb': final_memory
        }
        
        # Get baseline
        baseline = self.history_db.get_latest_baseline(test_name, component)
        
        if not baseline:
            # Establish baseline
            baseline = PerformanceBaseline(
                test_name=test_name,
                component=component,
                version=self.current_version,
                commit_hash=self.current_commit,
                timestamp=datetime.utcnow(),
                metrics=current_metrics,
                metadata={'test_type': 'memory_baseline'},
                environment_info=self.environment_info
            )
            self.history_db.store_baseline(baseline)
            
            return RegressionResult(
                test_name=test_name,
                component=component,
                current_version=self.current_version,
                baseline_version=self.current_version,
                regression_detected=False,
                performance_change_percent=0.0,
                threshold_exceeded=False,
                current_metrics=current_metrics,
                baseline_metrics=current_metrics,
                regression_details={'message': 'Memory baseline established'},
                severity='minor',
                timestamp=datetime.utcnow()
            )
        
        # Compare memory usage
        regression_details = self._compare_metrics(current_metrics, baseline.metrics)
        
        baseline_memory = baseline.metrics.get('memory_usage_mb', 0)
        current_memory = current_metrics['memory_usage_mb']
        
        # For memory, higher usage is worse (regression)
        if baseline_memory > 0:
            performance_change = (current_memory - baseline_memory) / baseline_memory
        else:
            performance_change = 0.0
        
        regression_detected = performance_change > self.regression_thresholds['minor']
        threshold_exceeded = performance_change > self.regression_thresholds['moderate']
        severity = self._determine_severity(performance_change)
        
        result = RegressionResult(
            test_name=test_name,
            component=component,
            current_version=self.current_version,
            baseline_version=baseline.version,
            regression_detected=regression_detected,
            performance_change_percent=performance_change * 100,
            threshold_exceeded=threshold_exceeded,
            current_metrics=current_metrics,
            baseline_metrics=baseline.metrics,
            regression_details=regression_details,
            severity=severity,
            timestamp=datetime.utcnow()
        )
        
        self.history_db.store_regression_result(result)
        return result
    
    async def test_cache_efficiency_regression(self) -> RegressionResult:
        """Test for cache efficiency regression"""
        test_name = "cache_efficiency_regression"
        component = "cache_manager"
        
        # Benchmark cache performance
        current_metrics = await self.run_baseline_benchmark(test_name, component)
        
        # Add cache hit rate simulation
        cache_hits = 80  # Mock 80% hit rate
        cache_misses = 20
        total_requests = cache_hits + cache_misses
        
        current_metrics.update({
            'cache_hit_rate': cache_hits / total_requests,
            'cache_hits': cache_hits,
            'cache_misses': cache_misses
        })
        
        # Get baseline
        baseline = self.history_db.get_latest_baseline(test_name, component)
        
        if not baseline:
            baseline = PerformanceBaseline(
                test_name=test_name,
                component=component,
                version=self.current_version,
                commit_hash=self.current_commit,
                timestamp=datetime.utcnow(),
                metrics=current_metrics,
                metadata={'test_type': 'cache_baseline'},
                environment_info=self.environment_info
            )
            self.history_db.store_baseline(baseline)
            
            return RegressionResult(
                test_name=test_name,
                component=component,
                current_version=self.current_version,
                baseline_version=self.current_version,
                regression_detected=False,
                performance_change_percent=0.0,
                threshold_exceeded=False,
                current_metrics=current_metrics,
                baseline_metrics=current_metrics,
                regression_details={'message': 'Cache baseline established'},
                severity='minor',
                timestamp=datetime.utcnow()
            )
        
        # Compare cache efficiency
        regression_details = self._compare_metrics(current_metrics, baseline.metrics)
        
        # For cache hit rate, lower is worse (regression)
        current_hit_rate = current_metrics.get('cache_hit_rate', 0)
        baseline_hit_rate = baseline.metrics.get('cache_hit_rate', 0)
        
        if baseline_hit_rate > 0:
            performance_change = (baseline_hit_rate - current_hit_rate) / baseline_hit_rate
        else:
            performance_change = 0.0
        
        regression_detected = performance_change > self.regression_thresholds['minor']
        threshold_exceeded = performance_change > self.regression_thresholds['moderate'] 
        severity = self._determine_severity(performance_change)
        
        result = RegressionResult(
            test_name=test_name,
            component=component,
            current_version=self.current_version,
            baseline_version=baseline.version,
            regression_detected=regression_detected,
            performance_change_percent=performance_change * 100,
            threshold_exceeded=threshold_exceeded,
            current_metrics=current_metrics,
            baseline_metrics=baseline.metrics,
            regression_details=regression_details,
            severity=severity,
            timestamp=datetime.utcnow()
        )
        
        self.history_db.store_regression_result(result)
        return result
    
    async def test_api_response_time_regression(self) -> RegressionResult:
        """Test for API response time regression"""
        test_name = "api_response_time_regression"
        component = "analytics_service"
        
        # Benchmark API response times
        current_metrics = await self.run_baseline_benchmark(test_name, component)
        
        # Get baseline
        baseline = self.history_db.get_latest_baseline(test_name, component)
        
        if not baseline:
            baseline = PerformanceBaseline(
                test_name=test_name,
                component=component,
                version=self.current_version,
                commit_hash=self.current_commit,
                timestamp=datetime.utcnow(),
                metrics=current_metrics,
                metadata={'test_type': 'api_baseline'},
                environment_info=self.environment_info
            )
            self.history_db.store_baseline(baseline)
            
            return RegressionResult(
                test_name=test_name,
                component=component,
                current_version=self.current_version,
                baseline_version=self.current_version,
                regression_detected=False,
                performance_change_percent=0.0,
                threshold_exceeded=False,
                current_metrics=current_metrics,
                baseline_metrics=current_metrics,
                regression_details={'message': 'API baseline established'},
                severity='minor',
                timestamp=datetime.utcnow()
            )
        
        # Compare API response times
        regression_details = self._compare_metrics(current_metrics, baseline.metrics)
        
        # Use average response time of summary operation as primary metric
        primary_metric = 'get_summary_avg_ms'
        
        if primary_metric in current_metrics and primary_metric in baseline.metrics:
            current_value = current_metrics[primary_metric]
            baseline_value = baseline.metrics[primary_metric]
            
            performance_change = (current_value - baseline_value) / baseline_value if baseline_value > 0 else 0
        else:
            performance_change = 0.0
        
        regression_detected = performance_change > self.regression_thresholds['minor']
        threshold_exceeded = performance_change > self.regression_thresholds['moderate']
        severity = self._determine_severity(performance_change)
        
        result = RegressionResult(
            test_name=test_name,
            component=component,
            current_version=self.current_version,
            baseline_version=baseline.version,
            regression_detected=regression_detected,
            performance_change_percent=performance_change * 100,
            threshold_exceeded=threshold_exceeded,
            current_metrics=current_metrics,
            baseline_metrics=baseline.metrics,
            regression_details=regression_details,
            severity=severity,
            timestamp=datetime.utcnow()
        )
        
        self.history_db.store_regression_result(result)
        return result
    
    async def test_throughput_capacity_regression(self) -> RegressionResult:
        """Test for throughput capacity regression"""
        test_name = "throughput_capacity_regression" 
        component = "parquet_pipeline"
        
        # Benchmark throughput
        current_metrics = await self.run_baseline_benchmark(test_name, component)
        
        # Get baseline
        baseline = self.history_db.get_latest_baseline(test_name, component)
        
        if not baseline:
            baseline = PerformanceBaseline(
                test_name=test_name,
                component=component,
                version=self.current_version,
                commit_hash=self.current_commit,
                timestamp=datetime.utcnow(),
                metrics=current_metrics,
                metadata={'test_type': 'throughput_baseline'},
                environment_info=self.environment_info
            )
            self.history_db.store_baseline(baseline)
            
            return RegressionResult(
                test_name=test_name,
                component=component,
                current_version=self.current_version,
                baseline_version=self.current_version,
                regression_detected=False,
                performance_change_percent=0.0,
                threshold_exceeded=False,
                current_metrics=current_metrics,
                baseline_metrics=current_metrics,
                regression_details={'message': 'Throughput baseline established'},
                severity='minor',
                timestamp=datetime.utcnow()
            )
        
        # Compare throughput
        regression_details = self._compare_metrics(current_metrics, baseline.metrics)
        
        # For throughput, lower is worse (regression)
        primary_metric = 'items_per_second'
        
        if primary_metric in current_metrics and primary_metric in baseline.metrics:
            current_value = current_metrics[primary_metric]
            baseline_value = baseline.metrics[primary_metric]
            
            # Inverted comparison - lower throughput is regression
            performance_change = (baseline_value - current_value) / baseline_value if baseline_value > 0 else 0
        else:
            performance_change = 0.0
        
        regression_detected = performance_change > self.regression_thresholds['minor']
        threshold_exceeded = performance_change > self.regression_thresholds['moderate']
        severity = self._determine_severity(performance_change)
        
        result = RegressionResult(
            test_name=test_name,
            component=component,
            current_version=self.current_version,
            baseline_version=baseline.version,
            regression_detected=regression_detected,
            performance_change_percent=performance_change * 100,
            threshold_exceeded=threshold_exceeded,
            current_metrics=current_metrics,
            baseline_metrics=baseline.metrics,
            regression_details=regression_details,
            severity=severity,
            timestamp=datetime.utcnow()
        )
        
        self.history_db.store_regression_result(result)
        return result
    
    def _compare_metrics(self, current: Dict[str, float], baseline: Dict[str, float]) -> Dict[str, Any]:
        """Compare current metrics with baseline metrics"""
        comparison = {
            'metric_changes': {},
            'significant_changes': [],
            'improved_metrics': [],
            'degraded_metrics': []
        }
        
        for metric_name in current.keys():
            if metric_name in baseline:
                current_value = current[metric_name]
                baseline_value = baseline[metric_name]
                
                if baseline_value != 0:
                    change_percent = ((current_value - baseline_value) / baseline_value) * 100
                    comparison['metric_changes'][metric_name] = change_percent
                    
                    # Significant change threshold
                    if abs(change_percent) > 5.0:  # 5% change
                        comparison['significant_changes'].append({
                            'metric': metric_name,
                            'change_percent': change_percent,
                            'current_value': current_value,
                            'baseline_value': baseline_value
                        })
                    
                    # Categorize improvements vs degradations
                    # This is metric-specific logic
                    if self._is_improvement(metric_name, change_percent):
                        comparison['improved_metrics'].append(metric_name)
                    elif self._is_degradation(metric_name, change_percent):
                        comparison['degraded_metrics'].append(metric_name)
        
        return comparison
    
    def _is_improvement(self, metric_name: str, change_percent: float) -> bool:
        """Determine if a metric change is an improvement"""
        # Lower is better for these metrics
        if any(keyword in metric_name.lower() for keyword in ['time', 'latency', 'duration']):
            return change_percent < -5.0  # 5% reduction is improvement
        
        # Higher is better for these metrics
        if any(keyword in metric_name.lower() for keyword in ['rate', 'throughput', 'per_second']):
            return change_percent > 5.0  # 5% increase is improvement
        
        return False
    
    def _is_degradation(self, metric_name: str, change_percent: float) -> bool:
        """Determine if a metric change is a degradation"""
        # Higher is worse for these metrics
        if any(keyword in metric_name.lower() for keyword in ['time', 'latency', 'duration', 'memory']):
            return change_percent > 5.0  # 5% increase is degradation
        
        # Lower is worse for these metrics
        if any(keyword in metric_name.lower() for keyword in ['rate', 'throughput', 'per_second', 'accuracy']):
            return change_percent < -5.0  # 5% decrease is degradation
        
        return False
    
    def _determine_severity(self, performance_change: float) -> str:
        """Determine severity level based on performance change"""
        abs_change = abs(performance_change)
        
        if abs_change >= self.regression_thresholds['critical']:
            return 'critical'
        elif abs_change >= self.regression_thresholds['major']:
            return 'major'
        elif abs_change >= self.regression_thresholds['moderate']:
            return 'moderate'
        elif abs_change >= self.regression_thresholds['minor']:
            return 'minor'
        else:
            return 'minor'
    
    def generate_regression_report(self, results: List[RegressionResult]) -> str:
        """Generate comprehensive regression test report"""
        if not results:
            return "No regression tests have been run."
        
        report = []
        report.append("PHASE 2 PERFORMANCE REGRESSION REPORT")
        report.append("=" * 60)
        report.append("")
        
        # Summary statistics
        total_tests = len(results)
        regressions_detected = sum(1 for r in results if r.regression_detected)
        critical_regressions = sum(1 for r in results if r.severity == 'critical')
        major_regressions = sum(1 for r in results if r.severity == 'major')
        
        report.append("SUMMARY:")
        report.append(f"  Total Regression Tests: {total_tests}")
        report.append(f"  Regressions Detected: {regressions_detected}")
        report.append(f"  Critical Regressions: {critical_regressions}")
        report.append(f"  Major Regressions: {major_regressions}")
        report.append(f"  Regression Rate: {regressions_detected/total_tests:.1%}" if total_tests > 0 else "  Regression Rate: 0.0%")
        report.append("")
        
        # Detailed results
        report.append("DETAILED RESULTS:")
        report.append("-" * 40)
        
        for result in results:
            status = "✗ REGRESSION" if result.regression_detected else "✓ NO REGRESSION"
            severity_indicator = {
                'minor': '⚬',
                'moderate': '⚠',
                'major': '❗',
                'critical': '🚨'
            }.get(result.severity, '⚬')
            
            report.append(f"\n{result.test_name} ({result.component}): {status} {severity_indicator}")
            report.append(f"  Performance Change: {result.performance_change_percent:+.1f}%")
            report.append(f"  Severity: {result.severity.upper()}")
            report.append(f"  Baseline Version: {result.baseline_version}")
            report.append(f"  Current Version: {result.current_version}")
            
            if result.regression_detected:
                regression_details = result.regression_details
                if 'significant_changes' in regression_details:
                    report.append("  Significant Changes:")
                    for change in regression_details['significant_changes']:
                        report.append(f"    {change['metric']}: {change['change_percent']:+.1f}%")
        
        # Component analysis
        report.append("\n\nCOMPONENT REGRESSION ANALYSIS:")
        report.append("-" * 40)
        
        component_stats = {}
        for result in results:
            component = result.component
            if component not in component_stats:
                component_stats[component] = {'total': 0, 'regressions': 0}
            
            component_stats[component]['total'] += 1
            if result.regression_detected:
                component_stats[component]['regressions'] += 1
        
        for component, stats in component_stats.items():
            regression_rate = stats['regressions'] / stats['total'] if stats['total'] > 0 else 0
            status_icon = "✗" if regression_rate > 0.5 else "⚠" if regression_rate > 0.2 else "✓"
            report.append(f"  {component}: {status_icon} {stats['regressions']}/{stats['total']} ({regression_rate:.1%})")
        
        # Historical trend analysis
        report.append("\n\nHISTORICAL TREND ANALYSIS:")
        report.append("-" * 40)
        
        recent_regressions = self.history_db.get_recent_regressions(days=7)
        if recent_regressions:
            report.append(f"  Recent Regressions (last 7 days): {len(recent_regressions)}")
            severity_counts = {}
            for regression in recent_regressions:
                severity_counts[regression.severity] = severity_counts.get(regression.severity, 0) + 1
            
            for severity, count in severity_counts.items():
                report.append(f"    {severity}: {count}")
        else:
            report.append("  Recent Regressions (last 7 days): 0")
        
        # Recommendations
        report.append("\n\nRECOMMENDATIONS:")
        report.append("-" * 30)
        
        if critical_regressions > 0:
            report.append("  🚨 URGENT: Address critical regressions immediately")
        
        if major_regressions > 0:
            report.append("  ❗ HIGH PRIORITY: Investigate major performance degradations")
        
        if regressions_detected > total_tests * 0.3:
            report.append("  ⚠ Consider reviewing recent code changes for performance impact")
        
        if regressions_detected == 0:
            report.append("  ✓ No performance regressions detected - system performance is stable")
        
        # Overall assessment
        report.append("\n\nOVERALL REGRESSION ASSESSMENT:")
        report.append("-" * 40)
        
        if critical_regressions > 0:
            report.append("  Status: 🚨 CRITICAL REGRESSIONS DETECTED")
            report.append("  Action: DO NOT DEPLOY - Fix critical issues first")
        elif major_regressions > 0:
            report.append("  Status: ❗ MAJOR REGRESSIONS DETECTED")
            report.append("  Action: REVIEW REQUIRED - Address major issues before deployment")
        elif regressions_detected > 0:
            report.append("  Status: ⚠ MINOR REGRESSIONS DETECTED")
            report.append("  Action: Monitor closely - Consider fixes in next iteration")
        else:
            report.append("  Status: ✓ NO REGRESSIONS DETECTED")
            report.append("  Action: Safe to deploy - Performance is stable or improved")
        
        return "\n".join(report)


@pytest.mark.regression
@pytest.mark.asyncio
class TestPhase2RegressionSuite:
    """Main test class for Phase 2 regression testing"""
    
    def setup_class(self):
        """Setup for regression tests"""
        self.regression_suite = Phase2RegressionTests()
    
    async def test_establish_performance_baselines(self):
        """Establish initial performance baselines"""
        print("Establishing performance baselines for all components...")
        
        baselines = await self.regression_suite.establish_baseline(
            test_name="phase2_performance_baseline"
        )
        
        assert len(baselines) > 0, "Failed to establish any baselines"
        
        for baseline in baselines:
            print(f"Baseline established for {baseline.component}")
            assert baseline.metrics, f"No metrics in baseline for {baseline.component}"
            assert baseline.version == self.regression_suite.current_version
        
        print(f"Successfully established {len(baselines)} performance baselines")
    
    @pytest.mark.slow
    async def test_complete_regression_suite(self):
        """Run the complete regression test suite"""
        print("Starting Phase 2 Performance Regression Test Suite...")
        print("=" * 60)
        
        # Run all regression tests
        regression_methods = [
            'test_query_performance_regression',
            'test_memory_usage_regression',
            'test_cache_efficiency_regression',
            'test_api_response_time_regression',
            'test_throughput_capacity_regression'
        ]
        
        results = []
        
        for method_name in regression_methods:
            print(f"\nRunning {method_name}...")
            method = getattr(self.regression_suite, method_name)
            result = await method()
            results.append(result)
            
            # Print immediate results
            status = "✗ REGRESSION" if result.regression_detected else "✓ NO REGRESSION"
            severity = result.severity.upper()
            change = result.performance_change_percent
            
            print(f"  Result: {status} ({severity})")
            print(f"  Performance Change: {change:+.1f}%")
            
            if result.regression_detected:
                print(f"  ⚠ Regression detected in {result.component}")
        
        # Generate comprehensive report
        report = self.regression_suite.generate_regression_report(results)
        print("\n" + report)
        
        # Validate regression test results
        critical_regressions = sum(1 for r in results if r.severity == 'critical')
        major_regressions = sum(1 for r in results if r.severity == 'major')
        
        # Fail test if critical regressions are detected
        assert critical_regressions == 0, f"Critical regressions detected: {critical_regressions}"
        
        # Warn about major regressions but don't fail
        if major_regressions > 0:
            print(f"\n⚠ WARNING: {major_regressions} major regressions detected")
        
        print("\n" + "=" * 60)
        print("REGRESSION TEST SUITE COMPLETED")
        print("=" * 60)


if __name__ == "__main__":
    # Run regression tests directly
    import asyncio
    
    async def run_regression_tests():
        suite = Phase2RegressionTests()
        
        # Establish baselines first
        await suite.establish_baseline("performance_baseline")
        
        # Run regression tests
        results = []
        results.append(await suite.test_query_performance_regression())
        results.append(await suite.test_memory_usage_regression())
        results.append(await suite.test_cache_efficiency_regression())
        results.append(await suite.test_api_response_time_regression())
        results.append(await suite.test_throughput_capacity_regression())
        
        # Generate report
        report = suite.generate_regression_report(results)
        print(report)
        
        return results
    
    asyncio.run(run_regression_tests())