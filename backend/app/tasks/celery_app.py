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
        "app.tasks.parquet_tasks",  # Parquet pipeline processing tasks
        # "app.tasks.backup_tasks"  # Backup and recovery tasks - Disabled
    ]
)

# Optimized Celery configuration for intelligent content extraction system
celery_app.conf.update(
    # Serialization - JSON for simplicity and reliability
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    
    # Task execution - optimized for intelligent extraction workload
    task_track_started=True,
    task_time_limit=40 * 60,  # 40 minutes hard limit for complex extractions
    task_soft_time_limit=30 * 60,  # 30 minutes soft limit
    task_acks_late=True,  # Acknowledge only after completion
    task_reject_on_worker_lost=True,
    task_routes_max_retries=3,
    
    # Worker settings - optimized for intelligent extraction memory management
    worker_prefetch_multiplier=1,  # Conservative prefetch for memory efficiency
    worker_max_tasks_per_child=30,  # Reduced for aggressive memory recycling
    worker_max_memory_per_child=350000,  # 350MB limit per worker process
    worker_hijack_root_logger=False,
    result_extended=True,
    worker_concurrency=8,  # Optimized for 2.5 CPU cores with intelligent extraction
    
    # Priority queue configuration for intelligent extraction
    task_default_priority=5,
    task_inherit_parent_priority=True,
    task_compression='gzip',  # Essential for large content payloads
    result_compression='gzip',
    
    # Memory optimization for intelligent extraction workload
    result_expires=1800,  # Results expire after 30 minutes (faster cleanup)
    task_always_eager=False,
    task_eager_propagates=False,
    task_store_eager_result=False,
    
    # Connection pool optimization for high-throughput extraction
    broker_connection_retry_on_startup=True,
    broker_connection_max_retries=10,
    broker_pool_limit=20,  # Higher pool for concurrent extractions
    
    # Result backend optimization
    result_backend_max_connections=15,
    cache_backend_options={
        'max_connections': 20,
        'retry_on_timeout': True,
    },
    
    # Task execution optimization for extraction libraries
    task_send_sent_event=True,
    task_send_events=True,
    worker_send_task_events=True,
    
    # Advanced worker optimization for intelligent extraction
    worker_disable_rate_limits=False,
    worker_enable_remote_control=True,
    worker_pool_restarts=True,
    worker_autoscaler='celery.worker.autoscale:Autoscaler',
    
    # Memory management for extraction libraries
    celeryd_force_execv=True,  # Force process replacement for memory cleanup
    celeryd_max_tasks_per_child=30,  # Aggressive recycling
)

# Priority-based task routing for optimal resource allocation
celery_app.conf.task_routes = {
    # High priority: Quick API operations and critical tasks
    "app.tasks.project_tasks.quick_*": {"queue": "quick", "priority": 9},
    "app.tasks.index_tasks.quick_*": {"queue": "quick", "priority": 9},
    "app.tasks.backup_tasks.execute_recovery": {"queue": "quick", "priority": 9},
    
    # Medium priority: Main scraping operations and backups
    "app.tasks.firecrawl_scraping.scrape_domain_with_intelligent_extraction": {"queue": "scraping", "priority": 5},
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