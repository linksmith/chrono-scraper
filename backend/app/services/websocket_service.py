"""
WebSocket service for real-time scraping progress updates
"""
import asyncio
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Set
from dataclasses import dataclass, asdict

from fastapi import WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session

from ..core.database import get_db, SyncSessionLocal
from ..models import ScrapeSession, Domain, ScrapePage, ScrapeMonitoringLog
from ..models.scraping import ScrapeProgressUpdate, PageProgressEvent, CDXDiscoveryEvent, ProcessingStageEvent, SessionStatsEvent

logger = logging.getLogger(__name__)


@dataclass
class WebSocketConnection:
    """WebSocket connection info"""
    websocket: WebSocket
    user_id: int
    scrape_session_id: int
    connected_at: datetime
    last_ping: datetime


class WebSocketManager:
    """Manager for WebSocket connections and progress broadcasting"""
    
    def __init__(self):
        # Store active connections: {connection_id: WebSocketConnection}
        self.connections: Dict[str, WebSocketConnection] = {}
        
        # Map sessions to connections for efficient broadcasting
        self.session_connections: Dict[int, Set[str]] = {}
        
        # Background task for periodic updates
        self._update_task: Optional[asyncio.Task] = None
        self._running = False
        
        logger.info("Initialized WebSocket manager")
    
    async def connect(self, websocket: WebSocket, user_id: int, scrape_session_id: int) -> str:
        """
        Add a new WebSocket connection
        
        Args:
            websocket: WebSocket instance
            user_id: User ID for authorization
            scrape_session_id: Scrape session to monitor
            
        Returns:
            Connection ID
        """
        await websocket.accept()
        
        # Generate connection ID
        connection_id = f"{user_id}_{scrape_session_id}_{datetime.utcnow().timestamp()}"
        
        # Create connection object
        connection = WebSocketConnection(
            websocket=websocket,
            user_id=user_id,
            scrape_session_id=scrape_session_id,
            connected_at=datetime.utcnow(),
            last_ping=datetime.utcnow()
        )
        
        # Store connection
        self.connections[connection_id] = connection
        
        # Map to session
        if scrape_session_id not in self.session_connections:
            self.session_connections[scrape_session_id] = set()
        self.session_connections[scrape_session_id].add(connection_id)
        
        logger.info(f"WebSocket connected: {connection_id} for session {scrape_session_id}")
        
        # Send initial progress update
        await self._send_initial_progress(connection_id)
        
        # Start background update task if not running
        if not self._running:
            await self._start_background_updates()
        
        return connection_id
    
    async def disconnect(self, connection_id: str):
        """
        Remove a WebSocket connection
        
        Args:
            connection_id: Connection ID to remove
        """
        if connection_id not in self.connections:
            return
        
        connection = self.connections[connection_id]
        scrape_session_id = connection.scrape_session_id
        
        # Remove from connections
        del self.connections[connection_id]
        
        # Remove from session mapping
        if scrape_session_id in self.session_connections:
            self.session_connections[scrape_session_id].discard(connection_id)
            
            # Clean up empty session mappings
            if not self.session_connections[scrape_session_id]:
                del self.session_connections[scrape_session_id]
        
        logger.info(f"WebSocket disconnected: {connection_id}")
        
        # Stop background updates if no connections
        if not self.connections:
            await self._stop_background_updates()
    
    async def broadcast_to_session(self, scrape_session_id: int, message: Dict[str, Any]):
        """
        Broadcast message to all connections for a scrape session
        
        Args:
            scrape_session_id: Session ID to broadcast to
            message: Message to send
        """
        if scrape_session_id not in self.session_connections:
            return
        
        connection_ids = list(self.session_connections[scrape_session_id])
        
        # Send to all connections for this session
        for connection_id in connection_ids:
            await self._send_to_connection(connection_id, message)
    
    async def broadcast_progress_update(self, progress_update: ScrapeProgressUpdate):
        """
        Broadcast progress update to relevant connections
        
        Args:
            progress_update: Progress update to broadcast
        """
        # Use JSON-friendly dump to avoid serialization issues with enums/datetimes
        message = {
            "type": "progress_update",
            "data": progress_update.model_dump(mode='json'),
            "timestamp": datetime.utcnow().isoformat()
        }
        
        await self.broadcast_to_session(progress_update.scrape_session_id, message)
    
    async def broadcast_page_progress(self, page_event: PageProgressEvent):
        """
        Broadcast individual page progress event
        
        Args:
            page_event: Page progress event to broadcast
        """
        message = {
            "type": "page_progress",
            "data": page_event.model_dump(mode='json'),
            "timestamp": datetime.utcnow().isoformat()
        }
        
        await self.broadcast_to_session(page_event.scrape_session_id, message)
    
    async def broadcast_cdx_discovery(self, cdx_event: CDXDiscoveryEvent):
        """
        Broadcast CDX discovery progress event
        
        Args:
            cdx_event: CDX discovery event to broadcast
        """
        message = {
            "type": "cdx_discovery",
            "data": cdx_event.model_dump(mode='json'),
            "timestamp": datetime.utcnow().isoformat()
        }
        
        await self.broadcast_to_session(cdx_event.scrape_session_id, message)
    
    async def broadcast_processing_stage(self, stage_event: ProcessingStageEvent):
        """
        Broadcast processing stage event
        
        Args:
            stage_event: Processing stage event to broadcast
        """
        message = {
            "type": "processing_stage",
            "data": stage_event.model_dump(mode='json'),
            "timestamp": datetime.utcnow().isoformat()
        }
        
        await self.broadcast_to_session(stage_event.scrape_session_id, message)
    
    async def broadcast_session_stats(self, stats_event: SessionStatsEvent):
        """
        Broadcast session statistics event
        
        Args:
            stats_event: Session statistics event to broadcast
        """
        message = {
            "type": "session_stats",
            "data": stats_event.model_dump(mode='json'),
            "timestamp": datetime.utcnow().isoformat()
        }
        
        await self.broadcast_to_session(stats_event.scrape_session_id, message)
    
    async def _send_to_connection(self, connection_id: str, message: Dict[str, Any]):
        """
        Send message to a specific connection
        
        Args:
            connection_id: Connection to send to
            message: Message to send
        """
        if connection_id not in self.connections:
            return
        
        connection = self.connections[connection_id]
        
        try:
            await connection.websocket.send_text(json.dumps(message))
            connection.last_ping = datetime.utcnow()
            
        except Exception as e:
            logger.error(f"Failed to send message to {connection_id}: {str(e)}")
            # Remove failed connection
            await self.disconnect(connection_id)
    
    async def _send_initial_progress(self, connection_id: str):
        """
        Send initial progress data to a new connection
        
        Args:
            connection_id: Connection to send to
        """
        if connection_id not in self.connections:
            return
        
        connection = self.connections[connection_id]
        
        # Get current progress from database
        progress_data = await self._get_session_progress(connection.scrape_session_id)
        
        message = {
            "type": "initial_progress",
            "data": progress_data,
            "timestamp": datetime.utcnow().isoformat()
        }
        
        await self._send_to_connection(connection_id, message)
    
    async def _get_session_progress(self, scrape_session_id: int) -> Dict[str, Any]:
        """
        Get current progress for a scrape session
        
        Args:
            scrape_session_id: Session ID to get progress for
            
        Returns:
            Progress data dictionary
        """
        # Run database query in thread pool to avoid blocking
        loop = asyncio.get_event_loop()
        
        def get_progress():
            with SyncSessionLocal() as db:
                # Get scrape session
                session = db.query(ScrapeSession).filter(ScrapeSession.id == scrape_session_id).first()
                if not session:
                    return {"error": "Session not found"}
                
                # Get domains for this session
                domains = db.query(Domain).filter(Domain.project_id == session.project_id).all()
                
                # Aggregate statistics
                total_pages = sum(d.total_pages for d in domains)
                scraped_pages = sum(d.scraped_pages for d in domains)
                failed_pages = sum(d.failed_pages for d in domains)
                pending_pages = sum(d.pending_pages for d in domains)
                
                # Calculate progress percentage
                progress_percentage = 0.0
                if total_pages > 0:
                    progress_percentage = (scraped_pages / total_pages) * 100
                
                # Get recent error summary
                recent_errors = db.query(ScrapePage.error_type).filter(
                    ScrapePage.scrape_session_id == scrape_session_id,
                    ScrapePage.status == 'failed',
                    ScrapePage.last_attempt_at > datetime.utcnow() - timedelta(hours=1)
                ).all()
                
                error_summary = {}
                for error in recent_errors:
                    error_type = error.error_type or "unknown"
                    error_summary[error_type] = error_summary.get(error_type, 0) + 1
                
                # Calculate pages per minute
                pages_per_minute = 0.0
                if session.started_at:
                    elapsed_minutes = (datetime.utcnow() - session.started_at).total_seconds() / 60
                    if elapsed_minutes > 0:
                        pages_per_minute = scraped_pages / elapsed_minutes
                
                # Estimate completion time
                estimated_completion = None
                if pages_per_minute > 0 and pending_pages > 0:
                    minutes_remaining = pending_pages / pages_per_minute
                    estimated_completion = datetime.utcnow() + timedelta(minutes=minutes_remaining)
                
                return {
                    "scrape_session_id": scrape_session_id,
                    "status": session.status.value,
                    "total_urls": total_pages,
                    "completed_urls": scraped_pages,
                    "failed_urls": failed_pages,
                    "pending_urls": pending_pages,
                    "progress_percentage": round(progress_percentage, 2),
                    "pages_per_minute": round(pages_per_minute, 2),
                    "estimated_completion": estimated_completion.isoformat() if estimated_completion else None,
                    "error_summary": error_summary,
                    "started_at": session.started_at.isoformat() if session.started_at else None,
                    "domains": [
                        {
                            "id": d.id,
                            "domain_name": d.domain_name,
                            "status": d.status.value,
                            "scraped_pages": d.scraped_pages,
                            "failed_pages": d.failed_pages,
                            "total_pages": d.total_pages
                        }
                        for d in domains
                    ]
                }
        
        try:
            progress_data = await loop.run_in_executor(None, get_progress)
            return progress_data
        except Exception as e:
            logger.error(f"Failed to get progress for session {scrape_session_id}: {str(e)}")
            return {"error": str(e)}
    
    async def _start_background_updates(self):
        """Start background task for periodic progress updates"""
        if self._running:
            return
        
        self._running = True
        self._update_task = asyncio.create_task(self._background_update_loop())
        logger.info("Started WebSocket background update task")
    
    async def _stop_background_updates(self):
        """Stop background update task"""
        if not self._running:
            return
        
        self._running = False
        
        if self._update_task:
            self._update_task.cancel()
            try:
                await self._update_task
            except asyncio.CancelledError:
                pass
            self._update_task = None
        
        logger.info("Stopped WebSocket background update task")
    
    async def _background_update_loop(self):
        """Background loop for sending periodic updates"""
        try:
            while self._running:
                await asyncio.sleep(5)  # Update every 5 seconds
                
                if not self.connections:
                    continue
                
                # Get unique session IDs
                session_ids = set()
                for connection in self.connections.values():
                    session_ids.add(connection.scrape_session_id)
                
                # Send updates for each active session
                for session_id in session_ids:
                    try:
                        progress_data = await self._get_session_progress(session_id)
                        
                        message = {
                            "type": "progress_update",
                            "data": progress_data,
                            "timestamp": datetime.utcnow().isoformat()
                        }
                        
                        await self.broadcast_to_session(session_id, message)
                        
                    except Exception as e:
                        logger.error(f"Failed to send update for session {session_id}: {str(e)}")
                
                # Clean up stale connections (no ping in 60 seconds)
                cutoff_time = datetime.utcnow() - timedelta(seconds=60)
                stale_connections = [
                    conn_id for conn_id, conn in self.connections.items()
                    if conn.last_ping < cutoff_time
                ]
                
                for conn_id in stale_connections:
                    logger.warning(f"Removing stale connection: {conn_id}")
                    await self.disconnect(conn_id)
                
        except asyncio.CancelledError:
            logger.info("Background update loop cancelled")
        except Exception as e:
            logger.error(f"Background update loop error: {str(e)}")
            self._running = False


# Global WebSocket manager instance
websocket_manager = WebSocketManager()


async def handle_websocket_connection(websocket: WebSocket, user_id: int, scrape_session_id: int):
    """
    Handle a WebSocket connection for scrape progress monitoring
    
    Args:
        websocket: WebSocket connection
        user_id: Authenticated user ID
        scrape_session_id: Scrape session to monitor
    """
    connection_id = None
    
    try:
        # Verify user has access to this scrape session
        with SyncSessionLocal() as db:
            session = db.query(ScrapeSession).join(
                Domain, Domain.project_id == ScrapeSession.project_id
            ).filter(
                ScrapeSession.id == scrape_session_id
                # Add user authorization check here based on your auth model
                # For now, allowing all authenticated users
            ).first()
            
            if not session:
                await websocket.close(code=4004, reason="Scrape session not found or access denied")
                return
        
        # Connect to WebSocket manager
        connection_id = await websocket_manager.connect(websocket, user_id, scrape_session_id)
        
        # Keep connection alive and handle messages
        while True:
            try:
                # Wait for messages from client (ping/pong, etc.)
                message = await asyncio.wait_for(websocket.receive_text(), timeout=30)
                
                # Handle client messages
                try:
                    data = json.loads(message)
                    message_type = data.get("type")
                    
                    if message_type == "ping":
                        # Respond to ping
                        await websocket.send_text(json.dumps({
                            "type": "pong",
                            "timestamp": datetime.utcnow().isoformat()
                        }))
                        
                        # Update last ping time
                        if connection_id in websocket_manager.connections:
                            websocket_manager.connections[connection_id].last_ping = datetime.utcnow()
                    
                    elif message_type == "request_update":
                        # Client requesting immediate update
                        progress_data = await websocket_manager._get_session_progress(scrape_session_id)
                        await websocket.send_text(json.dumps({
                            "type": "progress_update",
                            "data": progress_data,
                            "timestamp": datetime.utcnow().isoformat()
                        }))
                    
                except json.JSONDecodeError:
                    logger.warning(f"Invalid JSON from client {connection_id}: {message}")
                except Exception as e:
                    logger.error(f"Error handling client message {connection_id}: {str(e)}")
                
            except asyncio.TimeoutError:
                # Send ping to keep connection alive
                await websocket.send_text(json.dumps({
                    "type": "ping",
                    "timestamp": datetime.utcnow().isoformat()
                }))
            
    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected normally: {connection_id}")
    except Exception as e:
        logger.error(f"WebSocket connection error: {str(e)}")
    finally:
        if connection_id:
            await websocket_manager.disconnect(connection_id)


# Helper functions for broadcasting from Celery tasks
def broadcast_progress_update_sync(scrape_session_id: int, progress_data: Dict[str, Any]):
    """
    Synchronous function to broadcast progress updates from Celery tasks
    
    Args:
        scrape_session_id: Session ID
        progress_data: Progress data to broadcast
    """
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        progress_update = ScrapeProgressUpdate(
            scrape_session_id=scrape_session_id,
            **progress_data
        )
        
        loop.run_until_complete(
            websocket_manager.broadcast_progress_update(progress_update)
        )
        
        loop.close()
        
    except Exception as e:
        logger.error(f"Failed to broadcast progress update: {str(e)}")


def broadcast_page_progress_sync(page_event_data: Dict[str, Any]):
    """
    Synchronous function to broadcast page progress from Celery tasks
    
    Args:
        page_event_data: Page event data to broadcast
    """
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        page_event = PageProgressEvent(**page_event_data)
        
        loop.run_until_complete(
            websocket_manager.broadcast_page_progress(page_event)
        )
        
        loop.close()
        
    except Exception as e:
        logger.error(f"Failed to broadcast page progress: {str(e)}")


def broadcast_cdx_discovery_sync(cdx_event_data: Dict[str, Any]):
    """
    Synchronous function to broadcast CDX discovery from Celery tasks
    
    Args:
        cdx_event_data: CDX discovery event data to broadcast
    """
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        cdx_event = CDXDiscoveryEvent(**cdx_event_data)
        
        loop.run_until_complete(
            websocket_manager.broadcast_cdx_discovery(cdx_event)
        )
        
        loop.close()
        
    except Exception as e:
        logger.error(f"Failed to broadcast CDX discovery: {str(e)}")


def broadcast_processing_stage_sync(stage_event_data: Dict[str, Any]):
    """
    Synchronous function to broadcast processing stage from Celery tasks
    
    Args:
        stage_event_data: Processing stage event data to broadcast
    """
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        stage_event = ProcessingStageEvent(**stage_event_data)
        
        loop.run_until_complete(
            websocket_manager.broadcast_processing_stage(stage_event)
        )
        
        loop.close()
        
    except Exception as e:
        logger.error(f"Failed to broadcast processing stage: {str(e)}")


def broadcast_session_stats_sync(stats_event_data: Dict[str, Any]):
    """
    Synchronous function to broadcast session stats from Celery tasks
    
    Args:
        stats_event_data: Session stats event data to broadcast
    """
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        stats_event = SessionStatsEvent(**stats_event_data)
        
        loop.run_until_complete(
            websocket_manager.broadcast_session_stats(stats_event)
        )
        
        loop.close()
        
    except Exception as e:
        logger.error(f"Failed to broadcast session stats: {str(e)}")


# Export public interface
__all__ = [
    'websocket_manager',
    'handle_websocket_connection', 
    'broadcast_progress_update_sync',
    'broadcast_page_progress_sync',
    'broadcast_cdx_discovery_sync',
    'broadcast_processing_stage_sync',
    'broadcast_session_stats_sync',
    'WebSocketManager',
    'ScrapeProgressUpdate',
    'PageProgressEvent',
    'CDXDiscoveryEvent',
    'ProcessingStageEvent',
    'SessionStatsEvent'
]