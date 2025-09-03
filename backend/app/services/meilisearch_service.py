"""
Meilisearch integration service for full-text search indexing
CLEANED VERSION - Legacy Page model support removed
"""
import asyncio
import logging
from typing import Dict, Any, List, Optional

try:
    import meilisearch_python_async as meilisearch
    from meilisearch_python_async.errors import MeilisearchApiError, MeilisearchError
    MEILISEARCH_AVAILABLE = True
except ImportError:
    MEILISEARCH_AVAILABLE = False

from ..core.config import settings

logger = logging.getLogger(__name__)


class MeilisearchException(Exception):
    """Base exception for Meilisearch operations"""
    pass


class MeilisearchService:
    """Service for managing Meilisearch operations"""
    
    def __init__(self, api_key: Optional[str] = None, use_master_key: bool = False):
        """
        Initialize with specific API key or default to master key
        
        Args:
            api_key: Specific API key to use (project key, public key, etc.)
            use_master_key: Force use of master key for admin operations
        """
        if not MEILISEARCH_AVAILABLE:
            logger.warning("Meilisearch not available, using mock service")
            
        self.client = None
        self.host = settings.MEILISEARCH_HOST or "http://localhost:7700"
        
        # Key selection logic for secure multi-tenancy
        if use_master_key or not api_key:
            self.api_key = settings.MEILISEARCH_MASTER_KEY
            self.use_master_key = True
        else:
            self.api_key = api_key
            self.use_master_key = False
            
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
    
    @classmethod
    async def for_project(cls, project) -> 'MeilisearchService':
        """
        Create service instance with project-specific key for secure access
        
        Args:
            project: Project instance with search key
            
        Returns:
            MeilisearchService configured with project's dedicated key
        """
        if not project.index_search_key:
            # Fallback to master key for legacy projects during migration
            logger.warning(f"Project {project.id} missing search key, using master key fallback")
            return cls(use_master_key=True)
        
        return cls(api_key=project.index_search_key)
    
    @classmethod
    async def for_admin(cls) -> 'MeilisearchService':
        """
        Create service instance with master key for admin operations only
        
        Use this for:
        - Index creation/deletion
        - Key management
        - System administration
        
        Returns:
            MeilisearchService configured with master key
        """
        return cls(use_master_key=True)
    
    @classmethod
    async def for_public(cls, public_search_config) -> 'MeilisearchService':
        """
        Create service instance with public search key
        
        Args:
            public_search_config: PublicSearchConfig with search key
            
        Returns:
            MeilisearchService configured with public key
        """
        if not public_search_config.search_key:
            raise MeilisearchException("Public search config missing search key")
        
        return cls(api_key=public_search_config.search_key)
    
    @classmethod
    async def for_tenant_token(cls, tenant_token: str) -> 'MeilisearchService':
        """
        Create service instance with JWT tenant token for shared access
        
        Args:
            tenant_token: JWT tenant token from MeilisearchKeyManager
            
        Returns:
            MeilisearchService configured with tenant token
        """
        return cls(api_key=tenant_token)
    
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
    
    # LEGACY FUNCTIONS REMOVED - Page model no longer supported
    # The following functions were removed as part of migrating to shared pages architecture:
    # - _prepare_document
    # - index_document_with_entities 
    # - index_document
    # - reindex_with_optimization
    # Equivalent functionality now exists in shared_pages_meilisearch.py
    
    def _truncate_content(self, content: str, max_length: int) -> str:
        """Intelligently truncate content while preserving word boundaries"""
        if not content or len(content) <= max_length:
            return content or ''
        
        # Truncate at word boundary
        truncated = content[:max_length]
        last_space = truncated.rfind(' ')
        if last_space > max_length * 0.8:  # Only truncate at word if it's not too short
            truncated = truncated[:last_space]
        
        return truncated + '...'
    
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
    
    async def configure_optimized_index(self, index_name: str) -> Dict[str, Any]:
        """Configure index with optimized settings for scale"""
        if not MEILISEARCH_AVAILABLE:
            return {"status": "configured"}
        
        if not self._connected:
            await self.connect()
        
        try:
            index = self.client.index(index_name)
            
            # Apply optimized configuration
            tasks = []
            
            # Searchable attributes (prioritized)
            tasks.append(index.update_searchable_attributes([
                'title', 'text', 'meta_description', 'author',
                'entity_person_names', 'entity_organization_names', 'entity_location_names'
            ]))
            
            # Filterable attributes (minimal set)
            tasks.append(index.update_filterable_attributes([
                'domain_id', 'mime_type', 'language', 'review_status', 
                'page_category', 'priority_level', 'tags', 'published_date', 
                'capture_date', 'entity_count', 'status_code'
            ]))
            
            # Sortable attributes
            tasks.append(index.update_sortable_attributes([
                'published_date', 'capture_date', 'word_count', 'quality_score',
                'entity_count', 'created_at', 'scraped_at'
            ]))
            
            # Display attributes (minimal for performance)
            tasks.append(index.update_displayed_attributes([
                'id', 'page_id', 'title', 'original_url', 'content_url',
                'meta_description', 'author', 'published_date', 'word_count',
                'review_status', 'tags', 'quality_score', 'language'
            ]))
            
            # Custom ranking rules for OSINT relevance
            tasks.append(index.update_ranking_rules([
                'words', 'typo', 'proximity', 'attribute',
                'quality_score:desc', 'published_date:desc', 'word_count:desc'
            ]))
            
            # Configure typo tolerance for accuracy
            tasks.append(index.update_typo_tolerance({
                'enabled': True,
                'minWordSizeForTypos': {'oneTypo': 4, 'twoTypos': 8}
            }))
            
            # Wait for all configuration tasks
            await asyncio.gather(*tasks)
            
            logger.info(f"Optimized configuration applied to index '{index_name}'")
            return {"status": "configured", "tasks": len(tasks)}
            
        except MeilisearchApiError as e:
            logger.error(f"Failed to configure optimized index {index_name}: {str(e)}")
            raise MeilisearchException(f"Index configuration failed: {str(e)}")
    
    async def add_documents_batch(self, index_name: str, documents: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Add multiple documents to index in batch"""
        if not MEILISEARCH_AVAILABLE:
            return {"status": "indexed"}
        
        if not self._connected:
            await self.connect()
        
        try:
            index = self.client.index(index_name)
            task = await index.add_documents(documents)
            logger.debug(f"Batch indexed {len(documents)} documents in index '{index_name}'")
            return task
        except MeilisearchApiError as e:
            logger.error(f"Failed to batch index documents: {str(e)}")
            raise MeilisearchException(f"Batch indexing failed: {str(e)}")
    
    @classmethod
    async def create_project_index(cls, project) -> Dict[str, Any]:
        """Create a project-specific Meilisearch index using admin privileges"""
        index_name = f"project_{project.id}"
        
        # Use admin service for index creation (requires master key)
        admin_service = await cls.for_admin()
        async with admin_service as ms:
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
        admin_service = await cls.for_admin()
        async with admin_service as ms:
            try:
                if ms.client:
                    await ms.client.delete_index_if_exists(index_name)
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
        admin_service = await cls.for_admin()
        async with admin_service as ms:
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
        admin_service = await cls.for_admin()
        async with admin_service as ms:
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
        admin_service = await cls.for_admin()
        async with admin_service as ms:
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
    admin_service = await MeilisearchService.for_admin()
    async with admin_service as ms:
        return await ms.create_index(index_name, "id")

# LEGACY FUNCTION REMOVED: index_page
# This function was removed as part of migrating from legacy Page model to shared pages architecture
# Equivalent functionality now exists in shared_pages_meilisearch.py