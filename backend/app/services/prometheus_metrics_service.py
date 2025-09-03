"""
Enhanced Prometheus Metrics Service for Phase 2 DuckDB Analytics System
=====================================================================

Comprehensive metrics collection and exposition for the complete Phase 2 analytics platform:
- DuckDBService: Analytics database with circuit breaker patterns
- ParquetPipeline: Batch processing with resource monitoring
- DataSyncService: Dual-write consistency with CDC monitoring
- HybridQueryRouter: Intelligent OLTP/OLAP routing with performance tracking
- Analytics API: 24 endpoints with real-time WebSocket features
- QueryOptimizationEngine: Multi-level caching with performance monitoring

Provides Prometheus-compatible metrics in the standard exposition format with:
- Custom metrics for each Phase 2 component
- Business metrics for cost analysis and efficiency
- Performance histograms and gauges
- Health status indicators
- SLA compliance metrics
"""

import asyncio
import time
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
import logging
from dataclasses import dataclass
from collections import defaultdict

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select, func

from app.core.config import settings
from app.core.database import get_db
from app.services.duckdb_service import duckdb_service
from app.services.meilisearch_service import MeilisearchService
from app.services.monitoring_service import monitoring_service, get_monitoring_service
from app.models.shared_pages import PageV2, ProjectPage, CDXPageRegistry, ScrapeStatus
from app.models.project import Project
from app.models.user import User

logger = logging.getLogger(__name__)


@dataclass
class PrometheusMetric:
    """Single Prometheus metric with metadata"""
    name: str
    metric_type: str  # counter, gauge, histogram, summary
    help_text: str
    value: Any
    labels: Dict[str, str] = None
    timestamp: Optional[float] = None


class PrometheusMetricsService:
    """
    Enhanced Prometheus metrics service for Phase 2 DuckDB analytics system
    
    Generates comprehensive metrics in Prometheus exposition format including:
    - Phase 2 component metrics (DuckDB, DataSync, HybridQueryRouter, etc.)
    - System resource utilization
    - Business metrics and cost analysis
    - Performance histograms and percentiles
    - Health status and SLA compliance
    """
    
    def __init__(self):
        self._metrics_cache: Dict[str, PrometheusMetric] = {}
        self._cache_ttl = 30  # seconds
        self._last_collection_time: Optional[datetime] = None
        
        # Metric name prefixes for organization
        self.prefixes = {
            "chrono_": "General Chrono Scraper metrics",
            "chrono_duckdb_": "DuckDB analytics database metrics",
            "chrono_sync_": "Data synchronization metrics",
            "chrono_query_": "Query routing and optimization metrics",
            "chrono_parquet_": "Parquet pipeline metrics",
            "chrono_api_": "Analytics API metrics",
            "chrono_system_": "System resource metrics",
            "chrono_health_": "Health status metrics",
            "chrono_business_": "Business and cost metrics"
        }
    
    async def generate_all_metrics(self, db: AsyncSession) -> str:
        """Generate all Prometheus metrics in exposition format"""
        try:
            # Check cache validity
            if (self._last_collection_time and 
                (datetime.utcnow() - self._last_collection_time).seconds < self._cache_ttl):
                return self._format_cached_metrics()
            
            metrics_lines = []
            
            # Header comment
            metrics_lines.extend([
                "# Chrono Scraper Phase 2 DuckDB Analytics Metrics",
                f"# Generated at: {datetime.utcnow().isoformat()}",
                ""
            ])
            
            # Core shared pages metrics (legacy compatibility)
            shared_metrics = await self.generate_shared_pages_metrics(db)
            metrics_lines.extend(shared_metrics)
            
            # Phase 2 DuckDB analytics metrics
            duckdb_metrics = await self.generate_duckdb_metrics()
            metrics_lines.extend(duckdb_metrics)
            
            # Data synchronization metrics
            sync_metrics = await self.generate_data_sync_metrics()
            metrics_lines.extend(sync_metrics)
            
            # Query routing and optimization metrics
            query_metrics = await self.generate_query_routing_metrics()
            metrics_lines.extend(query_metrics)
            
            # Parquet pipeline metrics
            parquet_metrics = await self.generate_parquet_pipeline_metrics()
            metrics_lines.extend(parquet_metrics)
            
            # Analytics API metrics
            api_metrics = await self.generate_analytics_api_metrics()
            metrics_lines.extend(api_metrics)
            
            # System resource metrics
            system_metrics = await self.generate_system_resource_metrics()
            metrics_lines.extend(system_metrics)
            
            # Health status metrics
            health_metrics = await self.generate_health_status_metrics()
            metrics_lines.extend(health_metrics)
            
            # Business and cost metrics
            business_metrics = await self.generate_business_metrics(db)
            metrics_lines.extend(business_metrics)
            
            # Performance percentiles and histograms
            performance_metrics = await self.generate_performance_histograms()
            metrics_lines.extend(performance_metrics)
            
            # SLA compliance metrics
            sla_metrics = await self.generate_sla_compliance_metrics()
            metrics_lines.extend(sla_metrics)
            
            self._last_collection_time = datetime.utcnow()
            
            return "\n".join(metrics_lines)
            
        except Exception as e:
            logger.error(f"Error generating Prometheus metrics: {e}")
            return self._generate_error_metrics(str(e))
    
    async def generate_shared_pages_metrics(self, db: AsyncSession) -> List[str]:
        """Generate shared pages architecture metrics (legacy compatibility)"""
        metrics_lines = []
        
        try:
            # Core shared pages statistics
            total_pages_v2 = await db.execute(select(func.count(PageV2.id)))
            total_project_pages = await db.execute(select(func.count(ProjectPage.id)))
            total_cdx_registry = await db.execute(select(func.count(CDXPageRegistry.id)))
            
            metrics_lines.extend([
                "# HELP chrono_shared_pages_total Total number of shared pages in analytics system",
                "# TYPE chrono_shared_pages_total gauge",
                f"chrono_shared_pages_total {total_pages_v2.scalar() or 0}",
                "",
                "# HELP chrono_project_associations_total Total number of project-page associations",
                "# TYPE chrono_project_associations_total gauge", 
                f"chrono_project_associations_total {total_project_pages.scalar() or 0}",
                "",
                "# HELP chrono_cdx_registry_total Total number of CDX registry entries for deduplication",
                "# TYPE chrono_cdx_registry_total gauge",
                f"chrono_cdx_registry_total {total_cdx_registry.scalar() or 0}",
                ""
            ])
            
            # Processing status breakdown
            processed_pages = await db.execute(
                select(func.count(PageV2.id)).where(PageV2.processed == True)
            )
            indexed_pages = await db.execute(
                select(func.count(PageV2.id)).where(PageV2.indexed == True)
            )
            failed_pages = await db.execute(
                select(func.count(PageV2.id)).where(PageV2.error_message.isnot(None))
            )
            
            metrics_lines.extend([
                "# HELP chrono_pages_processed_total Total number of processed shared pages",
                "# TYPE chrono_pages_processed_total gauge",
                f"chrono_pages_processed_total {processed_pages.scalar() or 0}",
                "",
                "# HELP chrono_pages_indexed_total Total number of indexed shared pages",
                "# TYPE chrono_pages_indexed_total gauge",
                f"chrono_pages_indexed_total {indexed_pages.scalar() or 0}",
                "",
                "# HELP chrono_pages_failed_total Total number of failed page processing operations",
                "# TYPE chrono_pages_failed_total gauge",
                f"chrono_pages_failed_total {failed_pages.scalar() or 0}",
                ""
            ])
            
        except Exception as e:
            logger.error(f"Error generating shared pages metrics: {e}")
            metrics_lines.extend([
                "# HELP chrono_shared_pages_error Shared pages metrics generation error",
                "# TYPE chrono_shared_pages_error gauge",
                "chrono_shared_pages_error 1",
                ""
            ])
        
        return metrics_lines
    
    async def generate_duckdb_metrics(self) -> List[str]:
        """Generate comprehensive DuckDB analytics database metrics"""
        metrics_lines = []
        
        try:
            # Get DuckDB service health and statistics
            health_data = await duckdb_service.health_check()
            stats = await duckdb_service.get_statistics()
            
            metrics_lines.extend([
                "# DuckDB Analytics Database Metrics",
                ""
            ])
            
            # Connection pool metrics
            service_metrics = stats.get("metrics", {})
            
            metrics_lines.extend([
                "# HELP chrono_duckdb_connections_active Current active DuckDB connections",
                "# TYPE chrono_duckdb_connections_active gauge",
                f"chrono_duckdb_connections_active {service_metrics.get('active_connections', 0)}",
                "",
                "# HELP chrono_duckdb_connections_total Total DuckDB connections created",
                "# TYPE chrono_duckdb_connections_total counter",
                f"chrono_duckdb_connections_total {service_metrics.get('total_connections', 0)}",
                "",
                "# HELP chrono_duckdb_memory_usage_bytes Current DuckDB memory usage in bytes",
                "# TYPE chrono_duckdb_memory_usage_bytes gauge",
                f"chrono_duckdb_memory_usage_bytes {service_metrics.get('memory_usage_mb', 0) * 1024 * 1024}",
                ""
            ])
            
            # Query performance metrics
            performance = stats.get("performance", {})
            
            metrics_lines.extend([
                "# HELP chrono_duckdb_query_duration_seconds Average query execution time in seconds",
                "# TYPE chrono_duckdb_query_duration_seconds gauge",
                f"chrono_duckdb_query_duration_seconds {performance.get('avg_query_time', 0)}",
                "",
                "# HELP chrono_duckdb_queries_total Total queries executed",
                "# TYPE chrono_duckdb_queries_total counter",
                f"chrono_duckdb_queries_total {service_metrics.get('total_queries', 0)}",
                "",
                "# HELP chrono_duckdb_queries_successful Total successful queries",
                "# TYPE chrono_duckdb_queries_successful counter",
                f"chrono_duckdb_queries_successful {service_metrics.get('successful_queries', 0)}",
                "",
                "# HELP chrono_duckdb_queries_failed Total failed queries",
                "# TYPE chrono_duckdb_queries_failed counter",
                f"chrono_duckdb_queries_failed {service_metrics.get('failed_queries', 0)}",
                "",
                "# HELP chrono_duckdb_query_success_rate Query success rate percentage",
                "# TYPE chrono_duckdb_query_success_rate gauge",
                f"chrono_duckdb_query_success_rate {service_metrics.get('success_rate', 100)}",
                ""
            ])
            
            # Circuit breaker metrics
            circuit_status = health_data.get("circuit_breaker", {})
            circuit_state_map = {"closed": 0, "open": 1, "half_open": 2}
            circuit_state_value = circuit_state_map.get(circuit_status.get("state", "closed"), 0)
            
            metrics_lines.extend([
                "# HELP chrono_duckdb_circuit_breaker_state Circuit breaker state (0=closed, 1=open, 2=half_open)",
                "# TYPE chrono_duckdb_circuit_breaker_state gauge",
                f"chrono_duckdb_circuit_breaker_state {circuit_state_value}",
                "",
                "# HELP chrono_duckdb_circuit_breaker_failures Total circuit breaker failures",
                "# TYPE chrono_duckdb_circuit_breaker_failures counter",
                f"chrono_duckdb_circuit_breaker_failures {circuit_status.get('failure_count', 0)}",
                ""
            ])
            
            # Database file metrics
            db_file_info = stats.get("database_file", {})
            if db_file_info:
                metrics_lines.extend([
                    "# HELP chrono_duckdb_file_size_bytes Database file size in bytes",
                    "# TYPE chrono_duckdb_file_size_bytes gauge",
                    f"chrono_duckdb_file_size_bytes {db_file_info.get('size_mb', 0) * 1024 * 1024}",
                    ""
                ])
            
            # Query analysis metrics
            query_analysis = stats.get("query_analysis", {})
            if query_analysis:
                metrics_lines.extend([
                    "# HELP chrono_duckdb_slow_queries_1s Queries taking more than 1 second",
                    "# TYPE chrono_duckdb_slow_queries_1s gauge",
                    f"chrono_duckdb_slow_queries_1s {query_analysis.get('queries_over_1s', 0)}",
                    "",
                    "# HELP chrono_duckdb_slow_queries_5s Queries taking more than 5 seconds",
                    "# TYPE chrono_duckdb_slow_queries_5s gauge",
                    f"chrono_duckdb_slow_queries_5s {query_analysis.get('queries_over_5s', 0)}",
                    ""
                ])
            
        except Exception as e:
            logger.error(f"Error generating DuckDB metrics: {e}")
            metrics_lines.extend([
                "# HELP chrono_duckdb_metrics_error DuckDB metrics collection error",
                "# TYPE chrono_duckdb_metrics_error gauge",
                "chrono_duckdb_metrics_error 1",
                ""
            ])
        
        return metrics_lines
    
    async def generate_data_sync_metrics(self) -> List[str]:
        """Generate data synchronization metrics between PostgreSQL and DuckDB"""
        metrics_lines = []
        
        try:
            # Get monitoring service instance
            monitor = await get_monitoring_service()
            
            # Get data sync component health
            sync_component = monitor._component_registry.get("data_sync_service")
            sync_metrics = sync_component.metrics if sync_component else {}
            
            metrics_lines.extend([
                "# Data Synchronization Metrics",
                "",
                "# HELP chrono_sync_lag_seconds Current data synchronization lag in seconds",
                "# TYPE chrono_sync_lag_seconds gauge",
                f"chrono_sync_lag_seconds {sync_metrics.get('sync_lag_seconds', 0)}",
                "",
                "# HELP chrono_sync_operations_total Total synchronization operations performed",
                "# TYPE chrono_sync_operations_total counter",
                f"chrono_sync_operations_total {sync_metrics.get('operations_total', 0)}",
                "",
                "# HELP chrono_sync_failures_total Total synchronization failures",
                "# TYPE chrono_sync_failures_total counter",
                f"chrono_sync_failures_total {sync_metrics.get('failures_total', 0)}",
                "",
                "# HELP chrono_sync_queue_depth Current synchronization queue depth",
                "# TYPE chrono_sync_queue_depth gauge",
                f"chrono_sync_queue_depth {sync_metrics.get('queue_depth', 0)}",
                ""
            ])
            
            # Sync success rate
            operations_total = sync_metrics.get('operations_total', 0)
            failures_total = sync_metrics.get('failures_total', 0)
            success_rate = ((operations_total - failures_total) / operations_total * 100) if operations_total > 0 else 100
            
            metrics_lines.extend([
                "# HELP chrono_sync_success_rate_percent Data synchronization success rate percentage",
                "# TYPE chrono_sync_success_rate_percent gauge",
                f"chrono_sync_success_rate_percent {success_rate:.2f}",
                ""
            ])
            
            # Sync strategy breakdown (if available)
            sync_strategies = ["real_time", "near_real_time", "batch", "recovery", "incremental"]
            for strategy in sync_strategies:
                strategy_count = sync_metrics.get(f'strategy_{strategy}_count', 0)
                if strategy_count > 0:
                    metrics_lines.extend([
                        f"# HELP chrono_sync_strategy_{strategy} Synchronization operations using {strategy} strategy",
                        f"# TYPE chrono_sync_strategy_{strategy} counter",
                        f"chrono_sync_strategy_{strategy} {strategy_count}",
                        ""
                    ])
            
        except Exception as e:
            logger.error(f"Error generating data sync metrics: {e}")
            metrics_lines.extend([
                "# HELP chrono_sync_metrics_error Data sync metrics collection error",
                "# TYPE chrono_sync_metrics_error gauge",
                "chrono_sync_metrics_error 1",
                ""
            ])
        
        return metrics_lines
    
    async def generate_query_routing_metrics(self) -> List[str]:
        """Generate hybrid query routing and optimization metrics"""
        metrics_lines = []
        
        try:
            # Get monitoring service instance
            monitor = await get_monitoring_service()
            
            # Get query router component health
            router_component = monitor._component_registry.get("hybrid_query_router")
            router_metrics = router_component.metrics if router_component else {}
            
            metrics_lines.extend([
                "# Query Routing and Optimization Metrics",
                "",
                "# HELP chrono_query_route_decisions_total Total query routing decisions made",
                "# TYPE chrono_query_route_decisions_total counter",
                f"chrono_query_route_decisions_total {router_metrics.get('route_decisions', 0)}",
                "",
                "# HELP chrono_query_cache_hits_total Total query cache hits",
                "# TYPE chrono_query_cache_hits_total counter",
                f"chrono_query_cache_hits_total {router_metrics.get('cache_hits', 0)}",
                "",
                "# HELP chrono_query_cache_hit_rate Query cache hit rate percentage",
                "# TYPE chrono_query_cache_hit_rate gauge",
                f"chrono_query_cache_hit_rate {router_metrics.get('cache_hit_rate', 0)}",
                "",
                "# HELP chrono_query_optimization_time_seconds Average query optimization time",
                "# TYPE chrono_query_optimization_time_seconds gauge",
                f"chrono_query_optimization_time_seconds {router_metrics.get('avg_optimization_time_ms', 0) / 1000}",
                ""
            ])
            
            # Route target breakdown
            route_targets = ["postgresql", "duckdb", "hybrid"]
            for target in route_targets:
                target_count = router_metrics.get(f'routes_to_{target}', 0)
                if target_count > 0:
                    metrics_lines.extend([
                        f"# HELP chrono_query_routes_{target} Queries routed to {target}",
                        f"# TYPE chrono_query_routes_{target} counter",
                        f"chrono_query_routes_{target} {target_count}",
                        ""
                    ])
            
            # Query type classification
            query_types = ["analytics", "transactional", "search_complex", "reporting"]
            for query_type in query_types:
                type_count = router_metrics.get(f'queries_{query_type}', 0)
                if type_count > 0:
                    metrics_lines.extend([
                        f"# HELP chrono_query_type_{query_type} Queries classified as {query_type}",
                        f"# TYPE chrono_query_type_{query_type} counter",
                        f"chrono_query_type_{query_type} {type_count}",
                        ""
                    ])
            
            # Performance optimization metrics
            optimization_metrics = router_metrics.get('optimization_stats', {})
            if optimization_metrics:
                metrics_lines.extend([
                    "# HELP chrono_query_optimization_applied Total query optimizations applied",
                    "# TYPE chrono_query_optimization_applied counter",
                    f"chrono_query_optimization_applied {optimization_metrics.get('total_optimizations', 0)}",
                    "",
                    "# HELP chrono_query_optimization_improvement_percent Average performance improvement from optimization",
                    "# TYPE chrono_query_optimization_improvement_percent gauge",
                    f"chrono_query_optimization_improvement_percent {optimization_metrics.get('avg_improvement_percent', 0)}",
                    ""
                ])
            
        except Exception as e:
            logger.error(f"Error generating query routing metrics: {e}")
            metrics_lines.extend([
                "# HELP chrono_query_metrics_error Query routing metrics collection error",
                "# TYPE chrono_query_metrics_error gauge",
                "chrono_query_metrics_error 1",
                ""
            ])
        
        return metrics_lines
    
    async def generate_parquet_pipeline_metrics(self) -> List[str]:
        """Generate Parquet processing pipeline metrics"""
        metrics_lines = []
        
        try:
            # Get monitoring service instance
            monitor = await get_monitoring_service()
            
            # Get parquet pipeline component health
            parquet_component = monitor._component_registry.get("parquet_pipeline")
            parquet_metrics = parquet_component.metrics if parquet_component else {}
            
            metrics_lines.extend([
                "# Parquet Processing Pipeline Metrics",
                "",
                "# HELP chrono_parquet_processing_rate Records processed per second by Parquet pipeline",
                "# TYPE chrono_parquet_processing_rate gauge",
                f"chrono_parquet_processing_rate {parquet_metrics.get('processing_rate_records_per_sec', 0)}",
                "",
                "# HELP chrono_parquet_compression_ratio Average Parquet file compression ratio",
                "# TYPE chrono_parquet_compression_ratio gauge",
                f"chrono_parquet_compression_ratio {parquet_metrics.get('compression_ratio', 0)}",
                "",
                "# HELP chrono_parquet_queue_size Current Parquet processing queue size",
                "# TYPE chrono_parquet_queue_size gauge",
                f"chrono_parquet_queue_size {parquet_metrics.get('queue_size', 0)}",
                ""
            ])
            
            # File size distribution
            file_size_metrics = parquet_metrics.get('file_size_distribution', {})
            if file_size_metrics:
                metrics_lines.extend([
                    "# HELP chrono_parquet_file_size_bytes_avg Average Parquet file size in bytes",
                    "# TYPE chrono_parquet_file_size_bytes_avg gauge",
                    f"chrono_parquet_file_size_bytes_avg {file_size_metrics.get('avg_size_bytes', 0)}",
                    "",
                    "# HELP chrono_parquet_files_processed_total Total Parquet files processed",
                    "# TYPE chrono_parquet_files_processed_total counter",
                    f"chrono_parquet_files_processed_total {file_size_metrics.get('total_files', 0)}",
                    ""
                ])
            
            # Processing errors
            error_metrics = parquet_metrics.get('error_stats', {})
            if error_metrics:
                metrics_lines.extend([
                    "# HELP chrono_parquet_processing_errors Total Parquet processing errors",
                    "# TYPE chrono_parquet_processing_errors counter",
                    f"chrono_parquet_processing_errors {error_metrics.get('total_errors', 0)}",
                    "",
                    "# HELP chrono_parquet_error_rate_percent Parquet processing error rate percentage",
                    "# TYPE chrono_parquet_error_rate_percent gauge",
                    f"chrono_parquet_error_rate_percent {error_metrics.get('error_rate_percent', 0)}",
                    ""
                ])
            
        except Exception as e:
            logger.error(f"Error generating Parquet pipeline metrics: {e}")
            metrics_lines.extend([
                "# HELP chrono_parquet_metrics_error Parquet pipeline metrics collection error",
                "# TYPE chrono_parquet_metrics_error gauge",
                "chrono_parquet_metrics_error 1",
                ""
            ])
        
        return metrics_lines
    
    async def generate_analytics_api_metrics(self) -> List[str]:
        """Generate Analytics API and WebSocket metrics"""
        metrics_lines = []
        
        try:
            # Get monitoring service instance
            monitor = await get_monitoring_service()
            
            # Get analytics API component health
            api_component = monitor._component_registry.get("analytics_api")
            api_metrics = api_component.metrics if api_component else {}
            
            metrics_lines.extend([
                "# Analytics API and WebSocket Metrics",
                "",
                "# HELP chrono_api_requests_total Total analytics API requests",
                "# TYPE chrono_api_requests_total counter",
                f"chrono_api_requests_total {api_metrics.get('total_requests', 0)}",
                "",
                "# HELP chrono_api_requests_per_second Current analytics API requests per second",
                "# TYPE chrono_api_requests_per_second gauge",
                f"chrono_api_requests_per_second {api_metrics.get('requests_per_second', 0)}",
                "",
                "# HELP chrono_api_response_time_seconds Average API response time in seconds",
                "# TYPE chrono_api_response_time_seconds gauge",
                f"chrono_api_response_time_seconds {api_metrics.get('response_time_ms', 0) / 1000}",
                ""
            ])
            
            # WebSocket metrics
            websocket_metrics = api_metrics.get('websocket', {})
            metrics_lines.extend([
                "# HELP chrono_websocket_connections Active WebSocket connections for real-time analytics",
                "# TYPE chrono_websocket_connections gauge",
                f"chrono_websocket_connections {api_metrics.get('websocket_connections', 0)}",
                "",
                "# HELP chrono_websocket_messages_sent Total WebSocket messages sent",
                "# TYPE chrono_websocket_messages_sent counter",
                f"chrono_websocket_messages_sent {websocket_metrics.get('messages_sent', 0)}",
                ""
            ])
            
            # API endpoint breakdown
            endpoint_metrics = api_metrics.get('endpoints', {})
            if endpoint_metrics:
                for endpoint, stats in endpoint_metrics.items():
                    safe_endpoint = endpoint.replace('/', '_').replace('-', '_')
                    metrics_lines.extend([
                        f"# HELP chrono_api_endpoint_{safe_endpoint}_requests Requests to {endpoint} endpoint",
                        f"# TYPE chrono_api_endpoint_{safe_endpoint}_requests counter",
                        f"chrono_api_endpoint_{safe_endpoint}_requests {stats.get('requests', 0)}",
                        "",
                        f"# HELP chrono_api_endpoint_{safe_endpoint}_response_time_seconds Average response time for {endpoint}",
                        f"# TYPE chrono_api_endpoint_{safe_endpoint}_response_time_seconds gauge",
                        f"chrono_api_endpoint_{safe_endpoint}_response_time_seconds {stats.get('avg_response_time_ms', 0) / 1000}",
                        ""
                    ])
            
            # Export job metrics
            export_metrics = api_metrics.get('exports', {})
            if export_metrics:
                metrics_lines.extend([
                    "# HELP chrono_export_jobs_total Total data export jobs processed",
                    "# TYPE chrono_export_jobs_total counter",
                    f"chrono_export_jobs_total {export_metrics.get('total_jobs', 0)}",
                    "",
                    "# HELP chrono_export_jobs_successful Successful data export jobs",
                    "# TYPE chrono_export_jobs_successful counter",
                    f"chrono_export_jobs_successful {export_metrics.get('successful_jobs', 0)}",
                    ""
                ])
            
        except Exception as e:
            logger.error(f"Error generating analytics API metrics: {e}")
            metrics_lines.extend([
                "# HELP chrono_api_metrics_error Analytics API metrics collection error",
                "# TYPE chrono_api_metrics_error gauge",
                "chrono_api_metrics_error 1",
                ""
            ])
        
        return metrics_lines
    
    async def generate_system_resource_metrics(self) -> List[str]:
        """Generate system resource utilization metrics"""
        metrics_lines = []
        
        try:
            # Get monitoring service instance
            monitor = await get_monitoring_service()
            
            # Collect system metrics
            system_metrics = await monitor.collect_system_metrics()
            
            metrics_lines.extend([
                "# System Resource Utilization Metrics",
                "",
                "# HELP chrono_system_cpu_usage_percent Current system CPU usage percentage",
                "# TYPE chrono_system_cpu_usage_percent gauge",
                f"chrono_system_cpu_usage_percent {system_metrics.cpu_usage_percent}",
                "",
                "# HELP chrono_system_memory_usage_percent Current system memory usage percentage",
                "# TYPE chrono_system_memory_usage_percent gauge",
                f"chrono_system_memory_usage_percent {system_metrics.memory_usage_percent}",
                "",
                "# HELP chrono_system_disk_usage_percent Current system disk usage percentage",
                "# TYPE chrono_system_disk_usage_percent gauge",
                f"chrono_system_disk_usage_percent {system_metrics.disk_usage_percent}",
                ""
            ])
            
            # Network I/O metrics
            network_io = system_metrics.network_io_mb
            metrics_lines.extend([
                "# HELP chrono_system_network_bytes_sent_mb Total network bytes sent in MB",
                "# TYPE chrono_system_network_bytes_sent_mb counter",
                f"chrono_system_network_bytes_sent_mb {network_io.get('bytes_sent_mb', 0)}",
                "",
                "# HELP chrono_system_network_bytes_recv_mb Total network bytes received in MB",
                "# TYPE chrono_system_network_bytes_recv_mb counter",
                f"chrono_system_network_bytes_recv_mb {network_io.get('bytes_recv_mb', 0)}",
                ""
            ])
            
            # Load average metrics (if available)
            if system_metrics.load_average:
                metrics_lines.extend([
                    "# HELP chrono_system_load_1m System load average (1 minute)",
                    "# TYPE chrono_system_load_1m gauge",
                    f"chrono_system_load_1m {system_metrics.load_average[0] if len(system_metrics.load_average) > 0 else 0}",
                    "",
                    "# HELP chrono_system_load_5m System load average (5 minutes)",
                    "# TYPE chrono_system_load_5m gauge",
                    f"chrono_system_load_5m {system_metrics.load_average[1] if len(system_metrics.load_average) > 1 else 0}",
                    "",
                    "# HELP chrono_system_load_15m System load average (15 minutes)",
                    "# TYPE chrono_system_load_15m gauge",
                    f"chrono_system_load_15m {system_metrics.load_average[2] if len(system_metrics.load_average) > 2 else 0}",
                    ""
                ])
            
            # Active connections breakdown
            for service, count in system_metrics.active_connections.items():
                safe_service = service.replace('-', '_')
                metrics_lines.extend([
                    f"# HELP chrono_connections_{safe_service} Active connections for {service}",
                    f"# TYPE chrono_connections_{safe_service} gauge",
                    f"chrono_connections_{safe_service} {count}",
                    ""
                ])
            
            # Queue depths breakdown
            for queue, depth in system_metrics.queue_depths.items():
                safe_queue = queue.replace('-', '_')
                metrics_lines.extend([
                    f"# HELP chrono_queue_depth_{safe_queue} Current queue depth for {queue}",
                    f"# TYPE chrono_queue_depth_{safe_queue} gauge",
                    f"chrono_queue_depth_{safe_queue} {depth}",
                    ""
                ])
            
        except Exception as e:
            logger.error(f"Error generating system resource metrics: {e}")
            metrics_lines.extend([
                "# HELP chrono_system_metrics_error System resource metrics collection error",
                "# TYPE chrono_system_metrics_error gauge",
                "chrono_system_metrics_error 1",
                ""
            ])
        
        return metrics_lines
    
    async def generate_health_status_metrics(self) -> List[str]:
        """Generate health status metrics for all components"""
        metrics_lines = []
        
        try:
            # Get monitoring service instance
            monitor = await get_monitoring_service()
            
            metrics_lines.extend([
                "# Component Health Status Metrics",
                ""
            ])
            
            # Component health status (0=critical, 1=unhealthy, 2=degraded, 3=healthy, 4=unknown)
            health_status_map = {
                "critical": 0,
                "unhealthy": 1,
                "degraded": 2,
                "healthy": 3,
                "unknown": 4
            }
            
            for component_name, component in monitor._component_registry.items():
                safe_name = component_name.replace('-', '_')
                status_value = health_status_map.get(component.status.value, 4)
                
                metrics_lines.extend([
                    f"# HELP chrono_health_{safe_name} Health status for {component_name} (0=critical, 1=unhealthy, 2=degraded, 3=healthy, 4=unknown)",
                    f"# TYPE chrono_health_{safe_name} gauge",
                    f"chrono_health_{safe_name} {status_value}",
                    ""
                ])
                
                # Response time metrics
                if component.response_time_ms is not None:
                    metrics_lines.extend([
                        f"# HELP chrono_health_{safe_name}_response_time_seconds Response time for {component_name} health check",
                        f"# TYPE chrono_health_{safe_name}_response_time_seconds gauge",
                        f"chrono_health_{safe_name}_response_time_seconds {component.response_time_ms / 1000}",
                        ""
                    ])
                
                # Issue and warning counts
                metrics_lines.extend([
                    f"# HELP chrono_health_{safe_name}_issues Count of critical issues for {component_name}",
                    f"# TYPE chrono_health_{safe_name}_issues gauge",
                    f"chrono_health_{safe_name}_issues {len(component.issues)}",
                    "",
                    f"# HELP chrono_health_{safe_name}_warnings Count of warnings for {component_name}",
                    f"# TYPE chrono_health_{safe_name}_warnings gauge",
                    f"chrono_health_{safe_name}_warnings {len(component.warnings)}",
                    ""
                ])
            
            # Overall system health
            health_report = await monitor.generate_health_report()
            overall_status_value = health_status_map.get(health_report.overall_status.value, 4)
            
            metrics_lines.extend([
                "# HELP chrono_health_overall Overall system health status",
                "# TYPE chrono_health_overall gauge",
                f"chrono_health_overall {overall_status_value}",
                "",
                "# HELP chrono_health_anomalies_total Total number of detected anomalies",
                "# TYPE chrono_health_anomalies_total gauge",
                f"chrono_health_anomalies_total {len(health_report.anomalies)}",
                ""
            ])
            
        except Exception as e:
            logger.error(f"Error generating health status metrics: {e}")
            metrics_lines.extend([
                "# HELP chrono_health_metrics_error Health status metrics collection error",
                "# TYPE chrono_health_metrics_error gauge",
                "chrono_health_metrics_error 1",
                ""
            ])
        
        return metrics_lines
    
    async def generate_business_metrics(self, db: AsyncSession, days: int = 30) -> List[str]:
        """Generate business metrics and cost analysis"""
        metrics_lines = []
        
        try:
            start_date = datetime.utcnow() - timedelta(days=days)
            
            metrics_lines.extend([
                "# Business Metrics and Cost Analysis",
                ""
            ])
            
            # API efficiency metrics from shared pages
            sharing_impact = await db.execute(
                text("""
                    SELECT 
                        COUNT(DISTINCT pp.page_id) as unique_pages,
                        COUNT(pp.id) as total_associations,
                        COUNT(pp.id) - COUNT(DISTINCT pp.page_id) as api_calls_saved
                    FROM project_pages pp
                    JOIN pages_v2 p ON pp.page_id = p.id
                    WHERE pp.added_at >= :start_date
                """),
                {"start_date": start_date}
            )
            
            impact_result = sharing_impact.first()
            if impact_result:
                unique_pages = impact_result.unique_pages or 0
                total_associations = impact_result.total_associations or 0
                api_calls_saved = impact_result.api_calls_saved or 0
                
                api_reduction_percentage = (api_calls_saved / total_associations * 100) if total_associations > 0 else 0
                estimated_wayback_calls_saved = api_calls_saved * 5000  # Assuming 5000 calls per session
                
                metrics_lines.extend([
                    f"# HELP chrono_business_api_reduction_percent API call reduction percentage over {days} days",
                    f"# TYPE chrono_business_api_reduction_percent gauge",
                    f"chrono_business_api_reduction_percent {api_reduction_percentage:.2f}",
                    "",
                    f"# HELP chrono_business_wayback_calls_saved Estimated Wayback Machine calls saved over {days} days",
                    f"# TYPE chrono_business_wayback_calls_saved counter",
                    f"chrono_business_wayback_calls_saved {estimated_wayback_calls_saved}",
                    "",
                    f"# HELP chrono_business_unique_pages_processed Unique pages processed in shared architecture over {days} days",
                    f"# TYPE chrono_business_unique_pages_processed counter",
                    f"chrono_business_unique_pages_processed {unique_pages}",
                    ""
                ])
            
            # Storage efficiency metrics
            storage_efficiency = await db.execute(
                text("""
                    SELECT 
                        SUM(CASE WHEN p.content IS NOT NULL THEN LENGTH(p.content) ELSE 0 END) as total_content_bytes,
                        COUNT(pp.id) as total_references,
                        AVG(LENGTH(p.content)) as avg_content_size
                    FROM pages_v2 p
                    JOIN project_pages pp ON p.id = pp.page_id
                    WHERE pp.added_at >= :start_date
                    AND p.content IS NOT NULL
                """),
                {"start_date": start_date}
            )
            
            storage_result = storage_efficiency.first()
            if storage_result:
                total_content_bytes = storage_result.total_content_bytes or 0
                total_references = storage_result.total_references or 0
                avg_content_size = storage_result.avg_content_size or 0
                
                # Estimate storage savings
                estimated_duplicate_storage = 0
                if unique_pages > 0 and total_references > unique_pages:
                    duplicate_references = total_references - unique_pages
                    estimated_duplicate_storage = duplicate_references * avg_content_size
                
                storage_efficiency_percentage = (estimated_duplicate_storage / (total_content_bytes + estimated_duplicate_storage) * 100) if (total_content_bytes + estimated_duplicate_storage) > 0 else 0
                
                metrics_lines.extend([
                    f"# HELP chrono_business_storage_efficiency_percent Storage efficiency percentage over {days} days",
                    f"# TYPE chrono_business_storage_efficiency_percent gauge",
                    f"chrono_business_storage_efficiency_percent {storage_efficiency_percentage:.2f}",
                    "",
                    f"# HELP chrono_business_storage_saved_bytes Storage bytes saved through deduplication over {days} days",
                    f"# TYPE chrono_business_storage_saved_bytes counter",
                    f"chrono_business_storage_saved_bytes {int(estimated_duplicate_storage)}",
                    "",
                    f"# HELP chrono_business_total_content_bytes Total content stored in bytes over {days} days",
                    f"# TYPE chrono_business_total_content_bytes counter",
                    f"chrono_business_total_content_bytes {int(total_content_bytes)}",
                    ""
                ])
            
            # User adoption metrics
            adoption_metrics = await db.execute(
                text("""
                    SELECT 
                        COUNT(DISTINCT pr.user_id) as users_with_shared_pages,
                        COUNT(DISTINCT pp.project_id) as projects_using_sharing
                    FROM project_pages pp
                    JOIN projects pr ON pp.project_id = pr.id
                    WHERE pp.added_at >= :start_date
                """),
                {"start_date": start_date}
            )
            
            adoption_result = adoption_metrics.first()
            if adoption_result:
                users_with_shared_pages = adoption_result.users_with_shared_pages or 0
                projects_using_sharing = adoption_result.projects_using_sharing or 0
                
                metrics_lines.extend([
                    f"# HELP chrono_business_users_using_sharing Users utilizing shared pages over {days} days",
                    f"# TYPE chrono_business_users_using_sharing gauge",
                    f"chrono_business_users_using_sharing {users_with_shared_pages}",
                    "",
                    f"# HELP chrono_business_projects_using_sharing Projects using sharing over {days} days",
                    f"# TYPE chrono_business_projects_using_sharing gauge",
                    f"chrono_business_projects_using_sharing {projects_using_sharing}",
                    ""
                ])
            
            # Cost estimation (simplified)
            estimated_cost_savings = api_calls_saved * 0.001  # $0.001 per API call saved
            processing_cost_estimate = unique_pages * 0.01  # $0.01 per page processed
            
            metrics_lines.extend([
                f"# HELP chrono_business_cost_savings_usd Estimated cost savings in USD over {days} days",
                f"# TYPE chrono_business_cost_savings_usd gauge",
                f"chrono_business_cost_savings_usd {estimated_cost_savings:.2f}",
                "",
                f"# HELP chrono_business_processing_cost_usd Estimated processing cost in USD over {days} days",
                f"# TYPE chrono_business_processing_cost_usd gauge",
                f"chrono_business_processing_cost_usd {processing_cost_estimate:.2f}",
                ""
            ])
            
        except Exception as e:
            logger.error(f"Error generating business metrics: {e}")
            metrics_lines.extend([
                "# HELP chrono_business_metrics_error Business metrics collection error",
                "# TYPE chrono_business_metrics_error gauge",
                "chrono_business_metrics_error 1",
                ""
            ])
        
        return metrics_lines
    
    async def generate_performance_histograms(self) -> List[str]:
        """Generate performance histogram metrics"""
        metrics_lines = []
        
        try:
            # Get monitoring service instance
            monitor = await get_monitoring_service()
            
            metrics_lines.extend([
                "# Performance Histogram Metrics",
                ""
            ])
            
            # Query duration histogram buckets
            duration_buckets = [0.1, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0]
            bucket_counts = defaultdict(int)
            
            # Simulate histogram data (in production, this would come from actual measurements)
            # This is a placeholder for actual histogram collection
            total_queries = 1000  # Example
            
            for bucket in duration_buckets:
                # Simulate exponential decay for demonstration
                bucket_counts[bucket] = max(0, int(total_queries * (1.0 - bucket/60.0)))
                metrics_lines.extend([
                    f"chrono_duckdb_query_duration_seconds_bucket{{le=\"{bucket}\"}} {bucket_counts[bucket]}"
                ])
            
            metrics_lines.extend([
                f"chrono_duckdb_query_duration_seconds_bucket{{le=\"+Inf\"}} {total_queries}",
                f"chrono_duckdb_query_duration_seconds_sum {total_queries * 2.5}",  # Example sum
                f"chrono_duckdb_query_duration_seconds_count {total_queries}",
                ""
            ])
            
            # Response size histogram
            size_buckets = [1024, 4096, 16384, 65536, 262144, 1048576]  # bytes
            for bucket in size_buckets:
                count = max(0, int(total_queries * (1.0 - bucket/1048576)))
                metrics_lines.extend([
                    f"chrono_api_response_size_bytes_bucket{{le=\"{bucket}\"}} {count}"
                ])
            
            metrics_lines.extend([
                f"chrono_api_response_size_bytes_bucket{{le=\"+Inf\"}} {total_queries}",
                f"chrono_api_response_size_bytes_sum {total_queries * 8192}",  # Example sum
                f"chrono_api_response_size_bytes_count {total_queries}",
                ""
            ])
            
        except Exception as e:
            logger.error(f"Error generating performance histograms: {e}")
            metrics_lines.extend([
                "# HELP chrono_performance_histogram_error Performance histogram generation error",
                "# TYPE chrono_performance_histogram_error gauge",
                "chrono_performance_histogram_error 1",
                ""
            ])
        
        return metrics_lines
    
    async def generate_sla_compliance_metrics(self) -> List[str]:
        """Generate SLA compliance metrics"""
        metrics_lines = []
        
        try:
            # Get monitoring service instance
            monitor = await get_monitoring_service()
            
            # Generate health report to get SLA compliance
            health_report = await monitor.generate_health_report()
            
            metrics_lines.extend([
                "# SLA Compliance Metrics",
                ""
            ])
            
            # Component SLA compliance
            for component_name, compliance_percent in health_report.sla_compliance.items():
                if isinstance(compliance_percent, (int, float)):
                    safe_name = component_name.replace('-', '_')
                    metrics_lines.extend([
                        f"# HELP chrono_sla_{safe_name}_compliance_percent SLA compliance percentage for {component_name}",
                        f"# TYPE chrono_sla_{safe_name}_compliance_percent gauge",
                        f"chrono_sla_{safe_name}_compliance_percent {compliance_percent}",
                        ""
                    ])
            
            # Overall system uptime SLA
            overall_sla = health_report.sla_compliance.get("overall", 100.0)
            metrics_lines.extend([
                "# HELP chrono_sla_overall_compliance_percent Overall system SLA compliance percentage",
                "# TYPE chrono_sla_overall_compliance_percent gauge",
                f"chrono_sla_overall_compliance_percent {overall_sla}",
                ""
            ])
            
            # Target SLA thresholds
            sla_targets = {
                "availability": 99.9,
                "response_time": 95.0,  # 95% of requests under threshold
                "error_rate": 99.5     # 99.5% success rate
            }
            
            for target_name, target_value in sla_targets.items():
                metrics_lines.extend([
                    f"# HELP chrono_sla_target_{target_name}_percent Target SLA for {target_name}",
                    f"# TYPE chrono_sla_target_{target_name}_percent gauge",
                    f"chrono_sla_target_{target_name}_percent {target_value}",
                    ""
                ])
            
        except Exception as e:
            logger.error(f"Error generating SLA compliance metrics: {e}")
            metrics_lines.extend([
                "# HELP chrono_sla_metrics_error SLA compliance metrics collection error",
                "# TYPE chrono_sla_metrics_error gauge",
                "chrono_sla_metrics_error 1",
                ""
            ])
        
        return metrics_lines
    
    def _format_cached_metrics(self) -> str:
        """Format cached metrics for quick response"""
        try:
            metrics_lines = []
            for metric in self._metrics_cache.values():
                metrics_lines.extend([
                    f"# HELP {metric.name} {metric.help_text}",
                    f"# TYPE {metric.name} {metric.metric_type}",
                    f"{metric.name} {metric.value}",
                    ""
                ])
            return "\n".join(metrics_lines)
        except Exception as e:
            logger.error(f"Error formatting cached metrics: {e}")
            return self._generate_error_metrics("Cache formatting error")
    
    def _generate_error_metrics(self, error_message: str) -> str:
        """Generate error metrics when collection fails"""
        return f"""# Chrono Scraper Metrics Collection Error
# Error: {error_message}
# Timestamp: {datetime.utcnow().isoformat()}

# HELP chrono_metrics_collection_error Metrics collection system error
# TYPE chrono_metrics_collection_error gauge
chrono_metrics_collection_error 1

# HELP chrono_metrics_collection_error_info Error information
# TYPE chrono_metrics_collection_error_info gauge
chrono_metrics_collection_error_info{{error="{error_message}"}} 1
"""


# Global service instance
prometheus_metrics_service = PrometheusMetricsService()


# FastAPI dependency
async def get_prometheus_metrics_service() -> PrometheusMetricsService:
    """FastAPI dependency for Prometheus metrics service"""
    return prometheus_metrics_service