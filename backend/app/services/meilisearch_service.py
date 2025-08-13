"""
Meilisearch integration service for full-text search indexing
"""
import asyncio
import logging
from datetime import datetime
from typing import Dict, Any, List, Optional

try:
    import meilisearch_python_async as meilisearch
    from meilisearch_python_async.errors import MeilisearchApiError, MeilisearchError
    MEILISEARCH_AVAILABLE = True
except ImportError:
    MEILISEARCH_AVAILABLE = False

from ..core.config import settings
from ..models.project import Page
from .content_extractor import ExtractedContent

logger = logging.getLogger(__name__)


class MeilisearchException(Exception):
    """Base exception for Meilisearch operations"""
    pass


class MeilisearchService:
    """Service for managing Meilisearch operations"""
    
    def __init__(self):
        if not MEILISEARCH_AVAILABLE:
            logger.warning("Meilisearch not available, using mock service")
            
        self.client = None
        self.host = settings.MEILISEARCH_HOST or "http://localhost:7700"
        self.api_key = settings.MEILISEARCH_MASTER_KEY
        self._connected = False
        
    async def connect(self):
        """Initialize Meilisearch client"""
        if not MEILISEARCH_AVAILABLE:
            logger.info("Mock Meilisearch service connected")
            self._connected = True
            return
            
        if not self._connected:
            try:
                self.client = meilisearch.Client(
                    url=self.host,
                    api_key=self.api_key
                )
                
                # Test connection
                health = await self.client.health()
                logger.info(f"Connected to Meilisearch at {self.host}: {health}")
                self._connected = True
                
            except Exception as e:
                logger.error(f"Failed to connect to Meilisearch: {str(e)}")
                raise MeilisearchException(f"Connection failed: {str(e)}")
    
    async def disconnect(self):
        """Close Meilisearch client"""
        if not MEILISEARCH_AVAILABLE:
            logger.info("Mock Meilisearch service disconnected")
            self._connected = False
            return
            
        if self.client:
            await self.client.aclose()
            self._connected = False
    
    async def __aenter__(self):
        await self.connect()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.disconnect()
    
    async def create_index(self, index_name: str, primary_key: str = "id") -> Dict[str, Any]:
        """Create a new Meilisearch index"""
        if not MEILISEARCH_AVAILABLE:
            logger.info(f"Mock: Created index '{index_name}'")
            return {"status": "created"}
            
        if not self._connected:
            await self.connect()
        
        try:
            task = await self.client.create_index(index_name, primary_key)
            logger.info(f"Created index '{index_name}' with primary key '{primary_key}'")
            return task
            
        except MeilisearchApiError as e:
            if e.code == "index_already_exists":
                logger.info(f"Index '{index_name}' already exists")
                return {"status": "exists"}
            else:
                logger.error(f"Failed to create index '{index_name}': {str(e)}")
                raise MeilisearchException(f"Index creation failed: {str(e)}")
    
    def _prepare_document(self, page: Page, extracted_content: Optional[ExtractedContent] = None) -> Dict[str, Any]:
        """Prepare a page document for indexing"""
        doc = {
            'id': f"page_{page.id}",
            'page_id': page.id,
            'domain_id': page.domain_id,
            'original_url': page.original_url,
            'wayback_url': page.wayback_url,
            'title': page.title or "Untitled",
            'content': page.content or "",
            'unix_timestamp': page.unix_timestamp,
            'mime_type': page.mime_type,
            'status_code': page.status_code,
            'capture_date': page.capture_date.isoformat() if page.capture_date else None,
            'created_at': page.created_at.isoformat(),
            'updated_at': page.updated_at.isoformat(),
            'scraped_at': page.scraped_at.isoformat() if page.scraped_at else None
        }
        
        # Add extracted content if available
        if extracted_content:
            doc.update({
                'extracted_title': extracted_content.title,
                'extracted_text': extracted_content.text,
                'markdown_content': extracted_content.markdown,
                'meta_description': extracted_content.meta_description,
                'meta_keywords': extracted_content.meta_keywords,
                'author': extracted_content.author,
                'published_date': extracted_content.published_date.isoformat() if extracted_content.published_date else None,
                'language': extracted_content.language,
                'word_count': extracted_content.word_count,
                'character_count': extracted_content.character_count,
                'extraction_method': extracted_content.extraction_method
            })
            
            # Use extracted title if available
            if extracted_content.title and extracted_content.title != "No Title":
                doc['title'] = extracted_content.title
        
        return doc
    
    async def index_document(self, index_name: str, page: Page, 
                           extracted_content: Optional[ExtractedContent] = None) -> Dict[str, Any]:
        """Index a single page document"""
        if not MEILISEARCH_AVAILABLE:
            logger.debug(f"Mock: Indexed page {page.id} in index '{index_name}'")
            return {"status": "indexed"}
            
        if not self._connected:
            await self.connect()
        
        try:
            index = self.client.index(index_name)
            document = self._prepare_document(page, extracted_content)
            
            task = await index.add_documents([document])
            logger.debug(f"Indexed page {page.id} in index '{index_name}'")
            
            return task
            
        except MeilisearchApiError as e:
            logger.error(f"Failed to index page {page.id}: {str(e)}")
            raise MeilisearchException(f"Document indexing failed: {str(e)}")


# Global service instance
meilisearch_service = MeilisearchService()


# Convenience functions
async def create_project_index(project_id: int, index_name: str) -> Dict[str, Any]:
    """Create and configure an index for a project"""
    async with meilisearch_service as ms:
        return await ms.create_index(index_name, "id")


async def index_page(index_name: str, page: Page, 
                   extracted_content: Optional[ExtractedContent] = None) -> Dict[str, Any]:
    """Index a single page"""
    async with meilisearch_service as ms:
        return await ms.index_document(index_name, page, extracted_content)