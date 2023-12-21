from celery import Celery

celery = Celery(
    'worker',
    broker='redis://redis:6379/0',
    backend='redis://redis:6379/0'
)

@celery.task
def some_task(args):
    # Task implementation
    pass
