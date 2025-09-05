"""
DuckDB Analytics API endpoints for operational monitoring and analytics queries
"""
from datetime import datetime
from typing import Any, Dict, List, Optional, Union
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from ....services.duckdb_service import (
    DuckDBService, 
    get_duckdb_service,
    DuckDBException,
    QueryResult
)
from ...deps import get_current_active_user
from ....models.user import User

router = APIRouter()


# Request/Response Models
class AnalyticsQueryRequest(BaseModel):
    """Request model for analytics query execution"""
    query: str = Field(..., description="SQL query to execute", min_length=1, max_length=10000)
    params: Optional[Dict[str, Any]] = Field(None, description="Query parameters")
    fetch_mode: str = Field("all", description="Fetch mode: 'all', 'one', 'many', or 'none'")
    timeout_seconds: Optional[int] = Field(30, description="Query timeout in seconds", ge=1, le=300)


class BatchQueryRequest(BaseModel):
    """Request model for batch query execution"""
    queries: List[str] = Field(..., description="List of SQL queries to execute", min_items=1, max_items=10)
    use_transaction: bool = Field(True, description="Execute queries in a transaction")


class QueryResponse(BaseModel):
    """Response model for query results"""
    data: Any = Field(..., description="Query result data")
    execution_time: float = Field(..., description="Execution time in seconds")
    memory_usage: float = Field(..., description="Memory usage in MB")
    row_count: Optional[int] = Field(None, description="Number of rows returned")
    columns: Optional[List[str]] = Field(None, description="Column names")
    query_hash: Optional[str] = Field(None, description="Query hash for caching")


class BatchQueryResponse(BaseModel):
    """Response model for batch query results"""
    results: List[QueryResponse] = Field(..., description="List of query results")
    total_queries: int = Field(..., description="Total number of queries executed")
    total_execution_time: float = Field(..., description="Total execution time in seconds")
    success_count: int = Field(..., description="Number of successful queries")


class ServiceHealthResponse(BaseModel):
    """Response model for service health check"""
    status: str = Field(..., description="Health status: 'healthy', 'unhealthy', 'not_initialized'")
    timestamp: str = Field(..., description="Health check timestamp")
    service_initialized: bool = Field(..., description="Whether service is initialized")
    database_path: str = Field(..., description="Database file path")
    database_exists: bool = Field(..., description="Whether database file exists")
    database_size_mb: Optional[float] = Field(None, description="Database size in MB")
    query_test: Optional[Dict[str, Any]] = Field(None, description="Query test results")
    connection_pool: Optional[Dict[str, Any]] = Field(None, description="Connection pool status")
    circuit_breaker: Dict[str, Any] = Field(..., description="Circuit breaker status")
    metrics: Dict[str, Any] = Field(..., description="Service metrics")
    system: Dict[str, Any] = Field(..., description="System metrics")
    errors: List[str] = Field(..., description="Error messages")


class ServiceStatisticsResponse(BaseModel):
    """Response model for service statistics"""
    service: Dict[str, Any] = Field(..., description="Service information")
    metrics: Dict[str, Any] = Field(..., description="Performance metrics")
    performance: Dict[str, Any] = Field(..., description="Performance analysis")
    system: Dict[str, Any] = Field(..., description="System resource metrics")
    circuit_breaker: Dict[str, Any] = Field(..., description="Circuit breaker status")
    database_file: Optional[Dict[str, Any]] = Field(None, description="Database file information")
    query_analysis: Optional[Dict[str, Any]] = Field(None, description="Query performance analysis")


# Health Check Endpoints (No authentication required for monitoring)
@router.get(
    "/health",
    response_model=ServiceHealthResponse,
    summary="DuckDB Service Health Check",
    description="Get comprehensive health status of the DuckDB analytics service"
)
async def get_health(
    service: DuckDBService = Depends(get_duckdb_service)
) -> ServiceHealthResponse:
    """
    Get comprehensive health status of the DuckDB analytics service.
    
    This endpoint is used by monitoring systems and load balancers to check
    service availability and performance.
    """
    try:
        health_data = await service.health_check()
        return ServiceHealthResponse(**health_data)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Health check failed: {str(e)}"
        )


@router.get(
    "/statistics",
    response_model=ServiceStatisticsResponse,
    summary="DuckDB Service Statistics",
    description="Get detailed performance statistics and metrics"
)
async def get_statistics(
    current_user: User = Depends(get_current_active_user),
    service: DuckDBService = Depends(get_duckdb_service)
) -> ServiceStatisticsResponse:
    """
    Get detailed performance statistics and metrics for the DuckDB service.
    
    Requires authentication as this endpoint provides detailed system information.
    """
    try:
        stats_data = await service.get_statistics()
        return ServiceStatisticsResponse(**stats_data)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Statistics collection failed: {str(e)}"
        )


# Analytics Query Endpoints (Authentication required)
@router.post(
    "/query",
    response_model=QueryResponse,
    summary="Execute Analytics Query",
    description="Execute a SQL query against the DuckDB analytics database"
)
async def execute_query(
    request: AnalyticsQueryRequest,
    current_user: User = Depends(get_current_active_user),
    service: DuckDBService = Depends(get_duckdb_service)
) -> QueryResponse:
    """
    Execute a SQL query against the DuckDB analytics database.
    
    Supports parameterized queries and different fetch modes for optimal performance.
    """
    try:
        result = await service.execute_query(
            query=request.query,
            params=request.params,
            fetch_mode=request.fetch_mode
        )
        
        if result is None:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Query execution returned no result"
            )
        
        return QueryResponse(
            data=result.data,
            execution_time=result.execution_time,
            memory_usage=result.memory_usage,
            row_count=result.row_count,
            columns=result.columns,
            query_hash=result.query_hash
        )
        
    except DuckDBException as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Query execution failed: {str(e)}"
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Unexpected error: {str(e)}"
        )


@router.post(
    "/batch",
    response_model=BatchQueryResponse,
    summary="Execute Batch Queries",
    description="Execute multiple SQL queries in batch with transaction support"
)
async def execute_batch(
    request: BatchQueryRequest,
    current_user: User = Depends(get_current_active_user),
    service: DuckDBService = Depends(get_duckdb_service)
) -> BatchQueryResponse:
    """
    Execute multiple SQL queries in batch with transaction support.
    
    All queries are executed within a single transaction by default,
    ensuring atomicity of the batch operation.
    """
    try:
        results = await service.execute_batch(request.queries)
        
        # Convert results to response format
        query_responses = []
        total_execution_time = 0.0
        success_count = 0
        
        for result in results:
            if result:
                query_responses.append(QueryResponse(
                    data=result.data,
                    execution_time=result.execution_time,
                    memory_usage=result.memory_usage,
                    row_count=result.row_count,
                    columns=result.columns,
                    query_hash=result.query_hash
                ))
                total_execution_time += result.execution_time
                success_count += 1
        
        return BatchQueryResponse(
            results=query_responses,
            total_queries=len(request.queries),
            total_execution_time=total_execution_time,
            success_count=success_count
        )
        
    except DuckDBException as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Batch execution failed: {str(e)}"
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Unexpected error: {str(e)}"
        )


# Operational Endpoints
@router.post(
    "/initialize",
    summary="Initialize DuckDB Service",
    description="Initialize the DuckDB service (admin operation)"
)
async def initialize_service(
    current_user: User = Depends(get_current_active_user),
    service: DuckDBService = Depends(get_duckdb_service)
) -> Dict[str, str]:
    """
    Initialize the DuckDB service.
    
    This endpoint allows manual initialization of the service if needed.
    Normally the service is initialized automatically on first use.
    """
    try:
        await service.initialize()
        return {"status": "success", "message": "DuckDB service initialized successfully"}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Service initialization failed: {str(e)}"
        )


@router.post(
    "/circuit-breaker/reset",
    summary="Reset Circuit Breaker",
    description="Reset the circuit breaker to closed state (admin operation)"
)
async def reset_circuit_breaker(
    current_user: User = Depends(get_current_active_user),
    service: DuckDBService = Depends(get_duckdb_service)
) -> Dict[str, str]:
    """
    Reset the circuit breaker to closed state.
    
    This endpoint allows manual recovery from circuit breaker open state
    in case of temporary issues that have been resolved.
    """
    try:
        service.circuit_breaker.force_closed("Manual reset via API")
        return {"status": "success", "message": "Circuit breaker reset to closed state"}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Circuit breaker reset failed: {str(e)}"
        )


# Analytics Template Queries (Common use cases)
@router.get(
    "/templates/page-stats",
    summary="Get Page Statistics",
    description="Get aggregated page statistics from the analytics database"
)
async def get_page_statistics(
    current_user: User = Depends(get_current_active_user),
    service: DuckDBService = Depends(get_duckdb_service),
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of results"),
    start_date: Optional[str] = Query(None, description="Start date filter (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="End date filter (YYYY-MM-DD)")
) -> QueryResponse:
    """
    Get aggregated page statistics from the analytics database.
    
    This template query demonstrates common analytics patterns and
    can be customized based on your data structure.
    """
    try:
        # Build dynamic query based on parameters
        where_clauses = []
        if start_date:
            where_clauses.append(f"created_at >= '{start_date}'")
        if end_date:
            where_clauses.append(f"created_at <= '{end_date}'")
        
        where_clause = " WHERE " + " AND ".join(where_clauses) if where_clauses else ""
        
        query = f"""
            SELECT 
                domain,
                COUNT(*) as page_count,
                AVG(content_length) as avg_content_length,
                MAX(created_at) as last_scraped
            FROM pages_analytics
            {where_clause}
            GROUP BY domain
            ORDER BY page_count DESC
            LIMIT {limit}
        """
        
        result = await service.execute_query(query)
        
        if result is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No analytics data found"
            )
        
        return QueryResponse(
            data=result.data,
            execution_time=result.execution_time,
            memory_usage=result.memory_usage,
            row_count=result.row_count,
            columns=result.columns,
            query_hash=result.query_hash
        )
        
    except DuckDBException as e:
        # Table might not exist yet
        if "does not exist" in str(e).lower():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Analytics tables not yet created. Run data sync first."
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Query execution failed: {str(e)}"
            )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Unexpected error: {str(e)}"
        )


@router.get(
    "/templates/performance-metrics",
    summary="Get Performance Metrics",
    description="Get system and query performance metrics"
)
async def get_performance_metrics(
    current_user: User = Depends(get_current_active_user),
    service: DuckDBService = Depends(get_duckdb_service)
) -> Dict[str, Any]:
    """
    Get system and query performance metrics.
    
    Returns comprehensive performance data including query times,
    memory usage, and system resource utilization.
    """
    try:
        stats = await service.get_statistics()
        
        # Extract performance metrics
        performance_data = {
            "query_performance": {
                "total_queries": stats["metrics"]["total_queries"],
                "success_rate": stats["metrics"]["success_rate"],
                "avg_query_time": stats["metrics"]["avg_query_time"],
                "recent_query_times": stats["performance"].get("recent_query_times", []),
            },
            "system_performance": stats["system"],
            "memory_usage": {
                "service_memory_mb": stats["metrics"]["memory_usage_mb"],
                "avg_query_memory_mb": stats["performance"].get("avg_memory_per_query", 0)
            },
            "circuit_breaker": {
                "state": stats["circuit_breaker"]["state"],
                "success_rate": stats["circuit_breaker"]["metrics"]["success_rate"],
                "failure_count": stats["circuit_breaker"]["failure_count"]
            }
        }
        
        return performance_data
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Performance metrics collection failed: {str(e)}"
        )


# Error handler for DuckDB-specific exceptions
@router.exception_handler(DuckDBException)
async def duckdb_exception_handler(request, exc: DuckDBException):
    """Handle DuckDB-specific exceptions"""
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={
            "detail": str(exc),
            "type": "DuckDBException",
            "timestamp": datetime.now().isoformat()
        }
    )


# Export router
__all__ = ['router']