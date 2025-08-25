"""
Alert management views for the admin interface.

Provides web-based management interface for:
- Alert dashboard with real-time monitoring
- Alert rule configuration and management  
- Notification channel setup and testing
- Alert history and analytics
- System health monitoring integration
"""

import logging
import json
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Any
from urllib.parse import urlencode

from fastapi import APIRouter, Request, Depends, HTTPException, Form, Query
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import select, and_, or_, func, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_admin_user, get_db
from app.core.audit_logger import log_security_event
from app.models.user import User
from app.models.audit_log import SeverityLevel
from app.services.alert_management import (
    alert_manager,
    AlertRule,
    Alert,
    AlertSeverity,
    AlertCategory,
    AlertStatus,
    NotificationChannel
)
from app.services.monitoring import MonitoringService


logger = logging.getLogger(__name__)

router = APIRouter()
templates = Jinja2Templates(directory="app/admin/templates")


@router.get("/alerts/dashboard", response_class=HTMLResponse, summary="Alert management dashboard")
async def alert_dashboard(
    request: Request,
    current_admin: User = Depends(get_current_admin_user)
):
    """Display the main alert management dashboard"""
    try:
        # Get basic statistics for initial page load
        stats = await alert_manager.get_alert_statistics()
        health = await alert_manager.get_alert_system_health()
        
        context = {
            "request": request,
            "current_admin": current_admin,
            "stats": stats,
            "health": health,
            "page_title": "Alert Management Dashboard",
            "sidebar_active": "alerts"
        }
        
        return templates.TemplateResponse("alert_dashboard.html", context)
        
    except Exception as e:
        logger.error(f"Error loading alert dashboard: {e}")
        raise HTTPException(status_code=500, detail="Failed to load alert dashboard")


@router.get("/alerts/api/statistics", response_class=JSONResponse)
async def get_alert_statistics_api(
    time_range_hours: int = Query(24, ge=1, le=168),
    current_admin: User = Depends(get_current_admin_user)
):
    """API endpoint for alert statistics"""
    try:
        stats = await alert_manager.get_alert_statistics()
        
        # Add time-based analysis
        cutoff_time = datetime.now(timezone.utc) - timedelta(hours=time_range_hours)
        
        # Get recent alert activity from history
        recent_alerts = [
            alert for alert in alert_manager.alert_history
            if alert.first_seen >= cutoff_time
        ]
        
        # Calculate additional metrics
        resolved_alerts = [a for a in recent_alerts if a.is_resolved()]
        avg_resolution_time = 0
        
        if resolved_alerts:
            resolution_times = []
            for alert in resolved_alerts:
                if alert.resolved_at:
                    duration = (alert.resolved_at - alert.first_seen).total_seconds() / 60
                    resolution_times.append(duration)
            
            if resolution_times:
                avg_resolution_time = sum(resolution_times) / len(resolution_times)
        
        # Enhanced statistics
        enhanced_stats = {
            **stats,
            'time_range_hours': time_range_hours,
            'recent_activity': {
                'alerts_in_period': len(recent_alerts),
                'resolved_in_period': len(resolved_alerts),
                'avg_resolution_time_minutes': round(avg_resolution_time, 1),
                'resolution_rate': round(len(resolved_alerts) / len(recent_alerts) * 100, 1) if recent_alerts else 0
            },
            'trend_data': await _generate_trend_data(time_range_hours),
            'top_alert_sources': await _get_top_alert_sources(recent_alerts),
            'escalation_metrics': await _get_escalation_metrics(recent_alerts)
        }
        
        return enhanced_stats
        
    except Exception as e:
        logger.error(f"Error getting alert statistics: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve statistics")


@router.get("/alerts/api/active", response_class=JSONResponse)
async def get_active_alerts_api(
    severity: Optional[List[AlertSeverity]] = Query(None),
    category: Optional[List[AlertCategory]] = Query(None),
    status: Optional[List[AlertStatus]] = Query(None),
    assigned_to: Optional[int] = Query(None),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    current_admin: User = Depends(get_current_admin_user)
):
    """API endpoint for active alerts with filtering"""
    try:
        # Build filters
        filters = {}
        if severity:
            filters['severity'] = severity
        if category:
            filters['category'] = category
        if status:
            filters['status'] = status
        if assigned_to:
            filters['assigned_to'] = assigned_to
        
        # Get filtered alerts
        all_alerts = await alert_manager.get_active_alerts(filters)
        
        # Apply pagination
        total_count = len(all_alerts)
        alerts = all_alerts[offset:offset + limit]
        
        # Format for frontend
        formatted_alerts = []
        for alert in alerts:
            formatted_alerts.append({
                'id': alert.id,
                'rule_id': alert.rule_id,
                'title': alert.title,
                'description': alert.description,
                'category': alert.category.value,
                'severity': alert.severity.value,
                'status': alert.status.value,
                'source': alert.source,
                'affected_resources': alert.affected_resources,
                'labels': alert.labels,
                'fingerprint': alert.fingerprint,
                'first_seen': alert.first_seen.isoformat(),
                'last_seen': alert.last_seen.isoformat(),
                'acknowledged_at': alert.acknowledged_at.isoformat() if alert.acknowledged_at else None,
                'acknowledged_by': alert.acknowledged_by,
                'assigned_to': alert.assigned_to,
                'escalation_level': alert.escalation_level,
                'notification_count': alert.notification_count,
                'last_notification': alert.last_notification.isoformat() if alert.last_notification else None,
                'is_acknowledged': alert.is_acknowledged(),
                'is_resolved': alert.is_resolved(),
                'is_suppressed': alert.is_suppressed(),
                'suppressed_until': alert.suppressed_until.isoformat() if alert.suppressed_until else None
            })
        
        return {
            'alerts': formatted_alerts,
            'total_count': total_count,
            'returned_count': len(formatted_alerts),
            'has_more': offset + len(formatted_alerts) < total_count,
            'filters_applied': bool(filters)
        }
        
    except Exception as e:
        logger.error(f"Error getting active alerts: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve active alerts")


@router.get("/alerts/api/rules", response_class=JSONResponse)
async def get_alert_rules_api(
    enabled_only: bool = Query(False),
    category: Optional[AlertCategory] = Query(None),
    current_admin: User = Depends(get_current_admin_user)
):
    """API endpoint for alert rules"""
    try:
        rules = alert_manager.get_alert_rules()
        
        # Apply filters and format
        formatted_rules = []
        for rule in rules.values():
            if enabled_only and not rule.enabled:
                continue
            if category and rule.category != category:
                continue
            
            formatted_rules.append({
                'id': rule.id,
                'name': rule.name,
                'description': rule.description,
                'category': rule.category.value,
                'severity': rule.severity.value,
                'condition': rule.condition,
                'threshold_value': rule.threshold_value,
                'comparison_operator': rule.comparison_operator,
                'evaluation_window_minutes': rule.evaluation_window_minutes,
                'evaluation_interval_minutes': rule.evaluation_interval_minutes,
                'consecutive_violations': rule.consecutive_violations,
                'enabled': rule.enabled,
                'notification_channels': [ch.value for ch in rule.notification_channels],
                'suppression_conditions': rule.suppression_conditions,
                'escalation_rules': rule.escalation_rules,
                'custom_metadata': rule.custom_metadata,
                'created_at': rule.created_at.isoformat(),
                'created_by': rule.created_by
            })
        
        return {
            'rules': formatted_rules,
            'total_count': len(formatted_rules),
            'enabled_count': len([r for r in formatted_rules if r['enabled']])
        }
        
    except Exception as e:
        logger.error(f"Error getting alert rules: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve alert rules")


@router.get("/alerts/health", response_class=JSONResponse)
async def get_alert_system_health_api(
    current_admin: User = Depends(get_current_admin_user)
):
    """API endpoint for alert system health check"""
    try:
        # Get alert system health
        health = await alert_manager.get_alert_system_health()
        
        # Add integration with overall system monitoring
        system_health = await MonitoringService.get_comprehensive_system_health()
        
        # Combine health data
        combined_health = {
            'alert_system': health,
            'overall_system': {
                'status': system_health.get('overall', 'unknown'),
                'services': system_health.get('services', {}),
                'infrastructure': system_health.get('infrastructure', {}),
                'issues': system_health.get('issues', []),
                'warnings': system_health.get('warnings', [])
            },
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'health_score': await _calculate_health_score(health, system_health)
        }
        
        return combined_health
        
    except Exception as e:
        logger.error(f"Error getting alert system health: {e}")
        return {
            'status': 'error',
            'error': str(e),
            'timestamp': datetime.now(timezone.utc).isoformat()
        }


@router.post("/alerts/test-integration", response_class=JSONResponse)
async def test_alert_integration(
    current_admin: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """Test alert system integration with monitoring services"""
    try:
        test_results = {
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'tests': {},
            'overall_success': True
        }
        
        # Test monitoring service integration
        try:
            system_metrics = await MonitoringService.get_comprehensive_system_health()
            test_results['tests']['monitoring_integration'] = {
                'success': True,
                'message': 'Successfully connected to monitoring service',
                'metrics_collected': len(system_metrics.get('services', {}))
            }
        except Exception as e:
            test_results['tests']['monitoring_integration'] = {
                'success': False,
                'error': str(e)
            }
            test_results['overall_success'] = False
        
        # Test Redis connection (if configured)
        if alert_manager.redis_client:
            try:
                await alert_manager.redis_client.ping()
                test_results['tests']['redis_connection'] = {
                    'success': True,
                    'message': 'Redis connection successful'
                }
            except Exception as e:
                test_results['tests']['redis_connection'] = {
                    'success': False,
                    'error': str(e)
                }
                test_results['overall_success'] = False
        else:
            test_results['tests']['redis_connection'] = {
                'success': False,
                'message': 'Redis not configured'
            }
        
        # Test alert rule evaluation
        try:
            from app.services.alert_management import AlertMetric
            test_metric = AlertMetric(
                name="test_metric",
                value=100,
                timestamp=datetime.now(timezone.utc)
            )
            
            # Process test metric (should not trigger alerts)
            alerts_triggered = await alert_manager.process_metric(test_metric)
            test_results['tests']['rule_evaluation'] = {
                'success': True,
                'message': f'Rule evaluation successful, {len(alerts_triggered)} alerts would be triggered',
                'alerts_triggered': len(alerts_triggered)
            }
        except Exception as e:
            test_results['tests']['rule_evaluation'] = {
                'success': False,
                'error': str(e)
            }
            test_results['overall_success'] = False
        
        # Test database connectivity
        try:
            await db.execute(select(1))
            test_results['tests']['database_connection'] = {
                'success': True,
                'message': 'Database connection successful'
            }
        except Exception as e:
            test_results['tests']['database_connection'] = {
                'success': False,
                'error': str(e)
            }
            test_results['overall_success'] = False
        
        # Log the test
        await log_security_event(
            action="ALERT_SYSTEM_TEST",
            admin_user_id=current_admin.id,
            severity=SeverityLevel.LOW,
            details={
                'overall_success': test_results['overall_success'],
                'tests_passed': sum(1 for test in test_results['tests'].values() if test.get('success')),
                'tests_failed': sum(1 for test in test_results['tests'].values() if not test.get('success'))
            }
        )
        
        return test_results
        
    except Exception as e:
        logger.error(f"Error testing alert integration: {e}")
        raise HTTPException(status_code=500, detail="Failed to test alert integration")


# Helper functions

async def _generate_trend_data(hours: int) -> List[Dict[str, Any]]:
    """Generate trend data for charts"""
    try:
        trend_data = []
        now = datetime.now(timezone.utc)
        
        # Generate hourly buckets
        for i in range(hours):
            bucket_time = now - timedelta(hours=i)
            
            # Count alerts in this time bucket
            bucket_start = bucket_time - timedelta(minutes=30)
            bucket_end = bucket_time + timedelta(minutes=30)
            
            alert_count = len([
                alert for alert in alert_manager.alert_history
                if bucket_start <= alert.first_seen <= bucket_end
            ])
            
            trend_data.append({
                'timestamp': bucket_time.isoformat(),
                'alert_count': alert_count
            })
        
        return list(reversed(trend_data))  # Chronological order
        
    except Exception as e:
        logger.error(f"Error generating trend data: {e}")
        return []


async def _get_top_alert_sources(alerts: List[Alert]) -> List[Dict[str, Any]]:
    """Get top alert sources for analysis"""
    try:
        source_counts = {}
        
        for alert in alerts:
            source = alert.source or 'unknown'
            source_counts[source] = source_counts.get(source, 0) + 1
        
        # Sort by count and return top 10
        sorted_sources = sorted(
            source_counts.items(),
            key=lambda x: x[1],
            reverse=True
        )[:10]
        
        return [
            {'source': source, 'count': count}
            for source, count in sorted_sources
        ]
        
    except Exception as e:
        logger.error(f"Error getting top alert sources: {e}")
        return []


async def _get_escalation_metrics(alerts: List[Alert]) -> Dict[str, Any]:
    """Get escalation metrics"""
    try:
        escalated_alerts = [a for a in alerts if a.escalation_level > 0]
        
        metrics = {
            'total_escalations': len(escalated_alerts),
            'escalation_rate': len(escalated_alerts) / len(alerts) * 100 if alerts else 0,
            'avg_escalation_level': sum(a.escalation_level for a in escalated_alerts) / len(escalated_alerts) if escalated_alerts else 0,
            'max_escalation_level': max(a.escalation_level for a in escalated_alerts) if escalated_alerts else 0
        }
        
        return {
            k: round(v, 2) if isinstance(v, float) else v
            for k, v in metrics.items()
        }
        
    except Exception as e:
        logger.error(f"Error getting escalation metrics: {e}")
        return {
            'total_escalations': 0,
            'escalation_rate': 0,
            'avg_escalation_level': 0,
            'max_escalation_level': 0
        }


async def _calculate_health_score(alert_health: Dict[str, Any], system_health: Dict[str, Any]) -> int:
    """Calculate overall health score (0-100)"""
    try:
        score = 100
        
        # Alert system health penalties
        if alert_health.get('status') == 'critical':
            score -= 50
        elif alert_health.get('status') == 'unhealthy':
            score -= 30
        elif alert_health.get('status') == 'degraded':
            score -= 15
        
        # System health penalties
        system_status = system_health.get('overall', 'healthy')
        if system_status == 'critical':
            score -= 40
        elif system_status == 'unhealthy':
            score -= 25
        elif system_status == 'degraded':
            score -= 10
        
        # Service-specific penalties
        services = system_health.get('services', {})
        unhealthy_services = sum(
            1 for service_data in services.values()
            if isinstance(service_data, dict) and service_data.get('status') != 'healthy'
        )
        
        score -= unhealthy_services * 5
        
        # Component penalties from alert system
        components = alert_health.get('components', {})
        unhealthy_components = sum(
            1 for component_status in components.values()
            if component_status != 'healthy'
        )
        
        score -= unhealthy_components * 8
        
        # Ensure score is within bounds
        return max(0, min(100, score))
        
    except Exception as e:
        logger.error(f"Error calculating health score: {e}")
        return 50  # Neutral score on error