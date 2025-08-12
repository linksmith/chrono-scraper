"""
Meilisearch integration service
"""
import asyncio
import secrets
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta

import meilisearch
from meilisearch.models.task import TaskInfo

from app.core.config import settings
from app.models.project import Project


class MeilisearchService:
    """Service for Meilisearch operations"""
    
    _client = None
    
    @classmethod
    def get_client(cls) -> meilisearch.Client:
        """Get Meilisearch client instance"""
        if cls._client is None:
            cls._client = meilisearch.Client(
                settings.MEILISEARCH_HOST,
                settings.MEILISEARCH_MASTER_KEY
            )
        return cls._client
    
    @classmethod
    def get_index_name(cls, project: Project) -> str:
        """Get index name for project"""
        if project.index_name:
            return project.index_name
        return f"project_{project.id}_pages"
    
    @classmethod
    async def create_project_index(cls, project: Project) -> dict:
        """Create Meilisearch index for project"""
        client = cls.get_client()
        index_name = cls.get_index_name(project)
        
        try:
            # Create index
            task_info = client.create_index(index_name, {"primaryKey": "id"})
            
            # Wait for index creation
            await cls._wait_for_task(task_info.task_uid)
            
            # Configure index settings
            index = client.index(index_name)
            
            # Set searchable attributes
            searchable_attributes = [
                "title",
                "content", 
                "original_url",
                "wayback_url"
            ]
            index.update_searchable_attributes(searchable_attributes)
            
            # Set filterable attributes
            filterable_attributes = [
                "domain_id",
                "scraped_at",
                "unix_timestamp",
                "mime_type",
                "status_code",
                "processed",
                "indexed"
            ]
            index.update_filterable_attributes(filterable_attributes)
            
            # Set sortable attributes
            sortable_attributes = [
                "scraped_at",
                "unix_timestamp",
                "title"
            ]
            index.update_sortable_attributes(sortable_attributes)
            
            # Generate search key for project
            search_key = await cls.create_search_key(index_name)
            
            return {
                "index_name": index_name,
                "search_key": search_key.get("key"),
                "search_key_uid": search_key.get("uid"),
                "status": "created"
            }
            
        except Exception as e:
            raise Exception(f"Failed to create Meilisearch index: {str(e)}")
    
    @classmethod
    async def delete_project_index(cls, project: Project) -> bool:
        """Delete Meilisearch index for project"""
        client = cls.get_client()
        index_name = cls.get_index_name(project)
        
        try:
            # Delete search keys first
            if project.index_search_key_uid:
                await cls.delete_search_key(project.index_search_key_uid)
            
            # Delete index
            task_info = client.delete_index(index_name)
            await cls._wait_for_task(task_info.task_uid)
            
            return True
            
        except Exception as e:
            print(f"Failed to delete Meilisearch index: {str(e)}")
            return False
    
    @classmethod
    async def create_search_key(cls, index_name: str) -> dict:
        """Create a search-only API key for index"""
        client = cls.get_client()
        
        try:
            # Create search key with restrictions
            key_data = {
                "description": f"Search key for {index_name}",
                "actions": ["search"],
                "indexes": [index_name],
                "expiresAt": datetime.utcnow() + timedelta(days=365)  # 1 year
            }
            
            result = client.create_key(key_data)
            
            return {
                "key": result.key,
                "uid": result.uid,
                "description": result.description,
                "actions": result.actions,
                "indexes": result.indexes,
                "expires_at": result.expires_at
            }
            
        except Exception as e:
            raise Exception(f"Failed to create search key: {str(e)}")
    
    @classmethod
    async def delete_search_key(cls, key_uid: str) -> bool:
        """Delete search API key"""
        client = cls.get_client()
        
        try:
            client.delete_key(key_uid)
            return True
        except Exception as e:
            print(f"Failed to delete search key: {str(e)}")
            return False
    
    @classmethod
    async def add_documents(
        cls, 
        project: Project, 
        documents: List[Dict[str, Any]]
    ) -> bool:
        """Add documents to project index"""
        if not documents:
            return True
        
        client = cls.get_client()
        index_name = cls.get_index_name(project)
        
        try:
            index = client.index(index_name)
            task_info = index.add_documents(documents)
            await cls._wait_for_task(task_info.task_uid)
            
            return True
            
        except Exception as e:
            print(f"Failed to add documents to index: {str(e)}")
            return False
    
    @classmethod
    async def update_documents(
        cls, 
        project: Project, 
        documents: List[Dict[str, Any]]
    ) -> bool:
        """Update documents in project index"""
        if not documents:
            return True
        
        client = cls.get_client()
        index_name = cls.get_index_name(project)
        
        try:
            index = client.index(index_name)
            task_info = index.update_documents(documents)
            await cls._wait_for_task(task_info.task_uid)
            
            return True
            
        except Exception as e:
            print(f"Failed to update documents in index: {str(e)}")
            return False
    
    @classmethod
    async def delete_documents(
        cls, 
        project: Project, 
        document_ids: List[str]
    ) -> bool:
        """Delete documents from project index"""
        if not document_ids:
            return True
        
        client = cls.get_client()
        index_name = cls.get_index_name(project)
        
        try:
            index = client.index(index_name)
            task_info = index.delete_documents(document_ids)
            await cls._wait_for_task(task_info.task_uid)
            
            return True
            
        except Exception as e:
            print(f"Failed to delete documents from index: {str(e)}")
            return False
    
    @classmethod
    async def search(
        cls,
        project: Project,
        query: str,
        filters: Optional[str] = None,
        sort: Optional[List[str]] = None,
        limit: int = 20,
        offset: int = 0
    ) -> dict:
        """Search documents in project index"""
        client = cls.get_client()
        index_name = cls.get_index_name(project)
        
        try:
            index = client.index(index_name)
            
            search_params = {
                "q": query,
                "limit": limit,
                "offset": offset
            }
            
            if filters:
                search_params["filter"] = filters
            
            if sort:
                search_params["sort"] = sort
            
            results = index.search(**search_params)
            
            return {
                "hits": results.hits,
                "total_hits": results.estimated_total_hits,
                "query": query,
                "processing_time": results.processing_time_ms,
                "limit": limit,
                "offset": offset
            }
            
        except Exception as e:
            raise Exception(f"Search failed: {str(e)}")
    
    @classmethod
    async def get_index_stats(cls, project: Project) -> dict:
        """Get index statistics"""
        client = cls.get_client()
        index_name = cls.get_index_name(project)
        
        try:
            index = client.index(index_name)
            stats = index.get_stats()
            
            return {
                "number_of_documents": stats.number_of_documents,
                "is_indexing": stats.is_indexing,
                "field_distribution": stats.field_distribution
            }
            
        except Exception as e:
            print(f"Failed to get index stats: {str(e)}")
            return {
                "number_of_documents": 0,
                "is_indexing": False,
                "field_distribution": {}
            }
    
    @classmethod
    async def rebuild_index(cls, project: Project) -> bool:
        """Rebuild project index from scratch"""
        try:
            # Delete existing index
            await cls.delete_project_index(project)
            
            # Create new index
            await cls.create_project_index(project)
            
            # Note: Documents will need to be re-added by the scraping system
            
            return True
            
        except Exception as e:
            print(f"Failed to rebuild index: {str(e)}")
            return False
    
    @classmethod
    async def _wait_for_task(cls, task_uid: int, timeout: int = 30) -> bool:
        """Wait for Meilisearch task to complete"""
        client = cls.get_client()
        
        start_time = datetime.utcnow()
        
        while True:
            task = client.get_task(task_uid)
            
            if task.status in ["succeeded", "failed"]:
                return task.status == "succeeded"
            
            # Check timeout
            if (datetime.utcnow() - start_time).seconds > timeout:
                raise Exception(f"Task {task_uid} timed out")
            
            # Wait a bit before checking again
            await asyncio.sleep(0.5)
    
    @classmethod
    async def health_check(cls) -> dict:
        """Check Meilisearch health"""
        try:
            client = cls.get_client()
            health = client.health()
            
            return {
                "status": "healthy" if health.status == "available" else "unhealthy",
                "version": client.get_version().pkg_version if hasattr(client.get_version(), 'pkg_version') else "unknown"
            }
            
        except Exception as e:
            return {
                "status": "unhealthy",
                "error": str(e)
            }