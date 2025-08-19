"""
Celery tasks for Meilisearch batch synchronization

This module provides:
1. Background batch processing of Meilisearch sync operations
2. Periodic cleanup of old sync statistics
3. Health monitoring for batch sync system
4. Retry logic with exponential backoff
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, Any

from celery import shared_task
from app.services.batch_sync_manager import batch_sync_manager
from app.core.config import settings

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3)
def process_sync_batch(self) -> Dict[str, Any]:
    """
    Process a batch of Meilisearch synchronization operations
    
    This task:
    1. Gets a batch of operations from Redis queue
    2. Groups operations by type for efficiency
    3. Processes deletes, then updates/indexes
    4. Cleans up processed operations from queue
    5. Reports statistics and errors
    """
    import asyncio
    
    logger.info("🔄 Starting batch sync processing")
    start_time = datetime.utcnow()
    
    try:
        # Run async batch processing
        result = asyncio.run(_async_process_batch())
        
        # Calculate duration
        duration = (datetime.utcnow() - start_time).total_seconds()
        result['processing_time_seconds'] = duration
        
        if result.get('processed', 0) > 0:
            logger.info(f"✅ Batch sync completed: {result['processed']} operations in {duration:.1f}s")
            
            # Log operation breakdown
            if result.get('by_operation'):
                ops_str = ", ".join([f"{k}: {v}" for k, v in result['by_operation'].items()])
                logger.info(f"   📊 Operations: {ops_str}")
        else:
            logger.debug("📭 No operations to process")
        
        if result.get('errors', 0) > 0:
            logger.warning(f"⚠️  {result['errors']} operations failed")
        
        return result
        
    except Exception as exc:
        duration = (datetime.utcnow() - start_time).total_seconds()
        logger.error(f"❌ Batch sync failed after {duration:.1f}s: {str(exc)}")
        
        # Retry with exponential backoff
        if self.request.retries < self.max_retries:
            retry_delay = 60 * (2 ** self.request.retries)  # 60s, 120s, 240s
            logger.info(f"🔄 Retrying batch sync in {retry_delay}s (attempt {self.request.retries + 1}/{self.max_retries})")
            raise self.retry(countdown=retry_delay, exc=exc)
        else:
            logger.error(f"💥 Batch sync failed permanently after {self.max_retries} retries")
            return {
                "status": "failed",
                "error": str(exc),
                "processing_time_seconds": duration,
                "retries_exhausted": True
            }


async def _async_process_batch() -> Dict[str, Any]:
    """Async helper for batch processing"""
    async with batch_sync_manager as bsm:
        if not bsm.redis_client:
            return {
                "status": "skipped", 
                "reason": "Redis not available",
                "processed": 0,
                "errors": 0
            }
        
        # Get batch of operations
        operations = await bsm.get_batch_operations()
        
        if not operations:
            return {
                "status": "completed",
                "processed": 0,
                "errors": 0,
                "reason": "No operations in queue"
            }
        
        logger.info(f"📦 Processing batch of {len(operations)} operations")
        
        # Process the batch
        results = await bsm._process_operations_batch(operations)
        
        # Clean up processed operations
        await bsm.clear_processed_operations(operations)
        
        return {
            "status": "completed",
            "total_operations": len(operations),
            **results
        }


@shared_task(bind=True)
def cleanup_sync_statistics(self, days_to_keep: int = 30) -> Dict[str, Any]:
    """
    Periodic cleanup of old synchronization statistics
    
    Args:
        days_to_keep: Number of days of statistics to retain
    """
    import asyncio
    
    logger.info(f"🧹 Cleaning up sync statistics older than {days_to_keep} days")
    
    try:
        result = asyncio.run(_async_cleanup_stats(days_to_keep))
        
        if result['cleaned_keys'] > 0:
            logger.info(f"✅ Cleaned up {result['cleaned_keys']} old statistics keys")
        else:
            logger.debug("📭 No old statistics to clean up")
        
        return result
        
    except Exception as exc:
        logger.error(f"❌ Statistics cleanup failed: {str(exc)}")
        return {
            "status": "error",
            "error": str(exc),
            "cleaned_keys": 0
        }


async def _async_cleanup_stats(days_to_keep: int) -> Dict[str, Any]:
    """Async helper for statistics cleanup"""
    async with batch_sync_manager as bsm:
        if not bsm.redis_client:
            return {
                "status": "skipped",
                "reason": "Redis not available",
                "cleaned_keys": 0
            }
        
        # Calculate cutoff date
        cutoff_date = datetime.utcnow() - timedelta(days=days_to_keep)
        
        # Find old statistics keys
        pattern = f"{bsm.stats_key}:*"
        all_stats_keys = await bsm.redis_client.keys(pattern)
        
        keys_to_delete = []
        for key in all_stats_keys:
            # Extract date from key (format: meilisearch:sync_stats:YYYY-MM-DD)
            try:
                date_str = key.split(":")[-1]  # Get the date part
                key_date = datetime.strptime(date_str, "%Y-%m-%d")
                
                if key_date < cutoff_date:
                    keys_to_delete.append(key)
            except (ValueError, IndexError):
                # Invalid key format, skip
                continue
        
        # Delete old keys
        if keys_to_delete:
            await bsm.redis_client.delete(*keys_to_delete)
        
        return {
            "status": "completed",
            "cleaned_keys": len(keys_to_delete),
            "cutoff_date": cutoff_date.isoformat(),
            "total_stats_keys": len(all_stats_keys)
        }


@shared_task(bind=True)
def monitor_sync_health(self) -> Dict[str, Any]:
    """
    Monitor the health of the batch sync system
    
    Checks:
    1. Redis connectivity
    2. Queue size and growth rate
    3. Processing statistics
    4. Error rates
    """
    import asyncio
    
    try:
        result = asyncio.run(_async_monitor_health())
        
        # Log health status
        if result['status'] == 'healthy':
            logger.debug(f"💚 Batch sync system healthy (queue: {result.get('queue_size', 0)})")
        elif result['status'] == 'warning':
            logger.warning(f"⚠️  Batch sync system warning: {result.get('issues', [])}")
        else:
            logger.error(f"🔴 Batch sync system unhealthy: {result.get('issues', [])}")
        
        return result
        
    except Exception as exc:
        logger.error(f"❌ Health monitoring failed: {str(exc)}")
        return {
            "status": "error",
            "error": str(exc),
            "timestamp": datetime.utcnow().isoformat()
        }


async def _async_monitor_health() -> Dict[str, Any]:
    """Async helper for health monitoring"""
    health_report = {
        "timestamp": datetime.utcnow().isoformat(),
        "status": "healthy",
        "issues": [],
        "metrics": {}
    }
    
    async with batch_sync_manager as bsm:
        if not bsm.redis_client:
            health_report["status"] = "error"
            health_report["issues"].append("Redis not available")
            return health_report
        
        # Get queue statistics
        queue_stats = await bsm.get_queue_stats()
        health_report["metrics"].update(queue_stats)
        
        # Check queue size (warning if > 5000, critical if > 10000)
        queue_size = queue_stats.get("queue_size", 0)
        if queue_size > 10000:
            health_report["status"] = "critical"
            health_report["issues"].append(f"Queue size critical: {queue_size} operations")
        elif queue_size > 5000:
            if health_report["status"] == "healthy":
                health_report["status"] = "warning"
            health_report["issues"].append(f"Queue size high: {queue_size} operations")
        
        # Check if processing is stuck
        if queue_stats.get("is_processing") and queue_size > 0:
            # This is normal, processing is active
            pass
        elif not queue_stats.get("is_processing") and queue_size > 100:
            if health_report["status"] == "healthy":
                health_report["status"] = "warning"
            health_report["issues"].append("Queue has items but no processing active")
        
        # Check today's error rate
        today_stats = queue_stats.get("today_stats", {})
        if today_stats:
            total_processed = sum([
                int(today_stats.get(f"processed_{op}", 0)) 
                for op in ["index", "update", "delete"]
            ])
            total_errors = int(today_stats.get("errors_total", 0))
            
            if total_processed > 0:
                error_rate = (total_errors / (total_processed + total_errors)) * 100
                health_report["metrics"]["error_rate_percent"] = round(error_rate, 2)
                
                if error_rate > 20:  # More than 20% error rate
                    if health_report["status"] == "healthy":
                        health_report["status"] = "warning"
                    health_report["issues"].append(f"High error rate: {error_rate:.1f}%")
        
        # Add configuration info
        health_report["metrics"]["batch_size"] = bsm.batch_size
        health_report["metrics"]["batch_timeout"] = bsm.batch_timeout
        
    return health_report


@shared_task(bind=True)
def force_batch_processing(self) -> Dict[str, Any]:
    """
    Force immediate batch processing regardless of queue size
    
    Useful for:
    1. Manual triggering during low-traffic periods
    2. Processing small batches that haven't reached size threshold
    3. Emergency processing of stuck operations
    """
    import asyncio
    
    logger.info("🚀 Force triggering batch processing")
    
    try:
        result = asyncio.run(_async_force_batch())
        
        if result.get('processed', 0) > 0:
            logger.info(f"✅ Force batch completed: {result['processed']} operations processed")
        else:
            logger.info("📭 No operations to process in forced batch")
        
        return result
        
    except Exception as exc:
        logger.error(f"❌ Force batch processing failed: {str(exc)}")
        return {
            "status": "error",
            "error": str(exc),
            "processed": 0
        }


async def _async_force_batch() -> Dict[str, Any]:
    """Async helper for forced batch processing"""
    async with batch_sync_manager as bsm:
        if not bsm.redis_client:
            return {
                "status": "skipped",
                "reason": "Redis not available", 
                "processed": 0
            }
        
        # Get all operations (not limited by batch size)
        operations = await bsm.get_batch_operations(max_operations=1000)
        
        if not operations:
            return {
                "status": "completed",
                "processed": 0,
                "reason": "No operations in queue"
            }
        
        logger.info(f"📦 Force processing {len(operations)} operations")
        
        # Process the batch
        results = await bsm._process_operations_batch(operations)
        
        # Clean up processed operations
        await bsm.clear_processed_operations(operations)
        
        return {
            "status": "completed",
            "total_operations": len(operations),
            **results
        }