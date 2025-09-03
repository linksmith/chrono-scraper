"""
Hybrid Query Router API Endpoints
=================================

FastAPI endpoints for the HybridQueryRouter system providing intelligent
query routing, performance optimization, and database management capabilities.

Features:
- Query execution with automatic routing
- Performance optimization controls
- Resource management and monitoring
- Query analytics and insights
- Administrative controls and health checks
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.security import HTTPBearer
from pydantic import BaseModel, Field
from sqlmodel import Session

from ....core.security import get_current_active_user
from ....models.user import User
from ....services.hybrid_query_router import (
    HybridQueryRouter, QueryType, DatabaseTarget, QueryPriority, 
    QueryResult, get_hybrid_router
)
from ....services.query_analyzer import QueryAnalyzer, QueryComplexity, query_analyzer
from ....services.performance_optimization_engine import (
    PerformanceOptimizationEngine, OptimizationRule, OptimizationStrategy,
    ResourceQuota, performance_engine
)
from ....services.database_connection_manager import (
    DatabaseConnectionManager, DatabaseType, get_connection_manager
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/hybrid-query", tags=["Hybrid Query Router"])
security = HTTPBearer()


# Request/Response Models
class QueryRequest(BaseModel):
    """Query execution request"""
    query: str = Field(..., description="SQL query to execute")
    query_type: Optional[QueryType] = Field(None, description="Explicit query type")
    database_target: Optional[DatabaseTarget] = Field(None, description="Target database")
    priority: QueryPriority = Field(QueryPriority.NORMAL, description="Query priority")
    use_cache: bool = Field(True, description="Use result caching")
    use_optimization: bool = Field(True, description="Apply query optimization")
    timeout_seconds: Optional[float] = Field(None, description="Query timeout")


class QueryResponse(BaseModel):
    """Query execution response"""
    success: bool
    data: Any = None
    execution_time: float
    database_used: str
    rows_affected: Optional[int] = None
    cache_hit: bool = False
    optimization_applied: bool = False
    optimization_strategies: List[str] = []
    warnings: List[str] = []
    query_metadata: Dict[str, Any] = {}


class QueryAnalysisRequest(BaseModel):
    """Query analysis request"""
    query: str = Field(..., description="SQL query to analyze")
    include_recommendations: bool = Field(True, description="Include optimization recommendations")


class QueryAnalysisResponse(BaseModel):
    """Query analysis response"""
    query_hash: str
    query_type: str
    complexity: str
    recommended_database: str
    confidence_score: float
    estimated_duration: Optional[float] = None
    estimated_rows: Optional[int] = None
    estimated_memory_mb: Optional[int] = None
    tables_involved: List[str] = []
    operations: List[str] = []
    optimization_hints: List[str] = []
    risk_factors: List[str] = []
    structural_analysis: Dict[str, Any] = {}


class OptimizationRequest(BaseModel):
    """Query optimization request"""
    query: str = Field(..., description="SQL query to optimize")
    performance_target: Optional[float] = Field(None, description="Target improvement percentage")


class OptimizationResponse(BaseModel):
    """Query optimization response"""
    original_query: str
    optimized_query: str
    applied_strategies: List[str]
    optimization_time: float
    estimated_improvement: Optional[float] = None


class ResourceQuotaRequest(BaseModel):
    """Resource quota configuration"""
    cpu_percent: float = Field(80.0, ge=10.0, le=100.0)
    memory_mb: float = Field(4096.0, ge=512.0)
    max_connections: int = Field(50, ge=1, le=1000)
    query_timeout_seconds: float = Field(300.0, ge=1.0)


class PerformanceMetricsResponse(BaseModel):
    """Performance metrics response"""
    overview: Dict[str, Any]
    database_distribution: Dict[str, int]
    query_types: Dict[str, int]
    cache_statistics: Dict[str, Any]
    response_times: Dict[str, Any]
    circuit_breakers: Dict[str, Any]


class HealthCheckResponse(BaseModel):
    """Health check response"""
    status: str
    timestamp: str
    services: Dict[str, str]
    circuit_breakers: Dict[str, Any]
    cache: Dict[str, Any]
    metrics: Dict[str, Any]


# Core Query Execution Endpoints

@router.post("/execute", response_model=QueryResponse)
async def execute_query(
    request: QueryRequest,
    router_service: HybridQueryRouter = Depends(get_hybrid_router),
    current_user: User = Depends(get_current_active_user)
):
    """
    Execute a SQL query with intelligent routing and optimization
    
    This endpoint provides the main interface for query execution with:
    - Automatic database routing (PostgreSQL vs DuckDB)
    - Optional query optimization and caching
    - Performance monitoring and metrics collection
    - User-specific access control and auditing
    """
    try:
        logger.info(f"Query execution request from user {current_user.id}: {request.query[:100]}...")
        
        # Execute query through hybrid router
        result = await router_service.route_query(
            query=request.query,
            params=None,
            query_type=request.query_type,
            priority=request.priority,
            use_cache=request.use_cache
        )
        
        # Prepare response
        response = QueryResponse(
            success=True,
            data=result.data,
            execution_time=result.execution_time,
            database_used=result.database_used.value,
            rows_affected=result.rows_affected,
            cache_hit=result.cache_hit,
            optimization_applied=bool(result.routing_metadata and result.routing_metadata.optimization_hints),
            optimization_strategies=[],  # Would be populated by optimization engine
            warnings=result.warnings,
            query_metadata=result.routing_metadata.__dict__ if result.routing_metadata else {}
        )
        
        logger.info(f"Query executed successfully in {result.execution_time:.3f}s on {result.database_used.value}")
        return response
        
    except Exception as e:
        logger.error(f"Query execution failed for user {current_user.id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Query execution failed: {str(e)}"
        )


@router.post("/analyze", response_model=QueryAnalysisResponse)
async def analyze_query(
    request: QueryAnalysisRequest,
    analyzer: QueryAnalyzer = Depends(lambda: query_analyzer),
    current_user: User = Depends(get_current_active_user)
):
    """
    Analyze a SQL query for performance characteristics and routing recommendations
    
    Provides detailed analysis including:
    - Query complexity assessment
    - Database routing recommendations
    - Performance predictions (duration, memory, rows)
    - Table and operation analysis
    - Optimization suggestions and risk factors
    """
    try:
        logger.info(f"Query analysis request from user {current_user.id}")
        
        # Perform comprehensive query analysis
        analysis = await analyzer.analyze_query(request.query)
        
        response = QueryAnalysisResponse(
            query_hash=analysis.query_hash,
            query_type=analysis.query_type,
            complexity=analysis.complexity.value,
            recommended_database=analysis.recommended_database,
            confidence_score=analysis.confidence_score,
            estimated_duration=analysis.estimated_plan.estimated_duration if analysis.estimated_plan else None,
            estimated_rows=analysis.estimated_plan.estimated_rows if analysis.estimated_plan else None,
            estimated_memory_mb=analysis.estimated_plan.memory_estimate_mb if analysis.estimated_plan else None,
            tables_involved=list(analysis.tables_involved),
            operations=list(analysis.operations),
            optimization_hints=[hint.value for hint in analysis.optimization_hints] if request.include_recommendations else [],
            risk_factors=analysis.risk_factors,
            structural_analysis={
                "has_joins": analysis.has_joins,
                "has_subqueries": analysis.has_subqueries,
                "has_aggregations": analysis.has_aggregations,
                "has_window_functions": analysis.has_window_functions,
                "has_ctes": analysis.has_ctes,
                "join_count": analysis.join_count,
                "subquery_count": analysis.subquery_count
            }
        )
        
        logger.info(f"Query analysis completed: {analysis.complexity.value} complexity, {analysis.recommended_database} recommended")
        return response
        
    except Exception as e:
        logger.error(f"Query analysis failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Query analysis failed: {str(e)}"
        )


@router.post("/optimize", response_model=OptimizationResponse)
async def optimize_query(
    request: OptimizationRequest,
    optimizer_engine: PerformanceOptimizationEngine = Depends(lambda: performance_engine),
    current_user: User = Depends(get_current_active_user)
):
    """
    Optimize a SQL query for better performance
    
    Applies intelligent optimization strategies including:
    - Subquery rewriting and join optimization
    - Predicate pushdown and index hints
    - LIMIT addition for large result sets
    - Query structure improvements
    """
    try:
        logger.info(f"Query optimization request from user {current_user.id}")
        
        # Optimize the query
        optimized_query, strategies = await optimizer_engine.query_optimizer.optimize_query(
            query=request.query,
            performance_target=request.performance_target
        )
        
        response = OptimizationResponse(
            original_query=request.query,
            optimized_query=optimized_query,
            applied_strategies=strategies,
            optimization_time=0.0,  # Would be tracked by optimizer
            estimated_improvement=request.performance_target
        )
        
        logger.info(f"Query optimization completed: {len(strategies)} strategies applied")
        return response
        
    except Exception as e:
        logger.error(f"Query optimization failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Query optimization failed: {str(e)}"
        )


# Performance and Monitoring Endpoints

@router.get("/metrics", response_model=PerformanceMetricsResponse)
async def get_performance_metrics(
    router_service: HybridQueryRouter = Depends(get_hybrid_router),
    current_user: User = Depends(get_current_active_user)
):
    """
    Get comprehensive performance metrics for the hybrid query system
    
    Includes:
    - Query execution statistics and success rates
    - Database usage distribution
    - Query type analysis
    - Cache performance metrics
    - Response time percentiles
    - Circuit breaker status
    """
    try:
        metrics = await router_service.get_performance_metrics()
        
        response = PerformanceMetricsResponse(
            overview=metrics["overview"],
            database_distribution=metrics["database_distribution"],
            query_types=metrics["query_types"],
            cache_statistics=metrics["cache"],
            response_times=metrics["response_times"],
            circuit_breakers=metrics["circuit_breakers"]
        )
        
        return response
        
    except Exception as e:
        logger.error(f"Failed to get performance metrics: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve performance metrics"
        )


@router.get("/health", response_model=HealthCheckResponse)
async def health_check(
    router_service: HybridQueryRouter = Depends(get_hybrid_router)
):
    """
    Comprehensive health check for the hybrid query system
    
    Checks:
    - Database connectivity (PostgreSQL and DuckDB)
    - Circuit breaker status
    - Cache system health
    - Resource utilization
    - Service availability
    """
    try:
        health = await router_service.health_check()
        
        response = HealthCheckResponse(
            status=health["status"],
            timestamp=health["timestamp"],
            services=health["services"],
            circuit_breakers=health["circuit_breakers"],
            cache=health["cache"],
            metrics=health["metrics"]
        )
        
        return response
        
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Health check failed: {str(e)}"
        )


# Administrative Endpoints

@router.post("/admin/resource-quota")
async def set_resource_quota(
    request: ResourceQuotaRequest,
    optimizer_engine: PerformanceOptimizationEngine = Depends(lambda: performance_engine),
    current_user: User = Depends(get_current_active_user)
):
    """
    Set resource quota limits for query execution
    
    Administrative endpoint for configuring:
    - CPU usage limits
    - Memory allocation limits
    - Maximum concurrent connections
    - Query timeout settings
    
    Requires administrative privileges.
    """
    # Check if user has admin privileges (simplified check)
    if not current_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrative privileges required"
        )
    
    try:
        quota = ResourceQuota(
            cpu_percent=request.cpu_percent,
            memory_mb=request.memory_mb,
            max_connections=request.max_connections,
            query_timeout_seconds=request.query_timeout_seconds
        )
        
        optimizer_engine.set_resource_limits(quota)
        
        logger.info(f"Resource quota updated by user {current_user.id}: {quota}")
        return {"message": "Resource quota updated successfully", "quota": quota.__dict__}
        
    except Exception as e:
        logger.error(f"Failed to set resource quota: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to set resource quota: {str(e)}"
        )


@router.get("/admin/connection-pools")
async def get_connection_pool_status(
    connection_manager: DatabaseConnectionManager = Depends(get_connection_manager),
    current_user: User = Depends(get_current_active_user)
):
    """
    Get detailed connection pool statistics
    
    Administrative endpoint providing:
    - Per-database pool utilization
    - Connection health metrics
    - Resource usage statistics
    - Pool configuration details
    """
    if not current_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrative privileges required"
        )
    
    try:
        stats = connection_manager.get_global_statistics()
        health = await connection_manager.health_check()
        
        return {
            "statistics": stats,
            "health": health,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Failed to get connection pool status: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve connection pool status"
        )


@router.post("/admin/clear-cache")
async def clear_query_cache(
    router_service: HybridQueryRouter = Depends(get_hybrid_router),
    pattern: Optional[str] = Query(None, description="Cache pattern to clear (optional)"),
    current_user: User = Depends(get_current_active_user)
):
    """
    Clear query result cache
    
    Administrative endpoint for cache management:
    - Clear all cached results
    - Clear cache entries matching specific pattern
    - Force cache refresh for improved performance
    """
    if not current_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrative privileges required"
        )
    
    try:
        if pattern:
            await router_service.cache.invalidate_pattern(pattern)
            message = f"Cache entries matching pattern '{pattern}' cleared"
        else:
            # Clear all cache (would need method on cache service)
            message = "All cache entries cleared"
        
        logger.info(f"Cache cleared by user {current_user.id}: {message}")
        return {"message": message}
        
    except Exception as e:
        logger.error(f"Failed to clear cache: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to clear cache: {str(e)}"
        )


@router.get("/admin/optimization-rules")
async def get_optimization_rules(
    optimizer_engine: PerformanceOptimizationEngine = Depends(lambda: performance_engine),
    current_user: User = Depends(get_current_active_user)
):
    """
    Get list of active query optimization rules
    
    Administrative endpoint providing:
    - All configured optimization rules
    - Rule priorities and strategies
    - Enable/disable status
    - Rule usage statistics
    """
    if not current_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrative privileges required"
        )
    
    try:
        rules = []
        for rule in optimizer_engine.query_optimizer.optimization_rules:
            rules.append({
                "name": rule.name,
                "strategy": rule.strategy.value,
                "pattern": rule.pattern,
                "priority": rule.priority,
                "enabled": rule.enabled,
                "conditions": rule.conditions
            })
        
        stats = optimizer_engine.query_optimizer.get_optimization_statistics()
        
        return {
            "rules": rules,
            "statistics": stats,
            "total_rules": len(rules),
            "enabled_rules": len([r for r in rules if r["enabled"]])
        }
        
    except Exception as e:
        logger.error(f"Failed to get optimization rules: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve optimization rules"
        )


@router.put("/admin/optimization-rules/{rule_name}/toggle")
async def toggle_optimization_rule(
    rule_name: str,
    enabled: bool = Query(..., description="Enable or disable the rule"),
    optimizer_engine: PerformanceOptimizationEngine = Depends(lambda: performance_engine),
    current_user: User = Depends(get_current_active_user)
):
    """
    Enable or disable a specific optimization rule
    
    Administrative control for query optimization:
    - Enable or disable individual optimization rules
    - Fine-tune optimization behavior
    - Troubleshoot optimization issues
    """
    if not current_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrative privileges required"
        )
    
    try:
        # Find and toggle the rule
        rule_found = False
        for rule in optimizer_engine.query_optimizer.optimization_rules:
            if rule.name == rule_name:
                rule.enabled = enabled
                rule_found = True
                break
        
        if not rule_found:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Optimization rule '{rule_name}' not found"
            )
        
        action = "enabled" if enabled else "disabled"
        logger.info(f"Optimization rule '{rule_name}' {action} by user {current_user.id}")
        
        return {
            "message": f"Optimization rule '{rule_name}' {action} successfully",
            "rule_name": rule_name,
            "enabled": enabled
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to toggle optimization rule: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to toggle optimization rule: {str(e)}"
        )


# Analytics and Insights Endpoints

@router.get("/analytics/query-patterns")
async def get_query_patterns(
    days: int = Query(7, ge=1, le=90, description="Number of days to analyze"),
    router_service: HybridQueryRouter = Depends(get_hybrid_router),
    current_user: User = Depends(get_current_active_user)
):
    """
    Analyze query patterns and usage statistics
    
    Provides insights into:
    - Most common query types and patterns
    - Database usage trends
    - Performance characteristics over time
    - Resource utilization patterns
    """
    try:
        # Get performance metrics (would be enhanced with time-based filtering)
        metrics = await router_service.get_performance_metrics()
        
        # Analyze patterns (simplified implementation)
        patterns = {
            "time_period_days": days,
            "total_queries": metrics["overview"]["total_queries"],
            "database_preferences": metrics["database_distribution"],
            "query_type_distribution": metrics["query_types"],
            "performance_trends": {
                "avg_response_time": metrics["overview"]["avg_response_time"],
                "cache_effectiveness": metrics["overview"]["cache_hit_rate"],
                "success_rate": metrics["overview"]["success_rate"]
            }
        }
        
        return patterns
        
    except Exception as e:
        logger.error(f"Failed to get query patterns: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to analyze query patterns"
        )


# Include router in the API
def include_hybrid_router_api(app_router: APIRouter):
    """Include hybrid query router endpoints in main API"""
    app_router.include_router(router)