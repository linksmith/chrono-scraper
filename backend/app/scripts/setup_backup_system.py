#!/usr/bin/env python3
"""
Setup script for the backup and recovery system.

This script initializes:
- Database schema for backup models
- Default storage backends
- Initial backup schedules
- Retention policies
- System health checks
- Example configurations
"""

import asyncio
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

# Add the backend app to the Python path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel, select

from app.core.config import settings
from app.models.backup import (
    StorageBackendConfig, BackupSchedule, BackupRetentionPolicy,
    BackupTypeEnum, StorageBackendEnum, CompressionTypeEnum
)


async def create_database_tables():
    """Create backup-related database tables."""
    print("Creating backup database tables...")
    
    engine = create_async_engine(settings.ASYNC_DATABASE_URL, echo=True)
    
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    
    await engine.dispose()
    print("✓ Database tables created successfully")


async def setup_default_storage_backends():
    """Set up default storage backends."""
    print("Setting up default storage backends...")
    
    engine = create_async_engine(settings.ASYNC_DATABASE_URL, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    async with async_session() as session:
        # Check if storage backends already exist
        result = await session.execute(select(StorageBackendConfig))
        existing_backends = result.scalars().all()
        
        if existing_backends:
            print(f"Found {len(existing_backends)} existing storage backends, skipping setup")
            return
        
        # Create local storage backend
        local_backend = StorageBackendConfig(
            name="Local Storage",
            backend_type=StorageBackendEnum.LOCAL,
            config_data={
                "base_path": "/app/backups",
                "description": "Local filesystem storage for backups"
            },
            description="Default local filesystem storage backend",
            tags=["default", "local"]
        )
        session.add(local_backend)
        
        # Create example S3 backend (disabled by default)
        s3_backend = StorageBackendConfig(
            name="AWS S3 Storage",
            backend_type=StorageBackendEnum.AWS_S3,
            config_data={
                "bucket_name": "chrono-scraper-backups",
                "region": "us-east-1",
                "prefix": "backups/",
                "description": "AWS S3 storage for production backups"
            },
            is_active=False,  # Disabled until properly configured
            description="AWS S3 storage backend - requires configuration",
            tags=["cloud", "s3", "production"]
        )
        session.add(s3_backend)
        
        await session.commit()
        print("✓ Default storage backends created")
    
    await engine.dispose()


async def setup_default_backup_schedules():
    """Set up default backup schedules."""
    print("Setting up default backup schedules...")
    
    engine = create_async_engine(settings.ASYNC_DATABASE_URL, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    async with async_session() as session:
        # Check if schedules already exist
        result = await session.execute(select(BackupSchedule))
        existing_schedules = result.scalars().all()
        
        if existing_schedules:
            print(f"Found {len(existing_schedules)} existing schedules, skipping setup")
            return
        
        # Get local storage backend
        storage_result = await session.execute(
            select(StorageBackendConfig).where(
                StorageBackendConfig.backend_type == StorageBackendEnum.LOCAL
            )
        )
        local_storage = storage_result.scalar_one_or_none()
        
        if not local_storage:
            print("⚠ No local storage backend found, cannot create schedules")
            return
        
        # Daily full backup at 2 AM
        daily_backup = BackupSchedule(
            name="Daily Full Backup",
            cron_expression="0 2 * * *",  # Daily at 2 AM
            timezone="UTC",
            backup_type=BackupTypeEnum.FULL,
            storage_backend_id=local_storage.id,
            compression_type=CompressionTypeEnum.GZIP,
            encrypt_backup=True,
            verify_integrity=True,
            retention_days=30,
            exclude_patterns=[
                "*.log",
                "*.tmp",
                "cache/*",
                "temp/*"
            ],
            bandwidth_limit_mbps=50,
            max_parallel_uploads=2,
            description="Automated daily full system backup",
            tags=["daily", "full", "automated"],
            next_run_at=datetime.utcnow().replace(hour=2, minute=0, second=0) + timedelta(days=1)
        )
        session.add(daily_backup)
        
        # Weekly database-only backup on Sundays
        weekly_db_backup = BackupSchedule(
            name="Weekly Database Backup",
            cron_expression="0 1 * * 0",  # Weekly on Sunday at 1 AM
            timezone="UTC",
            backup_type=BackupTypeEnum.DATABASE_ONLY,
            storage_backend_id=local_storage.id,
            compression_type=CompressionTypeEnum.ZSTD,
            encrypt_backup=True,
            verify_integrity=True,
            retention_days=90,
            description="Weekly database-only backup for data archival",
            tags=["weekly", "database", "archival"]
        )
        session.add(weekly_db_backup)
        
        await session.commit()
        print("✓ Default backup schedules created")
    
    await engine.dispose()


async def setup_retention_policies():
    """Set up default retention policies."""
    print("Setting up retention policies...")
    
    engine = create_async_engine(settings.ASYNC_DATABASE_URL, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    async with async_session() as session:
        # Check if policies already exist
        result = await session.execute(select(BackupRetentionPolicy))
        existing_policies = result.scalars().all()
        
        if existing_policies:
            print(f"Found {len(existing_policies)} existing policies, skipping setup")
            return
        
        # Get local storage backend
        storage_result = await session.execute(
            select(StorageBackendConfig).where(
                StorageBackendConfig.backend_type == StorageBackendEnum.LOCAL
            )
        )
        local_storage = storage_result.scalar_one_or_none()
        
        if not local_storage:
            print("⚠ No local storage backend found, cannot create policies")
            return
        
        # Standard retention policy
        standard_policy = BackupRetentionPolicy(
            name="Standard Retention Policy",
            storage_backend_id=local_storage.id,
            retention_days=30,
            keep_daily_for_days=7,
            keep_weekly_for_weeks=4,
            keep_monthly_for_months=12,
            keep_yearly_for_years=5,
            min_backups_to_keep=3,
            policy_rules={
                "compress_old_backups": True,
                "verify_before_deletion": True,
                "send_deletion_reports": True
            }
        )
        session.add(standard_policy)
        
        # Database retention policy (longer retention)
        database_policy = BackupRetentionPolicy(
            name="Database Retention Policy",
            storage_backend_id=local_storage.id,
            backup_type=BackupTypeEnum.DATABASE_ONLY,
            retention_days=90,
            keep_daily_for_days=14,
            keep_weekly_for_weeks=8,
            keep_monthly_for_months=24,
            keep_yearly_for_years=7,
            min_backups_to_keep=5,
            policy_rules={
                "compress_old_backups": True,
                "verify_before_deletion": True,
                "archive_to_cold_storage": True
            }
        )
        session.add(database_policy)
        
        await session.commit()
        print("✓ Retention policies created")
    
    await engine.dispose()


async def create_backup_directories():
    """Create necessary backup directories."""
    print("Creating backup directories...")
    
    backup_dirs = [
        "/app/backups",
        "/app/backups/local",
        "/app/backups/temp",
        "/app/backups/verification",
        "/app/logs/backup"
    ]
    
    for directory in backup_dirs:
        os.makedirs(directory, exist_ok=True)
        os.chmod(directory, 0o755)
        print(f"✓ Created directory: {directory}")


def create_backup_configuration_file():
    """Create backup system configuration file."""
    print("Creating backup configuration file...")
    
    config_content = '''# Backup System Configuration
# This file contains configuration for the Chrono Scraper backup system

# Storage Backend Configuration
BACKUP_LOCAL_PATH=/app/backups
BACKUP_ENCRYPTION_KEY=your_backup_encryption_key_here_32_bytes_long

# AWS S3 Configuration (optional)
# BACKUP_AWS_ACCESS_KEY_ID=your_access_key
# BACKUP_AWS_SECRET_ACCESS_KEY=your_secret_key
# BACKUP_AWS_BUCKET_NAME=chrono-scraper-backups
# BACKUP_AWS_REGION=us-east-1
# BACKUP_AWS_PREFIX=chrono-scraper/

# Google Cloud Storage Configuration (optional)
# BACKUP_GCS_PROJECT_ID=your_project_id
# BACKUP_GCS_BUCKET_NAME=chrono-scraper-backups
# BACKUP_GCS_PREFIX=chrono-scraper/

# Azure Blob Storage Configuration (optional)
# BACKUP_AZURE_ACCOUNT_NAME=your_account
# BACKUP_AZURE_ACCOUNT_KEY=your_key
# BACKUP_AZURE_CONTAINER_NAME=chrono-scraper-backups

# Backup Performance Settings
BACKUP_MAX_PARALLEL_OPERATIONS=3
BACKUP_BANDWIDTH_LIMIT_MBPS=100
BACKUP_COMPRESSION_LEVEL=6
BACKUP_VERIFICATION_ENABLED=true

# Monitoring and Alerting
BACKUP_HEALTH_CHECK_INTERVAL_MINUTES=60
BACKUP_ALERT_EMAIL_RECIPIENTS=admin@yourcompany.com
BACKUP_SLACK_WEBHOOK_URL=https://hooks.slack.com/services/your/webhook/url

# Retention Settings
BACKUP_DEFAULT_RETENTION_DAYS=30
BACKUP_MIN_BACKUPS_TO_KEEP=3
BACKUP_AUTO_CLEANUP_ENABLED=true
BACKUP_CLEANUP_DRY_RUN=false
'''
    
    config_path = Path("/app/.env.backup")
    with open(config_path, 'w') as f:
        f.write(config_content)
    
    print(f"✓ Configuration file created: {config_path}")
    print("  Please review and update the configuration with your specific settings")


def create_backup_scripts():
    """Create utility scripts for backup operations."""
    print("Creating backup utility scripts...")
    
    # Manual backup script
    manual_backup_script = '''#!/bin/bash
# Manual backup script for Chrono Scraper

echo "Starting manual backup..."

# Set defaults
BACKUP_TYPE="${1:-full}"
STORAGE_BACKEND="${2:-local}"
ENCRYPT="${3:-true}"

echo "Backup type: $BACKUP_TYPE"
echo "Storage backend: $STORAGE_BACKEND"
echo "Encryption: $ENCRYPT"

# Run the backup via API
curl -X POST "http://localhost:8000/api/v1/backup/manual" \\
  -H "Content-Type: application/json" \\
  -H "Authorization: Bearer $ADMIN_TOKEN" \\
  -d "{
    \\"backup_type\\": \\"$BACKUP_TYPE\\",
    \\"storage_backend_id\\": 1,
    \\"encrypt_backup\\": $ENCRYPT,
    \\"verify_integrity\\": true
  }"

echo "Backup initiated. Check the admin dashboard for progress."
'''
    
    # Restore script
    restore_script = '''#!/bin/bash
# Restore script for Chrono Scraper

echo "WARNING: This will restore from backup and may overwrite current data!"
echo "Press Ctrl+C to cancel, or Enter to continue..."
read

BACKUP_ID="${1}"
RECOVERY_TYPE="${2:-full_restore}"

if [ -z "$BACKUP_ID" ]; then
    echo "Usage: $0 <backup_id> [recovery_type]"
    echo "Recovery types: full_restore, database_only, files_only, configuration_only"
    exit 1
fi

echo "Starting restore from backup: $BACKUP_ID"
echo "Recovery type: $RECOVERY_TYPE"

# Run the restore via API
curl -X POST "http://localhost:8000/api/v1/backup/recovery" \\
  -H "Content-Type: application/json" \\
  -H "Authorization: Bearer $ADMIN_TOKEN" \\
  -d "{
    \\"recovery_type\\": \\"$RECOVERY_TYPE\\",
    \\"backup_id\\": \\"$BACKUP_ID\\",
    \\"storage_backend_id\\": 1,
    \\"validate_after_restore\\": true,
    \\"create_backup_before_restore\\": true
  }"

echo "Restore initiated. Monitor progress in the admin dashboard."
'''
    
    # Health check script
    health_check_script = '''#!/bin/bash
# Backup system health check script

echo "Checking backup system health..."

# Check backup API health
API_HEALTH=$(curl -s "http://localhost:8000/api/v1/backup/health" | grep -o '"overall_health":"[^"]*"' | cut -d'"' -f4)

echo "API Health: $API_HEALTH"

# Check storage space
BACKUP_DIR="/app/backups"
if [ -d "$BACKUP_DIR" ]; then
    USAGE=$(df -h "$BACKUP_DIR" | tail -1 | awk '{print $5}' | sed 's/%//')
    echo "Storage usage: ${USAGE}%"
    
    if [ "$USAGE" -gt 90 ]; then
        echo "WARNING: Storage usage is above 90%"
    fi
else
    echo "WARNING: Backup directory not found: $BACKUP_DIR"
fi

# Check recent backup status
echo "Recent backup status:"
curl -s "http://localhost:8000/api/v1/backup/history?limit=5" | \
  jq -r '.[] | "\\(.backup_id): \\(.status) (\\(.started_at))"' 2>/dev/null || \
  echo "Could not retrieve recent backup status"
'''
    
    scripts_dir = Path("/app/scripts/backup")
    scripts_dir.mkdir(parents=True, exist_ok=True)
    
    scripts = {
        "manual_backup.sh": manual_backup_script,
        "restore_backup.sh": restore_script,
        "health_check.sh": health_check_script
    }
    
    for script_name, script_content in scripts.items():
        script_path = scripts_dir / script_name
        with open(script_path, 'w') as f:
            f.write(script_content)
        os.chmod(script_path, 0o755)
        print(f"✓ Created script: {script_path}")


async def verify_setup():
    """Verify the backup system setup."""
    print("Verifying backup system setup...")
    
    engine = create_async_engine(settings.ASYNC_DATABASE_URL, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    async with async_session() as session:
        # Check storage backends
        storage_result = await session.execute(select(StorageBackendConfig))
        storage_backends = storage_result.scalars().all()
        print(f"✓ Storage backends: {len(storage_backends)}")
        
        # Check backup schedules
        schedule_result = await session.execute(select(BackupSchedule))
        schedules = schedule_result.scalars().all()
        print(f"✓ Backup schedules: {len(schedules)}")
        
        # Check retention policies
        policy_result = await session.execute(select(BackupRetentionPolicy))
        policies = policy_result.scalars().all()
        print(f"✓ Retention policies: {len(policies)}")
    
    await engine.dispose()
    
    # Check directories
    backup_dirs = ["/app/backups", "/app/logs/backup", "/app/scripts/backup"]
    for directory in backup_dirs:
        if os.path.exists(directory):
            print(f"✓ Directory exists: {directory}")
        else:
            print(f"✗ Directory missing: {directory}")
    
    print("\n=== Backup System Setup Complete ===")
    print("Next steps:")
    print("1. Review the configuration in /app/.env.backup")
    print("2. Configure external storage backends if needed")
    print("3. Test manual backup: /app/scripts/backup/manual_backup.sh")
    print("4. Access the admin dashboard: http://localhost:8000/admin/backup")
    print("5. Monitor system health: /app/scripts/backup/health_check.sh")


async def main():
    """Main setup function."""
    print("=== Chrono Scraper Backup System Setup ===\n")
    
    try:
        await create_database_tables()
        await setup_default_storage_backends()
        await setup_default_backup_schedules()
        await setup_retention_policies()
        await create_backup_directories()
        create_backup_configuration_file()
        create_backup_scripts()
        await verify_setup()
        
        print("\n✅ Backup system setup completed successfully!")
        
    except Exception as e:
        print(f"\n❌ Setup failed: {str(e)}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)