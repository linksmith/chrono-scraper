"""
Real-Time Analytics WebSocket Endpoints for Chrono Scraper

Provides real-time analytics updates via WebSocket connections for:
- Live scraping metrics and progress
- Real-time performance monitoring 
- System health status updates
- Dynamic dashboard data streaming
- Live alert notifications
"""

import asyncio
import json
import logging
import uuid
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set
from uuid import UUID

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, Query, HTTPException
from fastapi.websockets import WebSocketState
from pydantic import ValidationError

from ....api import deps
from ....models.user import User
from ....services.analytics_service import (
    AnalyticsService, 
    get_analytics_service,
    AnalyticsQueryContext
)
from ....schemas.analytics import (
    AnalyticsSubscription, 
    AnalyticsUpdate,
    TimeGranularity
)

logger = logging.getLogger(__name__)

router = APIRouter()


class AnalyticsWebSocketManager:
    """
    WebSocket connection manager for real-time analytics
    
    Manages WebSocket connections, subscriptions, and real-time data streaming
    for analytics updates and monitoring.
    """
    
    def __init__(self):
        # Active WebSocket connections
        self.active_connections: Dict[str, WebSocket] = {}
        
        # User-specific connections  
        self.user_connections: Dict[UUID, Set[str]] = {}
        
        # Subscription management
        self.subscriptions: Dict[str, AnalyticsSubscription] = {}
        self.subscription_connections: Dict[str, Set[str]] = {}
        
        # Background tasks
        self.background_tasks: Set[asyncio.Task] = set()
        self.running = False
        
    async def connect(self, websocket: WebSocket, user_id: UUID) -> str:
        """Accept WebSocket connection and return connection ID"""
        await websocket.accept()
        
        # Generate unique connection ID
        connection_id = str(uuid.uuid4())
        
        # Store connection
        self.active_connections[connection_id] = websocket
        
        # Track user connections
        if user_id not in self.user_connections:
            self.user_connections[user_id] = set()
        self.user_connections[user_id].add(connection_id)
        
        logger.info(f"WebSocket connected: {connection_id} for user {user_id}")
        return connection_id
    
    async def disconnect(self, connection_id: str, user_id: UUID):
        """Clean up WebSocket connection"""
        # Remove from active connections
        if connection_id in self.active_connections:
            del self.active_connections[connection_id]
        
        # Remove from user connections
        if user_id in self.user_connections:
            self.user_connections[user_id].discard(connection_id)
            if not self.user_connections[user_id]:
                del self.user_connections[user_id]
        
        # Clean up subscriptions
        for sub_id, connection_ids in list(self.subscription_connections.items()):
            connection_ids.discard(connection_id)
            if not connection_ids:
                del self.subscription_connections[sub_id]
                if sub_id in self.subscriptions:
                    del self.subscriptions[sub_id]
        
        logger.info(f"WebSocket disconnected: {connection_id} for user {user_id}")
    
    async def send_personal_message(self, message: str, connection_id: str):
        """Send message to specific WebSocket connection"""
        if connection_id in self.active_connections:
            websocket = self.active_connections[connection_id]
            if websocket.client_state == WebSocketState.CONNECTED:
                try:
                    await websocket.send_text(message)
                except Exception as e:
                    logger.error(f"Error sending message to {connection_id}: {e}")
                    # Connection might be broken, remove it
                    if connection_id in self.active_connections:
                        del self.active_connections[connection_id]
    
    async def broadcast_to_subscribers(self, subscription_id: str, data: Dict):
        """Broadcast analytics update to all subscribers"""
        if subscription_id not in self.subscription_connections:
            return
        
        message = json.dumps({
            "type": "analytics_update",
            "subscription_id": subscription_id,
            "timestamp": datetime.now().isoformat(),
            "data": data
        })
        
        # Send to all connections subscribed to this metric
        connection_ids = list(self.subscription_connections[subscription_id])
        for connection_id in connection_ids:
            await self.send_personal_message(message, connection_id)
    
    async def subscribe(
        self, 
        connection_id: str, 
        subscription: AnalyticsSubscription
    ):
        """Subscribe connection to analytics updates"""
        sub_id = subscription.subscription_id
        
        # Store subscription
        self.subscriptions[sub_id] = subscription
        
        # Track connection for this subscription
        if sub_id not in self.subscription_connections:
            self.subscription_connections[sub_id] = set()
        self.subscription_connections[sub_id].add(connection_id)
        
        logger.info(f"Subscription created: {sub_id} for connection {connection_id}")
    
    async def unsubscribe(self, connection_id: str, subscription_id: str):
        """Unsubscribe connection from analytics updates"""
        if subscription_id in self.subscription_connections:
            self.subscription_connections[subscription_id].discard(connection_id)
            
            # Clean up empty subscription
            if not self.subscription_connections[subscription_id]:
                del self.subscription_connections[subscription_id]
                if subscription_id in self.subscriptions:
                    del self.subscriptions[subscription_id]
        
        logger.info(f"Unsubscribed {connection_id} from {subscription_id}")
    
    async def start_background_updates(self, analytics_service: AnalyticsService):
        """Start background task for periodic analytics updates"""
        if self.running:
            return
        
        self.running = True
        
        # Create background tasks for different update intervals
        tasks = [
            asyncio.create_task(self._real_time_metrics_loop(analytics_service)),
            asyncio.create_task(self._periodic_updates_loop(analytics_service)),
            asyncio.create_task(self._health_monitoring_loop(analytics_service))
        ]
        
        self.background_tasks.update(tasks)
        logger.info("Analytics WebSocket background updates started")
    
    async def stop_background_updates(self):
        """Stop all background update tasks"""
        self.running = False
        
        for task in self.background_tasks:
            if not task.done():
                task.cancel()
        
        # Wait for all tasks to complete
        if self.background_tasks:
            await asyncio.gather(*self.background_tasks, return_exceptions=True)
        
        self.background_tasks.clear()
        logger.info("Analytics WebSocket background updates stopped")
    
    async def _real_time_metrics_loop(self, analytics_service: AnalyticsService):
        """Real-time metrics update loop (every 5 seconds)"""
        while self.running:
            try:
                # Get real-time metrics for active subscriptions
                for sub_id, subscription in self.subscriptions.items():
                    if subscription.metric_type == "real_time_scraping":
                        await self._update_real_time_scraping_metrics(
                            sub_id, subscription, analytics_service
                        )
                    elif subscription.metric_type == "system_performance":
                        await self._update_system_performance_metrics(
                            sub_id, subscription, analytics_service
                        )
                
                await asyncio.sleep(5)  # Update every 5 seconds
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in real-time metrics loop: {e}")
                await asyncio.sleep(5)
    
    async def _periodic_updates_loop(self, analytics_service: AnalyticsService):
        """Periodic analytics updates loop (every 30 seconds)"""
        while self.running:
            try:
                # Get periodic updates for subscriptions
                for sub_id, subscription in self.subscriptions.items():
                    if subscription.metric_type in ["domain_analytics", "project_performance"]:
                        await self._update_periodic_analytics(
                            sub_id, subscription, analytics_service
                        )
                
                await asyncio.sleep(30)  # Update every 30 seconds
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in periodic updates loop: {e}")
                await asyncio.sleep(30)
    
    async def _health_monitoring_loop(self, analytics_service: AnalyticsService):
        """Health monitoring update loop (every 60 seconds)"""
        while self.running:
            try:
                # Check for health monitoring subscriptions
                for sub_id, subscription in self.subscriptions.items():
                    if subscription.metric_type == "health_monitoring":
                        health_data = await analytics_service.get_service_health()
                        await self.broadcast_to_subscribers(sub_id, health_data)
                
                await asyncio.sleep(60)  # Update every minute
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in health monitoring loop: {e}")
                await asyncio.sleep(60)
    
    async def _update_real_time_scraping_metrics(
        self, 
        sub_id: str, 
        subscription: AnalyticsSubscription,
        analytics_service: AnalyticsService
    ):
        """Update real-time scraping metrics"""
        try:
            # This would get live scraping metrics
            # For now, return placeholder data
            metrics = {
                "active_scrapers": 0,
                "pages_per_minute": 0.0,
                "current_success_rate": 0.0,
                "queue_size": 0,
                "avg_response_time": 0.0
            }
            
            await self.broadcast_to_subscribers(sub_id, metrics)
        except Exception as e:
            logger.error(f"Error updating real-time scraping metrics: {e}")
    
    async def _update_system_performance_metrics(
        self, 
        sub_id: str, 
        subscription: AnalyticsSubscription,
        analytics_service: AnalyticsService
    ):
        """Update system performance metrics"""
        try:
            context = AnalyticsQueryContext(use_cache=False)
            system_data = await analytics_service.get_system_performance(context=context)
            
            # Convert to serializable format
            metrics = {
                "active_users": system_data.active_users,
                "active_projects": system_data.active_projects,
                "scraping_throughput": system_data.scraping_throughput,
                "avg_response_time": system_data.avg_response_time,
                "error_rate": system_data.error_rate
            }
            
            await self.broadcast_to_subscribers(sub_id, metrics)
        except Exception as e:
            logger.error(f"Error updating system performance metrics: {e}")
    
    async def _update_periodic_analytics(
        self, 
        sub_id: str, 
        subscription: AnalyticsSubscription,
        analytics_service: AnalyticsService
    ):
        """Update periodic analytics data"""
        try:
            # This would implement specific analytics updates based on subscription type
            # For now, return placeholder data
            analytics = {
                "timestamp": datetime.now().isoformat(),
                "metric_type": subscription.metric_type,
                "update_interval": subscription.update_interval,
                "data": {}
            }
            
            await self.broadcast_to_subscribers(sub_id, analytics)
        except Exception as e:
            logger.error(f"Error updating periodic analytics: {e}")


# Global WebSocket manager instance
websocket_manager = AnalyticsWebSocketManager()


@router.websocket("/ws/analytics")
async def analytics_websocket_endpoint(
    websocket: WebSocket,
    token: Optional[str] = Query(None),
    analytics_service: AnalyticsService = Depends(get_analytics_service)
):
    """
    WebSocket endpoint for real-time analytics updates
    
    Supports:
    - Real-time scraping metrics
    - System performance monitoring  
    - Live dashboard updates
    - Custom analytics subscriptions
    """
    connection_id = None
    current_user = None
    
    try:
        # Authenticate user via token
        if token:
            try:
                current_user = await deps.get_current_user_from_token(token)
            except Exception as e:
                logger.error(f"WebSocket authentication failed: {e}")
                await websocket.close(code=4001, reason="Authentication failed")
                return
        else:
            await websocket.close(code=4001, reason="Authentication token required")
            return
        
        # Accept connection
        connection_id = await websocket_manager.connect(websocket, current_user.id)
        
        # Start background updates if not already running
        await websocket_manager.start_background_updates(analytics_service)
        
        # Send welcome message
        welcome_message = {
            "type": "connection_established",
            "connection_id": connection_id,
            "timestamp": datetime.now().isoformat(),
            "user_id": str(current_user.id)
        }
        await websocket.send_text(json.dumps(welcome_message))
        
        # Handle incoming messages
        while True:
            try:
                # Wait for messages from client
                data = await websocket.receive_text()
                message = json.loads(data)
                
                await handle_websocket_message(
                    connection_id, message, current_user, analytics_service
                )
                
            except WebSocketDisconnect:
                logger.info(f"WebSocket disconnected: {connection_id}")
                break
            except json.JSONDecodeError:
                await websocket.send_text(json.dumps({
                    "type": "error",
                    "message": "Invalid JSON format"
                }))
            except Exception as e:
                logger.error(f"Error handling WebSocket message: {e}")
                await websocket.send_text(json.dumps({
                    "type": "error", 
                    "message": str(e)
                }))
    
    except Exception as e:
        logger.error(f"WebSocket connection error: {e}")
    
    finally:
        # Clean up connection
        if connection_id and current_user:
            await websocket_manager.disconnect(connection_id, current_user.id)


async def handle_websocket_message(
    connection_id: str,
    message: Dict,
    current_user: User,
    analytics_service: AnalyticsService
):
    """Handle incoming WebSocket messages"""
    message_type = message.get("type")
    
    if message_type == "subscribe":
        await handle_subscription_message(connection_id, message, current_user)
    elif message_type == "unsubscribe":
        await handle_unsubscription_message(connection_id, message)
    elif message_type == "get_analytics":
        await handle_analytics_request(connection_id, message, current_user, analytics_service)
    elif message_type == "ping":
        # Respond to ping with pong
        await websocket_manager.send_personal_message(
            json.dumps({"type": "pong", "timestamp": datetime.now().isoformat()}),
            connection_id
        )
    else:
        # Unknown message type
        await websocket_manager.send_personal_message(
            json.dumps({
                "type": "error",
                "message": f"Unknown message type: {message_type}"
            }),
            connection_id
        )


async def handle_subscription_message(
    connection_id: str,
    message: Dict,
    current_user: User
):
    """Handle subscription requests"""
    try:
        # Parse subscription request
        subscription_data = message.get("subscription", {})
        
        # Generate subscription ID
        subscription_id = subscription_data.get("subscription_id") or str(uuid.uuid4())
        
        subscription = AnalyticsSubscription(
            subscription_id=subscription_id,
            metric_type=subscription_data.get("metric_type", "system_performance"),
            filters=subscription_data.get("filters", {}),
            update_interval=subscription_data.get("update_interval", 30)
        )
        
        # Validate subscription
        if subscription.update_interval < 5:
            raise ValueError("Update interval must be at least 5 seconds")
        
        # Subscribe connection
        await websocket_manager.subscribe(connection_id, subscription)
        
        # Confirm subscription
        response = {
            "type": "subscription_confirmed",
            "subscription_id": subscription_id,
            "metric_type": subscription.metric_type,
            "update_interval": subscription.update_interval
        }
        
        await websocket_manager.send_personal_message(
            json.dumps(response), connection_id
        )
        
    except Exception as e:
        error_response = {
            "type": "subscription_error",
            "message": str(e)
        }
        await websocket_manager.send_personal_message(
            json.dumps(error_response), connection_id
        )


async def handle_unsubscription_message(connection_id: str, message: Dict):
    """Handle unsubscription requests"""
    subscription_id = message.get("subscription_id")
    
    if subscription_id:
        await websocket_manager.unsubscribe(connection_id, subscription_id)
        
        response = {
            "type": "unsubscription_confirmed",
            "subscription_id": subscription_id
        }
    else:
        response = {
            "type": "error",
            "message": "Subscription ID required for unsubscription"
        }
    
    await websocket_manager.send_personal_message(
        json.dumps(response), connection_id
    )


async def handle_analytics_request(
    connection_id: str,
    message: Dict,
    current_user: User,
    analytics_service: AnalyticsService
):
    """Handle one-time analytics requests"""
    try:
        request_type = message.get("request_type")
        request_params = message.get("params", {})
        
        if request_type == "domain_stats":
            domain = request_params.get("domain")
            if not domain:
                raise ValueError("Domain parameter required")
            
            context = AnalyticsQueryContext(
                user_id=current_user.id,
                use_cache=True
            )
            
            stats = await analytics_service.get_domain_statistics(domain, context)
            
            response = {
                "type": "analytics_response",
                "request_type": request_type,
                "data": stats.dict()
            }
            
        elif request_type == "project_performance":
            project_id = request_params.get("project_id")
            if not project_id:
                raise ValueError("Project ID parameter required")
            
            context = AnalyticsQueryContext(
                user_id=current_user.id,
                use_cache=True
            )
            
            performance = await analytics_service.get_project_performance(
                UUID(project_id), context=context
            )
            
            response = {
                "type": "analytics_response",
                "request_type": request_type,
                "data": performance.dict()
            }
            
        else:
            response = {
                "type": "error",
                "message": f"Unknown request type: {request_type}"
            }
        
        await websocket_manager.send_personal_message(
            json.dumps(response, default=str), connection_id
        )
        
    except Exception as e:
        error_response = {
            "type": "analytics_error",
            "message": str(e)
        }
        await websocket_manager.send_personal_message(
            json.dumps(error_response), connection_id
        )


@router.get("/ws/analytics/connections")
async def get_websocket_connections(
    current_user: User = Depends(deps.get_current_admin_user)
):
    """Get current WebSocket connections (admin only)"""
    return {
        "active_connections": len(websocket_manager.active_connections),
        "user_connections": len(websocket_manager.user_connections),
        "active_subscriptions": len(websocket_manager.subscriptions),
        "background_tasks_running": websocket_manager.running
    }


@router.post("/ws/analytics/broadcast")
async def broadcast_message(
    message: str = Query(..., description="Message to broadcast"),
    subscription_id: Optional[str] = Query(None, description="Target subscription ID"),
    current_user: User = Depends(deps.get_current_admin_user)
):
    """Broadcast message to WebSocket connections (admin only)"""
    try:
        broadcast_data = {
            "type": "admin_broadcast",
            "message": message,
            "timestamp": datetime.now().isoformat(),
            "from": "system"
        }
        
        if subscription_id and subscription_id in websocket_manager.subscriptions:
            # Broadcast to specific subscription
            await websocket_manager.broadcast_to_subscribers(subscription_id, broadcast_data)
            return {"message": f"Broadcasted to subscription {subscription_id}"}
        else:
            # Broadcast to all connections
            for connection_id in websocket_manager.active_connections:
                await websocket_manager.send_personal_message(
                    json.dumps(broadcast_data), connection_id
                )
            return {"message": f"Broadcasted to {len(websocket_manager.active_connections)} connections"}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))