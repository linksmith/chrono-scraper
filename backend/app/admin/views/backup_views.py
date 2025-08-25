"""
Admin interface views for backup and recovery management.

This module provides web-based admin interface for:
- Managing backup schedules and configurations
- Monitoring backup execution status and history
- Configuring storage backends and retention policies
- Managing recovery operations
- Viewing backup statistics and health monitoring
- System maintenance and troubleshooting
"""

from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from fastapi import Request, Depends, HTTPException, Form, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select, func, and_, or_
import json

from app.core.database import get_db
from app.core.admin_auth import get_admin_user_backup as get_admin_user
from app.models.user import User
from app.models.backup import (
    BackupSchedule, BackupExecution, RecoveryExecution,
    StorageBackendConfig, BackupRetentionPolicy, BackupCleanupHistory,
    BackupHealthCheck, BackupAuditLog, BackupTypeEnum, BackupStatusEnum,
    StorageBackendEnum, CompressionTypeEnum, RecoveryStatusEnum
)
from app.tasks.backup_tasks import (
    execute_scheduled_backup, execute_manual_backup, execute_recovery,
    verify_backup_integrity, cleanup_old_backups, health_check_backups
)
from app.admin.config import admin_templates


async def render_backup_dashboard(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_admin_user)
) -> HTMLResponse:
    """Render the main backup dashboard."""
    
    # Get backup statistics for the last 30 days
    since_date = datetime.utcnow() - timedelta(days=30)
    
    # Total backups and success rate
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
    
    # Active schedules
    active_schedules_stmt = select(func.count(BackupSchedule.id)).where(
        BackupSchedule.is_active == True
    )
    active_schedules_result = await db.execute(active_schedules_stmt)
    active_schedules_count = active_schedules_result.scalar()
    
    # Storage backends
    storage_backends_stmt = select(StorageBackendConfig).where(
        StorageBackendConfig.is_active == True
    )
    storage_backends_result = await db.execute(storage_backends_stmt)
    storage_backends = storage_backends_result.scalars().all()
    
    # Recent backup executions
    recent_backups_stmt = select(BackupExecution, StorageBackendConfig).join(
        StorageBackendConfig,
        BackupExecution.storage_backend_id == StorageBackendConfig.id
    ).order_by(BackupExecution.started_at.desc()).limit(10)
    
    recent_backups_result = await db.execute(recent_backups_stmt)
    recent_backups = recent_backups_result.all()
    
    # Recent recoveries
    recent_recoveries_stmt = select(RecoveryExecution).order_by(
        RecoveryExecution.started_at.desc()
    ).limit(5)
    
    recent_recoveries_result = await db.execute(recent_recoveries_stmt)
    recent_recoveries = recent_recoveries_result.scalars().all()
    
    # Calculate metrics
    total_backups = backup_stats.total_backups or 0
    successful_backups = backup_stats.successful_backups or 0
    success_rate = successful_backups / max(total_backups, 1)
    total_size_gb = (backup_stats.total_size_bytes or 0) / (1024 ** 3)
    avg_duration_minutes = (backup_stats.avg_duration_seconds or 0) / 60
    
    context = {
        "request": request,
        "user": current_user,
        "page_title": "Backup & Recovery Dashboard",
        "stats": {
            "total_backups": total_backups,
            "successful_backups": successful_backups,
            "success_rate": success_rate,
            "total_size_gb": round(total_size_gb, 2),
            "avg_duration_minutes": round(avg_duration_minutes, 1),
            "active_schedules": active_schedules_count,
            "storage_backends": len(storage_backends)
        },
        "recent_backups": [
            {
                "backup_id": backup.backup_id,
                "backup_type": backup.backup_type.value,
                "status": backup.status.value,
                "storage_backend": storage.name,
                "started_at": backup.started_at,
                "duration_minutes": backup.duration_seconds / 60 if backup.duration_seconds else 0,
                "size_mb": backup.size_bytes / (1024 ** 2) if backup.size_bytes else 0,
                "status_class": get_status_class(backup.status.value)
            }
            for backup, storage in recent_backups
        ],
        "recent_recoveries": [
            {
                "recovery_id": recovery.recovery_id,
                "recovery_type": recovery.recovery_type.value,
                "source_backup_id": recovery.source_backup_id,
                "status": recovery.status.value,
                "started_at": recovery.started_at,
                "duration_minutes": recovery.duration_seconds / 60 if recovery.duration_seconds else 0,
                "status_class": get_status_class(recovery.status.value)
            }
            for recovery in recent_recoveries
        ],
        "storage_backends": [
            {
                "name": backend.name,
                "backend_type": backend.backend_type.value,
                "is_healthy": backend.is_healthy,
                "total_backups": backend.total_backups,
                "total_size_gb": backend.total_size_bytes / (1024 ** 3) if backend.total_size_bytes else 0
            }
            for backend in storage_backends
        ]
    }
    
    return admin_templates.TemplateResponse("backup_dashboard.html", context)


async def render_backup_schedules(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_admin_user)
) -> HTMLResponse:
    """Render backup schedules management page."""
    
    # Get all backup schedules with storage backend info
    schedules_stmt = select(BackupSchedule, StorageBackendConfig).join(
        StorageBackendConfig,
        BackupSchedule.storage_backend_id == StorageBackendConfig.id
    ).order_by(BackupSchedule.created_at.desc())
    
    schedules_result = await db.execute(schedules_stmt)
    schedules_with_storage = schedules_result.all()
    
    # Get available storage backends for form
    storage_backends_stmt = select(StorageBackendConfig).where(
        StorageBackendConfig.is_active == True
    )
    storage_backends_result = await db.execute(storage_backends_stmt)
    storage_backends = storage_backends_result.scalars().all()
    
    context = {
        "request": request,
        "user": current_user,
        "page_title": "Backup Schedules",
        "schedules": [
            {
                "id": schedule.id,
                "name": schedule.name,
                "backup_type": schedule.backup_type.value,
                "cron_expression": schedule.cron_expression,
                "storage_backend": storage.name,
                "is_active": schedule.is_active,
                "last_run_at": schedule.last_run_at,
                "next_run_at": schedule.next_run_at,
                "total_runs": schedule.total_runs,
                "success_rate": schedule.successful_runs / max(schedule.total_runs, 1),
                "retention_days": schedule.retention_days,
                "created_at": schedule.created_at
            }
            for schedule, storage in schedules_with_storage
        ],
        "storage_backends": [
            {
                "id": backend.id,
                "name": backend.name,
                "backend_type": backend.backend_type.value
            }
            for backend in storage_backends
        ],
        "backup_types": [e.value for e in BackupTypeEnum],
        "compression_types": [e.value for e in CompressionTypeEnum]
    }
    
    return admin_templates.TemplateResponse("backup_schedules.html", context)


async def render_backup_history(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_admin_user),
    page: int = 1,
    status: Optional[str] = None,
    backup_type: Optional[str] = None,
    days: int = 30
) -> HTMLResponse:
    """Render backup execution history."""
    
    page_size = 50
    offset = (page - 1) * page_size
    since_date = datetime.utcnow() - timedelta(days=days)
    
    # Build query
    stmt = select(BackupExecution, StorageBackendConfig).join(
        StorageBackendConfig,
        BackupExecution.storage_backend_id == StorageBackendConfig.id
    ).where(BackupExecution.started_at >= since_date)
    
    if status:
        stmt = stmt.where(BackupExecution.status == BackupStatusEnum(status))
    
    if backup_type:
        stmt = stmt.where(BackupExecution.backup_type == BackupTypeEnum(backup_type))
    
    # Get total count for pagination
    count_stmt = select(func.count(BackupExecution.id)).where(
        BackupExecution.started_at >= since_date
    )
    if status:
        count_stmt = count_stmt.where(BackupExecution.status == BackupStatusEnum(status))
    if backup_type:
        count_stmt = count_stmt.where(BackupExecution.backup_type == BackupTypeEnum(backup_type))
    
    count_result = await db.execute(count_stmt)
    total_count = count_result.scalar()
    
    # Get paginated results
    stmt = stmt.offset(offset).limit(page_size).order_by(BackupExecution.started_at.desc())
    
    result = await db.execute(stmt)
    backups_with_storage = result.all()
    
    # Calculate pagination info
    total_pages = (total_count + page_size - 1) // page_size
    
    context = {
        "request": request,
        "user": current_user,
        "page_title": "Backup History",
        "backups": [
            {
                "id": backup.id,
                "backup_id": backup.backup_id,
                "backup_type": backup.backup_type.value,
                "status": backup.status.value,
                "triggered_by": backup.triggered_by,
                "storage_backend": storage.name,
                "started_at": backup.started_at,
                "completed_at": backup.completed_at,
                "duration_minutes": backup.duration_seconds / 60 if backup.duration_seconds else 0,
                "size_mb": backup.size_bytes / (1024 ** 2) if backup.size_bytes else 0,
                "compression_ratio": backup.compression_ratio,
                "verification_status": backup.verification_status,
                "error_message": backup.error_message,
                "status_class": get_status_class(backup.status.value)
            }
            for backup, storage in backups_with_storage
        ],
        "pagination": {
            "current_page": page,
            "total_pages": total_pages,
            "total_count": total_count,
            "has_prev": page > 1,
            "has_next": page < total_pages,
            "prev_page": page - 1 if page > 1 else None,
            "next_page": page + 1 if page < total_pages else None
        },
        "filters": {
            "status": status,
            "backup_type": backup_type,
            "days": days
        },
        "backup_statuses": [e.value for e in BackupStatusEnum],
        "backup_types": [e.value for e in BackupTypeEnum]
    }
    
    return admin_templates.TemplateResponse("backup_history.html", context)


async def render_storage_backends(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_admin_user)
) -> HTMLResponse:
    """Render storage backends management page."""
    
    # Get all storage backends
    backends_stmt = select(StorageBackendConfig).order_by(StorageBackendConfig.created_at.desc())
    backends_result = await db.execute(backends_stmt)
    backends = backends_result.scalars().all()
    
    context = {
        "request": request,
        "user": current_user,
        "page_title": "Storage Backends",
        "backends": [
            {
                "id": backend.id,
                "name": backend.name,
                "backend_type": backend.backend_type.value,
                "is_active": backend.is_active,
                "is_healthy": backend.is_healthy,
                "last_health_check": backend.last_health_check,
                "total_backups": backend.total_backups,
                "total_size_gb": backend.total_size_bytes / (1024 ** 3) if backend.total_size_bytes else 0,
                "description": backend.description,
                "created_at": backend.created_at
            }
            for backend in backends
        ],
        "backend_types": [e.value for e in StorageBackendEnum]
    }
    
    return admin_templates.TemplateResponse("storage_backends.html", context)


async def render_recovery_operations(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_admin_user)
) -> HTMLResponse:
    """Render recovery operations page."""
    
    # Get recent recovery operations
    recoveries_stmt = select(RecoveryExecution).order_by(
        RecoveryExecution.started_at.desc()
    ).limit(50)
    
    recoveries_result = await db.execute(recoveries_stmt)
    recoveries = recoveries_result.scalars().all()
    
    # Get available backups for recovery
    available_backups_stmt = select(BackupExecution, StorageBackendConfig).join(
        StorageBackendConfig,
        BackupExecution.storage_backend_id == StorageBackendConfig.id
    ).where(
        BackupExecution.status == BackupStatusEnum.COMPLETED
    ).order_by(BackupExecution.started_at.desc()).limit(20)
    
    available_backups_result = await db.execute(available_backups_stmt)
    available_backups = available_backups_result.all()
    
    context = {
        "request": request,
        "user": current_user,
        "page_title": "Recovery Operations",
        "recoveries": [
            {
                "id": recovery.id,
                "recovery_id": recovery.recovery_id,
                "recovery_type": recovery.recovery_type.value,
                "source_backup_id": recovery.source_backup_id,
                "status": recovery.status.value,
                "triggered_by": recovery.triggered_by,
                "target_system": recovery.target_system,
                "started_at": recovery.started_at,
                "completed_at": recovery.completed_at,
                "duration_minutes": recovery.duration_seconds / 60 if recovery.duration_seconds else 0,
                "restored_components": recovery.restored_components,
                "validation_performed": recovery.validation_performed,
                "validation_passed": recovery.validation_passed,
                "error_message": recovery.error_message,
                "status_class": get_status_class(recovery.status.value)
            }
            for recovery in recoveries
        ],
        "available_backups": [
            {
                "backup_id": backup.backup_id,
                "backup_type": backup.backup_type.value,
                "storage_backend": storage.name,
                "created_at": backup.started_at,
                "size_mb": backup.size_bytes / (1024 ** 2) if backup.size_bytes else 0
            }
            for backup, storage in available_backups
        ],
        "recovery_types": [
            {"value": "full_restore", "label": "Full System Restore"},
            {"value": "database_only", "label": "Database Only"},
            {"value": "files_only", "label": "Files Only"},
            {"value": "configuration_only", "label": "Configuration Only"},
            {"value": "selective_restore", "label": "Selective Restore"}
        ]
    }
    
    return admin_templates.TemplateResponse("recovery_operations.html", context)


async def render_system_health(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_admin_user)
) -> HTMLResponse:
    """Render backup system health monitoring page."""
    
    # Get recent health checks
    health_checks_stmt = select(BackupHealthCheck).order_by(
        BackupHealthCheck.checked_at.desc()
    ).limit(10)
    
    health_checks_result = await db.execute(health_checks_stmt)
    health_checks = health_checks_result.scalars().all()
    
    # Get recent audit logs
    audit_logs_stmt = select(BackupAuditLog).order_by(
        BackupAuditLog.created_at.desc()
    ).limit(20)
    
    audit_logs_result = await db.execute(audit_logs_stmt)
    audit_logs = audit_logs_result.scalars().all()
    
    # Get recent cleanup history
    cleanup_history_stmt = select(BackupCleanupHistory).order_by(
        BackupCleanupHistory.started_at.desc()
    ).limit(10)
    
    cleanup_history_result = await db.execute(cleanup_history_stmt)
    cleanup_history = cleanup_history_result.scalars().all()
    
    context = {
        "request": request,
        "user": current_user,
        "page_title": "System Health & Monitoring",
        "health_checks": [
            {
                "check_id": check.check_id,
                "check_type": check.check_type,
                "status": check.status,
                "checked_at": check.checked_at,
                "health_score": check.health_score,
                "issues_found": check.issues_found or [],
                "recommendations": check.recommendations or [],
                "status_class": get_status_class(check.status)
            }
            for check in health_checks
        ],
        "audit_logs": [
            {
                "audit_id": log.audit_id,
                "event_type": log.event_type,
                "event_category": log.event_category,
                "username": log.username or "System",
                "action": log.action,
                "status": log.status,
                "created_at": log.created_at,
                "risk_level": log.risk_level,
                "status_class": get_status_class(log.status)
            }
            for log in audit_logs
        ],
        "cleanup_history": [
            {
                "cleanup_id": cleanup.cleanup_id,
                "started_at": cleanup.started_at,
                "completed_at": cleanup.completed_at,
                "backups_evaluated": cleanup.backups_evaluated,
                "backups_deleted": cleanup.backups_deleted,
                "space_freed_gb": cleanup.space_freed_bytes / (1024 ** 3) if cleanup.space_freed_bytes else 0,
                "status": cleanup.status,
                "status_class": get_status_class(cleanup.status)
            }
            for cleanup in cleanup_history
        ]
    }
    
    return admin_templates.TemplateResponse("backup_health.html", context)


# Form handlers
async def create_backup_schedule_handler(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_admin_user),
    name: str = Form(...),
    cron_expression: str = Form(...),
    backup_type: str = Form(...),
    storage_backend_id: int = Form(...),
    compression_type: str = Form(default="gzip"),
    encrypt_backup: bool = Form(default=True),
    verify_integrity: bool = Form(default=True),
    retention_days: int = Form(default=30),
    description: str = Form(default="")
) -> RedirectResponse:
    """Handle backup schedule creation form."""
    
    try:
        schedule = BackupSchedule(
            name=name,
            cron_expression=cron_expression,
            backup_type=BackupTypeEnum(backup_type),
            storage_backend_id=storage_backend_id,
            compression_type=CompressionTypeEnum(compression_type),
            encrypt_backup=encrypt_backup,
            verify_integrity=verify_integrity,
            retention_days=retention_days,
            description=description,
            next_run_at=datetime.utcnow() + timedelta(hours=1)
        )
        
        db.add(schedule)
        await db.commit()
        
        return RedirectResponse(
            url="/admin/backup/schedules?success=Schedule created successfully",
            status_code=status.HTTP_302_FOUND
        )
    
    except Exception as e:
        return RedirectResponse(
            url=f"/admin/backup/schedules?error=Failed to create schedule: {str(e)}",
            status_code=status.HTTP_302_FOUND
        )


async def trigger_manual_backup_handler(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_admin_user),
    backup_type: str = Form(...),
    storage_backend_id: int = Form(...),
    compression_type: str = Form(default="gzip"),
    encrypt_backup: bool = Form(default=True)
) -> RedirectResponse:
    """Handle manual backup trigger form."""
    
    try:
        # Get storage backend info
        storage_stmt = select(StorageBackendConfig).where(
            StorageBackendConfig.id == storage_backend_id
        )
        storage_result = await db.execute(storage_stmt)
        storage_backend = storage_result.scalar_one_or_none()
        
        if not storage_backend:
            raise Exception(f"Storage backend {storage_backend_id} not found")
        
        backup_config = {
            "backup_type": backup_type,
            "storage_backend": storage_backend.backend_type.value,
            "compression": compression_type,
            "encrypt": encrypt_backup,
            "verify_integrity": True,
            "retention_days": 30
        }
        
        # Trigger backup task
        task = execute_manual_backup.delay(backup_config, current_user.id)
        
        return RedirectResponse(
            url=f"/admin/backup/history?success=Manual backup initiated (Task ID: {task.id})",
            status_code=status.HTTP_302_FOUND
        )
    
    except Exception as e:
        return RedirectResponse(
            url=f"/admin/backup?error=Failed to start manual backup: {str(e)}",
            status_code=status.HTTP_302_FOUND
        )


def get_status_class(status: str) -> str:
    """Get CSS class for status display."""
    status_classes = {
        "completed": "success",
        "verified": "success", 
        "healthy": "success",
        "success": "success",
        "running": "warning",
        "pending": "info",
        "verifying": "info",
        "warning": "warning",
        "failed": "danger",
        "error": "danger",
        "corrupted": "danger",
        "critical": "danger",
        "cancelled": "secondary"
    }
    return status_classes.get(status.lower(), "secondary")