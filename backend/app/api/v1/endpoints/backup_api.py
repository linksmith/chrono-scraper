"""
API endpoints for backup and recovery management.

This module provides REST API endpoints for:
- Managing backup schedules and configurations
- Triggering manual backups and recovery operations
- Monitoring backup status and history
- Configuring storage backends and retention policies
- Backup verification and integrity checking
- Health monitoring and alerting
"""

from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from fastapi import APIRouter, Depends, HTTPException, status, Query, Body
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select, and_, func
from pydantic import BaseModel, Field

from app.core.database import get_db
from app.core.admin_auth import get_admin_user_backup as get_admin_user
from app.models.user import User
from app.models.backup import (
    BackupSchedule, BackupExecution, RecoveryExecution,
    StorageBackendConfig, BackupRetentionPolicy, BackupTypeEnum, BackupStatusEnum,
    StorageBackendEnum, CompressionTypeEnum, RecoveryStatusEnum,
    RecoveryTypeEnum
)
from app.tasks.backup_tasks import (
    execute_scheduled_backup, execute_manual_backup, execute_recovery,
    verify_backup_integrity, cleanup_old_backups, health_check_backups
)


router = APIRouter()


# Pydantic models for request/response
class BackupScheduleCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    cron_expression: str = Field(..., min_length=5, max_length=100)
    timezone: str = Field(default="UTC", max_length=50)
    backup_type: BackupTypeEnum
    storage_backend_id: int
    compression_type: CompressionTypeEnum = CompressionTypeEnum.GZIP
    encrypt_backup: bool = True
    verify_integrity: bool = True
    retention_days: int = Field(default=30, ge=1, le=365)
    include_patterns: Optional[List[str]] = None
    exclude_patterns: Optional[List[str]] = None
    bandwidth_limit_mbps: Optional[int] = Field(default=None, ge=1)
    max_parallel_uploads: int = Field(default=3, ge=1, le=10)
    description: Optional[str] = Field(default=None, max_length=1000)
    tags: Optional[List[str]] = None


class BackupScheduleUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    cron_expression: Optional[str] = Field(default=None, min_length=5, max_length=100)
    timezone: Optional[str] = Field(default=None, max_length=50)
    backup_type: Optional[BackupTypeEnum] = None
    storage_backend_id: Optional[int] = None
    compression_type: Optional[CompressionTypeEnum] = None
    encrypt_backup: Optional[bool] = None
    verify_integrity: Optional[bool] = None
    retention_days: Optional[int] = Field(default=None, ge=1, le=365)
    include_patterns: Optional[List[str]] = None
    exclude_patterns: Optional[List[str]] = None
    bandwidth_limit_mbps: Optional[int] = Field(default=None, ge=1)
    max_parallel_uploads: Optional[int] = Field(default=None, ge=1, le=10)
    is_active: Optional[bool] = None
    description: Optional[str] = Field(default=None, max_length=1000)
    tags: Optional[List[str]] = None


class ManualBackupRequest(BaseModel):
    backup_type: BackupTypeEnum = BackupTypeEnum.FULL
    storage_backend_id: int
    compression_type: CompressionTypeEnum = CompressionTypeEnum.GZIP
    encrypt_backup: bool = True
    verify_integrity: bool = True
    retention_days: int = Field(default=30, ge=1, le=365)
    include_patterns: Optional[List[str]] = None
    exclude_patterns: Optional[List[str]] = None
    bandwidth_limit_mbps: Optional[int] = Field(default=None, ge=1)
    max_parallel_uploads: int = Field(default=3, ge=1, le=10)


class RecoveryRequest(BaseModel):
    recovery_type: RecoveryTypeEnum
    backup_id: str
    storage_backend_id: int
    restore_target: str = "same_system"
    target_timestamp: Optional[datetime] = None
    restore_components: Optional[List[str]] = None
    validate_after_restore: bool = True
    create_backup_before_restore: bool = True
    skip_existing_files: bool = False
    restore_permissions: bool = True
    custom_restore_path: Optional[str] = None


class StorageBackendConfigCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    backend_type: StorageBackendEnum
    config_data: Dict[str, Any] = Field(..., description="Storage backend configuration")
    description: Optional[str] = Field(default=None, max_length=500)
    tags: Optional[List[str]] = None


class RetentionPolicyCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    storage_backend_id: int
    backup_type: Optional[BackupTypeEnum] = None
    retention_days: int = Field(default=30, ge=1)
    keep_daily_for_days: int = Field(default=7, ge=1)
    keep_weekly_for_weeks: int = Field(default=4, ge=1)
    keep_monthly_for_months: int = Field(default=12, ge=1)
    keep_yearly_for_years: int = Field(default=5, ge=1)
    min_backups_to_keep: int = Field(default=3, ge=1)


# Backup Schedule Management
@router.post("/schedules", response_model=Dict[str, Any])
async def create_backup_schedule(
    *,
    db: AsyncSession = Depends(get_db),
    schedule_data: BackupScheduleCreate,
    current_user: User = Depends(get_admin_user)
):
    """Create a new backup schedule."""
    
    # Verify storage backend exists
    storage_stmt = select(StorageBackendConfig).where(
        StorageBackendConfig.id == schedule_data.storage_backend_id,
        StorageBackendConfig.is_active is True
    )
    storage_result = await db.execute(storage_stmt)
    storage_backend = storage_result.scalar_one_or_none()
    
    if not storage_backend:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Storage backend {schedule_data.storage_backend_id} not found"
        )
    
    # Create backup schedule
    schedule = BackupSchedule(
        **schedule_data.model_dump(),
        next_run_at=datetime.utcnow() + timedelta(hours=1)  # Schedule first run in 1 hour
    )
    
    db.add(schedule)
    await db.commit()
    await db.refresh(schedule)
    
    return {
        "id": schedule.id,
        "name": schedule.name,
        "backup_type": schedule.backup_type,
        "cron_expression": schedule.cron_expression,
        "storage_backend": storage_backend.name,
        "is_active": schedule.is_active,
        "next_run_at": schedule.next_run_at.isoformat() if schedule.next_run_at else None
    }


@router.get("/schedules", response_model=List[Dict[str, Any]])
async def list_backup_schedules(
    *,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_admin_user),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=1000),
    active_only: bool = Query(default=False)
):
    """List backup schedules."""
    
    stmt = select(BackupSchedule, StorageBackendConfig).join(
        StorageBackendConfig, 
        BackupSchedule.storage_backend_id == StorageBackendConfig.id
    )
    
    if active_only:
        stmt = stmt.where(BackupSchedule.is_active is True)
    
    stmt = stmt.offset(skip).limit(limit).order_by(BackupSchedule.created_at.desc())
    
    result = await db.execute(stmt)
    schedules_with_storage = result.all()
    
    return [
        {
            "id": schedule.id,
            "name": schedule.name,
            "backup_type": schedule.backup_type,
            "cron_expression": schedule.cron_expression,
            "timezone": schedule.timezone,
            "storage_backend": storage.name,
            "is_active": schedule.is_active,
            "last_run_at": schedule.last_run_at.isoformat() if schedule.last_run_at else None,
            "next_run_at": schedule.next_run_at.isoformat() if schedule.next_run_at else None,
            "total_runs": schedule.total_runs,
            "successful_runs": schedule.successful_runs,
            "failed_runs": schedule.failed_runs,
            "success_rate": schedule.successful_runs / schedule.total_runs if schedule.total_runs > 0 else 0
        }
        for schedule, storage in schedules_with_storage
    ]


@router.get("/schedules/{schedule_id}", response_model=Dict[str, Any])
async def get_backup_schedule(
    *,
    db: AsyncSession = Depends(get_db),
    schedule_id: int,
    current_user: User = Depends(get_admin_user)
):
    """Get backup schedule details."""
    
    stmt = select(BackupSchedule, StorageBackendConfig).join(
        StorageBackendConfig,
        BackupSchedule.storage_backend_id == StorageBackendConfig.id
    ).where(BackupSchedule.id == schedule_id)
    
    result = await db.execute(stmt)
    schedule_with_storage = result.first()
    
    if not schedule_with_storage:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Backup schedule {schedule_id} not found"
        )
    
    schedule, storage = schedule_with_storage
    
    return {
        "id": schedule.id,
        "name": schedule.name,
        "backup_type": schedule.backup_type,
        "cron_expression": schedule.cron_expression,
        "timezone": schedule.timezone,
        "storage_backend": {
            "id": storage.id,
            "name": storage.name,
            "backend_type": storage.backend_type
        },
        "compression_type": schedule.compression_type,
        "encrypt_backup": schedule.encrypt_backup,
        "verify_integrity": schedule.verify_integrity,
        "retention_days": schedule.retention_days,
        "include_patterns": schedule.include_patterns,
        "exclude_patterns": schedule.exclude_patterns,
        "bandwidth_limit_mbps": schedule.bandwidth_limit_mbps,
        "max_parallel_uploads": schedule.max_parallel_uploads,
        "is_active": schedule.is_active,
        "last_run_at": schedule.last_run_at.isoformat() if schedule.last_run_at else None,
        "next_run_at": schedule.next_run_at.isoformat() if schedule.next_run_at else None,
        "total_runs": schedule.total_runs,
        "successful_runs": schedule.successful_runs,
        "failed_runs": schedule.failed_runs,
        "description": schedule.description,
        "tags": schedule.tags,
        "created_at": schedule.created_at.isoformat(),
        "updated_at": schedule.updated_at.isoformat() if schedule.updated_at else None
    }


@router.put("/schedules/{schedule_id}", response_model=Dict[str, Any])
async def update_backup_schedule(
    *,
    db: AsyncSession = Depends(get_db),
    schedule_id: int,
    schedule_update: BackupScheduleUpdate,
    current_user: User = Depends(get_admin_user)
):
    """Update backup schedule."""
    
    stmt = select(BackupSchedule).where(BackupSchedule.id == schedule_id)
    result = await db.execute(stmt)
    schedule = result.scalar_one_or_none()
    
    if not schedule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Backup schedule {schedule_id} not found"
        )
    
    # Update fields
    for field, value in schedule_update.model_dump(exclude_unset=True).items():
        setattr(schedule, field, value)
    
    schedule.updated_at = datetime.utcnow()
    
    await db.commit()
    await db.refresh(schedule)
    
    return {
        "id": schedule.id,
        "name": schedule.name,
        "is_active": schedule.is_active,
        "updated_at": schedule.updated_at.isoformat()
    }


@router.delete("/schedules/{schedule_id}")
async def delete_backup_schedule(
    *,
    db: AsyncSession = Depends(get_db),
    schedule_id: int,
    current_user: User = Depends(get_admin_user)
):
    """Delete backup schedule."""
    
    stmt = select(BackupSchedule).where(BackupSchedule.id == schedule_id)
    result = await db.execute(stmt)
    schedule = result.scalar_one_or_none()
    
    if not schedule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Backup schedule {schedule_id} not found"
        )
    
    await db.delete(schedule)
    await db.commit()
    
    return {"message": f"Backup schedule {schedule_id} deleted"}


@router.post("/schedules/{schedule_id}/trigger", response_model=Dict[str, Any])
async def trigger_backup_schedule(
    *,
    db: AsyncSession = Depends(get_db),
    schedule_id: int,
    current_user: User = Depends(get_admin_user)
):
    """Manually trigger a backup schedule."""
    
    stmt = select(BackupSchedule).where(
        BackupSchedule.id == schedule_id,
        BackupSchedule.is_active is True
    )
    result = await db.execute(stmt)
    schedule = result.scalar_one_or_none()
    
    if not schedule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Active backup schedule {schedule_id} not found"
        )
    
    # Trigger backup task
    task = execute_scheduled_backup.delay(schedule_id)
    
    return {
        "message": f"Backup schedule {schedule_id} triggered",
        "task_id": task.id,
        "schedule_name": schedule.name
    }


# Manual Backup Operations
@router.post("/manual", response_model=Dict[str, Any])
async def create_manual_backup(
    *,
    db: AsyncSession = Depends(get_db),
    backup_request: ManualBackupRequest,
    current_user: User = Depends(get_admin_user)
):
    """Create a manual backup."""
    
    # Verify storage backend exists
    storage_stmt = select(StorageBackendConfig).where(
        StorageBackendConfig.id == backup_request.storage_backend_id,
        StorageBackendConfig.is_active is True
    )
    storage_result = await db.execute(storage_stmt)
    storage_backend = storage_result.scalar_one_or_none()
    
    if not storage_backend:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Storage backend {backup_request.storage_backend_id} not found"
        )
    
    # Prepare backup configuration
    backup_config = {
        "backup_type": backup_request.backup_type.value,
        "storage_backend": storage_backend.backend_type.value,
        "compression": backup_request.compression_type.value,
        "encrypt": backup_request.encrypt_backup,
        "verify_integrity": backup_request.verify_integrity,
        "retention_days": backup_request.retention_days,
        "include_patterns": backup_request.include_patterns or [],
        "exclude_patterns": backup_request.exclude_patterns or [],
        "max_parallel_uploads": backup_request.max_parallel_uploads
    }
    
    if backup_request.bandwidth_limit_mbps:
        backup_config["bandwidth_limit_mbps"] = backup_request.bandwidth_limit_mbps
    
    # Trigger backup task
    task = execute_manual_backup.delay(backup_config, current_user.id)
    
    return {
        "message": "Manual backup initiated",
        "task_id": task.id,
        "backup_type": backup_request.backup_type,
        "storage_backend": storage_backend.name
    }


# Backup History and Monitoring
@router.get("/history", response_model=List[Dict[str, Any]])
async def get_backup_history(
    *,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_admin_user),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=1000),
    status: Optional[BackupStatusEnum] = Query(default=None),
    backup_type: Optional[BackupTypeEnum] = Query(default=None),
    since: Optional[datetime] = Query(default=None),
    until: Optional[datetime] = Query(default=None)
):
    """Get backup execution history."""
    
    stmt = select(BackupExecution, StorageBackendConfig).join(
        StorageBackendConfig,
        BackupExecution.storage_backend_id == StorageBackendConfig.id
    )
    
    if status:
        stmt = stmt.where(BackupExecution.status == status)
    
    if backup_type:
        stmt = stmt.where(BackupExecution.backup_type == backup_type)
    
    if since:
        stmt = stmt.where(BackupExecution.started_at >= since)
    
    if until:
        stmt = stmt.where(BackupExecution.started_at <= until)
    
    stmt = stmt.offset(skip).limit(limit).order_by(BackupExecution.started_at.desc())
    
    result = await db.execute(stmt)
    backups_with_storage = result.all()
    
    return [
        {
            "id": backup.id,
            "backup_id": backup.backup_id,
            "backup_type": backup.backup_type,
            "status": backup.status,
            "triggered_by": backup.triggered_by,
            "storage_backend": storage.name,
            "started_at": backup.started_at.isoformat(),
            "completed_at": backup.completed_at.isoformat() if backup.completed_at else None,
            "duration_seconds": backup.duration_seconds,
            "size_bytes": backup.size_bytes,
            "compressed_size_bytes": backup.compressed_size_bytes,
            "compression_ratio": backup.compression_ratio,
            "included_components": backup.included_components,
            "verification_status": backup.verification_status,
            "error_message": backup.error_message
        }
        for backup, storage in backups_with_storage
    ]


@router.get("/history/{backup_id}", response_model=Dict[str, Any])
async def get_backup_details(
    *,
    db: AsyncSession = Depends(get_db),
    backup_id: str,
    current_user: User = Depends(get_admin_user)
):
    """Get detailed information about a specific backup."""
    
    stmt = select(BackupExecution, StorageBackendConfig).join(
        StorageBackendConfig,
        BackupExecution.storage_backend_id == StorageBackendConfig.id
    ).where(BackupExecution.backup_id == backup_id)
    
    result = await db.execute(stmt)
    backup_with_storage = result.first()
    
    if not backup_with_storage:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Backup {backup_id} not found"
        )
    
    backup, storage = backup_with_storage
    
    return {
        "id": backup.id,
        "backup_id": backup.backup_id,
        "backup_type": backup.backup_type,
        "status": backup.status,
        "triggered_by": backup.triggered_by,
        "trigger_user_id": backup.trigger_user_id,
        "schedule_id": backup.schedule_id,
        "storage_backend": {
            "id": storage.id,
            "name": storage.name,
            "backend_type": storage.backend_type
        },
        "started_at": backup.started_at.isoformat(),
        "completed_at": backup.completed_at.isoformat() if backup.completed_at else None,
        "duration_seconds": backup.duration_seconds,
        "size_bytes": backup.size_bytes,
        "compressed_size_bytes": backup.compressed_size_bytes,
        "compression_ratio": backup.compression_ratio,
        "included_components": backup.included_components,
        "storage_location": backup.storage_location,
        "checksum": backup.checksum,
        "verification_status": backup.verification_status,
        "verified_at": backup.verified_at.isoformat() if backup.verified_at else None,
        "error_message": backup.error_message,
        "warnings": backup.warnings,
        "backup_config": backup.backup_config,
        "created_at": backup.created_at.isoformat()
    }


@router.post("/history/{backup_id}/verify", response_model=Dict[str, Any])
async def verify_backup(
    *,
    db: AsyncSession = Depends(get_db),
    backup_id: str,
    current_user: User = Depends(get_admin_user)
):
    """Verify backup integrity."""
    
    # Get backup execution record
    stmt = select(BackupExecution).where(BackupExecution.backup_id == backup_id)
    result = await db.execute(stmt)
    backup = result.scalar_one_or_none()
    
    if not backup:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Backup {backup_id} not found"
        )
    
    if backup.status != BackupStatusEnum.COMPLETED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot verify backup with status {backup.status}"
        )
    
    # Trigger verification task
    task = verify_backup_integrity.delay(backup.id)
    
    return {
        "message": f"Backup verification initiated for {backup_id}",
        "task_id": task.id,
        "backup_id": backup_id
    }


# Recovery Operations
@router.post("/recovery", response_model=Dict[str, Any])
async def initiate_recovery(
    *,
    db: AsyncSession = Depends(get_db),
    recovery_request: RecoveryRequest,
    current_user: User = Depends(get_admin_user)
):
    """Initiate a recovery operation."""
    
    # Verify backup exists
    backup_stmt = select(BackupExecution).where(
        BackupExecution.backup_id == recovery_request.backup_id,
        BackupExecution.status == BackupStatusEnum.COMPLETED
    )
    backup_result = await db.execute(backup_stmt)
    backup = backup_result.scalar_one_or_none()
    
    if not backup:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Completed backup {recovery_request.backup_id} not found"
        )
    
    # Verify storage backend exists
    storage_stmt = select(StorageBackendConfig).where(
        StorageBackendConfig.id == recovery_request.storage_backend_id,
        StorageBackendConfig.is_active is True
    )
    storage_result = await db.execute(storage_stmt)
    storage_backend = storage_result.scalar_one_or_none()
    
    if not storage_backend:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Storage backend {recovery_request.storage_backend_id} not found"
        )
    
    # Prepare recovery configuration
    recovery_config = {
        "recovery_type": recovery_request.recovery_type.value,
        "backup_id": recovery_request.backup_id,
        "storage_backend": storage_backend.backend_type.value,
        "restore_target": recovery_request.restore_target,
        "validate_after_restore": recovery_request.validate_after_restore,
        "create_backup_before_restore": recovery_request.create_backup_before_restore,
        "skip_existing_files": recovery_request.skip_existing_files,
        "restore_permissions": recovery_request.restore_permissions
    }
    
    if recovery_request.target_timestamp:
        recovery_config["target_timestamp"] = recovery_request.target_timestamp.isoformat()
    
    if recovery_request.restore_components:
        recovery_config["restore_components"] = recovery_request.restore_components
    
    if recovery_request.custom_restore_path:
        recovery_config["custom_restore_path"] = recovery_request.custom_restore_path
    
    # Trigger recovery task
    task = execute_recovery.delay(recovery_config, current_user.id)
    
    return {
        "message": f"Recovery operation initiated for backup {recovery_request.backup_id}",
        "task_id": task.id,
        "recovery_type": recovery_request.recovery_type,
        "backup_id": recovery_request.backup_id
    }


@router.get("/recovery/history", response_model=List[Dict[str, Any]])
async def get_recovery_history(
    *,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_admin_user),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=1000),
    status: Optional[RecoveryStatusEnum] = Query(default=None),
    recovery_type: Optional[RecoveryTypeEnum] = Query(default=None)
):
    """Get recovery operation history."""
    
    stmt = select(RecoveryExecution)
    
    if status:
        stmt = stmt.where(RecoveryExecution.status == status)
    
    if recovery_type:
        stmt = stmt.where(RecoveryExecution.recovery_type == recovery_type)
    
    stmt = stmt.offset(skip).limit(limit).order_by(RecoveryExecution.started_at.desc())
    
    result = await db.execute(stmt)
    recoveries = result.scalars().all()
    
    return [
        {
            "id": recovery.id,
            "recovery_id": recovery.recovery_id,
            "recovery_type": recovery.recovery_type,
            "source_backup_id": recovery.source_backup_id,
            "status": recovery.status,
            "triggered_by": recovery.triggered_by,
            "target_system": recovery.target_system,
            "started_at": recovery.started_at.isoformat(),
            "completed_at": recovery.completed_at.isoformat() if recovery.completed_at else None,
            "duration_seconds": recovery.duration_seconds,
            "restored_components": recovery.restored_components,
            "validation_performed": recovery.validation_performed,
            "validation_passed": recovery.validation_passed,
            "error_message": recovery.error_message
        }
        for recovery in recoveries
    ]


# Storage Backend Management
@router.post("/storage-backends", response_model=Dict[str, Any])
async def create_storage_backend(
    *,
    db: AsyncSession = Depends(get_db),
    backend_data: StorageBackendConfigCreate,
    current_user: User = Depends(get_admin_user)
):
    """Create storage backend configuration."""
    
    storage_backend = StorageBackendConfig(
        **backend_data.model_dump()
    )
    
    db.add(storage_backend)
    await db.commit()
    await db.refresh(storage_backend)
    
    return {
        "id": storage_backend.id,
        "name": storage_backend.name,
        "backend_type": storage_backend.backend_type,
        "is_active": storage_backend.is_active,
        "is_healthy": storage_backend.is_healthy
    }


@router.get("/storage-backends", response_model=List[Dict[str, Any]])
async def list_storage_backends(
    *,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_admin_user),
    active_only: bool = Query(default=False)
):
    """List storage backend configurations."""
    
    stmt = select(StorageBackendConfig)
    
    if active_only:
        stmt = stmt.where(StorageBackendConfig.is_active is True)
    
    result = await db.execute(stmt)
    backends = result.scalars().all()
    
    return [
        {
            "id": backend.id,
            "name": backend.name,
            "backend_type": backend.backend_type,
            "is_active": backend.is_active,
            "is_healthy": backend.is_healthy,
            "last_health_check": backend.last_health_check.isoformat() if backend.last_health_check else None,
            "total_backups": backend.total_backups,
            "total_size_bytes": backend.total_size_bytes,
            "description": backend.description,
            "created_at": backend.created_at.isoformat()
        }
        for backend in backends
    ]


# Health and Monitoring
@router.get("/health", response_model=Dict[str, Any])
async def get_backup_system_health(
    *,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_admin_user)
):
    """Get backup system health status."""
    
    # Trigger health check task and wait for result
    task = health_check_backups.delay()
    
    return {
        "message": "Health check initiated",
        "task_id": task.id
    }


@router.get("/statistics", response_model=Dict[str, Any])
async def get_backup_statistics(
    *,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_admin_user),
    days: int = Query(default=30, ge=1, le=365)
):
    """Get backup system statistics."""
    
    since_date = datetime.utcnow() - timedelta(days=days)
    
    # Get backup statistics
    backup_stats_stmt = select(
        func.count(BackupExecution.id).label("total_backups"),
        func.sum(
            func.case(
                (BackupExecution.status == BackupStatusEnum.COMPLETED, 1),
                else_=0
            )
        ).label("successful_backups"),
        func.sum(BackupExecution.size_bytes).label("total_size_bytes"),
        func.avg(BackupExecution.duration_seconds).label("avg_duration_seconds")
    ).where(BackupExecution.started_at >= since_date)
    
    backup_stats_result = await db.execute(backup_stats_stmt)
    backup_stats = backup_stats_result.first()
    
    # Get storage backend statistics
    storage_stats_stmt = select(
        StorageBackendConfig.backend_type,
        func.count(BackupExecution.id).label("backup_count"),
        func.sum(BackupExecution.size_bytes).label("total_size")
    ).select_from(
        BackupExecution.__table__.join(
            StorageBackendConfig.__table__,
            BackupExecution.storage_backend_id == StorageBackendConfig.id
        )
    ).where(
        BackupExecution.started_at >= since_date
    ).group_by(StorageBackendConfig.backend_type)
    
    storage_stats_result = await db.execute(storage_stats_stmt)
    storage_stats = storage_stats_result.all()
    
    # Get recent failures
    recent_failures_stmt = select(BackupExecution).where(
        and_(
            BackupExecution.status == BackupStatusEnum.FAILED,
            BackupExecution.started_at >= since_date
        )
    ).order_by(BackupExecution.started_at.desc()).limit(10)
    
    recent_failures_result = await db.execute(recent_failures_stmt)
    recent_failures = recent_failures_result.scalars().all()
    
    return {
        "period_days": days,
        "backup_statistics": {
            "total_backups": backup_stats.total_backups or 0,
            "successful_backups": backup_stats.successful_backups or 0,
            "success_rate": (backup_stats.successful_backups or 0) / max(backup_stats.total_backups or 1, 1),
            "total_size_bytes": backup_stats.total_size_bytes or 0,
            "average_duration_seconds": float(backup_stats.avg_duration_seconds or 0)
        },
        "storage_backend_statistics": [
            {
                "backend_type": stat.backend_type,
                "backup_count": stat.backup_count,
                "total_size_bytes": stat.total_size
            }
            for stat in storage_stats
        ],
        "recent_failures": [
            {
                "backup_id": failure.backup_id,
                "started_at": failure.started_at.isoformat(),
                "error_message": failure.error_message
            }
            for failure in recent_failures
        ]
    }


# Cleanup and Maintenance
@router.post("/cleanup", response_model=Dict[str, Any])
async def trigger_backup_cleanup(
    *,
    db: AsyncSession = Depends(get_db),
    retention_policy_id: int = Body(..., embed=True),
    current_user: User = Depends(get_admin_user)
):
    """Trigger backup cleanup based on retention policy."""
    
    # Verify retention policy exists
    policy_stmt = select(BackupRetentionPolicy).where(
        BackupRetentionPolicy.id == retention_policy_id,
        BackupRetentionPolicy.is_active is True
    )
    policy_result = await db.execute(policy_stmt)
    policy = policy_result.scalar_one_or_none()
    
    if not policy:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Retention policy {retention_policy_id} not found"
        )
    
    # Trigger cleanup task
    task = cleanup_old_backups.delay(retention_policy_id)
    
    return {
        "message": f"Backup cleanup initiated for policy {policy.name}",
        "task_id": task.id,
        "retention_policy_id": retention_policy_id
    }