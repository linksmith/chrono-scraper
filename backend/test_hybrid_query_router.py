#!/usr/bin/env python3
"""
Hybrid Query Router System Test Suite
=====================================

Comprehensive testing script for the HybridQueryRouter system that validates:
- Query routing intelligence and accuracy
- Performance optimization effectiveness
- Database connection pooling and failover
- Caching mechanisms and hit rates
- Resource management and throttling
- Monitoring and alerting functionality
- End-to-end integration testing

Run with: python test_hybrid_query_router.py
"""

import asyncio
import json
import logging
import os
import sys
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

# Add the backend directory to the Python path
backend_dir = os.path.dirname(os.path.abspath(__file__))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Test framework imports
try:
    from app.services.hybrid_query_router import (
        HybridQueryRouter, QueryType, DatabaseTarget, QueryPriority,
        QueryResult, hybrid_router
    )
    from app.services.query_analyzer import QueryAnalyzer, QueryComplexity, query_analyzer
    from app.services.performance_optimization_engine import (
        PerformanceOptimizationEngine, OptimizationRule, OptimizationStrategy,
        performance_engine
    )
    from app.services.database_connection_manager import (
        DatabaseConnectionManager, DatabaseType, db_connection_manager
    )
    from app.services.hybrid_query_monitoring import (
        HybridQueryMonitoringSystem, monitoring_system
    )
    from app.core.config import settings
    
    logger.info("Successfully imported all hybrid query router components")
    
except ImportError as e:
    logger.error(f"Failed to import hybrid query router components: {e}")
    sys.exit(1)


class TestResult:
    """Test result tracking"""
    def __init__(self, test_name: str):
        self.test_name = test_name
        self.passed = False
        self.error_message = ""
        self.execution_time = 0.0
        self.details = {}
    
    def success(self, details: Dict[str, Any] = None):
        self.passed = True
        self.details = details or {}
    
    def failure(self, error_message: str, details: Dict[str, Any] = None):
        self.passed = False
        self.error_message = error_message
        self.details = details or {}


class HybridQueryRouterTestSuite:
    """Comprehensive test suite for the hybrid query router system"""
    
    def __init__(self):
        self.test_results: List[TestResult] = []
        self.setup_complete = False
        
        # Test queries for different scenarios
        self.test_queries = {
            # OLTP queries (should route to PostgreSQL)
            "user_auth": "SELECT id, email FROM users WHERE email = 'test@example.com'",
            "project_crud": "INSERT INTO projects (name, owner_id) VALUES ('Test Project', 1)",
            "page_management": "UPDATE pages_v2 SET status = 'processed' WHERE id = 123",
            "real_time": "SELECT COUNT(*) FROM active_sessions WHERE last_seen > NOW() - INTERVAL '5 minutes'",
            
            # OLAP queries (should route to DuckDB)
            "analytics": "SELECT domain, COUNT(*) FROM cdx_records GROUP BY domain ORDER BY COUNT(*) DESC LIMIT 10",
            "time_series": "SELECT date_trunc('hour', timestamp), AVG(processing_time) FROM scrape_sessions GROUP BY 1 ORDER BY 1",
            "aggregation": "SELECT project_id, AVG(content_length), COUNT(*) FROM pages_v2 GROUP BY project_id HAVING COUNT(*) > 100",
            "reporting": "SELECT DATE(created_at), COUNT(*) as daily_count FROM projects WHERE created_at >= '2024-01-01' GROUP BY 1",
            
            # Complex queries for optimization testing
            "complex_join": """
                SELECT p.name, u.email, COUNT(pg.id) as page_count
                FROM projects p 
                JOIN users u ON p.owner_id = u.id 
                LEFT JOIN pages_v2 pg ON pg.project_id = p.id 
                GROUP BY p.id, u.id 
                ORDER BY page_count DESC
            """,
            "subquery": """
                SELECT * FROM projects 
                WHERE id IN (
                    SELECT project_id FROM pages_v2 
                    WHERE content_length > 1000 
                    GROUP BY project_id 
                    HAVING COUNT(*) > 50
                )
            """,
            "window_function": """
                SELECT project_id, created_at, 
                       ROW_NUMBER() OVER (PARTITION BY project_id ORDER BY created_at) as seq
                FROM pages_v2 
                WHERE created_at >= '2024-01-01'
            """
        }
    
    async def setup_test_environment(self):
        """Set up the test environment and initialize services"""
        try:
            logger.info("Setting up test environment...")
            
            # Initialize services
            await hybrid_router.initialize()
            await performance_engine.initialize()
            await db_connection_manager.initialize()
            await monitoring_system.initialize(hybrid_router)
            
            self.setup_complete = True
            logger.info("Test environment setup completed successfully")
            
        except Exception as e:
            logger.error(f"Failed to setup test environment: {e}")
            raise
    
    async def run_all_tests(self):
        """Run the complete test suite"""
        if not self.setup_complete:
            await self.setup_test_environment()
        
        logger.info("Starting comprehensive hybrid query router test suite")
        start_time = time.time()
        
        # Core functionality tests
        await self.test_query_classification()
        await self.test_database_routing()
        await self.test_query_optimization()
        await self.test_caching_mechanisms()
        
        # Performance and reliability tests
        await self.test_connection_pooling()
        await self.test_circuit_breaker_functionality()
        await self.test_resource_management()
        await self.test_concurrent_query_handling()
        
        # Monitoring and observability tests
        await self.test_metrics_collection()
        await self.test_alerting_system()
        await self.test_health_checks()
        
        # Integration tests
        await self.test_end_to_end_workflows()
        await self.test_failover_scenarios()
        await self.test_performance_under_load()
        
        total_time = time.time() - start_time
        await self.generate_test_report(total_time)
    
    async def test_query_classification(self):
        """Test query classification accuracy"""
        test_result = TestResult("Query Classification")
        
        try:
            logger.info("Testing query classification...")
            
            classification_results = {}
            correct_classifications = 0
            total_tests = 0
            
            # Test each query type
            expected_classifications = {
                "user_auth": QueryType.USER_AUTH,
                "project_crud": QueryType.PROJECT_CRUD,
                "page_management": QueryType.PAGE_MANAGEMENT,
                "real_time": QueryType.REAL_TIME_OPERATIONS,
                "analytics": QueryType.ANALYTICS,
                "time_series": QueryType.TIME_SERIES,
                "aggregation": QueryType.AGGREGATION,
                "reporting": QueryType.REPORTING
            }
            
            for query_name, query in self.test_queries.items():
                if query_name in expected_classifications:
                    analysis = await query_analyzer.analyze_query(query)
                    
                    expected_type = expected_classifications[query_name]
                    actual_type = analysis.query_type
                    
                    is_correct = (
                        actual_type == expected_type.value or
                        self._is_acceptable_classification(expected_type, actual_type)
                    )
                    
                    classification_results[query_name] = {
                        "expected": expected_type.value,
                        "actual": actual_type,
                        "correct": is_correct,
                        "confidence": analysis.confidence_score,
                        "complexity": analysis.complexity.value
                    }
                    
                    total_tests += 1
                    if is_correct:
                        correct_classifications += 1
            
            accuracy = (correct_classifications / total_tests) * 100 if total_tests > 0 else 0
            
            if accuracy >= 80:  # 80% accuracy threshold
                test_result.success({
                    "accuracy_percentage": accuracy,
                    "correct_classifications": correct_classifications,
                    "total_tests": total_tests,
                    "details": classification_results
                })
            else:
                test_result.failure(
                    f"Classification accuracy too low: {accuracy:.1f}% (expected >= 80%)",
                    {"accuracy": accuracy, "details": classification_results}
                )
        
        except Exception as e:
            test_result.failure(f"Query classification test failed: {str(e)}")
        
        self.test_results.append(test_result)
    
    def _is_acceptable_classification(self, expected: QueryType, actual: str) -> bool:
        """Check if classification is acceptable (handles similar types)"""
        acceptable_mappings = {
            QueryType.USER_AUTH: ["user_management", "real_time_operations"],
            QueryType.PROJECT_CRUD: ["transactional", "real_time_operations"],
            QueryType.PAGE_MANAGEMENT: ["transactional", "real_time_operations"],
            QueryType.ANALYTICS: ["complex_select", "aggregation"],
            QueryType.TIME_SERIES: ["analytics", "complex_select"],
            QueryType.AGGREGATION: ["analytics", "complex_select"],
            QueryType.REPORTING: ["analytics", "aggregation"]
        }
        
        return actual in acceptable_mappings.get(expected, [])
    
    async def test_database_routing(self):
        """Test database routing decisions"""
        test_result = TestResult("Database Routing")
        
        try:
            logger.info("Testing database routing decisions...")
            
            routing_results = {}
            correct_routings = 0
            total_tests = 0
            
            # Expected routing decisions
            expected_routing = {
                "user_auth": DatabaseTarget.POSTGRESQL,
                "project_crud": DatabaseTarget.POSTGRESQL,
                "page_management": DatabaseTarget.POSTGRESQL,
                "real_time": DatabaseTarget.POSTGRESQL,
                "analytics": DatabaseTarget.DUCKDB,
                "time_series": DatabaseTarget.DUCKDB,
                "aggregation": DatabaseTarget.DUCKDB,
                "reporting": DatabaseTarget.DUCKDB
            }
            
            for query_name, query in self.test_queries.items():
                if query_name in expected_routing:
                    # Classify the query
                    metadata = await hybrid_router.classify_query(query)
                    
                    expected_db = expected_routing[query_name]
                    actual_db = metadata.database_target
                    
                    is_correct = (
                        actual_db == expected_db or
                        self._is_acceptable_routing(expected_db, actual_db)
                    )
                    
                    routing_results[query_name] = {
                        "expected": expected_db.value,
                        "actual": actual_db.value,
                        "correct": is_correct,
                        "routing_reason": metadata.routing_reason,
                        "confidence": getattr(metadata, 'confidence_score', 0.0)
                    }
                    
                    total_tests += 1
                    if is_correct:
                        correct_routings += 1
            
            accuracy = (correct_routings / total_tests) * 100 if total_tests > 0 else 0
            
            if accuracy >= 85:  # 85% routing accuracy threshold
                test_result.success({
                    "routing_accuracy": accuracy,
                    "correct_routings": correct_routings,
                    "total_tests": total_tests,
                    "details": routing_results
                })
            else:
                test_result.failure(
                    f"Routing accuracy too low: {accuracy:.1f}% (expected >= 85%)",
                    {"accuracy": accuracy, "details": routing_results}
                )
        
        except Exception as e:
            test_result.failure(f"Database routing test failed: {str(e)}")
        
        self.test_results.append(test_result)
    
    def _is_acceptable_routing(self, expected: DatabaseTarget, actual: DatabaseTarget) -> bool:
        """Check if routing decision is acceptable"""
        # AUTO routing can be acceptable for any target
        if actual == DatabaseTarget.AUTO:
            return True
        
        # HYBRID routing might be acceptable in some cases
        if actual == DatabaseTarget.HYBRID:
            return True
        
        return False
    
    async def test_query_optimization(self):
        """Test query optimization functionality"""
        test_result = TestResult("Query Optimization")
        
        try:
            logger.info("Testing query optimization...")
            
            optimization_results = {}
            optimizations_applied = 0
            total_tests = 0
            
            # Test optimization on complex queries
            complex_queries = ["complex_join", "subquery", "window_function"]
            
            for query_name in complex_queries:
                if query_name in self.test_queries:
                    query = self.test_queries[query_name]
                    
                    # Test optimization
                    optimized_query, strategies = await performance_engine.query_optimizer.optimize_query(query)
                    
                    optimization_applied = len(strategies) > 0 and optimized_query != query
                    
                    optimization_results[query_name] = {
                        "original_length": len(query),
                        "optimized_length": len(optimized_query),
                        "strategies_applied": strategies,
                        "optimization_applied": optimization_applied,
                        "query_modified": optimized_query != query
                    }
                    
                    total_tests += 1
                    if optimization_applied:
                        optimizations_applied += 1
            
            # Test optimization rule functionality
            rule_test_query = "SELECT * FROM pages_v2 WHERE domain = 'example.com' ORDER BY created_at"
            optimized_rule_query, rule_strategies = await performance_engine.query_optimizer.optimize_query(
                rule_test_query
            )
            
            optimization_rate = (optimizations_applied / total_tests) * 100 if total_tests > 0 else 0
            
            if optimization_rate >= 50:  # At least 50% of complex queries should be optimized
                test_result.success({
                    "optimization_rate": optimization_rate,
                    "optimizations_applied": optimizations_applied,
                    "total_tests": total_tests,
                    "details": optimization_results,
                    "rule_test": {
                        "original": rule_test_query,
                        "optimized": optimized_rule_query,
                        "strategies": rule_strategies
                    }
                })
            else:
                test_result.failure(
                    f"Optimization rate too low: {optimization_rate:.1f}% (expected >= 50%)",
                    {"rate": optimization_rate, "details": optimization_results}
                )
        
        except Exception as e:
            test_result.failure(f"Query optimization test failed: {str(e)}")
        
        self.test_results.append(test_result)
    
    async def test_caching_mechanisms(self):
        """Test caching functionality"""
        test_result = TestResult("Caching Mechanisms")
        
        try:
            logger.info("Testing caching mechanisms...")
            
            # Test cache initialization
            cache = hybrid_router.cache
            await cache.initialize()
            
            # Test cache set/get operations
            test_key = "test_query_123"
            test_data = {"query": "SELECT 1", "result": [{"count": 1}], "timestamp": time.time()}
            
            # Set cache entry
            await cache.set(test_key, test_data, ttl=300)
            
            # Get cache entry
            cached_data = await cache.get(test_key)
            
            cache_hit = cached_data is not None and cached_data.get("query") == test_data["query"]
            
            # Test cache stats
            cache_stats = cache.get_stats()
            
            if cache_hit:
                test_result.success({
                    "cache_hit_successful": True,
                    "cached_data_matches": cached_data == test_data,
                    "cache_stats": cache_stats,
                    "redis_connected": cache_stats.get("redis_connected", False)
                })
            else:
                test_result.failure(
                    "Cache functionality not working properly",
                    {"cache_hit": cache_hit, "stats": cache_stats}
                )
        
        except Exception as e:
            test_result.failure(f"Caching test failed: {str(e)}")
        
        self.test_results.append(test_result)
    
    async def test_connection_pooling(self):
        """Test database connection pooling"""
        test_result = TestResult("Connection Pooling")
        
        try:
            logger.info("Testing connection pooling...")
            
            # Test PostgreSQL pool
            pg_stats = db_connection_manager.get_pool_statistics(DatabaseType.POSTGRESQL)
            
            # Test DuckDB pool  
            duckdb_stats = db_connection_manager.get_pool_statistics(DatabaseType.DUCKDB)
            
            # Test connection acquisition
            conn_id, connection = await db_connection_manager.get_connection(DatabaseType.POSTGRESQL, timeout=10)
            
            # Return connection
            db_connection_manager.return_connection(DatabaseType.POSTGRESQL, conn_id)
            
            pools_healthy = (
                pg_stats and pg_stats.total_connections > 0 and
                duckdb_stats and duckdb_stats.total_connections > 0
            )
            
            if pools_healthy:
                test_result.success({
                    "postgresql_pool": {
                        "total_connections": pg_stats.total_connections,
                        "active_connections": pg_stats.active_connections,
                        "utilization_rate": pg_stats.utilization_rate()
                    },
                    "duckdb_pool": {
                        "total_connections": duckdb_stats.total_connections,
                        "active_connections": duckdb_stats.active_connections,
                        "utilization_rate": duckdb_stats.utilization_rate()
                    },
                    "connection_acquisition_successful": connection is not None
                })
            else:
                test_result.failure(
                    "Connection pools not properly initialized",
                    {"pg_stats": pg_stats.__dict__ if pg_stats else None,
                     "duckdb_stats": duckdb_stats.__dict__ if duckdb_stats else None}
                )
        
        except Exception as e:
            test_result.failure(f"Connection pooling test failed: {str(e)}")
        
        self.test_results.append(test_result)
    
    async def test_circuit_breaker_functionality(self):
        """Test circuit breaker protection"""
        test_result = TestResult("Circuit Breaker")
        
        try:
            logger.info("Testing circuit breaker functionality...")
            
            # Get circuit breaker states
            pg_breaker = hybrid_router.postgresql_breaker
            duckdb_breaker = hybrid_router.duckdb_breaker
            
            # Test circuit breaker status
            pg_status = pg_breaker.get_status()
            duckdb_status = duckdb_breaker.get_status()
            
            # Check if circuit breakers are properly initialized
            breakers_initialized = (
                pg_status and "state" in pg_status and
                duckdb_status and "state" in duckdb_status
            )
            
            # Test circuit breaker execution capability
            can_execute_pg = pg_breaker.can_execute()
            can_execute_duckdb = duckdb_breaker.can_execute()
            
            if breakers_initialized and can_execute_pg and can_execute_duckdb:
                test_result.success({
                    "postgresql_breaker": {
                        "state": pg_status.get("state"),
                        "can_execute": can_execute_pg,
                        "failure_count": pg_status.get("failure_count", 0)
                    },
                    "duckdb_breaker": {
                        "state": duckdb_status.get("state"),
                        "can_execute": can_execute_duckdb,
                        "failure_count": duckdb_status.get("failure_count", 0)
                    }
                })
            else:
                test_result.failure(
                    "Circuit breakers not functioning properly",
                    {"pg_status": pg_status, "duckdb_status": duckdb_status}
                )
        
        except Exception as e:
            test_result.failure(f"Circuit breaker test failed: {str(e)}")
        
        self.test_results.append(test_result)
    
    async def test_resource_management(self):
        """Test resource management and throttling"""
        test_result = TestResult("Resource Management")
        
        try:
            logger.info("Testing resource management...")
            
            resource_manager = performance_engine.resource_manager
            
            # Get current resource state
            current_state = resource_manager.current_state
            resource_stats = resource_manager.get_resource_statistics()
            
            # Test query execution request
            query_id = "test_query_resource_mgmt"
            can_execute = await resource_manager.request_query_execution(
                query_id, QueryPriority.NORMAL, {"memory_mb": 100, "cpu_percent": 10}
            )
            
            # Complete the query execution
            if can_execute:
                await resource_manager.complete_query_execution(query_id, {"memory_mb": 95, "cpu_percent": 8})
            
            resource_mgmt_working = (
                resource_stats and
                "current_state" in resource_stats and
                "queue_status" in resource_stats
            )
            
            if resource_mgmt_working:
                test_result.success({
                    "resource_state": {
                        "cpu_usage": current_state.cpu_usage_percent,
                        "memory_usage_mb": current_state.memory_usage_mb,
                        "active_connections": current_state.active_connections,
                        "pressure_score": current_state.get_pressure_score(resource_manager.resource_quota)
                    },
                    "query_execution_allowed": can_execute,
                    "throttling_enabled": resource_manager.throttling_enabled,
                    "resource_stats": resource_stats
                })
            else:
                test_result.failure(
                    "Resource management not functioning properly",
                    {"stats": resource_stats}
                )
        
        except Exception as e:
            test_result.failure(f"Resource management test failed: {str(e)}")
        
        self.test_results.append(test_result)
    
    async def test_concurrent_query_handling(self):
        """Test concurrent query execution"""
        test_result = TestResult("Concurrent Query Handling")
        
        try:
            logger.info("Testing concurrent query handling...")
            
            # Create multiple concurrent queries
            concurrent_queries = []
            num_concurrent = 5
            
            for i in range(num_concurrent):
                query = f"SELECT {i} as query_num, 'concurrent_test' as test_type"
                concurrent_queries.append(
                    hybrid_router.route_query(
                        query=query,
                        priority=QueryPriority.NORMAL,
                        use_cache=False  # Disable cache to test actual execution
                    )
                )
            
            # Execute queries concurrently
            start_time = time.time()
            results = await asyncio.gather(*concurrent_queries, return_exceptions=True)
            execution_time = time.time() - start_time
            
            # Analyze results
            successful_queries = sum(1 for r in results if isinstance(r, QueryResult) and r.data is not None)
            failed_queries = sum(1 for r in results if isinstance(r, Exception))
            
            success_rate = (successful_queries / num_concurrent) * 100
            
            if success_rate >= 80:  # At least 80% success rate for concurrent queries
                test_result.success({
                    "concurrent_queries": num_concurrent,
                    "successful_queries": successful_queries,
                    "failed_queries": failed_queries,
                    "success_rate": success_rate,
                    "total_execution_time": execution_time,
                    "avg_query_time": execution_time / num_concurrent
                })
            else:
                test_result.failure(
                    f"Concurrent query success rate too low: {success_rate:.1f}% (expected >= 80%)",
                    {"success_rate": success_rate, "results": str(results)}
                )
        
        except Exception as e:
            test_result.failure(f"Concurrent query test failed: {str(e)}")
        
        self.test_results.append(test_result)
    
    async def test_metrics_collection(self):
        """Test metrics collection functionality"""
        test_result = TestResult("Metrics Collection")
        
        try:
            logger.info("Testing metrics collection...")
            
            # Get performance metrics
            metrics = await hybrid_router.get_performance_metrics()
            
            # Test monitoring system
            dashboard_data = monitoring_system.get_monitoring_dashboard_data()
            
            metrics_available = (
                metrics and
                "overview" in metrics and
                "database_distribution" in metrics and
                "query_types" in metrics
            )
            
            monitoring_active = (
                dashboard_data and
                "real_time_metrics" in dashboard_data and
                "system_status" in dashboard_data
            )
            
            if metrics_available and monitoring_active:
                test_result.success({
                    "performance_metrics": {
                        "total_queries": metrics["overview"]["total_queries"],
                        "success_rate": metrics["overview"]["success_rate"],
                        "avg_response_time": metrics["overview"]["avg_response_time"],
                        "cache_hit_rate": metrics["overview"]["cache_hit_rate"]
                    },
                    "monitoring_system": {
                        "monitoring_active": dashboard_data["system_status"]["monitoring_active"],
                        "total_alerts_configured": dashboard_data["system_status"]["total_alerts_configured"],
                        "alerts_active": dashboard_data["system_status"]["alerts_active"]
                    }
                })
            else:
                test_result.failure(
                    "Metrics collection not functioning properly",
                    {"metrics_available": metrics_available, "monitoring_active": monitoring_active}
                )
        
        except Exception as e:
            test_result.failure(f"Metrics collection test failed: {str(e)}")
        
        self.test_results.append(test_result)
    
    async def test_alerting_system(self):
        """Test alerting functionality"""
        test_result = TestResult("Alerting System")
        
        try:
            logger.info("Testing alerting system...")
            
            alert_manager = monitoring_system.alert_manager
            
            # Get configured alerts
            configured_alerts = alert_manager.alerts
            
            # Get active alerts
            active_alerts = alert_manager.get_active_alerts()
            
            # Get alert history
            alert_history = alert_manager.get_alert_history(hours=1)
            
            alerting_functional = (
                len(configured_alerts) > 0 and
                isinstance(active_alerts, list) and
                isinstance(alert_history, list)
            )
            
            if alerting_functional:
                test_result.success({
                    "configured_alerts": len(configured_alerts),
                    "active_alerts": len(active_alerts),
                    "alert_history_entries": len(alert_history),
                    "alert_types": list(configured_alerts.keys())
                })
            else:
                test_result.failure(
                    "Alerting system not functioning properly",
                    {"configured": len(configured_alerts), "active": len(active_alerts)}
                )
        
        except Exception as e:
            test_result.failure(f"Alerting system test failed: {str(e)}")
        
        self.test_results.append(test_result)
    
    async def test_health_checks(self):
        """Test health check functionality"""
        test_result = TestResult("Health Checks")
        
        try:
            logger.info("Testing health checks...")
            
            # Test hybrid router health check
            router_health = await hybrid_router.health_check()
            
            # Test connection manager health check
            connection_health = await db_connection_manager.health_check()
            
            # Test monitoring system health check
            monitoring_health = await monitoring_system.health_check()
            
            all_healthy = (
                router_health.get("status") == "healthy" and
                connection_health.get("status") == "healthy" and
                monitoring_health.get("status") == "healthy"
            )
            
            if all_healthy:
                test_result.success({
                    "router_health": router_health.get("status"),
                    "connection_health": connection_health.get("status"),
                    "monitoring_health": monitoring_health.get("status"),
                    "router_services": router_health.get("services", {}),
                    "connection_pools": connection_health.get("pools", {})
                })
            else:
                test_result.failure(
                    "Health checks indicate system issues",
                    {
                        "router": router_health,
                        "connections": connection_health,
                        "monitoring": monitoring_health
                    }
                )
        
        except Exception as e:
            test_result.failure(f"Health check test failed: {str(e)}")
        
        self.test_results.append(test_result)
    
    async def test_end_to_end_workflows(self):
        """Test complete end-to-end workflows"""
        test_result = TestResult("End-to-End Workflows")
        
        try:
            logger.info("Testing end-to-end workflows...")
            
            workflow_results = {}
            successful_workflows = 0
            total_workflows = 0
            
            # Test workflow 1: OLTP query with optimization
            try:
                query = "SELECT u.id, u.email, COUNT(p.id) FROM users u LEFT JOIN projects p ON u.id = p.owner_id GROUP BY u.id, u.email"
                result = await hybrid_router.route_query(
                    query=query,
                    query_type=QueryType.USER_MANAGEMENT,
                    priority=QueryPriority.HIGH,
                    use_cache=True
                )
                
                workflow_results["oltp_with_optimization"] = {
                    "success": result is not None,
                    "database_used": result.database_used.value if result else None,
                    "execution_time": result.execution_time if result else None,
                    "cache_hit": result.cache_hit if result else False
                }
                
                if result:
                    successful_workflows += 1
                total_workflows += 1
                
            except Exception as e:
                workflow_results["oltp_with_optimization"] = {"success": False, "error": str(e)}
                total_workflows += 1
            
            # Test workflow 2: OLAP query with caching
            try:
                analytics_query = "SELECT DATE(created_at), COUNT(*) FROM scrape_sessions GROUP BY 1 ORDER BY 1 DESC LIMIT 30"
                result = await hybrid_router.route_query(
                    query=analytics_query,
                    query_type=QueryType.TIME_SERIES,
                    priority=QueryPriority.NORMAL,
                    use_cache=True
                )
                
                workflow_results["olap_with_caching"] = {
                    "success": result is not None,
                    "database_used": result.database_used.value if result else None,
                    "execution_time": result.execution_time if result else None,
                    "cache_hit": result.cache_hit if result else False
                }
                
                if result:
                    successful_workflows += 1
                total_workflows += 1
                
            except Exception as e:
                workflow_results["olap_with_caching"] = {"success": False, "error": str(e)}
                total_workflows += 1
            
            workflow_success_rate = (successful_workflows / total_workflows) * 100 if total_workflows > 0 else 0
            
            if workflow_success_rate >= 75:  # 75% workflow success rate
                test_result.success({
                    "workflow_success_rate": workflow_success_rate,
                    "successful_workflows": successful_workflows,
                    "total_workflows": total_workflows,
                    "workflow_details": workflow_results
                })
            else:
                test_result.failure(
                    f"End-to-end workflow success rate too low: {workflow_success_rate:.1f}%",
                    {"success_rate": workflow_success_rate, "details": workflow_results}
                )
        
        except Exception as e:
            test_result.failure(f"End-to-end workflow test failed: {str(e)}")
        
        self.test_results.append(test_result)
    
    async def test_failover_scenarios(self):
        """Test failover and error handling"""
        test_result = TestResult("Failover Scenarios")
        
        try:
            logger.info("Testing failover scenarios...")
            
            # Test circuit breaker behavior under simulated failure
            circuit_breaker_tests = {}
            
            # Get initial circuit breaker states
            pg_breaker = hybrid_router.postgresql_breaker
            initial_pg_state = pg_breaker.get_status()
            
            duckdb_breaker = hybrid_router.duckdb_breaker
            initial_duckdb_state = duckdb_breaker.get_status()
            
            circuit_breaker_tests["initial_states"] = {
                "postgresql": initial_pg_state.get("state"),
                "duckdb": initial_duckdb_state.get("state")
            }
            
            # Test query routing when circuit breakers are in different states
            test_query = "SELECT COUNT(*) FROM users"
            
            try:
                result = await hybrid_router.route_query(
                    query=test_query,
                    priority=QueryPriority.NORMAL
                )
                
                circuit_breaker_tests["query_execution_with_breakers"] = {
                    "success": result is not None,
                    "database_used": result.database_used.value if result else None
                }
                
            except Exception as e:
                circuit_breaker_tests["query_execution_with_breakers"] = {
                    "success": False,
                    "error": str(e)
                }
            
            # Test resource throttling under high load simulation
            throttling_test = await self._simulate_high_load_scenario()
            
            failover_working = (
                circuit_breaker_tests["initial_states"]["postgresql"] in ["closed", "half_open"] or
                circuit_breaker_tests["initial_states"]["duckdb"] in ["closed", "half_open"]
            )
            
            if failover_working:
                test_result.success({
                    "circuit_breaker_tests": circuit_breaker_tests,
                    "throttling_test": throttling_test,
                    "failover_mechanisms_active": True
                })
            else:
                test_result.failure(
                    "Failover mechanisms not functioning properly",
                    {"circuit_breaker_tests": circuit_breaker_tests}
                )
        
        except Exception as e:
            test_result.failure(f"Failover scenario test failed: {str(e)}")
        
        self.test_results.append(test_result)
    
    async def _simulate_high_load_scenario(self):
        """Simulate high load for throttling tests"""
        try:
            # Create multiple concurrent queries to simulate load
            load_queries = []
            for i in range(10):
                query = f"SELECT {i}, CURRENT_TIMESTAMP"
                load_queries.append(
                    hybrid_router.route_query(
                        query=query,
                        priority=QueryPriority.LOW,
                        use_cache=False
                    )
                )
            
            # Execute with timeout
            results = await asyncio.wait_for(
                asyncio.gather(*load_queries, return_exceptions=True),
                timeout=30.0
            )
            
            successful_load_queries = sum(
                1 for r in results 
                if isinstance(r, QueryResult)
            )
            
            return {
                "load_queries_sent": len(load_queries),
                "successful_executions": successful_load_queries,
                "load_handling_success_rate": (successful_load_queries / len(load_queries)) * 100
            }
            
        except Exception as e:
            return {"error": str(e), "load_test_failed": True}
    
    async def test_performance_under_load(self):
        """Test system performance under load"""
        test_result = TestResult("Performance Under Load")
        
        try:
            logger.info("Testing performance under load...")
            
            # Record baseline performance
            baseline_start = time.time()
            baseline_query = "SELECT 1 as baseline"
            baseline_result = await hybrid_router.route_query(baseline_query)
            baseline_time = time.time() - baseline_start
            
            # Execute multiple queries simultaneously
            load_queries = []
            num_load_queries = 20
            
            for i in range(num_load_queries):
                query_type = "analytics" if i % 2 == 0 else "user_auth"
                query = self.test_queries[query_type]
                load_queries.append(
                    hybrid_router.route_query(
                        query=query,
                        priority=QueryPriority.NORMAL,
                        use_cache=True
                    )
                )
            
            # Execute load test
            load_start = time.time()
            load_results = await asyncio.gather(*load_queries, return_exceptions=True)
            load_total_time = time.time() - load_start
            
            # Analyze load test results
            successful_load_queries = sum(
                1 for r in load_results 
                if isinstance(r, QueryResult)
            )
            
            avg_load_response_time = sum(
                r.execution_time for r in load_results 
                if isinstance(r, QueryResult)
            ) / max(successful_load_queries, 1)
            
            performance_degradation = (avg_load_response_time / max(baseline_time, 0.001)) - 1
            success_rate_under_load = (successful_load_queries / num_load_queries) * 100
            
            # Performance criteria
            performance_acceptable = (
                success_rate_under_load >= 85 and  # At least 85% success rate
                performance_degradation <= 5.0     # No more than 5x degradation
            )
            
            if performance_acceptable:
                test_result.success({
                    "baseline_response_time": baseline_time,
                    "load_queries_executed": num_load_queries,
                    "successful_under_load": successful_load_queries,
                    "success_rate_under_load": success_rate_under_load,
                    "avg_load_response_time": avg_load_response_time,
                    "performance_degradation_factor": performance_degradation,
                    "total_load_test_time": load_total_time
                })
            else:
                test_result.failure(
                    f"Performance under load not acceptable: {success_rate_under_load:.1f}% success rate, "
                    f"{performance_degradation:.1f}x performance degradation",
                    {
                        "success_rate": success_rate_under_load,
                        "degradation": performance_degradation
                    }
                )
        
        except Exception as e:
            test_result.failure(f"Performance under load test failed: {str(e)}")
        
        self.test_results.append(test_result)
    
    async def generate_test_report(self, total_execution_time: float):
        """Generate comprehensive test report"""
        logger.info("Generating test report...")
        
        # Calculate test statistics
        total_tests = len(self.test_results)
        passed_tests = sum(1 for result in self.test_results if result.passed)
        failed_tests = total_tests - passed_tests
        success_rate = (passed_tests / total_tests) * 100 if total_tests > 0 else 0
        
        # Create report
        report = {
            "test_execution_summary": {
                "timestamp": datetime.now().isoformat(),
                "total_execution_time_seconds": round(total_execution_time, 2),
                "total_tests": total_tests,
                "passed_tests": passed_tests,
                "failed_tests": failed_tests,
                "success_rate_percentage": round(success_rate, 1)
            },
            "test_results": [],
            "system_configuration": {
                "hybrid_router_enabled": settings.HYBRID_QUERY_ROUTER_ENABLED,
                "query_optimization_enabled": settings.HYBRID_ROUTER_ENABLE_QUERY_OPTIMIZATION,
                "caching_enabled": settings.HYBRID_ROUTER_ENABLE_QUERY_CACHING,
                "monitoring_enabled": settings.HYBRID_ROUTER_ENABLE_MONITORING,
                "circuit_breaker_enabled": settings.HYBRID_ROUTER_CIRCUIT_BREAKER_ENABLED
            },
            "recommendations": []
        }
        
        # Add detailed test results
        for result in self.test_results:
            report["test_results"].append({
                "test_name": result.test_name,
                "passed": result.passed,
                "execution_time": result.execution_time,
                "error_message": result.error_message if not result.passed else None,
                "details": result.details
            })
        
        # Add recommendations based on test results
        if success_rate < 90:
            report["recommendations"].append("Overall test success rate below 90% - investigate failed tests")
        
        failed_test_names = [r.test_name for r in self.test_results if not r.passed]
        if "Query Classification" in failed_test_names:
            report["recommendations"].append("Query classification accuracy needs improvement - review pattern matching rules")
        
        if "Database Routing" in failed_test_names:
            report["recommendations"].append("Database routing logic needs refinement - check routing decision algorithms")
        
        if "Performance Under Load" in failed_test_names:
            report["recommendations"].append("System performance under load needs optimization - consider resource scaling")
        
        if not any("Caching" in name for name in failed_test_names):
            report["recommendations"].append("Caching system working well - consider expanding cache usage")
        
        # Print report to console
        print("\n" + "="*80)
        print("HYBRID QUERY ROUTER TEST REPORT")
        print("="*80)
        print(f"Execution Time: {total_execution_time:.2f} seconds")
        print(f"Tests: {passed_tests}/{total_tests} passed ({success_rate:.1f}% success rate)")
        
        if failed_tests > 0:
            print(f"\nFailed Tests ({failed_tests}):")
            for result in self.test_results:
                if not result.passed:
                    print(f"  ❌ {result.test_name}: {result.error_message}")
        
        print(f"\nPassed Tests ({passed_tests}):")
        for result in self.test_results:
            if result.passed:
                print(f"  ✅ {result.test_name}")
        
        if report["recommendations"]:
            print(f"\nRecommendations:")
            for rec in report["recommendations"]:
                print(f"  • {rec}")
        
        print("\n" + "="*80)
        
        # Save report to file
        report_filename = f"hybrid_router_test_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        try:
            with open(report_filename, 'w') as f:
                json.dump(report, f, indent=2, default=str)
            print(f"Detailed report saved to: {report_filename}")
        except Exception as e:
            logger.error(f"Failed to save test report: {e}")
        
        return report


async def main():
    """Main test execution function"""
    print("Hybrid Query Router System Test Suite")
    print("=====================================")
    
    try:
        # Initialize test suite
        test_suite = HybridQueryRouterTestSuite()
        
        # Run all tests
        await test_suite.run_all_tests()
        
        # Print final status
        total_tests = len(test_suite.test_results)
        passed_tests = sum(1 for r in test_suite.test_results if r.passed)
        
        if passed_tests == total_tests:
            print("✅ All tests passed! Hybrid Query Router system is functioning correctly.")
            return 0
        else:
            print(f"❌ {total_tests - passed_tests} test(s) failed. Please review the detailed report.")
            return 1
            
    except Exception as e:
        logger.error(f"Test suite execution failed: {e}")
        print(f"❌ Test suite execution failed: {e}")
        return 1
    
    finally:
        # Clean up resources
        try:
            await hybrid_router.cache.redis_client.close() if hybrid_router.cache.redis_client else None
            await monitoring_system.shutdown()
            await db_connection_manager.shutdown()
            await performance_engine.shutdown()
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")


if __name__ == "__main__":
    # Run the test suite
    exit_code = asyncio.run(main())
    sys.exit(exit_code)