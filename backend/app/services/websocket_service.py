"""
WebSocket service for real-time scraping progress updates

Browser connections live in the API process, but scrape events originate in
Celery worker processes — an in-memory manager there has no clients. Events
therefore travel over Redis pub/sub (channel `scrape_events:{session_id}`):
the worker-side `broadcast_*_sync` helpers publish, and the manager in the API
process runs a relay loop that subscribes and forwards to its connections.
"""
import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, Optional, Set
from dataclasses import dataclass

from fastapi import WebSocket, WebSocketDisconnect

from ..core.config import settings
from ..core.database import SyncSessionLocal
from ..models import ScrapeSession, Domain, ScrapePage
from ..models.scraping import ScrapeProgressUpdate, PageProgressEvent, CDXDiscoveryEvent, ProcessingStageEvent, SessionStatsEvent

logger = logging.getLogger(__name__)

# Redis pub/sub channel prefix for scrape events (worker -> API process).
SCRAPE_EVENTS_CHANNEL = "scrape_events:{}"


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
        # Relay task that forwards worker-published Redis events to connections
        self._relay_task: Optional[asyncio.Task] = None
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
    
    async def broadcast_to_project(self, project_id: int, message: Dict[str, Any]):
        """
        Broadcast message to all connections for sessions belonging to a project
        
        Args:
            project_id: Project ID to broadcast to
            message: Message to send
        """
        # Import here to avoid circular imports
        from sqlmodel import select
        from app.core.database import SyncSessionLocal
        from app.models.project import Domain, ScrapeSession
        
        # Get all scrape sessions for this project
        with SyncSessionLocal() as db:
            # Get all domains for this project
            domain_stmt = select(Domain.id).where(Domain.project_id == project_id)
            domain_result = db.execute(domain_stmt)
            domain_ids = [row[0] for row in domain_result.fetchall()]
            
            if not domain_ids:
                return
            
            # Get all scrape sessions for these domains
            session_stmt = select(ScrapeSession.id).where(ScrapeSession.domain_id.in_(domain_ids))
            session_result = db.execute(session_stmt)
            session_ids = [row[0] for row in session_result.fetchall()]
        
        # Broadcast to all sessions
        for session_id in session_ids:
            await self.broadcast_to_session(session_id, message)
    
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
                from sqlalchemy import func

                # Get scrape session
                session = db.query(ScrapeSession).filter(ScrapeSession.id == scrape_session_id).first()
                if not session:
                    return {"error": "Session not found"}

                # Count ScrapePage statuses for this session. The worker commits
                # these throughout the run; Domain counters are only written when
                # a scrape finishes, so they would read stale/zero here.
                def _status_key(value) -> str:
                    return value.value if hasattr(value, "value") else str(value)

                rows = (
                    db.query(ScrapePage.domain_id, ScrapePage.status, func.count(ScrapePage.id))
                    .filter(ScrapePage.scrape_session_id == scrape_session_id)
                    .group_by(ScrapePage.domain_id, ScrapePage.status)
                    .all()
                )
                totals: Dict[str, int] = {}
                by_domain: Dict[int, Dict[str, int]] = {}
                for domain_id, status, count in rows:
                    key = _status_key(status)
                    totals[key] = totals.get(key, 0) + count
                    dom_counts = by_domain.setdefault(domain_id, {})
                    dom_counts[key] = dom_counts.get(key, 0) + count

                scraped_pages = totals.get("completed", 0)
                failed_pages = totals.get("failed", 0)
                skipped_pages = totals.get("skipped", 0)
                in_progress_pages = totals.get("in_progress", 0)
                pending_pages = totals.get("pending", 0) + totals.get("retry", 0)
                # filtered_* / manually_* statuses were never scheduled for
                # scraping, so they don't count toward progress.
                processable = (
                    scraped_pages + failed_pages + skipped_pages
                    + in_progress_pages + pending_pages
                )

                progress_percentage = 0.0
                if processable > 0:
                    progress_percentage = (
                        (scraped_pages + failed_pages + skipped_pages) / processable
                    ) * 100

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

                # Pages per minute. started_at comes back timezone-aware from a
                # timestamptz column while utcnow() is naive — mixing the two
                # raised on subtraction and turned every frame into an error.
                now = datetime.now(timezone.utc)
                started = session.started_at
                if started is not None and started.tzinfo is None:
                    started = started.replace(tzinfo=timezone.utc)
                pages_per_minute = 0.0
                if started is not None:
                    elapsed_minutes = (now - started).total_seconds() / 60
                    if elapsed_minutes > 0:
                        pages_per_minute = scraped_pages / elapsed_minutes

                # Estimate completion time
                estimated_completion = None
                if pages_per_minute > 0 and pending_pages > 0:
                    minutes_remaining = pending_pages / pages_per_minute
                    estimated_completion = now + timedelta(minutes=minutes_remaining)

                domains = db.query(Domain).filter(Domain.project_id == session.project_id).all()
                domain_stats = []
                for d in domains:
                    counts = by_domain.get(d.id, {})
                    domain_stats.append({
                        "id": d.id,
                        "domain_name": d.domain_name,
                        "status": d.status.value if hasattr(d.status, "value") else str(d.status),
                        "scraped_pages": counts.get("completed", 0),
                        "failed_pages": counts.get("failed", 0),
                        "total_pages": sum(counts.values()),
                    })

                return {
                    "scrape_session_id": scrape_session_id,
                    "status": session.status.value,
                    "total_urls": processable,
                    "completed_urls": scraped_pages,
                    "failed_urls": failed_pages,
                    "pending_urls": pending_pages,
                    "progress_percentage": round(progress_percentage, 2),
                    "pages_per_minute": round(pages_per_minute, 2),
                    "estimated_completion": estimated_completion.isoformat() if estimated_completion else None,
                    "error_summary": error_summary,
                    "started_at": session.started_at.isoformat() if session.started_at else None,
                    "domains": domain_stats
                }
        
        try:
            progress_data = await loop.run_in_executor(None, get_progress)
            return progress_data
        except Exception as e:
            logger.error(f"Failed to get progress for session {scrape_session_id}: {str(e)}")
            return {"error": str(e)}
    
    async def _start_background_updates(self):
        """Start background tasks: periodic progress updates + Redis event relay"""
        if self._running:
            return

        self._running = True
        self._update_task = asyncio.create_task(self._background_update_loop())
        self._relay_task = asyncio.create_task(self._redis_relay_loop())
        logger.info("Started WebSocket background update and event relay tasks")

    async def _stop_background_updates(self):
        """Stop background update and relay tasks"""
        if not self._running:
            return

        self._running = False

        for task_attr in ("_update_task", "_relay_task"):
            task = getattr(self, task_attr)
            if task:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
                setattr(self, task_attr, None)

        logger.info("Stopped WebSocket background tasks")
    
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

    async def _redis_relay_loop(self):
        """
        Subscribe to worker-published scrape events and forward them to the
        WebSocket connections in this process. Celery workers cannot reach this
        manager directly (separate processes), so Redis pub/sub is the bridge.
        Reconnects with a short delay if Redis drops.
        """
        import redis.asyncio as aioredis

        while self._running:
            client = None
            pubsub = None
            try:
                client = aioredis.from_url(
                    settings.REDIS_URL,
                    decode_responses=True,
                    socket_connect_timeout=5,
                )
                pubsub = client.pubsub()
                await pubsub.psubscribe(SCRAPE_EVENTS_CHANNEL.format("*"))
                logger.info("Scrape event relay subscribed to Redis")

                async for message in pubsub.listen():
                    if not self._running:
                        break
                    if message.get("type") != "pmessage":
                        continue
                    channel = str(message.get("channel", ""))
                    try:
                        session_id = int(channel.rsplit(":", 1)[-1])
                    except ValueError:
                        continue
                    try:
                        payload = json.loads(message.get("data") or "{}")
                    except (TypeError, json.JSONDecodeError):
                        continue
                    await self.broadcast_to_session(session_id, payload)
            except asyncio.CancelledError:
                logger.info("Scrape event relay cancelled")
                break
            except Exception as e:
                logger.warning(f"Scrape event relay error, reconnecting: {e}")
                await asyncio.sleep(2)
            finally:
                try:
                    if pubsub is not None:
                        await pubsub.close()
                    if client is not None:
                        await client.aclose()
                except Exception:
                    pass


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

                    # Any client message counts as liveness — the stale-connection
                    # reaper drops connections idle for 60s, and clients that only
                    # send occasional non-ping messages shouldn't be reaped.
                    if connection_id in websocket_manager.connections:
                        websocket_manager.connections[connection_id].last_ping = datetime.utcnow()

                    if message_type == "ping":
                        # Respond to ping
                        await websocket.send_text(json.dumps({
                            "type": "pong",
                            "timestamp": datetime.utcnow().isoformat()
                        }))
                    
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


# --- Broadcasting from Celery tasks -----------------------------------------
#
# These helpers run inside worker processes, where the manager above has no
# connections. They publish the exact message envelope the manager would send,
# to the session's Redis channel; the manager's relay loop (in the API process)
# forwards it to the actual WebSocket clients.

_publish_client = None  # sync redis client, created lazily per process


def _publish_event(scrape_session_id: int, message: Dict[str, Any]) -> None:
    global _publish_client
    try:
        if _publish_client is None:
            import redis
            _publish_client = redis.Redis.from_url(
                settings.REDIS_URL,
                socket_connect_timeout=2,
                socket_timeout=2,
            )
        _publish_client.publish(
            SCRAPE_EVENTS_CHANNEL.format(scrape_session_id),
            json.dumps(message, default=str),
        )
    except Exception as e:
        # Never let progress reporting break the scrape itself.
        logger.warning(f"Failed to publish scrape event: {e}")
        _publish_client = None


def broadcast_progress_update_sync(scrape_session_id: int, progress_data: Dict[str, Any]):
    """Publish a progress update event from a Celery task."""
    try:
        progress_update = ScrapeProgressUpdate(
            scrape_session_id=scrape_session_id,
            **progress_data
        )
        _publish_event(scrape_session_id, {
            "type": "progress_update",
            "data": progress_update.model_dump(mode='json'),
            "timestamp": datetime.utcnow().isoformat()
        })
    except Exception as e:
        logger.error(f"Failed to broadcast progress update: {str(e)}")


def broadcast_page_progress_sync(page_event_data: Dict[str, Any]):
    """Publish an individual page progress event from a Celery task."""
    try:
        page_event = PageProgressEvent(**page_event_data)
        _publish_event(page_event.scrape_session_id, {
            "type": "page_progress",
            "data": page_event.model_dump(mode='json'),
            "timestamp": datetime.utcnow().isoformat()
        })
    except Exception as e:
        logger.error(f"Failed to broadcast page progress: {str(e)}")


def broadcast_cdx_discovery_sync(cdx_event_data: Dict[str, Any]):
    """Publish a CDX discovery event from a Celery task."""
    try:
        cdx_event = CDXDiscoveryEvent(**cdx_event_data)
        _publish_event(cdx_event.scrape_session_id, {
            "type": "cdx_discovery",
            "data": cdx_event.model_dump(mode='json'),
            "timestamp": datetime.utcnow().isoformat()
        })
    except Exception as e:
        logger.error(f"Failed to broadcast CDX discovery: {str(e)}")


def broadcast_processing_stage_sync(stage_event_data: Dict[str, Any]):
    """Publish a processing stage event from a Celery task."""
    try:
        stage_event = ProcessingStageEvent(**stage_event_data)
        _publish_event(stage_event.scrape_session_id, {
            "type": "processing_stage",
            "data": stage_event.model_dump(mode='json'),
            "timestamp": datetime.utcnow().isoformat()
        })
    except Exception as e:
        logger.error(f"Failed to broadcast processing stage: {str(e)}")


def broadcast_session_stats_sync(stats_event_data: Dict[str, Any]):
    """Publish a session statistics event from a Celery task."""
    try:
        stats_event = SessionStatsEvent(**stats_event_data)
        _publish_event(stats_event.scrape_session_id, {
            "type": "session_stats",
            "data": stats_event.model_dump(mode='json'),
            "timestamp": datetime.utcnow().isoformat()
        })
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