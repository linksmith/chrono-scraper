# Chrono Scraper Admin Quick Reference Guide

## Emergency Cheat Sheet for Enterprise Administrators

### 1. System Health Checks

#### Docker Compose Services
```bash
# Check all service status
docker compose ps

# View service logs
docker compose logs -f <service_name>
```

#### API Health Endpoints
- Backend API: `http://localhost:8000/api/v1/health`
- Meilisearch: `http://localhost:7700/health`
- Firecrawl API: `http://localhost:3002/health`

### 2. User Management Quick Commands

#### Database User Operations
```bash
# Direct PostgreSQL Access
docker compose exec postgres psql -U chrono_scraper -d chrono_scraper

# Check user status
SELECT email, is_verified, approval_status, is_active 
FROM users 
WHERE email = 'user@example.com';

# Approve User
UPDATE users 
SET approval_status = 'approved', 
    approval_date = NOW() 
WHERE email = 'user@example.com';
```

### 3. Performance Monitoring

#### Monitoring Tools
- **Flower (Celery Tasks)**: `http://localhost:5555`
- **Grafana Dashboards**: `http://localhost:3000`
- **Prometheus Metrics**: `http://localhost:9090`

#### Key Performance Commands
```bash
# Check Celery Worker Status
docker compose exec backend celery -A app.tasks.celery_app inspect active

# Monitor Resource Usage
docker compose exec backend top

# View System Resource Statistics
make resource-stats
```

### 4. Backup and Recovery

#### Backup Procedures
```bash
# Create Full Backup
./scripts/backup-full.sh

# Restore from Backup
./scripts/restore-backup.sh
```

### 5. Search and Indexing

#### Meilisearch Management
```bash
# List Meilisearch Indexes
curl http://localhost:7700/indexes

# Reindex Optimization
docker compose exec backend python scripts/reindex_optimized.py
```

### 6. Security Quick Checks

#### Authentication Verification
```bash
# Check User Authentication Details
docker compose exec backend python -c "
from app.core.security import verify_password
user_email = 'user@example.com'
plain_password = 'testpassword'
# Add verification logic here
"
```

### 7. Common Troubleshooting

#### Restart Services
```bash
# Restart Specific Service
docker compose restart <service_name>

# Complete System Restart
make down
make up
```

### 8. Emergency Reset Procedures

#### Database Reset
```bash
# Stop All Services
docker compose down

# Remove Database Volumes (CAUTION!)
docker volume rm chrono-scraper-fastapi-2_postgres_data

# Recreate Database
make init
```

### 9. Logging and Diagnostics

#### View Comprehensive Logs
```bash
# Backend Logs
docker compose logs -f backend

# Celery Worker Logs
docker compose logs -f celery_worker

# Firecrawl Logs
docker compose logs -f firecrawl-api
```

### 10. Certification Maintenance

#### Continuous Learning
- Review [ADMIN_TRAINING_PROGRAM.md](/ADMIN_TRAINING_PROGRAM.md)
- Complete annual recertification
- Stay updated with platform changes

## Important Contact Information
- **Support Email**: support@chronoscraper.com
- **Incident Response**: incidents@chronoscraper.com
- **Documentation**: docs@chronoscraper.com

## Version Information
- **Quick Reference Version**: 1.0.0
- **Last Updated**: 2025-08-24

**REMINDER**: Always follow the principle of least privilege and maintain comprehensive audit logs.