"""
Celery application configuration
"""
from celery import Celery
from app.core.config import settings

celery_app = Celery(
    "chrono_scraper",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=[
        "app.tasks.firecrawl_scraping",  # Firecrawl-only tasks
        "app.tasks.scraping_simple",  # Simple tasks for retries
        "app.tasks.project_tasks",  # Project management tasks
        "app.tasks.index_tasks",  # Meilisearch index tasks
        "app.tasks.meilisearch_sync"  # Batch synchronization tasks
    ]
)

# Simplified Celery configuration for Firecrawl-only architecture
celery_app.conf.update(
    # Serialization - JSON for simplicity and reliability
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    
    # Task execution - optimized for slow Wayback Machine + Firecrawl workflow
    task_track_started=True,
    task_time_limit=60 * 60,  # 60 minutes for slow Wayback Machine URLs
    task_soft_time_limit=55 * 60,  # 55 minutes
    task_acks_late=True,  # Acknowledge only after completion
    task_reject_on_worker_lost=True,
    
    # Worker settings - optimized for parallel Firecrawl processing
    worker_prefetch_multiplier=3,  # Allow more prefetching for better throughput
    worker_max_tasks_per_child=100,  # Process more tasks before restart
    worker_hijack_root_logger=False,
    result_extended=True,
    worker_concurrency=10,  # Increase worker concurrency for parallel processing
)

# Simplified task routing - use default celery queue for now
celery_app.conf.task_routes = {
    "app.tasks.firecrawl_scraping.*": {"queue": "celery"},  # Use default queue
    "app.tasks.scraping_simple.*": {"queue": "celery"},  # Use default queue
    "app.tasks.project_tasks.*": {"queue": "celery"},  # Use default queue
    "app.tasks.index_tasks.*": {"queue": "celery"},  # Use default queue
    "app.tasks.meilisearch_sync.*": {"queue": "celery"},  # Use default queue
}

# Periodic tasks for batch synchronization
celery_app.conf.beat_schedule = {
    "batch-sync-periodic": {
        "task": "app.tasks.meilisearch_sync.process_sync_batch",
        "schedule": 30.0,  # Every 30 seconds
        "options": {"queue": "celery"}
    },
    "sync-health-monitoring": {
        "task": "app.tasks.meilisearch_sync.monitor_sync_health", 
        "schedule": 300.0,  # Every 5 minutes
        "options": {"queue": "celery"}
    },
    "sync-stats-cleanup": {
        "task": "app.tasks.meilisearch_sync.cleanup_sync_statistics",
        "schedule": 24 * 60 * 60.0,  # Daily
        "options": {"queue": "celery"}
    },
}