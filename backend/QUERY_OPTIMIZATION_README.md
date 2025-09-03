# Query Optimization System

## Overview

The Chrono Scraper FastAPI application now includes a comprehensive query optimization system that provides significant performance improvements through intelligent query analysis, multi-level caching, performance monitoring, and adaptive execution.

## Architecture

The optimization system consists of five main components:

### 1. Query Optimization Engine (`query_optimization_engine.py`)
- **SQL Query Analysis & Rewriting**: Automatically analyzes and optimizes SQL queries
- **Database-Specific Optimizations**: Separate optimizations for PostgreSQL and DuckDB
- **Index Recommendations**: Suggests optimal database indexes based on query patterns
- **Cost Estimation**: Predicts query execution costs and performance improvements

### 2. Intelligent Cache Manager (`intelligent_cache_manager.py`)
- **Multi-Level Caching**: L1 (Memory) → L2 (Redis) → L3 (Persistent/DuckDB)
- **Smart Cache Promotion**: Frequently accessed items automatically promoted to faster layers
- **Compression**: Automatic compression for large cache entries
- **Predictive Warming**: Preloads cache based on usage patterns

### 3. Query Performance Monitor (`query_performance_monitor.py`)
- **Real-time Monitoring**: Tracks query execution times, resource usage, and performance
- **Anomaly Detection**: Automatically detects performance regressions and issues
- **Alerting System**: Configurable alerts for performance thresholds
- **Analytics Dashboard**: Comprehensive performance metrics and trends

### 4. Adaptive Query Executor (`adaptive_query_executor.py`)
- **Resource Management**: Memory and CPU limits per query and user
- **Query Queueing**: Priority-based query scheduling with resource awareness
- **Automatic Retries**: Intelligent retry logic with exponential backoff
- **Circuit Breakers**: Prevents cascade failures across database connections

### 5. Cache Integration Service (`cache_integration_service.py`)
- **Cross-Database Coordination**: Synchronizes caching between PostgreSQL, DuckDB, and Redis
- **Hybrid Query Support**: Executes queries across multiple databases efficiently
- **Cache Invalidation**: Intelligent invalidation based on data dependencies
- **Consistency Management**: Configurable consistency levels for different use cases

## Configuration

All optimization features are controlled by settings in `app/core/config.py`:

```python
# Query Optimization Configuration
QUERY_OPTIMIZATION_ENABLED: bool = True
ENABLE_AUTOMATIC_QUERY_REWRITING: bool = True
ENABLE_PREDICATE_PUSHDOWN: bool = True
ENABLE_JOIN_OPTIMIZATION: bool = True
MAX_QUERY_OPTIMIZATION_TIME_MS: int = 500

# Multi-Level Caching Configuration  
ENABLE_MULTI_LEVEL_CACHING: bool = True
L1_CACHE_SIZE_MB: int = 512
L2_REDIS_CACHE_TTL_SECONDS: int = 3600
L3_MATERIALIZED_VIEW_TTL_HOURS: int = 24
CACHE_WARM_UP_ENABLED: bool = True
PREDICTIVE_CACHING_ENABLED: bool = True
CACHE_COMPRESSION_ENABLED: bool = True

# Performance Monitoring Configuration
PERFORMANCE_MONITORING_ENABLED: bool = True
QUERY_PERFORMANCE_TRACKING_ENABLED: bool = True
SLOW_QUERY_THRESHOLD_MS: int = 1000
ENABLE_ANOMALY_DETECTION: bool = True

# Adaptive Query Executor Configuration
MAX_CONCURRENT_QUERIES: int = 100
QUERY_TIMEOUT_SECONDS: int = 300  
MEMORY_LIMIT_PER_QUERY_MB: int = 1024
ENABLE_QUERY_QUEUEING: bool = True
ENABLE_AUTOMATIC_RETRY: bool = True

# Resource Management Configuration
ENABLE_RESOURCE_QUOTAS: bool = True
DEFAULT_USER_QUERY_LIMIT_PER_HOUR: int = 1000
DEFAULT_USER_MEMORY_LIMIT_MB: int = 512
DEFAULT_USER_CONCURRENT_QUERIES: int = 10
```

## API Endpoints

The optimization system exposes comprehensive REST API endpoints at `/api/v1/optimization/`:

### Query Optimization

**GET** `/optimization/status`
- Get optimization service status and health metrics

**POST** `/optimization/analyze-query`
```json
{
  "query": "SELECT * FROM users WHERE created_at > '2024-01-01'",
  "database_type": "postgresql"
}
```

**POST** `/optimization/optimize-query`
```json
{
  "query": "SELECT * FROM users WHERE created_at > '2024-01-01'",
  "database_type": "postgresql",
  "optimization_level": 3,
  "enable_caching": true
}
```

**GET** `/optimization/recommendations`
- Get optimization recommendations for your database

### Cache Management

**GET** `/cache/statistics`
- Get comprehensive cache statistics and hit rates

**POST** `/cache/warm-up`
```json
{
  "queries": [
    "SELECT COUNT(*) FROM projects WHERE user_id = ?",
    "SELECT * FROM shared_pages WHERE project_id IN (?)"
  ]
}
```

**POST** `/cache/invalidate`
```json
{
  "patterns": ["user:123:*", "project:456:*"],
  "scope": "key_pattern"
}
```

**POST** `/cache/optimize`
- Trigger cache layout optimization and defragmentation

### Performance Monitoring

**GET** `/performance/dashboard`
- Get comprehensive performance dashboard data

**GET** `/performance/slow-queries?limit=50&min_duration_ms=1000`
- Get detailed slow query analysis

**POST** `/performance/create-alert`
```json
{
  "metric_type": "execution_time",
  "threshold_value": 5000,
  "comparison_operator": ">",
  "window_minutes": 5,
  "min_occurrences": 3,
  "severity": "high"
}
```

**GET** `/performance/alerts?active_only=true`
- Get active performance alerts

### System Health

**GET** `/optimization/health`
- Get overall optimization system health status

**GET** `/execution/metrics`
- Get query execution metrics and resource utilization

## Usage Examples

### 1. Basic Query Optimization

```python
from app.services.query_optimization_engine import get_query_optimization_engine, QueryContext, DatabaseType

async def optimize_user_query(sql_query: str):
    optimizer = get_query_optimization_engine()
    
    context = QueryContext(
        database_type=DatabaseType.POSTGRESQL,
        user_id="user_123",
        project_id="project_456",
        optimization_level=3
    )
    
    result = await optimizer.optimize_query(sql_query, context)
    
    print(f"Original: {result.original_query}")
    print(f"Optimized: {result.optimized_query}")
    print(f"Improvement: {result.estimated_improvement_percent}%")
    
    return result.optimized_query
```

### 2. Cache Management

```python
from app.services.intelligent_cache_manager import get_cache_manager

async def cache_expensive_query_result(query: str, result: any):
    cache_manager = get_cache_manager()
    
    # Cache with 1 hour TTL, tagged for easy invalidation
    await cache_manager.cache_result(
        query_key=f"analytics:{hash(query)}",
        result=result,
        ttl=3600,
        tags={"analytics", "reports"},
        dependencies={"table:projects", "table:shared_pages"}
    )

async def get_cached_result(query: str):
    cache_manager = get_cache_manager()
    
    cached = await cache_manager.get_cached_result(f"analytics:{hash(query)}")
    if cached:
        print(f"Cache hit! Source: {cached.source_level}")
        return cached.data
    
    return None
```

### 3. Performance Monitoring

```python
from app.services.query_performance_monitor import get_performance_monitor

async def track_query_performance(query: str, duration_ms: float):
    monitor = get_performance_monitor()
    
    metadata = {
        "query_id": "q_12345",
        "user_id": "user_123",
        "database_type": "postgresql",
        "cpu_usage_percent": 45.0,
        "memory_usage_mb": 128.0,
        "cache_hit": False
    }
    
    await monitor.track_query_execution(query, duration_ms, metadata)

async def check_for_anomalies():
    monitor = get_performance_monitor()
    anomalies = await monitor.detect_performance_anomalies()
    
    for anomaly in anomalies:
        print(f"Anomaly detected: {anomaly.description}")
        print(f"Severity: {anomaly.severity}")
        print(f"Confidence: {anomaly.confidence_score}")
```

### 4. Hybrid Database Queries

```python
from app.services.cache_integration_service import get_cache_integration_service

async def run_hybrid_analytics_query():
    integration = get_cache_integration_service()
    
    # Run query on both PostgreSQL and DuckDB
    result = await integration.execute_hybrid_query(
        postgresql_query="SELECT user_id, COUNT(*) FROM projects GROUP BY user_id",
        duckdb_query="SELECT date_trunc('month', created_at) as month, COUNT(*) FROM project_analytics GROUP BY month",
        combine_results=True,
        cache_result=True,
        cache_ttl=1800  # 30 minutes
    )
    
    print(f"PostgreSQL result: {result.postgresql_result}")
    print(f"DuckDB result: {result.duckdb_result}")
    print(f"Combined result: {result.combined_result}")
    print(f"Execution times: {result.execution_time_ms}")
    print(f"Cache sources: {result.cache_sources}")
```

### 5. Advanced Query Execution

```python
from app.services.adaptive_query_executor import get_query_executor, Query, Priority

async def execute_priority_query(sql: str, user_id: str):
    executor = get_query_executor()
    
    query = Query(
        query_id="priority_query_001",
        sql=sql,
        user_id=user_id,
        priority=Priority.HIGH,
        timeout_seconds=60,
        memory_limit_mb=512,
        enable_optimization=True,
        enable_caching=True
    )
    
    execution = await executor.schedule_query(query, Priority.HIGH)
    
    # Monitor execution progress
    while execution.status in ["queued", "running"]:
        status = await executor.monitor_execution(execution.execution_id)
        print(f"Status: {status.status}, Queue position: {status.queue_position}")
        await asyncio.sleep(1)
    
    if execution.status == "completed":
        return execution.result
    else:
        raise Exception(f"Query failed: {execution.error}")
```

## Performance Targets

The optimization system is designed to achieve the following performance improvements:

### Query Performance
- **50%+ reduction** in average query execution time
- **80%+ cache hit ratio** for frequently accessed queries  
- **90%+ of queries** complete within SLA thresholds
- **99.9% availability** with intelligent failover
- **10x improvement** in complex analytical queries

### Resource Utilization
- **30%+ reduction** in database CPU usage
- **40%+ reduction** in memory consumption  
- **50%+ reduction** in I/O operations
- **25%+ improvement** in connection pool efficiency
- **20%+ reduction** in network traffic

### Operational Excellence
- **Automated performance issue detection**
- **Self-healing query optimization**
- **Comprehensive performance analytics**
- **Proactive capacity planning**
- **Zero-configuration optimization** for common patterns

## Monitoring and Alerting

### Key Metrics to Monitor

1. **Cache Performance**
   - Cache hit rates by level (L1/L2/L3)
   - Cache eviction rates
   - Memory pressure and fragmentation

2. **Query Performance**
   - Average execution times by database
   - Slow query frequency and patterns
   - Resource utilization per query

3. **System Health**
   - Active vs queued queries
   - Circuit breaker states
   - Resource quota utilization

### Setting Up Alerts

```python
# Example alert configuration
PERFORMANCE_ALERT_THRESHOLDS = {
    "slow_query_percentage": 5.0,      # Alert if >5% queries are slow
    "error_rate_percentage": 1.0,      # Alert if >1% queries fail
    "memory_usage_percentage": 80.0,   # Alert if >80% memory used
    "cpu_usage_percentage": 75.0,      # Alert if >75% CPU used
    "cache_hit_rate_minimum": 70.0     # Alert if cache hit rate <70%
}
```

## Troubleshooting

### Common Issues

1. **High Memory Usage**
   - Reduce `L1_CACHE_SIZE_MB` 
   - Enable `CACHE_COMPRESSION_ENABLED`
   - Lower `DEFAULT_USER_MEMORY_LIMIT_MB`

2. **Cache Miss Rate High**
   - Enable `CACHE_WARM_UP_ENABLED`
   - Increase `L2_REDIS_CACHE_TTL_SECONDS`
   - Review cache invalidation patterns

3. **Slow Query Detection**
   - Lower `SLOW_QUERY_THRESHOLD_MS`
   - Enable `ENABLE_AUTOMATIC_QUERY_REWRITING`
   - Check database indexes

4. **Resource Contention**
   - Reduce `MAX_CONCURRENT_QUERIES`
   - Enable `ENABLE_RESOURCE_QUOTAS`
   - Increase `QUERY_TIMEOUT_SECONDS`

### Debug Mode

Enable debug logging for detailed optimization information:

```python
import logging
logging.getLogger('app.services').setLevel(logging.DEBUG)
```

## Integration with Existing Systems

The optimization system seamlessly integrates with:

- **Existing FastAPI endpoints** (transparent optimization)
- **User authentication and authorization**
- **Project-level resource quotas** 
- **Real-time WebSocket updates**
- **Export functionality and background jobs**
- **Monitoring and alerting systems**
- **All Phase 2 DuckDB analytics components**

## Best Practices

1. **Enable optimization gradually** - Start with caching only, then add query optimization
2. **Monitor performance metrics** - Use the dashboard to track improvements
3. **Set appropriate resource limits** - Prevent any single query from consuming too many resources  
4. **Use cache warming for predictable workloads** - Preload frequently accessed data
5. **Configure alerts based on your SLAs** - Set thresholds that match your performance requirements
6. **Regular cache maintenance** - Use the optimization endpoint to defragment and cleanup caches

## Future Enhancements

The system is designed to support future enhancements:

- **Machine Learning-based optimization** (requires ML model training)
- **Automated index creation** (requires database admin privileges)  
- **Cross-datacenter cache replication** (for distributed deployments)
- **Query result streaming** (for very large result sets)
- **Advanced cost-based optimization** (with workload-specific tuning)

---

For more detailed information about specific components, refer to the inline documentation in each service file.