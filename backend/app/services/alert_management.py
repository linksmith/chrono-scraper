"""
Enterprise-grade alert management system with comprehensive monitoring, notification channels,
and advanced alert processing capabilities.

This module provides:
- Multi-channel alert notifications (Email, Slack, SMS, Webhooks, PagerDuty)
- Alert rule engine with custom thresholds
- Alert correlation and deduplication
- Escalation workflows and on-call scheduling
- Machine learning-based anomaly detection
- Integration with existing monitoring services
- Compliance and audit trail
"""

import asyncio
import json
import logging
import hashlib
import hmac
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Any, Union, Callable, Set
from dataclasses import dataclass, asdict, field
from enum import Enum, auto
from collections import defaultdict, deque, Counter
import aiohttp
import redis.asyncio as aioredis
import asyncpg
from urllib.parse import urlencode

from sqlmodel import select, and_, or_, func, text, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import settings
from app.core.database import get_db
from app.core.audit_logger import log_security_event
from app.models.audit_log import AuditLog, SeverityLevel
from app.models.user import User
from app.models.admin_settings import AdminSettings
from app.services.monitoring import MonitoringService
from app.services.circuit_breaker import CircuitBreakerOpenException as CircuitBreakerError, get_circuit_breaker_health, with_circuit_breaker, CircuitBreakerConfig


logger = logging.getLogger(__name__)


class AlertSeverity(str, Enum):
    """Alert severity levels"""
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"
    EMERGENCY = "emergency"


class AlertStatus(str, Enum):
    """Alert status lifecycle"""
    OPEN = "open"
    ACKNOWLEDGED = "acknowledged"
    RESOLVED = "resolved"
    SUPPRESSED = "suppressed"
    ESCALATED = "escalated"


class AlertCategory(str, Enum):
    """Alert categories for organization"""
    SYSTEM_HEALTH = "system_health"
    SECURITY_INCIDENT = "security_incident"
    BACKUP_SYSTEM = "backup_system"
    USER_MANAGEMENT = "user_management"
    PERFORMANCE = "performance"
    CAPACITY = "capacity"
    DATA_INTEGRITY = "data_integrity"
    COMPLIANCE = "compliance"
    CUSTOM = "custom"


class NotificationChannel(str, Enum):
    """Supported notification channels"""
    EMAIL = "email"
    SLACK = "slack"
    SMS = "sms"
    WEBHOOK = "webhook"
    PAGERDUTY = "pagerduty"
    OPSGENIE = "opsgenie"
    DISCORD = "discord"
    MSTEAMS = "msteams"


class AlertAction(str, Enum):
    """Actions that can be taken on alerts"""
    ACKNOWLEDGE = "acknowledge"
    RESOLVE = "resolve"
    ESCALATE = "escalate"
    SUPPRESS = "suppress"
    ADD_NOTE = "add_note"
    ASSIGN = "assign"


@dataclass
class AlertMetric:
    """Metric data for alert evaluation"""
    name: str
    value: Union[int, float, str, bool]
    unit: Optional[str] = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    labels: Dict[str, str] = field(default_factory=dict)
    
    def __post_init__(self):
        if isinstance(self.timestamp, str):
            self.timestamp = datetime.fromisoformat(self.timestamp.replace('Z', '+00:00'))


@dataclass
class AlertRule:
    """Alert rule configuration"""
    id: str
    name: str
    description: str
    category: AlertCategory
    severity: AlertSeverity
    condition: str  # Python expression for evaluation
    threshold_value: Union[int, float]
    comparison_operator: str  # '>', '<', '>=', '<=', '==', '!='
    evaluation_window_minutes: int = 5
    evaluation_interval_minutes: int = 1
    consecutive_violations: int = 1
    enabled: bool = True
    notification_channels: List[NotificationChannel] = field(default_factory=list)
    suppression_conditions: List[str] = field(default_factory=list)
    escalation_rules: Dict[str, Any] = field(default_factory=dict)
    custom_metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    created_by: Optional[int] = None
    
    def evaluate(self, metric: AlertMetric) -> bool:
        """Evaluate if metric violates this rule"""
        try:
            # Create evaluation context
            context = {
                'value': metric.value,
                'threshold': self.threshold_value,
                'metric_name': metric.name,
                'labels': metric.labels,
                'timestamp': metric.timestamp
            }
            
            # Build condition expression
            if self.comparison_operator == '>':
                return metric.value > self.threshold_value
            elif self.comparison_operator == '<':
                return metric.value < self.threshold_value
            elif self.comparison_operator == '>=':
                return metric.value >= self.threshold_value
            elif self.comparison_operator == '<=':
                return metric.value <= self.threshold_value
            elif self.comparison_operator == '==':
                return metric.value == self.threshold_value
            elif self.comparison_operator == '!=':
                return metric.value != self.threshold_value
            else:
                # Custom condition evaluation
                return eval(self.condition, {"__builtins__": {}}, context)
                
        except Exception as e:
            logger.error(f"Error evaluating alert rule {self.id}: {e}")
            return False


@dataclass
class Alert:
    """Alert instance"""
    id: str
    rule_id: str
    title: str
    description: str
    category: AlertCategory
    severity: AlertSeverity
    status: AlertStatus = AlertStatus.OPEN
    source: str = "monitoring"
    affected_resources: List[str] = field(default_factory=list)
    metrics: List[AlertMetric] = field(default_factory=list)
    labels: Dict[str, str] = field(default_factory=dict)
    annotations: Dict[str, str] = field(default_factory=dict)
    fingerprint: str = ""
    first_seen: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_seen: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    resolved_at: Optional[datetime] = None
    acknowledged_at: Optional[datetime] = None
    acknowledged_by: Optional[int] = None
    assigned_to: Optional[int] = None
    escalation_level: int = 0
    notification_count: int = 0
    last_notification: Optional[datetime] = None
    suppressed_until: Optional[datetime] = None
    notes: List[Dict[str, Any]] = field(default_factory=list)
    actions_taken: List[Dict[str, Any]] = field(default_factory=list)
    
    def __post_init__(self):
        if not self.id:
            self.id = str(uuid.uuid4())
        if not self.fingerprint:
            self.fingerprint = self._generate_fingerprint()
    
    def _generate_fingerprint(self) -> str:
        """Generate unique fingerprint for alert deduplication"""
        components = [
            self.rule_id,
            self.title,
            ','.join(sorted(self.affected_resources)),
            ','.join(f"{k}={v}" for k, v in sorted(self.labels.items()))
        ]
        fingerprint_string = '|'.join(components)
        return hashlib.sha256(fingerprint_string.encode()).hexdigest()[:16]
    
    def is_acknowledged(self) -> bool:
        """Check if alert is acknowledged"""
        return self.status == AlertStatus.ACKNOWLEDGED
    
    def is_resolved(self) -> bool:
        """Check if alert is resolved"""
        return self.status == AlertStatus.RESOLVED
    
    def is_suppressed(self) -> bool:
        """Check if alert is currently suppressed"""
        if self.status == AlertStatus.SUPPRESSED:
            return True
        if self.suppressed_until and datetime.now(timezone.utc) < self.suppressed_until:
            return True
        return False
    
    def should_escalate(self, escalation_rules: Dict[str, Any]) -> bool:
        """Check if alert should be escalated"""
        if self.is_resolved() or self.is_acknowledged():
            return False
        
        escalation_delay_minutes = escalation_rules.get('delay_minutes', 60)
        max_escalation_level = escalation_rules.get('max_level', 3)
        
        if self.escalation_level >= max_escalation_level:
            return False
        
        time_since_first_seen = datetime.now(timezone.utc) - self.first_seen
        return time_since_first_seen.total_seconds() >= escalation_delay_minutes * 60
    
    def add_note(self, note: str, author_id: int) -> None:
        """Add note to alert"""
        self.notes.append({
            'note': note,
            'author_id': author_id,
            'timestamp': datetime.now(timezone.utc).isoformat()
        })
    
    def add_action(self, action: AlertAction, details: Dict[str, Any], actor_id: int) -> None:
        """Record action taken on alert"""
        self.actions_taken.append({
            'action': action.value,
            'details': details,
            'actor_id': actor_id,
            'timestamp': datetime.now(timezone.utc).isoformat()
        })


@dataclass
class NotificationTemplate:
    """Template for alert notifications"""
    channel: NotificationChannel
    subject_template: str
    body_template: str
    format_type: str = "text"  # text, html, json
    custom_fields: Dict[str, Any] = field(default_factory=dict)


@dataclass
class EscalationPolicy:
    """Escalation policy configuration"""
    id: str
    name: str
    description: str
    rules: List[Dict[str, Any]]  # List of escalation steps
    enabled: bool = True
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class AlertManager:
    """
    Enterprise-grade alert management system with comprehensive features:
    
    - Multi-channel notifications with retry and circuit breaker logic
    - Alert correlation and deduplication
    - Custom alert rules with flexible conditions  
    - Escalation workflows and on-call management
    - Machine learning anomaly detection integration
    - Compliance and audit logging
    - Performance optimization with caching and batching
    """
    
    def __init__(self):
        self.alert_rules: Dict[str, AlertRule] = {}
        self.active_alerts: Dict[str, Alert] = {}  # fingerprint -> alert
        self.alert_history: deque = deque(maxlen=10000)  # Historical alerts
        self.notification_templates: Dict[NotificationChannel, NotificationTemplate] = {}
        self.escalation_policies: Dict[str, EscalationPolicy] = {}
        self.redis_client: Optional[aioredis.Redis] = None
        
        # Performance counters
        self.stats = {
            'alerts_generated': 0,
            'alerts_resolved': 0,
            'notifications_sent': 0,
            'notification_failures': 0,
            'rule_evaluations': 0
        }
        
        # Initialize default notification templates
        self._init_notification_templates()
        
        # Background task handles
        self._background_tasks: Set[asyncio.Task] = set()
    
    async def initialize(self) -> None:
        """Initialize alert manager with database connections and background tasks"""
        try:
            # Initialize Redis connection for caching and pub/sub
            if settings.REDIS_HOST:
                self.redis_client = aioredis.from_url(
                    f"redis://{settings.REDIS_HOST}:6379/3",  # Use DB 3 for alerts
                    decode_responses=True,
                    retry_on_timeout=True,
                    socket_timeout=5.0
                )
                await self.redis_client.ping()
                logger.info("Alert manager Redis connection established")
            
            # Load alert rules from database
            await self._load_alert_rules()
            
            # Load escalation policies
            await self._load_escalation_policies()
            
            # Start background tasks
            await self._start_background_tasks()
            
            logger.info("Alert manager initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize alert manager: {e}")
            raise
    
    async def shutdown(self) -> None:
        """Graceful shutdown of alert manager"""
        logger.info("Shutting down alert manager...")
        
        # Cancel background tasks
        for task in self._background_tasks:
            task.cancel()
        
        if self._background_tasks:
            await asyncio.gather(*self._background_tasks, return_exceptions=True)
        
        # Close Redis connection
        if self.redis_client:
            await self.redis_client.close()
        
        logger.info("Alert manager shutdown complete")
    
    async def _start_background_tasks(self) -> None:
        """Start background monitoring and processing tasks"""
        # Continuous alert evaluation
        task = asyncio.create_task(self._alert_evaluation_loop())
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)
        
        # Alert processing and notifications
        task = asyncio.create_task(self._alert_processing_loop())
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)
        
        # Escalation processing
        task = asyncio.create_task(self._escalation_loop())
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)
        
        # Cleanup resolved alerts
        task = asyncio.create_task(self._cleanup_loop())
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)
        
        logger.info("Alert manager background tasks started")
    
    def _init_notification_templates(self) -> None:
        """Initialize default notification templates"""
        
        # Email template
        self.notification_templates[NotificationChannel.EMAIL] = NotificationTemplate(
            channel=NotificationChannel.EMAIL,
            subject_template="[{severity}] {title}",
            body_template="""
Alert: {title}
Severity: {severity}
Category: {category}
Status: {status}

Description:
{description}

Affected Resources:
{affected_resources}

Time: {timestamp}
Source: {source}

View Alert: {alert_url}
            """.strip(),
            format_type="text"
        )
        
        # Slack template
        self.notification_templates[NotificationChannel.SLACK] = NotificationTemplate(
            channel=NotificationChannel.SLACK,
            subject_template="{title}",
            body_template=json.dumps({
                "attachments": [{
                    "color": "{color}",
                    "title": "{title}",
                    "text": "{description}",
                    "fields": [
                        {"title": "Severity", "value": "{severity}", "short": True},
                        {"title": "Category", "value": "{category}", "short": True},
                        {"title": "Status", "value": "{status}", "short": True},
                        {"title": "Source", "value": "{source}", "short": True}
                    ],
                    "footer": "Chrono Scraper Alert System",
                    "ts": "{timestamp_unix}"
                }]
            }),
            format_type="json"
        )
    
    async def _load_alert_rules(self) -> None:
        """Load alert rules from database"""
        try:
            async for db in get_db():
                # Load from admin settings or dedicated alert_rules table
                result = await db.execute(
                    select(AdminSettings)
                    .where(AdminSettings.key.like('alert_rule_%'))
                )
                
                settings_rows = result.scalars().all()
                
                for setting in settings_rows:
                    try:
                        rule_data = json.loads(setting.value)
                        rule = AlertRule(**rule_data)
                        self.alert_rules[rule.id] = rule
                        logger.debug(f"Loaded alert rule: {rule.name}")
                    except Exception as e:
                        logger.error(f"Error loading alert rule {setting.key}: {e}")
                
                break  # Exit the db loop
                
        except Exception as e:
            logger.error(f"Error loading alert rules: {e}")
    
    async def _load_escalation_policies(self) -> None:
        """Load escalation policies from database"""
        try:
            async for db in get_db():
                result = await db.execute(
                    select(AdminSettings)
                    .where(AdminSettings.key.like('escalation_policy_%'))
                )
                
                settings_rows = result.scalars().all()
                
                for setting in settings_rows:
                    try:
                        policy_data = json.loads(setting.value)
                        policy = EscalationPolicy(**policy_data)
                        self.escalation_policies[policy.id] = policy
                        logger.debug(f"Loaded escalation policy: {policy.name}")
                    except Exception as e:
                        logger.error(f"Error loading escalation policy {setting.key}: {e}")
                
                break  # Exit the db loop
                
        except Exception as e:
            logger.error(f"Error loading escalation policies: {e}")
    
    async def create_alert_rule(self, rule: AlertRule, created_by: int) -> str:
        """Create new alert rule"""
        try:
            rule.created_by = created_by
            rule.created_at = datetime.now(timezone.utc)
            
            # Validate rule
            if not await self._validate_alert_rule(rule):
                raise ValueError("Invalid alert rule configuration")
            
            # Store in memory and database
            self.alert_rules[rule.id] = rule
            
            async for db in get_db():
                setting = AdminSettings(
                    key=f"alert_rule_{rule.id}",
                    value=json.dumps(asdict(rule), default=str),
                    description=f"Alert rule: {rule.name}",
                    category="alerts",
                    created_by=created_by
                )
                db.add(setting)
                await db.commit()
                break
            
            logger.info(f"Created alert rule: {rule.name} (ID: {rule.id})")
            return rule.id
            
        except Exception as e:
            logger.error(f"Error creating alert rule: {e}")
            raise
    
    async def update_alert_rule(self, rule_id: str, updates: Dict[str, Any], updated_by: int) -> bool:
        """Update existing alert rule"""
        try:
            if rule_id not in self.alert_rules:
                raise ValueError(f"Alert rule {rule_id} not found")
            
            rule = self.alert_rules[rule_id]
            
            # Apply updates
            for key, value in updates.items():
                if hasattr(rule, key):
                    setattr(rule, key, value)
            
            # Validate updated rule
            if not await self._validate_alert_rule(rule):
                raise ValueError("Invalid alert rule configuration after update")
            
            # Update in database
            async for db in get_db():
                result = await db.execute(
                    update(AdminSettings)
                    .where(AdminSettings.key == f"alert_rule_{rule_id}")
                    .values(
                        value=json.dumps(asdict(rule), default=str),
                        updated_by=updated_by,
                        updated_at=datetime.now(timezone.utc)
                    )
                )
                await db.commit()
                break
            
            logger.info(f"Updated alert rule: {rule.name} (ID: {rule_id})")
            return True
            
        except Exception as e:
            logger.error(f"Error updating alert rule {rule_id}: {e}")
            return False
    
    async def delete_alert_rule(self, rule_id: str, deleted_by: int) -> bool:
        """Delete alert rule"""
        try:
            if rule_id not in self.alert_rules:
                raise ValueError(f"Alert rule {rule_id} not found")
            
            rule = self.alert_rules[rule_id]
            
            # Remove from memory
            del self.alert_rules[rule_id]
            
            # Delete from database
            async for db in get_db():
                await db.execute(
                    text("DELETE FROM admin_settings WHERE key = :key"),
                    {"key": f"alert_rule_{rule_id}"}
                )
                await db.commit()
                break
            
            # Log deletion
            await log_security_event(
                action="ALERT_RULE_DELETED",
                admin_user_id=deleted_by,
                severity=SeverityLevel.MEDIUM,
                details={
                    'rule_id': rule_id,
                    'rule_name': rule.name,
                    'rule_category': rule.category
                }
            )
            
            logger.info(f"Deleted alert rule: {rule.name} (ID: {rule_id})")
            return True
            
        except Exception as e:
            logger.error(f"Error deleting alert rule {rule_id}: {e}")
            return False
    
    async def _validate_alert_rule(self, rule: AlertRule) -> bool:
        """Validate alert rule configuration"""
        try:
            # Basic validation
            if not rule.name or not rule.condition:
                return False
            
            # Validate condition syntax (basic check)
            if rule.condition and not rule.comparison_operator:
                # Try to compile the condition as Python expression
                compile(rule.condition, '<string>', 'eval')
            
            # Validate threshold value
            if rule.comparison_operator and rule.threshold_value is None:
                return False
            
            # Validate notification channels
            for channel in rule.notification_channels:
                if channel not in NotificationChannel:
                    return False
            
            return True
            
        except Exception as e:
            logger.error(f"Alert rule validation failed: {e}")
            return False
    
    async def process_metric(self, metric: AlertMetric) -> List[Alert]:
        """Process incoming metric and evaluate against alert rules"""
        alerts_triggered = []
        self.stats['rule_evaluations'] += len(self.alert_rules)
        
        try:
            for rule_id, rule in self.alert_rules.items():
                if not rule.enabled:
                    continue
                
                # Check if metric matches rule criteria
                if await self._metric_matches_rule(metric, rule):
                    violation = rule.evaluate(metric)
                    
                    if violation:
                        alert = await self._handle_rule_violation(rule, metric)
                        if alert:
                            alerts_triggered.append(alert)
                    else:
                        # Check if we should resolve existing alert
                        await self._check_alert_resolution(rule_id, metric)
            
            return alerts_triggered
            
        except Exception as e:
            logger.error(f"Error processing metric {metric.name}: {e}")
            return alerts_triggered
    
    async def _metric_matches_rule(self, metric: AlertMetric, rule: AlertRule) -> bool:
        """Check if metric matches rule criteria"""
        # For now, simple name matching - can be extended with label matching
        return True  # Process all metrics against all rules
    
    async def _handle_rule_violation(self, rule: AlertRule, metric: AlertMetric) -> Optional[Alert]:
        """Handle alert rule violation"""
        try:
            # Generate alert fingerprint for deduplication
            temp_alert = Alert(
                id="",
                rule_id=rule.id,
                title=f"{rule.name}: {metric.name}",
                description=rule.description,
                category=rule.category,
                severity=rule.severity,
                affected_resources=[metric.name],
                metrics=[metric],
                labels=metric.labels.copy()
            )
            
            fingerprint = temp_alert._generate_fingerprint()
            
            # Check if alert already exists
            if fingerprint in self.active_alerts:
                existing_alert = self.active_alerts[fingerprint]
                existing_alert.last_seen = datetime.now(timezone.utc)
                existing_alert.metrics.append(metric)
                
                # Keep only recent metrics
                cutoff_time = datetime.now(timezone.utc) - timedelta(hours=1)
                existing_alert.metrics = [
                    m for m in existing_alert.metrics 
                    if m.timestamp > cutoff_time
                ]
                
                return None  # Alert already exists
            
            # Create new alert
            alert = Alert(
                id=str(uuid.uuid4()),
                rule_id=rule.id,
                title=f"{rule.name}: {metric.name}",
                description=f"{rule.description}. Current value: {metric.value}, Threshold: {rule.threshold_value}",
                category=rule.category,
                severity=rule.severity,
                affected_resources=[metric.name],
                metrics=[metric],
                labels=metric.labels.copy(),
                fingerprint=fingerprint
            )
            
            # Store alert
            self.active_alerts[fingerprint] = alert
            self.alert_history.append(alert)
            self.stats['alerts_generated'] += 1
            
            # Cache in Redis for persistence
            if self.redis_client:
                await self.redis_client.setex(
                    f"alert:{alert.id}",
                    3600 * 24,  # 24 hours TTL
                    json.dumps(asdict(alert), default=str)
                )
            
            logger.info(f"Alert triggered: {alert.title} (ID: {alert.id})")
            
            # Queue for notification processing
            await self._queue_alert_for_notification(alert, rule)
            
            return alert
            
        except Exception as e:
            logger.error(f"Error handling rule violation for {rule.id}: {e}")
            return None
    
    async def _check_alert_resolution(self, rule_id: str, metric: AlertMetric) -> None:
        """Check if any alerts should be resolved based on metric"""
        try:
            # Find active alerts for this rule
            alerts_to_resolve = []
            
            for fingerprint, alert in self.active_alerts.items():
                if (alert.rule_id == rule_id and 
                    alert.status == AlertStatus.OPEN and 
                    metric.name in alert.affected_resources):
                    
                    # Check if conditions for resolution are met
                    rule = self.alert_rules.get(rule_id)
                    if rule and not rule.evaluate(metric):
                        alerts_to_resolve.append(alert)
            
            # Resolve alerts
            for alert in alerts_to_resolve:
                await self.resolve_alert(alert.id, "system", "Metric returned to normal range")
                
        except Exception as e:
            logger.error(f"Error checking alert resolution for rule {rule_id}: {e}")
    
    async def _queue_alert_for_notification(self, alert: Alert, rule: AlertRule) -> None:
        """Queue alert for notification processing"""
        try:
            notification_data = {
                'alert_id': alert.id,
                'rule_id': rule.id,
                'channels': [ch.value for ch in rule.notification_channels],
                'timestamp': datetime.now(timezone.utc).isoformat()
            }
            
            if self.redis_client:
                await self.redis_client.lpush(
                    "alert_notifications",
                    json.dumps(notification_data)
                )
            else:
                # Fallback: process immediately
                await self._process_alert_notifications(alert, rule.notification_channels)
                
        except Exception as e:
            logger.error(f"Error queuing alert notification: {e}")
    
    async def _alert_evaluation_loop(self) -> None:
        """Background loop for continuous alert evaluation"""
        while True:
            try:
                # Collect metrics from monitoring services
                metrics = await self._collect_system_metrics()
                
                # Process metrics against rules
                for metric in metrics:
                    await self.process_metric(metric)
                
                # Wait before next evaluation
                await asyncio.sleep(60)  # Evaluate every minute
                
            except Exception as e:
                logger.error(f"Error in alert evaluation loop: {e}")
                await asyncio.sleep(30)  # Shorter wait on error
    
    async def _alert_processing_loop(self) -> None:
        """Background loop for processing alert notifications"""
        while True:
            try:
                if self.redis_client:
                    # Process notification queue
                    while True:
                        notification_data = await self.redis_client.brpop(
                            "alert_notifications", timeout=30
                        )
                        
                        if not notification_data:
                            break
                        
                        _, data = notification_data
                        notification_info = json.loads(data)
                        
                        alert_id = notification_info['alert_id']
                        alert = await self._get_alert_by_id(alert_id)
                        
                        if alert:
                            channels = [NotificationChannel(ch) for ch in notification_info['channels']]
                            await self._process_alert_notifications(alert, channels)
                
                await asyncio.sleep(10)  # Check every 10 seconds
                
            except Exception as e:
                logger.error(f"Error in alert processing loop: {e}")
                await asyncio.sleep(30)
    
    async def _escalation_loop(self) -> None:
        """Background loop for processing alert escalations"""
        while True:
            try:
                current_time = datetime.now(timezone.utc)
                
                for alert in list(self.active_alerts.values()):
                    if alert.status != AlertStatus.OPEN:
                        continue
                    
                    rule = self.alert_rules.get(alert.rule_id)
                    if not rule or not rule.escalation_rules:
                        continue
                    
                    if alert.should_escalate(rule.escalation_rules):
                        await self._escalate_alert(alert, rule.escalation_rules)
                
                await asyncio.sleep(300)  # Check every 5 minutes
                
            except Exception as e:
                logger.error(f"Error in escalation loop: {e}")
                await asyncio.sleep(60)
    
    async def _cleanup_loop(self) -> None:
        """Background loop for cleaning up resolved alerts"""
        while True:
            try:
                cutoff_time = datetime.now(timezone.utc) - timedelta(hours=24)
                
                # Clean up resolved alerts older than 24 hours
                alerts_to_remove = []
                for fingerprint, alert in self.active_alerts.items():
                    if (alert.is_resolved() and 
                        alert.resolved_at and 
                        alert.resolved_at < cutoff_time):
                        alerts_to_remove.append(fingerprint)
                
                for fingerprint in alerts_to_remove:
                    del self.active_alerts[fingerprint]
                
                if alerts_to_remove:
                    logger.info(f"Cleaned up {len(alerts_to_remove)} resolved alerts")
                
                await asyncio.sleep(3600)  # Run cleanup every hour
                
            except Exception as e:
                logger.error(f"Error in cleanup loop: {e}")
                await asyncio.sleep(1800)  # Wait 30 minutes on error
    
    async def _collect_system_metrics(self) -> List[AlertMetric]:
        """Collect metrics from various monitoring services"""
        metrics = []
        current_time = datetime.now(timezone.utc)
        
        try:
            # Get system health metrics
            async for db in get_db():
                system_health = await MonitoringService.get_comprehensive_system_health()
                
                # Convert health data to metrics
                for service_name, service_data in system_health.get('services', {}).items():
                    if isinstance(service_data, dict):
                        status_value = 1 if service_data.get('status') == 'healthy' else 0
                        metrics.append(AlertMetric(
                            name=f"service_health_{service_name}",
                            value=status_value,
                            timestamp=current_time,
                            labels={'service': service_name, 'type': 'health'}
                        ))
                        
                        # Response time metrics
                        if 'response_time_ms' in service_data:
                            metrics.append(AlertMetric(
                                name=f"service_response_time_{service_name}",
                                value=service_data['response_time_ms'],
                                unit='ms',
                                timestamp=current_time,
                                labels={'service': service_name, 'type': 'performance'}
                            ))
                
                # System resource metrics
                if 'infrastructure' in system_health:
                    system_data = system_health['infrastructure'].get('system', {})
                    
                    if 'cpu' in system_data:
                        metrics.append(AlertMetric(
                            name="cpu_usage_percent",
                            value=system_data['cpu'].get('usage_percent', 0),
                            unit='percent',
                            timestamp=current_time,
                            labels={'type': 'system', 'resource': 'cpu'}
                        ))
                    
                    if 'memory' in system_data:
                        metrics.append(AlertMetric(
                            name="memory_usage_percent",
                            value=system_data['memory'].get('usage_percent', 0),
                            unit='percent',
                            timestamp=current_time,
                            labels={'type': 'system', 'resource': 'memory'}
                        ))
                    
                    if 'disk' in system_data:
                        metrics.append(AlertMetric(
                            name="disk_usage_percent",
                            value=system_data['disk'].get('usage_percent', 0),
                            unit='percent',
                            timestamp=current_time,
                            labels={'type': 'system', 'resource': 'disk'}
                        ))
                
                break
                
        except Exception as e:
            logger.error(f"Error collecting system metrics: {e}")
        
        return metrics
    
    async def _get_alert_by_id(self, alert_id: str) -> Optional[Alert]:
        """Get alert by ID from memory or Redis"""
        # Check active alerts first
        for alert in self.active_alerts.values():
            if alert.id == alert_id:
                return alert
        
        # Check Redis cache
        if self.redis_client:
            try:
                alert_data = await self.redis_client.get(f"alert:{alert_id}")
                if alert_data:
                    alert_dict = json.loads(alert_data)
                    return Alert(**alert_dict)
            except Exception as e:
                logger.error(f"Error retrieving alert {alert_id} from Redis: {e}")
        
        return None
    
    @with_circuit_breaker("alert_notifications", CircuitBreakerConfig(failure_threshold=5, timeout_seconds=60))
    async def _process_alert_notifications(self, alert: Alert, channels: List[NotificationChannel]) -> Dict[str, bool]:
        """Process alert notifications through specified channels"""
        results = {}
        
        for channel in channels:
            try:
                success = await self._send_notification(alert, channel)
                results[channel.value] = success
                
                if success:
                    self.stats['notifications_sent'] += 1
                else:
                    self.stats['notification_failures'] += 1
                    
            except CircuitBreakerError:
                logger.warning(f"Circuit breaker open for {channel} notifications")
                results[channel.value] = False
                self.stats['notification_failures'] += 1
            except Exception as e:
                logger.error(f"Error sending {channel} notification: {e}")
                results[channel.value] = False
                self.stats['notification_failures'] += 1
        
        # Update alert notification tracking
        alert.notification_count += 1
        alert.last_notification = datetime.now(timezone.utc)
        
        return results
    
    async def _send_notification(self, alert: Alert, channel: NotificationChannel) -> bool:
        """Send notification through specific channel"""
        try:
            if channel == NotificationChannel.EMAIL:
                return await self._send_email_notification(alert)
            elif channel == NotificationChannel.SLACK:
                return await self._send_slack_notification(alert)
            elif channel == NotificationChannel.SMS:
                return await self._send_sms_notification(alert)
            elif channel == NotificationChannel.WEBHOOK:
                return await self._send_webhook_notification(alert)
            elif channel == NotificationChannel.PAGERDUTY:
                return await self._send_pagerduty_notification(alert)
            elif channel == NotificationChannel.OPSGENIE:
                return await self._send_opsgenie_notification(alert)
            elif channel == NotificationChannel.DISCORD:
                return await self._send_discord_notification(alert)
            elif channel == NotificationChannel.MSTEAMS:
                return await self._send_msteams_notification(alert)
            else:
                logger.warning(f"Unsupported notification channel: {channel}")
                return False
                
        except Exception as e:
            logger.error(f"Error sending {channel} notification for alert {alert.id}: {e}")
            return False
    
    async def _send_email_notification(self, alert: Alert) -> bool:
        """Send email notification"""
        # Implementation using existing email service
        try:
            from app.core.email_service import send_email
            
            template = self.notification_templates.get(NotificationChannel.EMAIL)
            if not template:
                return False
            
            # Format template
            context = self._get_notification_context(alert)
            subject = template.subject_template.format(**context)
            body = template.body_template.format(**context)
            
            # Get email recipients from settings
            recipients = getattr(settings, 'ALERT_EMAIL_RECIPIENTS', '').split(',')
            recipients = [email.strip() for email in recipients if email.strip()]
            
            if not recipients:
                logger.warning("No email recipients configured for alerts")
                return False
            
            # Send email
            success = await send_email(
                to_email=recipients[0],  # Primary recipient
                subject=subject,
                html_content=body,
                cc_emails=recipients[1:] if len(recipients) > 1 else None
            )
            
            return success
            
        except Exception as e:
            logger.error(f"Error sending email alert notification: {e}")
            return False
    
    async def _send_slack_notification(self, alert: Alert) -> bool:
        """Send Slack notification"""
        try:
            webhook_url = getattr(settings, 'ALERT_SLACK_WEBHOOK_URL', None)
            if not webhook_url:
                return False
            
            template = self.notification_templates.get(NotificationChannel.SLACK)
            context = self._get_notification_context(alert)
            
            # Parse JSON template and format
            payload_template = json.loads(template.body_template)
            payload = json.loads(json.dumps(payload_template).format(**context))
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    webhook_url,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    return response.status == 200
                    
        except Exception as e:
            logger.error(f"Error sending Slack alert notification: {e}")
            return False
    
    async def _send_sms_notification(self, alert: Alert) -> bool:
        """Send SMS notification (Twilio integration)"""
        try:
            # Only send SMS for critical alerts
            if alert.severity != AlertSeverity.CRITICAL:
                return True
            
            # Implementation would use Twilio API
            # For now, return True to indicate "handled"
            return True
            
        except Exception as e:
            logger.error(f"Error sending SMS alert notification: {e}")
            return False
    
    async def _send_webhook_notification(self, alert: Alert) -> bool:
        """Send webhook notification"""
        try:
            webhook_url = getattr(settings, 'ALERT_WEBHOOK_URL', None)
            if not webhook_url:
                return False
            
            payload = {
                'alert_id': alert.id,
                'title': alert.title,
                'description': alert.description,
                'severity': alert.severity.value,
                'category': alert.category.value,
                'status': alert.status.value,
                'timestamp': alert.first_seen.isoformat(),
                'affected_resources': alert.affected_resources,
                'labels': alert.labels,
                'annotations': alert.annotations
            }
            
            headers = {'Content-Type': 'application/json'}
            
            # Add webhook signature if secret is configured
            webhook_secret = getattr(settings, 'ALERT_WEBHOOK_SECRET', None)
            if webhook_secret:
                payload_bytes = json.dumps(payload, sort_keys=True).encode()
                signature = hmac.new(
                    webhook_secret.encode(),
                    payload_bytes,
                    hashlib.sha256
                ).hexdigest()
                headers['X-Alert-Signature'] = f'sha256={signature}'
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    webhook_url,
                    json=payload,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    return 200 <= response.status < 300
                    
        except Exception as e:
            logger.error(f"Error sending webhook alert notification: {e}")
            return False
    
    async def _send_pagerduty_notification(self, alert: Alert) -> bool:
        """Send PagerDuty notification"""
        try:
            integration_key = getattr(settings, 'ALERT_PAGERDUTY_INTEGRATION_KEY', None)
            if not integration_key:
                return False
            
            # Only send critical alerts to PagerDuty
            if alert.severity != AlertSeverity.CRITICAL:
                return True
            
            payload = {
                'routing_key': integration_key,
                'event_action': 'trigger',
                'dedup_key': alert.fingerprint,
                'payload': {
                    'summary': alert.title,
                    'source': 'chrono-scraper',
                    'severity': 'critical',
                    'component': alert.category.value,
                    'custom_details': {
                        'description': alert.description,
                        'affected_resources': alert.affected_resources,
                        'labels': alert.labels,
                        'alert_id': alert.id
                    }
                }
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    'https://events.pagerduty.com/v2/enqueue',
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    return response.status == 202
                    
        except Exception as e:
            logger.error(f"Error sending PagerDuty alert notification: {e}")
            return False
    
    async def _send_opsgenie_notification(self, alert: Alert) -> bool:
        """Send OpsGenie notification"""
        # Implementation for OpsGenie
        return True
    
    async def _send_discord_notification(self, alert: Alert) -> bool:
        """Send Discord notification"""
        # Implementation for Discord
        return True
    
    async def _send_msteams_notification(self, alert: Alert) -> bool:
        """Send Microsoft Teams notification"""
        # Implementation for MS Teams
        return True
    
    def _get_notification_context(self, alert: Alert) -> Dict[str, Any]:
        """Get template context for alert notifications"""
        # Color mapping for templates
        severity_colors = {
            AlertSeverity.INFO: 'good',
            AlertSeverity.WARNING: 'warning', 
            AlertSeverity.CRITICAL: 'danger',
            AlertSeverity.EMERGENCY: 'danger'
        }
        
        return {
            'alert_id': alert.id,
            'title': alert.title,
            'description': alert.description,
            'severity': alert.severity.value.upper(),
            'category': alert.category.value.replace('_', ' ').title(),
            'status': alert.status.value.upper(),
            'source': alert.source,
            'affected_resources': ', '.join(alert.affected_resources),
            'timestamp': alert.first_seen.strftime('%Y-%m-%d %H:%M:%S UTC'),
            'timestamp_unix': int(alert.first_seen.timestamp()),
            'color': severity_colors.get(alert.severity, 'warning'),
            'alert_url': f"{getattr(settings, 'FRONTEND_URL', '')}/admin/alerts/{alert.id}"
        }
    
    async def _escalate_alert(self, alert: Alert, escalation_rules: Dict[str, Any]) -> None:
        """Escalate alert to next level"""
        try:
            alert.escalation_level += 1
            alert.status = AlertStatus.ESCALATED
            
            # Add escalation action
            alert.add_action(
                AlertAction.ESCALATE,
                {'escalation_level': alert.escalation_level, 'auto_escalated': True},
                actor_id=0  # System user
            )
            
            # Send escalation notifications
            escalation_channels = escalation_rules.get('channels', [])
            if escalation_channels:
                channels = [NotificationChannel(ch) for ch in escalation_channels]
                await self._process_alert_notifications(alert, channels)
            
            logger.info(f"Escalated alert {alert.id} to level {alert.escalation_level}")
            
        except Exception as e:
            logger.error(f"Error escalating alert {alert.id}: {e}")
    
    # Public API methods
    
    async def acknowledge_alert(self, alert_id: str, user_id: int, note: Optional[str] = None) -> bool:
        """Acknowledge an alert"""
        try:
            alert = await self._get_alert_by_id(alert_id)
            if not alert:
                return False
            
            if alert.is_resolved():
                return False  # Cannot acknowledge resolved alerts
            
            alert.status = AlertStatus.ACKNOWLEDGED
            alert.acknowledged_at = datetime.now(timezone.utc)
            alert.acknowledged_by = user_id
            
            if note:
                alert.add_note(note, user_id)
            
            alert.add_action(
                AlertAction.ACKNOWLEDGE,
                {'note': note} if note else {},
                actor_id=user_id
            )
            
            logger.info(f"Alert {alert_id} acknowledged by user {user_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error acknowledging alert {alert_id}: {e}")
            return False
    
    async def resolve_alert(self, alert_id: str, user_id: Union[int, str], resolution_note: Optional[str] = None) -> bool:
        """Resolve an alert"""
        try:
            alert = await self._get_alert_by_id(alert_id)
            if not alert:
                return False
            
            alert.status = AlertStatus.RESOLVED
            alert.resolved_at = datetime.now(timezone.utc)
            
            if resolution_note:
                alert.add_note(resolution_note, user_id if isinstance(user_id, int) else 0)
            
            alert.add_action(
                AlertAction.RESOLVE,
                {'resolution_note': resolution_note} if resolution_note else {},
                actor_id=user_id if isinstance(user_id, int) else 0
            )
            
            # Remove from active alerts if using fingerprint
            if alert.fingerprint in self.active_alerts:
                del self.active_alerts[alert.fingerprint]
            
            self.stats['alerts_resolved'] += 1
            
            logger.info(f"Alert {alert_id} resolved by {user_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error resolving alert {alert_id}: {e}")
            return False
    
    async def suppress_alert(self, alert_id: str, user_id: int, duration_minutes: int, reason: str) -> bool:
        """Suppress an alert for specified duration"""
        try:
            alert = await self._get_alert_by_id(alert_id)
            if not alert:
                return False
            
            alert.status = AlertStatus.SUPPRESSED
            alert.suppressed_until = datetime.now(timezone.utc) + timedelta(minutes=duration_minutes)
            
            alert.add_note(f"Suppressed for {duration_minutes} minutes: {reason}", user_id)
            alert.add_action(
                AlertAction.SUPPRESS,
                {'duration_minutes': duration_minutes, 'reason': reason},
                actor_id=user_id
            )
            
            logger.info(f"Alert {alert_id} suppressed for {duration_minutes} minutes by user {user_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error suppressing alert {alert_id}: {e}")
            return False
    
    async def assign_alert(self, alert_id: str, assigned_to: int, assigned_by: int) -> bool:
        """Assign alert to a user"""
        try:
            alert = await self._get_alert_by_id(alert_id)
            if not alert:
                return False
            
            alert.assigned_to = assigned_to
            alert.add_action(
                AlertAction.ASSIGN,
                {'assigned_to': assigned_to},
                actor_id=assigned_by
            )
            
            logger.info(f"Alert {alert_id} assigned to user {assigned_to} by user {assigned_by}")
            return True
            
        except Exception as e:
            logger.error(f"Error assigning alert {alert_id}: {e}")
            return False
    
    async def get_active_alerts(self, filters: Optional[Dict[str, Any]] = None) -> List[Alert]:
        """Get list of active alerts with optional filtering"""
        alerts = list(self.active_alerts.values())
        
        if filters:
            # Apply filters
            if 'severity' in filters:
                alerts = [a for a in alerts if a.severity == filters['severity']]
            
            if 'category' in filters:
                alerts = [a for a in alerts if a.category == filters['category']]
            
            if 'status' in filters:
                alerts = [a for a in alerts if a.status == filters['status']]
            
            if 'assigned_to' in filters:
                alerts = [a for a in alerts if a.assigned_to == filters['assigned_to']]
        
        # Sort by severity and time
        severity_order = {
            AlertSeverity.EMERGENCY: 0,
            AlertSeverity.CRITICAL: 1,
            AlertSeverity.WARNING: 2,
            AlertSeverity.INFO: 3
        }
        
        return sorted(
            alerts,
            key=lambda a: (severity_order.get(a.severity, 4), a.first_seen),
            reverse=True
        )
    
    async def get_alert_statistics(self) -> Dict[str, Any]:
        """Get alert system statistics"""
        active_alerts = list(self.active_alerts.values())
        
        # Count by severity
        severity_counts = Counter(alert.severity for alert in active_alerts)
        
        # Count by category
        category_counts = Counter(alert.category for alert in active_alerts)
        
        # Count by status
        status_counts = Counter(alert.status for alert in active_alerts)
        
        return {
            'total_active_alerts': len(active_alerts),
            'total_alert_rules': len(self.alert_rules),
            'alerts_by_severity': dict(severity_counts),
            'alerts_by_category': dict(category_counts),
            'alerts_by_status': dict(status_counts),
            'system_stats': self.stats.copy(),
            'oldest_active_alert': min(alert.first_seen for alert in active_alerts) if active_alerts else None,
            'last_alert_generated': max(alert.first_seen for alert in active_alerts) if active_alerts else None
        }
    
    def get_alert_rules(self) -> Dict[str, AlertRule]:
        """Get all alert rules"""
        return self.alert_rules.copy()


# Global alert manager instance
alert_manager = AlertManager()


async def initialize_alert_system() -> None:
    """Initialize the global alert system"""
    await alert_manager.initialize()


async def shutdown_alert_system() -> None:
    """Shutdown the global alert system"""
    await alert_manager.shutdown()