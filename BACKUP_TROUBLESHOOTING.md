# Backup System Troubleshooting Quick Reference

## Emergency Procedures

### 🚨 Backup System Down
```bash
# 1. Check system health
curl -H "Authorization: Bearer TOKEN" http://localhost:8000/api/v1/backup/health

# 2. Check container logs
docker compose logs backend | grep -i backup | tail -20

# 3. Restart backup-related services
docker compose restart backend celery_worker celery_beat

# 4. Validate environment
docker compose exec backend python app/scripts/validate_backup_environment.py
```

### 🚨 Critical Data Recovery
```bash
# 1. List available backups
curl -H "Authorization: Bearer TOKEN" \
     "http://localhost:8000/api/v1/backup/list?storage_backend=local"

# 2. Start emergency recovery
curl -X POST -H "Authorization: Bearer TOKEN" \
     -H "Content-Type: application/json" \
     http://localhost:8000/api/v1/backup/recover \
     -d '{
       "backup_id": "full_20241201_020000",
       "recovery_type": "full_restore",
       "restore_components": ["database", "files"]
     }'

# 3. Monitor recovery progress
curl -H "Authorization: Bearer TOKEN" \
     "http://localhost:8000/api/v1/backup/recovery/status/RECOVERY_ID"
```

## Common Issues & Solutions

### ❌ "Permission Denied" Errors
```bash
# Check and fix backup directory permissions
sudo chown -R $(id -u):$(id -g) /app/backups
sudo chmod 755 /app/backups
```

### ❌ "Encryption Key Invalid"
```bash
# Regenerate encryption key
./scripts/setup-backup-encryption.sh

# Or manually generate:
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

### ❌ Database Connection Failures
```bash
# Test database connectivity
docker compose exec backend python -c "
import asyncio, asyncpg
async def test():
    try:
        conn = await asyncpg.connect('postgresql://chrono_scraper:chrono_scraper_dev@postgres:5432/chrono_scraper')
        print('✅ Database connection successful')
        await conn.close()
    except Exception as e:
        print(f'❌ Database connection failed: {e}')
asyncio.run(test())
"
```

### ❌ Storage Backend Issues

**AWS S3**:
```bash
# Test S3 connection
aws s3 ls s3://your-bucket --region us-east-1

# Check credentials
aws sts get-caller-identity
```

**Local Storage Full**:
```bash
# Check disk space
df -h /app/backups

# Clean old backups
docker compose exec backend python -c "
from app.services.backup_service import backup_service
import asyncio
async def cleanup():
    await backup_service.initialize()
    deleted = await backup_service.cleanup_old_backups(retention_days=7)
    print(f'Deleted {deleted} old backups')
asyncio.run(cleanup())
"
```

### ❌ High Memory Usage
```bash
# Check memory usage
docker stats chrono_backend

# Reduce parallel operations
docker compose exec backend python -c "
import os
print('Current parallel ops:', os.getenv('BACKUP_MAX_PARALLEL_OPERATIONS', '3'))
"

# Edit .env to reduce:
# BACKUP_MAX_PARALLEL_OPERATIONS=1
# BACKUP_MEMORY_LIMIT_GB=1
```

### ❌ Backup Taking Too Long
```bash
# Check active backup status
curl -H "Authorization: Bearer TOKEN" \
     "http://localhost:8000/api/v1/backup/status"

# Monitor backup progress logs
docker compose logs -f backend | grep -i backup

# Cancel stuck backup
curl -X POST -H "Authorization: Bearer TOKEN" \
     "http://localhost:8000/api/v1/backup/cancel/BACKUP_ID"
```

## Diagnostic Commands

### System Status
```bash
# Overall health check
docker compose exec backend python app/scripts/validate_backup_environment.py --verbose

# Check service status
make status
# or
docker compose ps

# View resource usage
docker stats --no-stream
```

### Backup System Status
```bash
# API health check
curl -s -H "Authorization: Bearer TOKEN" \
     http://localhost:8000/api/v1/backup/health | jq .

# Recent backup history
curl -s -H "Authorization: Bearer TOKEN" \
     "http://localhost:8000/api/v1/backup/list?limit=5" | jq .

# Active operations
curl -s -H "Authorization: Bearer TOKEN" \
     "http://localhost:8000/api/v1/backup/status" | jq .
```

### Log Analysis
```bash
# Backup operation logs
docker compose logs backend | grep -E "(backup|recovery)" | tail -20

# Error logs only
docker compose logs backend | grep -i error | grep -i backup

# Notification logs
docker compose logs backend | grep -i notification | tail -10

# Performance logs
docker compose logs backend | grep -E "(duration|completed)" | tail -10
```

## Configuration Validation

### Environment Variables
```bash
# Check critical backup settings
docker compose exec backend python -c "
from app.core.config import settings
import os

print('Backup System Configuration:')
print(f'  Enabled: {getattr(settings, \"BACKUP_ENABLED\", False)}')
print(f'  Local Path: {getattr(settings, \"BACKUP_LOCAL_PATH\", \"not set\")}')
print(f'  Encryption Key: {\"set\" if getattr(settings, \"BACKUP_ENCRYPTION_KEY\", \"\") else \"missing\"}')
print(f'  Notifications: {getattr(settings, \"BACKUP_NOTIFICATIONS_ENABLED\", False)}')
print(f'  AWS S3: {getattr(settings, \"BACKUP_AWS_ENABLED\", False)}')
print(f'  Google Cloud: {getattr(settings, \"BACKUP_GCS_ENABLED\", False)}')
print(f'  Azure: {getattr(settings, \"BACKUP_AZURE_ENABLED\", False)}')
"
```

### Storage Backend Tests
```bash
# Test all configured backends
curl -X POST -H "Authorization: Bearer TOKEN" \
     -H "Content-Type: application/json" \
     http://localhost:8000/api/v1/backup/storage/test \
     -d '{"test_all": true}'
```

## Performance Optimization

### Slow Backups
```bash
# Check compression settings
# In .env, try faster compression:
BACKUP_COMPRESSION_TYPE=lz4  # Faster than gzip
BACKUP_COMPRESSION_LEVEL=1   # Lower compression, faster

# Increase parallel operations (if sufficient resources):
BACKUP_MAX_PARALLEL_OPERATIONS=5

# Increase bandwidth limit:
BACKUP_BANDWIDTH_LIMIT_MBPS=100
```

### Memory Issues
```bash
# Reduce memory usage
BACKUP_MEMORY_LIMIT_GB=1
BACKUP_MAX_PARALLEL_OPERATIONS=1
BACKUP_CHUNK_SIZE_MB=32  # Smaller chunks

# Monitor memory during backup
watch -n 5 'docker stats --no-stream chrono_backend'
```

## Recovery Testing

### Test Backup Integrity
```bash
# Verify specific backup
curl -X POST -H "Authorization: Bearer TOKEN" \
     -H "Content-Type: application/json" \
     http://localhost:8000/api/v1/backup/verify \
     -d '{"backup_id": "full_20241201_020000"}'
```

### Dry-run Recovery
```bash
# Test recovery without actually restoring
curl -X POST -H "Authorization: Bearer TOKEN" \
     -H "Content-Type: application/json" \
     http://localhost:8000/api/v1/backup/recover \
     -d '{
       "backup_id": "full_20241201_020000",
       "recovery_type": "full_restore",
       "dry_run": true
     }'
```

## Emergency Contacts

### Development Team
- **Primary**: Check project README for team contacts
- **Secondary**: System administrator
- **Emergency**: On-call engineer

### External Services
- **AWS Support**: AWS Console → Support
- **Google Cloud**: Cloud Console → Support
- **Azure Support**: Azure Portal → Support

## Quick Reference URLs

### Local Development
- Backup API: http://localhost:8000/api/v1/backup/
- Health Check: http://localhost:8000/api/v1/backup/health
- Flower (Celery): http://localhost:5555
- Mailpit: http://localhost:8025

### Documentation
- Full Backup Guide: `./BACKUP_SYSTEM_GUIDE.md`
- Project README: `./README.md`
- API Documentation: http://localhost:8000/docs

---

**Emergency Hotline**: Check your organization's incident response procedures

**Last Updated**: December 2024