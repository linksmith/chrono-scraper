"""
Intelligent batch synchronization manager for Meilisearch updates

This service provides:
1. Redis-based queuing for batch operations
2. Priority-based processing (deletes > new content > updates)
3. Deduplication of multiple updates to same page
4. Smart batching with size and time-based triggers
5. Error handling and retry logic
"""

import json
import logging
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, asdict
from enum import Enum

try:
    import redis.asyncio as redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False

from ..core.config import settings

logger = logging.getLogger(__name__)


class SyncOperation(str, Enum):
    """Types of synchronization operations"""
    INDEX = "index"      # New page
    UPDATE = "update"    # Page content/metadata update
    DELETE = "delete"    # Page deletion


@dataclass
class SyncRequest:
    """Individual synchronization request"""
    page_id: int
    operation: SyncOperation
    data: Dict[str, Any]
    timestamp: datetime
    priority: float
    project_id: int
    retry_count: int = 0
    
    def to_json(self) -> str:
        """Convert to JSON string for Redis storage"""
        data_dict = asdict(self)
        data_dict['timestamp'] = self.timestamp.isoformat()
        data_dict['operation'] = self.operation.value
        return json.dumps(data_dict)
    
    @classmethod
    def from_json(cls, json_str: str) -> 'SyncRequest':
        """Create from JSON string"""
        data = json.loads(json_str)
        data['timestamp'] = datetime.fromisoformat(data['timestamp'])
        data['operation'] = SyncOperation(data['operation'])
        return cls(**data)


class BatchSyncManager:
    """Manages intelligent batching of Meilisearch synchronization operations"""
    
    def __init__(self):
        self.redis_client: Optional[redis.Redis] = None
        self.batch_size = settings.MEILISEARCH_BATCH_SIZE or 100
        self.batch_timeout = settings.MEILISEARCH_BATCH_TIMEOUT or 30  # seconds
        self.max_retries = settings.MEILISEARCH_MAX_RETRIES or 3
        self.redis_url = f"redis://{settings.REDIS_HOST}:{settings.REDIS_PORT or 6379}"
        
        # Redis keys
        self.sync_queue_key = "meilisearch:sync_queue"
        self.batch_lock_key = "meilisearch:batch_lock"
        self.stats_key = "meilisearch:sync_stats"
        
    async def connect(self):
        """Initialize Redis connection"""
        if not REDIS_AVAILABLE:
            logger.warning("Redis not available, using mock batch sync manager")
            return
        
        try:
            self.redis_client = redis.from_url(
                self.redis_url,
                encoding="utf-8",
                decode_responses=True,
                socket_keepalive=True,
                socket_keepalive_options={}
            )
            
            # Test connection
            await self.redis_client.ping()
            logger.info(f"Connected to Redis for batch sync: {self.redis_url}")
            
        except Exception as e:
            logger.error(f"Failed to connect to Redis: {str(e)}")
            self.redis_client = None
    
    async def disconnect(self):
        """Close Redis connection"""
        if self.redis_client:
            await self.redis_client.aclose()
            self.redis_client = None
    
    async def __aenter__(self):
        await self.connect()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.disconnect()
    
    def _calculate_priority(self, operation: SyncOperation, project_id: int) -> float:
        """Calculate operation priority (higher = more urgent)"""
        base_time = datetime.utcnow().timestamp()
        
        # Priority modifiers
        if operation == SyncOperation.DELETE:
            return base_time + 10000  # Highest priority
        elif operation == SyncOperation.INDEX:
            return base_time + 1000   # High priority (new content)
        else:  # UPDATE
            return base_time          # Normal priority
    
    async def queue_sync_operation(self, page_id: int, operation: SyncOperation, 
                                 project_id: int, data: Dict[str, Any]) -> bool:
        """Queue a page synchronization operation"""
        if not self.redis_client:
            logger.warning("Redis not available, skipping batch sync queue")
            return False
        
        try:
            # Create sync request
            sync_request = SyncRequest(
                page_id=page_id,
                operation=operation,
                data=data,
                timestamp=datetime.utcnow(),
                priority=self._calculate_priority(operation, project_id),
                project_id=project_id
            )
            
            # Check for existing request for same page (deduplication)
            existing_key = await self._find_existing_request(page_id, project_id)
            if existing_key:
                # Remove old request (will be replaced with newer one)
                await self.redis_client.zrem(self.sync_queue_key, existing_key)
                logger.debug(f"Replaced existing sync request for page {page_id}")
            
            # Add to priority queue (sorted set)
            queue_key = f"{project_id}:{page_id}:{operation.value}:{sync_request.timestamp.timestamp()}"
            await self.redis_client.zadd(
                self.sync_queue_key,
                {queue_key: sync_request.priority}
            )
            
            # Store request data
            await self.redis_client.hset(
                f"{self.sync_queue_key}:data",
                queue_key,
                sync_request.to_json()
            )
            
            # Update statistics
            await self._update_stats("queued", operation.value)
            
            # Check if we should trigger batch processing
            queue_size = await self.redis_client.zcard(self.sync_queue_key)
            if queue_size >= self.batch_size:
                await self._trigger_batch_processing()
            
            logger.debug(f"Queued {operation.value} operation for page {page_id} (queue size: {queue_size})")
            return True
            
        except Exception as e:
            logger.error(f"Failed to queue sync operation for page {page_id}: {str(e)}")
            return False
    
    async def _find_existing_request(self, page_id: int, project_id: int) -> Optional[str]:
        """Find existing request for the same page"""
        try:
            # Get all queue keys for this project/page
            all_keys = await self.redis_client.zrange(self.sync_queue_key, 0, -1)
            
            for key in all_keys:
                if key.startswith(f"{project_id}:{page_id}:"):
                    return key
            return None
        except Exception:
            return None
    
    async def _trigger_batch_processing(self):
        """Trigger batch processing via Celery if available"""
        try:
            # Try to import and trigger Celery task
            from app.tasks.meilisearch_sync import process_sync_batch
            process_sync_batch.delay()
            logger.debug("Triggered batch processing via Celery")
        except ImportError:
            # Celery not available, process inline (for development)
            await self._process_batch_inline()
    
    async def _process_batch_inline(self):
        """Process batch inline (for development/testing)"""
        try:
            batch_operations = await self.get_batch_operations()
            if batch_operations:
                logger.info(f"Processing {len(batch_operations)} sync operations inline")
                await self._process_operations_batch(batch_operations)
        except Exception as e:
            logger.error(f"Inline batch processing failed: {str(e)}")
    
    async def get_batch_operations(self, max_operations: Optional[int] = None) -> List[Tuple[str, SyncRequest]]:
        """Get a batch of operations to process"""
        if not self.redis_client:
            return []
        
        batch_size = max_operations or self.batch_size
        
        try:
            # Acquire batch processing lock
            lock_acquired = await self.redis_client.set(
                self.batch_lock_key, 
                "processing",
                nx=True,
                ex=300  # 5 minute lock timeout
            )
            
            if not lock_acquired:
                logger.debug("Batch processing already in progress")
                return []
            
            # Get highest priority operations
            queue_keys = await self.redis_client.zrevrange(
                self.sync_queue_key, 0, batch_size - 1
            )
            
            if not queue_keys:
                await self.redis_client.delete(self.batch_lock_key)
                return []
            
            # Get operation data
            operations = []
            for queue_key in queue_keys:
                request_data = await self.redis_client.hget(
                    f"{self.sync_queue_key}:data", 
                    queue_key
                )
                
                if request_data:
                    try:
                        sync_request = SyncRequest.from_json(request_data)
                        operations.append((queue_key, sync_request))
                    except Exception as e:
                        logger.warning(f"Failed to parse sync request {queue_key}: {str(e)}")
            
            return operations
            
        except Exception as e:
            logger.error(f"Failed to get batch operations: {str(e)}")
            # Release lock on error
            await self.redis_client.delete(self.batch_lock_key)
            return []
    
    def group_operations(self, operations: List[Tuple[str, SyncRequest]]) -> Dict[str, List[Tuple[str, SyncRequest]]]:
        """Group operations by type for efficient processing"""
        grouped = {
            SyncOperation.DELETE.value: [],
            SyncOperation.INDEX.value: [],
            SyncOperation.UPDATE.value: []
        }
        
        for queue_key, sync_request in operations:
            grouped[sync_request.operation.value].append((queue_key, sync_request))
        
        return grouped
    
    async def _process_operations_batch(self, operations: List[Tuple[str, SyncRequest]]) -> Dict[str, Any]:
        """Process a batch of operations"""
        from app.services.meilisearch_service import meilisearch_service
        
        results = {
            'processed': 0,
            'errors': 0,
            'by_operation': {}
        }
        
        try:
            # Group operations by type
            grouped_ops = self.group_operations(operations)
            
            async with meilisearch_service as ms:
                # Process deletes first (highest priority)
                if grouped_ops[SyncOperation.DELETE.value]:
                    delete_ops = grouped_ops[SyncOperation.DELETE.value]
                    await self._process_delete_operations(ms, delete_ops, results)
                
                # Process updates and indexes together
                update_index_ops = (
                    grouped_ops[SyncOperation.INDEX.value] + 
                    grouped_ops[SyncOperation.UPDATE.value]
                )
                if update_index_ops:
                    await self._process_index_operations(ms, update_index_ops, results)
            
            results['processed'] = len(operations) - results['errors']
            
        except Exception as e:
            logger.error(f"Batch processing failed: {str(e)}")
            results['errors'] = len(operations)
            results['error_message'] = str(e)
        
        return results
    
    async def _process_delete_operations(self, ms, operations: List[Tuple[str, SyncRequest]], results: Dict[str, Any]):
        """Process delete operations"""
        delete_ids = []
        successful_keys = []
        
        for queue_key, sync_request in operations:
            try:
                document_id = f"page_{sync_request.page_id}"
                delete_ids.append(document_id)
                successful_keys.append(queue_key)
            except Exception as e:
                logger.warning(f"Failed to prepare delete for page {sync_request.page_id}: {str(e)}")
                results['errors'] += 1
        
        if delete_ids:
            try:
                # Group by project for deletion
                projects_deletes = {}
                for i, (queue_key, sync_request) in enumerate([op for op in operations if queue_key in successful_keys]):
                    project_id = sync_request.project_id
                    if project_id not in projects_deletes:
                        projects_deletes[project_id] = []
                    projects_deletes[project_id].append(delete_ids[i])
                
                # Delete from each project index
                for project_id, doc_ids in projects_deletes.items():
                    index_name = f"project_{project_id}"
                    await ms.delete_documents_batch(index_name, doc_ids)
                
                results['by_operation']['delete'] = len(delete_ids)
                await self._update_stats("processed", "delete", len(delete_ids))
                
            except Exception as e:
                logger.error(f"Failed to process delete operations: {str(e)}")
                results['errors'] += len(delete_ids)
    
    async def _process_index_operations(self, ms, operations: List[Tuple[str, SyncRequest]], results: Dict[str, Any]):
        """Process index/update operations"""
        # Group by project
        projects_documents = {}
        successful_keys = []
        
        for queue_key, sync_request in operations:
            try:
                project_id = sync_request.project_id
                if project_id not in projects_documents:
                    projects_documents[project_id] = []
                
                # Document data is in the sync_request.data
                document = sync_request.data
                projects_documents[project_id].append(document)
                successful_keys.append(queue_key)
                
            except Exception as e:
                logger.warning(f"Failed to prepare document for page {sync_request.page_id}: {str(e)}")
                results['errors'] += 1
        
        # Index documents by project
        for project_id, documents in projects_documents.items():
            try:
                index_name = f"project_{project_id}"
                await ms.add_documents_batch(index_name, documents)
                
                results['by_operation']['index'] = results['by_operation'].get('index', 0) + len(documents)
                await self._update_stats("processed", "index", len(documents))
                
            except Exception as e:
                logger.error(f"Failed to index documents for project {project_id}: {str(e)}")
                results['errors'] += len(documents)
    
    async def clear_processed_operations(self, operations: List[Tuple[str, SyncRequest]]):
        """Remove processed operations from queue"""
        if not self.redis_client:
            return
        
        try:
            # Remove from priority queue
            queue_keys = [queue_key for queue_key, _ in operations]
            if queue_keys:
                await self.redis_client.zrem(self.sync_queue_key, *queue_keys)
                
                # Remove data
                await self.redis_client.hdel(f"{self.sync_queue_key}:data", *queue_keys)
                
            # Release batch lock
            await self.redis_client.delete(self.batch_lock_key)
            
        except Exception as e:
            logger.error(f"Failed to clear processed operations: {str(e)}")
    
    async def _update_stats(self, stat_type: str, operation_type: str, count: int = 1):
        """Update synchronization statistics"""
        if not self.redis_client:
            return
        
        try:
            timestamp = datetime.utcnow().isoformat()
            stats_key = f"{self.stats_key}:{datetime.utcnow().strftime('%Y-%m-%d')}"
            
            # Increment counters
            await self.redis_client.hincrby(stats_key, f"{stat_type}_{operation_type}", count)
            await self.redis_client.hset(stats_key, "last_update", timestamp)
            
            # Set expiry (30 days)
            await self.redis_client.expire(stats_key, 30 * 24 * 3600)
            
        except Exception as e:
            logger.warning(f"Failed to update sync stats: {str(e)}")
    
    async def get_queue_stats(self) -> Dict[str, Any]:
        """Get current queue statistics"""
        if not self.redis_client:
            return {"queue_size": 0, "available": False}
        
        try:
            queue_size = await self.redis_client.zcard(self.sync_queue_key)
            is_processing = await self.redis_client.exists(self.batch_lock_key)
            
            # Get today's stats
            today_stats_key = f"{self.stats_key}:{datetime.utcnow().strftime('%Y-%m-%d')}"
            today_stats = await self.redis_client.hgetall(today_stats_key)
            
            return {
                "queue_size": queue_size,
                "is_processing": bool(is_processing),
                "today_stats": today_stats,
                "available": True
            }
            
        except Exception as e:
            logger.error(f"Failed to get queue stats: {str(e)}")
            return {"queue_size": 0, "error": str(e), "available": False}


# Global instance
batch_sync_manager = BatchSyncManager()