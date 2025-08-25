# Admin Troubleshooting Guide

## Quick Diagnosis Framework

### Step 1: Immediate Assessment (2-3 minutes)
1. **Scope of Impact**: Who/what is affected?
2. **Severity Level**: Critical, High, Medium, or Low?
3. **Recent Changes**: Any deployments, config changes, or updates?
4. **Error Messages**: Specific error messages or codes?
5. **Reproducibility**: Can the issue be reproduced consistently?

### Step 2: System Health Check (5 minutes)
```bash
# Quick system status
make status
curl -I http://localhost:8000/api/v1/health

# Resource utilization
make resource-stats

# Service logs (last 100 lines)
docker compose logs --tail=100 backend postgres redis
```

### Step 3: Service-Specific Diagnostics

## Common Issues and Solutions

### 1. Admin Panel Access Issues

#### Symptom: "Admin panel won't load" / 500 error
**Quick Diagnosis**:
```bash
# Check backend service
docker compose logs backend --tail=50

# Verify admin routes are loaded
docker compose exec backend python -c "from app.main import app; print([r.path for r in app.routes if 'admin' in r.path])"
```

**Common Causes & Solutions**:

**A. SQLAdmin not properly initialized**
```python
# Check admin configuration
docker compose exec backend python -c "
from app.admin.config import admin
print(f'Admin configured: {admin is not None}')
print(f'Views registered: {len(admin._views) if admin else 0}')
"
```
*Solution*: Restart backend service, verify admin views are registered

**B. Database connection issues**  
```bash
# Test database connection
docker compose exec backend python -c "
import asyncio
from app.core.database import get_db
async def test_db():
    async for db in get_db():
        result = await db.execute('SELECT 1')
        print(f'DB Connection: OK')
        break
asyncio.run(test_db())
"
```
*Solution*: Check postgres service, verify connection settings

**C. Session/Redis issues**
```bash
# Test Redis connection
docker compose exec backend python -c "
import redis
r = redis.Redis(host='redis', port=6379)
print(f'Redis ping: {r.ping()}')
"
```
*Solution*: Restart Redis service, clear corrupted sessions

#### Symptom: "Access Denied" / 403 error
**Diagnosis**:
```bash
# Check user superuser status
docker compose exec postgres psql -U chrono_scraper -d chrono_scraper -c "
SELECT email, is_superuser, is_active FROM users WHERE email = 'YOUR_ADMIN_EMAIL';
"
```

**Solutions**:
- Verify user has `is_superuser=true`
- Ensure user account is active
- Clear browser cookies/cache
- Check IP restrictions if configured

#### Symptom: Login redirect loop
**Diagnosis**:
```bash
# Check session configuration
docker compose exec backend python -c "
from app.core.config import settings
print(f'SECRET_KEY exists: {bool(settings.SECRET_KEY)}')
print(f'Session timeout: {settings.SESSION_TIMEOUT_MINUTES}')
"
```

**Solutions**:
- Verify SECRET_KEY in environment
- Clear Redis session data
- Check browser cookie settings
- Restart backend service

### 2. User Management Issues

#### Symptom: "Bulk user operations failing"
**Diagnosis**:
```bash
# Check for database locks
docker compose exec postgres psql -U chrono_scraper -d chrono_scraper -c "
SELECT pid, state, query, query_start FROM pg_stat_activity 
WHERE state != 'idle' AND query LIKE '%users%';
"
```

**Solutions**:
- Reduce batch size (max 50 users at once)
- Check for concurrent operations
- Verify database transaction limits
- Monitor memory usage during operations

#### Symptom: "User approval emails not sending"
**Diagnosis**:
```bash
# Check email configuration
docker compose exec backend python -c "
from app.core.config import settings
print(f'Email backend: {settings.EMAIL_BACKEND}')
print(f'SMTP configured: {bool(settings.SMTP_HOST)}')
print(f'Mailgun configured: {bool(settings.MAILGUN_API_KEY)}')
"

# Check Mailpit (development)
curl -I http://localhost:8025/api/v1/messages
```

**Solutions**:
- Verify email service configuration
- Check Mailpit for captured emails (development)
- Test email connectivity to external providers
- Review email template syntax

### 3. Content Management Issues

#### Symptom: "Content search not working"
**Diagnosis**:
```bash
# Check Meilisearch status
curl http://localhost:7700/health

# Check index status
curl http://localhost:7700/indexes

# Verify index contents
curl "http://localhost:7700/indexes/pages/search?q=test"
```

**Solutions**:
- Restart Meilisearch service
- Rebuild search indexes
- Check index synchronization
- Verify content indexing pipeline

#### Symptom: "Content quality scoring inconsistent"
**Diagnosis**:
```bash
# Check scoring algorithm
docker compose exec backend python -c "
from app.services.content_scoring import ContentScorer
scorer = ContentScorer()
print(f'Scoring rules loaded: {len(scorer.rules)}')
"
```

**Solutions**:
- Review scoring rule configuration
- Update content quality thresholds
- Recalculate scores for affected content
- Check for algorithm updates

### 4. System Performance Issues

#### Symptom: "Slow admin panel response"
**Diagnosis**:
```bash
# Check database performance
docker compose exec postgres psql -U chrono_scraper -d chrono_scraper -c "
SELECT query, calls, total_time, mean_time 
FROM pg_stat_statements 
ORDER BY total_time DESC 
LIMIT 10;
"

# Check Redis performance
docker compose exec redis redis-cli info stats | grep -E "(ops|hits|misses)"

# Monitor resource usage
docker stats --no-stream
```

**Common Performance Issues**:

**A. Database Query Performance**
```sql
-- Find slow queries
SELECT query, calls, total_time, mean_time, rows
FROM pg_stat_statements
WHERE mean_time > 1000  -- More than 1 second
ORDER BY mean_time DESC;

-- Check for missing indexes
SELECT schemaname, tablename, attname, n_distinct, correlation
FROM pg_stats
WHERE schemaname = 'public' AND n_distinct > 100;
```

**B. Memory Issues**
```bash
# Check container memory usage
docker stats --format "table {{.Container}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.MemPerc}}"

# Check for memory leaks
docker compose exec backend python -c "
import psutil
p = psutil.Process()
print(f'Memory: {p.memory_info().rss / 1024 / 1024:.2f} MB')
print(f'Open files: {len(p.open_files())}')
"
```

**Solutions**:
- Add database indexes for frequently queried columns
- Implement query result caching
- Increase memory limits if needed
- Optimize large data operations

### 5. Security and Session Issues

#### Symptom: "Users getting logged out frequently"
**Diagnosis**:
```bash
# Check session configuration
docker compose exec backend python -c "
from app.core.config import settings
print(f'Session timeout: {settings.SESSION_TIMEOUT_MINUTES} minutes')
"

# Check Redis memory and eviction
docker compose exec redis redis-cli info memory | grep -E "(used_memory|maxmemory|evicted_keys)"
```

**Solutions**:
- Increase session timeout if appropriate
- Check Redis memory configuration
- Monitor session creation/destruction patterns
- Review Redis eviction policies

#### Symptom: "Security alerts not triggering"
**Diagnosis**:
```bash
# Check audit logging
docker compose exec postgres psql -U chrono_scraper -d chrono_scraper -c "
SELECT COUNT(*) as total_events, 
       COUNT(*) FILTER (WHERE action LIKE '%login%') as login_events,
       MAX(created_at) as last_event
FROM admin_audit_log
WHERE created_at > NOW() - INTERVAL '24 hours';
"

# Verify alert configuration
docker compose exec backend python -c "
from app.admin.services.security_monitor import SecurityMonitor
monitor = SecurityMonitor()
print(f'Alert rules loaded: {len(monitor.rules)}')
"
```

**Solutions**:
- Verify audit logging is working
- Check alert rule configuration
- Test alert delivery mechanisms
- Review event threshold settings

### 6. Backup and Recovery Issues

#### Symptom: "Backup creation failing"
**Diagnosis**:
```bash
# Check backup script permissions
ls -la /app/scripts/backup_*.sh

# Test manual backup
docker compose exec postgres pg_dump -U chrono_scraper chrono_scraper --verbose

# Check disk space
df -h
docker system df
```

**Solutions**:
- Verify script permissions and paths
- Check available disk space
- Test database connectivity
- Review backup storage configuration

#### Symptom: "Restore process fails"
**Diagnosis**:
```bash
# Verify backup file integrity
docker compose exec postgres pg_restore --list backup_file.dump | head -20

# Check for schema conflicts
docker compose exec postgres psql -U chrono_scraper -d chrono_scraper -c "\dt"
```

**Solutions**:
- Validate backup file integrity
- Resolve schema version conflicts
- Use appropriate restore options
- Test restore in isolated environment first

## Escalation Procedures

### Level 1: Self-Resolution (15-30 minutes)
- Follow this troubleshooting guide
- Check recent documentation updates
- Review system logs for obvious issues
- Try standard restart procedures

### Level 2: Team Support (30 minutes - 2 hours)
- **Contact**: Senior administrator or team lead
- **Information to provide**:
  - Exact error messages and screenshots
  - Steps already taken
  - System logs and diagnostic output
  - Business impact assessment

### Level 3: Technical Support (2-24 hours)
- **Contact**: Technical support team
- **Preparation required**:
  - Complete system diagnostic report
  - Database and configuration backups
  - Detailed timeline of events
  - Impact on users and operations

### Level 4: Emergency Response (Immediate)
- **Triggers**: Complete system failure, security breach, data loss
- **Actions**:
  - Activate incident response team
  - Implement emergency procedures
  - Notify all stakeholders
  - Begin disaster recovery if needed

## Diagnostic Data Collection

### System Information Script
```bash
#!/bin/bash
# save as: collect_diagnostic_info.sh

echo "=== Chrono Scraper Diagnostic Report ===" > diagnostic_report.txt
echo "Generated: $(date)" >> diagnostic_report.txt
echo "" >> diagnostic_report.txt

echo "=== Service Status ===" >> diagnostic_report.txt
docker compose ps >> diagnostic_report.txt
echo "" >> diagnostic_report.txt

echo "=== System Resources ===" >> diagnostic_report.txt
docker stats --no-stream >> diagnostic_report.txt
echo "" >> diagnostic_report.txt

echo "=== Recent Logs ===" >> diagnostic_report.txt
docker compose logs --tail=50 backend >> diagnostic_report.txt
docker compose logs --tail=50 postgres >> diagnostic_report.txt
docker compose logs --tail=50 redis >> diagnostic_report.txt

echo "=== Database Status ===" >> diagnostic_report.txt
docker compose exec postgres psql -U chrono_scraper -d chrono_scraper -c "
SELECT version();
SELECT pg_size_pretty(pg_database_size('chrono_scraper')) as db_size;
SELECT count(*) as total_users FROM users;
SELECT count(*) as active_sessions FROM admin_audit_log WHERE action = 'login_success' AND created_at > NOW() - INTERVAL '1 hour';
" >> diagnostic_report.txt

echo "Diagnostic report saved to: diagnostic_report.txt"
```

### Log Analysis Commands
```bash
# Find errors in last 1000 lines
docker compose logs --tail=1000 | grep -i error

# Find specific user issues
docker compose logs | grep "user_id:USER_ID" | tail -20

# Monitor real-time issues
docker compose logs -f | grep -E "(error|failed|exception)"

# Database connection issues
docker compose logs postgres | grep -E "(connection|authentication|error)"

# Performance issues
docker compose logs backend | grep -E "(slow|timeout|performance)"
```

## Prevention and Monitoring

### Proactive Monitoring Setup
```bash
# Create monitoring script: monitor_health.sh
#!/bin/bash

# Check all critical services
services=("backend" "postgres" "redis" "meilisearch")
for service in "${services[@]}"; do
    if ! docker compose ps $service | grep -q "Up"; then
        echo "ALERT: $service is not running"
        # Add notification logic here
    fi
done

# Check resource usage
memory_usage=$(docker stats --no-stream --format "{{.MemPerc}}" backend | sed 's/%//')
if (( $(echo "$memory_usage > 90" | bc -l) )); then
    echo "ALERT: Backend memory usage is ${memory_usage}%"
fi

# Check database connections
connections=$(docker compose exec postgres psql -U chrono_scraper -d chrono_scraper -t -c "SELECT count(*) FROM pg_stat_activity;")
if [ $connections -gt 50 ]; then
    echo "ALERT: High database connection count: $connections"
fi
```

### Regular Maintenance Tasks
```bash
# Weekly maintenance script: weekly_maintenance.sh
#!/bin/bash

echo "Starting weekly maintenance..."

# Clean old audit logs (keep 90 days)
docker compose exec postgres psql -U chrono_scraper -d chrono_scraper -c "
DELETE FROM admin_audit_log WHERE created_at < NOW() - INTERVAL '90 days';
"

# Analyze database performance
docker compose exec postgres psql -U chrono_scraper -d chrono_scraper -c "ANALYZE;"

# Clean old Redis sessions
docker compose exec redis redis-cli EVAL "
local keys = redis.call('KEYS', 'session:*')
local expired = 0
for i=1,#keys do
    local ttl = redis.call('TTL', keys[i])
    if ttl == -1 then
        redis.call('DEL', keys[i])
        expired = expired + 1
    end
end
return expired
" 0

# Check backup integrity
if [ -f "/backups/latest.dump" ]; then
    docker compose exec postgres pg_restore --list /backups/latest.dump > /dev/null
    if [ $? -eq 0 ]; then
        echo "Backup integrity: OK"
    else
        echo "ALERT: Backup integrity check failed"
    fi
fi

echo "Weekly maintenance completed"
```

---

**Remember**: Always test solutions in a development environment first when possible, and maintain detailed logs of all troubleshooting actions for future reference and continuous improvement.