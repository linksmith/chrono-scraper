# HybridQueryRouter System - Production Ready Database Routing

A sophisticated database routing and optimization system that intelligently routes queries between PostgreSQL (OLTP) and DuckDB (OLAP) based on query characteristics, performance patterns, and resource optimization.

## 🎯 Overview

The HybridQueryRouter system provides:

- **Intelligent Query Classification**: Automatically analyzes SQL queries to determine optimal database routing
- **Performance Optimization**: Query rewriting, predicate pushdown, and index optimization
- **Resource Management**: Connection pooling, throttling, and adaptive resource allocation
- **Circuit Breaker Protection**: Automatic failover and recovery for high availability
- **Comprehensive Monitoring**: Real-time metrics, alerting, and performance insights
- **Multi-level Caching**: Redis and local caching for improved response times

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    FastAPI Application                          │
├─────────────────────────────────────────────────────────────────┤
│                 HybridQueryRouter API                           │
│  /hybrid-query/execute  /analyze  /optimize  /metrics          │
├─────────────────────────────────────────────────────────────────┤
│                   Core Components                               │
│ ┌─────────────┐ ┌─────────────┐ ┌─────────────┐                │
│ │ QueryRouter │ │ QueryAnalyzer│ │ Optimizer   │                │
│ └─────────────┘ └─────────────┘ └─────────────┘                │
├─────────────────────────────────────────────────────────────────┤
│              Database Connection Management                      │
│ ┌─────────────┐ ┌─────────────┐ ┌─────────────┐                │
│ │ PostgreSQL  │ │   DuckDB    │ │ Circuit     │                │
│ │ Pool        │ │   Pool      │ │ Breakers    │                │
│ └─────────────┘ └─────────────┘ └─────────────┘                │
├─────────────────────────────────────────────────────────────────┤
│                    Infrastructure                               │
│ ┌─────────────┐ ┌─────────────┐ ┌─────────────┐                │
│ │ PostgreSQL  │ │   DuckDB    │ │ Redis Cache │                │
│ │ Database    │ │  Analytics  │ │ & Metrics   │                │
│ └─────────────┘ └─────────────┘ └─────────────┘                │
└─────────────────────────────────────────────────────────────────┘
```

## 📦 Components

### 1. HybridQueryRouter (`app/services/hybrid_query_router.py`)
The main orchestrator that:
- Classifies incoming queries based on patterns and characteristics
- Routes queries to optimal databases (PostgreSQL for OLTP, DuckDB for OLAP)
- Manages caching strategies and cache invalidation
- Coordinates with circuit breakers for fault tolerance

**Key Features:**
- Automatic query type detection (USER_AUTH, ANALYTICS, TIME_SERIES, etc.)
- Database target selection based on query complexity and resource requirements
- Multi-level caching with Redis and local cache support
- Circuit breaker integration for database protection

### 2. QueryAnalyzer (`app/services/query_analyzer.py`)
Advanced SQL analysis engine that:
- Parses SQL queries to extract structural information
- Predicts performance characteristics (duration, memory, rows)
- Recommends optimization strategies
- Maintains table statistics for routing decisions

**Analysis Capabilities:**
- Query complexity scoring (SIMPLE, MODERATE, COMPLEX, VERY_COMPLEX)
- Table and column dependency tracking
- Join pattern analysis and optimization suggestions
- Performance prediction based on historical data

### 3. PerformanceOptimizationEngine (`app/services/performance_optimization_engine.py`)
Intelligent query optimization system featuring:
- Automated query rewriting with 10+ optimization strategies
- Resource-based query scheduling and throttling
- Adaptive performance tuning based on system load
- Memory and CPU resource management

**Optimization Strategies:**
- Subquery to JOIN conversion
- Predicate pushdown optimization
- Automatic LIMIT addition for large result sets
- Index hint suggestions
- Query plan caching and reuse

### 4. DatabaseConnectionManager (`app/services/database_connection_manager.py`)
Sophisticated connection pooling system providing:
- Separate pools for PostgreSQL and DuckDB with load balancing
- Health monitoring and automatic connection recovery
- Resource usage tracking and optimization
- Failover mechanisms and circuit breaker integration

**Pool Management:**
- Round-robin, least-connections, and performance-based load balancing
- Connection lifecycle management with idle timeout and max lifetime
- Pool utilization monitoring and automatic scaling
- Connection health checks and stale connection cleanup

### 5. HybridQueryMonitoringSystem (`app/services/hybrid_query_monitoring.py`)
Comprehensive observability platform offering:
- Real-time performance metrics collection
- Alerting system with customizable thresholds
- Prometheus metrics integration
- Performance dashboards and insights

**Monitoring Features:**
- Query execution tracking with P50, P95, P99 percentiles
- Database usage distribution analysis
- Cache hit rate monitoring
- Resource utilization alerts and notifications

## 🚀 Getting Started

### Installation

1. **Install Dependencies**
   ```bash
   # Backend dependencies (includes DuckDB, SQLParse, Prometheus client)
   pip install -r requirements.txt
   
   # Optional: Install SQLParse for advanced SQL parsing
   pip install sqlparse
   ```

2. **Configure Environment Variables**
   Add to your `.env` file:
   ```env
   # Enable Hybrid Query Router
   HYBRID_QUERY_ROUTER_ENABLED=true
   
   # Database Configuration
   DUCKDB_DATABASE_PATH=/var/lib/duckdb/chrono_analytics.db
   DUCKDB_MEMORY_LIMIT=4GB
   DUCKDB_WORKER_THREADS=4
   
   # Circuit Breaker Settings
   POSTGRESQL_CIRCUIT_BREAKER_THRESHOLD=5
   DUCKDB_CIRCUIT_BREAKER_THRESHOLD=3
   
   # Performance Settings
   HYBRID_ROUTER_MAX_CONCURRENT_QUERIES=100
   HYBRID_ROUTER_ENABLE_QUERY_OPTIMIZATION=true
   HYBRID_ROUTER_ENABLE_QUERY_CACHING=true
   
   # Monitoring
   HYBRID_ROUTER_ENABLE_MONITORING=true
   ENABLE_PROMETHEUS_METRICS=true
   ```

3. **Initialize Services**
   ```python
   from app.services.hybrid_query_router import hybrid_router
   from app.services.performance_optimization_engine import performance_engine
   from app.services.database_connection_manager import db_connection_manager
   from app.services.hybrid_query_monitoring import monitoring_system
   
   # Initialize all services
   await hybrid_router.initialize()
   await performance_engine.initialize()
   await db_connection_manager.initialize()
   await monitoring_system.initialize(hybrid_router)
   ```

### Basic Usage

#### 1. Execute Queries with Automatic Routing
```python
from app.services.hybrid_query_router import hybrid_router, QueryPriority

# OLTP query (routes to PostgreSQL)
result = await hybrid_router.route_query(
    query="SELECT * FROM users WHERE email = 'user@example.com'",
    priority=QueryPriority.HIGH,
    use_cache=True
)

# OLAP query (routes to DuckDB)
result = await hybrid_router.route_query(
    query="SELECT domain, COUNT(*) FROM pages_v2 GROUP BY domain",
    priority=QueryPriority.NORMAL,
    use_cache=True
)
```

#### 2. Analyze Query Characteristics
```python
from app.services.query_analyzer import query_analyzer

analysis = await query_analyzer.analyze_query(
    "SELECT p.name, COUNT(pg.id) FROM projects p JOIN pages_v2 pg ON p.id = pg.project_id GROUP BY p.name"
)

print(f"Query Type: {analysis.query_type}")
print(f"Complexity: {analysis.complexity}")
print(f"Recommended DB: {analysis.recommended_database}")
print(f"Estimated Duration: {analysis.estimated_plan.estimated_duration}s")
print(f"Optimization Hints: {analysis.optimization_hints}")
```

#### 3. Optimize Queries
```python
from app.services.performance_optimization_engine import performance_engine

optimized_query, strategies = await performance_engine.query_optimizer.optimize_query(
    query="SELECT * FROM pages_v2 WHERE domain = 'example.com' ORDER BY created_at"
)

print(f"Original Query: {query}")
print(f"Optimized Query: {optimized_query}")
print(f"Applied Strategies: {strategies}")
```

### API Endpoints

The system provides RESTful API endpoints for all functionality:

#### Core Operations
- `POST /api/v1/hybrid-query/execute` - Execute queries with intelligent routing
- `POST /api/v1/hybrid-query/analyze` - Analyze query characteristics
- `POST /api/v1/hybrid-query/optimize` - Optimize query performance

#### Monitoring & Management
- `GET /api/v1/hybrid-query/metrics` - Performance metrics and statistics
- `GET /api/v1/hybrid-query/health` - System health checks
- `GET /api/v1/hybrid-query/analytics/query-patterns` - Query pattern analysis

#### Administrative
- `POST /api/v1/hybrid-query/admin/resource-quota` - Configure resource limits
- `GET /api/v1/hybrid-query/admin/connection-pools` - Connection pool status
- `POST /api/v1/hybrid-query/admin/clear-cache` - Cache management

## 📊 Query Classification

The system automatically classifies queries into categories for optimal routing:

### OLTP Operations (→ PostgreSQL)
- **USER_AUTH**: User authentication and session management
- **PROJECT_CRUD**: Project creation, updates, and management
- **PAGE_MANAGEMENT**: Individual page operations and metadata updates
- **REAL_TIME_OPERATIONS**: Time-sensitive operations requiring immediate consistency
- **TRANSACTIONAL**: Multi-step operations requiring ACID compliance

### OLAP Operations (→ DuckDB)
- **ANALYTICS**: Complex aggregations and statistical analysis
- **TIME_SERIES**: Temporal data analysis and trending
- **AGGREGATION**: Group-by operations and summary statistics
- **REPORTING**: Dashboard queries and report generation
- **BULK_READ**: Large dataset scans and exports

### Hybrid Operations (→ Both Databases)
- **CROSS_PROJECT_ANALYTICS**: Analytics spanning multiple projects
- **USER_ACTIVITY_ANALYSIS**: User behavior analysis across projects
- **PERFORMANCE_MONITORING**: System-wide performance tracking

## ⚡ Performance Optimization

### Automatic Query Rewriting

The system applies intelligent optimization strategies:

1. **Subquery to JOIN Conversion**
   ```sql
   -- Before
   SELECT * FROM projects WHERE id IN (SELECT project_id FROM pages_v2 WHERE content_length > 1000)
   
   -- After
   SELECT DISTINCT p.* FROM projects p JOIN pages_v2 pg ON p.id = pg.project_id WHERE pg.content_length > 1000
   ```

2. **Predicate Pushdown**
   ```sql
   -- Before
   SELECT * FROM projects p JOIN pages_v2 pg ON p.id = pg.project_id WHERE pg.status = 'processed'
   
   -- After
   SELECT * FROM projects p JOIN (SELECT * FROM pages_v2 WHERE status = 'processed') pg ON p.id = pg.project_id
   ```

3. **Automatic LIMIT Addition**
   ```sql
   -- Before
   SELECT * FROM pages_v2 WHERE domain = 'example.com'
   
   -- After (for potentially large result sets)
   SELECT * FROM pages_v2 WHERE domain = 'example.com' LIMIT 10000
   ```

### Resource Management

- **Query Prioritization**: Critical queries bypass throttling
- **Connection Pooling**: Optimized pool sizes per database type
- **Memory Management**: Per-query memory limits and monitoring
- **CPU Throttling**: Adaptive query scheduling based on system load

## 📈 Monitoring & Observability

### Real-time Metrics

The system collects comprehensive metrics:

- **Query Performance**: Response times, success rates, error rates
- **Database Distribution**: Query routing patterns and database usage
- **Resource Utilization**: CPU, memory, connection pool usage
- **Cache Effectiveness**: Hit rates, invalidation patterns

### Alerting System

Built-in alerts for operational issues:

- **High Error Rate**: Query failure rate exceeds 5%
- **Slow Performance**: Average response time exceeds 2 seconds
- **Circuit Breaker**: Database circuit breakers activate
- **Low Cache Hit Rate**: Cache effectiveness below 50%

### Prometheus Integration

Exports metrics for external monitoring:

```prometheus
# Query execution metrics
hybrid_router_queries_total{database="postgresql",type="user_auth",status="success"} 1250
hybrid_router_query_duration_seconds{database="duckdb",type="analytics"} 0.150

# Resource utilization
hybrid_router_active_connections{database="postgresql"} 15
hybrid_router_pool_utilization_percent{database="duckdb"} 60.0

# Circuit breaker status
hybrid_router_circuit_breaker_open{database="postgresql"} 0
```

## 🔧 Configuration

### Core Settings

```python
# Enable/disable the hybrid router
HYBRID_QUERY_ROUTER_ENABLED: bool = True

# Query routing preferences
HYBRID_ROUTER_OLTP_PREFERENCE: str = "postgresql"
HYBRID_ROUTER_OLAP_PREFERENCE: str = "duckdb" 
HYBRID_ROUTER_LARGE_RESULT_THRESHOLD: int = 100000
HYBRID_ROUTER_LONG_QUERY_THRESHOLD: float = 5.0

# Connection pool configuration
HYBRID_ROUTER_POSTGRESQL_POOL_SIZE: int = 20
HYBRID_ROUTER_DUCKDB_POOL_SIZE: int = 10
HYBRID_ROUTER_CONNECTION_TIMEOUT: int = 30

# Performance optimization
HYBRID_ROUTER_ENABLE_QUERY_OPTIMIZATION: bool = True
HYBRID_ROUTER_MAX_OPTIMIZATION_TIME: float = 2.0
HYBRID_ROUTER_OPTIMIZATION_STRATEGIES_LIMIT: int = 5
```

### Resource Management

```python
# Resource limits
HYBRID_ROUTER_MAX_CPU_PERCENT: float = 80.0
HYBRID_ROUTER_MAX_MEMORY_MB: float = 8192.0
HYBRID_ROUTER_MAX_CONNECTIONS_GLOBAL: int = 200

# Query prioritization
HYBRID_ROUTER_CRITICAL_PRIORITY_MAX_CONCURRENT: int = 10
HYBRID_ROUTER_HIGH_PRIORITY_MAX_CONCURRENT: int = 30
HYBRID_ROUTER_NORMAL_PRIORITY_MAX_CONCURRENT: int = 80
```

### Monitoring Configuration

```python
# Monitoring settings
HYBRID_ROUTER_ENABLE_MONITORING: bool = True
HYBRID_ROUTER_METRICS_COLLECTION_INTERVAL: int = 60
HYBRID_ROUTER_PERFORMANCE_SNAPSHOT_INTERVAL: int = 300

# Alerting thresholds
HYBRID_ROUTER_HIGH_ERROR_RATE_THRESHOLD: float = 5.0
HYBRID_ROUTER_SLOW_QUERY_THRESHOLD: float = 2.0
HYBRID_ROUTER_LOW_CACHE_HIT_RATE_THRESHOLD: float = 50.0
```

## 🧪 Testing

### Run Test Suite

Execute the comprehensive test suite:

```bash
cd backend
python test_hybrid_query_router.py
```

### Test Categories

The test suite covers:

1. **Query Classification**: Accuracy of automatic query type detection
2. **Database Routing**: Correctness of routing decisions  
3. **Query Optimization**: Effectiveness of optimization strategies
4. **Caching Mechanisms**: Cache hit rates and invalidation
5. **Connection Pooling**: Pool management and load balancing
6. **Circuit Breakers**: Failover and recovery mechanisms
7. **Resource Management**: Throttling and resource allocation
8. **Monitoring**: Metrics collection and alerting
9. **End-to-End Workflows**: Complete integration testing
10. **Performance Under Load**: System behavior under stress

### Expected Results

A healthy system should achieve:
- **Query Classification Accuracy**: ≥ 80%
- **Database Routing Accuracy**: ≥ 85%
- **Query Optimization Rate**: ≥ 50% (for complex queries)
- **Cache Hit Rate**: ≥ 30% (depends on workload)
- **Concurrent Query Success Rate**: ≥ 80%
- **Performance Under Load Success Rate**: ≥ 85%

## 🎛️ Administrative Operations

### Managing Query Routing Rules

Add custom routing rules:

```python
from app.services.performance_optimization_engine import OptimizationRule, OptimizationStrategy

custom_rule = OptimizationRule(
    name="custom_pagination_optimization",
    strategy=OptimizationStrategy.ADD_LIMITS,
    pattern=r"SELECT.*FROM\s+large_table.*ORDER\s+BY",
    replacement=r"\g<0> LIMIT 1000",
    priority=95,
    enabled=True
)

performance_engine.query_optimizer.add_optimization_rule(custom_rule)
```

### Resource Quota Management

Adjust resource limits dynamically:

```python
from app.services.performance_optimization_engine import ResourceQuota

new_quota = ResourceQuota(
    cpu_percent=75.0,
    memory_mb=6144.0,  # 6GB
    max_connections=150,
    query_timeout_seconds=600.0
)

performance_engine.set_resource_limits(new_quota)
```

### Cache Management

Control caching behavior:

```python
# Clear specific cache patterns
await hybrid_router.cache.invalidate_pattern("analytics_*")

# Get cache statistics
stats = hybrid_router.cache.get_stats()
print(f"Cache hit rate: {stats['hit_rate']}%")
```

## 🔍 Troubleshooting

### Common Issues

1. **High Query Latency**
   - Check resource utilization: CPU, memory, connections
   - Verify optimization is enabled and working
   - Review query patterns for inefficient operations

2. **Circuit Breakers Activating**
   - Check database connectivity and health
   - Review error logs for connection issues
   - Adjust circuit breaker thresholds if needed

3. **Low Cache Hit Rate**
   - Verify cache configuration and Redis connectivity
   - Check query patterns - transactional queries aren't cached
   - Review cache TTL settings for your workload

4. **Connection Pool Exhaustion**
   - Monitor pool utilization metrics
   - Adjust pool sizes based on workload
   - Check for connection leaks or long-running queries

### Debug Mode

Enable detailed logging:

```python
# In configuration
HYBRID_ROUTER_DEBUG_MODE: bool = True
HYBRID_ROUTER_LOG_ALL_QUERIES: bool = True
HYBRID_ROUTER_LOG_ROUTING_DECISIONS: bool = True
```

### Health Checks

Monitor system health:

```python
# Check overall health
health = await hybrid_router.health_check()
print(f"System Status: {health['status']}")

# Check connection pools
pool_health = await db_connection_manager.health_check()

# Check monitoring system
monitoring_health = await monitoring_system.health_check()
```

## 📋 Performance Recommendations

### For OLTP Workloads
- Use appropriate query types (USER_AUTH, PROJECT_CRUD)
- Enable connection pooling with sufficient pool size
- Set HIGH priority for time-sensitive operations
- Avoid caching for transactional queries

### For OLAP Workloads  
- Route complex analytics to DuckDB
- Enable caching for expensive aggregations
- Use NORMAL or LOW priority for batch operations
- Consider query optimization for complex joins

### For High-Volume Systems
- Monitor resource utilization continuously
- Set appropriate circuit breaker thresholds
- Use query prioritization effectively
- Scale connection pools based on load patterns

### For Development
- Enable debug logging for troubleshooting
- Use the test suite to validate configurations
- Monitor query patterns and optimization effectiveness
- Test failover scenarios regularly

## 🛡️ Security Considerations

- **Query Sanitization**: Enabled by default to prevent SQL injection
- **Access Control**: Admin endpoints require authentication
- **Audit Logging**: Failed and slow queries are logged
- **Resource Limits**: Prevent resource exhaustion attacks
- **Circuit Breaker Protection**: Automatic failover for availability

## 📚 Additional Resources

- **Configuration Reference**: See `app/core/config.py` for all settings
- **API Documentation**: Available via FastAPI `/docs` endpoint
- **Monitoring Dashboards**: Prometheus/Grafana integration examples
- **Performance Tuning**: Query optimization best practices
- **Troubleshooting Guide**: Common issues and solutions

## 🤝 Contributing

To contribute to the HybridQueryRouter system:

1. Run the test suite to ensure baseline functionality
2. Add tests for new features or modifications
3. Follow the existing code style and documentation patterns
4. Update configuration documentation for new settings
5. Test performance impact of changes

The system is designed to be extensible and maintainable, with clear separation of concerns and comprehensive testing coverage.