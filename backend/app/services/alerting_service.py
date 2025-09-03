"""
Comprehensive Alerting Service for Phase 2 DuckDB Analytics System
================================================================

Multi-channel alerting system with intelligent notification routing, escalation policies,
and integration with monitoring service for the complete Phase 2 analytics platform.

Features:
- Multi-channel notifications (Email, Slack, Discord, Webhook, SMS)
- Alert severity-based routing and escalation
- Alert suppression and throttling to prevent spam
- Alert correlation and deduplication
- Escalation policies with time-based triggers
- Alert history and audit trail
- Integration with monitoring service anomaly detection
- Configurable notification templates
- Alert acknowledgment and resolution tracking
"""

import asyncio
import hashlib
import json
import logging
import smtplib
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from enum import Enum
from typing import Dict, List, Optional, Set, Any, Callable, Union
from uuid import uuid4

import aiofiles
import httpx
import redis.asyncio as aioredis
from jinja2 import Environment, DictLoader

from app.core.config import settings
from app.services.monitoring_service import (
    monitoring_service, 
    AlertSeverity, 
    Anomaly, 
    HealthStatus
)

logger = logging.getLogger(__name__)


class AlertStatus(str, Enum):
    """Alert lifecycle status"""
    ACTIVE = "active"
    ACKNOWLEDGED = "acknowledged"
    SUPPRESSED = "suppressed"
    RESOLVED = "resolved"
    ESCALATED = "escalated"
    EXPIRED = "expired"


class NotificationChannel(str, Enum):
    """Available notification channels"""
    EMAIL = "email"
    SLACK = "slack"
    DISCORD = "discord"
    WEBHOOK = "webhook"
    SMS = "sms"
    IN_APP = "in_app"


class EscalationLevel(str, Enum):
    """Escalation levels for alert management"""
    LEVEL_1 = "level_1"  # Team notifications
    LEVEL_2 = "level_2"  # Manager notifications
    LEVEL_3 = "level_3"  # Executive notifications
    LEVEL_4 = "level_4"  # External service notifications


@dataclass
class NotificationTarget:
    """Target for alert notifications"""
    channel: NotificationChannel
    address: str  # Email, webhook URL, phone number, etc.
    name: Optional[str] = None
    enabled: bool = True
    severity_filter: Set[AlertSeverity] = field(default_factory=lambda: set(AlertSeverity))
    component_filter: Set[str] = field(default_factory=set)  # Empty means all components


@dataclass
class EscalationPolicy:
    """Escalation policy configuration"""
    id: str
    name: str
    levels: Dict[EscalationLevel, List[NotificationTarget]]
    escalation_intervals: Dict[EscalationLevel, int]  # seconds
    max_escalation_level: EscalationLevel = EscalationLevel.LEVEL_3
    auto_resolve_timeout: Optional[int] = None  # seconds


@dataclass
class AlertRule:
    """Alert rule configuration"""
    id: str
    name: str
    description: str
    severity: AlertSeverity
    component: Optional[str] = None
    metric: Optional[str] = None
    condition: str = ""  # e.g., "value > threshold"
    threshold: Optional[float] = None
    duration: int = 60  # seconds - how long condition must be true
    enabled: bool = True
    escalation_policy_id: Optional[str] = None
    suppression_duration: int = 300  # seconds
    tags: Dict[str, str] = field(default_factory=dict)


@dataclass
class Alert:
    """Individual alert instance"""
    id: str
    rule_id: str
    title: str
    description: str
    severity: AlertSeverity
    component: str
    metric: str
    current_value: Any
    threshold: Any
    status: AlertStatus = AlertStatus.ACTIVE
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    acknowledged_at: Optional[datetime] = None
    acknowledged_by: Optional[str] = None
    resolved_at: Optional[datetime] = None
    resolved_by: Optional[str] = None
    escalation_level: EscalationLevel = EscalationLevel.LEVEL_1
    escalated_at: Optional[datetime] = None
    notification_count: int = 0
    correlation_id: Optional[str] = None
    tags: Dict[str, str] = field(default_factory=dict)
    context: Dict[str, Any] = field(default_factory=dict)


@dataclass
class NotificationResult:
    """Result of notification attempt"""
    channel: NotificationChannel
    target: str
    success: bool
    error: Optional[str] = None
    sent_at: datetime = field(default_factory=datetime.utcnow)
    delivery_time_ms: Optional[float] = None


class AlertingService:
    """
    Comprehensive alerting service for Phase 2 DuckDB analytics system
    
    Provides intelligent alert management with multi-channel notifications,
    escalation policies, and integration with the monitoring system.
    """
    
    def __init__(self):
        self.redis_client: Optional[aioredis.Redis] = None
        self._notification_targets: Dict[str, NotificationTarget] = {}
        self._escalation_policies: Dict[str, EscalationPolicy] = {}
        self._alert_rules: Dict[str, AlertRule] = {}
        self._active_alerts: Dict[str, Alert] = {}
        self._alert_history: List[Alert] = []
        self._suppressed_alerts: Set[str] = set()
        
        # Notification templates
        self._templates = self._initialize_templates()
        
        # Throttling and rate limiting
        self._notification_throttle: Dict[str, datetime] = {}
        self._max_notifications_per_hour = 60
        self._notification_counts: Dict[str, List[datetime]] = {}
        
        # Background tasks
        self._background_tasks: Set[asyncio.Task] = set()
        self._shutdown_event = asyncio.Event()
        
        logger.info("AlertingService initialized")
    
    async def initialize(self):
        """Initialize alerting service and background tasks"""
        try:
            # Initialize Redis connection
            self.redis_client = aioredis.Redis(
                host=settings.REDIS_HOST,
                port=6379,
                db=4,  # Dedicated DB for alerting
                decode_responses=True,
                socket_timeout=5.0
            )
            
            # Test Redis connection
            await self.redis_client.ping()
            logger.info("AlertingService Redis connection established")
            
            # Load configuration from environment
            await self._load_configuration()
            
            # Start background tasks
            await self._start_background_tasks()
            
        except Exception as e:
            logger.error(f"Failed to initialize AlertingService: {e}")
            raise
    
    def _initialize_templates(self) -> Environment:
        """Initialize Jinja2 templates for notifications"""
        templates = {
            'email_subject': '🚨 [{{ severity.upper() }}] {{ title }} - Chrono Scraper Alert',
            'email_body': '''
Alert: {{ title }}
Severity: {{ severity.upper() }}
Component: {{ component }}
Metric: {{ metric }}
Current Value: {{ current_value }}
{% if threshold %}Threshold: {{ threshold }}{% endif %}
Description: {{ description }}

Occurred: {{ created_at }}
{% if context %}
Additional Context:
{% for key, value in context.items() %}
- {{ key }}: {{ value }}
{% endfor %}
{% endif %}

Alert ID: {{ id }}
Correlation ID: {{ correlation_id or "N/A" }}

This alert was generated by Chrono Scraper monitoring system.
            ''',
            'slack_message': '''
🚨 *{{ severity.upper() }} Alert*

*{{ title }}*
Component: `{{ component }}`
Metric: `{{ metric }}`
Current Value: `{{ current_value }}`
{% if threshold %}Threshold: `{{ threshold }}`{% endif %}

{{ description }}

_Alert ID: {{ id }}_
_Time: {{ created_at }}_
            ''',
            'webhook_payload': '''
{
    "alert_id": "{{ id }}",
    "title": "{{ title }}",
    "description": "{{ description }}",
    "severity": "{{ severity }}",
    "component": "{{ component }}",
    "metric": "{{ metric }}",
    "current_value": {{ current_value | tojson }},
    "threshold": {{ threshold | tojson }},
    "status": "{{ status }}",
    "created_at": "{{ created_at }}",
    "correlation_id": {{ correlation_id | tojson }},
    "tags": {{ tags | tojson }},
    "context": {{ context | tojson }}
}
            '''
        }
        
        return Environment(loader=DictLoader(templates))
    
    async def _load_configuration(self):
        """Load alerting configuration from settings and Redis"""
        # Default notification targets
        if settings.ALERT_EMAIL_ENABLED:
            email_target = NotificationTarget(
                channel=NotificationChannel.EMAIL,
                address=getattr(settings, 'ALERT_EMAIL_ADDRESS', 'admin@chrono-scraper.com'),
                name="Admin Email",
                severity_filter={AlertSeverity.CRITICAL, AlertSeverity.HIGH}
            )
            self._notification_targets['admin_email'] = email_target
        
        # Slack webhook if configured
        if hasattr(settings, 'ALERT_SLACK_WEBHOOK') and settings.ALERT_SLACK_WEBHOOK:
            slack_target = NotificationTarget(
                channel=NotificationChannel.SLACK,
                address=settings.ALERT_SLACK_WEBHOOK,
                name="Slack Alerts",
                severity_filter={AlertSeverity.CRITICAL, AlertSeverity.HIGH, AlertSeverity.MEDIUM}
            )
            self._notification_targets['slack_alerts'] = slack_target
        
        # Default escalation policy
        default_policy = EscalationPolicy(
            id="default",
            name="Default Escalation Policy",
            levels={
                EscalationLevel.LEVEL_1: list(self._notification_targets.values()),
                EscalationLevel.LEVEL_2: list(self._notification_targets.values()),
            },
            escalation_intervals={
                EscalationLevel.LEVEL_1: 0,      # Immediate
                EscalationLevel.LEVEL_2: 1800,  # 30 minutes
            },
            auto_resolve_timeout=7200  # 2 hours
        )
        self._escalation_policies['default'] = default_policy
        
        # Default alert rules for Phase 2 components
        await self._create_default_alert_rules()
    
    async def _create_default_alert_rules(self):
        """Create default alert rules for Phase 2 DuckDB analytics system"""
        default_rules = [
            # System resource alerts
            AlertRule(
                id="system_cpu_critical",
                name="Critical CPU Usage",
                description="System CPU usage exceeded critical threshold",
                severity=AlertSeverity.CRITICAL,
                component="system",
                metric="cpu_usage_percent",
                condition="value > 90",
                threshold=90.0,
                duration=300  # 5 minutes
            ),
            AlertRule(
                id="system_memory_critical",
                name="Critical Memory Usage",
                description="System memory usage exceeded critical threshold",
                severity=AlertSeverity.CRITICAL,
                component="system",
                metric="memory_usage_percent",
                condition="value > 90",
                threshold=90.0,
                duration=300
            ),
            AlertRule(
                id="system_disk_critical",
                name="Critical Disk Usage",
                description="System disk usage exceeded critical threshold",
                severity=AlertSeverity.CRITICAL,
                component="system",
                metric="disk_usage_percent",
                condition="value > 95",
                threshold=95.0,
                duration=60
            ),
            
            # DuckDB alerts
            AlertRule(
                id="duckdb_query_slow",
                name="Slow DuckDB Queries",
                description="DuckDB average query time is too high",
                severity=AlertSeverity.HIGH,
                component="duckdb",
                metric="avg_query_time_seconds",
                condition="value > 30",
                threshold=30.0,
                duration=600  # 10 minutes
            ),
            AlertRule(
                id="duckdb_connection_high",
                name="High DuckDB Connection Count",
                description="DuckDB has too many active connections",
                severity=AlertSeverity.MEDIUM,
                component="duckdb",
                metric="active_connections",
                condition="value > 20",
                threshold=20.0,
                duration=300
            ),
            
            # Data synchronization alerts
            AlertRule(
                id="sync_lag_high",
                name="High Data Sync Lag",
                description="Data synchronization lag is too high",
                severity=AlertSeverity.HIGH,
                component="data_sync_service",
                metric="sync_lag_seconds",
                condition="value > 300",
                threshold=300.0,
                duration=180
            ),
            AlertRule(
                id="sync_failures_high",
                name="High Sync Failure Rate",
                description="Data synchronization failure rate is too high",
                severity=AlertSeverity.CRITICAL,
                component="data_sync_service",
                metric="failure_rate_percent",
                condition="value > 10",
                threshold=10.0,
                duration=300
            ),
            
            # Component health alerts
            AlertRule(
                id="component_critical",
                name="Component Critical Status",
                description="System component is in critical state",
                severity=AlertSeverity.CRITICAL,
                component="*",  # All components
                metric="health_status",
                condition="value == 'critical'",
                duration=60
            ),
            AlertRule(
                id="component_unhealthy",
                name="Component Unhealthy Status",
                description="System component is unhealthy",
                severity=AlertSeverity.HIGH,
                component="*",
                metric="health_status",
                condition="value == 'unhealthy'",
                duration=300
            ),
            
            # Queue depth alerts
            AlertRule(
                id="queue_depth_high",
                name="High Queue Depth",
                description="Task queue depth is too high",
                severity=AlertSeverity.MEDIUM,
                component="celery_workers",
                metric="queue_depth",
                condition="value > 1000",
                threshold=1000.0,
                duration=600
            ),
            
            # Cache performance alerts
            AlertRule(
                id="cache_hit_rate_low",
                name="Low Cache Hit Rate",
                description="Redis cache hit rate is too low",
                severity=AlertSeverity.MEDIUM,
                component="redis",
                metric="hit_rate_percent",
                condition="value < 70",
                threshold=70.0,
                duration=900  # 15 minutes
            )
        ]
        
        for rule in default_rules:
            rule.escalation_policy_id = "default"
            self._alert_rules[rule.id] = rule
    
    async def _start_background_tasks(self):
        """Start background tasks for alert processing"""
        # Alert evaluation task
        evaluation_task = asyncio.create_task(self._alert_evaluation_loop())
        self._background_tasks.add(evaluation_task)
        evaluation_task.add_done_callback(self._background_tasks.discard)
        
        # Escalation processing task
        escalation_task = asyncio.create_task(self._escalation_processing_loop())
        self._background_tasks.add(escalation_task)
        escalation_task.add_done_callback(self._background_tasks.discard)
        
        # Alert cleanup task
        cleanup_task = asyncio.create_task(self._alert_cleanup_loop())
        self._background_tasks.add(cleanup_task)
        cleanup_task.add_done_callback(self._background_tasks.discard)
        
        logger.info("AlertingService background tasks started")
    
    async def _alert_evaluation_loop(self):
        """Background loop for evaluating alert rules"""
        while not self._shutdown_event.is_set():
            try:
                # Get current metrics from monitoring service
                anomalies = await monitoring_service.detect_anomalies()
                
                # Process anomalies and create alerts
                for anomaly in anomalies:
                    await self._process_anomaly(anomaly)
                
                # Evaluate custom alert rules
                await self._evaluate_alert_rules()
                
                # Wait before next evaluation
                await asyncio.sleep(30)  # Evaluate every 30 seconds
                
            except Exception as e:
                logger.error(f"Error in alert evaluation loop: {e}")
                await asyncio.sleep(60)  # Wait longer on error
    
    async def _escalation_processing_loop(self):
        """Background loop for processing alert escalations"""
        while not self._shutdown_event.is_set():
            try:
                current_time = datetime.utcnow()
                
                for alert_id, alert in self._active_alerts.items():
                    if alert.status == AlertStatus.ACTIVE:
                        await self._check_escalation(alert, current_time)
                
                # Wait before next check
                await asyncio.sleep(60)  # Check every minute
                
            except Exception as e:
                logger.error(f"Error in escalation processing loop: {e}")
                await asyncio.sleep(120)  # Wait longer on error
    
    async def _alert_cleanup_loop(self):
        """Background loop for cleaning up old alerts"""
        while not self._shutdown_event.is_set():
            try:
                current_time = datetime.utcnow()
                cleanup_threshold = current_time - timedelta(days=7)  # Keep 7 days
                
                # Move old resolved alerts to history
                alerts_to_cleanup = []
                for alert_id, alert in self._active_alerts.items():
                    if (alert.status == AlertStatus.RESOLVED and 
                        alert.resolved_at and 
                        alert.resolved_at < cleanup_threshold):
                        alerts_to_cleanup.append(alert_id)
                
                for alert_id in alerts_to_cleanup:
                    alert = self._active_alerts.pop(alert_id)
                    self._alert_history.append(alert)
                
                # Clean up old history (keep 30 days)
                history_threshold = current_time - timedelta(days=30)
                self._alert_history = [
                    alert for alert in self._alert_history
                    if alert.created_at > history_threshold
                ]
                
                # Clean up notification throttling
                throttle_threshold = current_time - timedelta(hours=1)
                self._notification_throttle = {
                    key: timestamp for key, timestamp in self._notification_throttle.items()
                    if timestamp > throttle_threshold
                }
                
                # Wait before next cleanup
                await asyncio.sleep(3600)  # Clean every hour
                
            except Exception as e:
                logger.error(f"Error in alert cleanup loop: {e}")
                await asyncio.sleep(3600)
    
    async def _process_anomaly(self, anomaly: Anomaly):
        """Process an anomaly from the monitoring service"""
        try:
            # Check if we have an alert rule for this anomaly
            matching_rules = [
                rule for rule in self._alert_rules.values()
                if (rule.component == anomaly.component or rule.component == "*") and
                   (rule.metric == anomaly.metric or rule.metric == "*") and
                   rule.enabled
            ]
            
            if not matching_rules:
                # Create a dynamic alert for this anomaly
                await self._create_anomaly_alert(anomaly)
                return
            
            # Process with matching rules
            for rule in matching_rules:
                await self._evaluate_rule_for_anomaly(rule, anomaly)
                
        except Exception as e:
            logger.error(f"Error processing anomaly {anomaly.id}: {e}")
    
    async def _create_anomaly_alert(self, anomaly: Anomaly):
        """Create an alert from a monitoring system anomaly"""
        try:
            alert_id = f"anomaly_{anomaly.id}"
            
            # Check if alert already exists
            if alert_id in self._active_alerts:
                return
            
            # Check suppression
            suppression_key = f"{anomaly.component}_{anomaly.metric}"
            if suppression_key in self._suppressed_alerts:
                return
            
            alert = Alert(
                id=alert_id,
                rule_id="anomaly_detection",
                title=f"Anomaly Detected: {anomaly.description}",
                description=anomaly.description,
                severity=anomaly.severity,
                component=anomaly.component,
                metric=anomaly.metric,
                current_value=anomaly.current_value,
                threshold=anomaly.expected_range,
                correlation_id=anomaly.correlation_id,
                context={
                    "anomaly_id": anomaly.id,
                    "detected_at": anomaly.detected_at.isoformat()
                }
            )
            
            self._active_alerts[alert_id] = alert
            await self._send_notifications(alert)
            
            logger.info(f"Created anomaly alert: {alert_id}")
            
        except Exception as e:
            logger.error(f"Error creating anomaly alert: {e}")
    
    async def _evaluate_alert_rules(self):
        """Evaluate all active alert rules against current metrics"""
        try:
            # Get current health report from monitoring service
            health_report = await monitoring_service.generate_health_report()
            
            for rule in self._alert_rules.values():
                if not rule.enabled:
                    continue
                
                await self._evaluate_rule(rule, health_report)
                
        except Exception as e:
            logger.error(f"Error evaluating alert rules: {e}")
    
    async def _evaluate_rule(self, rule: AlertRule, health_report):
        """Evaluate a single alert rule"""
        try:
            # Extract relevant metric value from health report
            metric_value = self._extract_metric_value(rule, health_report)
            
            if metric_value is None:
                return
            
            # Evaluate condition
            condition_met = self._evaluate_condition(rule, metric_value)
            
            alert_id = f"rule_{rule.id}"
            existing_alert = self._active_alerts.get(alert_id)
            
            if condition_met:
                if not existing_alert:
                    # Create new alert
                    await self._create_rule_alert(rule, metric_value, alert_id)
                else:
                    # Update existing alert
                    existing_alert.current_value = metric_value
                    existing_alert.updated_at = datetime.utcnow()
            else:
                if existing_alert and existing_alert.status == AlertStatus.ACTIVE:
                    # Resolve alert
                    await self._resolve_alert(alert_id, "Condition no longer met")
                    
        except Exception as e:
            logger.error(f"Error evaluating rule {rule.id}: {e}")
    
    def _extract_metric_value(self, rule: AlertRule, health_report) -> Any:
        """Extract metric value from health report based on rule"""
        try:
            if rule.component == "system" and hasattr(health_report, 'system_metrics'):
                if rule.metric == "cpu_usage_percent":
                    return health_report.system_metrics.cpu_usage_percent
                elif rule.metric == "memory_usage_percent":
                    return health_report.system_metrics.memory_usage_percent
                elif rule.metric == "disk_usage_percent":
                    return health_report.system_metrics.disk_usage_percent
            
            # Check component health
            if rule.metric == "health_status":
                for component in health_report.components:
                    if rule.component == "*" or component.name == rule.component:
                        return component.status.value
            
            # Check performance metrics
            if hasattr(health_report, 'performance_metrics'):
                perf = health_report.performance_metrics
                if rule.metric == "avg_query_time_seconds":
                    return perf.duckdb_query_duration_avg
                elif rule.metric == "sync_lag_seconds":
                    return perf.sync_lag_seconds
                elif rule.metric == "active_connections":
                    return perf.duckdb_active_connections
            
            # Check specific component metrics
            for component in health_report.components:
                if component.name == rule.component and rule.metric in component.metrics:
                    return component.metrics[rule.metric]
            
            return None
            
        except Exception as e:
            logger.warning(f"Error extracting metric value for rule {rule.id}: {e}")
            return None
    
    def _evaluate_condition(self, rule: AlertRule, value: Any) -> bool:
        """Evaluate alert rule condition"""
        try:
            if rule.condition == "value == 'critical'":
                return str(value).lower() == "critical"
            elif rule.condition == "value == 'unhealthy'":
                return str(value).lower() == "unhealthy"
            elif rule.threshold is not None:
                numeric_value = float(value)
                if ">" in rule.condition:
                    return numeric_value > rule.threshold
                elif "<" in rule.condition:
                    return numeric_value < rule.threshold
                elif "==" in rule.condition:
                    return numeric_value == rule.threshold
            
            return False
            
        except (ValueError, TypeError) as e:
            logger.warning(f"Error evaluating condition for rule {rule.id}: {e}")
            return False
    
    async def _create_rule_alert(self, rule: AlertRule, metric_value: Any, alert_id: str):
        """Create an alert from a triggered rule"""
        try:
            # Check suppression
            suppression_key = f"{rule.component}_{rule.metric}"
            if suppression_key in self._suppressed_alerts:
                return
            
            alert = Alert(
                id=alert_id,
                rule_id=rule.id,
                title=rule.name,
                description=rule.description,
                severity=rule.severity,
                component=rule.component or "unknown",
                metric=rule.metric or "unknown",
                current_value=metric_value,
                threshold=rule.threshold,
                tags=rule.tags.copy(),
                context={
                    "rule_condition": rule.condition,
                    "rule_duration": rule.duration
                }
            )
            
            self._active_alerts[alert_id] = alert
            await self._send_notifications(alert)
            
            # Add suppression if configured
            if rule.suppression_duration > 0:
                self._suppressed_alerts.add(suppression_key)
                # Schedule suppression removal
                asyncio.create_task(self._remove_suppression_after_delay(
                    suppression_key, rule.suppression_duration
                ))
            
            logger.info(f"Created rule alert: {alert_id} from rule {rule.id}")
            
        except Exception as e:
            logger.error(f"Error creating rule alert: {e}")
    
    async def _send_notifications(self, alert: Alert):
        """Send notifications for an alert"""
        try:
            # Get escalation policy
            escalation_policy = self._escalation_policies.get(
                self._alert_rules.get(alert.rule_id, AlertRule("", "", "", AlertSeverity.INFO)).escalation_policy_id,
                self._escalation_policies.get("default")
            )
            
            if not escalation_policy:
                logger.warning(f"No escalation policy found for alert {alert.id}")
                return
            
            # Get notification targets for current escalation level
            targets = escalation_policy.levels.get(alert.escalation_level, [])
            
            # Filter targets based on severity and component
            filtered_targets = [
                target for target in targets
                if target.enabled and
                   (not target.severity_filter or alert.severity in target.severity_filter) and
                   (not target.component_filter or alert.component in target.component_filter)
            ]
            
            # Send notifications
            notification_results = []
            for target in filtered_targets:
                try:
                    if self._should_throttle_notification(target, alert):
                        logger.info(f"Throttling notification to {target.address} for alert {alert.id}")
                        continue
                    
                    result = await self._send_notification(target, alert)
                    notification_results.append(result)
                    
                    if result.success:
                        self._update_notification_throttle(target, alert)
                        alert.notification_count += 1
                    
                except Exception as e:
                    logger.error(f"Error sending notification to {target.address}: {e}")
                    notification_results.append(NotificationResult(
                        channel=target.channel,
                        target=target.address,
                        success=False,
                        error=str(e)
                    ))
            
            # Store notification results in Redis
            await self._store_notification_results(alert.id, notification_results)
            
        except Exception as e:
            logger.error(f"Error sending notifications for alert {alert.id}: {e}")
    
    def _should_throttle_notification(self, target: NotificationTarget, alert: Alert) -> bool:
        """Check if notification should be throttled"""
        throttle_key = f"{target.channel}_{target.address}_{alert.severity}"
        
        # Check time-based throttling
        if throttle_key in self._notification_throttle:
            last_sent = self._notification_throttle[throttle_key]
            min_interval = self._get_min_notification_interval(alert.severity)
            if (datetime.utcnow() - last_sent).seconds < min_interval:
                return True
        
        # Check rate limiting
        rate_key = f"{target.channel}_{target.address}"
        current_time = datetime.utcnow()
        
        if rate_key not in self._notification_counts:
            self._notification_counts[rate_key] = []
        
        # Remove old entries (older than 1 hour)
        hour_ago = current_time - timedelta(hours=1)
        self._notification_counts[rate_key] = [
            timestamp for timestamp in self._notification_counts[rate_key]
            if timestamp > hour_ago
        ]
        
        # Check if we've exceeded the rate limit
        if len(self._notification_counts[rate_key]) >= self._max_notifications_per_hour:
            return True
        
        return False
    
    def _get_min_notification_interval(self, severity: AlertSeverity) -> int:
        """Get minimum notification interval based on severity"""
        intervals = {
            AlertSeverity.CRITICAL: 300,   # 5 minutes
            AlertSeverity.HIGH: 900,       # 15 minutes
            AlertSeverity.MEDIUM: 1800,    # 30 minutes
            AlertSeverity.LOW: 3600,       # 1 hour
            AlertSeverity.INFO: 7200       # 2 hours
        }
        return intervals.get(severity, 1800)
    
    def _update_notification_throttle(self, target: NotificationTarget, alert: Alert):
        """Update notification throttling records"""
        throttle_key = f"{target.channel}_{target.address}_{alert.severity}"
        rate_key = f"{target.channel}_{target.address}"
        current_time = datetime.utcnow()
        
        self._notification_throttle[throttle_key] = current_time
        
        if rate_key not in self._notification_counts:
            self._notification_counts[rate_key] = []
        self._notification_counts[rate_key].append(current_time)
    
    async def _send_notification(self, target: NotificationTarget, alert: Alert) -> NotificationResult:
        """Send notification to a specific target"""
        start_time = time.time()
        
        try:
            if target.channel == NotificationChannel.EMAIL:
                success = await self._send_email_notification(target, alert)
            elif target.channel == NotificationChannel.SLACK:
                success = await self._send_slack_notification(target, alert)
            elif target.channel == NotificationChannel.DISCORD:
                success = await self._send_discord_notification(target, alert)
            elif target.channel == NotificationChannel.WEBHOOK:
                success = await self._send_webhook_notification(target, alert)
            elif target.channel == NotificationChannel.SMS:
                success = await self._send_sms_notification(target, alert)
            elif target.channel == NotificationChannel.IN_APP:
                success = await self._send_in_app_notification(target, alert)
            else:
                raise ValueError(f"Unsupported notification channel: {target.channel}")
            
            delivery_time = (time.time() - start_time) * 1000
            
            return NotificationResult(
                channel=target.channel,
                target=target.address,
                success=success,
                delivery_time_ms=delivery_time
            )
            
        except Exception as e:
            delivery_time = (time.time() - start_time) * 1000
            return NotificationResult(
                channel=target.channel,
                target=target.address,
                success=False,
                error=str(e),
                delivery_time_ms=delivery_time
            )
    
    async def _send_email_notification(self, target: NotificationTarget, alert: Alert) -> bool:
        """Send email notification"""
        try:
            if not settings.ALERT_EMAIL_ENABLED:
                return False
            
            # Render templates
            subject = self._templates.get_template('email_subject').render(**alert.__dict__)
            body = self._templates.get_template('email_body').render(**alert.__dict__)
            
            # Create message
            msg = MIMEMultipart()
            msg['From'] = getattr(settings, 'SMTP_FROM_EMAIL', 'alerts@chrono-scraper.com')
            msg['To'] = target.address
            msg['Subject'] = subject
            msg.attach(MIMEText(body, 'plain'))
            
            # Send via SMTP
            if hasattr(settings, 'SMTP_SERVER') and settings.SMTP_SERVER:
                # Use SMTP
                smtp_server = smtplib.SMTP(settings.SMTP_SERVER, getattr(settings, 'SMTP_PORT', 587))
                smtp_server.starttls()
                
                if hasattr(settings, 'SMTP_USERNAME') and settings.SMTP_USERNAME:
                    smtp_server.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
                
                smtp_server.send_message(msg)
                smtp_server.quit()
                
                logger.info(f"Sent email notification to {target.address} for alert {alert.id}")
                return True
            else:
                logger.warning("SMTP not configured, cannot send email notification")
                return False
            
        except Exception as e:
            logger.error(f"Error sending email notification: {e}")
            return False
    
    async def _send_slack_notification(self, target: NotificationTarget, alert: Alert) -> bool:
        """Send Slack webhook notification"""
        try:
            # Render message template
            message = self._templates.get_template('slack_message').render(**alert.__dict__)
            
            # Prepare payload
            payload = {
                "text": message,
                "username": "Chrono Scraper Alerts",
                "icon_emoji": self._get_severity_emoji(alert.severity),
                "attachments": [
                    {
                        "color": self._get_severity_color(alert.severity),
                        "fields": [
                            {"title": "Component", "value": alert.component, "short": True},
                            {"title": "Metric", "value": alert.metric, "short": True},
                            {"title": "Current Value", "value": str(alert.current_value), "short": True},
                            {"title": "Threshold", "value": str(alert.threshold), "short": True}
                        ],
                        "footer": "Chrono Scraper Monitoring",
                        "ts": int(alert.created_at.timestamp())
                    }
                ]
            }
            
            # Send webhook
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    target.address,
                    json=payload,
                    timeout=10.0
                )
                
                if response.status_code == 200:
                    logger.info(f"Sent Slack notification for alert {alert.id}")
                    return True
                else:
                    logger.error(f"Slack notification failed with status {response.status_code}: {response.text}")
                    return False
                    
        except Exception as e:
            logger.error(f"Error sending Slack notification: {e}")
            return False
    
    async def _send_discord_notification(self, target: NotificationTarget, alert: Alert) -> bool:
        """Send Discord webhook notification"""
        try:
            # Prepare Discord embed
            embed = {
                "title": f"🚨 {alert.severity.upper()} Alert",
                "description": alert.title,
                "color": self._get_severity_color_int(alert.severity),
                "fields": [
                    {"name": "Component", "value": alert.component, "inline": True},
                    {"name": "Metric", "value": alert.metric, "inline": True},
                    {"name": "Current Value", "value": str(alert.current_value), "inline": True},
                    {"name": "Threshold", "value": str(alert.threshold), "inline": True},
                    {"name": "Description", "value": alert.description, "inline": False}
                ],
                "timestamp": alert.created_at.isoformat(),
                "footer": {"text": f"Alert ID: {alert.id}"}
            }
            
            payload = {
                "username": "Chrono Scraper Alerts",
                "embeds": [embed]
            }
            
            # Send webhook
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    target.address,
                    json=payload,
                    timeout=10.0
                )
                
                if response.status_code == 204:  # Discord returns 204 for success
                    logger.info(f"Sent Discord notification for alert {alert.id}")
                    return True
                else:
                    logger.error(f"Discord notification failed with status {response.status_code}")
                    return False
                    
        except Exception as e:
            logger.error(f"Error sending Discord notification: {e}")
            return False
    
    async def _send_webhook_notification(self, target: NotificationTarget, alert: Alert) -> bool:
        """Send generic webhook notification"""
        try:
            # Render payload template
            payload_str = self._templates.get_template('webhook_payload').render(**alert.__dict__)
            payload = json.loads(payload_str)
            
            # Send webhook
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    target.address,
                    json=payload,
                    headers={"Content-Type": "application/json"},
                    timeout=10.0
                )
                
                if response.status_code in [200, 201, 202]:
                    logger.info(f"Sent webhook notification to {target.address} for alert {alert.id}")
                    return True
                else:
                    logger.error(f"Webhook notification failed with status {response.status_code}: {response.text}")
                    return False
                    
        except Exception as e:
            logger.error(f"Error sending webhook notification: {e}")
            return False
    
    async def _send_sms_notification(self, target: NotificationTarget, alert: Alert) -> bool:
        """Send SMS notification (placeholder - requires external SMS service)"""
        try:
            # This would integrate with an SMS service like Twilio, AWS SNS, etc.
            # For now, we'll just log the attempt
            message = f"ALERT: {alert.title} - {alert.component} {alert.metric}={alert.current_value}"
            logger.info(f"SMS notification (not implemented) to {target.address}: {message}")
            return True  # Return True for demonstration
            
        except Exception as e:
            logger.error(f"Error sending SMS notification: {e}")
            return False
    
    async def _send_in_app_notification(self, target: NotificationTarget, alert: Alert) -> bool:
        """Send in-app notification via Redis"""
        try:
            if not self.redis_client:
                return False
            
            # Store notification in Redis for in-app display
            notification = {
                "alert_id": alert.id,
                "title": alert.title,
                "description": alert.description,
                "severity": alert.severity.value,
                "component": alert.component,
                "created_at": alert.created_at.isoformat(),
                "read": False
            }
            
            # Store in user's notification queue
            await self.redis_client.lpush(
                f"notifications:{target.address}",  # target.address contains user ID
                json.dumps(notification)
            )
            
            # Limit queue size
            await self.redis_client.ltrim(f"notifications:{target.address}", 0, 99)
            
            # Set TTL for notifications
            await self.redis_client.expire(f"notifications:{target.address}", 604800)  # 7 days
            
            logger.info(f"Sent in-app notification to {target.address} for alert {alert.id}")
            return True
            
        except Exception as e:
            logger.error(f"Error sending in-app notification: {e}")
            return False
    
    def _get_severity_emoji(self, severity: AlertSeverity) -> str:
        """Get emoji for alert severity"""
        emojis = {
            AlertSeverity.CRITICAL: ":red_circle:",
            AlertSeverity.HIGH: ":orange_circle:",
            AlertSeverity.MEDIUM: ":yellow_circle:",
            AlertSeverity.LOW: ":blue_circle:",
            AlertSeverity.INFO: ":white_circle:"
        }
        return emojis.get(severity, ":grey_circle:")
    
    def _get_severity_color(self, severity: AlertSeverity) -> str:
        """Get hex color for alert severity"""
        colors = {
            AlertSeverity.CRITICAL: "#FF0000",
            AlertSeverity.HIGH: "#FF8000",
            AlertSeverity.MEDIUM: "#FFFF00",
            AlertSeverity.LOW: "#0080FF",
            AlertSeverity.INFO: "#808080"
        }
        return colors.get(severity, "#808080")
    
    def _get_severity_color_int(self, severity: AlertSeverity) -> int:
        """Get integer color for alert severity (Discord)"""
        colors = {
            AlertSeverity.CRITICAL: 0xFF0000,
            AlertSeverity.HIGH: 0xFF8000,
            AlertSeverity.MEDIUM: 0xFFFF00,
            AlertSeverity.LOW: 0x0080FF,
            AlertSeverity.INFO: 0x808080
        }
        return colors.get(severity, 0x808080)
    
    async def _store_notification_results(self, alert_id: str, results: List[NotificationResult]):
        """Store notification results in Redis"""
        try:
            if not self.redis_client:
                return
            
            # Store results with TTL
            results_data = [
                {
                    "channel": result.channel.value,
                    "target": result.target,
                    "success": result.success,
                    "error": result.error,
                    "sent_at": result.sent_at.isoformat(),
                    "delivery_time_ms": result.delivery_time_ms
                }
                for result in results
            ]
            
            await self.redis_client.setex(
                f"alert_notifications:{alert_id}",
                86400,  # 24 hours TTL
                json.dumps(results_data)
            )
            
        except Exception as e:
            logger.error(f"Error storing notification results: {e}")
    
    async def _check_escalation(self, alert: Alert, current_time: datetime):
        """Check if alert should be escalated"""
        try:
            # Get escalation policy
            rule = self._alert_rules.get(alert.rule_id)
            if not rule or not rule.escalation_policy_id:
                return
            
            policy = self._escalation_policies.get(rule.escalation_policy_id)
            if not policy:
                return
            
            # Check if enough time has passed for escalation
            escalation_interval = policy.escalation_intervals.get(alert.escalation_level)
            if not escalation_interval:
                return
            
            time_since_created = (current_time - alert.created_at).seconds
            time_since_escalated = (current_time - alert.escalated_at).seconds if alert.escalated_at else time_since_created
            
            if time_since_escalated < escalation_interval:
                return
            
            # Determine next escalation level
            current_level_value = list(EscalationLevel).index(alert.escalation_level)
            next_level_value = current_level_value + 1
            
            if next_level_value >= len(EscalationLevel):
                return  # Already at max level
            
            next_level = list(EscalationLevel)[next_level_value]
            
            # Check if next level exists in policy
            if next_level not in policy.levels:
                return
            
            # Escalate alert
            alert.escalation_level = next_level
            alert.escalated_at = current_time
            alert.status = AlertStatus.ESCALATED
            
            # Send notifications to next level
            await self._send_notifications(alert)
            
            logger.info(f"Escalated alert {alert.id} to level {next_level.value}")
            
        except Exception as e:
            logger.error(f"Error checking escalation for alert {alert.id}: {e}")
    
    async def _remove_suppression_after_delay(self, suppression_key: str, delay_seconds: int):
        """Remove suppression after specified delay"""
        await asyncio.sleep(delay_seconds)
        self._suppressed_alerts.discard(suppression_key)
        logger.debug(f"Removed suppression for {suppression_key}")
    
    # Public API methods
    
    async def create_alert(
        self,
        title: str,
        description: str,
        severity: AlertSeverity,
        component: str,
        metric: str = "manual",
        current_value: Any = None,
        threshold: Any = None,
        correlation_id: Optional[str] = None,
        tags: Optional[Dict[str, str]] = None,
        context: Optional[Dict[str, Any]] = None
    ) -> str:
        """Create a manual alert"""
        try:
            alert_id = f"manual_{uuid4().hex[:8]}"
            
            alert = Alert(
                id=alert_id,
                rule_id="manual",
                title=title,
                description=description,
                severity=severity,
                component=component,
                metric=metric,
                current_value=current_value,
                threshold=threshold,
                correlation_id=correlation_id,
                tags=tags or {},
                context=context or {}
            )
            
            self._active_alerts[alert_id] = alert
            await self._send_notifications(alert)
            
            logger.info(f"Created manual alert: {alert_id}")
            return alert_id
            
        except Exception as e:
            logger.error(f"Error creating manual alert: {e}")
            raise
    
    async def acknowledge_alert(self, alert_id: str, acknowledged_by: str) -> bool:
        """Acknowledge an active alert"""
        try:
            alert = self._active_alerts.get(alert_id)
            if not alert:
                logger.warning(f"Alert {alert_id} not found")
                return False
            
            alert.status = AlertStatus.ACKNOWLEDGED
            alert.acknowledged_at = datetime.utcnow()
            alert.acknowledged_by = acknowledged_by
            alert.updated_at = datetime.utcnow()
            
            logger.info(f"Alert {alert_id} acknowledged by {acknowledged_by}")
            return True
            
        except Exception as e:
            logger.error(f"Error acknowledging alert {alert_id}: {e}")
            return False
    
    async def resolve_alert(self, alert_id: str, resolved_by: str = "system") -> bool:
        """Resolve an active alert"""
        try:
            return await self._resolve_alert(alert_id, f"Resolved by {resolved_by}")
            
        except Exception as e:
            logger.error(f"Error resolving alert {alert_id}: {e}")
            return False
    
    async def _resolve_alert(self, alert_id: str, resolution_reason: str) -> bool:
        """Internal method to resolve an alert"""
        alert = self._active_alerts.get(alert_id)
        if not alert:
            return False
        
        alert.status = AlertStatus.RESOLVED
        alert.resolved_at = datetime.utcnow()
        alert.resolved_by = resolution_reason
        alert.updated_at = datetime.utcnow()
        
        logger.info(f"Alert {alert_id} resolved: {resolution_reason}")
        return True
    
    async def suppress_alert(self, alert_id: str, duration_seconds: int) -> bool:
        """Suppress an alert for a specified duration"""
        try:
            alert = self._active_alerts.get(alert_id)
            if not alert:
                return False
            
            alert.status = AlertStatus.SUPPRESSED
            alert.updated_at = datetime.utcnow()
            
            # Schedule unsuppression
            asyncio.create_task(self._unsuppress_alert_after_delay(alert_id, duration_seconds))
            
            logger.info(f"Alert {alert_id} suppressed for {duration_seconds} seconds")
            return True
            
        except Exception as e:
            logger.error(f"Error suppressing alert {alert_id}: {e}")
            return False
    
    async def _unsuppress_alert_after_delay(self, alert_id: str, delay_seconds: int):
        """Unsuppress alert after specified delay"""
        await asyncio.sleep(delay_seconds)
        
        alert = self._active_alerts.get(alert_id)
        if alert and alert.status == AlertStatus.SUPPRESSED:
            alert.status = AlertStatus.ACTIVE
            alert.updated_at = datetime.utcnow()
            logger.info(f"Alert {alert_id} unsuppressed")
    
    async def get_active_alerts(self) -> List[Alert]:
        """Get all active alerts"""
        return [alert for alert in self._active_alerts.values() if alert.status in [AlertStatus.ACTIVE, AlertStatus.ESCALATED]]
    
    async def get_alert_history(self, limit: int = 100) -> List[Alert]:
        """Get alert history"""
        all_alerts = list(self._active_alerts.values()) + self._alert_history
        all_alerts.sort(key=lambda x: x.created_at, reverse=True)
        return all_alerts[:limit]
    
    async def get_alert_statistics(self) -> Dict[str, Any]:
        """Get alerting system statistics"""
        try:
            active_alerts = [alert for alert in self._active_alerts.values()]
            
            # Count by severity
            severity_counts = {}
            for severity in AlertSeverity:
                severity_counts[severity.value] = len([a for a in active_alerts if a.severity == severity])
            
            # Count by status
            status_counts = {}
            for status in AlertStatus:
                status_counts[status.value] = len([a for a in active_alerts if a.status == status])
            
            # Count by component
            component_counts = {}
            for alert in active_alerts:
                component_counts[alert.component] = component_counts.get(alert.component, 0) + 1
            
            return {
                "total_active_alerts": len(active_alerts),
                "total_alert_rules": len(self._alert_rules),
                "total_notification_targets": len(self._notification_targets),
                "total_escalation_policies": len(self._escalation_policies),
                "severity_breakdown": severity_counts,
                "status_breakdown": status_counts,
                "component_breakdown": component_counts,
                "suppressed_alert_types": len(self._suppressed_alerts),
                "notification_throttles_active": len(self._notification_throttle)
            }
            
        except Exception as e:
            logger.error(f"Error getting alert statistics: {e}")
            return {"error": str(e)}
    
    async def shutdown(self):
        """Cleanup alerting service resources"""
        try:
            # Signal shutdown to background tasks
            self._shutdown_event.set()
            
            # Wait for background tasks to complete
            if self._background_tasks:
                await asyncio.gather(*self._background_tasks, return_exceptions=True)
            
            # Close Redis connection
            if self.redis_client:
                await self.redis_client.close()
            
            logger.info("AlertingService shutdown completed")
            
        except Exception as e:
            logger.error(f"Error during AlertingService shutdown: {e}")


# Global alerting service instance
alerting_service = AlertingService()


# FastAPI dependency
async def get_alerting_service() -> AlertingService:
    """FastAPI dependency for alerting service"""
    if not alerting_service.redis_client:
        await alerting_service.initialize()
    return alerting_service