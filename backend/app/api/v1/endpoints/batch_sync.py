"""
Batch synchronization monitoring and management endpoints

These endpoints provide:
1. Queue statistics and monitoring
2. Manual batch processing triggers
3. Health checks for batch sync system
4. Performance metrics and optimization insights
"""

import logging
from typing import Dict, Any
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.user import User
from app.api.deps import get_current_approved_user
from app.services.batch_sync_manager import batch_sync_manager

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/stats")
async def get_batch_sync_stats(
    *,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_approved_user),
) -> Dict[str, Any]:
    """
    Get batch synchronization statistics and queue status
    """
    try:
        async with batch_sync_manager as bsm:
            stats = await bsm.get_queue_stats()
            
            return {
                "status": "success",
                "timestamp": datetime.utcnow().isoformat(),
                "batch_config": {
                    "batch_size": bsm.batch_size,
                    "batch_timeout": bsm.batch_timeout,
                    "max_retries": bsm.max_retries
                },
                **stats
            }
            
    except Exception as e:
        logger.error(f"Failed to get batch sync stats: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get batch sync statistics: {str(e)}"
        )


@router.post("/process")
async def trigger_batch_processing(
    *,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_approved_user),
    force: bool = Query(False, description="Force processing even if queue is small")
) -> Dict[str, Any]:
    """
    Manually trigger batch processing
    """
    try:
        from app.tasks.meilisearch_sync import process_sync_batch, force_batch_processing
        
        if force:
            # Use force processing task
            task = force_batch_processing.delay()
            task_type = "force_batch"
        else:
            # Use regular batch processing
            task = process_sync_batch.delay()
            task_type = "regular_batch"
        
        return {
            "status": "triggered",
            "task_id": task.id,
            "task_type": task_type,
            "message": "Batch processing task has been queued"
        }
        
    except Exception as e:
        logger.error(f"Failed to trigger batch processing: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to trigger batch processing: {str(e)}"
        )


@router.get("/health")
async def get_batch_sync_health(
    *,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_approved_user),
) -> Dict[str, Any]:
    """
    Get health status of the batch synchronization system
    """
    try:
        from app.tasks.meilisearch_sync import monitor_sync_health
        
        # Trigger health monitoring task
        task = monitor_sync_health.delay()
        
        # Wait for result (should be fast)
        try:
            health_result = task.get(timeout=10)  # 10 second timeout
            
            return {
                "status": "success",
                "health_check_completed": True,
                "health_result": health_result
            }
            
        except Exception as task_e:
            # If task fails or times out, return basic status
            logger.warning(f"Health monitoring task failed: {str(task_e)}")
            
            # Fallback to basic queue stats
            async with batch_sync_manager as bsm:
                queue_stats = await bsm.get_queue_stats()
                
                return {
                    "status": "partial",
                    "health_check_completed": False,
                    "health_task_error": str(task_e),
                    "basic_stats": queue_stats
                }
        
    except Exception as e:
        logger.error(f"Failed to get batch sync health: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get batch sync health: {str(e)}"
        )


@router.post("/cleanup-stats")
async def cleanup_old_statistics(
    *,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_approved_user),
    days_to_keep: int = Query(30, ge=1, le=365, description="Number of days of statistics to keep")
) -> Dict[str, Any]:
    """
    Clean up old synchronization statistics
    """
    try:
        from app.tasks.meilisearch_sync import cleanup_sync_statistics
        
        # Trigger cleanup task
        task = cleanup_sync_statistics.delay(days_to_keep=days_to_keep)
        
        return {
            "status": "triggered",
            "task_id": task.id,
            "days_to_keep": days_to_keep,
            "message": "Statistics cleanup task has been queued"
        }
        
    except Exception as e:
        logger.error(f"Failed to trigger statistics cleanup: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to trigger statistics cleanup: {str(e)}"
        )


@router.get("/performance-insights")
async def get_performance_insights(
    *,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_approved_user),
) -> Dict[str, Any]:
    """
    Get performance insights and optimization recommendations
    """
    try:
        async with batch_sync_manager as bsm:
            stats = await bsm.get_queue_stats()
            
            # Calculate insights
            insights = {
                "recommendations": [],
                "current_performance": {},
                "optimization_opportunities": []
            }
            
            queue_size = stats.get("queue_size", 0)
            today_stats = stats.get("today_stats", {})
            
            # Queue size insights
            if queue_size > 1000:
                insights["recommendations"].append({
                    "type": "queue_size",
                    "priority": "high",
                    "message": f"Queue size is high ({queue_size}). Consider increasing batch size or processing frequency.",
                    "suggested_action": "Increase MEILISEARCH_BATCH_SIZE or reduce MEILISEARCH_BATCH_TIMEOUT"
                })
            elif queue_size > 500:
                insights["recommendations"].append({
                    "type": "queue_size", 
                    "priority": "medium",
                    "message": f"Queue size is moderate ({queue_size}). Monitor for growth trends.",
                    "suggested_action": "Consider optimizing batch processing efficiency"
                })
            
            # Processing efficiency
            if today_stats:
                total_processed = sum([
                    int(today_stats.get(f"processed_{op}", 0)) 
                    for op in ["index", "update", "delete"]
                ])
                
                if total_processed > 0:
                    insights["current_performance"]["pages_processed_today"] = total_processed
                    
                    # Calculate throughput recommendations
                    if total_processed > 10000:
                        insights["recommendations"].append({
                            "type": "throughput",
                            "priority": "info", 
                            "message": f"High throughput detected ({total_processed:,} pages). System is performing well.",
                            "suggested_action": "Continue monitoring for consistency"
                        })
            
            # Configuration optimization
            current_batch_size = bsm.batch_size
            if queue_size > current_batch_size * 5:
                insights["optimization_opportunities"].append({
                    "type": "batch_size",
                    "current_value": current_batch_size,
                    "suggested_value": min(current_batch_size * 2, 500),
                    "reason": "Queue consistently exceeds batch size by large margin"
                })
            
            # System health
            if not stats.get("available", False):
                insights["recommendations"].append({
                    "type": "system_health",
                    "priority": "critical",
                    "message": "Redis is not available. Batch synchronization is disabled.",
                    "suggested_action": "Check Redis connection and service status"
                })
            
            return {
                "status": "success",
                "timestamp": datetime.utcnow().isoformat(),
                "queue_size": queue_size,
                "batch_config": {
                    "batch_size": bsm.batch_size,
                    "batch_timeout": bsm.batch_timeout,
                    "max_retries": bsm.max_retries
                },
                "insights": insights
            }
            
    except Exception as e:
        logger.error(f"Failed to get performance insights: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get performance insights: {str(e)}"
        )