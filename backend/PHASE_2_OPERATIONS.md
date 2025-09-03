# Phase 2 DuckDB Analytics System - Operations Manual

## 🛠️ Day-to-Day Operations & Troubleshooting

This comprehensive operations manual provides everything needed for the successful day-to-day management, monitoring, maintenance, and troubleshooting of the Phase 2 DuckDB analytics system.

## 📊 System Health Monitoring

### Daily Health Check Procedures

#### 1. Morning Health Dashboard Review
```bash
# Run comprehensive health check
cd /opt/chrono-scraper
./scripts/health_check.sh

# Check system resource usage
./scripts/performance_monitor.sh

# Review overnight logs for errors
docker-compose logs --since 24h backend | grep -i error
docker-compose logs --since 24h duckdb-service | grep -i error
```

#### 2. Key Performance Indicators (KPIs) to Monitor

**System Health KPIs**
```yaml
Critical Thresholds (Immediate Action Required):
  - System availability: <99%
  - Backend API response time: >5 seconds
  - Database connection failures: >5 in 1 hour
  - Memory usage: >90%
  - Disk space: >95% full

Warning Thresholds (Investigation Required):
  - Analytics query response time: >10 seconds
  - Cache hit rate: <70%
  - Error rate: >5%
  - CPU usage: >80% for 15+ minutes
  - DuckDB memory usage: >75% of allocated limit
```

**Business KPIs**
```yaml
Daily Metrics to Track:
  - Total analytics queries executed: Target >10,000/day
  - Average query response time: Target <2 seconds
  - Export success rate: Target >98%
  - WebSocket connection stability: Target >95%
  - Data synchronization lag: Target <5 minutes
```

### Automated Monitoring Setup

#### 1. Grafana Dashboard Configuration
```bash
# Import pre-configured dashboards
curl -X POST http://localhost:3000/api/dashboards/db \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <grafana-api-key>" \
  -d @config/grafana/phase2-analytics-dashboard.json

# Key dashboard panels to configure:
# - System overview (CPU, Memory, Disk)
# - Database performance (Query times, Connection pools)
# - Analytics performance (DuckDB query metrics)
# - Error rates and patterns
# - Cache performance
# - Business metrics
```

#### 2. Alert Configuration
```yaml
# Critical Alerts (Immediate notification)
alerts:
  system_down:
    condition: "Backend API returning 5xx for >2 minutes"
    notification: "SMS + Email + Slack"
    
  database_failure:
    condition: "PostgreSQL or DuckDB connection failures"
    notification: "SMS + Email + Slack"
    
  high_error_rate:
    condition: "Error rate >10% for 5 minutes"
    notification: "Email + Slack"

# Warning Alerts (Next business day)
warnings:
  slow_queries:
    condition: "95th percentile query time >10s for 15 minutes"
    notification: "Email"
    
  cache_degradation:
    condition: "Cache hit rate <60% for 30 minutes"
    notification: "Email"
    
  resource_pressure:
    condition: "CPU >85% or Memory >90% for 30 minutes"
    notification: "Email"
```

### Health Check Endpoints

#### 1. System Health Endpoints
```bash
# Basic health check
curl -f http://localhost:8000/api/v1/health

# Analytics system health
curl -f http://localhost:8000/api/v1/analytics/health

# Detailed component health
curl -f http://localhost:8000/api/v1/analytics/config

# DuckDB service health
curl -f http://localhost:8000/api/v1/duckdb/health
```

#### 2. Health Response Interpretation
```json
{
  "status": "healthy",  // healthy, degraded, unhealthy
  "components": {
    "duckdb": {
      "status": "healthy",
      "response_time": 0.023,     // <0.1s = excellent, <0.5s = good, >1s = poor
      "memory_usage": "2.3GB",    // Monitor vs configured limit
      "active_connections": 5     // Monitor vs pool size
    },
    "postgresql": {
      "status": "healthy",
      "response_time": 0.012,
      "active_connections": 23,   // Monitor vs max_connections
      "pool_utilization": 0.46    // <0.8 = good, >0.9 = investigate
    },
    "redis_cache": {
      "status": "healthy",
      "hit_rate": 87.6,          // >80% = good, <60% = poor
      "memory_usage": "512MB",
      "connected_clients": 15
    }
  },
  "circuit_breakers": {
    "duckdb": "closed",          // closed = good, open = service failing
    "postgresql": "closed"
  }
}
```

## 🔧 Routine Maintenance Procedures

### Daily Maintenance Tasks

#### 1. Morning Startup Checklist (5 minutes)
```bash
#!/bin/bash
# Daily morning checklist script

echo "=== Daily Morning Checklist ==="
date

# 1. Check all services are running
echo "✅ Checking service status..."
docker-compose ps | grep -v "Up" && echo "⚠️  Some services are not running!"

# 2. Verify disk space
echo "✅ Checking disk space..."
df -h | awk '$5 > 90 {print "⚠️  " $0}' || echo "Disk space OK"

# 3. Check recent errors
echo "✅ Checking for recent errors..."
ERROR_COUNT=$(docker-compose logs --since 24h | grep -ci error)
echo "Errors in last 24h: $ERROR_COUNT"
if [ $ERROR_COUNT -gt 50 ]; then
    echo "⚠️  High error count detected!"
fi

# 4. Verify analytics performance
echo "✅ Testing analytics endpoint..."
RESPONSE_TIME=$(curl -w "%{time_total}" -s -o /dev/null http://localhost:8000/api/v1/analytics/health)
echo "Analytics health check: ${RESPONSE_TIME}s"

# 5. Check backup status
echo "✅ Checking backup status..."
LATEST_BACKUP=$(ls -t backups/ | head -1)
echo "Latest backup: $LATEST_BACKUP"

echo "=== Morning Checklist Complete ==="
```

#### 2. Log Analysis and Rotation (10 minutes)
```bash
# Analyze overnight logs for patterns
./scripts/manage_logs.sh analyze

# Check for memory leaks or performance degradation
docker stats --no-stream | awk 'NR>1 {print $1 ": CPU=" $3 " MEM=" $4}'

# Monitor DuckDB query performance trends
grep "Query executed" logs/backend.log | tail -100 | \
  awk '{sum+=$NF} END {print "Average query time last 100 queries:", sum/NR "s"}'
```

### Weekly Maintenance Tasks

#### 1. Performance Review (30 minutes)
```bash
#!/bin/bash
# Weekly performance review script

echo "=== Weekly Performance Review ==="
WEEK_AGO=$(date -d "7 days ago" +"%Y-%m-%d")

# 1. Query performance analysis
echo "📊 Analytics Query Performance (Last 7 days):"
echo "Total queries: $(grep 'Query executed' logs/backend.log | wc -l)"
echo "Average response time: $(grep 'execution_time' logs/backend.log | \
  awk -F'execution_time.' '{sum+=$2} END {print sum/NR "s"}')"

# 2. Cache performance review
echo "📦 Cache Performance:"
CACHE_STATS=$(curl -s http://localhost:8000/api/v1/analytics/health | jq '.components.redis_cache')
echo "Cache hit rate: $(echo $CACHE_STATS | jq -r '.hit_rate')%"

# 3. Database performance
echo "🗄️  Database Performance:"
docker-compose exec postgres psql -U chrono_scraper -d chrono_scraper -c "
  SELECT 
    schemaname,
    tablename,
    seq_scan,
    seq_tup_read,
    idx_scan,
    idx_tup_fetch
  FROM pg_stat_user_tables 
  ORDER BY seq_tup_read DESC 
  LIMIT 10;
"

# 4. Resource utilization trends
echo "💾 Resource Utilization Trends:"
echo "Peak CPU usage: $(grep 'cpu_usage_percent' logs/metrics.log | sort -n | tail -1)"
echo "Peak memory usage: $(grep 'memory_usage_mb' logs/metrics.log | sort -n | tail -1)"

# 5. Error pattern analysis
echo "🚨 Error Pattern Analysis:"
grep -i error logs/backend.log | \
  awk '{print $NF}' | sort | uniq -c | sort -nr | head -5

echo "=== Weekly Review Complete ==="
```

#### 2. Database Maintenance
```bash
#!/bin/bash
# Weekly database maintenance

echo "🗄️  Running database maintenance..."

# PostgreSQL maintenance
docker-compose exec postgres psql -U chrono_scraper -d chrono_scraper << 'EOF'
-- Update table statistics
ANALYZE;

-- Reindex heavily used tables
REINDEX TABLE pages;
REINDEX TABLE scrape_pages;
REINDEX TABLE projects;

-- Check for bloated tables
SELECT 
  tablename,
  pg_size_pretty(pg_total_relation_size(tablename::regclass)) as size,
  pg_size_pretty(pg_relation_size(tablename::regclass)) as table_size,
  pg_size_pretty(pg_indexes_size(tablename::regclass)) as index_size
FROM pg_tables 
WHERE schemaname = 'public'
ORDER BY pg_total_relation_size(tablename::regclass) DESC;
EOF

# DuckDB maintenance
echo "🦆 DuckDB maintenance..."
docker-compose exec backend python -c "
import asyncio
from app.services.duckdb_service import duckdb_service

async def maintenance():
    await duckdb_service.initialize()
    # Run ANALYZE to update statistics
    await duckdb_service.execute_query('ANALYZE;')
    # Check database size
    result = await duckdb_service.execute_query('PRAGMA database_size;')
    print(f'DuckDB size: {result.data}')
    
asyncio.run(maintenance())
"

echo "Database maintenance complete"
```

### Monthly Maintenance Tasks

#### 1. Comprehensive System Review (2 hours)
```bash
# 1. Security updates
sudo apt update && sudo apt upgrade -y

# 2. Container image updates
docker-compose pull
./scripts/update.sh

# 3. Certificate renewal check
certbot certificates

# 4. Backup system verification
./scripts/restore.sh $(ls -t backups/ | head -1 | cut -d_ -f2) config
echo "Backup restoration test completed"

# 5. Performance benchmarking
python scripts/performance_benchmark.py --generate-report

# 6. Log archive and cleanup
./scripts/manage_logs.sh rotate 30
```

## 🚨 Incident Response Procedures

### Critical Incident Response (P0 - System Down)

#### 1. System Down Response Workflow
```bash
# STEP 1: Immediate Assessment (2 minutes)
echo "🚨 INCIDENT RESPONSE - System Down"
echo "Time: $(date)"

# Quick service status check
docker-compose ps
curl -f http://localhost:8000/api/v1/health || echo "Backend DOWN"

# STEP 2: Service Recovery Attempt (5 minutes)
echo "🔄 Attempting service recovery..."

# Restart all services
docker-compose restart

# Wait for services to start
sleep 30

# Re-test endpoints
if curl -f http://localhost:8000/api/v1/health; then
    echo "✅ Service recovery successful"
else
    echo "❌ Service recovery failed - escalating"
    # Escalate to senior engineer
    # Send critical alert notifications
fi

# STEP 3: Incident Documentation
echo "📝 Documenting incident..."
echo "Incident: System Down at $(date)" >> incidents.log
docker-compose logs --tail=100 >> incident_logs_$(date +%Y%m%d_%H%M%S).log
```

#### 2. Database Connection Failure Response
```bash
#!/bin/bash
# Database incident response

echo "🗄️  Database Connection Failure Response"

# Check PostgreSQL status
if ! docker-compose exec postgres pg_isready -U chrono_scraper; then
    echo "❌ PostgreSQL is not responding"
    
    # Check container status
    docker-compose logs postgres | tail -50
    
    # Attempt restart
    docker-compose restart postgres
    sleep 30
    
    # Re-test connection
    if docker-compose exec postgres pg_isready -U chrono_scraper; then
        echo "✅ PostgreSQL recovered"
    else
        echo "❌ PostgreSQL restart failed - manual intervention required"
        # Escalate immediately
    fi
fi

# Check DuckDB status
python -c "
import asyncio
from app.services.duckdb_service import duckdb_service

async def check_duckdb():
    try:
        await duckdb_service.initialize()
        result = await duckdb_service.execute_query('SELECT 1')
        print('✅ DuckDB is responding')
    except Exception as e:
        print(f'❌ DuckDB error: {e}')
        
asyncio.run(check_duckdb())
"
```

### High Priority Incidents (P1)

#### 1. Performance Degradation Response
```bash
#!/bin/bash
# Performance degradation incident response

echo "⚡ Performance Degradation Investigation"

# 1. Identify bottlenecks
echo "🔍 Identifying performance bottlenecks..."

# Check system resources
echo "CPU Usage: $(top -bn1 | grep "Cpu(s)" | awk '{print $2}')"
echo "Memory Usage: $(free | grep Mem | awk '{printf("%.1f%%", $3/$2 * 100.0)}')"
echo "Disk I/O: $(iostat | tail -n +4)"

# 2. Database performance analysis
echo "🗄️  Database Performance Analysis:"

# PostgreSQL slow queries
docker-compose exec postgres psql -U chrono_scraper -d chrono_scraper -c "
  SELECT query, calls, total_time, mean_time 
  FROM pg_stat_statements 
  ORDER BY total_time DESC 
  LIMIT 5;
"

# DuckDB performance metrics
curl -s http://localhost:8000/api/v1/analytics/health | \
  jq '.performance_metrics'

# 3. Cache analysis
echo "📦 Cache Performance:"
CACHE_HIT_RATE=$(curl -s http://localhost:8000/api/v1/analytics/health | \
  jq -r '.components.redis_cache.hit_rate')
echo "Cache hit rate: ${CACHE_HIT_RATE}%"

if (( $(echo "$CACHE_HIT_RATE < 70" | bc -l) )); then
    echo "⚠️  Low cache hit rate detected - investigating cache issues"
    docker-compose exec redis redis-cli -a "$REDIS_PASSWORD" info memory
fi

# 4. Circuit breaker status
echo "🔌 Circuit Breaker Status:"
curl -s http://localhost:8000/api/v1/analytics/health | \
  jq '.circuit_breakers'
```

#### 2. High Error Rate Response
```bash
#!/bin/bash
# High error rate incident response

echo "🚨 High Error Rate Investigation"

# 1. Error pattern analysis
echo "📊 Recent error patterns:"
docker-compose logs --since 1h backend | grep -i error | \
  awk '{print $NF}' | sort | uniq -c | sort -nr

# 2. Specific error investigation
echo "🔍 Detailed error analysis:"
docker-compose logs --since 1h backend | grep -i error | tail -20

# 3. Check external service dependencies
echo "🌐 External service health:"
curl -f https://api.firecrawl.dev/health || echo "Firecrawl API issue"
curl -f https://archive.org || echo "Internet Archive issue"

# 4. Database connection pool status
echo "🗄️  Database connection status:"
docker-compose exec postgres psql -U chrono_scraper -d chrono_scraper -c "
  SELECT state, count(*) 
  FROM pg_stat_activity 
  WHERE datname = 'chrono_scraper' 
  GROUP BY state;
"
```

### Warning Level Incidents (P2)

#### 1. Slow Query Investigation
```bash
#!/bin/bash
# Slow query investigation

echo "🐌 Slow Query Investigation"

# 1. Identify slow analytics queries
echo "📊 Slow DuckDB queries (>5 seconds):"
grep "Query executed" logs/backend.log | \
  awk '$NF > 5 {print $0}' | tail -10

# 2. PostgreSQL slow queries
docker-compose exec postgres psql -U chrono_scraper -d chrono_scraper -c "
  SELECT 
    query,
    calls,
    total_time,
    mean_time,
    max_time
  FROM pg_stat_statements 
  WHERE mean_time > 1000
  ORDER BY mean_time DESC 
  LIMIT 10;
"

# 3. Query optimization recommendations
echo "💡 Optimization recommendations:"
echo "- Consider adding indexes for frequently filtered columns"
echo "- Review query complexity and add appropriate LIMIT clauses"
echo "- Check if cache warming is needed for common queries"
```

## 🔧 Common Troubleshooting Scenarios

### Scenario 1: DuckDB Memory Issues

#### Symptoms:
- DuckDB queries failing with memory errors
- System memory usage near 100%
- Analytics endpoints timing out

#### Troubleshooting Steps:
```bash
# 1. Check current DuckDB memory usage
curl -s http://localhost:8000/api/v1/analytics/health | \
  jq '.components.duckdb.memory_usage'

# 2. Review DuckDB configuration
docker-compose exec backend python -c "
from app.core.config import settings
print(f'DuckDB Memory Limit: {settings.DUCKDB_MEMORY_LIMIT}')
print(f'DuckDB Worker Threads: {settings.DUCKDB_WORKER_THREADS}')
print(f'Max Memory Percentage: {settings.DUCKDB_MAX_MEMORY_PERCENTAGE}')
"

# 3. Check for memory leaks
docker stats --no-stream | grep backend

# 4. Restart DuckDB service if needed
docker-compose restart backend

# 5. Temporary memory increase (if safe)
# Edit .env: DUCKDB_MEMORY_LIMIT=32GB
# docker-compose up -d backend
```

#### Resolution:
- Adjust DUCKDB_MEMORY_LIMIT in .env file
- Reduce DUCKDB_WORKER_THREADS if necessary
- Implement query result pagination
- Add query complexity limits

### Scenario 2: Cache Performance Degradation

#### Symptoms:
- Cache hit rate below 70%
- Analytics queries slower than usual
- Redis memory usage high

#### Troubleshooting Steps:
```bash
# 1. Check Redis status and memory
docker-compose exec redis redis-cli -a "$REDIS_PASSWORD" info memory

# 2. Analyze cache key patterns
docker-compose exec redis redis-cli -a "$REDIS_PASSWORD" --scan | head -20

# 3. Check cache eviction statistics
docker-compose exec redis redis-cli -a "$REDIS_PASSWORD" info stats | grep evicted

# 4. Review cache configuration
curl -s http://localhost:8000/api/v1/analytics/config | jq '.caching_config'

# 5. Clear cache if needed (last resort)
docker-compose exec redis redis-cli -a "$REDIS_PASSWORD" FLUSHALL
```

#### Resolution:
- Increase Redis memory limit
- Adjust cache TTL values
- Review cache key strategies
- Implement cache warming for common queries

### Scenario 3: Data Synchronization Issues

#### Symptoms:
- Analytics data doesn't match transactional data
- Sync lag exceeding 10 minutes
- Sync service errors in logs

#### Troubleshooting Steps:
```bash
# 1. Check sync service status
curl -s http://localhost:8000/api/v1/data-sync/status

# 2. Review sync metrics
docker-compose logs data-sync-service | grep -i "sync operation"

# 3. Check CDC (Change Data Capture) status
docker-compose exec postgres psql -U chrono_scraper -d chrono_scraper -c "
  SELECT * FROM pg_replication_slots;
"

# 4. Verify data consistency
python scripts/verify_data_consistency.py

# 5. Manual sync trigger if needed
curl -X POST http://localhost:8000/api/v1/data-sync/trigger-full-sync
```

#### Resolution:
- Restart sync service
- Clear sync queue if corrupted
- Run full data synchronization
- Update sync configuration

### Scenario 4: Export Job Failures

#### Symptoms:
- Export jobs stuck in "processing" status
- Export downloads failing
- High memory usage during exports

#### Troubleshooting Steps:
```bash
# 1. Check export job queue
curl -s http://localhost:8000/api/v1/analytics/export/jobs | jq '.jobs[0:5]'

# 2. Check export worker status
docker-compose exec celery-worker celery -A app.tasks.celery_app inspect active

# 3. Review export errors
docker-compose logs celery-worker | grep -i export

# 4. Check temporary disk space
df -h /tmp

# 5. Clean up old export files
find exports/ -name "*.xlsx" -mtime +2 -delete
find exports/ -name "*.csv" -mtime +2 -delete
```

#### Resolution:
- Restart Celery workers
- Clean up temporary files
- Reduce export dataset size
- Increase worker memory limits

## 📈 Performance Optimization

### Query Performance Optimization

#### 1. DuckDB Query Optimization
```sql
-- Create performance-optimized views for common analytics queries
CREATE VIEW IF NOT EXISTS analytics_daily_summary AS
SELECT 
    date_trunc('day', created_at) as day,
    project_id,
    domain_id,
    COUNT(*) as total_pages,
    COUNT(CASE WHEN status = 'completed' THEN 1 END) as completed_pages,
    AVG(content_size) as avg_content_size,
    AVG(processing_time) as avg_processing_time
FROM pages 
WHERE created_at >= CURRENT_DATE - INTERVAL 30 DAY
GROUP BY 1, 2, 3;

-- Create indexes for common query patterns
CREATE INDEX IF NOT EXISTS idx_pages_created_project ON pages(created_at, project_id);
CREATE INDEX IF NOT EXISTS idx_pages_status_domain ON pages(status, domain_id);
```

#### 2. PostgreSQL Query Optimization
```sql
-- Identify and optimize slow queries
SELECT 
    query,
    calls,
    total_time,
    mean_time,
    (total_time/calls) as avg_time
FROM pg_stat_statements 
WHERE calls > 100 
ORDER BY total_time DESC 
LIMIT 10;

-- Create composite indexes for common query patterns  
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_pages_project_created 
ON pages(project_id, created_at DESC) 
WHERE status = 'completed';

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_scrape_pages_domain_status
ON scrape_pages(domain_id, status, created_at);
```

### Cache Optimization Strategies

#### 1. Intelligent Cache Warming
```python
# Cache warming script for common queries
#!/usr/bin/env python3
import asyncio
import httpx
from datetime import datetime, timedelta

async def warm_analytics_cache():
    """Pre-warm cache with common analytics queries"""
    client = httpx.AsyncClient()
    
    # Common time ranges
    time_ranges = [
        {'days': 1, 'granularity': 'hour'},
        {'days': 7, 'granularity': 'day'},
        {'days': 30, 'granularity': 'day'}
    ]
    
    # Get top projects
    projects = await client.get('/api/v1/projects/')
    top_projects = projects.json()['data'][:10]
    
    # Warm cache for each project
    for project in top_projects:
        for time_range in time_ranges:
            end_date = datetime.now()
            start_date = end_date - timedelta(days=time_range['days'])
            
            url = f"/api/v1/analytics/projects/{project['id']}/performance"
            params = {
                'start_date': start_date.isoformat(),
                'end_date': end_date.isoformat(),
                'granularity': time_range['granularity']
            }
            
            try:
                await client.get(url, params=params)
                print(f"Warmed cache for project {project['id']}")
            except Exception as e:
                print(f"Failed to warm cache: {e}")
    
    await client.aclose()

if __name__ == "__main__":
    asyncio.run(warm_analytics_cache())
```

#### 2. Cache Performance Tuning
```bash
# Optimize Redis configuration for analytics workload
docker-compose exec redis redis-cli -a "$REDIS_PASSWORD" << 'EOF'
CONFIG SET maxmemory-policy allkeys-lru
CONFIG SET maxmemory-samples 10
CONFIG SET timeout 300
CONFIG SET tcp-keepalive 300
CONFIG REWRITE
EOF

# Monitor cache performance
docker-compose exec redis redis-cli -a "$REDIS_PASSWORD" info stats | \
  grep -E "(keyspace_hits|keyspace_misses|expired_keys|evicted_keys)"
```

### System Resource Optimization

#### 1. Memory Optimization
```bash
# PostgreSQL memory tuning
cat >> config/postgresql.conf << 'EOF'
# Memory optimization for analytics workload
shared_buffers = 6GB                    # 25% of total RAM
effective_cache_size = 18GB             # 75% of total RAM  
work_mem = 256MB                        # For complex queries
maintenance_work_mem = 1GB              # For maintenance operations
temp_buffers = 32MB                     # Temporary table memory
EOF

# DuckDB memory optimization
# Adjust in .env file:
# DUCKDB_MEMORY_LIMIT=16GB
# DUCKDB_MAX_MEMORY_PERCENTAGE=60
```

#### 2. CPU Optimization
```bash
# Optimize worker processes based on CPU cores
CPU_CORES=$(nproc)
OPTIMAL_WORKERS=$((CPU_CORES * 2))

# Update docker-compose.yml
sed -i "s/--concurrency=4/--concurrency=$OPTIMAL_WORKERS/" docker-compose.production.yml

# DuckDB worker thread optimization
echo "DUCKDB_WORKER_THREADS=$CPU_CORES" >> .env
```

## 📊 Capacity Planning & Scaling

### Performance Baseline Metrics

#### Current System Capacity (as of deployment)
```yaml
Query Performance:
  - Simple analytics queries: <1 second
  - Complex aggregations: 2-5 seconds
  - Time series analysis: 5-10 seconds
  - Export generation: 30-120 seconds

Throughput Capacity:
  - Concurrent analytics users: 100-200
  - Queries per minute: 1,000-2,000
  - Data ingestion rate: 10,000 records/minute
  - Export jobs: 5-10 concurrent

Resource Utilization Baselines:
  - CPU utilization: 30-50% normal operation
  - Memory usage: 60-70% of allocated
  - Disk I/O: <50% utilization
  - Network: <100 Mbps
```

### Scaling Triggers & Thresholds

#### Scale-Up Triggers
```yaml
CPU Scaling:
  - Trigger: CPU >80% for 15+ minutes
  - Action: Increase CPU cores by 50%
  - Timeline: Next maintenance window

Memory Scaling:
  - Trigger: Memory >85% for 30+ minutes  
  - Action: Increase RAM by 50%
  - Timeline: Next maintenance window

Storage Scaling:
  - Trigger: Disk >90% full
  - Action: Increase storage by 100%
  - Timeline: Within 24 hours

Analytics Performance Scaling:
  - Trigger: P95 query time >10 seconds for 1 hour
  - Action: Scale DuckDB resources or add read replicas
  - Timeline: Within 48 hours
```

#### Horizontal Scaling Strategy
```yaml
Read Replicas:
  - PostgreSQL: Add read replicas for report queries
  - DuckDB: Implement query distribution across nodes
  - Redis: Implement Redis Cluster for cache distribution

Load Balancing:
  - API Gateway: Distribute requests across multiple backend instances
  - Database Load Balancing: Route read queries to replicas
  - Analytics Load Balancing: Distribute heavy queries
```

## 🎯 Standard Operating Procedures (SOPs)

### SOP 1: Monthly System Review

**Frequency**: First Monday of each month  
**Duration**: 2-3 hours  
**Responsible**: Senior DevOps Engineer

**Procedure**:
1. **Performance Analysis** (45 minutes)
   - Review monthly performance metrics
   - Identify performance trends and degradations
   - Update performance baselines if needed
   - Generate performance report

2. **Capacity Planning Review** (30 minutes)
   - Review resource utilization trends
   - Project capacity needs for next 3 months
   - Plan infrastructure scaling if needed
   - Update capacity planning documentation

3. **Security Review** (30 minutes)
   - Review access logs and authentication metrics
   - Check for security vulnerabilities
   - Update SSL certificates if expiring
   - Review backup security and encryption

4. **System Updates** (30 minutes)
   - Plan and schedule system updates
   - Review dependency updates
   - Update container images
   - Schedule maintenance windows

5. **Documentation Update** (15 minutes)
   - Update operational procedures
   - Document any configuration changes
   - Update troubleshooting guides
   - Review and update contact information

### SOP 2: Incident Response Escalation

**Severity Levels**:
- **P0 (Critical)**: System completely down, revenue impact
- **P1 (High)**: Major functionality impaired, user impact
- **P2 (Medium)**: Minor functionality issues, workaround available
- **P3 (Low)**: Cosmetic issues, no user impact

**Escalation Matrix**:
```yaml
P0 Incidents:
  - Initial Response: 5 minutes
  - Escalation to Manager: 15 minutes
  - Escalation to Senior Engineer: 30 minutes
  - Executive Notification: 1 hour (if not resolved)

P1 Incidents:
  - Initial Response: 15 minutes
  - Escalation to Senior Engineer: 1 hour
  - Manager Notification: 2 hours

P2 Incidents:
  - Initial Response: 2 hours
  - Assignment to Engineer: 4 hours
  - Senior Engineer Review: Next business day

P3 Incidents:
  - Initial Response: Next business day
  - Assignment to Engineer: 2 business days
```

### SOP 3: Backup and Recovery Testing

**Frequency**: Monthly  
**Duration**: 2 hours  
**Responsible**: Database Administrator

**Procedure**:
1. **Backup Verification** (30 minutes)
   - Verify all automated backups completed successfully
   - Test backup file integrity
   - Confirm backup encryption and compression
   - Validate backup size and timing metrics

2. **Recovery Testing** (60 minutes)
   - Restore test environment from latest backup
   - Verify data integrity and completeness
   - Test application functionality post-restore
   - Measure recovery time and document

3. **Disaster Recovery Simulation** (30 minutes)
   - Simulate various failure scenarios
   - Test failover procedures
   - Verify monitoring and alerting during recovery
   - Update disaster recovery documentation

## 📋 Emergency Procedures

### Emergency Contact Information
```yaml
Primary Contacts:
  - DevOps Lead: +1-xxx-xxx-xxxx (24/7)
  - Database Admin: +1-xxx-xxx-xxxx (business hours)
  - System Admin: +1-xxx-xxx-xxxx (on-call rotation)

Escalation Contacts:  
  - Engineering Manager: +1-xxx-xxx-xxxx
  - VP Engineering: +1-xxx-xxx-xxxx (P0 incidents only)

External Contacts:
  - AWS Support: Enterprise support case
  - Database Vendor: Priority support ticket
```

### Emergency Shutdown Procedure
```bash
#!/bin/bash
# Emergency system shutdown procedure

echo "🚨 EMERGENCY SHUTDOWN INITIATED"
echo "Time: $(date)"
echo "Initiated by: $USER"

# 1. Stop accepting new requests
echo "Stopping load balancer..."
docker-compose stop nginx

# 2. Allow existing requests to complete (30 seconds)
echo "Waiting for existing requests to complete..."
sleep 30

# 3. Stop application services
echo "Stopping application services..."
docker-compose stop backend celery-worker celery-beat

# 4. Stop databases (graceful shutdown)
echo "Stopping databases..."
docker-compose exec postgres pg_ctl stop -m fast
docker-compose stop redis

# 5. Create emergency backup
echo "Creating emergency backup..."
./scripts/backup.sh

# 6. Stop all remaining services
echo "Stopping all services..."
docker-compose down

echo "🚨 EMERGENCY SHUTDOWN COMPLETE"
echo "System down at: $(date)"
```

### Emergency Recovery Procedure
```bash
#!/bin/bash  
# Emergency recovery procedure

echo "🔄 EMERGENCY RECOVERY INITIATED"
echo "Time: $(date)"

# 1. Verify system resources
echo "Checking system resources..."
df -h
free -h
top -bn1 | head -20

# 2. Start databases first
echo "Starting databases..."
docker-compose up -d postgres redis
sleep 30

# 3. Verify database connectivity
echo "Testing database connectivity..."
docker-compose exec postgres pg_isready -U chrono_scraper
docker-compose exec redis redis-cli -a "$REDIS_PASSWORD" ping

# 4. Start application services
echo "Starting application services..."
docker-compose up -d backend celery-worker celery-beat

# 5. Start load balancer
echo "Starting load balancer..."
docker-compose up -d nginx

# 6. Run health checks
echo "Running health checks..."
sleep 60
./scripts/health_check.sh

echo "🔄 EMERGENCY RECOVERY COMPLETE"
echo "System recovered at: $(date)"
```

---

This comprehensive operations manual provides all the tools, procedures, and knowledge needed for successful day-to-day management of the Phase 2 DuckDB analytics system, ensuring high availability, performance, and reliability in production environments.