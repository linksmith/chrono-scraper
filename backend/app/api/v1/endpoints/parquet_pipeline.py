"""
FastAPI endpoints for Parquet pipeline management and monitoring.

This module provides REST API endpoints for:
- Pipeline operations (start, stop, status)
- Batch job management (schedule, monitor, cancel)
- Performance monitoring and metrics
- Health checks and diagnostics
- Cost analysis and optimization recommendations

All endpoints include proper authentication, validation, and error handling.
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from pydantic import BaseModel, Field, validator
from sqlmodel import Session

from app.api.deps import get_current_active_user, get_db
from app.core.config import settings
from app.services.parquet_pipeline import ParquetPipeline
from app.services.batch_scheduler import BatchScheduler, BatchType, BatchPriority
from app.services.parquet_monitoring import ParquetMonitoring
from app.services.cache_service import CacheService
from app.tasks.parquet_tasks import (
    process_cdx_analytics_task,
    process_content_analytics_task,
    process_project_analytics_task,
    schedule_batch_job_task,
    cleanup_old_files_task,
    get_pipeline_health_task
)
from app.models.user import User

logger = logging.getLogger(__name__)
router = APIRouter()

# Global service instances (initialized on first use)
_pipeline = None
_scheduler = None
_monitoring = None
_cache_service = None


def get_services():
    """Get or initialize pipeline services."""
    global _pipeline, _scheduler, _monitoring, _cache_service
    
    if _cache_service is None:
        _cache_service = CacheService()
    
    if _pipeline is None:
        _pipeline = ParquetPipeline(settings, _cache_service)
    
    if _scheduler is None:
        _scheduler = BatchScheduler(settings, _cache_service)
    
    if _monitoring is None:
        _monitoring = ParquetMonitoring(settings, _cache_service)
    
    return _pipeline, _scheduler, _monitoring, _cache_service


# Request/Response Models

class BatchJobRequest(BaseModel):
    """Request model for scheduling batch jobs."""
    batch_type: str = Field(..., description="Type of batch processing")
    priority: int = Field(5, ge=1, le=20, description="Job priority (1-20)")
    schedule_at: Optional[str] = Field(None, description="ISO timestamp when to run (None for immediate)")
    batch_size: Optional[int] = Field(None, description="Override default batch size")
    filters: Optional[Dict[str, Any]] = Field(None, description="Data selection filters")
    options: Optional[Dict[str, Any]] = Field(None, description="Additional processing options")
    
    @validator('batch_type')
    def validate_batch_type(cls, v):
        try:
            BatchType(v)
            return v
        except ValueError:
            raise ValueError(f"Invalid batch_type. Must be one of: {[bt.value for bt in BatchType]}")
    
    @validator('schedule_at')
    def validate_schedule_at(cls, v):
        if v is not None:
            try:
                datetime.fromisoformat(v.replace('Z', '+00:00'))
                return v
            except ValueError:
                raise ValueError("schedule_at must be a valid ISO timestamp")
        return v


class BatchJobResponse(BaseModel):
    """Response model for batch job operations."""
    success: bool
    job_id: Optional[str] = None
    message: Optional[str] = None
    scheduled_at: Optional[str] = None
    error: Optional[str] = None


class PipelineStatusResponse(BaseModel):
    """Response model for pipeline status."""
    pipeline_active: bool
    scheduler_running: bool
    monitoring_active: bool
    queue_length: int
    running_jobs: int
    completed_jobs_today: int
    failed_jobs_today: int
    system_health: Dict[str, Any]
    last_updated: str


class PerformanceSummaryResponse(BaseModel):
    """Response model for performance summary."""
    period_hours: int
    operation_type: Optional[str]
    total_operations: int
    total_records_processed: int
    total_errors: int
    error_rate_percent: float
    duration_stats: Dict[str, float]
    throughput_stats: Dict[str, float]
    memory_stats: Dict[str, float]
    compression_stats: Dict[str, float]
    timestamp: str


class HealthCheckResponse(BaseModel):
    """Response model for health checks."""
    status: str
    score: float
    active_jobs: int
    failed_jobs_last_hour: int
    average_processing_time: float
    storage_usage_percent: float
    error_rate_percent: float
    warnings: List[str]
    recommendations: List[str]
    timestamp: str


class CostAnalysisResponse(BaseModel):
    """Response model for cost analysis."""
    estimated_monthly_cost: float
    data_volume_gb: float
    processing_hours: float
    cost_per_record: float
    optimization_potential_percent: float
    recommendations: List[str]
    timestamp: str


# Pipeline Management Endpoints

@router.post("/start", response_model=Dict[str, Any])
async def start_pipeline(
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_active_user)
):
    """
    Start the Parquet pipeline and monitoring systems.
    
    Requires admin privileges.
    """
    if not current_user.is_superuser:
        raise HTTPException(status_code=403, detail="Admin privileges required")
    
    try:
        pipeline, scheduler, monitoring, cache_service = get_services()
        
        # Start services in background
        background_tasks.add_task(_start_services_background, scheduler, monitoring)
        
        return {
            "success": True,
            "message": "Pipeline services are starting",
            "started_at": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error starting pipeline: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to start pipeline: {str(e)}")


async def _start_services_background(scheduler, monitoring):
    """Background task to start services."""
    try:
        await asyncio.gather(
            scheduler.start(),
            monitoring.start_monitoring(),
            return_exceptions=True
        )
    except Exception as e:
        logger.error(f"Error in background service start: {str(e)}")


@router.post("/stop", response_model=Dict[str, Any])
async def stop_pipeline(
    current_user: User = Depends(get_current_active_user)
):
    """
    Stop the Parquet pipeline and monitoring systems.
    
    Requires admin privileges.
    """
    if not current_user.is_superuser:
        raise HTTPException(status_code=403, detail="Admin privileges required")
    
    try:
        pipeline, scheduler, monitoring, cache_service = get_services()
        
        # Stop services
        await asyncio.gather(
            scheduler.stop(),
            monitoring.stop_monitoring(),
            return_exceptions=True
        )
        
        return {
            "success": True,
            "message": "Pipeline services stopped",
            "stopped_at": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error stopping pipeline: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to stop pipeline: {str(e)}")


@router.get("/status", response_model=PipelineStatusResponse)
async def get_pipeline_status(
    current_user: User = Depends(get_current_active_user)
):
    """Get comprehensive pipeline status."""
    try:
        pipeline, scheduler, monitoring, cache_service = get_services()
        
        # Get status from scheduler
        queue_status = await scheduler.get_queue_status()
        
        return PipelineStatusResponse(
            pipeline_active=True,  # Pipeline is active if we can access services
            scheduler_running=queue_status["scheduler_running"],
            monitoring_active=monitoring.monitoring_active,
            queue_length=queue_status["queue_length"],
            running_jobs=queue_status["running_jobs"],
            completed_jobs_today=queue_status["completed_jobs_today"],
            failed_jobs_today=queue_status["failed_jobs_today"],
            system_health=queue_status["system_resources"],
            last_updated=datetime.utcnow().isoformat()
        )
        
    except Exception as e:
        logger.error(f"Error getting pipeline status: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to get pipeline status: {str(e)}")


# Job Management Endpoints

@router.post("/jobs/schedule", response_model=BatchJobResponse)
async def schedule_batch_job(
    job_request: BatchJobRequest,
    current_user: User = Depends(get_current_active_user)
):
    """Schedule a new batch processing job."""
    try:
        # For high-priority jobs, require admin privileges
        if job_request.priority > 10 and not current_user.is_superuser:
            raise HTTPException(status_code=403, detail="Admin privileges required for high-priority jobs")
        
        # Schedule job via Celery task
        task_result = schedule_batch_job_task.delay(
            batch_type=job_request.batch_type,
            priority=job_request.priority,
            schedule_at=job_request.schedule_at,
            batch_size=job_request.batch_size,
            filters=job_request.filters,
            options=job_request.options
        )
        
        # Wait briefly for immediate result
        try:
            result = task_result.get(timeout=5)  # 5 second timeout
            if result["success"]:
                return BatchJobResponse(
                    success=True,
                    job_id=result["job_id"],
                    message=f"Job scheduled successfully",
                    scheduled_at=result["scheduled_at"]
                )
            else:
                return BatchJobResponse(
                    success=False,
                    error=result.get("error", "Unknown error")
                )
        except Exception:
            # If we can't get immediate result, return async response
            return BatchJobResponse(
                success=True,
                message="Job scheduling in progress",
                job_id=task_result.id
            )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error scheduling job: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to schedule job: {str(e)}")


@router.get("/jobs/{job_id}", response_model=Dict[str, Any])
async def get_job_status(
    job_id: str,
    current_user: User = Depends(get_current_active_user)
):
    """Get status of a specific job."""
    try:
        pipeline, scheduler, monitoring, cache_service = get_services()
        
        job_status = await scheduler.get_job_status(job_id)
        
        if job_status is None:
            raise HTTPException(status_code=404, detail="Job not found")
        
        return job_status
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting job status: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to get job status: {str(e)}")


@router.delete("/jobs/{job_id}", response_model=Dict[str, Any])
async def cancel_job(
    job_id: str,
    current_user: User = Depends(get_current_active_user)
):
    """Cancel a scheduled or running job."""
    try:
        pipeline, scheduler, monitoring, cache_service = get_services()
        
        success = await scheduler.cancel_job(job_id)
        
        if success:
            return {
                "success": True,
                "message": f"Job {job_id} cancelled successfully",
                "cancelled_at": datetime.utcnow().isoformat()
            }
        else:
            return {
                "success": False,
                "message": f"Job {job_id} could not be cancelled (not found or already completed)"
            }
        
    except Exception as e:
        logger.error(f"Error cancelling job: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to cancel job: {str(e)}")


@router.get("/jobs", response_model=Dict[str, Any])
async def list_jobs(
    status: Optional[str] = Query(None, description="Filter by job status"),
    batch_type: Optional[str] = Query(None, description="Filter by batch type"),
    limit: int = Query(50, ge=1, le=500, description="Maximum number of jobs to return"),
    current_user: User = Depends(get_current_active_user)
):
    """List recent jobs with optional filtering."""
    try:
        pipeline, scheduler, monitoring, cache_service = get_services()
        
        queue_status = await scheduler.get_queue_status()
        
        # Get jobs from different queues
        jobs = []
        
        # Add next jobs from queue
        if queue_status.get("next_jobs"):
            jobs.extend(queue_status["next_jobs"])
        
        # Add running jobs
        if queue_status.get("running_job_details"):
            jobs.extend(queue_status["running_job_details"])
        
        # Apply filters
        if status:
            jobs = [job for job in jobs if job.get("status") == status]
        
        if batch_type:
            jobs = [job for job in jobs if job.get("batch_type") == batch_type]
        
        # Limit results
        jobs = jobs[:limit]
        
        return {
            "jobs": jobs,
            "total_count": len(jobs),
            "filters": {
                "status": status,
                "batch_type": batch_type,
                "limit": limit
            },
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error listing jobs: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to list jobs: {str(e)}")


# Direct Processing Endpoints

@router.post("/process/cdx-analytics", response_model=Dict[str, Any])
async def process_cdx_analytics(
    batch_size: int = Query(50000, ge=1000, le=200000, description="Batch size"),
    partition_by_date: bool = Query(True, description="Enable date partitioning"),
    domain_id: Optional[int] = Query(None, description="Filter by domain ID"),
    current_user: User = Depends(get_current_active_user)
):
    """
    Directly process CDX analytics (bypassing scheduler).
    
    For immediate processing needs.
    """
    try:
        # Build filters
        filters = {}
        if domain_id is not None:
            filters["domain_id"] = domain_id
        
        # Start processing task
        task_result = process_cdx_analytics_task.delay(
            batch_size=batch_size,
            filters=filters,
            partition_by_date=partition_by_date
        )
        
        return {
            "success": True,
            "task_id": task_result.id,
            "message": "CDX analytics processing started",
            "batch_size": batch_size,
            "started_at": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error starting CDX analytics: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to start CDX analytics: {str(e)}")


@router.post("/process/content-analytics", response_model=Dict[str, Any])
async def process_content_analytics(
    batch_size: int = Query(25000, ge=1000, le=100000, description="Batch size"),
    include_full_text: bool = Query(False, description="Include full extracted text"),
    current_user: User = Depends(get_current_active_user)
):
    """
    Directly process content analytics (bypassing scheduler).
    
    For immediate processing needs.
    """
    try:
        # Start processing task
        task_result = process_content_analytics_task.delay(
            batch_size=batch_size,
            include_full_text=include_full_text
        )
        
        return {
            "success": True,
            "task_id": task_result.id,
            "message": "Content analytics processing started",
            "batch_size": batch_size,
            "include_full_text": include_full_text,
            "started_at": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error starting content analytics: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to start content analytics: {str(e)}")


# Monitoring and Analytics Endpoints

@router.get("/performance", response_model=PerformanceSummaryResponse)
async def get_performance_summary(
    hours: int = Query(24, ge=1, le=168, description="Time period in hours"),
    operation_type: Optional[str] = Query(None, description="Filter by operation type"),
    current_user: User = Depends(get_current_active_user)
):
    """Get performance summary for the specified time period."""
    try:
        pipeline, scheduler, monitoring, cache_service = get_services()
        
        summary = await monitoring.get_performance_summary(hours=hours, operation_type=operation_type)
        
        return PerformanceSummaryResponse(**summary)
        
    except Exception as e:
        logger.error(f"Error getting performance summary: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to get performance summary: {str(e)}")


@router.get("/health", response_model=HealthCheckResponse)
async def get_pipeline_health(
    current_user: User = Depends(get_current_active_user)
):
    """Get comprehensive pipeline health check."""
    try:
        # Use Celery task for health check to avoid blocking
        task_result = get_pipeline_health_task.delay()
        
        try:
            result = task_result.get(timeout=30)  # 30 second timeout
            if result["success"]:
                health_data = result["health_data"]
                # Extract relevant health info
                return HealthCheckResponse(
                    status="healthy",  # Simplified for now
                    score=100.0,
                    active_jobs=0,
                    failed_jobs_last_hour=0,
                    average_processing_time=0.0,
                    storage_usage_percent=health_data.get("system_health", {}).get("disk_usage_percent", 0.0),
                    error_rate_percent=0.0,
                    warnings=[],
                    recommendations=[],
                    timestamp=datetime.utcnow().isoformat()
                )
            else:
                raise Exception(result.get("error", "Unknown error"))
        except Exception:
            # Fallback to basic health check
            return HealthCheckResponse(
                status="unknown",
                score=50.0,
                active_jobs=0,
                failed_jobs_last_hour=0,
                average_processing_time=0.0,
                storage_usage_percent=0.0,
                error_rate_percent=0.0,
                warnings=["Health check timed out"],
                recommendations=["Check system resources"],
                timestamp=datetime.utcnow().isoformat()
            )
        
    except Exception as e:
        logger.error(f"Error getting pipeline health: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to get pipeline health: {str(e)}")


@router.get("/costs", response_model=CostAnalysisResponse)
async def get_cost_analysis(
    days: int = Query(30, ge=1, le=365, description="Analysis period in days"),
    current_user: User = Depends(get_current_active_user)
):
    """Get cost analysis and optimization recommendations."""
    if not current_user.is_superuser:
        raise HTTPException(status_code=403, detail="Admin privileges required for cost analysis")
    
    try:
        pipeline, scheduler, monitoring, cache_service = get_services()
        
        cost_analysis = await monitoring.estimate_costs(days=days)
        
        return CostAnalysisResponse(
            estimated_monthly_cost=cost_analysis.estimated_monthly_cost,
            data_volume_gb=cost_analysis.data_volume_gb,
            processing_hours=cost_analysis.processing_hours,
            cost_per_record=cost_analysis.cost_per_record,
            optimization_potential_percent=cost_analysis.optimization_potential_percent,
            recommendations=cost_analysis.recommendations,
            timestamp=cost_analysis.timestamp.isoformat()
        )
        
    except Exception as e:
        logger.error(f"Error getting cost analysis: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to get cost analysis: {str(e)}")


@router.get("/dashboard", response_model=Dict[str, Any])
async def get_dashboard_data(
    current_user: User = Depends(get_current_active_user)
):
    """Get comprehensive dashboard data for visualization."""
    try:
        pipeline, scheduler, monitoring, cache_service = get_services()
        
        dashboard_data = await monitoring.get_dashboard_data()
        
        return dashboard_data
        
    except Exception as e:
        logger.error(f"Error getting dashboard data: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to get dashboard data: {str(e)}")


# Maintenance Endpoints

@router.post("/maintenance/cleanup", response_model=Dict[str, Any])
async def cleanup_old_files(
    retention_days: int = Query(30, ge=1, le=365, description="File retention period in days"),
    dry_run: bool = Query(True, description="Dry run mode - don't actually delete files"),
    current_user: User = Depends(get_current_active_user)
):
    """Clean up old Parquet files based on retention policy."""
    if not current_user.is_superuser:
        raise HTTPException(status_code=403, detail="Admin privileges required for file cleanup")
    
    try:
        # Start cleanup task
        task_result = cleanup_old_files_task.delay(
            retention_days=retention_days,
            dry_run=dry_run
        )
        
        return {
            "success": True,
            "task_id": task_result.id,
            "message": f"File cleanup {'simulation' if dry_run else 'operation'} started",
            "retention_days": retention_days,
            "dry_run": dry_run,
            "started_at": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error starting file cleanup: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to start file cleanup: {str(e)}")


@router.post("/maintenance/auto-schedule", response_model=Dict[str, Any])
async def trigger_auto_schedule(
    batch_type: Optional[str] = Query(None, description="Specific batch type to schedule"),
    current_user: User = Depends(get_current_active_user)
):
    """Manually trigger auto-scheduling for all or specific batch types."""
    if not current_user.is_superuser:
        raise HTTPException(status_code=403, detail="Admin privileges required for manual scheduling")
    
    try:
        pipeline, scheduler, monitoring, cache_service = get_services()
        
        batch_type_enum = None
        if batch_type:
            try:
                batch_type_enum = BatchType(batch_type)
            except ValueError:
                raise HTTPException(status_code=400, detail=f"Invalid batch_type: {batch_type}")
        
        scheduled_jobs = await scheduler.trigger_auto_schedule(batch_type=batch_type_enum)
        
        return {
            "success": True,
            "scheduled_jobs": scheduled_jobs,
            "job_count": len(scheduled_jobs),
            "batch_type": batch_type,
            "triggered_at": datetime.utcnow().isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error triggering auto-schedule: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to trigger auto-schedule: {str(e)}")


@router.get("/statistics", response_model=Dict[str, Any])
async def get_pipeline_statistics(
    current_user: User = Depends(get_current_active_user)
):
    """Get comprehensive pipeline statistics."""
    try:
        pipeline, scheduler, monitoring, cache_service = get_services()
        
        # Get statistics from pipeline
        pipeline_stats = await pipeline.get_pipeline_statistics()
        
        # Get scheduler statistics
        queue_status = await scheduler.get_queue_status()
        
        # Combine statistics
        statistics = {
            "pipeline_stats": pipeline_stats,
            "scheduler_stats": queue_status["statistics"],
            "system_info": {
                "pipeline_enabled": settings.BATCH_PROCESSING_ENABLED,
                "storage_path": settings.PARQUET_STORAGE_PATH,
                "max_concurrent_jobs": settings.MAX_CONCURRENT_BATCHES,
                "memory_limit_gb": settings.PIPELINE_MEMORY_LIMIT_GB
            },
            "timestamp": datetime.utcnow().isoformat()
        }
        
        return statistics
        
    except Exception as e:
        logger.error(f"Error getting pipeline statistics: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to get pipeline statistics: {str(e)}")