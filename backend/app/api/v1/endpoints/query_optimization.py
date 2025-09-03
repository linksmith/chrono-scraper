"""
Query Optimization API Endpoints

Provides FastAPI endpoints for query optimization management, performance monitoring,
cache control, and system analytics.
"""

import asyncio
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query as QueryParam, status
from pydantic import BaseModel, Field
from sqlmodel import select

from ....core.auth import get_current_active_admin_user
from ....core.database import get_db
from ....models.user import User
from ....services.query_optimization_engine import (
    get_query_optimization_engine,
    QueryContext,
    DatabaseType,
    OptimizationType,
    QueryComplexity
)
from ....services.intelligent_cache_manager import (
    get_cache_manager,
    CacheLevel,
    CacheStrategy
)
from ....services.query_performance_monitor import (
    get_performance_monitor,
    AlertSeverity,
    PerformanceMetricType,
    AlertThreshold
)
from ....services.adaptive_query_executor import (
    get_query_executor,
    Priority
)
from ....services.cache_integration_service import (
    get_cache_integration_service,
    InvalidationScope,
    ConsistencyLevel
)

logger = logging.getLogger(__name__)

router = APIRouter()


# Pydantic models for API requests/responses

class OptimizationRequest(BaseModel):
    """Request to optimize a query"""
    query: str = Field(..., description="SQL query to optimize")
    database_type: str = Field(default="postgresql", description="Target database type")
    user_id: Optional[str] = Field(None, description="User ID for context")
    project_id: Optional[str] = Field(None, description="Project ID for context")
    optimization_level: int = Field(default=3, ge=1, le=5, description="Optimization aggressiveness (1-5)")
    enable_caching: bool = Field(default=True, description="Enable query result caching")


class OptimizationResponse(BaseModel):
    """Response with optimized query"""
    original_query: str
    optimized_query: str
    optimization_types: List[str]
    estimated_improvement_percent: float
    estimated_cost_before: Dict[str, float]
    estimated_cost_after: Dict[str, float]
    cache_key: Optional[str]
    warnings: List[str]


class QueryAnalysisRequest(BaseModel):
    """Request for query analysis"""
    query: str = Field(..., description="SQL query to analyze")
    database_type: str = Field(default="postgresql", description="Database type")


class QueryAnalysisResponse(BaseModel):
    """Response with query analysis"""
    query_hash: str
    estimated_cost: float
    estimated_rows: int
    complexity: str
    tables_accessed: List[str]
    indexes_used: List[str]
    missing_indexes: List[str]
    performance_issues: List[str]
    optimization_suggestions: List[str]


class CacheOperationRequest(BaseModel):
    """Request for cache operations"""
    operation: str = Field(..., description="Cache operation (warm, invalidate, optimize)")
    patterns: Optional[List[str]] = Field(None, description="Patterns for invalidation")
    queries: Optional[List[str]] = Field(None, description="Queries for warming")


class PerformanceAlertRequest(BaseModel):
    """Request to create performance alert"""
    metric_type: str = Field(..., description="Performance metric type")
    threshold_value: float = Field(..., description="Alert threshold value")
    comparison_operator: str = Field(..., description="Comparison operator (>, <, >=, <=, ==)")
    window_minutes: int = Field(default=5, description="Time window in minutes")
    min_occurrences: int = Field(default=1, description="Minimum occurrences to trigger")
    severity: str = Field(default="medium", description="Alert severity level")


# Query optimization endpoints

@router.get("/optimization/status")
async def get_optimization_status(
    current_admin: User = Depends(get_current_active_admin_user)
):
    """Get query optimization service status"""
    try:
        optimization_engine = get_query_optimization_engine()
        if not optimization_engine:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Query optimization engine not available"
            )
        
        stats = await optimization_engine.get_optimization_stats()
        
        return {
            "status": "active",
            "optimization_engine_available": True,
            "cache_stats": stats.get("cache_stats", {}),
            "optimization_counts": stats.get("optimization_counts", {}),
            "service_health": stats.get("service_health", {})
        }
        
    except Exception as e:
        logger.error(f"Error getting optimization status: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get optimization status: {str(e)}"
        )


@router.post("/optimization/analyze-query", response_model=QueryAnalysisResponse)
async def analyze_query(
    request: QueryAnalysisRequest,
    current_admin: User = Depends(get_current_active_admin_user)
):
    """Analyze query performance and optimization opportunities"""
    try:
        optimization_engine = get_query_optimization_engine()
        if not optimization_engine:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Query optimization engine not available"
            )
        
        # Analyze query plan
        plan = await optimization_engine.analyze_query_plan(
            request.query,
            request.database_type
        )
        
        return QueryAnalysisResponse(
            query_hash=plan.plan_id,
            estimated_cost=plan.estimated_cost,
            estimated_rows=plan.estimated_rows,
            complexity=plan.complexity.value,
            tables_accessed=plan.table_scans,
            indexes_used=plan.index_usage,
            missing_indexes=[],  # Would be populated by analysis
            performance_issues=plan.bottlenecks,
            optimization_suggestions=plan.optimization_opportunities
        )
        
    except Exception as e:
        logger.error(f"Error analyzing query: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to analyze query: {str(e)}"
        )


@router.post("/optimization/optimize-query", response_model=OptimizationResponse)
async def optimize_query(
    request: OptimizationRequest,
    current_admin: User = Depends(get_current_active_admin_user)
):
    """Optimize a SQL query for better performance"""
    try:
        optimization_engine = get_query_optimization_engine()
        if not optimization_engine:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Query optimization engine not available"
            )
        
        # Create optimization context
        context = QueryContext(
            database_type=DatabaseType(request.database_type),
            user_id=request.user_id,
            project_id=request.project_id,
            enable_caching=request.enable_caching,
            optimization_level=request.optimization_level
        )
        
        # Optimize query
        optimized = await optimization_engine.optimize_query(request.query, context)
        
        return OptimizationResponse(
            original_query=optimized.original_query,
            optimized_query=optimized.optimized_query,
            optimization_types=[opt.value for opt in optimized.optimization_types],
            estimated_improvement_percent=optimized.estimated_improvement_percent,
            estimated_cost_before={
                "cpu_cost": optimized.cost_before.cpu_cost,
                "io_cost": optimized.cost_before.io_cost,
                "memory_cost": optimized.cost_before.memory_cost,
                "total_cost": optimized.cost_before.total_cost
            },
            estimated_cost_after={
                "cpu_cost": optimized.cost_after.cpu_cost,
                "io_cost": optimized.cost_after.io_cost,
                "memory_cost": optimized.cost_after.memory_cost,
                "total_cost": optimized.cost_after.total_cost
            },
            cache_key=optimized.cache_key,
            warnings=optimized.warnings
        )
        
    except Exception as e:
        logger.error(f"Error optimizing query: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to optimize query: {str(e)}"
        )


@router.get("/optimization/recommendations")
async def get_optimization_recommendations(
    table_name: Optional[str] = QueryParam(None, description="Filter by table name"),
    current_admin: User = Depends(get_current_active_admin_user)
):
    """Get optimization recommendations"""
    try:
        optimization_engine = get_query_optimization_engine()
        if not optimization_engine:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Query optimization engine not available"
            )
        
        recommendations = await optimization_engine.get_optimization_recommendations(table_name)
        
        return {
            "recommendations": [
                {
                    "type": rec.type,
                    "description": rec.description,
                    "affected_queries": rec.affected_queries,
                    "estimated_improvement_percent": rec.estimated_improvement_percent,
                    "implementation_effort": rec.implementation_effort,
                    "priority": rec.priority,
                    "sql_changes": rec.sql_changes,
                    "configuration_changes": rec.configuration_changes
                }
                for rec in recommendations
            ]
        }
        
    except Exception as e:
        logger.error(f"Error getting optimization recommendations: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get recommendations: {str(e)}"
        )


# Cache management endpoints

@router.get("/cache/statistics")
async def get_cache_statistics(
    current_admin: User = Depends(get_current_active_admin_user)
):
    """Get comprehensive cache statistics"""
    try:
        cache_manager = get_cache_manager()
        if not cache_manager:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Cache manager not available"
            )
        
        stats = await cache_manager.get_cache_statistics()
        
        return {
            "total_entries": stats.total_entries,
            "total_size_bytes": stats.total_size_bytes,
            "total_size_mb": round(stats.total_size_bytes / (1024 * 1024), 2),
            "hit_rate": round(stats.hit_rate, 2),
            "miss_rate": round(stats.miss_rate, 2),
            "eviction_rate": round(stats.eviction_rate, 2),
            "average_access_time_ms": round(stats.average_access_time_ms, 2),
            "level_stats": {
                level.name.lower(): {
                    "hits": level_stats["hits"],
                    "misses": level_stats["misses"],
                    "evictions": level_stats["evictions"],
                    "hit_rate": round(level_stats["hit_rate"], 2)
                }
                for level, level_stats in stats.level_stats.items()
            },
            "top_keys": [{"key": key, "access_count": count} for key, count in stats.top_keys],
            "memory_pressure": round(stats.memory_pressure, 2),
            "fragmentation_ratio": round(stats.fragmentation_ratio, 2),
            "last_cleanup": stats.last_cleanup.isoformat() if stats.last_cleanup else None
        }
        
    except Exception as e:
        logger.error(f"Error getting cache statistics: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get cache statistics: {str(e)}"
        )


@router.post("/cache/warm-up")
async def warm_up_cache(
    queries: List[str],
    current_admin: User = Depends(get_current_active_admin_user)
):
    """Warm up cache with popular queries"""
    try:
        cache_manager = get_cache_manager()
        if not cache_manager:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Cache manager not available"
            )
        
        # Start cache warming in background
        await cache_manager.warm_cache(queries)
        
        return {
            "message": f"Cache warming initiated for {len(queries)} queries",
            "query_count": len(queries)
        }
        
    except Exception as e:
        logger.error(f"Error warming cache: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to warm cache: {str(e)}"
        )


@router.post("/cache/invalidate")
async def invalidate_cache(
    patterns: List[str],
    scope: str = "key_pattern",
    current_admin: User = Depends(get_current_active_admin_user)
):
    """Invalidate cache entries matching patterns"""
    try:
        cache_integration_service = get_cache_integration_service()
        if not cache_integration_service:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Cache integration service not available"
            )
        
        # Perform coordinated invalidation
        invalidation_result = await cache_integration_service.invalidate_coordinated_cache(
            scope=InvalidationScope(scope),
            patterns=patterns,
            reason="Manual admin invalidation",
            triggered_by=f"admin:{current_admin.email}"
        )
        
        return {
            "invalidation_id": invalidation_result.invalidation_id,
            "scope": invalidation_result.scope.value,
            "patterns": invalidation_result.patterns,
            "affected_databases": [db.value for db in invalidation_result.affected_databases],
            "estimated_impact": invalidation_result.estimated_impact,
            "triggered_at": invalidation_result.triggered_at.isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error invalidating cache: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to invalidate cache: {str(e)}"
        )


@router.post("/cache/optimize")
async def optimize_cache_layout(
    current_admin: User = Depends(get_current_active_admin_user)
):
    """Optimize cache layout for better performance"""
    try:
        cache_manager = get_cache_manager()
        if not cache_manager:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Cache manager not available"
            )
        
        optimization_result = await cache_manager.optimize_cache_layout()
        
        return {
            "optimizations_applied": optimization_result.optimizations_applied,
            "space_saved_bytes": optimization_result.space_saved_bytes,
            "space_saved_mb": round(optimization_result.space_saved_bytes / (1024 * 1024), 2),
            "performance_improvement_ms": round(optimization_result.performance_improvement_ms, 2),
            "entries_relocated": optimization_result.entries_relocated,
            "entries_compressed": optimization_result.entries_compressed,
            "entries_evicted": optimization_result.entries_evicted
        }
        
    except Exception as e:
        logger.error(f"Error optimizing cache: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to optimize cache: {str(e)}"
        )


# Performance monitoring endpoints

@router.get("/performance/dashboard")
async def get_performance_dashboard(
    current_admin: User = Depends(get_current_active_admin_user)
):
    """Get performance monitoring dashboard data"""
    try:
        performance_monitor = get_performance_monitor()
        if not performance_monitor:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Performance monitor not available"
            )
        
        dashboard_data = await performance_monitor.get_performance_dashboard_data()
        
        return {
            "current_metrics": dashboard_data.current_metrics,
            "historical_trends": {
                metric: [(ts.isoformat(), value) for ts, value in trend]
                for metric, trend in dashboard_data.historical_trends.items()
            },
            "top_slow_queries": [
                {
                    "query_id": q.query_id,
                    "query": q.query[:200] + "..." if len(q.query) > 200 else q.query,
                    "duration_ms": q.duration_ms,
                    "database_type": q.database_type,
                    "user_id": q.user_id,
                    "project_id": q.project_id,
                    "start_time": q.start_time.isoformat() if q.start_time else None
                }
                for q in dashboard_data.top_slow_queries
            ],
            "recent_anomalies": [
                {
                    "anomaly_id": a.anomaly_id,
                    "type": a.anomaly_type.value,
                    "severity": a.severity.value,
                    "description": a.description,
                    "detected_at": a.detected_at.isoformat(),
                    "confidence_score": a.confidence_score
                }
                for a in dashboard_data.recent_anomalies
            ],
            "active_alerts": dashboard_data.active_alerts,
            "system_health": dashboard_data.system_health,
            "optimization_opportunities": [
                {
                    "recommendation_id": o.recommendation_id,
                    "type": o.type,
                    "description": o.description,
                    "estimated_improvement_percent": o.estimated_improvement_percent,
                    "priority": o.priority
                }
                for o in dashboard_data.optimization_opportunities
            ]
        }
        
    except Exception as e:
        logger.error(f"Error getting performance dashboard: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get performance dashboard: {str(e)}"
        )


@router.get("/performance/slow-queries")
async def get_slow_queries(
    limit: int = QueryParam(50, description="Maximum number of slow queries to return"),
    min_duration_ms: int = QueryParam(1000, description="Minimum duration in milliseconds"),
    current_admin: User = Depends(get_current_active_admin_user)
):
    """Get slow query analysis"""
    try:
        performance_monitor = get_performance_monitor()
        if not performance_monitor:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Performance monitor not available"
            )
        
        # Filter slow queries from execution history
        slow_queries = [
            execution for execution in performance_monitor.execution_history
            if execution.duration_ms and execution.duration_ms >= min_duration_ms
        ]
        
        # Sort by duration descending and limit results
        slow_queries.sort(key=lambda x: x.duration_ms or 0, reverse=True)
        slow_queries = slow_queries[:limit]
        
        return {
            "slow_queries": [
                {
                    "query_id": q.query_id,
                    "query": q.query[:500] + "..." if len(q.query) > 500 else q.query,
                    "duration_ms": q.duration_ms,
                    "database_type": q.database_type,
                    "user_id": q.user_id,
                    "project_id": q.project_id,
                    "cpu_usage_percent": q.cpu_usage_percent,
                    "memory_usage_mb": q.memory_usage_mb,
                    "rows_processed": q.rows_processed,
                    "rows_returned": q.rows_returned,
                    "cache_hit": q.cache_hit,
                    "optimization_applied": q.optimization_applied,
                    "start_time": q.start_time.isoformat() if q.start_time else None,
                    "error": q.error
                }
                for q in slow_queries
            ],
            "total_count": len(slow_queries),
            "average_duration_ms": sum(q.duration_ms for q in slow_queries if q.duration_ms) / len(slow_queries) if slow_queries else 0
        }
        
    except Exception as e:
        logger.error(f"Error getting slow queries: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get slow queries: {str(e)}"
        )


@router.post("/performance/create-alert")
async def create_performance_alert(
    request: PerformanceAlertRequest,
    current_admin: User = Depends(get_current_active_admin_user)
):
    """Create a performance monitoring alert"""
    try:
        performance_monitor = get_performance_monitor()
        if not performance_monitor:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Performance monitor not available"
            )
        
        # Create alert threshold
        threshold = AlertThreshold(
            metric_type=PerformanceMetricType(request.metric_type),
            threshold_value=request.threshold_value,
            comparison_operator=request.comparison_operator,
            window_minutes=request.window_minutes,
            min_occurrences=request.min_occurrences,
            severity=AlertSeverity(request.severity),
            notification_channels=['email']  # Default to email
        )
        
        alert = await performance_monitor.create_performance_alert(threshold)
        
        return {
            "alert_id": alert.alert_id,
            "threshold": {
                "metric_type": alert.threshold.metric_type.value,
                "threshold_value": alert.threshold.threshold_value,
                "comparison_operator": alert.threshold.comparison_operator,
                "window_minutes": alert.threshold.window_minutes,
                "severity": alert.threshold.severity.value
            },
            "description": alert.description,
            "current_value": alert.current_value,
            "triggered_at": alert.triggered_at.isoformat(),
            "suggested_actions": alert.suggested_actions
        }
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid alert configuration: {str(e)}"
        )
    except Exception as e:
        logger.error(f"Error creating performance alert: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create performance alert: {str(e)}"
        )


@router.get("/performance/alerts")
async def get_performance_alerts(
    active_only: bool = QueryParam(True, description="Return only active alerts"),
    current_admin: User = Depends(get_current_active_admin_user)
):
    """Get performance alerts"""
    try:
        performance_monitor = get_performance_monitor()
        if not performance_monitor:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Performance monitor not available"
            )
        
        if active_only:
            alerts = [
                alert for alert in performance_monitor.active_alerts.values()
                if not alert.resolved
            ]
        else:
            # Get recent alerts from history
            alerts = list(performance_monitor.alert_history)[-50:]  # Last 50 alerts
        
        return {
            "alerts": [
                {
                    "alert_id": alert.alert_id,
                    "metric_type": alert.threshold.metric_type.value,
                    "severity": alert.threshold.severity.value,
                    "description": alert.description,
                    "threshold_value": alert.threshold.threshold_value,
                    "current_value": alert.current_value,
                    "triggered_at": alert.triggered_at.isoformat(),
                    "acknowledged": alert.acknowledged,
                    "resolved": alert.resolved,
                    "suggested_actions": alert.suggested_actions
                }
                for alert in alerts
            ],
            "total_count": len(alerts)
        }
        
    except Exception as e:
        logger.error(f"Error getting performance alerts: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get performance alerts: {str(e)}"
        )


# Query execution endpoints

@router.get("/execution/metrics")
async def get_execution_metrics(
    current_admin: User = Depends(get_current_active_admin_user)
):
    """Get query execution metrics"""
    try:
        query_executor = get_query_executor()
        if not query_executor:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Query executor not available"
            )
        
        metrics = await query_executor.get_execution_metrics()
        
        return {
            "active_queries": metrics.active_queries,
            "queued_queries": metrics.queued_queries,
            "completed_queries_last_hour": metrics.completed_queries_last_hour,
            "failed_queries_last_hour": metrics.failed_queries_last_hour,
            "average_execution_time_ms": round(metrics.average_execution_time_ms, 2),
            "resource_utilization": {
                resource.value: round(utilization, 2)
                for resource, utilization in metrics.resource_utilization.items()
            },
            "queue_wait_time_ms": round(metrics.queue_wait_time_ms, 2),
            "system_load": round(metrics.system_load, 2),
            "connection_pool_usage": round(metrics.connection_pool_usage, 2)
        }
        
    except Exception as e:
        logger.error(f"Error getting execution metrics: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get execution metrics: {str(e)}"
        )


@router.get("/health")
async def get_optimization_health(
    current_admin: User = Depends(get_current_active_admin_user)
):
    """Get overall optimization system health"""
    try:
        health_status = {
            "optimization_engine": {
                "available": get_query_optimization_engine() is not None,
                "status": "healthy" if get_query_optimization_engine() else "unavailable"
            },
            "cache_manager": {
                "available": get_cache_manager() is not None,
                "status": "healthy" if get_cache_manager() else "unavailable"
            },
            "performance_monitor": {
                "available": get_performance_monitor() is not None,
                "status": "healthy" if get_performance_monitor() else "unavailable"
            },
            "query_executor": {
                "available": get_query_executor() is not None,
                "status": "healthy" if get_query_executor() else "unavailable"
            },
            "cache_integration": {
                "available": get_cache_integration_service() is not None,
                "status": "healthy" if get_cache_integration_service() else "unavailable"
            }
        }
        
        # Overall health score
        available_services = sum(1 for service in health_status.values() if service["available"])
        total_services = len(health_status)
        health_score = (available_services / total_services) * 100
        
        overall_status = "healthy" if health_score == 100 else "degraded" if health_score >= 60 else "unhealthy"
        
        return {
            "overall_status": overall_status,
            "health_score": health_score,
            "services": health_status,
            "checked_at": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error getting optimization health: {str(e)}")
        return {
            "overall_status": "unhealthy",
            "health_score": 0,
            "services": {},
            "error": str(e),
            "checked_at": datetime.now().isoformat()
        }