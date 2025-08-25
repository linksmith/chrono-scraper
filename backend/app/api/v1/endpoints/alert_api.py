"""
Alert management API endpoints for comprehensive alert system administration.

Provides REST API for:
- Alert rule management (CRUD operations)
- Active alert monitoring and actions
- Notification channel configuration  
- Escalation policy management
- Alert statistics and reporting
- External webhook integrations
"""

from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Any, Union
import logging
import json
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Body, Path
from fastapi.responses import JSONResponse
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
    AlertAction,
    NotificationChannel,
    AlertMetric,
    EscalationPolicy
)
from pydantic import BaseModel, Field
from typing_extensions import Annotated


logger = logging.getLogger(__name__)

router = APIRouter()


# Pydantic models for request/response
class AlertRuleCreate(BaseModel):
    """Alert rule creation request"""
    name: str = Field(..., min_length=1, max_length=200)
    description: str = Field(..., max_length=1000)
    category: AlertCategory
    severity: AlertSeverity
    condition: str = Field(..., description="Python expression for evaluation")
    threshold_value: Union[int, float] = Field(..., description="Threshold value for comparison")
    comparison_operator: str = Field(..., pattern=r'^(>|<|>=|<=|==|!=)$')
    evaluation_window_minutes: int = Field(default=5, ge=1, le=60)
    evaluation_interval_minutes: int = Field(default=1, ge=1, le=30)
    consecutive_violations: int = Field(default=1, ge=1, le=10)
    enabled: bool = True
    notification_channels: List[NotificationChannel] = Field(default_factory=list)
    suppression_conditions: List[str] = Field(default_factory=list)
    escalation_rules: Dict[str, Any] = Field(default_factory=dict)
    custom_metadata: Dict[str, Any] = Field(default_factory=dict)


class AlertRuleUpdate(BaseModel):
    """Alert rule update request"""
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = Field(None, max_length=1000)
    category: Optional[AlertCategory] = None
    severity: Optional[AlertSeverity] = None
    condition: Optional[str] = None
    threshold_value: Optional[Union[int, float]] = None
    comparison_operator: Optional[str] = Field(None, pattern=r'^(>|<|>=|<=|==|!=)$')
    evaluation_window_minutes: Optional[int] = Field(None, ge=1, le=60)
    evaluation_interval_minutes: Optional[int] = Field(None, ge=1, le=30)
    consecutive_violations: Optional[int] = Field(None, ge=1, le=10)
    enabled: Optional[bool] = None
    notification_channels: Optional[List[NotificationChannel]] = None
    suppression_conditions: Optional[List[str]] = None
    escalation_rules: Optional[Dict[str, Any]] = None
    custom_metadata: Optional[Dict[str, Any]] = None


class AlertActionRequest(BaseModel):
    """Request for alert actions"""
    action: AlertAction
    note: Optional[str] = None
    assigned_to: Optional[int] = None
    duration_minutes: Optional[int] = None
    reason: Optional[str] = None


class MetricSubmission(BaseModel):
    """External metric submission"""
    name: str = Field(..., min_length=1, max_length=200)
    value: Union[int, float, str, bool]
    unit: Optional[str] = None
    timestamp: Optional[datetime] = None
    labels: Dict[str, str] = Field(default_factory=dict)


class AlertFilters(BaseModel):
    """Alert filtering options"""
    severity: Optional[List[AlertSeverity]] = None
    category: Optional[List[AlertCategory]] = None
    status: Optional[List[AlertStatus]] = None
    assigned_to: Optional[int] = None
    created_after: Optional[datetime] = None
    created_before: Optional[datetime] = None
    resolved: Optional[bool] = None


class EscalationPolicyCreate(BaseModel):
    """Escalation policy creation request"""
    name: str = Field(..., min_length=1, max_length=200)
    description: str = Field(..., max_length=1000)
    rules: List[Dict[str, Any]] = Field(..., description="List of escalation steps")
    enabled: bool = True


# Alert Rule Management Endpoints

@router.get("/rules", summary="List all alert rules")
async def get_alert_rules(
    current_admin: User = Depends(get_current_admin_user),
    enabled_only: bool = Query(False, description="Filter to enabled rules only"),
    category: Optional[AlertCategory] = Query(None, description="Filter by category")
) -> Dict[str, Any]:
    """Get all alert rules with optional filtering"""
    try:
        rules = alert_manager.get_alert_rules()
        
        # Apply filters
        filtered_rules = []
        for rule in rules.values():
            if enabled_only and not rule.enabled:
                continue
            if category and rule.category != category:
                continue
            filtered_rules.append({
                'id': rule.id,
                'name': rule.name,
                'description': rule.description,
                'category': rule.category,
                'severity': rule.severity,
                'condition': rule.condition,
                'threshold_value': rule.threshold_value,
                'comparison_operator': rule.comparison_operator,
                'evaluation_window_minutes': rule.evaluation_window_minutes,
                'evaluation_interval_minutes': rule.evaluation_interval_minutes,
                'consecutive_violations': rule.consecutive_violations,
                'enabled': rule.enabled,
                'notification_channels': rule.notification_channels,
                'escalation_rules': rule.escalation_rules,
                'created_at': rule.created_at.isoformat(),
                'created_by': rule.created_by
            })
        
        return {
            'rules': filtered_rules,
            'total_count': len(filtered_rules),
            'enabled_count': len([r for r in filtered_rules if r['enabled']])
        }
        
    except Exception as e:
        logger.error(f"Error retrieving alert rules: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve alert rules")


@router.post("/rules", summary="Create new alert rule", status_code=201)
async def create_alert_rule(
    rule_data: AlertRuleCreate,
    current_admin: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
) -> Dict[str, Any]:
    """Create a new alert rule"""
    try:
        # Create AlertRule object
        rule = AlertRule(
            id=str(uuid4()),
            name=rule_data.name,
            description=rule_data.description,
            category=rule_data.category,
            severity=rule_data.severity,
            condition=rule_data.condition,
            threshold_value=rule_data.threshold_value,
            comparison_operator=rule_data.comparison_operator,
            evaluation_window_minutes=rule_data.evaluation_window_minutes,
            evaluation_interval_minutes=rule_data.evaluation_interval_minutes,
            consecutive_violations=rule_data.consecutive_violations,
            enabled=rule_data.enabled,
            notification_channels=rule_data.notification_channels,
            suppression_conditions=rule_data.suppression_conditions,
            escalation_rules=rule_data.escalation_rules,
            custom_metadata=rule_data.custom_metadata,
            created_at=datetime.now(timezone.utc),
            created_by=current_admin.id
        )
        
        # Create the rule
        rule_id = await alert_manager.create_alert_rule(rule, current_admin.id)
        
        # Log the action
        await log_security_event(
            action="ALERT_RULE_CREATED",
            admin_user_id=current_admin.id,
            severity=SeverityLevel.MEDIUM,
            details={
                'rule_id': rule_id,
                'rule_name': rule.name,
                'rule_category': rule.category.value,
                'rule_severity': rule.severity.value
            }
        )
        
        return {
            'rule_id': rule_id,
            'message': f"Alert rule '{rule.name}' created successfully"
        }
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error creating alert rule: {e}")
        raise HTTPException(status_code=500, detail="Failed to create alert rule")


@router.get("/rules/{rule_id}", summary="Get specific alert rule")
async def get_alert_rule(
    rule_id: Annotated[str, Path(..., description="Alert rule ID")],
    current_admin: User = Depends(get_current_admin_user)
) -> Dict[str, Any]:
    """Get details of a specific alert rule"""
    try:
        rules = alert_manager.get_alert_rules()
        
        if rule_id not in rules:
            raise HTTPException(status_code=404, detail="Alert rule not found")
        
        rule = rules[rule_id]
        return {
            'id': rule.id,
            'name': rule.name,
            'description': rule.description,
            'category': rule.category,
            'severity': rule.severity,
            'condition': rule.condition,
            'threshold_value': rule.threshold_value,
            'comparison_operator': rule.comparison_operator,
            'evaluation_window_minutes': rule.evaluation_window_minutes,
            'evaluation_interval_minutes': rule.evaluation_interval_minutes,
            'consecutive_violations': rule.consecutive_violations,
            'enabled': rule.enabled,
            'notification_channels': rule.notification_channels,
            'suppression_conditions': rule.suppression_conditions,
            'escalation_rules': rule.escalation_rules,
            'custom_metadata': rule.custom_metadata,
            'created_at': rule.created_at.isoformat(),
            'created_by': rule.created_by
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving alert rule {rule_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve alert rule")


@router.put("/rules/{rule_id}", summary="Update alert rule")
async def update_alert_rule(
    rule_id: Annotated[str, Path(..., description="Alert rule ID")],
    rule_updates: AlertRuleUpdate,
    current_admin: User = Depends(get_current_admin_user)
) -> Dict[str, Any]:
    """Update an existing alert rule"""
    try:
        # Convert to dict for update
        updates = {}
        for field, value in rule_updates.dict(exclude_unset=True).items():
            if value is not None:
                updates[field] = value
        
        success = await alert_manager.update_alert_rule(rule_id, updates, current_admin.id)
        
        if not success:
            raise HTTPException(status_code=404, detail="Alert rule not found or update failed")
        
        # Log the action
        await log_security_event(
            action="ALERT_RULE_UPDATED",
            admin_user_id=current_admin.id,
            severity=SeverityLevel.MEDIUM,
            details={
                'rule_id': rule_id,
                'updated_fields': list(updates.keys())
            }
        )
        
        return {
            'rule_id': rule_id,
            'message': "Alert rule updated successfully"
        }
        
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error updating alert rule {rule_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to update alert rule")


@router.delete("/rules/{rule_id}", summary="Delete alert rule")
async def delete_alert_rule(
    rule_id: Annotated[str, Path(..., description="Alert rule ID")],
    current_admin: User = Depends(get_current_admin_user)
) -> Dict[str, Any]:
    """Delete an alert rule"""
    try:
        success = await alert_manager.delete_alert_rule(rule_id, current_admin.id)
        
        if not success:
            raise HTTPException(status_code=404, detail="Alert rule not found")
        
        return {
            'rule_id': rule_id,
            'message': "Alert rule deleted successfully"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting alert rule {rule_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete alert rule")


# Active Alert Management Endpoints

@router.get("/alerts", summary="List active alerts")
async def get_active_alerts(
    current_admin: User = Depends(get_current_admin_user),
    severity: Optional[List[AlertSeverity]] = Query(None, description="Filter by severity"),
    category: Optional[List[AlertCategory]] = Query(None, description="Filter by category"),
    status: Optional[List[AlertStatus]] = Query(None, description="Filter by status"),
    assigned_to: Optional[int] = Query(None, description="Filter by assigned user ID"),
    limit: int = Query(50, ge=1, le=1000, description="Number of alerts to return"),
    offset: int = Query(0, ge=0, description="Number of alerts to skip")
) -> Dict[str, Any]:
    """Get list of active alerts with filtering and pagination"""
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
        
        # Format response
        alert_list = []
        for alert in alerts:
            alert_list.append({
                'id': alert.id,
                'rule_id': alert.rule_id,
                'title': alert.title,
                'description': alert.description,
                'category': alert.category,
                'severity': alert.severity,
                'status': alert.status,
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
                'is_suppressed': alert.is_suppressed()
            })
        
        return {
            'alerts': alert_list,
            'total_count': total_count,
            'returned_count': len(alert_list),
            'has_more': offset + len(alert_list) < total_count
        }
        
    except Exception as e:
        logger.error(f"Error retrieving active alerts: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve active alerts")


@router.get("/alerts/{alert_id}", summary="Get specific alert")
async def get_alert(
    alert_id: Annotated[str, Path(..., description="Alert ID")],
    current_admin: User = Depends(get_current_admin_user)
) -> Dict[str, Any]:
    """Get detailed information about a specific alert"""
    try:
        alert = await alert_manager._get_alert_by_id(alert_id)
        
        if not alert:
            raise HTTPException(status_code=404, detail="Alert not found")
        
        return {
            'id': alert.id,
            'rule_id': alert.rule_id,
            'title': alert.title,
            'description': alert.description,
            'category': alert.category,
            'severity': alert.severity,
            'status': alert.status,
            'source': alert.source,
            'affected_resources': alert.affected_resources,
            'metrics': [
                {
                    'name': m.name,
                    'value': m.value,
                    'unit': m.unit,
                    'timestamp': m.timestamp.isoformat(),
                    'labels': m.labels
                }
                for m in alert.metrics[-10:]  # Last 10 metrics
            ],
            'labels': alert.labels,
            'annotations': alert.annotations,
            'fingerprint': alert.fingerprint,
            'first_seen': alert.first_seen.isoformat(),
            'last_seen': alert.last_seen.isoformat(),
            'resolved_at': alert.resolved_at.isoformat() if alert.resolved_at else None,
            'acknowledged_at': alert.acknowledged_at.isoformat() if alert.acknowledged_at else None,
            'acknowledged_by': alert.acknowledged_by,
            'assigned_to': alert.assigned_to,
            'escalation_level': alert.escalation_level,
            'notification_count': alert.notification_count,
            'last_notification': alert.last_notification.isoformat() if alert.last_notification else None,
            'suppressed_until': alert.suppressed_until.isoformat() if alert.suppressed_until else None,
            'notes': alert.notes,
            'actions_taken': alert.actions_taken,
            'is_acknowledged': alert.is_acknowledged(),
            'is_resolved': alert.is_resolved(),
            'is_suppressed': alert.is_suppressed()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving alert {alert_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve alert")


@router.post("/alerts/{alert_id}/actions", summary="Take action on alert")
async def take_alert_action(
    alert_id: Annotated[str, Path(..., description="Alert ID")],
    action_request: AlertActionRequest,
    current_admin: User = Depends(get_current_admin_user)
) -> Dict[str, Any]:
    """Take an action on an alert (acknowledge, resolve, suppress, assign)"""
    try:
        alert = await alert_manager._get_alert_by_id(alert_id)
        
        if not alert:
            raise HTTPException(status_code=404, detail="Alert not found")
        
        success = False
        message = ""
        
        if action_request.action == AlertAction.ACKNOWLEDGE:
            success = await alert_manager.acknowledge_alert(
                alert_id, 
                current_admin.id, 
                action_request.note
            )
            message = "Alert acknowledged successfully"
            
        elif action_request.action == AlertAction.RESOLVE:
            success = await alert_manager.resolve_alert(
                alert_id,
                current_admin.id, 
                action_request.note
            )
            message = "Alert resolved successfully"
            
        elif action_request.action == AlertAction.SUPPRESS:
            if not action_request.duration_minutes:
                raise HTTPException(status_code=400, detail="Duration required for suppression")
            
            success = await alert_manager.suppress_alert(
                alert_id,
                current_admin.id,
                action_request.duration_minutes,
                action_request.reason or "Manual suppression"
            )
            message = f"Alert suppressed for {action_request.duration_minutes} minutes"
            
        elif action_request.action == AlertAction.ASSIGN:
            if not action_request.assigned_to:
                raise HTTPException(status_code=400, detail="User ID required for assignment")
            
            success = await alert_manager.assign_alert(
                alert_id,
                action_request.assigned_to,
                current_admin.id
            )
            message = f"Alert assigned to user {action_request.assigned_to}"
            
        elif action_request.action == AlertAction.ADD_NOTE:
            if not action_request.note:
                raise HTTPException(status_code=400, detail="Note content required")
            
            alert.add_note(action_request.note, current_admin.id)
            success = True
            message = "Note added to alert"
            
        else:
            raise HTTPException(status_code=400, detail="Unsupported action")
        
        if not success:
            raise HTTPException(status_code=400, detail="Action failed")
        
        # Log the action
        await log_security_event(
            action=f"ALERT_{action_request.action.value.upper()}",
            admin_user_id=current_admin.id,
            severity=SeverityLevel.LOW,
            details={
                'alert_id': alert_id,
                'action': action_request.action.value,
                'note': action_request.note,
                'assigned_to': action_request.assigned_to,
                'duration_minutes': action_request.duration_minutes
            }
        )
        
        return {
            'alert_id': alert_id,
            'action': action_request.action.value,
            'message': message
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error taking action on alert {alert_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to execute alert action")


# External Metric Submission

@router.post("/metrics", summary="Submit external metrics")
async def submit_metrics(
    metrics: List[MetricSubmission],
    current_admin: User = Depends(get_current_admin_user)
) -> Dict[str, Any]:
    """Submit external metrics for alert evaluation"""
    try:
        alerts_triggered = []
        
        for metric_data in metrics:
            # Convert to AlertMetric
            metric = AlertMetric(
                name=metric_data.name,
                value=metric_data.value,
                unit=metric_data.unit,
                timestamp=metric_data.timestamp or datetime.now(timezone.utc),
                labels=metric_data.labels
            )
            
            # Process metric
            triggered_alerts = await alert_manager.process_metric(metric)
            alerts_triggered.extend(triggered_alerts)
        
        return {
            'metrics_processed': len(metrics),
            'alerts_triggered': len(alerts_triggered),
            'alert_ids': [alert.id for alert in alerts_triggered]
        }
        
    except Exception as e:
        logger.error(f"Error processing submitted metrics: {e}")
        raise HTTPException(status_code=500, detail="Failed to process metrics")


# Alert Statistics and Reporting

@router.get("/statistics", summary="Get alert system statistics")
async def get_alert_statistics(
    current_admin: User = Depends(get_current_admin_user),
    time_range_hours: int = Query(24, ge=1, le=168, description="Time range for statistics in hours")
) -> Dict[str, Any]:
    """Get comprehensive alert system statistics"""
    try:
        stats = await alert_manager.get_alert_statistics()
        
        # Add time-based metrics
        cutoff_time = datetime.now(timezone.utc) - timedelta(hours=time_range_hours)
        
        # Get recent alert activity from history
        recent_alerts = [
            alert for alert in alert_manager.alert_history
            if alert.first_seen >= cutoff_time
        ]
        
        recent_stats = {
            'alerts_in_period': len(recent_alerts),
            'resolved_in_period': len([a for a in recent_alerts if a.is_resolved()]),
            'avg_resolution_time_minutes': 0
        }
        
        # Calculate average resolution time
        resolved_with_times = [
            a for a in recent_alerts 
            if a.is_resolved() and a.resolved_at
        ]
        
        if resolved_with_times:
            resolution_times = [
                (a.resolved_at - a.first_seen).total_seconds() / 60
                for a in resolved_with_times
            ]
            recent_stats['avg_resolution_time_minutes'] = sum(resolution_times) / len(resolution_times)
        
        return {
            **stats,
            'time_range_hours': time_range_hours,
            'recent_activity': recent_stats
        }
        
    except Exception as e:
        logger.error(f"Error retrieving alert statistics: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve alert statistics")


# Notification Channel Testing

@router.post("/test-notification", summary="Test notification channel")
async def test_notification_channel(
    channel: NotificationChannel = Body(..., embed=True),
    current_admin: User = Depends(get_current_admin_user)
) -> Dict[str, Any]:
    """Send a test notification through specified channel"""
    try:
        # Create test alert
        test_alert = Alert(
            id="test-alert",
            rule_id="test-rule",
            title="Test Alert Notification",
            description="This is a test alert to verify notification channel configuration.",
            category=AlertCategory.SYSTEM_HEALTH,
            severity=AlertSeverity.INFO,
            affected_resources=["test-resource"],
            labels={"test": "true"}
        )
        
        # Send test notification
        success = await alert_manager._send_notification(test_alert, channel)
        
        # Log the test
        await log_security_event(
            action="ALERT_NOTIFICATION_TEST",
            admin_user_id=current_admin.id,
            severity=SeverityLevel.LOW,
            details={
                'channel': channel.value,
                'success': success
            }
        )
        
        return {
            'channel': channel.value,
            'success': success,
            'message': f"Test notification {'sent successfully' if success else 'failed'}"
        }
        
    except Exception as e:
        logger.error(f"Error testing notification channel {channel}: {e}")
        raise HTTPException(status_code=500, detail="Failed to test notification channel")


# Health Check

@router.get("/health", summary="Alert system health check")
async def get_alert_system_health(
    current_admin: User = Depends(get_current_admin_user)
) -> Dict[str, Any]:
    """Get health status of the alert system"""
    try:
        health_status = {
            'status': 'healthy',
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'components': {},
            'metrics': {}
        }
        
        # Check alert manager initialization
        if not hasattr(alert_manager, 'alert_rules'):
            health_status['status'] = 'unhealthy'
            health_status['components']['alert_manager'] = 'not_initialized'
        else:
            health_status['components']['alert_manager'] = 'healthy'
        
        # Check Redis connection
        if alert_manager.redis_client:
            try:
                await alert_manager.redis_client.ping()
                health_status['components']['redis'] = 'healthy'
            except Exception as e:
                health_status['components']['redis'] = 'unhealthy'
                health_status['status'] = 'degraded'
        else:
            health_status['components']['redis'] = 'not_configured'
        
        # Get system metrics
        stats = await alert_manager.get_alert_statistics()
        health_status['metrics'] = {
            'active_alerts': stats['total_active_alerts'],
            'alert_rules': stats['total_alert_rules'],
            'critical_alerts': stats['alerts_by_severity'].get(AlertSeverity.CRITICAL, 0),
            'emergency_alerts': stats['alerts_by_severity'].get(AlertSeverity.EMERGENCY, 0)
        }
        
        # Check for critical conditions
        if health_status['metrics']['emergency_alerts'] > 0:
            health_status['status'] = 'critical'
        elif health_status['metrics']['critical_alerts'] > 10:
            health_status['status'] = 'degraded'
        
        return health_status
        
    except Exception as e:
        logger.error(f"Error checking alert system health: {e}")
        return {
            'status': 'unhealthy',
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'error': str(e)
        }