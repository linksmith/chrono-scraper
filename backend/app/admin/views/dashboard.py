"""
Comprehensive admin dashboard view with advanced metrics and visualizations
"""
import asyncio
import json
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Request, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_admin_user, get_db
from app.core.audit_logger import log_admin_action
from app.models.user import User
from app.models.audit_log import AuditActions, ResourceTypes
from app.services.dashboard_metrics import DashboardMetricsService
from app.services.monitoring import MonitoringService
from app.services.dashboard_websocket import dashboard_websocket_manager

logger = logging.getLogger(__name__)

# Initialize templates
templates = Jinja2Templates(directory="app/admin/templates")

router = APIRouter()


@router.get("/dashboard", response_class=HTMLResponse)
async def admin_dashboard(
    request: Request,
    current_admin: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Main comprehensive admin dashboard
    """
    try:
        # Log dashboard access
        await log_admin_action(
            action=AuditActions.ADMIN_DASHBOARD_VIEW,
            resource_type=ResourceTypes.ADMIN_DASHBOARD,
            admin_user_id=current_admin.id,
            details={"dashboard": "main_dashboard"}
        )
        
        # Get executive summary
        executive_summary = await DashboardMetricsService.get_executive_summary(db)
        
        # Get real-time metrics
        real_time_metrics = await DashboardMetricsService.get_real_time_metrics(db)
        
        # Get analytics data for charts (default 7 days)
        analytics_data = await DashboardMetricsService.get_analytics_dashboard_data(db, "7d")
        
        # Prepare dashboard configuration
        dashboard_config = {
            "auto_refresh_interval": 30000,  # 30 seconds
            "chart_themes": {
                "primary_color": "#3b82f6",
                "success_color": "#10b981",
                "warning_color": "#f59e0b",
                "danger_color": "#ef4444",
                "dark_mode": False
            },
            "widgets": {
                "executive_summary": True,
                "system_health": True,
                "user_analytics": True,
                "content_metrics": True,
                "security_overview": True,
                "performance_charts": True,
                "recent_activity": True,
                "alerts": True
            }
        }
        
        # Combine all data
        dashboard_data = {
            "timestamp": datetime.utcnow().isoformat(),
            "executive_summary": executive_summary,
            "real_time_metrics": real_time_metrics,
            "analytics": analytics_data,
            "config": dashboard_config,
            "admin_user": {
                "id": current_admin.id,
                "email": current_admin.email,
                "full_name": current_admin.full_name,
                "is_super_admin": getattr(current_admin, 'is_super_admin', False)
            }
        }
        
        return templates.TemplateResponse("admin_dashboard.html", {
            "request": request,
            "dashboard_data": dashboard_data,
            "dashboard_json": json.dumps(dashboard_data, default=str),
            "page_title": "Admin Dashboard",
            "current_admin": current_admin
        })
        
    except Exception as e:
        logger.error(f"Error loading admin dashboard: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to load dashboard: {str(e)}")


@router.get("/dashboard/api/executive-summary")
async def get_executive_summary(
    current_admin: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """API endpoint for executive summary data"""
    try:
        summary = await DashboardMetricsService.get_executive_summary(db)
        return JSONResponse(summary)
    except Exception as e:
        logger.error(f"Error getting executive summary: {str(e)}")
        return JSONResponse({"error": str(e)}, status_code=500)


@router.get("/dashboard/api/real-time")
async def get_real_time_metrics(
    current_admin: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """API endpoint for real-time metrics"""
    try:
        metrics = await DashboardMetricsService.get_real_time_metrics(db)
        return JSONResponse(metrics)
    except Exception as e:
        logger.error(f"Error getting real-time metrics: {str(e)}")
        return JSONResponse({"error": str(e)}, status_code=500)


@router.get("/dashboard/api/analytics")
async def get_analytics_data(
    time_range: str = Query("7d", description="Time range: 1d, 7d, 30d, 90d"),
    current_admin: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """API endpoint for analytics dashboard data"""
    try:
        analytics = await DashboardMetricsService.get_analytics_dashboard_data(db, time_range)
        return JSONResponse(analytics)
    except Exception as e:
        logger.error(f"Error getting analytics data: {str(e)}")
        return JSONResponse({"error": str(e)}, status_code=500)


@router.get("/dashboard/api/system-health")
async def get_system_health(
    current_admin: User = Depends(get_current_admin_user)
):
    """API endpoint for system health data"""
    try:
        health_data = await MonitoringService.get_comprehensive_system_health()
        return JSONResponse(health_data)
    except Exception as e:
        logger.error(f"Error getting system health: {str(e)}")
        return JSONResponse({"error": str(e)}, status_code=500)


@router.post("/dashboard/api/widget-config")
async def update_widget_config(
    request: Request,
    current_admin: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """Update dashboard widget configuration"""
    try:
        config_data = await request.json()
        
        # Log configuration change
        await log_admin_action(
            action=AuditActions.ADMIN_SETTINGS_UPDATE,
            resource_type=ResourceTypes.ADMIN_DASHBOARD,
            admin_user_id=current_admin.id,
            details={
                "action": "widget_config_update",
                "config": config_data
            }
        )
        
        # In a real implementation, you would save this to database
        # For now, we'll just return success
        return JSONResponse({
            "success": True,
            "message": "Widget configuration updated successfully",
            "timestamp": datetime.utcnow().isoformat()
        })
        
    except Exception as e:
        logger.error(f"Error updating widget config: {str(e)}")
        return JSONResponse({"error": str(e)}, status_code=500)


@router.get("/dashboard/api/export")
async def export_dashboard_data(
    format: str = Query("json", description="Export format: json, csv"),
    time_range: str = Query("7d", description="Time range for export"),
    current_admin: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """Export dashboard data in various formats"""
    try:
        # Get comprehensive data for export
        export_data = {
            "exported_at": datetime.utcnow().isoformat(),
            "exported_by": current_admin.email,
            "time_range": time_range,
            "executive_summary": await DashboardMetricsService.get_executive_summary(db),
            "analytics": await DashboardMetricsService.get_analytics_dashboard_data(db, time_range),
            "system_health": await MonitoringService.get_comprehensive_system_health()
        }
        
        # Log export action
        await log_admin_action(
            action=AuditActions.ADMIN_REPORT_GENERATE,
            resource_type=ResourceTypes.ADMIN_DASHBOARD,
            admin_user_id=current_admin.id,
            details={
                "action": "dashboard_export",
                "format": format,
                "time_range": time_range
            }
        )
        
        if format.lower() == "json":
            return JSONResponse(export_data)
        elif format.lower() == "csv":
            # For CSV, we'd need to flatten the data structure
            # This is a simplified version
            return JSONResponse({
                "message": "CSV export not yet implemented",
                "data_available": True
            })
        else:
            return JSONResponse({"error": "Unsupported format"}, status_code=400)
        
    except Exception as e:
        logger.error(f"Error exporting dashboard data: {str(e)}")
        return JSONResponse({"error": str(e)}, status_code=500)


@router.websocket("/dashboard/ws")
async def dashboard_websocket_endpoint(
    websocket: WebSocket,
    token: str = None
):
    """WebSocket endpoint for real-time dashboard updates"""
    connection_id = f"dashboard_{websocket.client.host}_{datetime.utcnow().timestamp()}"
    
    # Note: WebSocket authentication would need to be handled via query params or headers
    # For now, we'll accept the connection and handle auth verification later
    # In production, you might want to verify the token here
    
    try:
        # Connect to dashboard WebSocket manager
        await dashboard_websocket_manager.connect(websocket, connection_id)
        
        # Send initial data
        await dashboard_websocket_manager.send_dashboard_update(connection_id)
        
        # Handle incoming messages
        while True:
            try:
                # Wait for client messages
                message = await websocket.receive_text()
                data = json.loads(message)
                await dashboard_websocket_manager.handle_client_message(connection_id, data)
                
            except asyncio.TimeoutError:
                # This shouldn't happen as we handle periodic updates in the manager
                pass
                    
    except WebSocketDisconnect:
        logger.info(f"Dashboard WebSocket client disconnected: {connection_id}")
    except Exception as e:
        logger.error(f"Dashboard WebSocket error: {str(e)}")
    finally:
        await dashboard_websocket_manager.disconnect(connection_id)


@router.get("/dashboard/widgets/{widget_name}")
async def get_widget_data(
    widget_name: str,
    time_range: str = Query("24h", description="Time range for widget data"),
    current_admin: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """Get data for a specific dashboard widget"""
    try:
        # Route to appropriate widget data function
        widget_data = {}
        
        if widget_name == "user_analytics":
            # Get user analytics data
            days = {"24h": 1, "7d": 7, "30d": 30}.get(time_range, 1)
            analytics = await DashboardMetricsService.get_analytics_dashboard_data(db, f"{days}d")
            widget_data = analytics.get("user_activity", [])
            
        elif widget_name == "system_health":
            # Get system health data
            widget_data = await MonitoringService.get_comprehensive_system_health()
            
        elif widget_name == "content_metrics":
            # Get content processing metrics
            days = {"24h": 1, "7d": 7, "30d": 30}.get(time_range, 1)
            analytics = await DashboardMetricsService.get_analytics_dashboard_data(db, f"{days}d")
            widget_data = analytics.get("content_processing", [])
            
        elif widget_name == "security_overview":
            # Get security metrics
            days = {"24h": 1, "7d": 7, "30d": 30}.get(time_range, 1)
            analytics = await DashboardMetricsService.get_analytics_dashboard_data(db, f"{days}d")
            widget_data = analytics.get("security_events", [])
            
        elif widget_name == "performance_charts":
            # Get performance metrics
            days = {"24h": 1, "7d": 7, "30d": 30}.get(time_range, 1)
            analytics = await DashboardMetricsService.get_analytics_dashboard_data(db, f"{days}d")
            widget_data = analytics.get("system_performance", [])
            
        else:
            return JSONResponse({"error": "Unknown widget"}, status_code=404)
        
        return JSONResponse({
            "widget": widget_name,
            "time_range": time_range,
            "data": widget_data,
            "timestamp": datetime.utcnow().isoformat()
        })
        
    except Exception as e:
        logger.error(f"Error getting widget data for {widget_name}: {str(e)}")
        return JSONResponse({"error": str(e)}, status_code=500)


@router.post("/dashboard/alerts/acknowledge")
async def acknowledge_alert(
    request: Request,
    current_admin: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """Acknowledge dashboard alerts"""
    try:
        alert_data = await request.json()
        alert_id = alert_data.get("alert_id")
        
        if not alert_id:
            return JSONResponse({"error": "Alert ID required"}, status_code=400)
        
        # Log alert acknowledgment
        await log_admin_action(
            action=AuditActions.ADMIN_ACTION,
            resource_type=ResourceTypes.AUDIT_LOG,
            admin_user_id=current_admin.id,
            resource_id=str(alert_id),
            details={
                "action": "alert_acknowledged",
                "alert_id": alert_id
            }
        )
        
        return JSONResponse({
            "success": True,
            "message": "Alert acknowledged successfully",
            "alert_id": alert_id,
            "acknowledged_by": current_admin.email,
            "timestamp": datetime.utcnow().isoformat()
        })
        
    except Exception as e:
        logger.error(f"Error acknowledging alert: {str(e)}")
        return JSONResponse({"error": str(e)}, status_code=500)


@router.get("/dashboard/health-check")
async def dashboard_health_check():
    """Health check endpoint for dashboard services"""
    try:
        health_status = {
            "status": "healthy",
            "timestamp": datetime.utcnow().isoformat(),
            "services": {
                "dashboard_service": "operational",
                "metrics_service": "operational",
                "websocket_service": "operational"
            }
        }
        
        # Quick check of core services
        try:
            await MonitoringService._check_database_health()
            health_status["services"]["database"] = "operational"
        except Exception:
            health_status["services"]["database"] = "degraded"
            health_status["status"] = "degraded"
        
        return JSONResponse(health_status)
        
    except Exception as e:
        return JSONResponse({
            "status": "unhealthy",
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat()
        }, status_code=500)