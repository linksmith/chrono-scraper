"""
Dashboard-specific WebSocket service for real-time updates
"""
import asyncio
import logging
from typing import Dict, Set, Any, Optional
from datetime import datetime
from fastapi import WebSocket, WebSocketDisconnect

from app.core.database import get_db
from app.services.dashboard_metrics import DashboardMetricsService
from app.services.monitoring import MonitoringService

logger = logging.getLogger(__name__)


class DashboardWebSocketManager:
    """WebSocket manager specifically for admin dashboard"""
    
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}
        self.connection_metadata: Dict[str, Dict[str, Any]] = {}
        self.update_interval = 30  # seconds
        self.running_tasks: Set[asyncio.Task] = set()
    
    async def connect(self, websocket: WebSocket, connection_id: str, user_id: Optional[int] = None):
        """Connect a new WebSocket client"""
        await websocket.accept()
        self.active_connections[connection_id] = websocket
        self.connection_metadata[connection_id] = {
            "user_id": user_id,
            "connected_at": datetime.utcnow(),
            "last_ping": datetime.utcnow()
        }
        
        logger.info(f"Dashboard WebSocket client connected: {connection_id}")
        
        # Start periodic updates for this connection
        task = asyncio.create_task(self._periodic_updates(connection_id))
        self.running_tasks.add(task)
        task.add_done_callback(self.running_tasks.discard)
    
    async def disconnect(self, connection_id: str):
        """Disconnect a WebSocket client"""
        if connection_id in self.active_connections:
            try:
                await self.active_connections[connection_id].close()
            except Exception as e:
                logger.warning(f"Error closing WebSocket {connection_id}: {e}")
            
            del self.active_connections[connection_id]
            del self.connection_metadata[connection_id]
            logger.info(f"Dashboard WebSocket client disconnected: {connection_id}")
    
    async def send_to_connection(self, connection_id: str, data: Dict[str, Any]):
        """Send data to a specific connection"""
        if connection_id not in self.active_connections:
            return False
        
        try:
            websocket = self.active_connections[connection_id]
            await websocket.send_json(data)
            
            # Update last ping time
            if connection_id in self.connection_metadata:
                self.connection_metadata[connection_id]["last_ping"] = datetime.utcnow()
            
            return True
        except WebSocketDisconnect:
            await self.disconnect(connection_id)
            return False
        except Exception as e:
            logger.error(f"Error sending to WebSocket {connection_id}: {e}")
            await self.disconnect(connection_id)
            return False
    
    async def broadcast(self, data: Dict[str, Any], exclude_connections: Set[str] = None):
        """Broadcast data to all connected clients"""
        if exclude_connections is None:
            exclude_connections = set()
        
        disconnected_connections = []
        
        for connection_id in self.active_connections:
            if connection_id not in exclude_connections:
                success = await self.send_to_connection(connection_id, data)
                if not success:
                    disconnected_connections.append(connection_id)
        
        # Clean up disconnected connections
        for connection_id in disconnected_connections:
            if connection_id in self.active_connections:
                await self.disconnect(connection_id)
    
    async def send_dashboard_update(self, connection_id: str = None):
        """Send dashboard data update to specific connection or all connections"""
        try:
            async for db in get_db():
                # Get real-time metrics
                real_time_data = await DashboardMetricsService.get_real_time_metrics(db)
                
                # Get system health
                system_health = await MonitoringService.get_comprehensive_system_health()
                
                update_data = {
                    "type": "dashboard_update",
                    "timestamp": datetime.utcnow().isoformat(),
                    "data": {
                        "real_time_metrics": real_time_data,
                        "system_health": system_health
                    }
                }
                
                if connection_id:
                    await self.send_to_connection(connection_id, update_data)
                else:
                    await self.broadcast(update_data)
                
                break
                
        except Exception as e:
            logger.error(f"Error sending dashboard update: {e}")
            error_data = {
                "type": "error",
                "timestamp": datetime.utcnow().isoformat(),
                "message": "Failed to get dashboard update",
                "error": str(e)
            }
            
            if connection_id:
                await self.send_to_connection(connection_id, error_data)
            else:
                await self.broadcast(error_data)
    
    async def send_alert(self, alert_data: Dict[str, Any]):
        """Send alert to all connected dashboard clients"""
        alert_message = {
            "type": "alert",
            "timestamp": datetime.utcnow().isoformat(),
            "data": alert_data
        }
        
        await self.broadcast(alert_message)
    
    async def send_metric_update(self, metric_name: str, value: Any, metadata: Dict[str, Any] = None):
        """Send specific metric update"""
        metric_update = {
            "type": "metric_update",
            "timestamp": datetime.utcnow().isoformat(),
            "metric": metric_name,
            "value": value,
            "metadata": metadata or {}
        }
        
        await self.broadcast(metric_update)
    
    async def _periodic_updates(self, connection_id: str):
        """Send periodic updates to a specific connection"""
        try:
            while connection_id in self.active_connections:
                await self.send_dashboard_update(connection_id)
                await asyncio.sleep(self.update_interval)
                
        except asyncio.CancelledError:
            logger.info(f"Periodic updates cancelled for connection {connection_id}")
        except Exception as e:
            logger.error(f"Error in periodic updates for {connection_id}: {e}")
        finally:
            if connection_id in self.active_connections:
                await self.disconnect(connection_id)
    
    async def handle_client_message(self, connection_id: str, message: Dict[str, Any]):
        """Handle incoming message from WebSocket client"""
        try:
            message_type = message.get("type")
            
            if message_type == "ping":
                # Respond to ping with pong
                await self.send_to_connection(connection_id, {
                    "type": "pong",
                    "timestamp": datetime.utcnow().isoformat()
                })
            
            elif message_type == "subscribe":
                # Handle subscription to specific metrics
                metrics = message.get("metrics", [])
                logger.info(f"Connection {connection_id} subscribing to metrics: {metrics}")
                
                # Store subscription preferences
                if connection_id in self.connection_metadata:
                    self.connection_metadata[connection_id]["subscriptions"] = metrics
            
            elif message_type == "request_update":
                # Handle manual update request
                await self.send_dashboard_update(connection_id)
            
            elif message_type == "change_interval":
                # Handle update interval change
                interval = message.get("interval", 30)
                if 5 <= interval <= 300:  # Limit between 5 seconds and 5 minutes
                    if connection_id in self.connection_metadata:
                        self.connection_metadata[connection_id]["update_interval"] = interval
            
            else:
                logger.warning(f"Unknown message type from {connection_id}: {message_type}")
                
        except Exception as e:
            logger.error(f"Error handling client message from {connection_id}: {e}")
            await self.send_to_connection(connection_id, {
                "type": "error",
                "message": "Failed to process message",
                "error": str(e)
            })
    
    def get_connection_stats(self) -> Dict[str, Any]:
        """Get statistics about active connections"""
        now = datetime.utcnow()
        stats = {
            "total_connections": len(self.active_connections),
            "connections": []
        }
        
        for conn_id, metadata in self.connection_metadata.items():
            connected_duration = (now - metadata["connected_at"]).total_seconds()
            last_ping_duration = (now - metadata["last_ping"]).total_seconds()
            
            stats["connections"].append({
                "connection_id": conn_id,
                "user_id": metadata.get("user_id"),
                "connected_duration_seconds": connected_duration,
                "last_ping_seconds_ago": last_ping_duration,
                "subscriptions": metadata.get("subscriptions", [])
            })
        
        return stats
    
    async def cleanup_stale_connections(self):
        """Remove stale connections (no ping for more than 5 minutes)"""
        now = datetime.utcnow()
        stale_connections = []
        
        for conn_id, metadata in self.connection_metadata.items():
            last_ping = metadata["last_ping"]
            if (now - last_ping).total_seconds() > 300:  # 5 minutes
                stale_connections.append(conn_id)
        
        for conn_id in stale_connections:
            logger.info(f"Cleaning up stale connection: {conn_id}")
            await self.disconnect(conn_id)
    
    async def shutdown(self):
        """Shutdown the WebSocket manager"""
        logger.info("Shutting down dashboard WebSocket manager")
        
        # Cancel all running tasks
        for task in self.running_tasks:
            task.cancel()
        
        # Disconnect all connections
        connection_ids = list(self.active_connections.keys())
        for connection_id in connection_ids:
            await self.disconnect(connection_id)


# Global dashboard WebSocket manager instance
dashboard_websocket_manager = DashboardWebSocketManager()


async def get_dashboard_websocket_manager():
    """Dependency to get the dashboard WebSocket manager"""
    return dashboard_websocket_manager