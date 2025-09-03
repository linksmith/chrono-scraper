"""
Admin Performance Optimization API Endpoints

This module provides comprehensive API endpoints for database performance monitoring,
query optimization, and cache management specifically for admin operations.
"""

import logging
from datetime import datetime
from typing import Dict, List, Optional, Any
from fastapi import APIRouter, Depends, HTTPException, Query, Body
from fastapi.security import HTTPBearer
from pydantic import BaseModel, Field

from app.core.auth import get_current_superuser
from app.models.user import User
from app.services.performance_integration import get_performance_integration

logger = logging.getLogger(__name__)
security = HTTPBearer()

router = APIRouter()


# Request/Response Models
class QueryAnalysisRequest(BaseModel):
    """Request model for query analysis"""
    query: str = Field(..., description="SQL query to analyze")
    params: Optional[Dict[str, Any]] = Field(None, description="Query parameters")
    execution_time_ms: Optional[float] = Field(None, description="Actual execution time if known")


class CacheWarmupRequest(BaseModel):
    """Request model for cache warmup"""
    namespace: Optional[str] = Field(None, description="Specific namespace to warm")
    force: bool = Field(False, description="Force warmup even if recently warmed")


class CacheClearRequest(BaseModel):
    """Request model for cache clearing"""
    pattern: Optional[str] = Field(None, description="Pattern to match for selective clearing")
    confirm: bool = Field(False, description="Confirmation flag for destructive operations")


class PerformanceOptimizationResponse(BaseModel):
    """Response model for performance optimization results"""
    timestamp: datetime
    status: str
    message: str
    data: Optional[Dict[str, Any]] = None
    recommendations: Optional[List[str]] = None


class HealthCheckResponse(BaseModel):
    """Response model for health check"""
    overall_healthy: bool
    timestamp: datetime
    services: Dict[str, Any]
    issues: List[str]
    health_score: Optional[int] = None


# Performance Dashboard Endpoints

@router.get("/dashboard", response_model=Dict[str, Any])
async def get_performance_dashboard(
    current_user: User = Depends(get_current_superuser)
) -> Dict[str, Any]:
    """
    Get comprehensive performance dashboard data for admin interface.
    
    Returns real-time metrics, database statistics, cache performance,
    and optimization recommendations.
    """
    try:
        performance_service = await get_performance_integration()
        dashboard_data = await performance_service.get_performance_dashboard_data()
        
        return {
            "status": "success",
            "data": dashboard_data,
            "generated_at": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error getting performance dashboard data: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get performance dashboard data: {str(e)}"
        )


@router.get("/health", response_model=HealthCheckResponse)
async def get_performance_health(
    current_user: User = Depends(get_current_superuser)
) -> HealthCheckResponse:
    """
    Comprehensive health check of all performance optimization services.
    
    Checks database performance, cache services, Redis connectivity,
    and overall system health.
    """
    try:
        performance_service = await get_performance_integration()
        health_status = await performance_service.comprehensive_health_check()
        
        return HealthCheckResponse(**health_status)
        
    except Exception as e:
        logger.error(f"Error performing performance health check: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Health check failed: {str(e)}"
        )


# Database Performance Endpoints

@router.get("/database/stats")
async def get_database_stats(
    current_user: User = Depends(get_current_superuser)
) -> Dict[str, Any]:
    """
    Get detailed database performance statistics.
    
    Returns connection stats, cache hit ratios, index usage,
    and performance metrics.
    """
    try:
        performance_service = await get_performance_integration()
        
        if not performance_service.performance_monitor:
            raise HTTPException(
                status_code=503,
                detail="Performance monitoring service not available"
            )
        
        db_stats = await performance_service.performance_monitor.get_database_stats()
        table_stats = await performance_service.performance_monitor.get_table_stats()
        index_stats = await performance_service.performance_monitor.get_index_stats()
        
        return {
            "status": "success",
            "data": {
                "database_stats": db_stats.dict(),
                "table_stats": [ts.dict() for ts in table_stats],
                "index_stats": [idx.dict() for idx in index_stats],
                "timestamp": datetime.now().isoformat()
            }
        }
        
    except Exception as e:
        logger.error(f"Error getting database stats: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get database stats: {str(e)}"
        )


@router.get("/database/slow-queries")
async def get_slow_queries(
    hours: int = Query(24, ge=1, le=168, description="Hours to look back for slow queries"),
    current_user: User = Depends(get_current_superuser)
) -> Dict[str, Any]:
    """
    Get analysis of slow queries from recent performance monitoring.
    
    Provides detailed analysis of slow queries with optimization suggestions.
    """
    try:
        performance_service = await get_performance_integration()
        slow_queries = await performance_service.get_slow_queries(hours=hours)
        
        return {
            "status": "success",
            "data": {
                "slow_queries": [sq.dict() for sq in slow_queries],
                "analysis_period_hours": hours,
                "total_slow_queries": len(slow_queries),
                "timestamp": datetime.now().isoformat()
            }
        }
        
    except Exception as e:
        logger.error(f"Error getting slow queries: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get slow queries analysis: {str(e)}"
        )


# Query Optimization Endpoints

@router.post("/query/analyze")
async def analyze_query(
    request: QueryAnalysisRequest,
    current_user: User = Depends(get_current_superuser)
) -> Dict[str, Any]:
    """
    Analyze a specific SQL query for performance optimization.
    
    Returns execution plan analysis, performance issues identification,
    and specific optimization recommendations.
    """
    try:
        performance_service = await get_performance_integration()
        
        analysis = await performance_service.optimize_query(
            query=request.query,
            params=request.params
        )
        
        return {
            "status": "success",
            "data": {
                "query_hash": analysis.query_hash,
                "original_query": analysis.original_query,
                "execution_plan": analysis.execution_plan,
                "estimated_cost": analysis.estimated_cost,
                "actual_time_ms": analysis.actual_time_ms,
                "performance_issues": analysis.performance_issues,
                "optimization_suggestions": analysis.optimization_suggestions,
                "optimized_query": analysis.optimized_query,
                "missing_indexes": analysis.missing_indexes,
                "tables_accessed": analysis.tables_accessed,
                "indexes_used": analysis.indexes_used,
                "timestamp": analysis.timestamp.isoformat()
            }
        }
        
    except Exception as e:
        logger.error(f"Error analyzing query: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Query analysis failed: {str(e)}"
        )


@router.get("/query/recommendations")
async def get_query_optimization_recommendations(
    table_name: Optional[str] = Query(None, description="Filter by specific table"),
    current_user: User = Depends(get_current_superuser)
) -> Dict[str, Any]:
    """
    Get comprehensive query optimization recommendations.
    
    Returns system-wide optimization suggestions based on performance analysis.
    """
    try:
        performance_service = await get_performance_integration()
        
        if not performance_service.query_optimizer:
            raise HTTPException(
                status_code=503,
                detail="Query optimization service not available"
            )
        
        recommendations = await performance_service.query_optimizer.get_optimization_recommendations(
            table_name=table_name
        )
        
        return {
            "status": "success",
            "data": {
                "recommendations": [rec.dict() for rec in recommendations],
                "total_recommendations": len(recommendations),
                "filtered_by_table": table_name,
                "timestamp": datetime.now().isoformat()
            }
        }
        
    except Exception as e:
        logger.error(f"Error getting optimization recommendations: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get optimization recommendations: {str(e)}"
        )


# Cache Management Endpoints

@router.get("/cache/stats")
async def get_cache_stats(
    current_user: User = Depends(get_current_superuser)
) -> Dict[str, Any]:
    """
    Get detailed cache performance statistics and metrics.
    
    Returns cache hit ratios, memory usage, and performance by namespace.
    """
    try:
        performance_service = await get_performance_integration()
        
        if not performance_service.cache_service:
            raise HTTPException(
                status_code=503,
                detail="Cache service not available"
            )
        
        cache_info = await performance_service.cache_service.get_cache_info()
        cache_metrics = await performance_service.cache_service.get_metrics()
        
        return {
            "status": "success",
            "data": {
                "cache_info": cache_info,
                "metrics_by_namespace": cache_metrics,
                "timestamp": datetime.now().isoformat()
            }
        }
        
    except Exception as e:
        logger.error(f"Error getting cache stats: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get cache stats: {str(e)}"
        )


@router.post("/cache/warm")
async def warm_cache(
    request: CacheWarmupRequest,
    current_user: User = Depends(get_current_superuser)
) -> PerformanceOptimizationResponse:
    """
    Manually trigger cache warming for improved performance.
    
    Warms frequently accessed admin data into cache layers.
    """
    try:
        performance_service = await get_performance_integration()
        
        result = await performance_service.warm_cache(namespace=request.namespace)
        
        return PerformanceOptimizationResponse(
            timestamp=datetime.now(),
            status="success",
            message=result["message"],
            data={"namespace": request.namespace, "force": request.force}
        )
        
    except Exception as e:
        logger.error(f"Error warming cache: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Cache warmup failed: {str(e)}"
        )


@router.post("/cache/clear")
async def clear_cache(
    request: CacheClearRequest,
    current_user: User = Depends(get_current_superuser)
) -> PerformanceOptimizationResponse:
    """
    Clear cache entries with optional pattern matching.
    
    WARNING: This can impact performance until cache is warmed again.
    """
    if not request.confirm:
        raise HTTPException(
            status_code=400,
            detail="Cache clearing requires confirmation flag to be set"
        )
    
    try:
        performance_service = await get_performance_integration()
        
        result = await performance_service.clear_caches(pattern=request.pattern)
        
        return PerformanceOptimizationResponse(
            timestamp=datetime.now(),
            status=result["status"],
            message=result.get("message", "Cache cleared successfully"),
            data={
                "pattern": request.pattern,
                "cleared_keys": result.get("cleared_keys", 0)
            }
        )
        
    except Exception as e:
        logger.error(f"Error clearing cache: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Cache clearing failed: {str(e)}"
        )


# System Optimization Endpoints

@router.get("/system/status")
async def get_system_performance_status(
    current_user: User = Depends(get_current_superuser)
) -> Dict[str, Any]:
    """
    Get comprehensive system performance status and service information.
    """
    try:
        performance_service = await get_performance_integration()
        
        service_status = performance_service.get_service_status()
        health_status = await performance_service.comprehensive_health_check()
        
        return {
            "status": "success",
            "data": {
                "service_status": service_status,
                "health_status": health_status,
                "timestamp": datetime.now().isoformat()
            }
        }
        
    except Exception as e:
        logger.error(f"Error getting system performance status: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get system status: {str(e)}"
        )


@router.post("/system/optimize")
async def run_system_optimization(
    force: bool = Body(False, description="Force optimization even if recently run"),
    current_user: User = Depends(get_current_superuser)
) -> PerformanceOptimizationResponse:
    """
    Run comprehensive system optimization including cache warming,
    performance analysis, and cleanup operations.
    """
    try:
        performance_service = await get_performance_integration()
        
        optimization_results = []
        
        # Warm caches
        cache_result = await performance_service.warm_cache()
        optimization_results.append(f"Cache warming: {cache_result['message']}")
        
        # Get performance summary
        if performance_service.performance_monitor:
            summary = await performance_service.performance_monitor.get_performance_summary()
            optimization_results.append(f"Health score: {summary.get('health_score', 'unknown')}")
        
        # Get optimization recommendations
        if performance_service.query_optimizer:
            recommendations = await performance_service.query_optimizer.get_optimization_recommendations()
            optimization_results.append(f"Found {len(recommendations)} optimization opportunities")
        
        return PerformanceOptimizationResponse(
            timestamp=datetime.now(),
            status="success",
            message="System optimization completed successfully",
            data={
                "force": force,
                "results": optimization_results
            },
            recommendations=optimization_results
        )
        
    except Exception as e:
        logger.error(f"Error running system optimization: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"System optimization failed: {str(e)}"
        )


# Performance Metrics Endpoints

@router.get("/metrics/summary")
async def get_performance_metrics_summary(
    hours: int = Query(1, ge=1, le=72, description="Hours to summarize metrics for"),
    current_user: User = Depends(get_current_superuser)
) -> Dict[str, Any]:
    """
    Get performance metrics summary for the specified time period.
    """
    try:
        performance_service = await get_performance_integration()
        
        summary_data = {}
        
        # Get performance summary
        if performance_service.performance_monitor:
            summary = await performance_service.performance_monitor.get_performance_summary()
            summary_data["performance_summary"] = summary
        
        # Get cache metrics
        if performance_service.cache_service:
            cache_metrics = await performance_service.cache_service.get_metrics()
            summary_data["cache_metrics"] = cache_metrics
        
        return {
            "status": "success",
            "data": {
                "metrics": summary_data,
                "time_period_hours": hours,
                "timestamp": datetime.now().isoformat()
            }
        }
        
    except Exception as e:
        logger.error(f"Error getting performance metrics summary: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get performance metrics: {str(e)}"
        )


@router.get("/metrics/trends")
async def get_performance_trends(
    days: int = Query(7, ge=1, le=30, description="Days to analyze for trends"),
    current_user: User = Depends(get_current_superuser)
) -> Dict[str, Any]:
    """
    Get performance trends and analysis over time.
    
    NOTE: This would require historical data storage in a real implementation.
    """
    try:
        # This is a placeholder for trend analysis
        # In a real implementation, you would store historical metrics
        # and analyze trends over time
        
        trend_data = {
            "database_performance": {
                "avg_query_time_trend": "improving",
                "cache_hit_ratio_trend": "stable",
                "slow_queries_trend": "decreasing"
            },
            "cache_performance": {
                "hit_ratio_trend": "improving",
                "memory_usage_trend": "stable",
                "response_time_trend": "improving"
            },
            "system_health": {
                "overall_trend": "stable",
                "health_score_trend": "improving"
            },
            "note": "Trend analysis requires historical data collection (not yet implemented)"
        }
        
        return {
            "status": "success",
            "data": {
                "trends": trend_data,
                "analysis_period_days": days,
                "timestamp": datetime.now().isoformat()
            }
        }
        
    except Exception as e:
        logger.error(f"Error getting performance trends: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get performance trends: {str(e)}"
        )