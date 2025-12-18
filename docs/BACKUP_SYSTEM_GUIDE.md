# Chrono Scraper Backup System - Production Deployment Guide

## Table of Contents
- [Overview](#overview)
- [Architecture](#architecture)
- [Installation & Setup](#installation--setup)
- [Configuration](#configuration)
- [Storage Backends](#storage-backends)
- [Notifications](#notifications)
- [Security](#security)
- [Monitoring & Maintenance](#monitoring--maintenance)
- [Troubleshooting](#troubleshooting)
- [API Reference](#api-reference)

## Overview

The Chrono Scraper backup system provides enterprise-grade backup and recovery capabilities with:

- **Multiple Storage Backends**: Local, AWS S3, Google Cloud Storage, Azure Blob Storage, SFTP
- **Comprehensive Backup Types**: Full, incremental, differential, database-only, files-only, configuration
- **Advanced Features**: Encryption, compression, integrity verification, point-in-time recovery
- **Multi-Channel Notifications**: Email, Slack, Discord, webhooks, PagerDuty
- **Monitoring & Audit**: Health checks, audit logging, performance metrics
- **Automated Scheduling**: Cron-based scheduling with retention policies

## Architecture

### Core Components

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Backup API    │    │ Backup Service  │    │ Storage Backend │
│                 │────│                 │────│                 │
│ - REST API      │    │ - Orchestration │    │ - Local/Cloud   │
│ - Scheduling    │    │ - Compression   │    │ - Multi-provider│
│ - Monitoring    │    │ - Encryption    │    │ - Redundancy    │
└─────────────────┘    └─────────────────┘    └─────────────────┘
         │                       │                       │
         │              ┌─────────────────┐              │
         │              │ Notification    │              │
         └──────────────│ Service         │──────────────┘
                        │                 │
                        │ - Multi-channel │
                        │ - Templates     │
                        │ - Alerting      │
                        └─────────────────┘
```

### Data Flow

1. **Backup Initiation**: API/Scheduler triggers backup job
2. **Data Collection**: Gather PostgreSQL, Redis, Meilisearch, files
3. **Processing**: Compress, encrypt, verify integrity
4. **Storage**: Upload to configured storage backend(s)
5. **Verification**: Validate backup integrity and completeness
6. **Notification**: Send status notifications via configured channels
7. **Cleanup**: Apply retention policies and cleanup old backups

## Installation & Setup

### Prerequisites

- Docker & Docker Compose
- PostgreSQL 17+
- Redis 7+
- Meilisearch
- Sufficient storage space (recommended: 5x data size)
- Network access to storage backends

### Quick Setup

1. **Clone and Configure**:
   ```bash
   cd chrono-scraper-fastapi-2
   cp .env.example .env
   # Edit .env with backup configuration (see Configuration section)
   ```

2. **Validate Environment**:
   ```bash
   docker compose exec backend python app/scripts/validate_backup_environment.py --verbose
   ```

3. **Initialize Backup System**:
   ```bash
   docker compose exec backend python app/scripts/setup_backup_system.py
   ```

4. **Test Backup**:
   ```bash
   curl -X POST http://localhost:8000/api/v1/backup/test \
        -H "Authorization: Bearer YOUR_TOKEN"
   ```

### Production Deployment Steps

1. **Environment Configuration**: Configure all backup settings in `.env`
2. **Storage Setup**: Configure and test storage backends
3. **Security Setup**: Generate encryption keys, configure access
4. **Notification Setup**: Configure notification channels
5. **Monitoring Setup**: Set up health checks and monitoring
6. **Testing**: Perform test backups and recovery operations
7. **Scheduling**: Configure automated backup schedules
8. **Documentation**: Document procedures and access credentials

## Configuration

### Environment Variables Reference

#### Basic Configuration
```bash
# Enable backup system
BACKUP_ENABLED=true
BACKUP_SYSTEM_VERSION=1.0.0
BACKUP_DEFAULT_TYPE=full
BACKUP_COMPRESSION_TYPE=gzip
```

#### Security & Encryption
```bash
# Generate with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
BACKUP_ENCRYPTION_KEY=your-base64-encryption-key
BACKUP_ENCRYPTION_ALGORITHM=AES-256-GCM
BACKUP_VERIFY_INTEGRITY=true
```

#### Local Storage
```bash
BACKUP_LOCAL_ENABLED=true
BACKUP_LOCAL_PATH=/app/backups
BACKUP_LOCAL_MAX_SIZE_GB=100
BACKUP_LOCAL_PERMISSIONS=0755
```

#### Performance & Limits
```bash
BACKUP_MAX_PARALLEL_OPERATIONS=3
BACKUP_BANDWIDTH_LIMIT_MBPS=50
BACKUP_TIMEOUT_SECONDS=3600
BACKUP_MEMORY_LIMIT_GB=2
```

#### Retention Policies
```bash
BACKUP_RETENTION_DAYS=30
BACKUP_KEEP_DAILY_FOR_DAYS=7
BACKUP_KEEP_WEEKLY_FOR_WEEKS=4
BACKUP_KEEP_MONTHLY_FOR_MONTHS=12
BACKUP_KEEP_YEARLY_FOR_YEARS=5
BACKUP_MIN_BACKUPS_TO_KEEP=3
```

### Backup Types Configuration

| Type | Description | Use Case | Size | Speed |
|------|-------------|----------|------|-------|
| `full` | Complete system backup | Initial backup, weekly/monthly | Large | Slow |
| `incremental` | Changes since last backup | Daily backups | Small | Fast |
| `differential` | Changes since last full backup | Alternative to incremental | Medium | Medium |
| `database_only` | PostgreSQL + Redis only | Quick data backups | Medium | Fast |
| `files_only` | Application files only | Code/config backups | Small | Fast |
| `configuration` | Settings and configs only | Configuration management | Tiny | Very Fast |

### Scheduling Configuration

```bash
# Cron expressions for backup schedules
BACKUP_SCHEDULE_FULL_BACKUPS="0 2 * * 0"        # Sunday 2 AM
BACKUP_SCHEDULE_INCREMENTAL_BACKUPS="0 3 * * 1-6" # Monday-Saturday 3 AM
BACKUP_SCHEDULE_DATABASE_ONLY="0 */6 * * *"     # Every 6 hours
BACKUP_SCHEDULE_CONFIGURATION="0 4 * * *"       # Daily 4 AM
```

## Storage Backends

### Local Storage

**Pros**: Fast, simple, no external dependencies
**Cons**: Single point of failure, limited by disk space

```bash
BACKUP_LOCAL_ENABLED=true
BACKUP_LOCAL_PATH=/app/backups
BACKUP_LOCAL_MAX_SIZE_GB=100
```

### AWS S3

**Pros**: Highly scalable, reliable, multiple storage classes
**Cons**: Network dependency, costs

**Setup**:
1. Create S3 bucket with versioning enabled
2. Create IAM user with S3 permissions
3. Configure environment variables

```bash
BACKUP_AWS_ENABLED=true
BACKUP_AWS_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE
BACKUP_AWS_SECRET_ACCESS_KEY=wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY
BACKUP_AWS_BUCKET_NAME=chrono-scraper-backups
BACKUP_AWS_REGION=us-east-1
BACKUP_AWS_PREFIX=backups/production/
BACKUP_AWS_STORAGE_CLASS=STANDARD_IA
```

**IAM Policy**:
```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "s3:ListBucket",
                "s3:GetBucketLocation"
            ],
            "Resource": "arn:aws:s3:::chrono-scraper-backups"
        },
        {
            "Effect": "Allow",
            "Action": [
                "s3:PutObject",
                "s3:GetObject",
                "s3:DeleteObject"
            ],
            "Resource": "arn:aws:s3:::chrono-scraper-backups/*"
        }
    ]
}
```

### Google Cloud Storage

**Pros**: Integration with Google Cloud, competitive pricing
**Cons**: Network dependency, Google Cloud account required

**Setup**:
1. Create GCS bucket with uniform bucket-level access
2. Create service account with Storage Admin role
3. Download service account key JSON

```bash
BACKUP_GCS_ENABLED=true
BACKUP_GCS_PROJECT_ID=your-gcp-project
BACKUP_GCS_BUCKET_NAME=chrono-scraper-backups
BACKUP_GCS_CREDENTIALS_PATH=/app/secrets/gcs-service-account.json
BACKUP_GCS_STORAGE_CLASS=NEARLINE
```

### Azure Blob Storage

**Pros**: Microsoft ecosystem integration, hot/cool/archive tiers
**Cons**: Network dependency, Azure account required

```bash
BACKUP_AZURE_ENABLED=true
BACKUP_AZURE_ACCOUNT_NAME=chronoscraperbackups
BACKUP_AZURE_ACCOUNT_KEY=your-storage-account-key
BACKUP_AZURE_CONTAINER_NAME=backups
BACKUP_AZURE_TIER=Cool
```

### SFTP Storage

**Pros**: Standard protocol, works with any SFTP server
**Cons**: Network dependency, manual server management

```bash
BACKUP_SFTP_ENABLED=true
BACKUP_SFTP_HOST=backup-server.company.com
BACKUP_SFTP_PORT=22
BACKUP_SFTP_USERNAME=backup-user
BACKUP_SFTP_PASSWORD=secure-password
# OR use key-based authentication:
BACKUP_SFTP_PRIVATE_KEY_PATH=/app/secrets/backup_ssh_key
```

## Notifications

### Email Notifications

**Setup with Mailgun**:
```bash
BACKUP_EMAIL_ENABLED=true
BACKUP_EMAIL_RECIPIENTS=admin@company.com,devops@company.com
BACKUP_EMAIL_FROM=backups@company.com
BACKUP_EMAIL_SMTP_HOST=smtp.mailgun.org
BACKUP_EMAIL_SMTP_PORT=587
BACKUP_EMAIL_SMTP_USE_TLS=true
BACKUP_EMAIL_SMTP_USERNAME=backups@company.com
BACKUP_EMAIL_SMTP_PASSWORD=your-mailgun-password
```

**Setup with Gmail**:
```bash
BACKUP_EMAIL_SMTP_HOST=smtp.gmail.com
BACKUP_EMAIL_SMTP_PORT=587
BACKUP_EMAIL_SMTP_USERNAME=your-gmail@gmail.com
BACKUP_EMAIL_SMTP_PASSWORD=your-app-password
```

### Slack Notifications

1. Create Slack webhook in your workspace
2. Configure channel and appearance settings

```bash
BACKUP_SLACK_ENABLED=true
BACKUP_SLACK_WEBHOOK_URL=https://hooks.slack.com/services/YOUR/SLACK/WEBHOOK
BACKUP_SLACK_CHANNEL=#backups
BACKUP_SLACK_USERNAME=BackupBot
BACKUP_SLACK_ICON_EMOJI=:floppy_disk:
```

### Discord Notifications

```bash
BACKUP_DISCORD_ENABLED=true
BACKUP_DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/YOUR/WEBHOOK
```

### PagerDuty Integration

For critical backup failures:

```bash
BACKUP_PAGERDUTY_ENABLED=true
BACKUP_PAGERDUTY_INTEGRATION_KEY=your-pagerduty-integration-key
BACKUP_PAGERDUTY_SEVERITY=error
```

### Custom Webhooks

For integration with monitoring systems:

```bash
BACKUP_WEBHOOK_ENABLED=true
BACKUP_WEBHOOK_URL=https://monitoring.company.com/webhooks/backup
BACKUP_WEBHOOK_SECRET=your-webhook-secret
BACKUP_WEBHOOK_TIMEOUT=30
```

## Security

### Encryption

**Key Generation**:
```python
from cryptography.fernet import Fernet
key = Fernet.generate_key()
print(f"BACKUP_ENCRYPTION_KEY={key.decode()}")
```

**Key Management Best Practices**:
- Store encryption keys in secure key management systems (AWS KMS, Azure Key Vault, etc.)
- Rotate encryption keys regularly
- Never commit encryption keys to version control
- Use different keys for different environments

### Access Control

**File Permissions**:
```bash
# Backup directories should be accessible only to backup user
chmod 700 /app/backups
chown backup:backup /app/backups

# Backup files should not be world-readable
BACKUP_LOCAL_PERMISSIONS=0700
```

**Network Security**:
- Use TLS for all network communications
- Implement VPN or private networks for SFTP connections
- Use IAM roles instead of access keys where possible
- Regularly rotate access credentials

### Audit Logging

```bash
BACKUP_AUDIT_ENABLED=true
BACKUP_AUDIT_LOG_ALL_OPERATIONS=true
BACKUP_AUDIT_LOG_FILE=/app/logs/backup_audit.log
BACKUP_AUDIT_RETENTION_DAYS=365
```

## Monitoring & Maintenance

### Health Checks

The backup system includes comprehensive health monitoring:

```bash
BACKUP_HEALTH_CHECK_ENABLED=true
BACKUP_HEALTH_CHECK_INTERVAL=300  # 5 minutes
BACKUP_HEALTH_CHECK_STORAGE_CONNECTIVITY=true
BACKUP_HEALTH_CHECK_DISK_SPACE=true
BACKUP_HEALTH_CHECK_RECENT_BACKUPS=true
```

### Monitoring Endpoints

- `GET /api/v1/backup/health` - Overall backup system health
- `GET /api/v1/backup/status` - Current backup operations
- `GET /api/v1/backup/metrics` - Performance and usage metrics
- `GET /api/v1/backup/schedules` - Backup schedule status

### Key Metrics to Monitor

1. **Backup Success Rate**: Should be >95%
2. **Backup Duration**: Monitor for degradation over time
3. **Storage Usage**: Track growth and capacity planning
4. **Recovery Time**: Test and monitor recovery performance
5. **Error Rates**: Monitor for recurring issues

### Maintenance Tasks

**Daily**:
- Check backup completion status
- Review backup logs for errors
- Monitor storage usage

**Weekly**:
- Test backup integrity verification
- Review and update retention policies
- Check notification channel functionality

**Monthly**:
- Perform test recovery operations
- Review backup performance metrics
- Update and patch backup system components
- Review security settings and credentials

**Quarterly**:
- Disaster recovery testing
- Security audit of backup configurations
- Review and update backup procedures
- Capacity planning review

## Troubleshooting

### Common Issues

#### Backup Fails with "Permission Denied"
```bash
# Check directory permissions
ls -la /app/backups/
# Fix permissions
chmod 755 /app/backups
chown -R app:app /app/backups
```

#### "Encryption Key Invalid" Error
```bash
# Regenerate encryption key
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
# Update .env file with new key
```

#### PostgreSQL Connection Fails
```bash
# Test database connection
docker compose exec backend python -c "
import asyncpg, asyncio
async def test():
    conn = await asyncpg.connect('postgresql://user:pass@host:port/db')
    print(await conn.fetchval('SELECT version()'))
    await conn.close()
asyncio.run(test())
"
```

#### Storage Backend Connection Issues

**AWS S3**:
```bash
# Test AWS credentials
aws s3 ls s3://your-bucket-name --region us-east-1
```

**Google Cloud**:
```bash
# Test GCS credentials
gsutil ls gs://your-bucket-name
```

**SFTP**:
```bash
# Test SFTP connection
sftp -P 22 user@host
```

#### High Memory Usage
```bash
# Reduce parallel operations
BACKUP_MAX_PARALLEL_OPERATIONS=1
BACKUP_MEMORY_LIMIT_GB=1

# Increase swap space if needed
sudo fallocate -l 2G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
```

### Diagnostic Commands

```bash
# Validate backup environment
docker compose exec backend python app/scripts/validate_backup_environment.py --verbose

# Check backup system status
curl -H "Authorization: Bearer TOKEN" http://localhost:8000/api/v1/backup/health

# View recent backup logs
docker compose logs backend | grep -i backup | tail -50

# Check storage space
df -h /app/backups

# Monitor active backup operations
curl -H "Authorization: Bearer TOKEN" http://localhost:8000/api/v1/backup/status
```

### Log Analysis

**Backup Logs Location**:
- Application logs: `/app/logs/backup.log`
- Audit logs: `/app/logs/backup_audit.log`
- Container logs: `docker compose logs backend`

**Important Log Patterns**:
```bash
# Successful backups
grep "Backup completed successfully" /app/logs/backup.log

# Failed backups
grep "Backup failed" /app/logs/backup.log

# Storage errors
grep -i "storage.*error" /app/logs/backup.log

# Encryption errors
grep -i "encrypt.*error" /app/logs/backup.log
```

## API Reference

### Authentication

All backup API endpoints require authentication:

```bash
# Get authentication token
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email": "admin@example.com", "password": "password"}'

# Use token in subsequent requests
curl -H "Authorization: Bearer YOUR_TOKEN" \
  http://localhost:8000/api/v1/backup/health
```

### Backup Operations

#### Create Backup
```bash
POST /api/v1/backup/create
Content-Type: application/json
Authorization: Bearer TOKEN

{
  "backup_type": "full",
  "storage_backend": "local",
  "compression": "gzip",
  "encrypt": true,
  "verify_integrity": true,
  "include_patterns": ["*.sql", "*.json"],
  "exclude_patterns": ["*.tmp", "*.cache"]
}
```

#### List Backups
```bash
GET /api/v1/backup/list?storage_backend=local&limit=20
```

#### Get Backup Status
```bash
GET /api/v1/backup/status/{backup_id}
```

#### Cancel Backup
```bash
POST /api/v1/backup/cancel/{backup_id}
```

### Recovery Operations

#### Start Recovery
```bash
POST /api/v1/backup/recover
Content-Type: application/json

{
  "backup_id": "full_20241201_020000",
  "recovery_type": "full_restore",
  "target_timestamp": "2024-12-01T02:00:00Z",
  "restore_components": ["database", "files", "configuration"]
}
```

#### Get Recovery Status
```bash
GET /api/v1/backup/recovery/status/{recovery_id}
```

### Management Operations

#### Health Check
```bash
GET /api/v1/backup/health
```

Response:
```json
{
  "status": "healthy",
  "checks": {
    "storage_backends": "healthy",
    "database_connectivity": "healthy",
    "disk_space": "warning",
    "recent_backups": "healthy"
  },
  "metrics": {
    "last_backup": "2024-12-01T02:00:00Z",
    "total_backups": 45,
    "storage_used_gb": 12.5,
    "average_backup_duration": "00:15:30"
  }
}
```

#### System Metrics
```bash
GET /api/v1/backup/metrics
```

#### Backup Schedules
```bash
GET /api/v1/backup/schedules
POST /api/v1/backup/schedules
PUT /api/v1/backup/schedules/{schedule_id}
DELETE /api/v1/backup/schedules/{schedule_id}
```

### Storage Backend Management

#### Test Storage Backend
```bash
POST /api/v1/backup/storage/test
Content-Type: application/json

{
  "backend_type": "aws_s3",
  "config": {
    "access_key_id": "...",
    "secret_access_key": "...",
    "bucket_name": "test-bucket",
    "region": "us-east-1"
  }
}
```

#### List Storage Backends
```bash
GET /api/v1/backup/storage/backends
```

---

## Support and Maintenance

For production deployments, ensure you have:

1. **Documented procedures** for backup and recovery operations
2. **Trained personnel** familiar with the backup system
3. **Regular testing** of backup and recovery processes
4. **Monitoring and alerting** for backup system health
5. **Incident response plans** for backup failures
6. **Security reviews** of backup configurations
7. **Capacity planning** for backup storage growth

For additional support or custom configurations, consult the Chrono Scraper documentation or contact your system administrator.

---

**Last Updated**: December 2024  
**Version**: 1.0.0  
**Compatibility**: Chrono Scraper v2.0+