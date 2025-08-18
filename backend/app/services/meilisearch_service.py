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
from ..models.extraction_data import ExtractedContent

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
    
    def _prepare_document(self, page: Page, extracted_content: Optional[ExtractedContent] = None, 
                         entities: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        """Prepare a page document for indexing with entity support"""
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
                'source_url': extracted_content.source_url,
                'firecrawl_status_code': extracted_content.status_code,
                'extraction_error': extracted_content.error,
                'word_count': extracted_content.word_count,
                'character_count': extracted_content.character_count,
                'extraction_method': extracted_content.extraction_method,
                'extraction_time': extracted_content.extraction_time
            })
            
            # Use extracted title if available
            if extracted_content.title and extracted_content.title != "No Title":
                doc['title'] = extracted_content.title
        
        # Add entity information for filtering and faceted search
        if entities:
            doc.update(self._prepare_entity_fields(entities))
        
        return doc
    
    def _prepare_entity_fields(self, entities: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Prepare entity fields for Meilisearch indexing and filtering"""
        entity_fields = {
            # Arrays for filtering
            'entity_person_names': [],
            'entity_organization_names': [],
            'entity_location_names': [],
            'entity_event_names': [],
            'entity_product_names': [],
            'entity_all_names': [],
            
            # Structured entity data for display
            'entities': {
                'persons': [],
                'organizations': [],
                'locations': [],
                'events': [],
                'products': [],
                'other': []
            },
            
            # Entity statistics
            'entity_count': len(entities),
            'entity_extraction_backend': None,
            'entity_confidence_avg': 0.0,
            'has_wikidata_links': False
        }
        
        total_confidence = 0.0
        backend_set = set()
        
        for entity in entities:
            entity_type = entity.get('entity_type')
            entity_text = entity.get('text', '').strip()
            confidence = entity.get('confidence', 0.0)
            extraction_method = entity.get('extraction_method', 'unknown')
            
            if not entity_text:
                continue
            
            # Add to all entities list
            entity_fields['entity_all_names'].append(entity_text)
            
            # Categorize by entity type
            if hasattr(entity_type, 'value'):
                entity_type_str = entity_type.value
            else:
                entity_type_str = str(entity_type).lower()
            
            # Prepare entity data for structured storage
            entity_data = {
                'text': entity_text,
                'confidence': confidence,
                'context': entity.get('context', ''),
                'extraction_method': extraction_method
            }
            
            # Add Wikidata information if available
            if entity.get('wikidata'):
                entity_data['wikidata'] = entity['wikidata']
                entity_fields['has_wikidata_links'] = True
            
            # Add to appropriate category arrays
            if 'person' in entity_type_str:
                entity_fields['entity_person_names'].append(entity_text)
                entity_fields['entities']['persons'].append(entity_data)
                
            elif 'organization' in entity_type_str:
                entity_fields['entity_organization_names'].append(entity_text)
                entity_fields['entities']['organizations'].append(entity_data)
                
            elif 'location' in entity_type_str:
                entity_fields['entity_location_names'].append(entity_text)
                entity_fields['entities']['locations'].append(entity_data)
                
            elif 'event' in entity_type_str:
                entity_fields['entity_event_names'].append(entity_text)
                entity_fields['entities']['events'].append(entity_data)
                
            elif 'product' in entity_type_str:
                entity_fields['entity_product_names'].append(entity_text)
                entity_fields['entities']['products'].append(entity_data)
                
            else:
                entity_fields['entities']['other'].append(entity_data)
            
            # Collect statistics
            total_confidence += confidence
            backend_set.add(extraction_method)
        
        # Calculate average confidence
        if entities:
            entity_fields['entity_confidence_avg'] = total_confidence / len(entities)
        
        # Set primary extraction backend
        if backend_set:
            entity_fields['entity_extraction_backend'] = sorted(list(backend_set))[0]
        
        return entity_fields
    
    async def configure_entity_filtering(self, index_name: str) -> Dict[str, Any]:
        """Configure filterable attributes for entity-based search"""
        if not MEILISEARCH_AVAILABLE:
            logger.info(f"Mock: Configured entity filtering for index '{index_name}'")
            return {"status": "configured"}
            
        if not self._connected:
            await self.connect()
        
        try:
            index = self.client.index(index_name)
            
            # Set filterable attributes for entity search
            filterable_attributes = [
                # Basic page attributes
                'domain_id',
                'mime_type',
                'status_code',
                'language',
                'capture_date',
                'unix_timestamp',
                
                # Firecrawl metadata
                'author',
                'source_url',
                'firecrawl_status_code',
                'extraction_method',
                'published_date',
                'word_count',
                'character_count',
                'extraction_time',
                
                # Entity filtering attributes
                'entity_person_names',
                'entity_organization_names', 
                'entity_location_names',
                'entity_event_names',
                'entity_product_names',
                'entity_all_names',
                'entity_count',
                'entity_extraction_backend',
                'entity_confidence_avg',
                'has_wikidata_links'
            ]
            
            task = await index.update_filterable_attributes(filterable_attributes)
            logger.info(f"Configured entity filtering for index '{index_name}'")
            
            return task
            
        except MeilisearchApiError as e:
            logger.error(f"Failed to configure entity filtering for {index_name}: {str(e)}")
            raise MeilisearchException(f"Entity filtering configuration failed: {str(e)}")
    
    async def index_document_with_entities(self, index_name: str, page: Page, 
                                         extracted_content: Optional[ExtractedContent] = None,
                                         entities: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        """Index a page document with entity information"""
        if not MEILISEARCH_AVAILABLE:
            logger.debug(f"Mock: Indexed page {page.id} with entities in index '{index_name}'")
            return {"status": "indexed"}
            
        if not self._connected:
            await self.connect()
        
        try:
            index = self.client.index(index_name)
            document = self._prepare_document(page, extracted_content, entities)
            
            task = await index.add_documents([document])
            
            if entities:
                logger.debug(f"Indexed page {page.id} with {len(entities)} entities in index '{index_name}'")
            else:
                logger.debug(f"Indexed page {page.id} in index '{index_name}'")
            
            return task
            
        except MeilisearchApiError as e:
            logger.error(f"Failed to index page {page.id}: {str(e)}")
            raise MeilisearchException(f"Document indexing failed: {str(e)}")
    
    async def index_document(self, index_name: str, page: Page, 
                           extracted_content: Optional[ExtractedContent] = None) -> Dict[str, Any]:
        """Index a single page document (legacy method without entities)"""
        return await self.index_document_with_entities(index_name, page, extracted_content, None)
    
    async def search_with_entity_filters(self, index_name: str, query: str = "", 
                                       filters: Dict[str, Any] = None,
                                       facets: List[str] = None,
                                       limit: int = 20, offset: int = 0) -> Dict[str, Any]:
        """Search with entity-based filtering and faceting"""
        if not MEILISEARCH_AVAILABLE:
            logger.debug(f"Mock: Entity search in index '{index_name}' with query '{query}'")
            return {"hits": [], "totalHits": 0, "facetDistribution": {}}
            
        if not self._connected:
            await self.connect()
        
        try:
            index = self.client.index(index_name)
            
            search_params = {
                'limit': limit,
                'offset': offset
            }
            
            # Add entity filters
            if filters:
                filter_strings = []
                
                # Convert filter dict to Meilisearch filter format
                for field, value in filters.items():
                    if isinstance(value, list):
                        # Multiple values (OR condition)
                        if value:
                            or_conditions = [f"{field} = '{v}'" for v in value]
                            filter_strings.append(f"({' OR '.join(or_conditions)})")
                    else:
                        # Single value
                        if isinstance(value, str):
                            filter_strings.append(f"{field} = '{value}'")
                        else:
                            filter_strings.append(f"{field} = {value}")
                
                if filter_strings:
                    search_params['filter'] = ' AND '.join(filter_strings)
            
            # Add faceting for entity types (simplified for now)
            if facets:
                search_params['facets'] = facets
            
            result = await index.search(query, **search_params)
            
            # Convert new API result to old format for backward compatibility
            compatible_result = {
                'hits': result.hits,
                'totalHits': result.estimated_total_hits or 0,
                'facetDistribution': result.facet_distribution or {}
            }
            
            logger.debug(f"Entity search in '{index_name}' returned {compatible_result['totalHits']} results")
            return compatible_result
            
        except MeilisearchApiError as e:
            logger.error(f"Entity search failed in {index_name}: {str(e)}")
            raise MeilisearchException(f"Entity search failed: {str(e)}")
    
    @classmethod
    async def create_project_index(cls, project) -> Dict[str, Any]:
        """Create a project-specific Meilisearch index (class method for backwards compatibility)"""
        index_name = f"project_{project.id}"
        async with meilisearch_service as ms:
            result = await ms.create_index(index_name, "id")
            await ms.configure_entity_filtering(index_name)
            # Normalize return to match callers expecting dict
            if isinstance(result, dict):
                return {"index_name": index_name, **result}
            return {"index_name": index_name, "status": "created"}

    @classmethod
    async def delete_project_index(cls, project) -> Dict[str, Any]:
        """Delete a project-specific Meilisearch index (class method for backwards compatibility)"""
        if not MEILISEARCH_AVAILABLE:
            logger.info(f"Mock: Deleted index 'project_{project.id}'")
            return {"status": "deleted"}

        index_name = f"project_{project.id}"
        async with meilisearch_service as ms:
            try:
                if ms.client:
                    task = await ms.client.delete_index_if_exists(index_name)
                    logger.info(f"Deleted index '{index_name}'")
                    return {"status": "deleted"}
                else:
                    return {"status": "no_client"}
            except Exception as e:
                logger.error(f"Failed to delete index '{index_name}': {str(e)}")
                return {"status": "error", "message": str(e)}

    # Convenience helpers required by tasks
    @staticmethod
    def get_index_name(project) -> str:
        return getattr(project, 'index_name', None) or f"project_{project.id}"

    @classmethod
    async def get_index_stats(cls, project) -> Dict[str, Any]:
        if not MEILISEARCH_AVAILABLE:
            return {"number_of_documents": 0}
        index_name = cls.get_index_name(project)
        async with meilisearch_service as ms:
            if not ms.client:
                return {"number_of_documents": 0}
            index = ms.client.index(index_name)
            try:
                stats = await index.get_stats()
                return dict(stats)
            except Exception as e:
                logger.error(f"Failed to get stats for index '{index_name}': {e}")
                return {}

    @classmethod
    async def add_documents(cls, project, documents: List[Dict[str, Any]]) -> bool:
        if not MEILISEARCH_AVAILABLE:
            return True
        index_name = cls.get_index_name(project)
        async with meilisearch_service as ms:
            if not ms.client:
                return True
            index = ms.client.index(index_name)
            await index.add_documents(documents)
            return True

    @classmethod
    async def update_documents(cls, project, documents: List[Dict[str, Any]]) -> bool:
        return await cls.add_documents(project, documents)

    @classmethod
    async def delete_documents(cls, project, document_ids: List[str]) -> bool:
        if not MEILISEARCH_AVAILABLE:
            return True
        index_name = cls.get_index_name(project)
        async with meilisearch_service as ms:
            if not ms.client:
                return True
            index = ms.client.index(index_name)
            await index.delete_documents(document_ids)
            return True

    @classmethod
    async def rebuild_index(cls, project) -> bool:
        """Delete and recreate the project's index with settings."""
        await cls.delete_project_index(project)
        await cls.create_project_index(project)
        return True

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