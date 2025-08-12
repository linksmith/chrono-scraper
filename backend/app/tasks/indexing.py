"""
Indexing tasks
"""
from app.tasks.celery_app import celery_app
import logging

logger = logging.getLogger(__name__)


@celery_app.task(name="app.tasks.indexing.test_index")
def test_index(document_id: int) -> dict:
    """Test indexing task"""
    logger.info(f"Indexing document: {document_id}")
    return {"status": "success", "document_id": document_id}