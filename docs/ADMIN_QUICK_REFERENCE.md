# Admin Quick Reference Guide

## Emergency Commands

### System Status Check
```bash
# Quick health verification
make status
curl http://localhost:8000/api/v1/health

# Service logs
docker compose logs -f backend
docker compose logs -f celery_worker
docker compose logs -f postgres

# Resource monitoring
make resource-stats
```

### Emergency Recovery
```bash
# Complete system restart
make down && make up

# Database recovery
docker compose exec postgres pg_restore --clean --create /backups/latest.dump

# Clear Redis cache
docker compose exec redis redis-cli FLUSHALL
```

## User Management Quick Actions

### Bulk User Operations
```sql
-- Approve all educational users
UPDATE users SET approval_status = 'approved', approval_date = NOW() 
WHERE email LIKE '%.edu' AND approval_status = 'pending';

-- Check pending users
SELECT email, research_interests, created_at FROM users 
WHERE approval_status = 'pending' ORDER BY created_at;

-- Deactivate inactive users (> 90 days)
UPDATE users SET is_active = FALSE 
WHERE last_login_at < NOW() - INTERVAL '90 days';
```

### Session Management
```bash
# View active sessions
docker compose exec redis redis-cli KEYS "session:*"

# Count sessions by user
docker compose exec redis redis-cli EVAL "
local sessions = redis.call('KEYS', 'session:*')
local users = {}
for i=1,#sessions do
    local user = redis.call('HGET', sessions[i], 'user_id')
    users[user] = (users[user] or 0) + 1
end
return users
" 0

# Revoke all sessions for user
docker compose exec redis redis-cli DEL session:USER_ID_HERE
```

## Content Management

### Content Quality Queries
```sql
-- High-quality content stats
SELECT 
    COUNT(*) as total,
    AVG(quality_score) as avg_quality,
    COUNT(*) FILTER (WHERE quality_score > 8) as high_quality
FROM pages WHERE created_at > NOW() - INTERVAL '7 days';

-- Entity extraction stats
SELECT 
    entity_type,
    COUNT(*) as count,
    AVG(confidence) as avg_confidence
FROM entities 
GROUP BY entity_type 
ORDER BY count DESC;
```

### Bulk Content Operations
```sql
-- Approve content from educational domains
UPDATE pages SET status = 'approved' 
WHERE url LIKE '%.edu%' AND status = 'pending';

-- Remove low-quality content
DELETE FROM pages 
WHERE quality_score < 3 AND created_at < NOW() - INTERVAL '30 days';
```

## Security Quick Actions

### Security Event Monitoring
```sql
-- Failed login attempts (last 24 hours)
SELECT 
    ip_address, 
    COUNT(*) as attempts,
    MAX(created_at) as last_attempt
FROM admin_audit_log 
WHERE action = 'login_failed' 
    AND created_at > NOW() - INTERVAL '24 hours'
GROUP BY ip_address 
HAVING COUNT(*) > 5
ORDER BY attempts DESC;

-- Suspicious geographic logins
SELECT DISTINCT 
    user_id,
    ip_address,
    created_at
FROM admin_audit_log 
WHERE action = 'login_success' 
    AND created_at > NOW() - INTERVAL '7 days'
ORDER BY user_id, created_at;
```

### IP Restriction Management
```bash
# Add IP to allowlist
echo "192.168.1.100" >> /etc/admin/allowed_ips.txt

# Block suspicious IP
iptables -A INPUT -s 192.168.1.200 -j DROP

# View current IP rules
iptables -L INPUT -n
```

## System Monitoring

### Performance Metrics
```bash
# Database performance
docker compose exec postgres psql -U chrono_scraper -d chrono_scraper -c "
SELECT 
    schemaname,
    tablename,
    n_tup_ins as inserts,
    n_tup_upd as updates,
    n_tup_del as deletes
FROM pg_stat_user_tables 
ORDER BY n_tup_ins + n_tup_upd + n_tup_del DESC LIMIT 10;
"

# Redis performance
docker compose exec redis redis-cli INFO stats | grep -E "(hits|misses|ops)"

# Celery queue status
docker compose exec backend celery -A app.tasks.celery_app inspect active
docker compose exec backend celery -A app.tasks.celery_app inspect reserved
```

### Alert Thresholds
| Metric | Warning | Critical |
|--------|---------|----------|
| CPU Usage | >70% | >90% |
| Memory Usage | >80% | >95% |
| Disk Space | <20% | <10% |
| Response Time | >2s | >5s |
| Error Rate | >2% | >5% |

## Backup and Recovery

### Quick Backup Commands
```bash
# Database backup
docker compose exec postgres pg_dump -U chrono_scraper chrono_scraper > backup_$(date +%Y%m%d).sql

# Configuration backup
docker compose exec backend python -c "
from app.models.admin_settings import AdminSetting
import json
settings = AdminSetting.get_all()
with open('config_backup.json', 'w') as f:
    json.dump(settings, f, indent=2)
"

# Redis backup
docker compose exec redis redis-cli SAVE
cp /var/lib/redis/dump.rdb redis_backup_$(date +%Y%m%d).rdb
```

### Recovery Procedures
```bash
# Database restore
docker compose exec -T postgres psql -U chrono_scraper chrono_scraper < backup_20240824.sql

# Configuration restore
docker compose exec backend python -c "
from app.models.admin_settings import AdminSetting
import json
with open('config_backup.json', 'r') as f:
    settings = json.load(f)
AdminSetting.restore_settings(settings)
"
```

## Common Troubleshooting

### Service Won't Start
1. Check logs: `docker compose logs service_name`
2. Verify dependencies: `make status`
3. Check disk space: `df -h`
4. Verify network: `docker network ls`
5. Restart clean: `make down && make up`

### Database Connection Issues
1. Check PostgreSQL status: `docker compose ps postgres`
2. Test connection: `docker compose exec postgres psql -U chrono_scraper -d chrono_scraper -c "SELECT 1;"`
3. Check logs: `docker compose logs postgres`
4. Verify credentials in `.env`

### Redis Connection Issues
1. Test Redis: `docker compose exec redis redis-cli ping`
2. Check memory: `docker compose exec redis redis-cli INFO memory`
3. Clear if needed: `docker compose exec redis redis-cli FLUSHALL`

### High CPU/Memory Usage
1. Check processes: `docker stats`
2. Identify culprit: `make resource-stats`
3. Review slow queries: `docker compose logs postgres | grep "slow query"`
4. Scale if needed: Increase resource limits in docker-compose.yml

## URL Reference

### Admin Panel URLs
- Main Dashboard: `http://localhost:8000/admin`
- User Management: `http://localhost:8000/admin/users`
- Content Management: `http://localhost:8000/admin/pages`
- System Monitoring: `http://localhost:8000/admin/monitoring`
- Settings: `http://localhost:8000/admin/settings`

### Development URLs
- API Health: `http://localhost:8000/api/v1/health`
- API Docs: `http://localhost:8000/docs`
- Mailpit: `http://localhost:8025`
- Flower (Celery): `http://localhost:5555`
- Meilisearch: `http://localhost:7700`

---

**Quick Tip**: Bookmark this page for instant access to common admin commands and procedures during daily operations.