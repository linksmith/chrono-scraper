"""
Celery tasks for Meilisearch key rotation and cleanup

This module provides automated maintenance tasks for the multi-tenant
Meilisearch security system, including key rotation, cleanup, and monitoring.
"""

import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any
from celery import Task

from ..tasks.celery_app import celery_app
from ..core.database import get_db
from ..models.project import Project
from ..models.meilisearch_audit import MeilisearchKey, MeilisearchKeyType, MeilisearchSecurityEvent
from ..services.meilisearch_key_manager import meilisearch_key_manager
from ..core.config import settings
from sqlmodel import select, and_, or_

logger = logging.getLogger(__name__)


class KeyRotationTask(Task):
    """Base class for key rotation tasks with error handling"""
    
    def on_failure(self, exc, task_id, args, kwargs, einfo):
        """Handle task failure"""
        logger.error(f"Key rotation task {task_id} failed: {exc}")
        # Could send alerts or create security events here


@celery_app.task(bind=True, base=KeyRotationTask, name="rotate_project_keys")
async def rotate_project_keys_task(self) -> Dict[str, Any]:
    """
    Periodic task to rotate project search keys that are due for rotation
    
    This task:
    1. Finds projects with keys older than MEILISEARCH_KEY_ROTATION_DAYS
    2. Rotates keys for those projects
    3. Updates database records
    4. Creates security audit events
    
    Returns:
        Dict with rotation statistics
    """
    logger.info("Starting project key rotation task")
    
    rotation_stats = {
        'total_checked': 0,
        'keys_rotated': 0,
        'keys_failed': 0,
        'errors': [],
        'start_time': datetime.utcnow()
    }
    
    try:
        async for db in get_db():
            # Calculate cutoff date for rotation
            cutoff_date = datetime.utcnow() - timedelta(days=settings.MEILISEARCH_KEY_ROTATION_DAYS)
            
            # Find projects with keys that need rotation
            query = select(Project).where(
                and_(
                    Project.index_search_key.isnot(None),  # Has a key
                    Project.key_rotation_enabled is True,  # Rotation enabled
                    or_(
                        Project.key_created_at < cutoff_date,  # Key too old
                        Project.key_last_rotated < cutoff_date,  # Last rotation too old
                        Project.key_created_at.is_(None)  # No creation date (legacy)
                    )
                )
            )
            
            result = await db.execute(query)
            projects_for_rotation = result.scalars().all()
            rotation_stats['total_checked'] = len(projects_for_rotation)
            
            logger.info(f"Found {rotation_stats['total_checked']} projects requiring key rotation")
            
            # Rotate keys for each project
            for project in projects_for_rotation:
                try:
                    logger.info(f"Rotating key for project {project.id}: {project.name}")
                    
                    # Rotate the key using key manager
                    new_key_data = await meilisearch_key_manager.rotate_project_key(project)
                    
                    # Update project with new key
                    project.index_search_key = new_key_data['key']
                    project.index_search_key_uid = new_key_data['uid']
                    project.key_last_rotated = datetime.utcnow()
                    
                    # Update audit record
                    old_key_query = select(MeilisearchKey).where(
                        MeilisearchKey.project_id == project.id,
                        MeilisearchKey.key_type == MeilisearchKeyType.PROJECT_OWNER,
                        MeilisearchKey.is_active is True
                    )
                    old_key_result = await db.execute(old_key_query)
                    old_key = old_key_result.scalar_one_or_none()
                    
                    if old_key:
                        old_key.is_active = False
                        old_key.revoked_at = datetime.utcnow()
                        old_key.revoked_reason = "Automatic key rotation"
                    
                    # Create new audit record
                    new_audit_record = MeilisearchKey(
                        project_id=project.id,
                        key_uid=new_key_data['uid'],
                        key_type=MeilisearchKeyType.PROJECT_OWNER,
                        key_name=f"project_owner_{project.id}_rotated",
                        key_description=f"Rotated owner search key for project: {project.name}",
                        actions=["search", "documents.get"],
                        indexes=[f"project_{project.id}"]
                    )
                    db.add(new_audit_record)
                    
                    # Create security event
                    security_event = MeilisearchSecurityEvent(
                        key_id=new_audit_record.id,
                        event_type="key_rotated",
                        severity="info",
                        description=f"Project key rotated for project {project.id}",
                        automated=True,
                        event_metadata={
                            "project_id": project.id,
                            "old_key_uid": old_key.key_uid if old_key else None,
                            "new_key_uid": new_key_data['uid'],
                            "rotation_reason": "scheduled_rotation"
                        }
                    )
                    db.add(security_event)
                    
                    await db.commit()
                    rotation_stats['keys_rotated'] += 1
                    
                    logger.info(f"Successfully rotated key for project {project.id}")
                    
                except Exception as e:
                    rotation_stats['keys_failed'] += 1
                    rotation_stats['errors'].append({
                        'project_id': project.id,
                        'error': str(e)
                    })
                    logger.error(f"Failed to rotate key for project {project.id}: {e}")
                    await db.rollback()
                    continue
            
            break  # Exit the async for loop
            
    except Exception as e:
        logger.error(f"Key rotation task failed: {e}")
        rotation_stats['errors'].append({'global_error': str(e)})
    
    finally:
        rotation_stats['end_time'] = datetime.utcnow()
        rotation_stats['duration_seconds'] = (
            rotation_stats['end_time'] - rotation_stats['start_time']
        ).total_seconds()
    
    logger.info(f"Key rotation task completed: {rotation_stats}")
    return rotation_stats


@celery_app.task(bind=True, base=KeyRotationTask, name="cleanup_expired_tokens")
async def cleanup_expired_tokens_task(self) -> Dict[str, Any]:
    """
    Clean up expired tenant tokens and revoked keys from Meilisearch
    
    This task:
    1. Calls the key manager to clean up expired tokens
    2. Updates database audit records
    3. Cleans up old security events
    
    Returns:
        Dict with cleanup statistics
    """
    logger.info("Starting expired token cleanup task")
    
    cleanup_stats = {
        'meilisearch_keys_cleaned': 0,
        'audit_records_updated': 0,
        'old_events_cleaned': 0,
        'errors': [],
        'start_time': datetime.utcnow()
    }
    
    try:
        # Clean up expired keys in Meilisearch
        cleanup_stats['meilisearch_keys_cleaned'] = await meilisearch_key_manager.cleanup_expired_tokens()
        
        async for db in get_db():
            # Update audit records for expired keys
            cutoff_date = datetime.utcnow()
            expired_keys_query = select(MeilisearchKey).where(
                and_(
                    MeilisearchKey.expires_at < cutoff_date,
                    MeilisearchKey.is_active is True
                )
            )
            
            result = await db.execute(expired_keys_query)
            expired_keys = result.scalars().all()
            
            for key in expired_keys:
                key.is_active = False
                key.revoked_at = datetime.utcnow()
                key.revoked_reason = "Automatic cleanup - expired"
                cleanup_stats['audit_records_updated'] += 1
            
            # Clean up old security events (keep last 90 days)
            events_cutoff = datetime.utcnow() - timedelta(days=90)
            old_events_query = select(MeilisearchSecurityEvent).where(
                MeilisearchSecurityEvent.created_at < events_cutoff
            )
            
            old_events_result = await db.execute(old_events_query)
            old_events = old_events_result.scalars().all()
            
            for event in old_events:
                await db.delete(event)
                cleanup_stats['old_events_cleaned'] += 1
            
            await db.commit()
            break  # Exit the async for loop
            
    except Exception as e:
        logger.error(f"Token cleanup task failed: {e}")
        cleanup_stats['errors'].append({'error': str(e)})
    
    finally:
        cleanup_stats['end_time'] = datetime.utcnow()
        cleanup_stats['duration_seconds'] = (
            cleanup_stats['end_time'] - cleanup_stats['start_time']
        ).total_seconds()
    
    logger.info(f"Token cleanup task completed: {cleanup_stats}")
    return cleanup_stats


@celery_app.task(bind=True, base=KeyRotationTask, name="monitor_key_usage")
async def monitor_key_usage_task(self) -> Dict[str, Any]:
    """
    Monitor API key usage patterns and detect suspicious activity
    
    This task:
    1. Analyzes recent key usage patterns
    2. Detects unusual activity (rate spikes, failed requests, etc.)
    3. Creates security alerts for suspicious behavior
    
    Returns:
        Dict with monitoring statistics
    """
    logger.info("Starting key usage monitoring task")
    
    monitoring_stats = {
        'keys_monitored': 0,
        'suspicious_patterns': 0,
        'alerts_created': 0,
        'errors': [],
        'start_time': datetime.utcnow()
    }
    
    try:
        async for db in get_db():
            # Get all active keys for monitoring
            active_keys_query = select(MeilisearchKey).where(
                MeilisearchKey.is_active is True
            )
            
            result = await db.execute(active_keys_query)
            active_keys = result.scalars().all()
            monitoring_stats['keys_monitored'] = len(active_keys)
            
            # Analyze usage patterns for each key
            for key in active_keys:
                try:
                    # Check for unusual usage patterns
                    suspicious_patterns = await _detect_suspicious_patterns(db, key)
                    
                    if suspicious_patterns:
                        monitoring_stats['suspicious_patterns'] += len(suspicious_patterns)
                        
                        # Create security alerts
                        for pattern in suspicious_patterns:
                            security_event = MeilisearchSecurityEvent(
                                key_id=key.id,
                                event_type="suspicious_activity",
                                severity=pattern['severity'],
                                description=pattern['description'],
                                automated=True,
                                event_metadata=pattern['metadata']
                            )
                            db.add(security_event)
                            monitoring_stats['alerts_created'] += 1
                            
                            logger.warning(f"Suspicious activity detected for key {key.key_uid}: {pattern['description']}")
                
                except Exception as e:
                    monitoring_stats['errors'].append({
                        'key_uid': key.key_uid,
                        'error': str(e)
                    })
                    logger.error(f"Failed to monitor key {key.key_uid}: {e}")
                    continue
            
            await db.commit()
            break  # Exit the async for loop
            
    except Exception as e:
        logger.error(f"Key monitoring task failed: {e}")
        monitoring_stats['errors'].append({'global_error': str(e)})
    
    finally:
        monitoring_stats['end_time'] = datetime.utcnow()
        monitoring_stats['duration_seconds'] = (
            monitoring_stats['end_time'] - monitoring_stats['start_time']
        ).total_seconds()
    
    logger.info(f"Key monitoring task completed: {monitoring_stats}")
    return monitoring_stats


async def _detect_suspicious_patterns(db, key: MeilisearchKey) -> List[Dict[str, Any]]:
    """
    Detect suspicious usage patterns for a specific key
    
    Args:
        db: Database session
        key: MeilisearchKey to analyze
        
    Returns:
        List of suspicious patterns found
    """
    patterns = []
    
    # Check for rapid usage spikes (simple heuristic)
    if key.usage_count > 10000:  # High usage threshold
        recent_usage = await _get_recent_usage_count(db, key, hours=1)
        if recent_usage > 1000:  # Very high recent usage
            patterns.append({
                'type': 'usage_spike',
                'severity': 'warning',
                'description': f'Unusual usage spike: {recent_usage} requests in last hour',
                'metadata': {
                    'recent_usage': recent_usage,
                    'total_usage': key.usage_count
                }
            })
    
    # Check for keys that haven't been used recently (potential compromise)
    if key.last_used_at:
        hours_since_use = (datetime.utcnow() - key.last_used_at).total_seconds() / 3600
        if hours_since_use > 168:  # More than 1 week
            patterns.append({
                'type': 'dormant_key',
                'severity': 'info',
                'description': f'Key dormant for {hours_since_use:.1f} hours',
                'metadata': {
                    'hours_since_use': hours_since_use,
                    'last_used': key.last_used_at.isoformat()
                }
            })
    
    return patterns


async def _get_recent_usage_count(db, key: MeilisearchKey, hours: int = 1) -> int:
    """Get usage count for a key within the specified time window"""
    # This would require the MeilisearchUsageLog model to be populated
    # For now, return a placeholder
    return 0  # TODO: Implement with actual usage logs


# Celery Beat Schedule Configuration
# Add this to your celery configuration:
"""
beat_schedule = {
    'rotate-project-keys': {
        'task': 'rotate_project_keys',
        'schedule': crontab(hour=2, minute=0),  # Daily at 2 AM
    },
    'cleanup-expired-tokens': {
        'task': 'cleanup_expired_tokens', 
        'schedule': crontab(hour=3, minute=0),  # Daily at 3 AM
    },
    'monitor-key-usage': {
        'task': 'monitor_key_usage',
        'schedule': crontab(minute=0),  # Every hour
    },
}
"""