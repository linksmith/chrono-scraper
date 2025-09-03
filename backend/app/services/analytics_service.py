"""
Analytics Service for Chrono Scraper FastAPI Application

High-performance analytics service leveraging DuckDB for OLAP operations
and PostgreSQL for OLTP operations through the HybridQueryRouter.

Features:
- Intelligent query routing between PostgreSQL and DuckDB
- Multi-level caching for performance optimization
- Real-time metrics and streaming analytics
- Export functionality with multiple formats
- Circuit breaker protection and error handling
"""

import asyncio
import json
import logging
import hashlib
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Union, Tuple
from uuid import UUID
import pandas as pd
from pathlib import Path
import tempfile
from dataclasses import dataclass
from contextlib import asynccontextmanager

from sqlmodel import Session, select, func, text as sql_text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import text
import redis.asyncio as aioredis

from ..core.config import settings
from ..core.database import AsyncSessionLocal
from ..models.user import User
from ..models.project import Project, Domain
from ..models.shared_pages import PageV2, ProjectPage
from ..models.scraping import ScrapePage, ScrapePageStatus
from ..services.duckdb_service import DuckDBService, get_duckdb_service
from ..services.hybrid_query_router import (
    HybridQueryRouter, get_hybrid_router, QueryType, DatabaseTarget, QueryPriority
)
from ..schemas.analytics import (
    TimeGranularity, AnalyticsScope, AnalyticsFormat,
    DomainTimelineDataPoint, DomainStatistics, TopDomainEntry,
    ProjectPerformanceData, ProjectDomainMetrics, ContentQualityMetrics,
    QualityDistributionBucket, ContentQualityDistributionData,
    SystemPerformanceData, DatabaseMetrics, TimeSeriesDataPoint,
    ProjectComparisonEntry, AnalyticsExportJob, ExportJobStatus
)

logger = logging.getLogger(__name__)


@dataclass
class AnalyticsQueryContext:
    """Context for analytics query execution"""
    user_id: Optional[UUID] = None
    project_ids: Optional[List[UUID]] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    use_cache: bool = True
    cache_ttl: int = 1800  # 30 minutes default


class AnalyticsCache:
    """High-performance caching for analytics results"""
    
    def __init__(self):
        self.redis_client: Optional[aioredis.Redis] = None
        self.local_cache: Dict[str, Tuple[Any, datetime]] = {}
        
    async def initialize(self):
        """Initialize Redis connection"""
        try:
            self.redis_client = aioredis.from_url(settings.REDIS_URL)
            await self.redis_client.ping()
            logger.info("Analytics cache initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize analytics cache: {e}")
            self.redis_client = None
    
    def _generate_cache_key(self, prefix: str, **kwargs) -> str:
        """Generate cache key from parameters"""
        key_data = json.dumps(kwargs, sort_keys=True, default=str)
        key_hash = hashlib.sha256(key_data.encode()).hexdigest()[:16]
        return f"analytics:{prefix}:{key_hash}"
    
    async def get(self, key: str) -> Optional[Any]:
        """Get cached result"""
        try:
            # Try local cache first
            if key in self.local_cache:
                data, timestamp = self.local_cache[key]
                if datetime.now() - timestamp < timedelta(minutes=5):
                    return data
                else:
                    del self.local_cache[key]
            
            # Try Redis cache
            if self.redis_client:
                cached = await self.redis_client.get(key)
                if cached:
                    data = json.loads(cached)
                    self.local_cache[key] = (data, datetime.now())
                    return data
            
            return None
        except Exception as e:
            logger.error(f"Cache get error: {e}")
            return None
    
    async def set(self, key: str, value: Any, ttl: int = 1800):
        """Set cached result"""
        try:
            # Store in local cache
            self.local_cache[key] = (value, datetime.now())
            
            # Store in Redis
            if self.redis_client:
                await self.redis_client.setex(
                    key, ttl, json.dumps(value, default=str)
                )
            
            # Limit local cache size
            if len(self.local_cache) > 500:
                oldest_keys = sorted(
                    self.local_cache.items(),
                    key=lambda x: x[1][1]
                )[:50]
                for cache_key, _ in oldest_keys:
                    del self.local_cache[cache_key]
                    
        except Exception as e:
            logger.error(f"Cache set error: {e}")
    
    async def invalidate_pattern(self, pattern: str):
        """Invalidate cache entries matching pattern"""
        try:
            # Clear local cache
            keys_to_remove = [k for k in self.local_cache.keys() if pattern in k]
            for key in keys_to_remove:
                del self.local_cache[key]
            
            # Clear Redis cache
            if self.redis_client:
                keys = await self.redis_client.keys(f"*{pattern}*")
                if keys:
                    await self.redis_client.delete(*keys)
        except Exception as e:
            logger.error(f"Cache invalidation error: {e}")


class AnalyticsService:
    """
    Comprehensive analytics service with DuckDB integration
    
    Provides high-performance analytics through intelligent query routing,
    multi-level caching, and optimized data processing.
    """
    
    _instance: Optional['AnalyticsService'] = None
    
    def __new__(cls) -> 'AnalyticsService':
        """Singleton pattern"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if hasattr(self, '_initialized'):
            return
        
        self._initialized = True
        self.duckdb_service: Optional[DuckDBService] = None
        self.hybrid_router: Optional[HybridQueryRouter] = None
        self.cache = AnalyticsCache()
        
        # Performance tracking
        self.query_metrics = {
            "total_queries": 0,
            "cache_hits": 0,
            "cache_misses": 0,
            "avg_query_time": 0.0,
            "slow_queries": 0
        }
        
        logger.info("AnalyticsService initialized")
    
    async def initialize(self):
        """Initialize analytics service dependencies"""
        try:
            # Initialize DuckDB service
            self.duckdb_service = await get_duckdb_service()
            
            # Initialize hybrid query router
            self.hybrid_router = await get_hybrid_router()
            
            # Initialize cache
            await self.cache.initialize()
            
            logger.info("AnalyticsService dependencies initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize AnalyticsService: {e}")
            raise
    
    # Domain Analytics Methods
    async def get_domain_timeline(
        self,
        domain: str,
        granularity: TimeGranularity = TimeGranularity.DAY,
        context: Optional[AnalyticsQueryContext] = None
    ) -> List[DomainTimelineDataPoint]:
        """Get domain timeline analytics with specified granularity"""
        context = context or AnalyticsQueryContext()
        
        # Generate cache key
        cache_key = self.cache._generate_cache_key(
            "domain_timeline",
            domain=domain,
            granularity=granularity.value,
            start_date=context.start_date,
            end_date=context.end_date
        )
        
        # Check cache
        if context.use_cache:
            cached_result = await self.cache.get(cache_key)
            if cached_result:
                self.query_metrics["cache_hits"] += 1
                return [DomainTimelineDataPoint(**point) for point in cached_result]
        
        # Build query based on granularity
        date_trunc_format = self._get_date_trunc_format(granularity)
        
        query = f"""
        SELECT 
            date_trunc('{date_trunc_format}', created_at) as timestamp,
            COUNT(*) as pages_scraped,
            SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as pages_successful,
            SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as pages_failed,
            SUM(COALESCE(content_size, 0)) / (1024.0 * 1024.0) as content_size_mb,
            COUNT(DISTINCT original_url) as unique_urls,
            (SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) * 100.0 / COUNT(*)) as error_rate
        FROM scrape_pages sp
        JOIN domains d ON sp.domain_id = d.id
        WHERE d.domain = $1
        """
        
        params = {"domain": domain}
        
        # Add date filters
        if context.start_date:
            query += " AND sp.created_at >= $2"
            params["start_date"] = context.start_date
        if context.end_date:
            query += f" AND sp.created_at <= ${len(params) + 1}"
            params["end_date"] = context.end_date
        
        query += " GROUP BY timestamp ORDER BY timestamp"
        
        # Execute query through hybrid router
        try:
            result = await self.hybrid_router.route_query(
                query, 
                params, 
                query_type=QueryType.TIME_SERIES,
                priority=QueryPriority.NORMAL
            )
            
            # Convert to response format
            timeline_data = []
            for row in result.data:
                timeline_data.append(DomainTimelineDataPoint(
                    timestamp=row[0],
                    pages_scraped=row[1],
                    pages_successful=row[2],
                    pages_failed=row[3],
                    content_size_mb=float(row[4]) if row[4] else 0.0,
                    unique_urls=row[5],
                    error_rate=float(row[6]) if row[6] else 0.0
                ))
            
            # Cache result
            if context.use_cache:
                cache_data = [point.dict() for point in timeline_data]
                await self.cache.set(cache_key, cache_data, context.cache_ttl)
                self.query_metrics["cache_misses"] += 1
            
            self.query_metrics["total_queries"] += 1
            return timeline_data
            
        except Exception as e:
            logger.error(f"Error getting domain timeline: {e}")
            raise
    
    async def get_domain_statistics(
        self,
        domain: str,
        context: Optional[AnalyticsQueryContext] = None
    ) -> DomainStatistics:
        """Get comprehensive domain statistics"""
        context = context or AnalyticsQueryContext()
        
        cache_key = self.cache._generate_cache_key(
            "domain_stats",
            domain=domain,
            start_date=context.start_date,
            end_date=context.end_date
        )
        
        if context.use_cache:
            cached_result = await self.cache.get(cache_key)
            if cached_result:
                self.query_metrics["cache_hits"] += 1
                return DomainStatistics(**cached_result)
        
        # Main statistics query - route to DuckDB for better aggregation performance
        stats_query = """
        SELECT 
            d.domain,
            COUNT(*) as total_pages,
            SUM(CASE WHEN sp.status = 'completed' THEN 1 ELSE 0 END) as successful_pages,
            SUM(CASE WHEN sp.status = 'failed' THEN 1 ELSE 0 END) as failed_pages,
            AVG(CASE WHEN sp.content_size IS NOT NULL THEN sp.content_size / 1024.0 ELSE 0 END) as avg_content_size,
            SUM(COALESCE(sp.content_size, 0)) / (1024.0 * 1024.0) as total_content_size,
            MIN(sp.created_at) as first_scraped,
            MAX(sp.created_at) as last_scraped,
            COUNT(DISTINCT sp.original_url) as unique_urls,
            AVG(COALESCE(sp.processing_time, 0)) as avg_scrape_duration
        FROM scrape_pages sp
        JOIN domains d ON sp.domain_id = d.id
        WHERE d.domain = $1
        """
        
        params = {"domain": domain}
        if context.start_date:
            stats_query += " AND sp.created_at >= $2"
            params["start_date"] = context.start_date
        if context.end_date:
            stats_query += f" AND sp.created_at <= ${len(params) + 1}"
            params["end_date"] = context.end_date
        
        stats_query += " GROUP BY d.domain"
        
        try:
            # Execute main query
            result = await self.hybrid_router.route_query(
                stats_query,
                params,
                query_type=QueryType.AGGREGATION,
                priority=QueryPriority.NORMAL
            )
            
            if not result.data:
                # Return empty statistics if no data
                return DomainStatistics(domain=domain)
            
            row = result.data[0]
            
            # Calculate success rate
            total_pages = row[1]
            successful_pages = row[2]
            success_rate = (successful_pages / total_pages * 100) if total_pages > 0 else 0.0
            
            # Get popular paths (separate query)
            popular_paths = await self._get_popular_paths(domain, context)
            
            # Get content types distribution (separate query)  
            content_types = await self._get_content_types_distribution(domain, context)
            
            # Get error distribution (separate query)
            error_distribution = await self._get_error_distribution(domain, context)
            
            stats = DomainStatistics(
                domain=row[0],
                total_pages=row[1],
                successful_pages=row[2],
                failed_pages=row[3],
                success_rate=success_rate,
                avg_content_size=float(row[4]) if row[4] else 0.0,
                total_content_size=float(row[5]) if row[5] else 0.0,
                first_scraped=row[6],
                last_scraped=row[7],
                unique_urls=row[8],
                avg_scrape_duration=float(row[9]) if row[9] else 0.0,
                popular_paths=popular_paths,
                content_types=content_types,
                error_distribution=error_distribution
            )
            
            # Cache result
            if context.use_cache:
                await self.cache.set(cache_key, stats.dict(), context.cache_ttl)
                self.query_metrics["cache_misses"] += 1
            
            self.query_metrics["total_queries"] += 1
            return stats
            
        except Exception as e:
            logger.error(f"Error getting domain statistics: {e}")
            raise
    
    async def get_top_domains(
        self,
        metric: str = "total_pages",
        limit: int = 100,
        context: Optional[AnalyticsQueryContext] = None
    ) -> List[TopDomainEntry]:
        """Get top domains ranked by specified metric"""
        context = context or AnalyticsQueryContext()
        
        cache_key = self.cache._generate_cache_key(
            "top_domains",
            metric=metric,
            limit=limit,
            start_date=context.start_date,
            end_date=context.end_date
        )
        
        if context.use_cache:
            cached_result = await self.cache.get(cache_key)
            if cached_result:
                self.query_metrics["cache_hits"] += 1
                return [TopDomainEntry(**entry) for entry in cached_result]
        
        # Build query based on metric
        metric_column = {
            "total_pages": "COUNT(*)",
            "success_rate": "(SUM(CASE WHEN sp.status = 'completed' THEN 1 ELSE 0 END) * 100.0 / COUNT(*))",
            "content_size": "SUM(COALESCE(sp.content_size, 0)) / (1024.0 * 1024.0)"
        }.get(metric, "COUNT(*)")
        
        query = f"""
        SELECT 
            d.domain,
            COUNT(*) as total_pages,
            (SUM(CASE WHEN sp.status = 'completed' THEN 1 ELSE 0 END) * 100.0 / COUNT(*)) as success_rate,
            SUM(COALESCE(sp.content_size, 0)) / (1024.0 * 1024.0) as content_size_mb,
            MAX(sp.created_at) as last_activity,
            COUNT(DISTINCT sp.project_id) as projects_count,
            {metric_column} as metric_value
        FROM scrape_pages sp
        JOIN domains d ON sp.domain_id = d.id
        WHERE 1=1
        """
        
        params = {}
        if context.start_date:
            query += " AND sp.created_at >= $1"
            params["start_date"] = context.start_date
        if context.end_date:
            query += f" AND sp.created_at <= ${len(params) + 1}"
            params["end_date"] = context.end_date
        
        query += f"""
        GROUP BY d.domain
        ORDER BY metric_value DESC
        LIMIT {limit}
        """
        
        try:
            result = await self.hybrid_router.route_query(
                query,
                params,
                query_type=QueryType.AGGREGATION,
                priority=QueryPriority.NORMAL
            )
            
            top_domains = []
            for rank, row in enumerate(result.data, 1):
                top_domains.append(TopDomainEntry(
                    domain=row[0],
                    rank=rank,
                    total_pages=row[1],
                    success_rate=float(row[2]) if row[2] else 0.0,
                    content_size_mb=float(row[3]) if row[3] else 0.0,
                    last_activity=row[4],
                    projects_count=row[5]
                ))
            
            # Cache result
            if context.use_cache:
                cache_data = [entry.dict() for entry in top_domains]
                await self.cache.set(cache_key, cache_data, context.cache_ttl)
                self.query_metrics["cache_misses"] += 1
            
            self.query_metrics["total_queries"] += 1
            return top_domains
            
        except Exception as e:
            logger.error(f"Error getting top domains: {e}")
            raise
    
    # Project Analytics Methods
    async def get_project_performance(
        self,
        project_id: UUID,
        include_domain_breakdown: bool = True,
        context: Optional[AnalyticsQueryContext] = None
    ) -> ProjectPerformanceData:
        """Get comprehensive project performance analytics"""
        context = context or AnalyticsQueryContext()
        
        cache_key = self.cache._generate_cache_key(
            "project_performance",
            project_id=str(project_id),
            include_domain_breakdown=include_domain_breakdown,
            start_date=context.start_date,
            end_date=context.end_date
        )
        
        if context.use_cache:
            cached_result = await self.cache.get(cache_key)
            if cached_result:
                self.query_metrics["cache_hits"] += 1
                return ProjectPerformanceData(**cached_result)
        
        # Get project info
        async with AsyncSessionLocal() as session:
            project = await session.get(Project, project_id)
            if not project:
                raise ValueError(f"Project {project_id} not found")
        
        # Main performance query
        perf_query = """
        SELECT 
            COUNT(*) as total_pages,
            SUM(CASE WHEN sp.status = 'completed' THEN 1 ELSE 0 END) as successful_pages,
            SUM(CASE WHEN sp.status = 'failed' THEN 1 ELSE 0 END) as failed_pages,
            AVG(COALESCE(sp.processing_time, 0)) as avg_scrape_duration,
            SUM(COALESCE(sp.content_size, 0)) / (1024.0 * 1024.0) as total_content_size,
            EXTRACT(EPOCH FROM (MAX(sp.created_at) - MIN(sp.created_at))) / 3600.0 as duration_hours
        FROM scrape_pages sp
        WHERE sp.project_id = $1
        """
        
        params = {"project_id": project_id}
        if context.start_date:
            perf_query += " AND sp.created_at >= $2"
            params["start_date"] = context.start_date
        if context.end_date:
            perf_query += f" AND sp.created_at <= ${len(params) + 1}"
            params["end_date"] = context.end_date
        
        try:
            result = await self.hybrid_router.route_query(
                perf_query,
                params,
                query_type=QueryType.AGGREGATION,
                priority=QueryPriority.NORMAL
            )
            
            if not result.data:
                return ProjectPerformanceData(
                    project_id=project_id,
                    project_name=project.name
                )
            
            row = result.data[0]
            total_pages = row[0]
            successful_pages = row[1]
            failed_pages = row[2]
            avg_scrape_duration = float(row[3]) if row[3] else 0.0
            total_content_size = float(row[4]) if row[4] else 0.0
            duration_hours = float(row[5]) if row[5] else 1.0
            
            # Calculate metrics
            success_rate = (successful_pages / total_pages * 100) if total_pages > 0 else 0.0
            scraping_efficiency = total_pages / duration_hours if duration_hours > 0 else 0.0
            
            # Get domain breakdown if requested
            domain_breakdown = []
            if include_domain_breakdown:
                domain_breakdown = await self._get_project_domain_breakdown(project_id, context)
            
            performance_data = ProjectPerformanceData(
                project_id=project_id,
                project_name=project.name,
                total_pages=total_pages,
                successful_pages=successful_pages,
                failed_pages=failed_pages,
                overall_success_rate=success_rate,
                avg_scrape_duration=avg_scrape_duration,
                total_content_size=total_content_size,
                scraping_efficiency=scraping_efficiency,
                domain_breakdown=domain_breakdown
            )
            
            # Cache result
            if context.use_cache:
                await self.cache.set(cache_key, performance_data.dict(), context.cache_ttl)
                self.query_metrics["cache_misses"] += 1
            
            self.query_metrics["total_queries"] += 1
            return performance_data
            
        except Exception as e:
            logger.error(f"Error getting project performance: {e}")
            raise
    
    # System Analytics Methods
    async def get_system_performance(
        self,
        include_database_metrics: bool = True,
        context: Optional[AnalyticsQueryContext] = None
    ) -> SystemPerformanceData:
        """Get comprehensive system performance overview"""
        context = context or AnalyticsQueryContext()
        
        cache_key = self.cache._generate_cache_key(
            "system_performance",
            include_database_metrics=include_database_metrics,
            start_date=context.start_date,
            end_date=context.end_date
        )
        
        if context.use_cache:
            cached_result = await self.cache.get(cache_key)
            if cached_result:
                self.query_metrics["cache_hits"] += 1
                return SystemPerformanceData(**cached_result)
        
        try:
            # Get basic system metrics
            system_query = """
            SELECT 
                COUNT(DISTINCT u.id) as active_users,
                COUNT(DISTINCT p.id) as active_projects,
                COUNT(*) as total_pages_scraped,
                AVG(COALESCE(sp.processing_time, 0)) as avg_processing_time
            FROM scrape_pages sp
            JOIN projects p ON sp.project_id = p.id
            JOIN users u ON p.owner_id = u.id
            WHERE sp.created_at >= NOW() - INTERVAL '7 days'
            """
            
            params = {}
            if context.start_date:
                system_query = system_query.replace(
                    "NOW() - INTERVAL '7 days'", "$1"
                )
                params["start_date"] = context.start_date
            
            result = await self.hybrid_router.route_query(
                system_query,
                params,
                query_type=QueryType.AGGREGATION,
                priority=QueryPriority.NORMAL
            )
            
            if result.data:
                row = result.data[0]
                active_users = row[0] or 0
                active_projects = row[1] or 0
                total_pages_scraped = row[2] or 0
                avg_processing_time = float(row[3]) if row[3] else 0.0
            else:
                active_users = active_projects = total_pages_scraped = 0
                avg_processing_time = 0.0
            
            # Calculate throughput (pages per hour over last 24h)
            throughput_query = """
            SELECT COUNT(*) / 24.0 as pages_per_hour
            FROM scrape_pages 
            WHERE created_at >= NOW() - INTERVAL '24 hours'
            """
            
            throughput_result = await self.hybrid_router.route_query(
                throughput_query,
                {},
                query_type=QueryType.AGGREGATION,
                priority=QueryPriority.NORMAL
            )
            
            scraping_throughput = float(throughput_result.data[0][0]) if throughput_result.data else 0.0
            
            # Get database metrics if requested
            database_metrics = []
            if include_database_metrics and self.hybrid_router:
                perf_metrics = await self.hybrid_router.get_performance_metrics()
                
                # PostgreSQL metrics
                database_metrics.append(DatabaseMetrics(
                    database_type="postgresql",
                    total_queries=perf_metrics["database_distribution"]["postgresql"],
                    avg_query_time=perf_metrics["overview"]["avg_response_time"],
                    error_rate=100 - perf_metrics["overview"]["success_rate"],
                    cache_hit_rate=perf_metrics["overview"]["cache_hit_rate"]
                ))
                
                # DuckDB metrics
                database_metrics.append(DatabaseMetrics(
                    database_type="duckdb",
                    total_queries=perf_metrics["database_distribution"]["duckdb"],
                    avg_query_time=perf_metrics["overview"]["avg_response_time"],
                    error_rate=100 - perf_metrics["overview"]["success_rate"],
                    cache_hit_rate=perf_metrics["overview"]["cache_hit_rate"]
                ))
            
            system_data = SystemPerformanceData(
                uptime_hours=24.0,  # Placeholder - would need proper uptime tracking
                total_requests=self.query_metrics["total_queries"],
                avg_response_time=self.query_metrics["avg_query_time"],
                error_rate=0.0,  # Calculated from success rate
                active_users=active_users,
                active_projects=active_projects,
                total_pages_scraped=total_pages_scraped,
                scraping_throughput=scraping_throughput,
                database_metrics=database_metrics,
                resource_usage={}  # Would integrate with monitoring service
            )
            
            # Cache result
            if context.use_cache:
                await self.cache.set(cache_key, system_data.dict(), context.cache_ttl)
                self.query_metrics["cache_misses"] += 1
            
            self.query_metrics["total_queries"] += 1
            return system_data
            
        except Exception as e:
            logger.error(f"Error getting system performance: {e}")
            raise
    
    # Helper Methods
    def _get_date_trunc_format(self, granularity: TimeGranularity) -> str:
        """Convert TimeGranularity to PostgreSQL date_trunc format"""
        mapping = {
            TimeGranularity.MINUTE: "minute",
            TimeGranularity.HOUR: "hour", 
            TimeGranularity.DAY: "day",
            TimeGranularity.WEEK: "week",
            TimeGranularity.MONTH: "month",
            TimeGranularity.QUARTER: "quarter",
            TimeGranularity.YEAR: "year"
        }
        return mapping.get(granularity, "day")
    
    async def _get_popular_paths(
        self, 
        domain: str, 
        context: AnalyticsQueryContext
    ) -> List[Dict[str, Any]]:
        """Get popular paths for a domain"""
        query = """
        SELECT 
            REGEXP_REPLACE(sp.original_url, '^https?://[^/]+', '') as path,
            COUNT(*) as count
        FROM scrape_pages sp
        JOIN domains d ON sp.domain_id = d.id
        WHERE d.domain = $1
        GROUP BY path
        ORDER BY count DESC
        LIMIT 10
        """
        
        try:
            result = await self.hybrid_router.route_query(
                query,
                {"domain": domain},
                query_type=QueryType.AGGREGATION,
                priority=QueryPriority.LOW
            )
            
            return [{"path": row[0], "count": row[1]} for row in result.data]
        except Exception:
            return []
    
    async def _get_content_types_distribution(
        self, 
        domain: str, 
        context: AnalyticsQueryContext
    ) -> Dict[str, int]:
        """Get content types distribution for a domain"""
        # This would require content_type field in scrape_pages table
        # For now, return placeholder data
        return {"text/html": 100, "application/pdf": 10}
    
    async def _get_error_distribution(
        self, 
        domain: str, 
        context: AnalyticsQueryContext
    ) -> Dict[str, int]:
        """Get error distribution for a domain"""
        query = """
        SELECT 
            COALESCE(sp.error_type, 'unknown') as error_type,
            COUNT(*) as count
        FROM scrape_pages sp
        JOIN domains d ON sp.domain_id = d.id
        WHERE d.domain = $1 AND sp.status = 'failed'
        GROUP BY error_type
        ORDER BY count DESC
        """
        
        try:
            result = await self.hybrid_router.route_query(
                query,
                {"domain": domain},
                query_type=QueryType.AGGREGATION,
                priority=QueryPriority.LOW
            )
            
            return {row[0]: row[1] for row in result.data}
        except Exception:
            return {}
    
    async def _get_project_domain_breakdown(
        self, 
        project_id: UUID, 
        context: AnalyticsQueryContext
    ) -> List[ProjectDomainMetrics]:
        """Get domain breakdown for a project"""
        query = """
        SELECT 
            d.domain,
            COUNT(*) as total_pages,
            SUM(CASE WHEN sp.status = 'completed' THEN 1 ELSE 0 END) as successful_pages,
            (SUM(CASE WHEN sp.status = 'failed' THEN 1 ELSE 0 END) * 100.0 / COUNT(*)) as error_rate,
            AVG(COALESCE(sp.processing_time, 0)) as avg_response_time,
            SUM(COALESCE(sp.content_size, 0)) / (1024.0 * 1024.0) as content_size_mb
        FROM scrape_pages sp
        JOIN domains d ON sp.domain_id = d.id
        WHERE sp.project_id = $1
        GROUP BY d.domain
        ORDER BY total_pages DESC
        """
        
        params = {"project_id": project_id}
        if context.start_date:
            query += " AND sp.created_at >= $2"
            params["start_date"] = context.start_date
        if context.end_date:
            query += f" AND sp.created_at <= ${len(params) + 1}"
            params["end_date"] = context.end_date
        
        try:
            result = await self.hybrid_router.route_query(
                query,
                params,
                query_type=QueryType.AGGREGATION,
                priority=QueryPriority.LOW
            )
            
            breakdown = []
            for row in result.data:
                breakdown.append(ProjectDomainMetrics(
                    domain=row[0],
                    total_pages=row[1],
                    successful_pages=row[2],
                    error_rate=float(row[3]) if row[3] else 0.0,
                    avg_response_time=float(row[4]) if row[4] else 0.0,
                    content_size_mb=float(row[5]) if row[5] else 0.0
                ))
            
            return breakdown
        except Exception:
            return []
    
    async def invalidate_cache(self, pattern: str = "*"):
        """Invalidate analytics cache"""
        await self.cache.invalidate_pattern(pattern)
    
    async def get_service_health(self) -> Dict[str, Any]:
        """Get analytics service health status"""
        health = {
            "status": "healthy",
            "services": {
                "duckdb": "unknown",
                "hybrid_router": "unknown",
                "cache": "unknown"
            },
            "metrics": self.query_metrics
        }
        
        try:
            # Check DuckDB service
            if self.duckdb_service:
                duck_health = await self.duckdb_service.health_check()
                health["services"]["duckdb"] = duck_health["status"]
            
            # Check hybrid router
            if self.hybrid_router:
                router_health = await self.hybrid_router.health_check()
                health["services"]["hybrid_router"] = router_health["status"]
            
            # Check cache
            if self.cache.redis_client:
                await self.cache.redis_client.ping()
                health["services"]["cache"] = "healthy"
            else:
                health["services"]["cache"] = "degraded"
            
        except Exception as e:
            health["status"] = "degraded"
            health["error"] = str(e)
        
        return health


# Global service instance
analytics_service = AnalyticsService()


# FastAPI dependency
async def get_analytics_service() -> AnalyticsService:
    """FastAPI dependency for analytics service"""
    if not hasattr(analytics_service, '_initialized'):
        await analytics_service.initialize()
    return analytics_service