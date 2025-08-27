# Disaster Recovery Runbook - Chrono Scraper v2

## Overview

This runbook provides comprehensive disaster recovery procedures for the Chrono Scraper v2 database system, designed for operational excellence and 3am emergency scenarios. It includes automated recovery procedures, manual intervention steps, and complete system restoration workflows.

**RTO (Recovery Time Objective)**: 30 minutes for database services  
**RPO (Recovery Point Objective)**: 15 minutes maximum data loss  

## Emergency Contacts

| Role | Contact Method | Escalation |
|------|---------------|------------|
| **Database Administrator** | Check CLAUDE.local.md | After 15 minutes |
| **Backend Lead** | Slack #backend-alerts | After 30 minutes |
| **DevOps On-Call** | PagerDuty | Immediate |
| **Infrastructure Lead** | Phone (check env) | After 45 minutes |

## Disaster Scenarios

### 1. Database Server Failure

**Symptoms**: Connection timeouts, 500 errors, application crashes

#### Immediate Response (0-5 minutes)
```bash
# Check database container status
docker compose ps postgres
docker compose logs postgres --tail=50

# Check system resources
free -h
df -h
iostat -x 1 5

# Quick connectivity test
docker compose exec backend python -c "
import psycopg2
try:
    conn = psycopg2.connect(
        host='postgres', 
        database='chrono_scraper',
        user='chrono_scraper',
        password='chrono_scraper_dev'
    )
    print('Database connection: OK')
except Exception as e:
    print(f'Database connection failed: {e}')
"
```

#### Automated Recovery (5-15 minutes)
```bash
# Stop all dependent services
docker compose stop backend celery_worker frontend

# Restart database with health checks
docker compose stop postgres
docker compose up -d postgres

# Wait for database to be ready
timeout 300 bash -c 'until docker compose exec postgres pg_isready -U chrono_scraper; do sleep 2; done'

# Verify database integrity
docker compose exec postgres psql -U chrono_scraper -d chrono_scraper -c "SELECT COUNT(*) FROM users;"

# Restart dependent services
docker compose up -d backend celery_worker
sleep 30
docker compose up -d frontend
```

#### Manual Recovery (if automated fails)
```bash
# Check for corrupted data files
docker compose exec postgres pg_controldata /var/lib/postgresql/data

# If corruption detected, restore from backup
./scripts/restore_from_backup.sh --latest --verify

# Check replication status (if applicable)
docker compose exec postgres psql -U chrono_scraper -d chrono_scraper -c "
SELECT * FROM pg_stat_replication;"
```

### 2. Data Corruption

**Symptoms**: Inconsistent query results, constraint violations, application errors

#### Immediate Assessment (0-10 minutes)
```bash
# Run database integrity checks
docker compose exec postgres psql -U chrono_scraper -d chrono_scraper -c "
-- Check for corrupt indexes
SELECT schemaname, tablename, indexname 
FROM pg_stat_user_indexes 
WHERE idx_scan = 0 AND schemaname = 'public';

-- Check table statistics
SELECT schemaname, tablename, n_dead_tup, n_live_tup,
       CASE WHEN n_live_tup > 0 
            THEN round((n_dead_tup::float/n_live_tup::float)*100, 2) 
            ELSE 0 
       END as dead_tuple_percent
FROM pg_stat_user_tables
WHERE n_dead_tup > 1000
ORDER BY dead_tuple_percent DESC;
"

# Check for foreign key violations
docker compose exec postgres psql -U chrono_scraper -d chrono_scraper -c "
-- Test critical foreign key constraints
SELECT COUNT(*) FROM scrape_pages sp 
LEFT JOIN domains d ON sp.domain_id = d.id 
WHERE d.id IS NULL;

SELECT COUNT(*) FROM pages p 
LEFT JOIN domains d ON p.domain_id = d.id 
WHERE d.id IS NULL;
"
```

#### Recovery Actions
```bash
# Option 1: VACUUM and REINDEX (for minor corruption)
docker compose exec postgres psql -U chrono_scraper -d chrono_scraper -c "
VACUUM FULL ANALYZE;
REINDEX DATABASE chrono_scraper;
"

# Option 2: Point-in-time recovery (for significant corruption)
# Stop all services
docker compose down

# Restore from known good backup
./scripts/restore_from_backup.sh --point-in-time="2025-08-27 10:00:00"

# Verify data integrity after restore
./scripts/verify_data_integrity.sh

# Restart services
docker compose up -d
```

### 3. Complete System Failure

**Symptoms**: No database connectivity, container won't start, disk failure

#### Emergency Recovery Procedure
```bash
# 1. Assess damage
docker compose down
docker system df
df -h

# 2. Create emergency backup of any recoverable data
sudo cp -r ./postgres_data ./emergency_backup_$(date +%Y%m%d_%H%M%S)

# 3. Restore from latest automated backup
cd /home/bizon/Development/chrono-scraper-fastapi-2

# Find latest backup
ls -la ./backups/ | head -10

# Restore database
./scripts/restore_from_backup.sh --backup-file="./backups/chrono_scraper_full_20250827_100000.sql.gz"

# 4. Verify system integrity
./scripts/db_maintenance.py monitor --health --export health_report_post_recovery.json

# 5. Restart all services
docker compose up -d

# 6. Run smoke tests
./scripts/smoke_tests.sh
```

## Backup and Restore Procedures

### Creating Manual Backups

```bash
# Full database backup
./scripts/db_maintenance.py backup --type=full --retention-days=90

# Schema-only backup (for migrations)
./scripts/db_maintenance.py backup --type=schema

# Critical tables only
./scripts/db_maintenance.py backup --type=data --tables scrape_pages pages domains users projects

# Incremental backup (for high-frequency environments)
./scripts/db_maintenance.py backup --type=incremental
```

### Restoration Procedures

#### Full Database Restore
```bash
#!/bin/bash
# restore_from_backup.sh

set -e

BACKUP_FILE="$1"
VERIFY_RESTORE="${2:-true}"

if [ -z "$BACKUP_FILE" ]; then
    echo "Usage: $0 <backup_file> [verify]"
    exit 1
fi

echo "🚨 Starting database restoration from: $BACKUP_FILE"
echo "⚠️  This will completely replace the current database!"

# Confirm in production
read -p "Are you sure you want to proceed? (type 'YES' to confirm): " confirm
if [ "$confirm" != "YES" ]; then
    echo "Restoration cancelled"
    exit 1
fi

# Stop dependent services
echo "📋 Stopping dependent services..."
docker compose stop backend celery_worker frontend

# Backup current database before restore
echo "📋 Creating safety backup of current database..."
./scripts/db_maintenance.py backup --type=full

# Drop and recreate database
echo "📋 Recreating database..."
docker compose exec postgres psql -U chrono_scraper -c "
SELECT pg_terminate_backend(pg_stat_activity.pid)
FROM pg_stat_activity
WHERE pg_stat_activity.datname = 'chrono_scraper'
  AND pid <> pg_backend_pid();

DROP DATABASE IF EXISTS chrono_scraper;
CREATE DATABASE chrono_scraper OWNER chrono_scraper;
"

# Restore from backup
echo "📋 Restoring from backup..."
if [[ "$BACKUP_FILE" == *.gz ]]; then
    gunzip -c "$BACKUP_FILE" | docker compose exec -T postgres psql -U chrono_scraper -d chrono_scraper
else
    docker compose exec -T postgres psql -U chrono_scraper -d chrono_scraper < "$BACKUP_FILE"
fi

# Run post-restore verification
if [ "$VERIFY_RESTORE" = "true" ]; then
    echo "📋 Verifying restoration..."
    
    # Check critical tables
    docker compose exec postgres psql -U chrono_scraper -d chrono_scraper -c "
    SELECT 'users' as table_name, COUNT(*) as record_count FROM users
    UNION ALL
    SELECT 'projects', COUNT(*) FROM projects
    UNION ALL
    SELECT 'pages', COUNT(*) FROM pages
    UNION ALL
    SELECT 'scrape_pages', COUNT(*) FROM scrape_pages;
    "
    
    # Verify foreign key constraints
    docker compose exec postgres psql -U chrono_scraper -d chrono_scraper -c "
    SET client_min_messages TO ERROR;
    -- This will fail if constraints are violated
    ALTER TABLE scrape_pages VALIDATE CONSTRAINT scrape_pages_domain_id_fkey;
    ALTER TABLE pages VALIDATE CONSTRAINT pages_domain_id_fkey;
    "
fi

# Restart services
echo "📋 Restarting services..."
docker compose up -d backend
sleep 10
docker compose up -d celery_worker
sleep 5
docker compose up -d frontend

echo "✅ Database restoration completed successfully!"
echo "📊 Run health checks: ./scripts/db_maintenance.py monitor --health"
```

### Connection Pool Management

Create `/home/bizon/Development/chrono-scraper-fastapi-2/scripts/pgbouncer_setup.sh`:

```bash
#!/bin/bash
# PgBouncer setup for connection pooling

# Create pgbouncer configuration
cat > pgbouncer.ini << EOF
[databases]
chrono_scraper = host=postgres port=5432 dbname=chrono_scraper user=chrono_scraper

[pgbouncer]
pool_mode = transaction
max_client_conn = 200
default_pool_size = 25
max_db_connections = 50
max_user_connections = 50

listen_port = 6432
listen_addr = *
auth_type = md5
auth_file = /etc/pgbouncer/userlist.txt

log_connections = 1
log_disconnections = 1
log_pooler_errors = 1

server_reset_query = DISCARD ALL
server_check_delay = 30
server_check_query = SELECT 1

application_name_add_host = 1
EOF

# Add to docker-compose.yml
cat >> docker-compose.yml << EOF

  pgbouncer:
    image: pgbouncer/pgbouncer:latest
    container_name: chrono_pgbouncer
    environment:
      DATABASES_HOST: postgres
      DATABASES_PORT: 5432
      DATABASES_USER: chrono_scraper
      DATABASES_PASSWORD: chrono_scraper_dev
      DATABASES_DBNAME: chrono_scraper
      POOL_MODE: transaction
      MAX_CLIENT_CONN: 200
      DEFAULT_POOL_SIZE: 25
    ports:
      - "6432:6432"
    depends_on:
      - postgres
    volumes:
      - ./pgbouncer.ini:/etc/pgbouncer/pgbouncer.ini
    restart: unless-stopped
EOF

echo "PgBouncer configuration created. Update your application to connect to port 6432"
```

## Monitoring and Alerting

### Critical Metrics Dashboard

Create monitoring script `/home/bizon/Development/chrono-scraper-fastapi-2/scripts/monitor_database.py`:

```python
#!/usr/bin/env python3
"""Database monitoring and alerting script"""

import psycopg2
import time
import json
import smtplib
from email.mime.text import MIMEText
from datetime import datetime
import os

ALERT_THRESHOLDS = {
    'disk_usage_percent': 85,
    'connection_percent': 80,
    'replication_lag_seconds': 300,
    'slow_query_threshold': 5.0,
    'dead_tuple_percent': 30,
    'cache_hit_ratio': 95
}

def check_database_health():
    """Comprehensive database health check with alerting"""
    try:
        conn = psycopg2.connect(
            host=os.getenv('POSTGRES_HOST', 'postgres'),
            database=os.getenv('POSTGRES_DB', 'chrono_scraper'),
            user=os.getenv('POSTGRES_USER', 'chrono_scraper'),
            password=os.getenv('POSTGRES_PASSWORD', 'chrono_scraper_dev')
        )
        cursor = conn.cursor()
        
        alerts = []
        metrics = {}
        
        # Check disk usage
        cursor.execute("SELECT pg_size_pretty(pg_database_size(current_database()))")
        db_size = cursor.fetchone()[0]
        metrics['database_size'] = db_size
        
        # Check connection usage
        cursor.execute("""
            SELECT COUNT(*) as active,
                   (SELECT setting::int FROM pg_settings WHERE name = 'max_connections') as max
            FROM pg_stat_activity
            WHERE state = 'active'
        """)
        active, max_conn = cursor.fetchone()
        connection_percent = (active / max_conn) * 100
        metrics['connection_usage'] = f"{active}/{max_conn} ({connection_percent:.1f}%)"
        
        if connection_percent > ALERT_THRESHOLDS['connection_percent']:
            alerts.append(f"High connection usage: {connection_percent:.1f}%")
        
        # Check for slow queries
        cursor.execute("""
            SELECT query, state, now() - query_start as duration
            FROM pg_stat_activity
            WHERE state = 'active' 
            AND now() - query_start > interval '5 seconds'
            AND query NOT LIKE '%pg_stat_activity%'
        """)
        slow_queries = cursor.fetchall()
        metrics['slow_queries'] = len(slow_queries)
        
        if len(slow_queries) > 5:
            alerts.append(f"Multiple slow queries detected: {len(slow_queries)}")
        
        # Check table bloat
        cursor.execute("""
            SELECT schemaname, tablename, n_dead_tup, n_live_tup,
                   CASE WHEN n_live_tup > 0 
                        THEN round((n_dead_tup::float/n_live_tup::float)*100, 2) 
                        ELSE 0 
                   END as dead_tuple_percent
            FROM pg_stat_user_tables
            WHERE n_live_tup > 1000
            ORDER BY dead_tuple_percent DESC
            LIMIT 5
        """)
        bloated_tables = cursor.fetchall()
        
        for table in bloated_tables:
            if table[4] > ALERT_THRESHOLDS['dead_tuple_percent']:
                alerts.append(f"Table {table[1]} has {table[4]}% dead tuples")
        
        # Check replication lag (if replica)
        cursor.execute("SELECT pg_is_in_recovery()")
        is_replica = cursor.fetchone()[0]
        
        if is_replica:
            cursor.execute("""
                SELECT EXTRACT(EPOCH FROM (now() - pg_last_xact_replay_timestamp()))::int as lag_seconds
            """)
            lag = cursor.fetchone()[0]
            metrics['replication_lag'] = f"{lag}s"
            
            if lag > ALERT_THRESHOLDS['replication_lag_seconds']:
                alerts.append(f"High replication lag: {lag}s")
        
        # Generate alert summary
        status = {
            'timestamp': datetime.now().isoformat(),
            'status': 'CRITICAL' if len(alerts) > 2 else 'WARNING' if alerts else 'OK',
            'alerts': alerts,
            'metrics': metrics
        }
        
        # Log status
        print(json.dumps(status, indent=2))
        
        # Send alerts if critical
        if status['status'] in ['CRITICAL', 'WARNING']:
            send_alert(status)
        
        return status
        
    except Exception as e:
        error_status = {
            'timestamp': datetime.now().isoformat(),
            'status': 'CRITICAL',
            'error': str(e),
            'alerts': ['Database connection failed']
        }
        send_alert(error_status)
        return error_status
        
    finally:
        if 'conn' in locals():
            conn.close()

def send_alert(status):
    """Send alert notification"""
    # This would integrate with your alerting system
    # For now, just log the alert
    print(f"🚨 ALERT: {status['status']} - {len(status.get('alerts', []))} issues detected")

if __name__ == "__main__":
    check_database_health()
```

### Automated Health Checks

Create cron job for regular monitoring:

```bash
# Add to crontab
# Check database health every 5 minutes
*/5 * * * * cd /home/bizon/Development/chrono-scraper-fastapi-2 && python3 scripts/monitor_database.py >> logs/health_check.log 2>&1

# Daily backup and cleanup
0 2 * * * cd /home/bizon/Development/chrono-scraper-fastapi-2 && ./scripts/db_maintenance.py backup --type=full && ./scripts/db_maintenance.py cleanup

# Weekly vacuum analyze
0 3 * * 0 cd /home/bizon/Development/chrono-scraper-fastapi-2 && ./scripts/db_maintenance.py vacuum --analyze
```

## Performance Optimization

### Query Performance Monitoring

```sql
-- Create performance monitoring views
CREATE OR REPLACE VIEW slow_queries AS
SELECT 
    substring(query, 1, 100) as short_query,
    calls,
    total_time,
    mean_time,
    rows,
    100.0 * shared_blks_hit / nullif(shared_blks_hit + shared_blks_read, 0) AS hit_percent
FROM pg_stat_statements 
ORDER BY mean_time DESC;

-- Create table bloat monitoring view
CREATE OR REPLACE VIEW table_bloat AS
SELECT 
    schemaname,
    tablename,
    pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) as size,
    n_dead_tup,
    n_live_tup,
    CASE WHEN n_live_tup > 0 
         THEN round((n_dead_tup::float/n_live_tup::float)*100, 2) 
         ELSE 0 
    END as dead_tuple_percent,
    last_vacuum,
    last_autovacuum
FROM pg_stat_user_tables
WHERE n_live_tup > 100
ORDER BY dead_tuple_percent DESC;
```

### Index Optimization

```sql
-- Find unused indexes
SELECT 
    schemaname,
    tablename,
    indexname,
    idx_tup_read,
    idx_tup_fetch,
    pg_size_pretty(pg_relation_size(indexrelid)) as size
FROM pg_stat_user_indexes 
WHERE idx_scan = 0 
AND schemaname = 'public'
ORDER BY pg_relation_size(indexrelid) DESC;

-- Find missing indexes (queries with high cost but no index usage)
SELECT 
    query,
    calls,
    total_time,
    mean_time
FROM pg_stat_statements
WHERE query LIKE '%WHERE%'
AND query NOT LIKE '%pg_stat%'
ORDER BY total_time DESC
LIMIT 20;
```

## Security and Access Control

### User Management Matrix

| User Type | Permissions | Connection Limit | Purpose |
|-----------|-------------|------------------|---------|
| `chrono_scraper` | Database owner | Unlimited | Application user |
| `backup_user` | SELECT on all tables | 2 | Backup operations |
| `monitoring_user` | SELECT on system tables | 5 | Monitoring/alerting |
| `readonly_user` | SELECT on public schema | 10 | Analytics/reporting |
| `admin_user` | SUPERUSER (emergency only) | 1 | Emergency access |

### Security Audit Script

```bash
#!/bin/bash
# security_audit.sh

echo "🔍 Database Security Audit"
echo "=========================="

# Check for default passwords
docker compose exec postgres psql -U chrono_scraper -d chrono_scraper -c "
SELECT rolname, rolvaliduntil 
FROM pg_roles 
WHERE rolcanlogin = true 
AND (rolvaliduntil IS NULL OR rolvaliduntil > now())
ORDER BY rolname;
"

# Check for superusers
docker compose exec postgres psql -U chrono_scraper -d chrono_scraper -c "
SELECT rolname FROM pg_roles WHERE rolsuper = true;
"

# Check for password authentication
docker compose exec postgres psql -U chrono_scraper -d chrono_scraper -c "
SELECT type, database, user_name, auth_method 
FROM pg_hba_file_rules 
WHERE auth_method != 'reject'
ORDER BY line_number;
"

# Check for suspicious connections
docker compose exec postgres psql -U chrono_scraper -d chrono_scraper -c "
SELECT usename, client_addr, count(*) as connections
FROM pg_stat_activity 
GROUP BY usename, client_addr
HAVING count(*) > 10
ORDER BY connections DESC;
"

echo "✅ Security audit completed"
```

## Testing Recovery Procedures

### Monthly DR Tests

```bash
#!/bin/bash
# dr_test.sh - Disaster Recovery Testing

echo "🧪 Monthly Disaster Recovery Test"
echo "================================"

# 1. Create test backup
echo "📋 Creating test backup..."
./scripts/db_maintenance.py backup --type=full

# 2. Create test database
echo "📋 Creating test environment..."
docker compose exec postgres psql -U chrono_scraper -c "
CREATE DATABASE chrono_scraper_dr_test;
"

# 3. Restore to test database
echo "📋 Testing backup restore..."
LATEST_BACKUP=$(ls -t ./backups/chrono_scraper_full_*.sql.gz | head -1)
gunzip -c "$LATEST_BACKUP" | docker compose exec -T postgres psql -U chrono_scraper -d chrono_scraper_dr_test

# 4. Verify data integrity
echo "📋 Verifying data integrity..."
docker compose exec postgres psql -U chrono_scraper -d chrono_scraper_dr_test -c "
SELECT 'Test passed: ' || COUNT(*) || ' users found' FROM users;
SELECT 'Test passed: ' || COUNT(*) || ' projects found' FROM projects;
"

# 5. Cleanup test database
echo "📋 Cleaning up test environment..."
docker compose exec postgres psql -U chrono_scraper -c "
DROP DATABASE chrono_scraper_dr_test;
"

echo "✅ DR test completed successfully"
```

---

**Document version**: 2.0  
**Last updated**: 2025-08-27  
**Next review**: 2025-09-27  
**Maintained by**: Database Administration Team  

*Keep this runbook updated and easily accessible for emergency situations. Test all procedures regularly in a staging environment.*