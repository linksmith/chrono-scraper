"""
WebSocket connection management and broadcasting system with best practices
"""
import json
import logging
import asyncio
from typing import Dict, List, Set, Any, Optional
from fastapi import WebSocket, WebSocketDisconnect
from datetime import datetime, timedelta
from enum import Enum
from dataclasses import dataclass
import redis.asyncio as redis

logger = logging.getLogger(__name__)


class ConnectionState(str, Enum):
    CONNECTING = "connecting"
    CONNECTED = "connected"
    DISCONNECTING = "disconnecting"
    DISCONNECTED = "disconnected"


class MessageType(str, Enum):
    HEARTBEAT = "heartbeat"
    TASK_PROGRESS = "task_progress"
    PROJECT_UPDATE = "project_update" 
    USER_MESSAGE = "user_message"
    ERROR = "error"
    RECONNECT = "reconnect"
    BATCH = "batch"


@dataclass
class ConnectionMetadata:
    user_id: int
    project_id: Optional[int]
    connection_type: str
    connected_at: datetime
    last_heartbeat: datetime


class ConnectionManager:
    """Enhanced WebSocket connection manager with Redis support and best practices"""
    
    def __init__(self, redis_url: str = "redis://localhost:6379"):
        # Connection storage
        self.user_connections: Dict[int, List[WebSocket]] = {}
        self.project_connections: Dict[int, List[WebSocket]] = {}
        self.dashboard_connections: List[WebSocket] = []
        self.connection_metadata: Dict[WebSocket, ConnectionMetadata] = {}
        
        # Configuration
        self.max_connections_per_user = 5  # Prevent connection spam
        self.heartbeat_interval = 30  # seconds
        self.message_queue_size = 1000
        self.cleanup_interval = 60  # seconds
        
        # Redis for horizontal scaling and persistence
        self._redis_client: Optional[redis.Redis] = None
        self.redis_url = redis_url
        
        # Message queuing for batching
        self.message_queue: asyncio.Queue = asyncio.Queue(maxsize=self.message_queue_size)
        self._queue_processor_task: Optional[asyncio.Task] = None
        self._heartbeat_task: Optional[asyncio.Task] = None
        self._cleanup_task: Optional[asyncio.Task] = None
        
        # Start background tasks lazily when an event loop is available
        try:
            asyncio.get_running_loop()
            self._start_background_tasks()
        except RuntimeError:
            # No running loop (e.g., during import in test collection). Defer startup.
            pass
    
    async def _get_redis_client(self) -> Optional[redis.Redis]:
        """Get or create Redis client"""
        if not self._redis_client:
            try:
                self._redis_client = redis.from_url(
                    self.redis_url,
                    decode_responses=True,
                    max_connections=20
                )
                await self._redis_client.ping()
                logger.info("Redis client connected successfully")
            except Exception as e:
                logger.warning(f"Failed to connect to Redis: {e}")
                self._redis_client = None
        return self._redis_client
    
    def _start_background_tasks(self):
        """Start background maintenance tasks"""
        self._queue_processor_task = asyncio.create_task(self._process_message_queue())
        self._heartbeat_task = asyncio.create_task(self._heartbeat_monitor())
        self._cleanup_task = asyncio.create_task(self._cleanup_stale_connections())
    
    async def _process_message_queue(self):
        """Process queued messages in batches for better performance"""
        while True:
            try:
                messages = []
                # Collect messages for batch processing
                try:
                    # Wait for first message
                    message = await asyncio.wait_for(self.message_queue.get(), timeout=1.0)
                    messages.append(message)
                    
                    # Collect additional messages (non-blocking)
                    while len(messages) < 50:  # Max batch size
                        try:
                            message = self.message_queue.get_nowait()
                            messages.append(message)
                        except asyncio.QueueEmpty:
                            break
                            
                except asyncio.TimeoutError:
                    continue  # No messages to process
                
                if messages:
                    await self._process_message_batch(messages)
                    
            except Exception as e:
                logger.error(f"Error in message queue processor: {e}")
                await asyncio.sleep(1)
    
    async def _process_message_batch(self, messages: List[Dict[str, Any]]):
        """Process a batch of messages efficiently"""
        # Group messages by target for efficient delivery
        user_messages: Dict[int, List[Dict]] = {}
        project_messages: Dict[int, List[Dict]] = {}
        
        for message in messages:
            target_type = message.get("target_type")
            target_id = message.get("target_id")
            
            if target_type == "user" and target_id:
                if target_id not in user_messages:
                    user_messages[target_id] = []
                user_messages[target_id].append(message["payload"])
            elif target_type == "project" and target_id:
                if target_id not in project_messages:
                    project_messages[target_id] = []
                project_messages[target_id].append(message["payload"])
        
        # Send batched messages
        tasks = []
        for user_id, user_msgs in user_messages.items():
            if len(user_msgs) == 1:
                task = self._send_to_user_direct(user_id, user_msgs[0])
            else:
                batch_message = {
                    "type": MessageType.BATCH,
                    "messages": user_msgs,
                    "timestamp": datetime.now().isoformat()
                }
                task = self._send_to_user_direct(user_id, batch_message)
            tasks.append(task)
        
        for project_id, project_msgs in project_messages.items():
            if len(project_msgs) == 1:
                task = self._send_to_project_direct(project_id, project_msgs[0])
            else:
                batch_message = {
                    "type": MessageType.BATCH,
                    "messages": project_msgs,
                    "timestamp": datetime.now().isoformat()
                }
                task = self._send_to_project_direct(project_id, batch_message)
            tasks.append(task)
        
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
    
    async def _heartbeat_monitor(self):
        """Monitor connection health and send heartbeats"""
        while True:
            try:
                now = datetime.now()
                stale_connections = []
                
                for websocket, metadata in self.connection_metadata.items():
                    # Check if connection needs heartbeat
                    if (now - metadata.last_heartbeat).seconds > self.heartbeat_interval:
                        try:
                            await websocket.send_text(json.dumps({
                                "type": MessageType.HEARTBEAT,
                                "timestamp": now.isoformat()
                            }))
                            metadata.last_heartbeat = now
                        except Exception:
                            stale_connections.append(websocket)
                
                # Clean up stale connections
                for ws in stale_connections:
                    await self._force_disconnect(ws)
                
                await asyncio.sleep(self.heartbeat_interval)
                
            except Exception as e:
                logger.error(f"Error in heartbeat monitor: {e}")
                await asyncio.sleep(5)
    
    async def _cleanup_stale_connections(self):
        """Periodic cleanup of stale connections and metadata"""
        while True:
            try:
                await asyncio.sleep(self.cleanup_interval)
                
                now = datetime.now()
                stale_connections = []
                
                for websocket, metadata in self.connection_metadata.items():
                    # Mark connections stale after 5 minutes without heartbeat
                    if (now - metadata.last_heartbeat).seconds > 300:
                        stale_connections.append(websocket)
                
                for ws in stale_connections:
                    await self._force_disconnect(ws)
                    
                logger.debug(f"Cleaned up {len(stale_connections)} stale connections")
                
            except Exception as e:
                logger.error(f"Error in cleanup task: {e}")
                await asyncio.sleep(30)
    
    async def connect_user(self, websocket: WebSocket, user_id: int):
        """Connect a user to their personal channel"""
        await websocket.accept()
        
        if user_id not in self.user_connections:
            self.user_connections[user_id] = []
        
        self.user_connections[user_id].append(websocket)
        self.connection_metadata[websocket] = {"user_id": user_id, "type": "user"}
        
        logger.info(f"User {user_id} connected to WebSocket")
    
    async def connect_project(self, websocket: WebSocket, user_id: int, project_id: int):
        """Connect a user to a specific project channel"""
        await websocket.accept()
        
        if project_id not in self.project_connections:
            self.project_connections[project_id] = []
        
        self.project_connections[project_id].append(websocket)
        self.connection_metadata[websocket] = {
            "user_id": user_id, 
            "project_id": project_id,
            "type": "project"
        }
        
        logger.info(f"User {user_id} connected to project {project_id} WebSocket")
    
    async def connect_dashboard(self, websocket: WebSocket, user_id: int):
        """Connect a user to the dashboard channel"""
        await websocket.accept()
        
        self.dashboard_connections.append(websocket)
        self.connection_metadata[websocket] = {"user_id": user_id, "type": "dashboard"}
        
        logger.info(f"User {user_id} connected to dashboard WebSocket")
    
    def disconnect(self, websocket: WebSocket):
        """Disconnect a WebSocket and clean up"""
        metadata = self.connection_metadata.get(websocket)
        if not metadata:
            return
        
        connection_type = metadata.get("type")
        user_id = metadata.get("user_id")
        
        if connection_type == "user" and user_id:
            if user_id in self.user_connections:
                self.user_connections[user_id] = [
                    ws for ws in self.user_connections[user_id] if ws != websocket
                ]
                if not self.user_connections[user_id]:
                    del self.user_connections[user_id]
        
        elif connection_type == "project":
            project_id = metadata.get("project_id")
            if project_id and project_id in self.project_connections:
                self.project_connections[project_id] = [
                    ws for ws in self.project_connections[project_id] if ws != websocket
                ]
                if not self.project_connections[project_id]:
                    del self.project_connections[project_id]
        
        elif connection_type == "dashboard":
            self.dashboard_connections = [
                ws for ws in self.dashboard_connections if ws != websocket
            ]
        
        if websocket in self.connection_metadata:
            del self.connection_metadata[websocket]
        
        logger.info(f"WebSocket disconnected for user {user_id}")
    
    async def send_to_user(self, user_id: int, message: Dict[str, Any]):
        """Send message to all connections for a specific user"""
        if user_id not in self.user_connections:
            return
        
        message_str = json.dumps({
            **message,
            "timestamp": datetime.now().isoformat()
        })
        
        disconnected = []
        for websocket in self.user_connections[user_id]:
            try:
                await websocket.send_text(message_str)
            except Exception as e:
                logger.error(f"Error sending to user {user_id}: {e}")
                disconnected.append(websocket)
        
        # Clean up disconnected websockets
        for ws in disconnected:
            self.disconnect(ws)
    
    async def send_to_project(self, project_id: int, message: Dict[str, Any]):
        """Send message to all connections for a specific project"""
        if project_id not in self.project_connections:
            return
        
        message_str = json.dumps({
            **message,
            "timestamp": datetime.now().isoformat()
        })
        
        disconnected = []
        for websocket in self.project_connections[project_id]:
            try:
                await websocket.send_text(message_str)
            except Exception as e:
                logger.error(f"Error sending to project {project_id}: {e}")
                disconnected.append(websocket)
        
        # Clean up disconnected websockets
        for ws in disconnected:
            self.disconnect(ws)
    
    async def send_to_dashboard(self, message: Dict[str, Any]):
        """Send message to all dashboard connections"""
        message_str = json.dumps({
            **message,
            "timestamp": datetime.now().isoformat()
        })
        
        disconnected = []
        for websocket in self.dashboard_connections:
            try:
                await websocket.send_text(message_str)
            except Exception as e:
                logger.error(f"Error sending to dashboard: {e}")
                disconnected.append(websocket)
        
        # Clean up disconnected websockets
        for ws in disconnected:
            self.disconnect(ws)
    
    async def broadcast_to_user_projects(self, user_id: int, message: Dict[str, Any]):
        """Broadcast message to all project connections for a user"""
        message_str = json.dumps({
            **message,
            "timestamp": datetime.now().isoformat()
        })
        
        disconnected = []
        for websocket, metadata in self.connection_metadata.items():
            if (metadata.get("user_id") == user_id and 
                metadata.get("type") == "project"):
                try:
                    await websocket.send_text(message_str)
                except Exception as e:
                    logger.error(f"Error broadcasting to user {user_id}: {e}")
                    disconnected.append(websocket)
        
        # Clean up disconnected websockets
        for ws in disconnected:
            self.disconnect(ws)
    
    def get_connection_stats(self) -> Dict[str, Any]:
        """Get connection statistics for monitoring"""
        return {
            "total_connections": len(self.connection_metadata),
            "user_connections": len(self.user_connections),
            "project_connections": len(self.project_connections),
            "dashboard_connections": len(self.dashboard_connections),
            "connections_by_user": {
                user_id: len(connections) 
                for user_id, connections in self.user_connections.items()
            },
            "connections_by_project": {
                project_id: len(connections)
                for project_id, connections in self.project_connections.items()
            }
        }


# Global connection manager instance
connection_manager = ConnectionManager()