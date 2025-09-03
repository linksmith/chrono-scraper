"""
Admin monitoring views for comprehensive system monitoring dashboard
"""
# Optional dependency: sqladmin
try:  # pragma: no cover
    from sqladmin import BaseView
    from sqladmin.forms import Form
    _HAS_SQLADMIN = True
except Exception:  # pragma: no cover
    # Provide a permissive stub that accepts the same class declaration
    class _BaseViewStub:
        def __init_subclass__(cls, **kwargs):
            return super().__init_subclass__()
    BaseView = _BaseViewStub  # type: ignore
    class Form:  # type: ignore
        pass
    _HAS_SQLADMIN = False

from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse
from starlette.templating import Jinja2Templates
import json
from datetime import datetime
import asyncio
import logging

from app.services.monitoring import MonitoringService
from app.core.database import get_db

logger = logging.getLogger(__name__)

templates = Jinja2Templates(directory="app/admin/templates")


class SystemMonitoringView(BaseView):
    """Admin view for comprehensive system monitoring dashboard"""
    
    name = "System Monitoring"
    icon = "fas fa-chart-line"
    identity = "system_monitoring"  # Explicit identity for SQLAdmin routing
    
    async def list(self, request: Request) -> HTMLResponse:
        """Main monitoring dashboard"""
        
        try:
            # Get comprehensive system health
            system_health = await MonitoringService.get_comprehensive_system_health()
            
            # Get Celery monitoring metrics
            celery_metrics = await MonitoringService.get_celery_monitoring_metrics()
            
            # Get database session for application metrics
            async for db in get_db():
                # Get application metrics for last 7 days
                app_metrics = await MonitoringService.get_application_metrics(db, days=7)
                
                # Get error log aggregation for last 24 hours
                error_logs = await MonitoringService.get_error_log_aggregation(db, hours=24)
                
                # Get shared pages metrics if available
                try:
                    shared_pages_metrics = await MonitoringService.get_shared_pages_metrics(db)
                except Exception as e:
                    logger.warning(f"Failed to get shared pages metrics: {str(e)}")
                    shared_pages_metrics = {"status": "unavailable", "error": str(e)}
                
                break
            
            # Prepare dashboard data
            dashboard_data = {
                "timestamp": datetime.utcnow().isoformat(),
                "overall_status": system_health.get("overall", "unknown"),
                "system_health": system_health,
                "celery_metrics": celery_metrics,
                "application_metrics": app_metrics,
                "error_analysis": error_logs,
                "shared_pages_metrics": shared_pages_metrics,
                "alert_counts": {
                    "critical": len([i for i in system_health.get("issues", []) if "critical" in i.lower()]),
                    "warnings": len(system_health.get("warnings", [])),
                    "total_issues": len(system_health.get("issues", []))
                }
            }
            
            return templates.TemplateResponse(
                "monitoring_dashboard.html",
                {
                    "request": request,
                    "dashboard_data": dashboard_data,
                    "dashboard_json": json.dumps(dashboard_data, default=str),
                    "page_title": "System Monitoring Dashboard"
                }
            )
            
        except Exception as e:
            logger.error(f"Error rendering monitoring dashboard: {str(e)}")
            return templates.TemplateResponse(
                "monitoring_error.html",
                {
                    "request": request,
                    "error": str(e),
                    "page_title": "Monitoring Error"
                }
            )

    async def api_health(self, request: Request) -> JSONResponse:
        """API endpoint for real-time health data"""
        
        try:
            system_health = await MonitoringService.get_comprehensive_system_health()
            return JSONResponse(system_health)
            
        except Exception as e:
            logger.error(f"Error getting health data: {str(e)}")
            return JSONResponse(
                {"error": str(e), "timestamp": datetime.utcnow().isoformat()},
                status_code=500
            )

    async def api_celery(self, request: Request) -> JSONResponse:
        """API endpoint for Celery monitoring data"""
        
        try:
            celery_metrics = await MonitoringService.get_celery_monitoring_metrics()
            return JSONResponse(celery_metrics)
            
        except Exception as e:
            logger.error(f"Error getting Celery data: {str(e)}")
            return JSONResponse(
                {"error": str(e), "timestamp": datetime.utcnow().isoformat()},
                status_code=500
            )

    async def api_application(self, request: Request) -> JSONResponse:
        """API endpoint for application metrics"""
        
        try:
            # Get days parameter from query string, default to 7
            days = int(request.query_params.get("days", 7))
            days = min(max(days, 1), 90)  # Limit between 1-90 days
            
            async for db in get_db():
                app_metrics = await MonitoringService.get_application_metrics(db, days=days)
                break
            
            return JSONResponse(app_metrics)
            
        except Exception as e:
            logger.error(f"Error getting application data: {str(e)}")
            return JSONResponse(
                {"error": str(e), "timestamp": datetime.utcnow().isoformat()},
                status_code=500
            )

    async def api_errors(self, request: Request) -> JSONResponse:
        """API endpoint for error log analysis"""
        
        try:
            # Get hours parameter from query string, default to 24
            hours = int(request.query_params.get("hours", 24))
            hours = min(max(hours, 1), 168)  # Limit between 1-168 hours (1 week)
            
            async for db in get_db():
                error_analysis = await MonitoringService.get_error_log_aggregation(db, hours=hours)
                break
            
            return JSONResponse(error_analysis)
            
        except Exception as e:
            logger.error(f"Error getting error analysis: {str(e)}")
            return JSONResponse(
                {"error": str(e), "timestamp": datetime.utcnow().isoformat()},
                status_code=500
            )

    async def api_system_status(self, request: Request) -> JSONResponse:
        """API endpoint for quick system status check"""
        
        try:
            # Quick status check for real-time updates
            status_data = {
                "timestamp": datetime.utcnow().isoformat(),
                "checks": {}
            }
            
            # Run health checks in parallel for faster response
            tasks = [
                MonitoringService._check_database_health(),
                MonitoringService._check_redis_health(),
                MonitoringService._check_meilisearch_health(),
                MonitoringService._check_firecrawl_health()
            ]
            
            results = await asyncio.gather(*tasks, return_exceptions=True)
            service_names = ["database", "redis", "meilisearch", "firecrawl"]
            
            overall_status = "healthy"
            
            for i, result in enumerate(results):
                service_name = service_names[i]
                
                if isinstance(result, Exception):
                    status_data["checks"][service_name] = {
                        "status": "error",
                        "error": str(result)
                    }
                    overall_status = "critical"
                else:
                    status_data["checks"][service_name] = {
                        "status": result.get("status", "unknown"),
                        "response_time_ms": result.get("response_time_ms", 0),
                        "issues_count": len(result.get("issues", [])),
                        "warnings_count": len(result.get("warnings", []))
                    }
                    
                    service_status = result.get("status", "unknown")
                    if service_status == "critical" and overall_status != "critical":
                        overall_status = "critical"
                    elif service_status in ["unhealthy", "degraded"] and overall_status == "healthy":
                        overall_status = service_status
            
            status_data["overall_status"] = overall_status
            
            return JSONResponse(status_data)
            
        except Exception as e:
            logger.error(f"Error getting system status: {str(e)}")
            return JSONResponse(
                {
                    "overall_status": "error",
                    "error": str(e),
                    "timestamp": datetime.utcnow().isoformat()
                },
                status_code=500
            )


class PerformanceAnalysisView(BaseView):
    """Admin view for detailed performance analysis"""
    
    name = "Performance Analysis"
    icon = "fas fa-tachometer-alt"
    identity = "performance_analysis"  # Explicit identity for SQLAdmin routing
    
    async def list(self, request: Request) -> HTMLResponse:
        """Performance analysis dashboard"""
        
        try:
            # Get system metrics
            system_metrics = await MonitoringService._get_system_metrics()
            
            # Get Docker metrics
            docker_metrics = await MonitoringService._get_docker_metrics()
            
            # Get performance metrics
            api_performance = await MonitoringService._get_performance_metrics()
            
            # Get database session for usage trends
            async for db in get_db():
                # Get usage trends for last 30 days
                usage_trends = await MonitoringService.get_usage_trends(db, days=30)
                
                # Get project analytics for performance insights
                system_overview = await MonitoringService.get_system_overview(db)
                
                break
            
            performance_data = {
                "timestamp": datetime.utcnow().isoformat(),
                "system_metrics": system_metrics,
                "container_metrics": docker_metrics,
                "api_performance": api_performance,
                "usage_trends": usage_trends,
                "system_overview": system_overview
            }
            
            return templates.TemplateResponse(
                "performance_analysis.html",
                {
                    "request": request,
                    "performance_data": performance_data,
                    "performance_json": json.dumps(performance_data, default=str),
                    "page_title": "Performance Analysis"
                }
            )
            
        except Exception as e:
            logger.error(f"Error rendering performance dashboard: {str(e)}")
            return templates.TemplateResponse(
                "monitoring_error.html",
                {
                    "request": request,
                    "error": str(e),
                    "page_title": "Performance Analysis Error"
                }
            )


class AlertConfigurationView(BaseView):
    """Admin view for configuring monitoring alerts and thresholds"""
    
    name = "Alert Configuration"
    icon = "fas fa-bell"
    identity = "alert_configuration"  # Explicit identity for SQLAdmin routing
    
    async def list(self, request: Request) -> HTMLResponse:
        """Alert configuration dashboard"""
        
        try:
            # Get current alert configuration (would be stored in database or config)
            alert_config = {
                "cpu_threshold_warning": 75.0,
                "cpu_threshold_critical": 90.0,
                "memory_threshold_warning": 80.0,
                "memory_threshold_critical": 90.0,
                "disk_threshold_warning": 85.0,
                "disk_threshold_critical": 95.0,
                "response_time_threshold_warning": 1000,  # ms
                "response_time_threshold_critical": 2000,  # ms
                "queue_length_threshold_warning": 50,
                "queue_length_threshold_critical": 100,
                "error_rate_threshold_warning": 10.0,  # percent
                "error_rate_threshold_critical": 20.0,  # percent
                "enabled_notifications": {
                    "email": True,
                    "webhook": False,
                    "slack": False
                },
                "notification_settings": {
                    "email_recipients": ["admin@chrono-scraper.com"],
                    "webhook_url": "",
                    "slack_channel": ""
                }
            }
            
            # Get recent alerts (last 24 hours)
            async for db in get_db():
                error_analysis = await MonitoringService.get_error_log_aggregation(db, hours=24)
                critical_alerts = error_analysis.get("critical_alerts", [])
                break
            
            alert_data = {
                "timestamp": datetime.utcnow().isoformat(),
                "configuration": alert_config,
                "recent_alerts": critical_alerts,
                "alert_history": []  # Would be populated from database
            }
            
            return templates.TemplateResponse(
                "alert_configuration.html",
                {
                    "request": request,
                    "alert_data": alert_data,
                    "alert_json": json.dumps(alert_data, default=str),
                    "page_title": "Alert Configuration"
                }
            )
            
        except Exception as e:
            logger.error(f"Error rendering alert configuration: {str(e)}")
            return templates.TemplateResponse(
                "monitoring_error.html",
                {
                    "request": request,
                    "error": str(e),
                    "page_title": "Alert Configuration Error"
                }
            )

    async def update_config(self, request: Request) -> JSONResponse:
        """Update alert configuration"""
        
        try:
            form_data = await request.form()
            
            # In a real implementation, you would save this to database
            # For now, we'll just return success
            
            updated_config = {
                "cpu_threshold_warning": float(form_data.get("cpu_warning", 75.0)),
                "cpu_threshold_critical": float(form_data.get("cpu_critical", 90.0)),
                "memory_threshold_warning": float(form_data.get("memory_warning", 80.0)),
                "memory_threshold_critical": float(form_data.get("memory_critical", 90.0)),
                "response_time_threshold_warning": int(form_data.get("response_time_warning", 1000)),
                "response_time_threshold_critical": int(form_data.get("response_time_critical", 2000)),
                "updated_at": datetime.utcnow().isoformat()
            }
            
            logger.info(f"Alert configuration updated: {updated_config}")
            
            return JSONResponse({
                "success": True,
                "message": "Alert configuration updated successfully",
                "config": updated_config
            })
            
        except Exception as e:
            logger.error(f"Error updating alert configuration: {str(e)}")
            return JSONResponse(
                {"success": False, "error": str(e)},
                status_code=500
            )


# List of monitoring views to register
MONITORING_VIEWS = [
    SystemMonitoringView,
    PerformanceAnalysisView,
    AlertConfigurationView
]