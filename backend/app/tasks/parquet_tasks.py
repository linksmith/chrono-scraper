"""
Celery tasks for distributed Parquet pipeline processing.

This module provides Celery tasks for:
- CDX analytics batch processing
- Content analytics processing
- Project analytics aggregation
- Event data processing
- Batch job management and monitoring

All tasks are designed for distributed execution with proper error handling,
progress tracking, and resource management.
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
import json
import traceback

from celery import Task, current_task
from celery.exceptions import Retry
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import settings
from app.services.parquet_pipeline import ParquetPipeline
from app.services.batch_scheduler import BatchScheduler, BatchType, BatchPriority
from app.services.cache_service import CacheService
from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


class ParquetTask(Task):
    """Base task class for Parquet processing with resource management."""
    
    def __init__(self):
        self.pipeline = None
        self.cache_service = None
        self._setup_services()
    
    def _setup_services(self):
        """Initialize services (called once per worker)."""
        try:
            self.cache_service = CacheService()
            self.pipeline = ParquetPipeline(settings, self.cache_service)
            logger.info("Parquet pipeline services initialized")
        except Exception as e:
            logger.error(f"Failed to initialize pipeline services: {str(e)}")
            raise
    
    def on_failure(self, exc, task_id, args, kwargs, einfo):
        """Handle task failure."""
        error_details = {
            "task_id": task_id,
            "task_name": self.name,
            "error": str(exc),
            "traceback": str(einfo),
            "args": args,
            "kwargs": kwargs,
            "timestamp": datetime.utcnow().isoformat()
        }
        
        logger.error(f"Parquet task {task_id} failed: {str(exc)}")
        
        # Store error details in cache
        if self.cache_service:
            asyncio.create_task(
                self.cache_service.set(f"task_error:{task_id}", error_details, ttl=86400)
            )
    
    def on_success(self, retval, task_id, args, kwargs):
        """Handle task success."""
        success_details = {
            "task_id": task_id,
            "task_name": self.name,
            "result": retval,
            "timestamp": datetime.utcnow().isoformat()
        }
        
        logger.info(f"Parquet task {task_id} completed successfully")
        
        # Store success details
        if self.cache_service:
            asyncio.create_task(
                self.cache_service.set(f"task_result:{task_id}", success_details, ttl=3600)
            )
    
    def update_progress(self, current: int, total: int, message: str = ""):
        """Update task progress."""
        if current_task:
            progress = (current / max(total, 1)) * 100
            current_task.update_state(
                state='PROGRESS',
                meta={
                    'current': current,
                    'total': total,
                    'progress': progress,
                    'message': message,
                    'timestamp': datetime.utcnow().isoformat()
                }
            )


@celery_app.task(
    bind=True,
    base=ParquetTask,
    name="parquet.process_cdx_analytics",
    max_retries=3,
    default_retry_delay=300,  # 5 minutes
    priority=7
)
def process_cdx_analytics_task(
    self,
    batch_size: int = 50000,
    filters: Optional[Dict[str, Any]] = None,
    partition_by_date: bool = True,
    job_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Process CDX records to Parquet format for analytics.
    
    Args:
        batch_size: Number of records per batch
        filters: Additional SQL filters
        partition_by_date: Enable date-based partitioning
        job_id: Associated batch job ID
        
    Returns:
        Processing result with file paths and statistics
    """
    try:
        logger.info(f"Starting CDX analytics processing (batch_size={batch_size})")
        self.update_progress(0, 100, "Initializing CDX analytics processing")
        
        if not self.pipeline:
            self._setup_services()
        
        # Run the processing
        async def _process():
            result = await self.pipeline.process_cdx_records(
                batch_size=batch_size,
                filters=filters or {},
                partition_by_date=partition_by_date
            )
            return result
        
        # Execute async function
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(_process())
        finally:
            loop.close()
        
        self.update_progress(100, 100, "CDX analytics processing completed")
        
        # Parse result
        file_paths = json.loads(result) if isinstance(result, str) else result
        
        # Get pipeline statistics
        async def _get_stats():
            return await self.pipeline.get_pipeline_statistics()
        
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            stats = loop.run_until_complete(_get_stats())
        finally:
            loop.close()
        
        success_result = {
            "success": True,
            "file_paths": file_paths,
            "file_count": len(file_paths),
            "statistics": stats,
            "job_id": job_id,
            "completed_at": datetime.utcnow().isoformat()
        }
        
        logger.info(f"CDX analytics processing completed: {len(file_paths)} files created")
        return success_result
        
    except Exception as exc:
        error_msg = f"CDX analytics processing failed: {str(exc)}"
        logger.error(f"{error_msg}\n{traceback.format_exc()}")
        
        # Retry with exponential backoff
        if self.request.retries < self.max_retries:
            retry_delay = 300 * (2 ** self.request.retries)  # 5, 10, 20 minutes
            logger.info(f"Retrying CDX analytics task in {retry_delay} seconds")
            raise self.retry(countdown=retry_delay, exc=exc)
        
        return {
            "success": False,
            "error": error_msg,
            "job_id": job_id,
            "failed_at": datetime.utcnow().isoformat()
        }


@celery_app.task(
    bind=True,
    base=ParquetTask,
    name="parquet.process_content_analytics",
    max_retries=3,
    default_retry_delay=600,  # 10 minutes
    priority=6
)
def process_content_analytics_task(
    self,
    batch_size: int = 25000,
    include_full_text: bool = False,
    job_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Process content data to Parquet format for analytics.
    
    Args:
        batch_size: Number of records per batch
        include_full_text: Include full extracted text
        job_id: Associated batch job ID
        
    Returns:
        Processing result with file paths and statistics
    """
    try:
        logger.info(f"Starting content analytics processing (batch_size={batch_size})")
        self.update_progress(0, 100, "Initializing content analytics processing")
        
        if not self.pipeline:
            self._setup_services()
        
        # Run the processing
        async def _process():
            result = await self.pipeline.process_content_analytics(
                batch_size=batch_size,
                include_full_text=include_full_text
            )
            return result
        
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(_process())
        finally:
            loop.close()
        
        self.update_progress(100, 100, "Content analytics processing completed")
        
        # Parse result
        file_paths = json.loads(result) if isinstance(result, str) else result
        
        # Get statistics
        async def _get_stats():
            return await self.pipeline.get_pipeline_statistics()
        
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            stats = loop.run_until_complete(_get_stats())
        finally:
            loop.close()
        
        success_result = {
            "success": True,
            "file_paths": file_paths,
            "file_count": len(file_paths),
            "statistics": stats,
            "job_id": job_id,
            "completed_at": datetime.utcnow().isoformat()
        }
        
        logger.info(f"Content analytics processing completed: {len(file_paths)} files created")
        return success_result
        
    except Exception as exc:
        error_msg = f"Content analytics processing failed: {str(exc)}"
        logger.error(f"{error_msg}\n{traceback.format_exc()}")
        
        if self.request.retries < self.max_retries:
            retry_delay = 600 * (2 ** self.request.retries)  # 10, 20, 40 minutes
            logger.info(f"Retrying content analytics task in {retry_delay} seconds")
            raise self.retry(countdown=retry_delay, exc=exc)
        
        return {
            "success": False,
            "error": error_msg,
            "job_id": job_id,
            "failed_at": datetime.utcnow().isoformat()
        }


@celery_app.task(
    bind=True,
    base=ParquetTask,
    name="parquet.process_project_analytics",
    max_retries=3,
    default_retry_delay=180,  # 3 minutes
    priority=5
)
def process_project_analytics_task(
    self,
    batch_size: int = 10000,
    job_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Process project analytics data to Parquet format.
    
    Args:
        batch_size: Number of records per batch
        job_id: Associated batch job ID
        
    Returns:
        Processing result with file paths and statistics
    """
    try:
        logger.info("Starting project analytics processing")
        self.update_progress(0, 100, "Initializing project analytics processing")
        
        if not self.pipeline:
            self._setup_services()
        
        # Run the processing
        async def _process():
            result = await self.pipeline.process_project_analytics(
                batch_size=batch_size
            )
            return result
        
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(_process())
        finally:
            loop.close()
        
        self.update_progress(100, 100, "Project analytics processing completed")
        
        # Parse result
        file_paths = json.loads(result) if isinstance(result, str) else result
        
        # Get statistics
        async def _get_stats():
            return await self.pipeline.get_pipeline_statistics()
        
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            stats = loop.run_until_complete(_get_stats())
        finally:
            loop.close()
        
        success_result = {
            "success": True,
            "file_paths": file_paths,
            "file_count": len(file_paths),
            "statistics": stats,
            "job_id": job_id,
            "completed_at": datetime.utcnow().isoformat()
        }
        
        logger.info(f"Project analytics processing completed: {len(file_paths)} files created")
        return success_result
        
    except Exception as exc:
        error_msg = f"Project analytics processing failed: {str(exc)}"
        logger.error(f"{error_msg}\n{traceback.format_exc()}")
        
        if self.request.retries < self.max_retries:
            retry_delay = 180 * (2 ** self.request.retries)  # 3, 6, 12 minutes
            logger.info(f"Retrying project analytics task in {retry_delay} seconds")
            raise self.retry(countdown=retry_delay, exc=exc)
        
        return {
            "success": False,
            "error": error_msg,
            "job_id": job_id,
            "failed_at": datetime.utcnow().isoformat()
        }


@celery_app.task(
    bind=True,
    base=ParquetTask,
    name="parquet.process_events",
    max_retries=2,
    default_retry_delay=60,  # 1 minute
    priority=4
)
def process_events_task(
    self,
    event_data: List[Dict[str, Any]],
    event_type: str = "system",
    job_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Process event data to Parquet format.
    
    Args:
        event_data: List of event dictionaries
        event_type: Type of events
        job_id: Associated batch job ID
        
    Returns:
        Processing result with file paths and statistics
    """
    try:
        logger.info(f"Starting {event_type} events processing ({len(event_data)} events)")
        self.update_progress(0, 100, f"Processing {len(event_data)} {event_type} events")
        
        if not self.pipeline:
            self._setup_services()
        
        # Run the processing
        async def _process():
            result = await self.pipeline.process_events(
                event_data=event_data,
                event_type=event_type
            )
            return result
        
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(_process())
        finally:
            loop.close()
        
        self.update_progress(100, 100, "Events processing completed")
        
        # Parse result
        file_paths = json.loads(result) if isinstance(result, str) else result
        
        success_result = {
            "success": True,
            "file_paths": file_paths,
            "file_count": len(file_paths),
            "event_count": len(event_data),
            "event_type": event_type,
            "job_id": job_id,
            "completed_at": datetime.utcnow().isoformat()
        }
        
        logger.info(f"Events processing completed: {len(file_paths)} files created")
        return success_result
        
    except Exception as exc:
        error_msg = f"Events processing failed: {str(exc)}"
        logger.error(f"{error_msg}\n{traceback.format_exc()}")
        
        if self.request.retries < self.max_retries:
            retry_delay = 60 * (2 ** self.request.retries)  # 1, 2 minutes
            logger.info(f"Retrying events task in {retry_delay} seconds")
            raise self.retry(countdown=retry_delay, exc=exc)
        
        return {
            "success": False,
            "error": error_msg,
            "job_id": job_id,
            "failed_at": datetime.utcnow().isoformat()
        }


@celery_app.task(
    bind=True,
    name="parquet.schedule_batch_job",
    max_retries=1,
    priority=8
)
def schedule_batch_job_task(
    self,
    batch_type: str,
    priority: int = 5,
    schedule_at: Optional[str] = None,
    batch_size: Optional[int] = None,
    filters: Optional[Dict[str, Any]] = None,
    options: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Schedule a batch processing job through Celery.
    
    Args:
        batch_type: Type of batch processing
        priority: Job priority (1-20)
        schedule_at: ISO timestamp when to run (None for immediate)
        batch_size: Override default batch size
        filters: Data selection filters
        options: Additional processing options
        
    Returns:
        Job scheduling result
    """
    try:
        logger.info(f"Scheduling {batch_type} batch job")
        
        # Convert string types back to enums
        batch_type_enum = BatchType(batch_type)
        priority_enum = BatchPriority(priority)
        
        # Parse schedule time
        scheduled_at = None
        if schedule_at:
            scheduled_at = datetime.fromisoformat(schedule_at.replace('Z', '+00:00'))
        
        # Initialize scheduler
        cache_service = CacheService()
        scheduler = BatchScheduler(settings, cache_service)
        
        # Schedule the job
        async def _schedule():
            return await scheduler.schedule_job(
                batch_type=batch_type_enum,
                priority=priority_enum,
                schedule_at=scheduled_at,
                batch_size=batch_size,
                filters=filters,
                options=options
            )
        
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            job_id = loop.run_until_complete(_schedule())
        finally:
            loop.close()
        
        return {
            "success": True,
            "job_id": job_id,
            "batch_type": batch_type,
            "scheduled_at": datetime.utcnow().isoformat()
        }
        
    except Exception as exc:
        error_msg = f"Failed to schedule batch job: {str(exc)}"
        logger.error(f"{error_msg}\n{traceback.format_exc()}")
        
        return {
            "success": False,
            "error": error_msg,
            "failed_at": datetime.utcnow().isoformat()
        }


@celery_app.task(
    name="parquet.cleanup_old_files",
    max_retries=1,
    priority=2
)
def cleanup_old_files_task(
    retention_days: int = 30,
    dry_run: bool = False
) -> Dict[str, Any]:
    """
    Clean up old Parquet files based on retention policy.
    
    Args:
        retention_days: Number of days to retain files
        dry_run: If True, only report what would be deleted
        
    Returns:
        Cleanup result
    """
    try:
        import os
        from pathlib import Path
        
        logger.info(f"Starting Parquet file cleanup (retention: {retention_days} days, dry_run: {dry_run})")
        
        storage_path = Path(settings.PARQUET_STORAGE_PATH)
        if not storage_path.exists():
            return {
                "success": True,
                "message": "Storage path does not exist",
                "files_deleted": 0,
                "space_freed_mb": 0
            }
        
        cutoff_date = datetime.utcnow() - timedelta(days=retention_days)
        deleted_files = 0
        space_freed = 0
        
        # Find old files
        for file_path in storage_path.rglob("*.parquet"):
            try:
                file_mtime = datetime.fromtimestamp(file_path.stat().st_mtime)
                if file_mtime < cutoff_date:
                    file_size = file_path.stat().st_size
                    
                    if dry_run:
                        logger.info(f"Would delete: {file_path} ({file_size} bytes)")
                    else:
                        file_path.unlink()
                        logger.info(f"Deleted: {file_path}")
                    
                    deleted_files += 1
                    space_freed += file_size
                    
            except Exception as e:
                logger.warning(f"Error processing file {file_path}: {str(e)}")
        
        space_freed_mb = space_freed / (1024 * 1024)
        
        result = {
            "success": True,
            "files_deleted": deleted_files,
            "space_freed_mb": round(space_freed_mb, 2),
            "retention_days": retention_days,
            "dry_run": dry_run,
            "completed_at": datetime.utcnow().isoformat()
        }
        
        logger.info(f"File cleanup completed: {deleted_files} files, {space_freed_mb:.2f} MB freed")
        return result
        
    except Exception as exc:
        error_msg = f"File cleanup failed: {str(exc)}"
        logger.error(f"{error_msg}\n{traceback.format_exc()}")
        
        return {
            "success": False,
            "error": error_msg,
            "failed_at": datetime.utcnow().isoformat()
        }


@celery_app.task(
    name="parquet.get_pipeline_health",
    priority=9
)
def get_pipeline_health_task() -> Dict[str, Any]:
    """
    Get comprehensive pipeline health status.
    
    Returns:
        Pipeline health information
    """
    try:
        # Initialize services
        cache_service = CacheService()
        pipeline = ParquetPipeline(settings, cache_service)
        
        # Get pipeline statistics
        async def _get_health():
            stats = await pipeline.get_pipeline_statistics()
            
            # Add system health indicators
            import psutil
            
            health_data = {
                "pipeline_stats": stats,
                "system_health": {
                    "cpu_percent": psutil.cpu_percent(interval=1),
                    "memory_percent": psutil.virtual_memory().percent,
                    "disk_usage_percent": psutil.disk_usage('/').percent,
                    "load_average": list(psutil.getloadavg()) if hasattr(psutil, 'getloadavg') else None
                },
                "service_status": {
                    "pipeline_initialized": True,
                    "storage_accessible": Path(settings.PARQUET_STORAGE_PATH).exists(),
                    "timestamp": datetime.utcnow().isoformat()
                }
            }
            
            return health_data
        
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            health_data = loop.run_until_complete(_get_health())
        finally:
            loop.close()
        
        return {
            "success": True,
            "health_data": health_data
        }
        
    except Exception as exc:
        error_msg = f"Health check failed: {str(exc)}"
        logger.error(f"{error_msg}\n{traceback.format_exc()}")
        
        return {
            "success": False,
            "error": error_msg,
            "timestamp": datetime.utcnow().isoformat()
        }


# Periodic tasks configuration
@celery_app.task(
    name="parquet.auto_schedule_analytics",
    priority=6
)
def auto_schedule_analytics_task() -> Dict[str, Any]:
    """
    Automatically schedule analytics processing based on data volume and timing.
    
    This task runs periodically to check if analytics processing should be triggered
    based on configuration and data availability.
    """
    try:
        if not settings.BATCH_PROCESSING_ENABLED:
            return {
                "success": True,
                "message": "Batch processing is disabled",
                "scheduled_jobs": []
            }
        
        logger.info("Running auto-schedule analytics check")
        
        # Initialize scheduler
        cache_service = CacheService()
        scheduler = BatchScheduler(settings, cache_service)
        
        # Trigger auto-scheduling
        async def _auto_schedule():
            return await scheduler.trigger_auto_schedule()
        
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            scheduled_jobs = loop.run_until_complete(_auto_schedule())
        finally:
            loop.close()
        
        result = {
            "success": True,
            "scheduled_jobs": scheduled_jobs,
            "job_count": len(scheduled_jobs),
            "timestamp": datetime.utcnow().isoformat()
        }
        
        logger.info(f"Auto-scheduling completed: {len(scheduled_jobs)} jobs scheduled")
        return result
        
    except Exception as exc:
        error_msg = f"Auto-scheduling failed: {str(exc)}"
        logger.error(f"{error_msg}\n{traceback.format_exc()}")
        
        return {
            "success": False,
            "error": error_msg,
            "timestamp": datetime.utcnow().isoformat()
        }