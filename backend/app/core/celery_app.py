"""
Celery configuration and app creation
"""
from celery import Celery

from app.core.config import settings


def create_celery_app() -> Celery:
    """Create and configure Celery app"""
    celery_app = Celery(
        "chrono_scraper",
        broker=settings.CELERY_BROKER_URL,
        backend=settings.CELERY_RESULT_BACKEND,
        include=[
            "app.tasks.project_tasks",
            "app.tasks.scraping_tasks",
            "app.tasks.index_tasks"
        ]
    )
    
    # Configure Celery
    celery_app.conf.update(
        task_serializer="json",
        accept_content=["json"],
        result_serializer="json",
        timezone="UTC",
        enable_utc=True,
        
        # Task routing
        task_routes={
            "app.tasks.project_tasks.*": {"queue": "projects"},
            "app.tasks.scraping_tasks.*": {"queue": "scraping"},
            "app.tasks.index_tasks.*": {"queue": "indexing"}
        },
        
        # Task execution settings
        task_always_eager=False,
        task_eager_propagates=True,
        task_ignore_result=False,
        task_store_eager_result=True,
        
        # Worker settings
        worker_prefetch_multiplier=1,
        worker_max_tasks_per_child=1000,
        
        # Beat schedule for periodic tasks
        beat_schedule={
            "cleanup-old-tasks": {
                "task": "app.tasks.project_tasks.cleanup_old_tasks",
                "schedule": 3600.0,  # Every hour
            },
            "index-health-check": {
                "task": "app.tasks.index_tasks.health_check_indexes",
                "schedule": 300.0,  # Every 5 minutes
            }
        },
        
        # Result backend settings
        result_expires=3600,  # 1 hour
        result_persistent=True,
    )
    
    return celery_app


# Create the Celery app instance
celery_app = create_celery_app()