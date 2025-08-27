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
        "app.tasks.meilisearch_sync",  # Batch synchronization tasks
        # "app.tasks.backup_tasks"  # Backup and recovery tasks - Disabled
    ]
)

# Optimized Celery configuration with priority queues and memory management
celery_app.conf.update(
    # Serialization - JSON for simplicity and reliability
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    
    # Task execution - optimized for memory efficiency
    task_track_started=True,
    task_time_limit=30 * 60,  # 30 minutes hard limit (reduced from 60)
    task_soft_time_limit=25 * 60,  # 25 minutes soft limit
    task_acks_late=True,  # Acknowledge only after completion
    task_reject_on_worker_lost=True,
    
    # Worker settings - optimized for memory management and throughput
    worker_prefetch_multiplier=2,  # Reduced from 3 for better memory management
    worker_max_tasks_per_child=50,  # Reduced from 100 for memory recycling
    worker_max_memory_per_child=400000,  # 400MB limit per worker process
    worker_hijack_root_logger=False,
    result_extended=True,
    worker_concurrency=6,  # Reduced from 10 based on optimization plan
    
    # Priority queue configuration
    task_default_priority=5,
    task_inherit_parent_priority=True,
    
    # Memory optimization
    result_expires=3600,  # Results expire after 1 hour
    task_compression='gzip',  # Compress task payloads
    result_compression='gzip',  # Compress results
)

# Priority-based task routing for optimal resource allocation
celery_app.conf.task_routes = {
    # High priority: Quick API operations and critical tasks
    "app.tasks.project_tasks.quick_*": {"queue": "quick", "priority": 9},
    "app.tasks.index_tasks.quick_*": {"queue": "quick", "priority": 9},
    "app.tasks.backup_tasks.execute_recovery": {"queue": "quick", "priority": 9},
    
    # Medium priority: Main scraping operations and backups
    "app.tasks.firecrawl_scraping.scrape_domain_with_firecrawl": {"queue": "scraping", "priority": 5},
    "app.tasks.firecrawl_scraping.scrape_domain_incremental": {"queue": "scraping", "priority": 6},
    "app.tasks.firecrawl_scraping.fill_coverage_gaps": {"queue": "scraping", "priority": 4},
    "app.tasks.scraping_simple.*": {"queue": "scraping", "priority": 5},
    "app.tasks.backup_tasks.execute_*_backup": {"queue": "backup", "priority": 6},
    
    # Lower priority: Indexing and background operations
    "app.tasks.index_tasks.*": {"queue": "indexing", "priority": 3},
    "app.tasks.meilisearch_sync.*": {"queue": "indexing", "priority": 3},
    "app.tasks.backup_tasks.*": {"queue": "backup", "priority": 4},
    
    # Periodic incremental tasks
    "app.tasks.firecrawl_scraping.check_domains_for_incremental": {"queue": "celery", "priority": 3},
    "app.tasks.firecrawl_scraping.update_incremental_statistics": {"queue": "celery", "priority": 2},
    
    # Default queue for other tasks
    "app.tasks.project_tasks.*": {"queue": "celery", "priority": 5},
}

# Periodic tasks for batch synchronization and incremental scraping
celery_app.conf.beat_schedule = {
    # Meilisearch sync tasks
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
    
    # Incremental scraping tasks
    "check-incremental-domains": {
        "task": "app.tasks.firecrawl_scraping.check_domains_for_incremental",
        "schedule": 4 * 60 * 60.0,  # Every 4 hours
        "options": {"queue": "celery"},
        "kwargs": {"force_check": False}
    },
    "update-incremental-statistics": {
        "task": "app.tasks.firecrawl_scraping.update_incremental_statistics",
        "schedule": 6 * 60 * 60.0,  # Every 6 hours
        "options": {"queue": "celery"}
    },
    "incremental-domains-daily-check": {
        "task": "app.tasks.firecrawl_scraping.check_domains_for_incremental",
        "schedule": 24 * 60 * 60.0,  # Daily at midnight
        "options": {"queue": "celery"},
        "kwargs": {"force_check": True}
    },
}