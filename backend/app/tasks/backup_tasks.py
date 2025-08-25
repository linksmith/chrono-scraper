"""
Celery tasks for backup and recovery operations.

This module provides:
- Scheduled backup execution
- Manual backup triggers
- Backup verification and integrity checking
- Cleanup and retention management
- Health monitoring and alerting
- Recovery operation management
"""

import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from celery import Task
from celery.utils.log import get_task_logger
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.tasks.celery_app import celery_app
from app.core.database import get_db
from app.services.backup_service import (
    BackupService, backup_service, BackupConfig, BackupType, 
    StorageBackend, CompressionType
)
from app.services.recovery_service import (
    RecoveryService, recovery_service, RecoveryConfig, RecoveryType
)
from app.models.backup import (
    BackupSchedule, BackupExecution, RecoveryExecution, 
    BackupRetentionPolicy, BackupCleanupHistory, BackupHealthCheck,
    BackupAuditLog, BackupStatusEnum, RecoveryStatusEnum,
    StorageBackendConfig
)
from app.services.monitoring import MonitoringService
from app.core.email_service import EmailService


logger = get_task_logger(__name__)


class BackupTaskBase(Task):
    """Base class for backup tasks with common functionality."""
    
    def __init__(self):
        self.monitoring = MonitoringService()
        self.email_service = EmailService()
    
    async def log_audit_event(self, event_type: str, event_data: Dict[str, Any], 
                             user_id: Optional[int] = None, status: str = "success"):
        """Log backup audit event."""
        try:
            async for db in get_db():
                audit_log = BackupAuditLog(
                    audit_id=f"audit_{datetime.utcnow().strftime('%Y%m%d_%H%M%S_%f')}",
                    event_type=event_type,
                    event_category="backup",
                    user_id=user_id,
                    action="execute",
                    status=status,
                    event_data=event_data
                )
                db.add(audit_log)
                await db.commit()
                break
        except Exception as e:
            logger.error(f"Failed to log audit event: {e}")
    
    async def send_notification(self, subject: str, message: str, 
                              notification_type: str = "info"):
        """Send backup notification email."""
        try:
            # This would integrate with your notification system
            logger.info(f"Notification [{notification_type}]: {subject} - {message}")
        except Exception as e:
            logger.error(f"Failed to send notification: {e}")


@celery_app.task(bind=True, base=BackupTaskBase)
def execute_scheduled_backup(self, schedule_id: int) -> Dict[str, Any]:
    """Execute a scheduled backup."""
    return asyncio.run(self._execute_scheduled_backup(schedule_id))


async def _execute_scheduled_backup(self, schedule_id: int) -> Dict[str, Any]:
    """Async implementation of scheduled backup execution."""
    start_time = datetime.utcnow()
    
    try:
        # Initialize services
        await backup_service.initialize()
        
        # Get backup schedule
        async for db in get_db():
            stmt = select(BackupSchedule).where(
                BackupSchedule.id == schedule_id,
                BackupSchedule.is_active == True
            )
            result = await db.execute(stmt)
            schedule = result.scalar_one_or_none()
            
            if not schedule:
                return {
                    "success": False,
                    "error": f"Schedule {schedule_id} not found or inactive"
                }
            
            # Get storage backend config
            storage_stmt = select(StorageBackendConfig).where(
                StorageBackendConfig.id == schedule.storage_backend_id,
                StorageBackendConfig.is_active == True
            )
            storage_result = await db.execute(storage_stmt)
            storage_config = storage_result.scalar_one_or_none()
            
            if not storage_config:
                return {
                    "success": False,
                    "error": f"Storage backend {schedule.storage_backend_id} not found or inactive"
                }
            
            # Create backup execution record
            backup_execution = BackupExecution(
                backup_id=f"scheduled_{schedule_id}_{start_time.strftime('%Y%m%d_%H%M%S')}",
                schedule_id=schedule_id,
                storage_backend_id=schedule.storage_backend_id,
                backup_type=schedule.backup_type,
                triggered_by="schedule",
                started_at=start_time,
                status=BackupStatusEnum.PENDING,
                included_components=[]
            )
            
            db.add(backup_execution)
            await db.commit()
            await db.refresh(backup_execution)
            
            try:
                # Update status to running
                backup_execution.status = BackupStatusEnum.RUNNING
                await db.commit()
                
                # Create backup configuration
                backup_config = BackupConfig(
                    backup_type=BackupType(schedule.backup_type.value),
                    storage_backend=StorageBackend(storage_config.backend_type.value),
                    compression=CompressionType(schedule.compression_type.value),
                    encrypt=schedule.encrypt_backup,
                    verify_integrity=schedule.verify_integrity,
                    retention_days=schedule.retention_days,
                    max_parallel_uploads=schedule.max_parallel_uploads,
                    include_patterns=schedule.include_patterns or [],
                    exclude_patterns=schedule.exclude_patterns or []
                )
                
                if schedule.bandwidth_limit_mbps:
                    backup_config.bandwidth_limit_mbps = schedule.bandwidth_limit_mbps
                
                # Execute backup
                backup_metadata = await backup_service.create_full_backup(backup_config)
                
                # Update execution record with results
                backup_execution.status = BackupStatusEnum(backup_metadata.status.value)
                backup_execution.completed_at = backup_metadata.completed_at
                backup_execution.size_bytes = backup_metadata.size_bytes
                backup_execution.compressed_size_bytes = backup_metadata.compressed_size_bytes
                backup_execution.compression_ratio = (
                    backup_metadata.size_bytes / backup_metadata.compressed_size_bytes 
                    if backup_metadata.compressed_size_bytes > 0 else 1.0
                )
                backup_execution.included_components = backup_metadata.included_components
                backup_execution.storage_location = backup_metadata.storage_location
                backup_execution.checksum = backup_metadata.checksum
                backup_execution.verification_status = backup_metadata.verification_status
                backup_execution.error_message = backup_metadata.error_message
                
                if backup_execution.completed_at:
                    backup_execution.duration_seconds = int(
                        (backup_execution.completed_at - backup_execution.started_at).total_seconds()
                    )
                
                # Update schedule statistics
                schedule.total_runs += 1
                schedule.last_run_at = start_time
                schedule.last_status = backup_execution.status.value
                
                if backup_execution.status == BackupStatusEnum.COMPLETED:
                    schedule.successful_runs += 1
                else:
                    schedule.failed_runs += 1
                
                await db.commit()
                
                # Log audit event
                await self.log_audit_event(
                    "scheduled_backup_completed",
                    {
                        "schedule_id": schedule_id,
                        "backup_id": backup_execution.backup_id,
                        "status": backup_execution.status.value,
                        "size_bytes": backup_execution.size_bytes,
                        "duration_seconds": backup_execution.duration_seconds
                    },
                    status="success" if backup_execution.status == BackupStatusEnum.COMPLETED else "failure"
                )
                
                # Send notification if backup failed
                if backup_execution.status != BackupStatusEnum.COMPLETED:
                    await self.send_notification(
                        f"Backup Failed: {schedule.name}",
                        f"Scheduled backup {backup_execution.backup_id} failed: {backup_execution.error_message}",
                        "error"
                    )
                
                return {
                    "success": backup_execution.status == BackupStatusEnum.COMPLETED,
                    "backup_id": backup_execution.backup_id,
                    "status": backup_execution.status.value,
                    "size_bytes": backup_execution.size_bytes,
                    "duration_seconds": backup_execution.duration_seconds,
                    "components": backup_execution.included_components
                }
            
            except Exception as e:
                # Update execution record with error
                backup_execution.status = BackupStatusEnum.FAILED
                backup_execution.completed_at = datetime.utcnow()
                backup_execution.error_message = str(e)
                backup_execution.duration_seconds = int(
                    (backup_execution.completed_at - backup_execution.started_at).total_seconds()
                )
                
                schedule.total_runs += 1
                schedule.failed_runs += 1
                schedule.last_run_at = start_time
                schedule.last_status = "failed"
                
                await db.commit()
                
                await self.log_audit_event(
                    "scheduled_backup_failed",
                    {
                        "schedule_id": schedule_id,
                        "backup_id": backup_execution.backup_id,
                        "error": str(e)
                    },
                    status="failure"
                )
                
                raise
            
            break  # Exit the async for loop
    
    except Exception as e:
        logger.error(f"Scheduled backup {schedule_id} failed: {e}")
        return {
            "success": False,
            "error": str(e)
        }


@celery_app.task(bind=True, base=BackupTaskBase)
def execute_manual_backup(self, backup_config: Dict[str, Any], user_id: Optional[int] = None) -> Dict[str, Any]:
    """Execute a manual backup."""
    return asyncio.run(self._execute_manual_backup(backup_config, user_id))


async def _execute_manual_backup(self, backup_config_data: Dict[str, Any], user_id: Optional[int] = None) -> Dict[str, Any]:
    """Async implementation of manual backup execution."""
    start_time = datetime.utcnow()
    
    try:
        await backup_service.initialize()
        
        # Parse backup configuration
        backup_config = BackupConfig(
            backup_type=BackupType(backup_config_data["backup_type"]),
            storage_backend=StorageBackend(backup_config_data["storage_backend"]),
            compression=CompressionType(backup_config_data.get("compression", "gzip")),
            encrypt=backup_config_data.get("encrypt", True),
            verify_integrity=backup_config_data.get("verify_integrity", True),
            retention_days=backup_config_data.get("retention_days", 30)
        )
        
        # Create backup execution record
        async for db in get_db():
            # Get storage backend config
            storage_stmt = select(StorageBackendConfig).where(
                StorageBackendConfig.backend_type == backup_config.storage_backend,
                StorageBackendConfig.is_active == True
            )
            storage_result = await db.execute(storage_stmt)
            storage_config = storage_result.scalar_one_or_none()
            
            if not storage_config:
                return {
                    "success": False,
                    "error": f"Storage backend {backup_config.storage_backend} not found or inactive"
                }
            
            backup_execution = BackupExecution(
                backup_id=f"manual_{start_time.strftime('%Y%m%d_%H%M%S')}",
                storage_backend_id=storage_config.id,
                backup_type=backup_config.backup_type.value,
                triggered_by="manual",
                trigger_user_id=user_id,
                started_at=start_time,
                status=BackupStatusEnum.RUNNING,
                included_components=[],
                backup_config=backup_config_data
            )
            
            db.add(backup_execution)
            await db.commit()
            await db.refresh(backup_execution)
            
            # Execute backup
            backup_metadata = await backup_service.create_full_backup(backup_config)
            
            # Update execution record
            backup_execution.status = BackupStatusEnum(backup_metadata.status.value)
            backup_execution.completed_at = backup_metadata.completed_at
            backup_execution.size_bytes = backup_metadata.size_bytes
            backup_execution.compressed_size_bytes = backup_metadata.compressed_size_bytes
            backup_execution.included_components = backup_metadata.included_components
            backup_execution.storage_location = backup_metadata.storage_location
            backup_execution.checksum = backup_metadata.checksum
            backup_execution.verification_status = backup_metadata.verification_status
            backup_execution.error_message = backup_metadata.error_message
            
            if backup_execution.completed_at:
                backup_execution.duration_seconds = int(
                    (backup_execution.completed_at - backup_execution.started_at).total_seconds()
                )
            
            await db.commit()
            
            await self.log_audit_event(
                "manual_backup_completed",
                {
                    "backup_id": backup_execution.backup_id,
                    "status": backup_execution.status.value,
                    "user_id": user_id
                },
                user_id=user_id,
                status="success" if backup_execution.status == BackupStatusEnum.COMPLETED else "failure"
            )
            
            return {
                "success": backup_execution.status == BackupStatusEnum.COMPLETED,
                "backup_id": backup_execution.backup_id,
                "status": backup_execution.status.value,
                "size_bytes": backup_execution.size_bytes,
                "duration_seconds": backup_execution.duration_seconds
            }
            
    except Exception as e:
        logger.error(f"Manual backup failed: {e}")
        return {
            "success": False,
            "error": str(e)
        }


@celery_app.task(bind=True, base=BackupTaskBase)
def verify_backup_integrity(self, backup_execution_id: int) -> Dict[str, Any]:
    """Verify backup integrity."""
    return asyncio.run(self._verify_backup_integrity(backup_execution_id))


async def _verify_backup_integrity(self, backup_execution_id: int) -> Dict[str, Any]:
    """Async implementation of backup integrity verification."""
    try:
        await backup_service.initialize()
        
        async for db in get_db():
            # Get backup execution
            stmt = select(BackupExecution).where(BackupExecution.id == backup_execution_id)
            result = await db.execute(stmt)
            backup_execution = result.scalar_one_or_none()
            
            if not backup_execution:
                return {
                    "success": False,
                    "error": f"Backup execution {backup_execution_id} not found"
                }
            
            # Get storage backend
            storage_stmt = select(StorageBackendConfig).where(
                StorageBackendConfig.id == backup_execution.storage_backend_id
            )
            storage_result = await db.execute(storage_stmt)
            storage_config = storage_result.scalar_one_or_none()
            
            if not storage_config:
                return {
                    "success": False,
                    "error": f"Storage backend not found"
                }
            
            # Verify backup integrity
            backend = backup_service.storage_backends.get(
                StorageBackend(storage_config.backend_type.value)
            )
            
            if not backend:
                return {
                    "success": False,
                    "error": f"Storage backend {storage_config.backend_type} not initialized"
                }
            
            # Download and verify checksum
            verification_result = await backup_service._verify_backup_integrity(
                backup_execution, 
                BackupConfig(
                    backup_type=BackupType(backup_execution.backup_type.value),
                    storage_backend=StorageBackend(storage_config.backend_type.value)
                )
            )
            
            # Update verification status
            backup_execution.verification_status = "verified" if verification_result else "failed"
            backup_execution.verified_at = datetime.utcnow()
            
            await db.commit()
            
            await self.log_audit_event(
                "backup_verification_completed",
                {
                    "backup_id": backup_execution.backup_id,
                    "verification_result": verification_result
                },
                status="success" if verification_result else "failure"
            )
            
            return {
                "success": verification_result,
                "backup_id": backup_execution.backup_id,
                "verification_status": backup_execution.verification_status
            }
            
    except Exception as e:
        logger.error(f"Backup verification failed: {e}")
        return {
            "success": False,
            "error": str(e)
        }


@celery_app.task(bind=True, base=BackupTaskBase)
def cleanup_old_backups(self, retention_policy_id: int) -> Dict[str, Any]:
    """Clean up old backups based on retention policy."""
    return asyncio.run(self._cleanup_old_backups(retention_policy_id))


async def _cleanup_old_backups(self, retention_policy_id: int) -> Dict[str, Any]:
    """Async implementation of backup cleanup."""
    start_time = datetime.utcnow()
    
    try:
        await backup_service.initialize()
        
        async for db in get_db():
            # Get retention policy
            stmt = select(BackupRetentionPolicy).where(
                BackupRetentionPolicy.id == retention_policy_id,
                BackupRetentionPolicy.is_active == True
            )
            result = await db.execute(stmt)
            policy = result.scalar_one_or_none()
            
            if not policy:
                return {
                    "success": False,
                    "error": f"Retention policy {retention_policy_id} not found or inactive"
                }
            
            # Get storage backend
            storage_stmt = select(StorageBackendConfig).where(
                StorageBackendConfig.id == policy.storage_backend_id
            )
            storage_result = await db.execute(storage_stmt)
            storage_config = storage_result.scalar_one_or_none()
            
            if not storage_config:
                return {
                    "success": False,
                    "error": f"Storage backend not found"
                }
            
            # Create cleanup history record
            cleanup_history = BackupCleanupHistory(
                cleanup_id=f"cleanup_{start_time.strftime('%Y%m%d_%H%M%S')}",
                retention_policy_id=retention_policy_id,
                storage_backend_id=policy.storage_backend_id,
                triggered_by="schedule",
                started_at=start_time,
                status="running"
            )
            
            db.add(cleanup_history)
            await db.commit()
            await db.refresh(cleanup_history)
            
            try:
                # Get backups to evaluate
                cutoff_date = datetime.utcnow() - timedelta(days=policy.retention_days)
                
                backup_stmt = select(BackupExecution).where(
                    BackupExecution.storage_backend_id == policy.storage_backend_id,
                    BackupExecution.status == BackupStatusEnum.COMPLETED
                )
                
                if policy.backup_type:
                    backup_stmt = backup_stmt.where(
                        BackupExecution.backup_type == policy.backup_type
                    )
                
                backup_result = await db.execute(backup_stmt)
                all_backups = backup_result.scalars().all()
                
                # Apply retention logic
                backups_to_delete = []
                backups_evaluated = len(all_backups)
                
                for backup in all_backups:
                    if backup.created_at < cutoff_date:
                        # Check if we should keep this backup based on policy
                        should_keep = await self._should_keep_backup(backup, policy, all_backups)
                        
                        if not should_keep:
                            backups_to_delete.append(backup)
                
                # Ensure we keep minimum number of backups
                if len(all_backups) - len(backups_to_delete) < policy.min_backups_to_keep:
                    # Sort by date and remove oldest from deletion list
                    backups_to_delete.sort(key=lambda x: x.created_at)
                    excess_deletions = (policy.min_backups_to_keep - 
                                      (len(all_backups) - len(backups_to_delete)))
                    backups_to_delete = backups_to_delete[excess_deletions:]
                
                # Delete backups
                deleted_backup_ids = []
                space_freed = 0
                
                backend = backup_service.storage_backends.get(
                    StorageBackend(storage_config.backend_type.value)
                )
                
                for backup in backups_to_delete:
                    if backup.storage_location:
                        success = await backend.delete_file(backup.storage_location)
                        if success:
                            deleted_backup_ids.append(backup.backup_id)
                            space_freed += backup.size_bytes
                            
                            # Mark backup as deleted in database
                            backup.status = BackupStatusEnum.CANCELLED  # Using cancelled to indicate deleted
                            await db.commit()
                
                # Update cleanup history
                cleanup_history.completed_at = datetime.utcnow()
                cleanup_history.duration_seconds = int(
                    (cleanup_history.completed_at - cleanup_history.started_at).total_seconds()
                )
                cleanup_history.backups_evaluated = backups_evaluated
                cleanup_history.backups_deleted = len(deleted_backup_ids)
                cleanup_history.backups_kept = backups_evaluated - len(deleted_backup_ids)
                cleanup_history.space_freed_bytes = space_freed
                cleanup_history.deleted_backup_ids = deleted_backup_ids
                cleanup_history.status = "completed"
                
                # Update policy statistics
                policy.last_cleanup_at = start_time
                policy.total_cleanups += 1
                policy.total_backups_deleted += len(deleted_backup_ids)
                policy.total_space_freed_bytes += space_freed
                
                await db.commit()
                
                await self.log_audit_event(
                    "backup_cleanup_completed",
                    {
                        "policy_id": retention_policy_id,
                        "deleted_count": len(deleted_backup_ids),
                        "space_freed_bytes": space_freed
                    }
                )
                
                return {
                    "success": True,
                    "cleanup_id": cleanup_history.cleanup_id,
                    "backups_evaluated": backups_evaluated,
                    "backups_deleted": len(deleted_backup_ids),
                    "space_freed_bytes": space_freed
                }
            
            except Exception as e:
                cleanup_history.status = "failed"
                cleanup_history.error_message = str(e)
                cleanup_history.completed_at = datetime.utcnow()
                await db.commit()
                raise
            
            break
    
    except Exception as e:
        logger.error(f"Backup cleanup failed: {e}")
        return {
            "success": False,
            "error": str(e)
        }


async def _should_keep_backup(backup: BackupExecution, policy: BackupRetentionPolicy, all_backups: List[BackupExecution]) -> bool:
    """Determine if a backup should be kept based on retention policy."""
    backup_date = backup.created_at
    now = datetime.utcnow()
    
    # Daily backups (keep for policy.keep_daily_for_days days)
    if now - backup_date <= timedelta(days=policy.keep_daily_for_days):
        return True
    
    # Weekly backups (keep one per week for policy.keep_weekly_for_weeks weeks)
    if now - backup_date <= timedelta(weeks=policy.keep_weekly_for_weeks):
        # Check if this is the newest backup in its week
        week_start = backup_date - timedelta(days=backup_date.weekday())
        week_end = week_start + timedelta(days=7)
        
        week_backups = [
            b for b in all_backups 
            if week_start <= b.created_at < week_end
        ]
        
        if backup == max(week_backups, key=lambda x: x.created_at):
            return True
    
    # Monthly backups (keep one per month for policy.keep_monthly_for_months months)
    if now - backup_date <= timedelta(days=policy.keep_monthly_for_months * 30):
        # Check if this is the newest backup in its month
        month_start = backup_date.replace(day=1)
        if month_start.month == 12:
            month_end = month_start.replace(year=month_start.year + 1, month=1)
        else:
            month_end = month_start.replace(month=month_start.month + 1)
        
        month_backups = [
            b for b in all_backups 
            if month_start <= b.created_at < month_end
        ]
        
        if backup == max(month_backups, key=lambda x: x.created_at):
            return True
    
    # Yearly backups (keep one per year for policy.keep_yearly_for_years years)
    if now - backup_date <= timedelta(days=policy.keep_yearly_for_years * 365):
        # Check if this is the newest backup in its year
        year_start = backup_date.replace(month=1, day=1)
        year_end = year_start.replace(year=year_start.year + 1)
        
        year_backups = [
            b for b in all_backups 
            if year_start <= b.created_at < year_end
        ]
        
        if backup == max(year_backups, key=lambda x: x.created_at):
            return True
    
    return False


@celery_app.task(bind=True, base=BackupTaskBase)
def execute_recovery(self, recovery_config: Dict[str, Any], user_id: Optional[int] = None) -> Dict[str, Any]:
    """Execute a recovery operation."""
    return asyncio.run(self._execute_recovery(recovery_config, user_id))


async def _execute_recovery(self, recovery_config_data: Dict[str, Any], user_id: Optional[int] = None) -> Dict[str, Any]:
    """Async implementation of recovery execution."""
    start_time = datetime.utcnow()
    
    try:
        await recovery_service.initialize()
        
        # Parse recovery configuration
        recovery_config = RecoveryConfig(
            recovery_type=RecoveryType(recovery_config_data["recovery_type"]),
            backup_id=recovery_config_data["backup_id"],
            storage_backend=StorageBackend(recovery_config_data["storage_backend"]),
            validate_after_restore=recovery_config_data.get("validate_after_restore", True),
            create_backup_before_restore=recovery_config_data.get("create_backup_before_restore", True)
        )
        
        if "restore_components" in recovery_config_data:
            recovery_config.restore_components = recovery_config_data["restore_components"]
        
        # Execute recovery
        recovery_metadata = await recovery_service.start_recovery(recovery_config)
        
        # Create recovery execution record
        async for db in get_db():
            # Find the source backup
            backup_stmt = select(BackupExecution).where(
                BackupExecution.backup_id == recovery_config.backup_id
            )
            backup_result = await db.execute(backup_stmt)
            source_backup = backup_result.scalar_one_or_none()
            
            recovery_execution = RecoveryExecution(
                recovery_id=recovery_metadata.recovery_id,
                backup_execution_id=source_backup.id if source_backup else None,
                source_backup_id=recovery_config.backup_id,
                recovery_type=recovery_metadata.recovery_type,
                restore_target=recovery_metadata.target_system,
                status=RecoveryStatusEnum(recovery_metadata.status.value),
                triggered_by="manual",
                trigger_user_id=user_id,
                started_at=recovery_metadata.created_at,
                completed_at=recovery_metadata.completed_at,
                restore_components=recovery_config.restore_components or [],
                restored_components=recovery_metadata.restored_components,
                pre_recovery_backup_id=recovery_metadata.pre_restore_backup_id,
                validation_performed=recovery_config.validate_after_restore,
                validation_results=recovery_metadata.validation_results,
                validation_passed=recovery_metadata.validation_results.get("overall_success") if recovery_metadata.validation_results else None,
                error_message=recovery_metadata.error_message,
                warnings=recovery_metadata.warnings,
                recovery_config=recovery_config_data
            )
            
            if recovery_execution.completed_at:
                recovery_execution.duration_seconds = int(
                    (recovery_execution.completed_at - recovery_execution.started_at).total_seconds()
                )
            
            db.add(recovery_execution)
            await db.commit()
            
            await self.log_audit_event(
                "recovery_completed",
                {
                    "recovery_id": recovery_metadata.recovery_id,
                    "backup_id": recovery_config.backup_id,
                    "recovery_type": recovery_config.recovery_type.value,
                    "status": recovery_metadata.status.value,
                    "user_id": user_id
                },
                user_id=user_id,
                status="success" if recovery_metadata.status.value == "completed" else "failure"
            )
            
            return {
                "success": recovery_metadata.status.value == "completed",
                "recovery_id": recovery_metadata.recovery_id,
                "status": recovery_metadata.status.value,
                "restored_components": recovery_metadata.restored_components,
                "validation_results": recovery_metadata.validation_results
            }
            
    except Exception as e:
        logger.error(f"Recovery execution failed: {e}")
        return {
            "success": False,
            "error": str(e)
        }


@celery_app.task(bind=True, base=BackupTaskBase)
def health_check_backups(self) -> Dict[str, Any]:
    """Perform health checks on backup system."""
    return asyncio.run(self._health_check_backups())


async def _health_check_backups(self) -> Dict[str, Any]:
    """Async implementation of backup health checks."""
    try:
        await backup_service.initialize()
        
        health_results = {
            "overall_health": "healthy",
            "checks": {},
            "issues": [],
            "recommendations": []
        }
        
        async for db in get_db():
            # Check recent backup success rate
            recent_date = datetime.utcnow() - timedelta(days=7)
            recent_stmt = select(BackupExecution).where(
                BackupExecution.started_at >= recent_date
            )
            recent_result = await db.execute(recent_stmt)
            recent_backups = recent_result.scalars().all()
            
            if recent_backups:
                successful_backups = sum(
                    1 for b in recent_backups 
                    if b.status == BackupStatusEnum.COMPLETED
                )
                success_rate = successful_backups / len(recent_backups)
                
                health_results["checks"]["recent_success_rate"] = success_rate
                
                if success_rate < 0.8:
                    health_results["overall_health"] = "warning"
                    health_results["issues"].append(
                        f"Low backup success rate: {success_rate:.1%} (last 7 days)"
                    )
                
                if success_rate < 0.5:
                    health_results["overall_health"] = "critical"
            
            # Check storage backend health
            storage_stmt = select(StorageBackendConfig).where(
                StorageBackendConfig.is_active == True
            )
            storage_result = await db.execute(storage_stmt)
            storage_backends = storage_result.scalars().all()
            
            unhealthy_backends = [
                sb for sb in storage_backends 
                if not sb.is_healthy
            ]
            
            if unhealthy_backends:
                health_results["overall_health"] = "warning"
                health_results["issues"].extend([
                    f"Unhealthy storage backend: {sb.name}"
                    for sb in unhealthy_backends
                ])
            
            # Check for old unverified backups
            unverified_stmt = select(BackupExecution).where(
                BackupExecution.verification_status == "pending",
                BackupExecution.created_at < datetime.utcnow() - timedelta(hours=24)
            )
            unverified_result = await db.execute(unverified_stmt)
            old_unverified = unverified_result.scalars().all()
            
            if old_unverified:
                health_results["issues"].append(
                    f"{len(old_unverified)} backups pending verification for >24h"
                )
                health_results["recommendations"].append(
                    "Run backup verification tasks for pending backups"
                )
            
            # Create health check record
            health_check = BackupHealthCheck(
                check_id=f"health_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}",
                check_type="system",
                checked_at=datetime.utcnow(),
                status=health_results["overall_health"],
                check_results=health_results,
                issues_found=health_results["issues"],
                recommendations=health_results["recommendations"]
            )
            
            db.add(health_check)
            await db.commit()
            
            return health_results
            
    except Exception as e:
        logger.error(f"Backup health check failed: {e}")
        return {
            "overall_health": "error",
            "error": str(e)
        }


# Periodic tasks
@celery_app.task
def schedule_all_backups():
    """Schedule all active backup schedules."""
    return asyncio.run(_schedule_all_backups())


async def _schedule_all_backups():
    """Check and trigger due backup schedules."""
    try:
        async for db in get_db():
            # Get all active schedules
            stmt = select(BackupSchedule).where(BackupSchedule.is_active == True)
            result = await db.execute(stmt)
            schedules = result.scalars().all()
            
            for schedule in schedules:
                # Check if backup is due (simplified - in production use proper cron parsing)
                if schedule.next_run_at and schedule.next_run_at <= datetime.utcnow():
                    # Trigger backup
                    execute_scheduled_backup.delay(schedule.id)
                    
                    # Update next run time (simplified - use croniter in production)
                    schedule.next_run_at = datetime.utcnow() + timedelta(hours=24)
                    await db.commit()
            
            return {"scheduled_backups": len(schedules)}
            
    except Exception as e:
        logger.error(f"Failed to schedule backups: {e}")
        return {"error": str(e)}


# Beat schedule for periodic tasks
celery_app.conf.beat_schedule.update({
    'schedule-backups': {
        'task': 'app.tasks.backup_tasks.schedule_all_backups',
        'schedule': 300.0,  # Run every 5 minutes
    },
    'health-check-backups': {
        'task': 'app.tasks.backup_tasks.health_check_backups',
        'schedule': 3600.0,  # Run every hour
    },
})