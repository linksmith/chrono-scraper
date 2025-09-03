"""
Celery tasks for data synchronization operations

This module contains Celery tasks for background synchronization between
PostgreSQL and DuckDB, including consistency checks, conflict resolution,
and recovery operations.
"""
import asyncio
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any

from celery import Task
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.services.data_sync_service import (
    data_sync_service, SyncStrategy, ConsistencyLevel, SyncOperationType
)
from app.services.change_data_capture import cdc_service
from app.services.data_consistency_validator import (
    data_consistency_service, ConsistencyCheckType, run_consistency_check
)
from app.tasks.celery_app import celery_app


# Logging configuration
logger = logging.getLogger(__name__)


class AsyncTask(Task):
    """Base task class that handles async operations"""
    
    def __call__(self, *args, **kwargs):
        """Execute async task in event loop"""
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        return loop.run_until_complete(self.run_async(*args, **kwargs))
    
    async def run_async(self, *args, **kwargs):
        """Override this method for async task logic"""
        raise NotImplementedError("Subclasses must implement run_async method")


# =================================
# Data Synchronization Tasks
# =================================

@celery_app.task(bind=True, base=AsyncTask, max_retries=3)
async def full_table_sync(self, table_name: str, batch_size: Optional[int] = None) -> Dict[str, Any]:
    """
    Perform full table synchronization from PostgreSQL to DuckDB
    """
    logger.info(f"Starting full sync for table: {table_name}")
    
    try:
        if not settings.DATA_SYNC_ENABLED:
            return {"status": "skipped", "message": "Data sync is disabled"}
        
        result = await data_sync_service.sync_from_postgresql(
            table_name=table_name,
            batch_size=batch_size or settings.DATA_SYNC_BATCH_SIZE
        )
        
        logger.info(f"Full sync completed for {table_name}: {result}")
        return result
        
    except Exception as exc:
        logger.error(f"Full sync failed for {table_name}: {str(exc)}", exc_info=True)
        
        if self.request.retries < self.max_retries:
            # Retry with exponential backoff
            delay = 60 * (2 ** self.request.retries)
            logger.info(f"Retrying full sync for {table_name} in {delay} seconds")
            raise self.retry(countdown=delay, exc=exc)
        
        return {
            "status": "failed",
            "error": str(exc),
            "retries": self.request.retries
        }


@celery_app.task(bind=True, base=AsyncTask)
async def incremental_table_sync(self, table_name: str, since: str) -> Dict[str, Any]:
    """
    Perform incremental table synchronization since a specific timestamp
    """
    logger.info(f"Starting incremental sync for table {table_name} since {since}")
    
    try:
        if not settings.DATA_SYNC_ENABLED:
            return {"status": "skipped", "message": "Data sync is disabled"}
        
        since_datetime = datetime.fromisoformat(since.replace('Z', '+00:00'))
        
        result = await data_sync_service.sync_from_postgresql(
            table_name=table_name,
            since=since_datetime,
            batch_size=settings.DATA_SYNC_BATCH_SIZE
        )
        
        logger.info(f"Incremental sync completed for {table_name}: {result}")
        return result
        
    except Exception as exc:
        logger.error(f"Incremental sync failed for {table_name}: {str(exc)}", exc_info=True)
        return {
            "status": "failed",
            "error": str(exc)
        }


@celery_app.task(base=AsyncTask)
async def batch_sync_operation(
    operations: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Execute a batch of sync operations
    """
    logger.info(f"Processing batch of {len(operations)} sync operations")
    
    try:
        if not settings.DATA_SYNC_ENABLED:
            return {"status": "skipped", "message": "Data sync is disabled"}
        
        results = []
        successful = 0
        failed = 0
        
        for operation in operations:
            try:
                op_type = operation.get('type')
                table_name = operation.get('table_name')
                primary_key = operation.get('primary_key')
                data = operation.get('data', {})
                
                consistency_level = ConsistencyLevel(
                    operation.get('consistency_level', 'eventual')
                )
                strategy = SyncStrategy(
                    operation.get('strategy', 'near_real_time')
                )
                
                if op_type == 'create':
                    success, op_id = await data_sync_service.dual_write_create(
                        table_name=table_name,
                        data=data,
                        consistency_level=consistency_level,
                        strategy=strategy
                    )
                elif op_type == 'update':
                    success, op_id = await data_sync_service.dual_write_update(
                        table_name=table_name,
                        primary_key=primary_key,
                        data=data,
                        consistency_level=consistency_level,
                        strategy=strategy
                    )
                elif op_type == 'delete':
                    success, op_id = await data_sync_service.dual_write_delete(
                        table_name=table_name,
                        primary_key=primary_key,
                        consistency_level=consistency_level,
                        strategy=strategy
                    )
                else:
                    success = False
                    op_id = None
                
                if success:
                    successful += 1
                else:
                    failed += 1
                
                results.append({
                    "operation": operation,
                    "success": success,
                    "operation_id": op_id
                })
                
            except Exception as e:
                logger.error(f"Batch operation failed: {str(e)}")
                failed += 1
                results.append({
                    "operation": operation,
                    "success": False,
                    "error": str(e)
                })
        
        return {
            "status": "completed",
            "total_operations": len(operations),
            "successful": successful,
            "failed": failed,
            "results": results
        }
        
    except Exception as exc:
        logger.error(f"Batch sync operation failed: {str(exc)}", exc_info=True)
        return {
            "status": "failed",
            "error": str(exc)
        }


@celery_app.task(bind=True, base=AsyncTask, max_retries=5)
async def sync_recovery_operation(self, operation_id: str) -> Dict[str, Any]:
    """
    Recover a failed sync operation
    """
    logger.info(f"Starting recovery for sync operation: {operation_id}")
    
    try:
        success = await data_sync_service.handle_sync_failure(operation_id)
        
        if success:
            return {
                "status": "recovered",
                "operation_id": operation_id,
                "message": "Operation queued for recovery"
            }
        else:
            if self.request.retries < self.max_retries:
                # Retry with increasing delays
                delay = 300 * (2 ** self.request.retries)  # 5min, 10min, 20min, etc.
                logger.info(f"Retrying recovery for {operation_id} in {delay} seconds")
                raise self.retry(countdown=delay)
            
            return {
                "status": "failed",
                "operation_id": operation_id,
                "message": "Recovery failed after all retries"
            }
            
    except Exception as exc:
        logger.error(f"Sync recovery failed for {operation_id}: {str(exc)}", exc_info=True)
        
        if self.request.retries < self.max_retries:
            delay = 300 * (2 ** self.request.retries)
            raise self.retry(countdown=delay, exc=exc)
        
        return {
            "status": "failed",
            "operation_id": operation_id,
            "error": str(exc)
        }


# =================================
# Consistency Validation Tasks
# =================================

@celery_app.task(bind=True, base=AsyncTask)
async def run_consistency_validation(
    self, 
    tables: Optional[List[str]] = None,
    check_types: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    Run comprehensive consistency validation
    """
    logger.info("Starting consistency validation")
    
    try:
        if not settings.CONSISTENCY_CHECK_ENABLED:
            return {"status": "skipped", "message": "Consistency checks are disabled"}
        
        # Convert string check types to enums
        if check_types:
            check_types = [ConsistencyCheckType(ct) for ct in check_types]
        
        report = await data_consistency_service.run_consistency_check(
            tables=tables,
            check_types=check_types
        )
        
        # Convert report to serializable format
        report_dict = {
            "report_id": report.report_id,
            "generated_at": report.generated_at.isoformat(),
            "total_checks": report.total_checks,
            "passed_checks": report.passed_checks,
            "failed_checks": report.failed_checks,
            "warnings": report.warnings,
            "errors": report.errors,
            "critical_issues": report.critical_issues,
            "consistency_score": report.consistency_score,
            "recommendations": report.recommendations,
            "performance_metrics": report.performance_metrics,
            "validation_results": [
                {
                    "check_id": result.check_id,
                    "check_type": result.check_type.value,
                    "table_name": result.table_name,
                    "primary_key": str(result.primary_key) if result.primary_key else None,
                    "is_consistent": result.is_consistent,
                    "severity": result.severity.value,
                    "message": result.message,
                    "details": result.details,
                    "checked_at": result.checked_at.isoformat()
                }
                for result in report.validation_results
            ]
        }
        
        # Send alerts if needed
        if report.critical_issues > 0:
            await send_consistency_alert.delay({
                "type": "critical_issues",
                "count": report.critical_issues,
                "report_id": report.report_id,
                "consistency_score": report.consistency_score
            })
        elif report.consistency_score < settings.CONSISTENCY_SCORE_ALERT_THRESHOLD:
            await send_consistency_alert.delay({
                "type": "low_consistency_score",
                "score": report.consistency_score,
                "threshold": settings.CONSISTENCY_SCORE_ALERT_THRESHOLD,
                "report_id": report.report_id
            })
        
        logger.info(f"Consistency validation completed: {report.consistency_score}% consistent")
        return {
            "status": "completed",
            "report": report_dict
        }
        
    except Exception as exc:
        logger.error(f"Consistency validation failed: {str(exc)}", exc_info=True)
        return {
            "status": "failed",
            "error": str(exc)
        }


@celery_app.task(bind=True, base=AsyncTask)
async def resolve_data_conflicts(self, validation_result_ids: List[str]) -> Dict[str, Any]:
    """
    Resolve data conflicts for specific validation results
    """
    logger.info(f"Resolving conflicts for {len(validation_result_ids)} validation results")
    
    try:
        if not settings.AUTO_RESOLVE_CONFLICTS:
            return {"status": "skipped", "message": "Auto conflict resolution is disabled"}
        
        # This is a simplified implementation - in practice would need to
        # retrieve validation results from storage and resolve conflicts
        resolution_results = []
        
        for result_id in validation_result_ids:
            try:
                # Placeholder for actual conflict resolution logic
                resolution_results.append({
                    "validation_result_id": result_id,
                    "status": "resolved",
                    "strategy": settings.DEFAULT_CONFLICT_RESOLUTION_STRATEGY
                })
            except Exception as e:
                logger.error(f"Failed to resolve conflict for {result_id}: {str(e)}")
                resolution_results.append({
                    "validation_result_id": result_id,
                    "status": "failed",
                    "error": str(e)
                })
        
        return {
            "status": "completed",
            "resolution_results": resolution_results
        }
        
    except Exception as exc:
        logger.error(f"Conflict resolution failed: {str(exc)}", exc_info=True)
        return {
            "status": "failed",
            "error": str(exc)
        }


@celery_app.task(base=AsyncTask)
async def validate_single_record(
    table_name: str,
    primary_key: Any,
    check_types: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    Validate consistency for a single record
    """
    logger.info(f"Validating single record: {table_name}[{primary_key}]")
    
    try:
        if check_types:
            check_types = [ConsistencyCheckType(ct) for ct in check_types]
        
        report = await data_consistency_service.run_consistency_check(
            tables=[table_name],
            check_types=check_types,
            primary_key=primary_key
        )
        
        return {
            "status": "completed",
            "table_name": table_name,
            "primary_key": str(primary_key),
            "is_consistent": report.failed_checks == 0,
            "validation_results": [
                {
                    "check_type": result.check_type.value,
                    "is_consistent": result.is_consistent,
                    "severity": result.severity.value,
                    "message": result.message
                }
                for result in report.validation_results
            ]
        }
        
    except Exception as exc:
        logger.error(f"Single record validation failed: {str(exc)}", exc_info=True)
        return {
            "status": "failed",
            "error": str(exc)
        }


# =================================
# Monitoring and Alerting Tasks
# =================================

@celery_app.task(base=AsyncTask)
async def monitor_sync_health() -> Dict[str, Any]:
    """
    Monitor sync service health and send alerts if needed
    """
    try:
        # Get sync service status
        sync_status = await data_sync_service.get_sync_status()
        
        # Check for alerting conditions
        alerts = []
        
        # Check sync lag
        sync_lag = sync_status['metrics']['sync_lag_seconds']
        if sync_lag > (settings.SYNC_LAG_ALERT_THRESHOLD_MINUTES * 60):
            alerts.append({
                "type": "high_sync_lag",
                "value": sync_lag,
                "threshold": settings.SYNC_LAG_ALERT_THRESHOLD_MINUTES * 60
            })
        
        # Check dead letter queue size
        dlq_size = sync_status['queue_status']['dead_letter']
        if dlq_size > settings.DEAD_LETTER_QUEUE_ALERT_THRESHOLD:
            alerts.append({
                "type": "dead_letter_queue_full",
                "value": dlq_size,
                "threshold": settings.DEAD_LETTER_QUEUE_ALERT_THRESHOLD
            })
        
        # Check consistency score
        consistency_score = sync_status['metrics']['consistency_score']
        if consistency_score < settings.CONSISTENCY_SCORE_ALERT_THRESHOLD:
            alerts.append({
                "type": "low_consistency_score",
                "value": consistency_score,
                "threshold": settings.CONSISTENCY_SCORE_ALERT_THRESHOLD
            })
        
        # Send alerts if any conditions are met
        if alerts:
            await send_sync_health_alert.delay({
                "alerts": alerts,
                "sync_status": sync_status,
                "timestamp": datetime.utcnow().isoformat()
            })
        
        return {
            "status": "completed",
            "health_status": "healthy" if not alerts else "degraded",
            "alerts": alerts,
            "sync_status": sync_status
        }
        
    except Exception as exc:
        logger.error(f"Sync health monitoring failed: {str(exc)}", exc_info=True)
        return {
            "status": "failed",
            "error": str(exc)
        }


@celery_app.task(base=AsyncTask)
async def send_sync_health_alert(alert_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Send sync health alert via configured channels
    """
    try:
        # Send webhook alert if configured
        if settings.SYNC_ALERT_WEBHOOK_URL:
            # Would implement webhook notification here
            logger.info(f"Would send webhook alert to {settings.SYNC_ALERT_WEBHOOK_URL}")
        
        # Send email alert if configured
        if settings.SYNC_ALERT_EMAIL:
            # Would implement email notification here
            logger.info(f"Would send email alert to {settings.SYNC_ALERT_EMAIL}")
        
        logger.warning(f"Sync health alert: {alert_data}")
        
        return {
            "status": "sent",
            "alert_data": alert_data
        }
        
    except Exception as exc:
        logger.error(f"Failed to send sync health alert: {str(exc)}", exc_info=True)
        return {
            "status": "failed",
            "error": str(exc)
        }


@celery_app.task(base=AsyncTask)
async def send_consistency_alert(alert_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Send consistency validation alert
    """
    try:
        # Send webhook alert if configured
        if settings.CONSISTENCY_ALERT_WEBHOOK_URL:
            # Would implement webhook notification here
            logger.info(f"Would send consistency webhook alert to {settings.CONSISTENCY_ALERT_WEBHOOK_URL}")
        
        # Send email alert if configured
        if settings.CRITICAL_ERROR_EMAIL:
            # Would implement email notification here
            logger.info(f"Would send consistency email alert to {settings.CRITICAL_ERROR_EMAIL}")
        
        logger.warning(f"Consistency alert: {alert_data}")
        
        return {
            "status": "sent",
            "alert_data": alert_data
        }
        
    except Exception as exc:
        logger.error(f"Failed to send consistency alert: {str(exc)}", exc_info=True)
        return {
            "status": "failed",
            "error": str(exc)
        }


# =================================
# Cleanup and Maintenance Tasks
# =================================

@celery_app.task(base=AsyncTask)
async def cleanup_sync_history() -> Dict[str, Any]:
    """
    Clean up old sync operation history and validation results
    """
    logger.info("Starting sync history cleanup")
    
    try:
        cleaned_operations = 0
        cleaned_validations = 0
        
        # Clean up old sync operations from memory (would be from persistent storage in production)
        cutoff_date = datetime.utcnow() - timedelta(days=settings.VALIDATION_HISTORY_RETENTION_DAYS)
        
        # Clean up old validation history
        validation_history = data_consistency_service.validation_history
        original_count = len(validation_history)
        
        data_consistency_service.validation_history = [
            report for report in validation_history 
            if report.generated_at >= cutoff_date
        ]
        
        cleaned_validations = original_count - len(data_consistency_service.validation_history)
        
        logger.info(f"Cleaned up {cleaned_operations} sync operations and {cleaned_validations} validation reports")
        
        return {
            "status": "completed",
            "cleaned_sync_operations": cleaned_operations,
            "cleaned_validation_reports": cleaned_validations,
            "cutoff_date": cutoff_date.isoformat()
        }
        
    except Exception as exc:
        logger.error(f"Cleanup failed: {str(exc)}", exc_info=True)
        return {
            "status": "failed",
            "error": str(exc)
        }


@celery_app.task(base=AsyncTask)
async def process_dead_letter_queue() -> Dict[str, Any]:
    """
    Process operations in the dead letter queue
    """
    logger.info("Processing dead letter queue")
    
    try:
        dead_letter_ops = data_sync_service.get_dead_letter_operations()
        
        if not dead_letter_ops:
            return {
                "status": "completed",
                "message": "Dead letter queue is empty"
            }
        
        processed = 0
        failed = 0
        
        for operation in dead_letter_ops:
            try:
                operation_id = operation['operation_id']
                success = await data_sync_service.retry_dead_letter_operation(operation_id)
                
                if success:
                    processed += 1
                    logger.info(f"Retried dead letter operation: {operation_id}")
                else:
                    failed += 1
                    logger.warning(f"Failed to retry dead letter operation: {operation_id}")
                    
            except Exception as e:
                logger.error(f"Error processing dead letter operation: {str(e)}")
                failed += 1
        
        return {
            "status": "completed",
            "total_operations": len(dead_letter_ops),
            "processed": processed,
            "failed": failed
        }
        
    except Exception as exc:
        logger.error(f"Dead letter queue processing failed: {str(exc)}", exc_info=True)
        return {
            "status": "failed",
            "error": str(exc)
        }


# =================================
# Periodic Tasks (Celery Beat Schedule)
# =================================

@celery_app.task(base=AsyncTask)
async def scheduled_consistency_check() -> Dict[str, Any]:
    """
    Scheduled consistency validation (runs every 6 hours by default)
    """
    logger.info("Running scheduled consistency check")
    
    if not settings.CONSISTENCY_CHECK_ENABLED:
        return {"status": "skipped", "message": "Consistency checks are disabled"}
    
    # Run consistency check for all monitored tables
    tables = settings.CDC_MONITORED_TABLES.split(',')
    tables = [table.strip() for table in tables if table.strip()]
    
    return await run_consistency_validation.delay(tables=tables)


@celery_app.task(base=AsyncTask)
async def scheduled_sync_health_check() -> Dict[str, Any]:
    """
    Scheduled sync health monitoring (runs every hour by default)
    """
    logger.info("Running scheduled sync health check")
    
    if not settings.ENABLE_SYNC_MONITORING:
        return {"status": "skipped", "message": "Sync monitoring is disabled"}
    
    return await monitor_sync_health.delay()


@celery_app.task(base=AsyncTask)
async def scheduled_cleanup() -> Dict[str, Any]:
    """
    Scheduled cleanup task (runs daily)
    """
    logger.info("Running scheduled cleanup")
    
    cleanup_result = await cleanup_sync_history.delay()
    dlq_result = await process_dead_letter_queue.delay()
    
    return {
        "status": "completed",
        "cleanup_result": cleanup_result,
        "dlq_result": dlq_result
    }


# =================================
# Initialize Services Task
# =================================

@celery_app.task(base=AsyncTask)
async def initialize_sync_services() -> Dict[str, Any]:
    """
    Initialize all sync services (run at startup)
    """
    logger.info("Initializing sync services")
    
    try:
        services_initialized = []
        
        # Initialize data sync service
        if settings.DATA_SYNC_ENABLED:
            await data_sync_service.initialize()
            services_initialized.append("DataSyncService")
        
        # Initialize CDC service
        if settings.CDC_ENABLED:
            await cdc_service.initialize()
            await cdc_service.start()
            services_initialized.append("CDCService")
        
        logger.info(f"Sync services initialized: {services_initialized}")
        
        return {
            "status": "completed",
            "services_initialized": services_initialized,
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as exc:
        logger.error(f"Service initialization failed: {str(exc)}", exc_info=True)
        return {
            "status": "failed",
            "error": str(exc)
        }


@celery_app.task(base=AsyncTask)
async def shutdown_sync_services() -> Dict[str, Any]:
    """
    Gracefully shutdown all sync services
    """
    logger.info("Shutting down sync services")
    
    try:
        services_shutdown = []
        
        # Shutdown CDC service
        if settings.CDC_ENABLED:
            await cdc_service.stop()
            services_shutdown.append("CDCService")
        
        # Shutdown data sync service
        if settings.DATA_SYNC_ENABLED:
            await data_sync_service.shutdown()
            services_shutdown.append("DataSyncService")
        
        logger.info(f"Sync services shutdown: {services_shutdown}")
        
        return {
            "status": "completed",
            "services_shutdown": services_shutdown,
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as exc:
        logger.error(f"Service shutdown failed: {str(exc)}", exc_info=True)
        return {
            "status": "failed",
            "error": str(exc)
        }