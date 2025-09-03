"""
Batch Processing Scheduler for automated Parquet pipeline operations.

This service manages automated scheduling of batch processing operations with:
- Configurable processing intervals (5 min, hourly, daily)
- Priority queues for different data types
- Resource usage monitoring and throttling
- Failure recovery and retry logic
- Progress tracking and notifications

The scheduler ensures efficient resource utilization while maintaining
system performance and reliability.
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Set, Tuple
from dataclasses import dataclass, field
from enum import Enum
import json
import psutil
from contextlib import asynccontextmanager

from sqlmodel import Session, select, func
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import Settings
from app.core.database import engine
from app.services.parquet_pipeline import ParquetPipeline
from app.services.cache_service import CacheService
from app.models.scraping import ScrapePage, ScrapePageStatus

logger = logging.getLogger(__name__)


class BatchType(str, Enum):
    """Types of batch processing operations."""
    CDX_ANALYTICS = "cdx_analytics"
    CONTENT_ANALYTICS = "content_analytics" 
    PROJECT_ANALYTICS = "project_analytics"
    SYSTEM_EVENTS = "system_events"


class BatchPriority(int, Enum):
    """Priority levels for batch operations."""
    LOW = 1
    NORMAL = 5
    HIGH = 10
    CRITICAL = 20


class BatchStatus(str, Enum):
    """Status of batch processing operations."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    PAUSED = "paused"


@dataclass
class BatchJob:
    """Represents a batch processing job."""
    job_id: str
    batch_type: BatchType
    priority: BatchPriority
    created_at: datetime
    scheduled_at: datetime
    status: BatchStatus = BatchStatus.PENDING
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    progress: float = 0.0
    error_message: Optional[str] = None
    retry_count: int = 0
    max_retries: int = 3
    
    # Job configuration
    batch_size: Optional[int] = None
    filters: Optional[Dict[str, Any]] = None
    options: Dict[str, Any] = field(default_factory=dict)
    
    # Resource requirements
    estimated_memory_mb: int = 512
    estimated_duration_minutes: int = 10
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            'job_id': self.job_id,
            'batch_type': self.batch_type.value,
            'priority': self.priority.value,
            'created_at': self.created_at.isoformat(),
            'scheduled_at': self.scheduled_at.isoformat(),
            'status': self.status.value,
            'started_at': self.started_at.isoformat() if self.started_at else None,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
            'progress': self.progress,
            'error_message': self.error_message,
            'retry_count': self.retry_count,
            'max_retries': self.max_retries,
            'batch_size': self.batch_size,
            'filters': self.filters,
            'options': self.options,
            'estimated_memory_mb': self.estimated_memory_mb,
            'estimated_duration_minutes': self.estimated_duration_minutes
        }


@dataclass
class SystemResources:
    """Current system resource utilization."""
    cpu_percent: float
    memory_percent: float
    memory_available_mb: float
    disk_free_gb: float
    active_processes: int
    
    def has_capacity_for(self, job: BatchJob) -> bool:
        """Check if system has capacity for a job."""
        # Conservative resource checks
        memory_threshold = 85.0  # Don't use more than 85% memory
        cpu_threshold = 80.0     # Don't use more than 80% CPU
        
        return (
            self.memory_percent < memory_threshold and
            self.memory_available_mb > job.estimated_memory_mb * 1.5 and  # 1.5x safety margin
            self.cpu_percent < cpu_threshold and
            self.disk_free_gb > 1.0  # At least 1GB free space
        )


class BatchScheduler:
    """
    Automated batch processing scheduler with resource management and monitoring.
    
    Features:
    - Priority-based job queue
    - Resource usage monitoring
    - Automatic retry with backoff
    - Progress tracking and notifications
    - Configurable processing intervals
    """
    
    def __init__(self, settings: Settings, cache_service: Optional[CacheService] = None):
        self.settings = settings
        self.cache_service = cache_service or CacheService()
        
        # Initialize pipeline
        self.pipeline = ParquetPipeline(settings, cache_service)
        
        # Job management
        self.job_queue: List[BatchJob] = []
        self.running_jobs: Dict[str, BatchJob] = {}
        self.completed_jobs: List[BatchJob] = []
        self.failed_jobs: List[BatchJob] = []
        
        # Scheduler state
        self.is_running = False
        self.is_paused = False
        self.last_resource_check = datetime.utcnow()
        self.resource_check_interval = timedelta(seconds=30)
        
        # Processing limits
        self.max_concurrent_jobs = settings.MAX_CONCURRENT_BATCHES
        self.memory_limit_gb = settings.PIPELINE_MEMORY_LIMIT_GB
        self.processing_timeout = timedelta(minutes=settings.PIPELINE_TIMEOUT_MINUTES)
        
        # Auto-scheduling configuration
        self.auto_schedule_intervals = {
            BatchType.CDX_ANALYTICS: timedelta(minutes=settings.BATCH_PROCESSING_INTERVAL_MINUTES),
            BatchType.CONTENT_ANALYTICS: timedelta(hours=2),
            BatchType.PROJECT_ANALYTICS: timedelta(hours=6),
            BatchType.SYSTEM_EVENTS: timedelta(minutes=15)
        }
        self.last_auto_schedule: Dict[BatchType, datetime] = {}
        
        # Statistics
        self.stats = {
            "total_jobs_processed": 0,
            "successful_jobs": 0,
            "failed_jobs": 0,
            "average_processing_time": 0.0,
            "total_records_processed": 0,
            "scheduler_uptime": datetime.utcnow()
        }
        
        logger.info("BatchScheduler initialized with max concurrent jobs: %d", self.max_concurrent_jobs)
    
    async def start(self):
        """Start the batch scheduler."""
        if self.is_running:
            logger.warning("Scheduler is already running")
            return
        
        self.is_running = True
        self.stats["scheduler_uptime"] = datetime.utcnow()
        
        logger.info("Starting batch scheduler")
        
        try:
            await asyncio.gather(
                self._scheduler_loop(),
                self._resource_monitor_loop(),
                self._auto_schedule_loop(),
                self._job_timeout_monitor(),
                return_exceptions=True
            )
        except Exception as e:
            logger.error(f"Scheduler error: {str(e)}")
            self.is_running = False
            raise
    
    async def stop(self):
        """Stop the batch scheduler gracefully."""
        logger.info("Stopping batch scheduler")
        self.is_running = False
        
        # Wait for running jobs to complete (with timeout)
        if self.running_jobs:
            logger.info(f"Waiting for {len(self.running_jobs)} running jobs to complete")
            timeout = 300  # 5 minutes max wait
            start_time = datetime.utcnow()
            
            while self.running_jobs and (datetime.utcnow() - start_time).seconds < timeout:
                await asyncio.sleep(1)
            
            # Cancel remaining jobs
            for job in self.running_jobs.values():
                job.status = BatchStatus.CANCELLED
                logger.info(f"Cancelled job {job.job_id}")
        
        logger.info("Batch scheduler stopped")
    
    async def pause(self):
        """Pause the scheduler (stop taking new jobs)."""
        self.is_paused = True
        logger.info("Batch scheduler paused")
    
    async def resume(self):
        """Resume the scheduler."""
        self.is_paused = False
        logger.info("Batch scheduler resumed")
    
    async def schedule_job(
        self,
        batch_type: BatchType,
        priority: BatchPriority = BatchPriority.NORMAL,
        schedule_at: Optional[datetime] = None,
        batch_size: Optional[int] = None,
        filters: Optional[Dict[str, Any]] = None,
        options: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Schedule a new batch processing job.
        
        Args:
            batch_type: Type of batch processing
            priority: Job priority
            schedule_at: When to run the job (None for immediate)
            batch_size: Override default batch size
            filters: Additional filters for data selection
            options: Additional processing options
            
        Returns:
            Job ID for tracking
        """
        job_id = self._generate_job_id(batch_type)
        
        job = BatchJob(
            job_id=job_id,
            batch_type=batch_type,
            priority=priority,
            created_at=datetime.utcnow(),
            scheduled_at=schedule_at or datetime.utcnow(),
            batch_size=batch_size or self._get_default_batch_size(batch_type),
            filters=filters or {},
            options=options or {}
        )
        
        # Estimate resource requirements
        job.estimated_memory_mb, job.estimated_duration_minutes = await self._estimate_job_requirements(job)
        
        # Add to queue
        self.job_queue.append(job)
        self._sort_job_queue()
        
        logger.info(f"Scheduled {batch_type.value} job {job_id} with priority {priority.value}")
        
        # Cache job for external tracking
        await self.cache_service.set(f"batch_job:{job_id}", job.to_dict(), ttl=86400)  # 24 hours
        
        return job_id
    
    async def cancel_job(self, job_id: str) -> bool:
        """Cancel a scheduled or running job."""
        # Check queue
        for i, job in enumerate(self.job_queue):
            if job.job_id == job_id:
                job.status = BatchStatus.CANCELLED
                self.job_queue.pop(i)
                logger.info(f"Cancelled queued job {job_id}")
                return True
        
        # Check running jobs
        if job_id in self.running_jobs:
            job = self.running_jobs[job_id]
            job.status = BatchStatus.CANCELLED
            logger.info(f"Cancelled running job {job_id}")
            return True
        
        logger.warning(f"Job {job_id} not found for cancellation")
        return False
    
    async def get_job_status(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Get status of a specific job."""
        # Check cache first
        cached_job = await self.cache_service.get(f"batch_job:{job_id}")
        if cached_job:
            return cached_job
        
        # Check active jobs
        for job in self.job_queue + list(self.running_jobs.values()) + self.completed_jobs + self.failed_jobs:
            if job.job_id == job_id:
                return job.to_dict()
        
        return None
    
    async def get_queue_status(self) -> Dict[str, Any]:
        """Get comprehensive queue and system status."""
        system_resources = await self._get_system_resources()
        
        return {
            "scheduler_running": self.is_running,
            "scheduler_paused": self.is_paused,
            "queue_length": len(self.job_queue),
            "running_jobs": len(self.running_jobs),
            "completed_jobs_today": len([j for j in self.completed_jobs if j.completed_at and j.completed_at.date() == datetime.utcnow().date()]),
            "failed_jobs_today": len([j for j in self.failed_jobs if j.completed_at and j.completed_at.date() == datetime.utcnow().date()]),
            "system_resources": {
                "cpu_percent": system_resources.cpu_percent,
                "memory_percent": system_resources.memory_percent,
                "memory_available_mb": system_resources.memory_available_mb,
                "disk_free_gb": system_resources.disk_free_gb
            },
            "statistics": self.stats,
            "next_jobs": [job.to_dict() for job in self.job_queue[:5]],  # Next 5 jobs
            "running_job_details": [job.to_dict() for job in self.running_jobs.values()]
        }
    
    async def trigger_auto_schedule(self, batch_type: Optional[BatchType] = None) -> List[str]:
        """Manually trigger auto-scheduling for specific or all batch types."""
        job_ids = []
        
        batch_types = [batch_type] if batch_type else list(BatchType)
        
        for bt in batch_types:
            if await self._should_auto_schedule(bt):
                job_id = await self.schedule_job(
                    batch_type=bt,
                    priority=BatchPriority.NORMAL,
                    options={"auto_scheduled": True}
                )
                job_ids.append(job_id)
                self.last_auto_schedule[bt] = datetime.utcnow()
        
        return job_ids
    
    # Private methods
    
    async def _scheduler_loop(self):
        """Main scheduler loop."""
        while self.is_running:
            try:
                if not self.is_paused:
                    await self._process_queue()
                await asyncio.sleep(5)  # Check every 5 seconds
            except Exception as e:
                logger.error(f"Error in scheduler loop: {str(e)}")
                await asyncio.sleep(10)  # Wait longer on error
    
    async def _process_queue(self):
        """Process jobs from the queue."""
        if not self.job_queue:
            return
        
        system_resources = await self._get_system_resources()
        
        # Process jobs up to concurrency limit
        while (len(self.running_jobs) < self.max_concurrent_jobs and 
               self.job_queue and
               self._can_process_more_jobs(system_resources)):
            
            job = self._get_next_job()
            if not job:
                break
            
            # Check if system has capacity
            if not system_resources.has_capacity_for(job):
                logger.info(f"Insufficient resources for job {job.job_id}, waiting...")
                break
            
            # Start the job
            await self._start_job(job)
            
            # Update system resources estimate
            system_resources.memory_available_mb -= job.estimated_memory_mb
    
    def _get_next_job(self) -> Optional[BatchJob]:
        """Get the next job to process from the queue."""
        now = datetime.utcnow()
        
        for i, job in enumerate(self.job_queue):
            if job.scheduled_at <= now and job.status == BatchStatus.PENDING:
                return self.job_queue.pop(i)
        
        return None
    
    def _can_process_more_jobs(self, resources: SystemResources) -> bool:
        """Check if system can handle more jobs."""
        return (
            len(self.running_jobs) < self.max_concurrent_jobs and
            resources.cpu_percent < 80.0 and
            resources.memory_percent < 85.0
        )
    
    async def _start_job(self, job: BatchJob):
        """Start executing a batch job."""
        job.status = BatchStatus.RUNNING
        job.started_at = datetime.utcnow()
        self.running_jobs[job.job_id] = job
        
        logger.info(f"Starting job {job.job_id} ({job.batch_type.value})")
        
        # Create background task
        asyncio.create_task(self._execute_job(job))
    
    async def _execute_job(self, job: BatchJob):
        """Execute a specific batch job."""
        try:
            start_time = datetime.utcnow()
            
            # Update progress
            job.progress = 0.1
            await self._update_job_cache(job)
            
            # Execute based on job type
            result = await self._execute_job_by_type(job)
            
            if result:
                job.status = BatchStatus.COMPLETED
                job.progress = 1.0
                job.completed_at = datetime.utcnow()
                
                # Update statistics
                processing_time = (job.completed_at - start_time).total_seconds()
                self.stats["successful_jobs"] += 1
                self.stats["total_jobs_processed"] += 1
                self._update_average_processing_time(processing_time)
                
                logger.info(f"Job {job.job_id} completed successfully in {processing_time:.2f}s")
                self.completed_jobs.append(job)
            else:
                await self._handle_job_failure(job, "Job execution returned failure")
        
        except Exception as e:
            await self._handle_job_failure(job, str(e))
        
        finally:
            # Remove from running jobs
            self.running_jobs.pop(job.job_id, None)
            await self._update_job_cache(job)
    
    async def _execute_job_by_type(self, job: BatchJob) -> bool:
        """Execute job based on its type."""
        try:
            if job.batch_type == BatchType.CDX_ANALYTICS:
                result = await self.pipeline.process_cdx_records(
                    batch_size=job.batch_size,
                    filters=job.filters,
                    partition_by_date=job.options.get("partition_by_date", True)
                )
                
            elif job.batch_type == BatchType.CONTENT_ANALYTICS:
                result = await self.pipeline.process_content_analytics(
                    batch_size=job.batch_size,
                    include_full_text=job.options.get("include_full_text", False)
                )
                
            elif job.batch_type == BatchType.PROJECT_ANALYTICS:
                result = await self.pipeline.process_project_analytics(
                    batch_size=job.batch_size
                )
                
            elif job.batch_type == BatchType.SYSTEM_EVENTS:
                # For events, we'd get them from a different source
                event_data = job.options.get("event_data", [])
                result = await self.pipeline.process_events(
                    event_data=event_data,
                    event_type=job.options.get("event_type", "system")
                )
            else:
                raise ValueError(f"Unknown batch type: {job.batch_type}")
            
            # Parse result to check success
            result_data = json.loads(result) if isinstance(result, str) else result
            return bool(result_data)  # Success if we got files
            
        except Exception as e:
            logger.error(f"Error executing {job.batch_type.value} job: {str(e)}")
            raise
    
    async def _handle_job_failure(self, job: BatchJob, error_message: str):
        """Handle job failure with retry logic."""
        job.error_message = error_message
        job.retry_count += 1
        
        if job.retry_count < job.max_retries:
            # Schedule retry with exponential backoff
            delay_minutes = 2 ** job.retry_count  # 2, 4, 8 minutes
            job.scheduled_at = datetime.utcnow() + timedelta(minutes=delay_minutes)
            job.status = BatchStatus.PENDING
            
            # Add back to queue
            self.job_queue.append(job)
            self._sort_job_queue()
            
            logger.info(f"Job {job.job_id} failed, scheduling retry {job.retry_count}/{job.max_retries} in {delay_minutes} minutes")
        else:
            job.status = BatchStatus.FAILED
            job.completed_at = datetime.utcnow()
            
            self.stats["failed_jobs"] += 1
            self.stats["total_jobs_processed"] += 1
            
            logger.error(f"Job {job.job_id} failed permanently after {job.retry_count} retries: {error_message}")
            self.failed_jobs.append(job)
    
    async def _resource_monitor_loop(self):
        """Monitor system resources."""
        while self.is_running:
            try:
                now = datetime.utcnow()
                if now - self.last_resource_check >= self.resource_check_interval:
                    resources = await self._get_system_resources()
                    
                    # Log high resource usage
                    if resources.cpu_percent > 90 or resources.memory_percent > 90:
                        logger.warning(f"High resource usage: CPU {resources.cpu_percent:.1f}%, Memory {resources.memory_percent:.1f}%")
                    
                    # Pause scheduler if resources are critically low
                    if resources.memory_percent > 95 or resources.disk_free_gb < 0.5:
                        if not self.is_paused:
                            logger.critical("Critical resource shortage, pausing scheduler")
                            await self.pause()
                    elif self.is_paused and resources.memory_percent < 80 and resources.disk_free_gb > 2:
                        logger.info("Resources recovered, resuming scheduler")
                        await self.resume()
                    
                    self.last_resource_check = now
                
                await asyncio.sleep(30)  # Check every 30 seconds
                
            except Exception as e:
                logger.error(f"Error in resource monitor: {str(e)}")
                await asyncio.sleep(60)
    
    async def _auto_schedule_loop(self):
        """Auto-schedule jobs based on intervals."""
        while self.is_running:
            try:
                for batch_type in BatchType:
                    if await self._should_auto_schedule(batch_type):
                        await self.schedule_job(
                            batch_type=batch_type,
                            priority=BatchPriority.NORMAL,
                            options={"auto_scheduled": True}
                        )
                        self.last_auto_schedule[batch_type] = datetime.utcnow()
                
                await asyncio.sleep(300)  # Check every 5 minutes
                
            except Exception as e:
                logger.error(f"Error in auto-schedule loop: {str(e)}")
                await asyncio.sleep(600)
    
    async def _job_timeout_monitor(self):
        """Monitor running jobs for timeouts."""
        while self.is_running:
            try:
                now = datetime.utcnow()
                timed_out_jobs = []
                
                for job in self.running_jobs.values():
                    if job.started_at and (now - job.started_at) > self.processing_timeout:
                        timed_out_jobs.append(job)
                
                for job in timed_out_jobs:
                    logger.warning(f"Job {job.job_id} timed out after {self.processing_timeout}")
                    await self._handle_job_failure(job, f"Job timed out after {self.processing_timeout}")
                
                await asyncio.sleep(60)  # Check every minute
                
            except Exception as e:
                logger.error(f"Error in timeout monitor: {str(e)}")
                await asyncio.sleep(120)
    
    async def _should_auto_schedule(self, batch_type: BatchType) -> bool:
        """Check if a batch type should be auto-scheduled."""
        if not self.settings.BATCH_PROCESSING_ENABLED:
            return False
        
        interval = self.auto_schedule_intervals.get(batch_type)
        if not interval:
            return False
        
        last_schedule = self.last_auto_schedule.get(batch_type)
        if not last_schedule:
            return True  # Never scheduled before
        
        return datetime.utcnow() - last_schedule >= interval
    
    async def _get_system_resources(self) -> SystemResources:
        """Get current system resource utilization."""
        try:
            # CPU and memory usage
            cpu_percent = psutil.cpu_percent(interval=1)
            memory = psutil.virtual_memory()
            
            # Disk space
            disk_usage = psutil.disk_usage('/')
            disk_free_gb = disk_usage.free / (1024**3)
            
            # Process count
            active_processes = len(psutil.pids())
            
            return SystemResources(
                cpu_percent=cpu_percent,
                memory_percent=memory.percent,
                memory_available_mb=memory.available / (1024**2),
                disk_free_gb=disk_free_gb,
                active_processes=active_processes
            )
            
        except Exception as e:
            logger.error(f"Error getting system resources: {str(e)}")
            # Return conservative estimates
            return SystemResources(
                cpu_percent=50.0,
                memory_percent=50.0,
                memory_available_mb=1024.0,
                disk_free_gb=10.0,
                active_processes=100
            )
    
    async def _estimate_job_requirements(self, job: BatchJob) -> Tuple[int, int]:
        """Estimate memory and time requirements for a job."""
        try:
            # Get record count estimate
            if job.batch_type == BatchType.CDX_ANALYTICS:
                record_count = await self._estimate_cdx_record_count(job.filters)
                memory_mb = min(max(record_count // 1000, 256), 2048)  # 256MB - 2GB
                duration_minutes = max(record_count // 10000, 5)  # At least 5 minutes
                
            elif job.batch_type == BatchType.CONTENT_ANALYTICS:
                record_count = await self._estimate_content_record_count(job.filters)
                memory_mb = min(max(record_count // 500, 512), 4096)  # 512MB - 4GB (content is larger)
                duration_minutes = max(record_count // 5000, 10)  # At least 10 minutes
                
            elif job.batch_type == BatchType.PROJECT_ANALYTICS:
                memory_mb = 256  # Projects are small
                duration_minutes = 5
                
            else:  # SYSTEM_EVENTS
                memory_mb = 128
                duration_minutes = 2
            
            return memory_mb, duration_minutes
            
        except Exception as e:
            logger.warning(f"Error estimating job requirements: {str(e)}")
            return 512, 10  # Conservative defaults
    
    async def _estimate_cdx_record_count(self, filters: Optional[Dict[str, Any]]) -> int:
        """Estimate number of CDX records to process."""
        try:
            with Session(engine) as session:
                stmt = select(func.count(ScrapePage.id)).where(
                    ScrapePage.status.in_([
                        ScrapePageStatus.COMPLETED,
                        ScrapePageStatus.FAILED,
                        ScrapePageStatus.SKIPPED
                    ])
                )
                
                if filters:
                    if "domain_id" in filters:
                        stmt = stmt.where(ScrapePage.domain_id == filters["domain_id"])
                    if "date_from" in filters:
                        stmt = stmt.where(ScrapePage.created_at >= filters["date_from"])
                    if "date_to" in filters:
                        stmt = stmt.where(ScrapePage.created_at <= filters["date_to"])
                
                result = session.execute(stmt)
                return result.scalar() or 0
                
        except Exception as e:
            logger.error(f"Error estimating CDX record count: {str(e)}")
            return 10000  # Default estimate
    
    async def _estimate_content_record_count(self, filters: Optional[Dict[str, Any]]) -> int:
        """Estimate number of content records to process."""
        try:
            with Session(engine) as session:
                stmt = select(func.count(ScrapePage.id)).where(
                    ScrapePage.status == ScrapePageStatus.COMPLETED,
                    ScrapePage.extracted_text.is_not(None)
                )
                
                if filters:
                    if "domain_id" in filters:
                        stmt = stmt.where(ScrapePage.domain_id == filters["domain_id"])
                    if "date_from" in filters:
                        stmt = stmt.where(ScrapePage.created_at >= filters["date_from"])
                    if "date_to" in filters:
                        stmt = stmt.where(ScrapePage.created_at <= filters["date_to"])
                
                result = session.execute(stmt)
                return result.scalar() or 0
                
        except Exception as e:
            logger.error(f"Error estimating content record count: {str(e)}")
            return 5000  # Default estimate
    
    def _sort_job_queue(self):
        """Sort job queue by priority and scheduled time."""
        self.job_queue.sort(key=lambda x: (-x.priority.value, x.scheduled_at))
    
    def _generate_job_id(self, batch_type: BatchType) -> str:
        """Generate a unique job ID."""
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        return f"{batch_type.value}_{timestamp}_{len(self.job_queue):03d}"
    
    def _get_default_batch_size(self, batch_type: BatchType) -> int:
        """Get default batch size for a batch type."""
        batch_sizes = {
            BatchType.CDX_ANALYTICS: self.settings.DEFAULT_BATCH_SIZE,
            BatchType.CONTENT_ANALYTICS: self.settings.CONTENT_BATCH_SIZE,
            BatchType.PROJECT_ANALYTICS: self.settings.PROJECT_BATCH_SIZE,
            BatchType.SYSTEM_EVENTS: 10000
        }
        return batch_sizes.get(batch_type, 10000)
    
    async def _update_job_cache(self, job: BatchJob):
        """Update job in cache."""
        try:
            await self.cache_service.set(f"batch_job:{job.job_id}", job.to_dict(), ttl=86400)
        except Exception as e:
            logger.warning(f"Failed to update job cache: {str(e)}")
    
    def _update_average_processing_time(self, processing_time: float):
        """Update running average of processing time."""
        current_avg = self.stats["average_processing_time"]
        successful_jobs = self.stats["successful_jobs"]
        
        if successful_jobs == 1:
            self.stats["average_processing_time"] = processing_time
        else:
            # Running average
            self.stats["average_processing_time"] = (
                (current_avg * (successful_jobs - 1) + processing_time) / successful_jobs
            )