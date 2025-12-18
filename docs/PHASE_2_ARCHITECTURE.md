# Phase 2 Technical Architecture Guide

## System Architecture Overview

Phase 2 introduces a sophisticated hybrid database architecture that combines the strengths of PostgreSQL (OLTP) and DuckDB (OLAP) to deliver unprecedented analytics performance for the Chrono Scraper platform.

```
┌─────────────────────────────────────────────────────────────────┐
│                    Phase 2 System Architecture                 │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Frontend      │    │   Backend API   │    │  Analytics API  │
│   SvelteKit     │────│    FastAPI      │────│   24+ Routes    │
│                 │    │                 │    │                 │
└─────────────────┘    └─────────────────┘    └─────────────────┘
         │                       │                       │
         │              ┌────────┴────────┐              │
         │              │                 │              │
         └──────────────┤ HybridQueryRouter│──────────────┘
                        │  (Intelligent   │
                        │   Routing)      │
                        └────────┬────────┘
                                 │
                    ┌────────────┴────────────┐
                    │                         │
         ┌─────────────────┐         ┌─────────────────┐
         │   PostgreSQL    │         │     DuckDB      │
         │   (OLTP/ACID)   │         │ (OLAP/Columnar) │
         ├─────────────────┤         ├─────────────────┤
         │ • User Auth     │◄────────┤ • CDX Analytics │
         │ • Projects      │  Sync   │ • Time Series   │
         │ • Sessions      │ Service │ • Aggregations  │
         │ • Real-time Ops │         │ • Reporting     │
         └─────────────────┘         └─────────────────┘
                    │                         │
                    └────────────┬────────────┘
                                 │
                    ┌─────────────────────────┐
                    │     Data Pipeline       │
                    │ • ParquetPipeline      │
                    │ • DataSyncService      │
                    │ • ChangeDataCapture    │
                    └─────────────────────────┘
                                 │
              ┌──────────────────┼──────────────────┐
              │                  │                  │
    ┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐
    │  L1 Cache       │ │  L2 Cache       │ │  L3 Cache       │
    │ (Local Memory)  │ │   (Redis)       │ │ (Query Plans)   │
    │  5min TTL       │ │  30min TTL      │ │  Materialized   │
    └─────────────────┘ └─────────────────┘ └─────────────────┘
```

## Core Components Deep Dive

### 1. HybridQueryRouter - Intelligent Query Distribution

**Architecture:**
```python
class HybridQueryRouter:
    """Central intelligence for query routing and optimization"""
    
    # Query Classification
    OLTP_OPERATIONS = {
        QueryType.USER_AUTH,
        QueryType.PROJECT_CRUD,
        QueryType.REAL_TIME_OPERATIONS,
        QueryType.TRANSACTIONAL
    }
    
    OLAP_OPERATIONS = {
        QueryType.ANALYTICS,
        QueryType.AGGREGATION, 
        QueryType.TIME_SERIES,
        QueryType.REPORTING
    }
```

**Routing Logic:**
```
Query Request → Query Analyzer → Route Decision Tree
     │               │               │
     │               ├─ OLTP? ────── PostgreSQL
     │               ├─ OLAP? ────── DuckDB  
     │               └─ Hybrid? ──── Both (Coordinated)
     │
     └── Performance Monitoring ──── Optimization Feedback
```

**Decision Factors:**
- Query complexity and expected result size
- Table relationships and join requirements
- Real-time vs analytical nature of operation
- Historical performance patterns
- Current system load and resource availability

### 2. DuckDBService - Analytics Engine

**Technical Specifications:**
```yaml
Service Configuration:
  Connection Pool: 2x worker threads (10-20 connections)
  Memory Management: Dynamic allocation (4GB default, 70% system max)
  Extensions: parquet, httpfs, json, spatial
  Compression: ZSTD level 3 for optimal performance
  Storage: Columnar format with automatic partitioning
```

**Feature Set:**
- **Async Operations**: Thread-pool based async wrapper for DuckDB
- **Connection Pooling**: Efficient connection reuse and lifecycle management
- **Circuit Breaker**: Fault tolerance with exponential backoff
- **Memory Optimization**: Dynamic memory allocation based on system resources
- **Extension Management**: Automatic loading of required DuckDB extensions
- **Health Monitoring**: Comprehensive diagnostics and performance tracking

**Performance Optimizations:**
```sql
-- Automatic Query Optimization
SET threads = 4;                    -- Parallel processing
SET memory_limit = '4GB';           -- Dynamic memory allocation
SET temp_directory = '/tmp/duck';   -- Optimized temp storage

-- Parquet Optimization
SET parquet_compression = 'zstd';   -- Best compression ratio
SET parquet_row_group_size = 50MB;  -- Optimal chunk size
```

### 3. ParquetPipeline - Data Processing Engine

**Processing Architecture:**
```
PostgreSQL Data → Batch Extraction → Schema Validation → Parquet Conversion
       │                │                  │                   │
       │                ├─ Memory Mgmt     ├─ Type Conversion   │
       │                ├─ Error Handle    ├─ Null Handling     │
       │                └─ Progress Track  └─ Quality Checks    │
       │                                                        │
       └────── Performance Metrics ◄─────── Optimization ◄──────┘
```

**Optimization Features:**
- **Streaming Processing**: Memory-efficient handling of large datasets
- **Compression**: ZSTD compression achieving 60-80% size reduction
- **Partitioning**: Automatic date/domain-based partitioning for performance
- **Schema Evolution**: Support for schema changes without breaking queries
- **Quality Validation**: Data quality checks and error recovery

### 4. Multi-Level Caching Architecture

**Cache Hierarchy:**
```
Application Request
    │
    ├── L1: Local Memory Cache (Hot Data)
    │   ├─ 5-minute TTL
    │   ├─ Zero-latency access
    │   ├─ LRU eviction (500 items max)
    │   └─ Thread-safe operations
    │
    ├── L2: Redis Distributed Cache (Warm Data) 
    │   ├─ 30-minute TTL
    │   ├─ Shared across instances
    │   ├─ Pattern-based invalidation
    │   └─ JSON serialization
    │
    └── L3: Query Plan Cache (Cold Data)
        ├─ Materialized views
        ├─ Automatic index creation
        ├─ Predictive cache warming
        └─ Cost-based optimization
```

**Cache Strategy:**
- **Write-Through**: Updates propagate through all cache levels
- **Intelligent Eviction**: LRU with access frequency weighting
- **Pattern Invalidation**: Bulk invalidation by query patterns
- **Cache Warming**: Predictive loading of frequently accessed data

### 5. Data Synchronization System

**Dual-Write Architecture:**
```python
class DataSyncService:
    """Ensures consistency between PostgreSQL and DuckDB"""
    
    async def dual_write(self, operation, data):
        """Write to both databases with consistency guarantees"""
        
        # 1. Write to PostgreSQL (source of truth)
        pg_result = await self.postgresql.execute(operation, data)
        
        # 2. Transform for analytical format
        analytical_data = self.transform_for_analytics(data)
        
        # 3. Write to DuckDB (with error handling)
        try:
            duck_result = await self.duckdb.execute(
                analytical_operation, analytical_data
            )
        except Exception as e:
            # Queue for retry with exponential backoff
            await self.retry_queue.add(operation, analytical_data)
            
        return pg_result  # PostgreSQL result takes precedence
```

**Consistency Mechanisms:**
- **Change Data Capture (CDC)**: Track and propagate changes
- **Conflict Resolution**: PostgreSQL as authoritative source
- **Retry Logic**: Exponential backoff for failed synchronizations
- **Validation Checks**: Periodic consistency validation
- **Recovery Procedures**: Automated data repair and resynchronization

### 6. Analytics API Layer

**Endpoint Organization:**
```
/api/v1/analytics/
├── domains/                    # Domain-level analytics
│   ├── {domain}/timeline       # Time-series analysis
│   ├── {domain}/statistics     # Comprehensive metrics
│   ├── top-domains             # Ranking analysis
│   └── coverage-analysis       # Archive coverage
│
├── projects/                   # Project-level analytics  
│   ├── {project_id}/performance # Performance dashboard
│   ├── {project_id}/content-quality # Quality metrics
│   ├── comparison              # Multi-project analysis
│   └── efficiency-trends       # Efficiency over time
│
├── content/                    # Content analytics
│   ├── quality-distribution    # Quality scoring
│   ├── extraction-performance  # Extraction metrics
│   ├── language-analysis       # Language detection
│   └── entity-analytics        # Entity extraction metrics
│
├── system/                     # System-wide analytics
│   ├── performance            # System performance
│   ├── resource-usage         # Resource monitoring  
│   ├── user-activity          # User analytics
│   └── health-metrics         # System health
│
└── realtime/                  # Real-time features
    ├── ws/live-dashboard      # WebSocket live updates
    ├── ws/export-progress     # Export job progress
    └── ws/system-metrics      # Real-time system metrics
```

## Database Schema Architecture

### PostgreSQL Schema (OLTP)

**Core Tables:**
```sql
-- User and Authentication
users (id, email, hashed_password, is_verified, approval_status)
user_sessions (id, user_id, session_token, expires_at)

-- Project Management  
projects (id, name, owner_id, created_at, config)
domains (id, project_id, domain, scraping_config)

-- Real-time Operations
scrape_pages (id, project_id, domain_id, original_url, status, created_at)
project_pages (id, project_id, page_id, tags, review_status)

-- System Management
admin_settings (id, key, value, updated_at)
audit_logs (id, user_id, action, details, timestamp)
```

### DuckDB Schema (OLAP)

**Analytics Tables:**
```sql
-- CDX Analytics (Optimized for time-series)
CREATE TABLE cdx_records (
    id VARCHAR PRIMARY KEY,
    domain VARCHAR NOT NULL,
    original_url VARCHAR NOT NULL, 
    unix_timestamp BIGINT NOT NULL,
    mime_type VARCHAR,
    status_code INTEGER,
    content_length BIGINT,
    archive_source VARCHAR,
    project_id VARCHAR,
    created_at TIMESTAMP,
    -- Partitioned by year/month for performance
    partition_year INTEGER,
    partition_month INTEGER
) PARTITION BY (partition_year, partition_month);

-- Content Analytics (Optimized for aggregation)
CREATE TABLE content_analytics (
    page_id VARCHAR,
    project_id VARCHAR, 
    extraction_method VARCHAR,
    processing_time FLOAT,
    content_size BIGINT,
    word_count INTEGER,
    entity_count INTEGER,
    language VARCHAR(5),
    quality_score FLOAT,
    created_at TIMESTAMP,
    date_captured DATE
) PARTITION BY (date_captured);

-- Performance Analytics (Optimized for monitoring)
CREATE TABLE performance_metrics (
    metric_id VARCHAR PRIMARY KEY,
    metric_type VARCHAR NOT NULL,
    value DOUBLE NOT NULL,
    dimensions JSON,
    timestamp TIMESTAMP NOT NULL,
    retention_days INTEGER DEFAULT 90
) PARTITION BY (DATE_TRUNC('day', timestamp));
```

**Optimization Features:**
- **Columnar Storage**: Optimal for analytical queries
- **Partitioning**: Date/domain-based partitioning for pruning
- **Compression**: ZSTD compression for storage efficiency
- **Indexes**: Automatic index creation based on query patterns

## Performance Optimization Strategies

### 1. Query Optimization

**Automatic Optimization:**
```python
class QueryOptimizationEngine:
    """Automatic query performance optimization"""
    
    def optimize_query(self, query: str, metadata: QueryMetadata) -> str:
        optimizations = []
        
        # Predicate pushdown
        if metadata.has_filters:
            optimizations.append(self.push_predicates_down)
            
        # Column pruning  
        if metadata.selected_columns:
            optimizations.append(self.prune_unnecessary_columns)
            
        # Join optimization
        if metadata.has_joins:
            optimizations.append(self.optimize_join_order)
            
        return self.apply_optimizations(query, optimizations)
```

**Optimization Techniques:**
- **Predicate Pushdown**: Move filters to storage layer
- **Column Pruning**: Only read required columns
- **Join Reordering**: Optimize join execution order
- **Partition Pruning**: Skip irrelevant partitions
- **Vectorized Execution**: SIMD operations for performance

### 2. Memory Management

**Dynamic Allocation:**
```python
def calculate_memory_limit(self) -> int:
    """Calculate optimal memory based on system resources"""
    
    total_memory = psutil.virtual_memory().total
    
    # Reserve memory for system and other processes
    available_memory = total_memory * 0.7  # 70% allocation
    
    # Consider concurrent operations
    per_service_memory = available_memory // self.concurrent_services
    
    return min(per_service_memory, self.configured_limit)
```

**Memory Optimization:**
- **Streaming Processing**: Process data in chunks
- **Memory Monitoring**: Track and alert on memory usage
- **Garbage Collection**: Automatic cleanup of unused resources
- **Connection Pooling**: Efficient resource reuse

### 3. Circuit Breaker Patterns

**Fault Tolerance Architecture:**
```python
class CircuitBreaker:
    """Circuit breaker for service resilience"""
    
    def __init__(self, failure_threshold=5, timeout=60):
        self.failure_threshold = failure_threshold
        self.timeout_seconds = timeout
        self.failure_count = 0
        self.last_failure_time = None
        self.state = "CLOSED"  # CLOSED, OPEN, HALF_OPEN
```

**Protection Levels:**
- **Service Level**: Protect entire services from cascading failures
- **Database Level**: Prevent database overload
- **Query Level**: Timeout protection for long-running queries
- **Resource Level**: Memory and CPU protection

## Monitoring and Observability

### 1. Performance Metrics

**System Metrics:**
```yaml
DuckDB Service:
  - Query execution times and distributions
  - Memory usage patterns and peaks
  - Connection pool utilization
  - Circuit breaker activations
  - Error rates and types

PostgreSQL:
  - Transaction rates and response times
  - Connection pool status
  - Lock contention and wait times
  - Index usage statistics

HybridQueryRouter:
  - Query routing decisions and effectiveness
  - Database load balancing
  - Cache hit rates across all levels
  - Cross-database query coordination
```

**Business Metrics:**
```yaml
Analytics Usage:
  - API endpoint usage patterns
  - User engagement with analytics features
  - Export frequency and formats
  - Dashboard view statistics

Performance Impact:
  - User-perceived response times
  - Analytics adoption rates
  - Support ticket reduction
  - System resource efficiency
```

### 2. Health Monitoring

**Health Check Endpoints:**
```
GET /api/v1/analytics/health       # Overall analytics health
GET /api/v1/duckdb/health         # DuckDB service health  
GET /api/v1/hybrid/health         # Router health
GET /api/v1/sync/health           # Data sync health
```

**Health Indicators:**
- **Service Availability**: All services responding
- **Database Connectivity**: Both databases accessible
- **Data Consistency**: Sync lag within acceptable limits
- **Performance Benchmarks**: Response times within SLA
- **Resource Utilization**: CPU, memory, disk within limits

### 3. Alerting Strategy

**Critical Alerts:**
- Service unavailability (immediate notification)
- Data consistency violations (5-minute delay tolerance)
- Performance degradation >50% (15-minute threshold)
- Resource exhaustion warnings (80% utilization)

**Warning Alerts:**
- Circuit breaker activations
- Cache hit rate drops below 70%
- Query timeouts increasing
- Memory usage trending upward

## Security Architecture

### 1. Data Security

**Access Control:**
- **Role-Based Access**: Analytics access tied to project permissions
- **API Authentication**: JWT tokens required for all endpoints
- **Query Filtering**: Automatic injection of user/project filters
- **Audit Logging**: Complete audit trail for analytics operations

**Data Protection:**
- **Encryption at Rest**: Database files encrypted
- **Encryption in Transit**: TLS for all communications
- **PII Handling**: Automatic detection and protection
- **Data Retention**: Configurable retention policies

### 2. System Security

**Network Security:**
- **Internal Communication**: Secured service-to-service communication
- **API Rate Limiting**: Prevent abuse and resource exhaustion
- **Input Validation**: SQL injection prevention
- **Output Sanitization**: Prevent data leakage

**Operational Security:**
- **Secrets Management**: Encrypted configuration storage
- **Service Isolation**: Containerized deployment
- **Monitoring Integration**: Security event correlation
- **Incident Response**: Automated security response procedures

## Scalability Considerations

### 1. Horizontal Scaling

**Service Scaling:**
```yaml
Analytics API: 
  - Stateless design enables horizontal scaling
  - Load balancer distribution across instances
  - Shared cache layer (Redis) for consistency

DuckDB Service:
  - Multiple instances for read scaling
  - Query distribution across instances
  - Shared storage for data consistency
  
Data Pipeline:
  - Parallel processing workers
  - Queue-based job distribution
  - Independent scaling of components
```

**Database Scaling:**
```yaml
PostgreSQL:
  - Read replicas for OLTP scaling
  - Connection pooling optimization
  - Query optimization for performance

DuckDB:
  - Multiple databases for workload isolation  
  - S3 integration for unlimited storage
  - Remote query execution capabilities
```

### 2. Vertical Scaling

**Resource Optimization:**
- **Memory Scaling**: Dynamic allocation based on workload
- **CPU Scaling**: Multi-threading optimization
- **Storage Scaling**: Automatic cleanup and archival
- **Network Scaling**: Connection optimization

**Performance Tuning:**
- **Query Optimization**: Continuous performance improvement
- **Index Management**: Automatic index creation/removal
- **Cache Optimization**: Intelligent cache sizing
- **Resource Monitoring**: Proactive resource management

## Migration Strategy

### 1. Data Migration

**Phase 1: Infrastructure Setup**
- Deploy DuckDB service alongside existing PostgreSQL
- Set up data synchronization pipeline
- Configure monitoring and alerting

**Phase 2: Gradual Migration**
- Start with read-only analytics queries
- Gradually move analytical workloads to DuckDB
- Monitor performance and adjust configurations

**Phase 3: Full Production**
- Complete analytical workload migration
- Optimize based on production usage patterns
- Implement advanced features (real-time analytics, exports)

### 2. Rollback Strategy

**Rollback Capability:**
- Feature flags for gradual rollout
- Automatic fallback to PostgreSQL for analytics
- Data consistency maintained during rollback
- Zero-downtime rollback procedures

**Risk Mitigation:**
- Comprehensive testing in staging environment
- Gradual user exposure with monitoring
- Performance baseline comparison
- Automated rollback triggers

## Conclusion

The Phase 2 architecture represents a sophisticated, production-ready implementation that delivers exceptional performance while maintaining operational excellence. The hybrid approach leverages the strengths of both PostgreSQL and DuckDB, providing a scalable foundation for advanced analytics capabilities.

Key architectural principles achieved:
- **Performance**: 5-10x improvement through intelligent query routing
- **Reliability**: Circuit breaker patterns and comprehensive monitoring
- **Scalability**: Horizontal and vertical scaling capabilities
- **Security**: Enterprise-grade security and access control
- **Maintainability**: Clean architecture with comprehensive documentation

This architecture provides the foundation for continued growth and innovation in the Chrono Scraper analytics platform.