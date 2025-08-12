"""
Scraping tasks
"""
from app.tasks.celery_app import celery_app
import logging

logger = logging.getLogger(__name__)


@celery_app.task(name="app.tasks.scraping.test_scrape")
def test_scrape(url: str) -> dict:
    """Test scraping task"""
    logger.info(f"Scraping URL: {url}")
    return {"status": "success", "url": url}