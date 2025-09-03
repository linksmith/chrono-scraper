"""
FastAPI endpoints for Data Synchronization management

This module provides REST API endpoints for managing data synchronization
between PostgreSQL and DuckDB, including monitoring, consistency checks,
and conflict resolution.
"""
import logging
from datetime import datetime
from typing import Dict, List, Optional, Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_admin_user
from app.core.database import get_db
from app.models.user import User
from app.services.data_sync_service import (
    data_sync_service, SyncStrategy, ConsistencyLevel
)
from app.services.change_data_capture import cdc_service
from app.services.data_consistency_validator import (
    data_consistency_service, ConsistencyCheckType, run_consistency_check
)
from app.services.sync_monitoring_service import sync_monitoring_service
from app.tasks.data_sync_tasks import (
    full_table_sync, incremental_table_sync, run_consistency_validation,
    initialize_sync_services, scheduled_consistency_check
)


# Logging configuration
logger = logging.getLogger(__name__)

# Create router
router = APIRouter()


# =================================
# Request/Response Models
# =================================

class SyncOperationRequest(BaseModel):
    """Request model for sync operations"""
    table_name: str = Field(..., description="Name of the table to sync")
    operation_type: str = Field(..., description="Type of operation: create, update, delete")
    primary_key: Optional[Any] = Field(None, description="Primary key of the record")
    data: Dict[str, Any] = Field(default_factory=dict, description="Data to sync")
    consistency_level: str = Field("eventual", description="Consistency level: strong, eventual, weak")
    strategy: str = Field("near_real_time", description="Sync strategy: real_time, near_real_time, batch, recovery")


class BatchSyncRequest(BaseModel):
    """Request model for batch sync operations"""
    operations: List[SyncOperationRequest] = Field(..., description="List of sync operations")


class ConsistencyCheckRequest(BaseModel):
    """Request model for consistency checks"""
    tables: Optional[List[str]] = Field(None, description="Tables to check (empty for all)")
    check_types: Optional[List[str]] = Field(None, description="Types of checks to perform")
    primary_key: Optional[Any] = Field(None, description="Specific record to check")


class AlertRequest(BaseModel):
    """Request model for manual alerts"""
    alert_type: str = Field(..., description="Type of alert")
    severity: str = Field(..., description="Alert severity: info, warning, critical, emergency")
    title: str = Field(..., description="Alert title")
    description: str = Field(..., description="Alert description")
    service: str = Field(..., description="Service that generated the alert")
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Additional metadata")


class SyncStatusResponse(BaseModel):
    """Response model for sync status"""
    service_status: str
    metrics: Dict[str, Any]
    queue_status: Dict[str, int]
    database_health: Dict[str, Any]
    background_workers: int
    configuration: Dict[str, Any]


class ConsistencyReportResponse(BaseModel):
    """Response model for consistency reports"""
    report_id: str
    generated_at: str
    total_checks: int
    passed_checks: int
    failed_checks: int
    consistency_score: float
    recommendations: List[str]
    validation_results: List[Dict[str, Any]]


# =================================
# Data Sync Management Endpoints
# =================================

@router.get("/sync/status", response_model=Dict[str, Any])
async def get_sync_status(
    current_user: User = Depends(get_current_admin_user)
):
    """Get comprehensive sync service status"""
    try:
        status = await data_sync_service.get_sync_status()
        return {
            "status": "success",
            "data": status,
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        logger.error(f"Failed to get sync status: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to get sync status: {str(e)}")


@router.post("/sync/operation")
async def create_sync_operation(
    request: SyncOperationRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_admin_user)
):
    """Create a new sync operation"""
    try:
        consistency_level = ConsistencyLevel(request.consistency_level)
        strategy = SyncStrategy(request.strategy)
        
        if request.operation_type == "create":
            success, operation_id = await data_sync_service.dual_write_create(
                table_name=request.table_name,
                data=request.data,
                consistency_level=consistency_level,
                strategy=strategy
            )
        elif request.operation_type == "update":
            success, operation_id = await data_sync_service.dual_write_update(
                table_name=request.table_name,
                primary_key=request.primary_key,
                data=request.data,
                consistency_level=consistency_level,
                strategy=strategy
            )
        elif request.operation_type == "delete":
            success, operation_id = await data_sync_service.dual_write_delete(
                table_name=request.table_name,
                primary_key=request.primary_key,
                consistency_level=consistency_level,
                strategy=strategy
            )
        else:
            raise HTTPException(status_code=400, detail=f"Invalid operation type: {request.operation_type}")
        
        return {
            "status": "success" if success else "failed",
            "operation_id": operation_id,
            "message": f"Sync operation {'queued' if success else 'failed'}"
        }
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid request: {str(e)}")
    except Exception as e:
        logger.error(f"Sync operation failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Sync operation failed: {str(e)}")


@router.post("/sync/batch")
async def create_batch_sync_operation(
    request: BatchSyncRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_admin_user)
):
    """Create a batch of sync operations"""
    try:
        # Convert requests to dict format for Celery task
        operations = []
        for op in request.operations:
            operations.append({
                "type": op.operation_type,
                "table_name": op.table_name,
                "primary_key": op.primary_key,
                "data": op.data,
                "consistency_level": op.consistency_level,
                "strategy": op.strategy
            })
        
        # Queue batch operation as background task
        from app.tasks.data_sync_tasks import batch_sync_operation
        task = batch_sync_operation.delay(operations)
        
        return {
            "status": "success",
            "task_id": task.id,
            "operations_count": len(operations),
            "message": "Batch sync operation queued"
        }
        
    except Exception as e:
        logger.error(f"Batch sync operation failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Batch sync operation failed: {str(e)}")


@router.post("/sync/table/{table_name}/full")
async def trigger_full_table_sync(
    table_name: str,
    batch_size: Optional[int] = Query(None, description="Batch size for sync operation"),
    current_user: User = Depends(get_current_admin_user)
):
    """Trigger full table synchronization"""
    try:
        # Queue full sync as background task
        task = full_table_sync.delay(table_name, batch_size)
        
        return {
            "status": "success",
            "task_id": task.id,
            "table_name": table_name,
            "message": "Full table sync queued"
        }
        
    except Exception as e:
        logger.error(f"Full table sync failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Full table sync failed: {str(e)}")


@router.post("/sync/table/{table_name}/incremental")
async def trigger_incremental_table_sync(
    table_name: str,
    since: str = Query(..., description="ISO timestamp to sync since"),
    current_user: User = Depends(get_current_admin_user)
):
    """Trigger incremental table synchronization"""
    try:
        # Validate timestamp format
        try:
            datetime.fromisoformat(since.replace('Z', '+00:00'))
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid timestamp format. Use ISO format.")
        
        # Queue incremental sync as background task
        task = incremental_table_sync.delay(table_name, since)
        
        return {
            "status": "success",
            "task_id": task.id,
            "table_name": table_name,
            "since": since,
            "message": "Incremental table sync queued"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Incremental table sync failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Incremental table sync failed: {str(e)}")


@router.post("/sync/recovery/{operation_id}")
async def trigger_sync_recovery(
    operation_id: str,
    current_user: User = Depends(get_current_admin_user)
):
    """Trigger recovery for a failed sync operation"""
    try:
        from app.tasks.data_sync_tasks import sync_recovery_operation
        task = sync_recovery_operation.delay(operation_id)
        
        return {
            "status": "success",
            "task_id": task.id,
            "operation_id": operation_id,
            "message": "Sync recovery queued"
        }
        
    except Exception as e:
        logger.error(f"Sync recovery failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Sync recovery failed: {str(e)}")


@router.get("/sync/dead-letter-queue")
async def get_dead_letter_queue(
    current_user: User = Depends(get_current_admin_user)
):
    """Get operations in the dead letter queue"""
    try:
        dead_letter_ops = data_sync_service.get_dead_letter_operations()
        
        return {
            "status": "success",
            "operations": dead_letter_ops,
            "count": len(dead_letter_ops),
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Failed to get dead letter queue: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to get dead letter queue: {str(e)}")


@router.post("/sync/dead-letter-queue/{operation_id}/retry")
async def retry_dead_letter_operation(
    operation_id: str,
    current_user: User = Depends(get_current_admin_user)
):
    """Retry a specific dead letter operation"""
    try:
        success = await data_sync_service.retry_dead_letter_operation(operation_id)
        
        return {
            "status": "success" if success else "failed",
            "operation_id": operation_id,
            "message": "Operation retry queued" if success else "Operation not found in dead letter queue"
        }
        
    except Exception as e:
        logger.error(f"Dead letter retry failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Dead letter retry failed: {str(e)}")


# =================================
# Consistency Validation Endpoints
# =================================

@router.post("/consistency/check", response_model=Dict[str, Any])
async def trigger_consistency_check(
    request: ConsistencyCheckRequest,
    current_user: User = Depends(get_current_admin_user)
):
    """Trigger consistency validation"""
    try:
        # Queue consistency check as background task
        task = run_consistency_validation.delay(
            tables=request.tables,
            check_types=request.check_types
        )
        
        return {
            "status": "success",
            "task_id": task.id,
            "message": "Consistency check queued",
            "tables": request.tables or "all",
            "check_types": request.check_types or "all"
        }
        
    except Exception as e:
        logger.error(f"Consistency check failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Consistency check failed: {str(e)}")


@router.post("/consistency/check/sync")
async def run_consistency_check_sync(
    request: ConsistencyCheckRequest,
    current_user: User = Depends(get_current_admin_user)
):
    """Run consistency validation synchronously"""
    try:
        # Convert string check types to enums
        check_types = None
        if request.check_types:
            check_types = [ConsistencyCheckType(ct) for ct in request.check_types]
        
        report = await data_consistency_service.run_consistency_check(
            tables=request.tables,
            check_types=check_types,
            primary_key=request.primary_key
        )
        
        # Convert report to response format
        return {
            "status": "success",
            "report": {
                "report_id": report.report_id,
                "generated_at": report.generated_at.isoformat(),
                "total_checks": report.total_checks,
                "passed_checks": report.passed_checks,
                "failed_checks": report.failed_checks,
                "consistency_score": report.consistency_score,
                "recommendations": report.recommendations,
                "validation_results": [
                    {
                        "check_id": result.check_id,
                        "check_type": result.check_type.value,
                        "table_name": result.table_name,
                        "primary_key": str(result.primary_key) if result.primary_key else None,
                        "is_consistent": result.is_consistent,
                        "severity": result.severity.value,
                        "message": result.message,
                        "details": result.details
                    }
                    for result in report.validation_results
                ]
            }
        }
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid request: {str(e)}")
    except Exception as e:
        logger.error(f"Consistency check failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Consistency check failed: {str(e)}")


@router.get("/consistency/validate/{table_name}")
async def validate_table_consistency(
    table_name: str,
    primary_key: Optional[str] = Query(None, description="Specific record to validate"),
    check_types: Optional[List[str]] = Query(None, description="Types of checks to perform"),
    current_user: User = Depends(get_current_admin_user)
):
    """Validate consistency for a specific table or record"""
    try:
        from app.tasks.data_sync_tasks import validate_single_record
        
        # Queue validation as background task
        task = validate_single_record.delay(
            table_name=table_name,
            primary_key=primary_key,
            check_types=check_types
        )
        
        return {
            "status": "success",
            "task_id": task.id,
            "table_name": table_name,
            "primary_key": primary_key,
            "message": "Validation queued"
        }
        
    except Exception as e:
        logger.error(f"Table validation failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Table validation failed: {str(e)}")


@router.get("/consistency/status")
async def get_consistency_status(
    current_user: User = Depends(get_current_admin_user)
):
    """Get consistency service status"""
    try:
        status = await data_consistency_service.get_service_status()
        
        return {
            "status": "success",
            "data": status,
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Failed to get consistency status: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to get consistency status: {str(e)}")


@router.get("/consistency/history")
async def get_consistency_history(
    limit: int = Query(50, ge=1, le=1000, description="Number of reports to return"),
    current_user: User = Depends(get_current_admin_user)
):
    """Get consistency validation history"""
    try:
        history = data_consistency_service.get_validation_history(limit=limit)
        
        return {
            "status": "success",
            "history": history,
            "count": len(history),
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Failed to get consistency history: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to get consistency history: {str(e)}")


# =================================
# CDC Management Endpoints
# =================================

@router.get("/cdc/status")
async def get_cdc_status(
    current_user: User = Depends(get_current_admin_user)
):
    """Get CDC service status"""
    try:
        status = await cdc_service.get_status()
        
        return {
            "status": "success",
            "data": status,
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Failed to get CDC status: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to get CDC status: {str(e)}")


@router.post("/cdc/table/{table_name}/add")
async def add_monitored_table(
    table_name: str,
    current_user: User = Depends(get_current_admin_user)
):
    """Add a table to CDC monitoring"""
    try:
        success = await cdc_service.add_monitored_table(table_name)
        
        return {
            "status": "success" if success else "failed",
            "table_name": table_name,
            "message": f"Table {'added to' if success else 'already in'} CDC monitoring"
        }
        
    except Exception as e:
        logger.error(f"Failed to add monitored table: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to add monitored table: {str(e)}")


@router.delete("/cdc/table/{table_name}/remove")
async def remove_monitored_table(
    table_name: str,
    current_user: User = Depends(get_current_admin_user)
):
    """Remove a table from CDC monitoring"""
    try:
        success = await cdc_service.remove_monitored_table(table_name)
        
        return {
            "status": "success" if success else "failed",
            "table_name": table_name,
            "message": f"Table {'removed from' if success else 'not found in'} CDC monitoring"
        }
        
    except Exception as e:
        logger.error(f"Failed to remove monitored table: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to remove monitored table: {str(e)}")


@router.post("/cdc/replication-slot/reset")
async def reset_cdc_replication_slot(
    current_user: User = Depends(get_current_admin_user)
):
    """Reset CDC replication slot"""
    try:
        success = await cdc_service.reset_replication_slot()
        
        return {
            "status": "success" if success else "failed",
            "message": "Replication slot reset" if success else "Failed to reset replication slot"
        }
        
    except Exception as e:
        logger.error(f"Failed to reset replication slot: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to reset replication slot: {str(e)}")


# =================================
# Monitoring and Alerting Endpoints
# =================================

@router.get("/monitoring/dashboard")
async def get_monitoring_dashboard(
    current_user: User = Depends(get_current_admin_user)
):
    """Get comprehensive monitoring dashboard data"""
    try:
        dashboard_data = await sync_monitoring_service.get_monitoring_dashboard_data()
        
        return {
            "status": "success",
            "data": dashboard_data
        }
        
    except Exception as e:
        logger.error(f"Failed to get dashboard data: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to get dashboard data: {str(e)}")


@router.get("/monitoring/health")
async def get_overall_health(
    current_user: User = Depends(get_current_admin_user)
):
    """Get overall health status of all sync services"""
    try:
        health_status = await sync_monitoring_service.get_overall_health_status()
        
        return health_status
        
    except Exception as e:
        logger.error(f"Health check failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Health check failed: {str(e)}")


@router.get("/monitoring/alerts")
async def get_active_alerts(
    current_user: User = Depends(get_current_admin_user)
):
    """Get active alerts"""
    try:
        active_alerts = sync_monitoring_service.alert_manager.get_active_alerts()
        
        return {
            "status": "success",
            "alerts": active_alerts,
            "count": len(active_alerts),
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Failed to get alerts: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to get alerts: {str(e)}")


@router.get("/monitoring/alerts/history")
async def get_alert_history(
    limit: int = Query(100, ge=1, le=1000, description="Number of alerts to return"),
    current_user: User = Depends(get_current_admin_user)
):
    """Get alert history"""
    try:
        alert_history = sync_monitoring_service.alert_manager.get_alert_history(limit=limit)
        
        return {
            "status": "success",
            "alerts": alert_history,
            "count": len(alert_history),
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Failed to get alert history: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to get alert history: {str(e)}")


@router.post("/monitoring/alerts")
async def create_manual_alert(
    request: AlertRequest,
    current_user: User = Depends(get_current_admin_user)
):
    """Create a manual alert"""
    try:
        alert_id = await sync_monitoring_service.create_manual_alert(
            alert_type=request.alert_type,
            severity=request.severity,
            title=request.title,
            description=request.description,
            service=request.service,
            metadata=request.metadata
        )
        
        return {
            "status": "success",
            "alert_id": alert_id,
            "message": "Alert created"
        }
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid request: {str(e)}")
    except Exception as e:
        logger.error(f"Failed to create alert: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to create alert: {str(e)}")


@router.post("/monitoring/alerts/{alert_id}/resolve")
async def resolve_alert(
    alert_id: str,
    current_user: User = Depends(get_current_admin_user)
):
    """Resolve an active alert"""
    try:
        success = await sync_monitoring_service.resolve_alert(alert_id)
        
        return {
            "status": "success" if success else "failed",
            "alert_id": alert_id,
            "message": "Alert resolved" if success else "Alert not found or already resolved"
        }
        
    except Exception as e:
        logger.error(f"Failed to resolve alert: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to resolve alert: {str(e)}")


@router.get("/monitoring/metrics/prometheus")
async def get_prometheus_metrics(
    current_user: User = Depends(get_current_admin_user)
):
    """Get Prometheus metrics for external monitoring"""
    try:
        metrics = sync_monitoring_service.get_prometheus_metrics()
        
        return Response(
            content=metrics,
            media_type="text/plain; version=0.0.4; charset=utf-8"
        )
        
    except Exception as e:
        logger.error(f"Failed to get Prometheus metrics: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to get Prometheus metrics: {str(e)}")


# =================================
# Service Management Endpoints
# =================================

@router.post("/services/initialize")
async def initialize_services(
    current_user: User = Depends(get_current_admin_user)
):
    """Initialize all sync services"""
    try:
        # Queue initialization as background task
        task = initialize_sync_services.delay()
        
        return {
            "status": "success",
            "task_id": task.id,
            "message": "Service initialization queued"
        }
        
    except Exception as e:
        logger.error(f"Service initialization failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Service initialization failed: {str(e)}")


@router.post("/services/shutdown")
async def shutdown_services(
    current_user: User = Depends(get_current_admin_user)
):
    """Shutdown all sync services"""
    try:
        from app.tasks.data_sync_tasks import shutdown_sync_services
        task = shutdown_sync_services.delay()
        
        return {
            "status": "success",
            "task_id": task.id,
            "message": "Service shutdown queued"
        }
        
    except Exception as e:
        logger.error(f"Service shutdown failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Service shutdown failed: {str(e)}")


@router.post("/maintenance/cleanup")
async def trigger_maintenance_cleanup(
    current_user: User = Depends(get_current_admin_user)
):
    """Trigger maintenance cleanup tasks"""
    try:
        from app.tasks.data_sync_tasks import scheduled_cleanup
        task = scheduled_cleanup.delay()
        
        return {
            "status": "success",
            "task_id": task.id,
            "message": "Maintenance cleanup queued"
        }
        
    except Exception as e:
        logger.error(f"Maintenance cleanup failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Maintenance cleanup failed: {str(e)}")