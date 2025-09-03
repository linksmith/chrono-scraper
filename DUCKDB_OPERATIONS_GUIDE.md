# DuckDB Analytics Service - Operations Guide

## Overview

The DuckDB Analytics Service provides a high-performance, columnar analytics database for the Chrono Scraper platform. This guide covers operational aspects including deployment, monitoring, backup strategies, and troubleshooting.

## Service Architecture

### Core Components
- **DuckDBService**: Main service class with async operations
- **ConnectionPool**: Thread-safe connection management
- **CircuitBreaker**: Resilience pattern for fault tolerance
- **API Endpoints**: FastAPI integration for query execution and monitoring

### Key Features
- Thread-safe async operations via ThreadPoolExecutor
- Connection pooling with lifecycle management
- Circuit breaker pattern for service resilience
- Comprehensive error handling and monitoring
- Memory optimization and resource management
- Extension support (Parquet, JSON, HTTP, S3)
- Health checks and performance metrics

## Configuration

### Environment Variables

```bash
# Core Database Settings
DUCKDB_DATABASE_PATH="/var/lib/duckdb/chrono_analytics.db"
DUCKDB_MEMORY_LIMIT="4GB"
DUCKDB_WORKER_THREADS=4
DUCKDB_TEMP_DIRECTORY="/tmp/duckdb"
DUCKDB_MAX_MEMORY_PERCENTAGE=60

# Optional S3 Integration
DUCKDB_ENABLE_S3=false
AWS_ACCESS_KEY_ID=""
AWS_SECRET_ACCESS_KEY=""
AWS_DEFAULT_REGION="us-east-1"

# Parquet Settings
PARQUET_COMPRESSION="ZSTD"
PARQUET_ROW_GROUP_SIZE=1000000
PARQUET_PAGE_SIZE=1048576
PARQUET_ENABLE_DICTIONARY=true
```

### Memory Configuration
The service automatically calculates optimal memory usage:
- Uses percentage-based allocation (default: 60% of available RAM)
- Respects configured memory limits
- Monitors memory usage during query execution

## Deployment

### Docker Environment
```bash
# Database directory must be persistent
mkdir -p /var/lib/duckdb
chown -R app:app /var/lib/duckdb

# Temp directory for operations
mkdir -p /tmp/duckdb
chmod 755 /tmp/duckdb
```

### Service Initialization
```python
from app.services.duckdb_service import get_duckdb_service

# Service initializes automatically on first use
service = await get_duckdb_service()

# Manual initialization if needed
await service.initialize()
```

## Operational Excellence

### Backup Strategies

#### 1. Database File Backup
```bash
#!/bin/bash
# backup_duckdb.sh - Full database backup

DB_PATH="/var/lib/duckdb/chrono_analytics.db"
BACKUP_DIR="/backups/duckdb/$(date +%Y%m%d)"
mkdir -p "$BACKUP_DIR"

# Stop writes temporarily for consistent backup
# Copy database file
cp "$DB_PATH" "$BACKUP_DIR/chrono_analytics_$(date +%Y%m%d_%H%M%S).db"

# Compress backup
gzip "$BACKUP_DIR/chrono_analytics_"*.db

# Retention: Keep 30 days of backups
find /backups/duckdb -type f -name "*.gz" -mtime +30 -delete
```

#### 2. Export-Based Backup
```sql
-- Export critical tables to Parquet for backup
COPY (SELECT * FROM pages_analytics) TO '/backups/pages_analytics.parquet' (FORMAT PARQUET);
COPY (SELECT * FROM user_metrics) TO '/backups/user_metrics.parquet' (FORMAT PARQUET);
```

### Disaster Recovery

#### Recovery Time Objective (RTO): 5 minutes
#### Recovery Point Objective (RPO): 1 hour

**Recovery Procedures:**

1. **Database Corruption Recovery**
```bash
# Stop service
systemctl stop chrono-scraper

# Restore from latest backup
cd /var/lib/duckdb
cp /backups/duckdb/latest/chrono_analytics.db.gz .
gunzip chrono_analytics.db.gz

# Restart service
systemctl start chrono-scraper

# Verify integrity
curl http://localhost:8000/api/v1/duckdb/health
```

2. **Memory Issues Recovery**
```bash
# Check memory usage
curl http://localhost:8000/api/v1/duckdb/statistics | jq '.system'

# Adjust memory limits
export DUCKDB_MEMORY_LIMIT="2GB"
systemctl restart chrono-scraper

# Reset circuit breaker if needed
curl -X POST http://localhost:8000/api/v1/duckdb/circuit-breaker/reset
```

### Monitoring and Alerting

#### Health Check Endpoints
```bash
# Basic health check
curl http://localhost:8000/api/v1/duckdb/health

# Detailed statistics
curl http://localhost:8000/api/v1/duckdb/statistics

# Performance metrics
curl http://localhost:8000/api/v1/duckdb/templates/performance-metrics
```

#### Key Metrics to Monitor

**Service Health:**
- Service initialization status
- Database file existence and size
- Circuit breaker state
- Connection pool utilization

**Performance Metrics:**
- Query success rate (target: >99%)
- Average query execution time (target: <1s)
- Memory usage percentage (alert: >80%)
- System resource utilization

**Alert Thresholds:**
```yaml
# Prometheus alerting rules
- alert: DuckDBServiceDown
  expr: duckdb_service_health == 0
  for: 30s
  labels:
    severity: critical

- alert: DuckDBHighMemoryUsage
  expr: duckdb_memory_usage_percent > 90
  for: 2m
  labels:
    severity: warning

- alert: DuckDBSlowQueries
  expr: duckdb_avg_query_time > 5
  for: 5m
  labels:
    severity: warning

- alert: DuckDBCircuitBreakerOpen
  expr: duckdb_circuit_breaker_state == "open"
  for: 1m
  labels:
    severity: warning
```

### Maintenance Procedures

#### Daily Operations
```bash
#!/bin/bash
# daily_maintenance.sh

# Check service health
curl -s http://localhost:8000/api/v1/duckdb/health | jq '.status'

# Monitor disk usage
du -sh /var/lib/duckdb/

# Check for large temp files
find /tmp/duckdb -size +100M -ls

# Archive old logs
find /var/log/chrono-scraper -name "*duckdb*" -mtime +7 -exec gzip {} \;
```

#### Weekly Operations
```bash
#!/bin/bash
# weekly_maintenance.sh

# Analyze query performance
curl -s http://localhost:8000/api/v1/duckdb/statistics | \
    jq '.query_analysis.queries_over_5s'

# Database optimization (if needed)
# Note: DuckDB is self-optimizing, but manual VACUUM can help
psql -c "SELECT pg_size_pretty(pg_database_size('chrono_scraper'));"

# Check backup retention
ls -la /backups/duckdb/ | tail -10
```

#### Monthly Operations
```bash
#!/bin/bash
# monthly_maintenance.sh

# Full backup verification
latest_backup=$(ls -t /backups/duckdb/*/chrono_analytics_*.db.gz | head -1)
gunzip -t "$latest_backup" && echo "Backup integrity OK"

# Performance analysis report
curl -s http://localhost:8000/api/v1/duckdb/statistics > /tmp/duckdb_stats.json

# Capacity planning
df -h /var/lib/duckdb
du -sh /var/lib/duckdb/chrono_analytics.db
```

### Connection Pooling Management

#### Pool Configuration
```python
# Connection pool is automatically managed
# Monitor pool status via health endpoint

# Pool metrics available:
# - total_connections
# - available_connections  
# - max_connections (default: worker_threads * 2)
```

#### Pool Troubleshooting
```bash
# Check pool exhaustion
curl -s http://localhost:8000/api/v1/duckdb/health | \
    jq '.connection_pool'

# If pool is exhausted:
# 1. Check for long-running queries
# 2. Increase worker threads if needed
# 3. Restart service to reset pool
```

### Performance Optimization

#### Query Optimization
```sql
-- Use EXPLAIN to analyze query plans
EXPLAIN SELECT * FROM large_table WHERE date > '2024-01-01';

-- Create indexes for frequently queried columns
-- Note: DuckDB automatically optimizes many queries

-- Use column pruning
SELECT id, title FROM pages WHERE created_at > '2024-01-01';

-- Prefer columnar operations
SELECT domain, COUNT(*) FROM pages GROUP BY domain;
```

#### Memory Optimization
```sql
-- Monitor memory usage during queries
SELECT current_setting('memory_limit');

-- Use LIMIT for large result sets
SELECT * FROM large_table LIMIT 1000;

-- Stream large exports
COPY (SELECT * FROM large_table) TO '/path/to/output.parquet' (FORMAT PARQUET);
```

### Troubleshooting Guide

#### Common Issues

**1. Service Won't Start**
```bash
# Check database file permissions
ls -la /var/lib/duckdb/chrono_analytics.db

# Check temp directory permissions
ls -ld /tmp/duckdb

# Review startup logs
tail -f /var/log/chrono-scraper/duckdb.log
```

**2. Memory Issues**
```bash
# Check current memory usage
curl -s http://localhost:8000/api/v1/duckdb/statistics | jq '.system'

# Reduce memory limit temporarily
export DUCKDB_MEMORY_LIMIT="2GB"

# Monitor memory-intensive queries
tail -f /var/log/chrono-scraper/duckdb.log | grep "memory"
```

**3. Slow Queries**
```bash
# Check query performance
curl -s http://localhost:8000/api/v1/duckdb/statistics | jq '.performance'

# Review slow queries in logs
grep "execution_time.*[5-9]\." /var/log/chrono-scraper/duckdb.log
```

**4. Circuit Breaker Tripped**
```bash
# Check circuit breaker status
curl -s http://localhost:8000/api/v1/duckdb/health | jq '.circuit_breaker'

# Manual reset if issue is resolved
curl -X POST http://localhost:8000/api/v1/duckdb/circuit-breaker/reset
```

### Security Considerations

#### File Permissions
```bash
# Database file should be owned by application user
chown app:app /var/lib/duckdb/chrono_analytics.db
chmod 640 /var/lib/duckdb/chrono_analytics.db

# Temp directory permissions
chmod 755 /tmp/duckdb
```

#### API Security
- All query endpoints require authentication
- Health checks are public for monitoring
- Input validation on all queries
- SQL injection protection via parameterized queries

#### Data Protection
```bash
# Encrypt backups
gpg --cipher-algo AES256 --compress-algo 1 --symmetric \
    chrono_analytics_backup.db.gz
```

### Integration with Other Services

#### PostgreSQL Data Sync
```sql
-- Example: Sync data from PostgreSQL to DuckDB
CREATE TABLE pages_sync AS 
SELECT * FROM postgres_scan('host=postgres dbname=chrono_scraper user=app', 'pages');
```

#### Meilisearch Integration
```python
# Export analytics results to Meilisearch for search
results = await duckdb_service.execute_query(
    "SELECT domain, COUNT(*) as page_count FROM pages GROUP BY domain"
)
# Index results in Meilisearch for dashboard search
```

### Capacity Planning

#### Storage Requirements
- Base database: ~100MB for 1M pages
- Indexes: ~20% of data size
- Temp space: 2x memory limit during large operations
- Backup storage: 3x database size (compressed, retained)

#### Memory Requirements
- Base: 512MB minimum
- Per 1M rows: ~200MB additional
- Query processing: 2-4x data size being processed
- Buffer pool: 60% of available RAM (configurable)

#### CPU Requirements
- Base: 2 cores minimum
- Parallel processing: 1 core per worker thread
- Query complexity affects CPU usage

### Emergency Procedures

#### 3 AM Troubleshooting Runbook

**Service Down:**
1. Check health endpoint: `curl http://localhost:8000/api/v1/duckdb/health`
2. Check logs: `tail -50 /var/log/chrono-scraper/duckdb.log`
3. Restart service: `systemctl restart chrono-scraper`
4. Verify recovery: `curl http://localhost:8000/api/v1/duckdb/health`

**Database Corruption:**
1. Stop service: `systemctl stop chrono-scraper`
2. Backup corrupted file: `mv chrono_analytics.db chrono_analytics.db.corrupt`
3. Restore from backup: `cp /backups/latest/chrono_analytics.db.gz . && gunzip chrono_analytics.db.gz`
4. Start service: `systemctl start chrono-scraper`
5. Verify: `curl http://localhost:8000/api/v1/duckdb/health`

**Memory Exhaustion:**
1. Check memory usage: `free -h && docker stats`
2. Reduce DuckDB memory limit: `export DUCKDB_MEMORY_LIMIT="1GB"`
3. Restart service: `systemctl restart chrono-scraper`
4. Monitor recovery: `watch 'curl -s http://localhost:8000/api/v1/duckdb/statistics | jq ".system.process_memory_mb"'`

**Contact Information:**
- On-call: [Your on-call system]
- Escalation: [Your escalation path]
- Documentation: This guide + `/docs/api/duckdb`

This operations guide provides comprehensive coverage for managing the DuckDB Analytics Service in production environments, ensuring high availability and optimal performance.