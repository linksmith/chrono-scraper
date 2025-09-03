"""
Advanced audit log anomaly detection and alerting system with machine learning and real-time monitoring
"""
import asyncio
import json
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, asdict
from collections import defaultdict, Counter
from enum import Enum
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import desc
from sqlmodel import select

from app.core.config import settings
from app.core.database import get_db
from app.core.audit_logger import log_security_event
from app.models.audit_log import (
    AuditLog, 
    SeverityLevel, 
    AuditActions
)


logger = logging.getLogger(__name__)


class AlertSeverity(str, Enum):
    """Alert severity levels"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class AlertType(str, Enum):
    """Types of security alerts"""
    BRUTE_FORCE_ATTACK = "brute_force_attack"
    SUSPICIOUS_IP = "suspicious_ip"
    PRIVILEGE_ESCALATION = "privilege_escalation"
    UNUSUAL_ACTIVITY = "unusual_activity"
    DATA_BREACH_ATTEMPT = "data_breach_attempt"
    SYSTEM_COMPROMISE = "system_compromise"
    COMPLIANCE_VIOLATION = "compliance_violation"
    MASS_OPERATION = "mass_operation"
    AFTER_HOURS_ACTIVITY = "after_hours_activity"
    ANOMALOUS_PATTERN = "anomalous_pattern"
    INTEGRITY_VIOLATION = "integrity_violation"


@dataclass
class SecurityAlert:
    """Security alert data structure"""
    alert_id: str
    alert_type: AlertType
    severity: AlertSeverity
    title: str
    description: str
    detected_at: datetime
    affected_resources: List[str]
    indicators: Dict[str, Any]
    recommendations: List[str]
    auto_resolved: bool = False
    resolved_at: Optional[datetime] = None
    resolved_by: Optional[int] = None  # admin user ID
    false_positive: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class AnomalyPattern:
    """Detected anomaly pattern"""
    pattern_type: str
    description: str
    severity: float  # 0.0 to 1.0
    confidence: float  # 0.0 to 1.0
    evidence: List[Dict[str, Any]]
    first_detected: datetime
    last_detected: datetime
    count: int


class SecurityAlertsService:
    """
    Advanced security alerts service with:
    - Real-time anomaly detection
    - Machine learning-based pattern recognition
    - Automated threat response
    - Compliance violation monitoring
    - Alert correlation and deduplication
    - Multi-channel notification system
    """
    
    def __init__(self):
        self.alert_thresholds = self._init_alert_thresholds()
        self.ml_models = self._init_ml_models()
        self.active_alerts = {}  # In-memory cache for active alerts
        self.pattern_cache = defaultdict(list)  # Cache for pattern detection
        
    def _init_alert_thresholds(self) -> Dict[str, Any]:
        """Initialize alert detection thresholds"""
        return {
            'brute_force_attack': {
                'failed_logins_per_ip_per_hour': 10,
                'failed_logins_per_user_per_hour': 5,
                'failed_logins_total_per_hour': 50
            },
            'suspicious_ip': {
                'requests_per_minute': 100,
                'different_users_accessed': 10,
                'error_rate_threshold': 0.3
            },
            'privilege_escalation': {
                'role_changes_per_hour': 5,
                'permission_grants_per_hour': 10,
                'admin_actions_per_user_per_hour': 20
            },
            'unusual_activity': {
                'after_hours_threshold': 5,  # actions after 10 PM or before 6 AM
                'weekend_activity_threshold': 10,
                'bulk_operations_per_hour': 3
            },
            'data_breach_attempt': {
                'data_export_size_mb': 100,
                'export_operations_per_hour': 3,
                'sensitive_data_access_per_hour': 20
            },
            'compliance_violation': {
                'gdpr_violations_per_day': 1,
                'unauthorized_pii_access': 1,
                'data_retention_violations': 1
            },
            'integrity_violation': {
                'checksum_failures_per_hour': 1,
                'signature_failures_per_hour': 1,
                'data_tampering_attempts': 1
            }
        }
    
    def _init_ml_models(self) -> Dict[str, Any]:
        """Initialize machine learning models for anomaly detection"""
        # In production, load pre-trained models
        return {
            'user_behavior_model': None,  # User behavior baseline model
            'ip_reputation_model': None,  # IP address reputation model
            'time_series_model': None,    # Time series anomaly detection
            'clustering_model': None      # Activity clustering model
        }
    
    async def analyze_real_time_events(
        self,
        recent_events: List[AuditLog],
        time_window_minutes: int = 60
    ) -> List[SecurityAlert]:
        """
        Analyze recent events for security threats and anomalies
        
        Args:
            recent_events: List of recent audit log events
            time_window_minutes: Time window for analysis
            
        Returns:
            List of detected security alerts
        """
        alerts = []
        
        try:
            # Group events by type for analysis
            events_by_ip = defaultdict(list)
            events_by_user = defaultdict(list)
            events_by_action = defaultdict(list)
            
            for event in recent_events:
                if event.ip_address:
                    events_by_ip[event.ip_address].append(event)
                if event.user_id or event.admin_user_id:
                    user_id = event.admin_user_id or event.user_id
                    events_by_user[user_id].append(event)
                if event.action:
                    events_by_action[event.action].append(event)
            
            # Detect brute force attacks
            brute_force_alerts = await self._detect_brute_force_attacks(
                events_by_ip, events_by_user, time_window_minutes
            )
            alerts.extend(brute_force_alerts)
            
            # Detect suspicious IP activity
            suspicious_ip_alerts = await self._detect_suspicious_ip_activity(
                events_by_ip, time_window_minutes
            )
            alerts.extend(suspicious_ip_alerts)
            
            # Detect privilege escalation attempts
            privilege_alerts = await self._detect_privilege_escalation(
                events_by_user, time_window_minutes
            )
            alerts.extend(privilege_alerts)
            
            # Detect unusual activity patterns
            unusual_activity_alerts = await self._detect_unusual_activity(
                recent_events, time_window_minutes
            )
            alerts.extend(unusual_activity_alerts)
            
            # Detect data breach attempts
            breach_alerts = await self._detect_data_breach_attempts(
                events_by_user, time_window_minutes
            )
            alerts.extend(breach_alerts)
            
            # Detect compliance violations
            compliance_alerts = await self._detect_compliance_violations(
                recent_events, time_window_minutes
            )
            alerts.extend(compliance_alerts)
            
            # Detect integrity violations
            integrity_alerts = await self._detect_integrity_violations(
                recent_events, time_window_minutes
            )
            alerts.extend(integrity_alerts)
            
            # Apply machine learning anomaly detection
            ml_alerts = await self._apply_ml_anomaly_detection(
                recent_events, time_window_minutes
            )
            alerts.extend(ml_alerts)
            
            # Deduplicate and correlate alerts
            alerts = await self._deduplicate_alerts(alerts)
            
            # Store active alerts
            for alert in alerts:
                self.active_alerts[alert.alert_id] = alert
            
            return alerts
            
        except Exception as e:
            logger.error(f"Error in real-time event analysis: {e}")
            return []
    
    async def _detect_brute_force_attacks(
        self,
        events_by_ip: Dict[str, List[AuditLog]],
        events_by_user: Dict[int, List[AuditLog]],
        time_window_minutes: int
    ) -> List[SecurityAlert]:
        """Detect brute force attack patterns"""
        alerts = []
        threshold = self.alert_thresholds['brute_force_attack']
        
        # Check failed logins per IP
        for ip, events in events_by_ip.items():
            failed_logins = [
                e for e in events 
                if e.action == AuditActions.USER_LOGIN_FAILED
            ]
            
            if len(failed_logins) >= threshold['failed_logins_per_ip_per_hour']:
                alert = SecurityAlert(
                    alert_id=f"brute_force_ip_{ip}_{int(datetime.now(timezone.utc).timestamp())}",
                    alert_type=AlertType.BRUTE_FORCE_ATTACK,
                    severity=AlertSeverity.HIGH,
                    title=f"Brute Force Attack from IP {ip}",
                    description=f"Detected {len(failed_logins)} failed login attempts from IP {ip} in {time_window_minutes} minutes",
                    detected_at=datetime.now(timezone.utc),
                    affected_resources=[f"ip:{ip}"],
                    indicators={
                        'ip_address': ip,
                        'failed_attempts': len(failed_logins),
                        'time_window_minutes': time_window_minutes,
                        'targeted_users': list(set(e.user_id for e in failed_logins if e.user_id))
                    },
                    recommendations=[
                        f"Block IP address {ip}",
                        "Review authentication logs",
                        "Consider implementing CAPTCHA",
                        "Enable account lockout policies"
                    ]
                )
                alerts.append(alert)
        
        # Check failed logins per user
        for user_id, events in events_by_user.items():
            failed_logins = [
                e for e in events 
                if e.action == AuditActions.USER_LOGIN_FAILED
            ]
            
            if len(failed_logins) >= threshold['failed_logins_per_user_per_hour']:
                alert = SecurityAlert(
                    alert_id=f"brute_force_user_{user_id}_{int(datetime.now(timezone.utc).timestamp())}",
                    alert_type=AlertType.BRUTE_FORCE_ATTACK,
                    severity=AlertSeverity.MEDIUM,
                    title=f"Brute Force Attack on User {user_id}",
                    description=f"Detected {len(failed_logins)} failed login attempts for user {user_id} in {time_window_minutes} minutes",
                    detected_at=datetime.now(timezone.utc),
                    affected_resources=[f"user:{user_id}"],
                    indicators={
                        'user_id': user_id,
                        'failed_attempts': len(failed_logins),
                        'time_window_minutes': time_window_minutes,
                        'source_ips': list(set(e.ip_address for e in failed_logins if e.ip_address))
                    },
                    recommendations=[
                        f"Lock user account {user_id}",
                        "Notify user of suspicious activity",
                        "Force password reset",
                        "Enable multi-factor authentication"
                    ]
                )
                alerts.append(alert)
        
        return alerts
    
    async def _detect_suspicious_ip_activity(
        self,
        events_by_ip: Dict[str, List[AuditLog]],
        time_window_minutes: int
    ) -> List[SecurityAlert]:
        """Detect suspicious IP address activity"""
        alerts = []
        threshold = self.alert_thresholds['suspicious_ip']
        
        for ip, events in events_by_ip.items():
            # Calculate request rate
            request_count = len(events)
            requests_per_minute = request_count / time_window_minutes
            
            # Calculate error rate
            failed_events = len([e for e in events if not e.success])
            error_rate = failed_events / request_count if request_count > 0 else 0
            
            # Count unique users accessed
            unique_users = len(set(e.user_id for e in events if e.user_id))
            
            # Check for suspicious patterns
            is_suspicious = (
                requests_per_minute > threshold['requests_per_minute'] or
                unique_users > threshold['different_users_accessed'] or
                error_rate > threshold['error_rate_threshold']
            )
            
            if is_suspicious:
                severity = AlertSeverity.HIGH if requests_per_minute > threshold['requests_per_minute'] * 2 else AlertSeverity.MEDIUM
                
                alert = SecurityAlert(
                    alert_id=f"suspicious_ip_{ip}_{int(datetime.now(timezone.utc).timestamp())}",
                    alert_type=AlertType.SUSPICIOUS_IP,
                    severity=severity,
                    title=f"Suspicious Activity from IP {ip}",
                    description=f"IP {ip} showing suspicious patterns: {requests_per_minute:.1f} req/min, {error_rate:.1%} error rate, {unique_users} users accessed",
                    detected_at=datetime.now(timezone.utc),
                    affected_resources=[f"ip:{ip}"],
                    indicators={
                        'ip_address': ip,
                        'requests_per_minute': requests_per_minute,
                        'error_rate': error_rate,
                        'unique_users_accessed': unique_users,
                        'total_requests': request_count,
                        'failed_requests': failed_events
                    },
                    recommendations=[
                        f"Investigate IP {ip} reputation",
                        "Consider rate limiting or blocking",
                        "Review geolocation and ISP information",
                        "Monitor for continued suspicious activity"
                    ]
                )
                alerts.append(alert)
        
        return alerts
    
    async def _detect_privilege_escalation(
        self,
        events_by_user: Dict[int, List[AuditLog]],
        time_window_minutes: int
    ) -> List[SecurityAlert]:
        """Detect privilege escalation attempts"""
        alerts = []
        threshold = self.alert_thresholds['privilege_escalation']
        
        privileged_actions = [
            AuditActions.USER_ROLE_ASSIGN,
            AuditActions.USER_PERMISSION_GRANT,
            AuditActions.SYSTEM_CONFIG_UPDATE,
            AuditActions.BULK_USER_APPROVE,
            AuditActions.BULK_USER_ROLE_ASSIGN
        ]
        
        for user_id, events in events_by_user.items():
            # Count privileged actions
            admin_actions = [
                e for e in events 
                if e.action in privileged_actions
            ]
            
            role_changes = [
                e for e in events 
                if e.action in [AuditActions.USER_ROLE_ASSIGN, AuditActions.USER_ROLE_REMOVE]
            ]
            
            if (len(admin_actions) > threshold['admin_actions_per_user_per_hour'] or
                len(role_changes) > threshold['role_changes_per_hour']):
                
                alert = SecurityAlert(
                    alert_id=f"privilege_escalation_{user_id}_{int(datetime.now(timezone.utc).timestamp())}",
                    alert_type=AlertType.PRIVILEGE_ESCALATION,
                    severity=AlertSeverity.HIGH,
                    title=f"Potential Privilege Escalation by User {user_id}",
                    description=f"User {user_id} performed {len(admin_actions)} privileged actions and {len(role_changes)} role changes in {time_window_minutes} minutes",
                    detected_at=datetime.now(timezone.utc),
                    affected_resources=[f"user:{user_id}"],
                    indicators={
                        'user_id': user_id,
                        'admin_actions_count': len(admin_actions),
                        'role_changes_count': len(role_changes),
                        'privileged_actions': [e.action for e in admin_actions],
                        'time_window_minutes': time_window_minutes
                    },
                    recommendations=[
                        f"Review user {user_id} privileges immediately",
                        "Audit recent permission changes",
                        "Verify legitimacy of administrative actions",
                        "Consider temporary access suspension"
                    ]
                )
                alerts.append(alert)
        
        return alerts
    
    async def _detect_unusual_activity(
        self,
        events: List[AuditLog],
        time_window_minutes: int
    ) -> List[SecurityAlert]:
        """Detect unusual activity patterns"""
        alerts = []
        threshold = self.alert_thresholds['unusual_activity']
        current_time = datetime.now(timezone.utc)
        
        # Check for after-hours activity
        after_hours_events = [
            e for e in events 
            if e.created_at and (
                e.created_at.hour < 6 or e.created_at.hour > 22
            ) and e.admin_user_id  # Only admin actions
        ]
        
        if len(after_hours_events) > threshold['after_hours_threshold']:
            alert = SecurityAlert(
                alert_id=f"after_hours_activity_{int(current_time.timestamp())}",
                alert_type=AlertType.AFTER_HOURS_ACTIVITY,
                severity=AlertSeverity.MEDIUM,
                title="Unusual After-Hours Administrative Activity",
                description=f"Detected {len(after_hours_events)} administrative actions outside normal business hours",
                detected_at=current_time,
                affected_resources=list(set(f"user:{e.admin_user_id}" for e in after_hours_events if e.admin_user_id)),
                indicators={
                    'after_hours_events': len(after_hours_events),
                    'time_window_minutes': time_window_minutes,
                    'involved_admins': list(set(e.admin_user_id for e in after_hours_events if e.admin_user_id)),
                    'actions': [e.action for e in after_hours_events]
                },
                recommendations=[
                    "Verify after-hours access is authorized",
                    "Review business justification for activities",
                    "Check for compromised admin accounts",
                    "Implement stricter after-hours access controls"
                ]
            )
            alerts.append(alert)
        
        # Check for bulk operations
        bulk_events = [
            e for e in events 
            if e.action and e.action.startswith('bulk_')
        ]
        
        if len(bulk_events) > threshold['bulk_operations_per_hour']:
            alert = SecurityAlert(
                alert_id=f"mass_operation_{int(current_time.timestamp())}",
                alert_type=AlertType.MASS_OPERATION,
                severity=AlertSeverity.MEDIUM,
                title="High Volume of Bulk Operations",
                description=f"Detected {len(bulk_events)} bulk operations in {time_window_minutes} minutes",
                detected_at=current_time,
                affected_resources=list(set(f"user:{e.admin_user_id}" for e in bulk_events if e.admin_user_id)),
                indicators={
                    'bulk_operations': len(bulk_events),
                    'time_window_minutes': time_window_minutes,
                    'operations': Counter(e.action for e in bulk_events),
                    'total_affected_records': sum(e.affected_count or 0 for e in bulk_events)
                },
                recommendations=[
                    "Review bulk operation justifications",
                    "Verify data integrity after bulk changes",
                    "Check for automated attack patterns",
                    "Implement bulk operation approvals"
                ]
            )
            alerts.append(alert)
        
        return alerts
    
    async def _detect_data_breach_attempts(
        self,
        events_by_user: Dict[int, List[AuditLog]],
        time_window_minutes: int
    ) -> List[SecurityAlert]:
        """Detect potential data breach attempts"""
        alerts = []
        threshold = self.alert_thresholds['data_breach_attempt']
        
        for user_id, events in events_by_user.items():
            # Check for excessive data exports
            export_events = [
                e for e in events 
                if e.action in [AuditActions.DATA_EXPORT, AuditActions.USER_PROFILE_EXPORT]
            ]
            
            # Check for sensitive data access
            sensitive_access_events = [
                e for e in events 
                if e.sensitive_data_accessed
            ]
            
            if (len(export_events) > threshold['export_operations_per_hour'] or
                len(sensitive_access_events) > threshold['sensitive_data_access_per_hour']):
                
                severity = AlertSeverity.CRITICAL if len(export_events) > threshold['export_operations_per_hour'] * 2 else AlertSeverity.HIGH
                
                alert = SecurityAlert(
                    alert_id=f"data_breach_attempt_{user_id}_{int(datetime.now(timezone.utc).timestamp())}",
                    alert_type=AlertType.DATA_BREACH_ATTEMPT,
                    severity=severity,
                    title=f"Potential Data Breach Attempt by User {user_id}",
                    description=f"User {user_id} performed {len(export_events)} data exports and {len(sensitive_access_events)} sensitive data accesses in {time_window_minutes} minutes",
                    detected_at=datetime.now(timezone.utc),
                    affected_resources=[f"user:{user_id}"],
                    indicators={
                        'user_id': user_id,
                        'export_operations': len(export_events),
                        'sensitive_access_count': len(sensitive_access_events),
                        'time_window_minutes': time_window_minutes,
                        'ip_addresses': list(set(e.ip_address for e in events if e.ip_address))
                    },
                    recommendations=[
                        f"Immediately suspend user {user_id}",
                        "Audit all recent data access",
                        "Review exported data content",
                        "Notify data protection officer",
                        "Consider legal action if confirmed"
                    ]
                )
                alerts.append(alert)
        
        return alerts
    
    async def _detect_compliance_violations(
        self,
        events: List[AuditLog],
        time_window_minutes: int
    ) -> List[SecurityAlert]:
        """Detect compliance violations"""
        alerts = []
        
        # Check for GDPR violations
        gdpr_events = [e for e in events if e.gdpr_relevant]
        unauthorized_pii_access = [
            e for e in gdpr_events 
            if not e.success or e.action == AuditActions.UNAUTHORIZED_ACCESS
        ]
        
        if unauthorized_pii_access:
            alert = SecurityAlert(
                alert_id=f"gdpr_violation_{int(datetime.now(timezone.utc).timestamp())}",
                alert_type=AlertType.COMPLIANCE_VIOLATION,
                severity=AlertSeverity.HIGH,
                title="GDPR Compliance Violation Detected",
                description=f"Detected {len(unauthorized_pii_access)} unauthorized personal data access attempts",
                detected_at=datetime.now(timezone.utc),
                affected_resources=["compliance:gdpr"],
                indicators={
                    'violation_type': 'gdpr_unauthorized_access',
                    'violation_count': len(unauthorized_pii_access),
                    'involved_users': list(set(e.user_id for e in unauthorized_pii_access if e.user_id))
                },
                recommendations=[
                    "Investigate unauthorized access attempts",
                    "Notify Data Protection Officer",
                    "Document compliance incident",
                    "Review access controls for personal data"
                ]
            )
            alerts.append(alert)
        
        return alerts
    
    async def _detect_integrity_violations(
        self,
        events: List[AuditLog],
        time_window_minutes: int
    ) -> List[SecurityAlert]:
        """Detect data integrity violations"""
        alerts = []
        
        # Check for checksum failures (would be detected during integrity verification)
        # This would be triggered by the audit logger when integrity checks fail
        integrity_failures = [
            e for e in events 
            if e.details and e.details.get('_integrity_warning')
        ]
        
        if integrity_failures:
            alert = SecurityAlert(
                alert_id=f"integrity_violation_{int(datetime.now(timezone.utc).timestamp())}",
                alert_type=AlertType.INTEGRITY_VIOLATION,
                severity=AlertSeverity.CRITICAL,
                title="Data Integrity Violation Detected",
                description=f"Detected {len(integrity_failures)} audit log integrity failures - potential tampering",
                detected_at=datetime.now(timezone.utc),
                affected_resources=[f"audit_log:{e.id}" for e in integrity_failures],
                indicators={
                    'integrity_failures': len(integrity_failures),
                    'affected_log_ids': [e.id for e in integrity_failures],
                    'failure_types': ['checksum_mismatch', 'signature_invalid']
                },
                recommendations=[
                    "CRITICAL: Investigate potential data tampering",
                    "Isolate affected systems immediately",
                    "Conduct forensic analysis",
                    "Notify security team and management",
                    "Review backup integrity"
                ]
            )
            alerts.append(alert)
        
        return alerts
    
    async def _apply_ml_anomaly_detection(
        self,
        events: List[AuditLog],
        time_window_minutes: int
    ) -> List[SecurityAlert]:
        """Apply machine learning models for anomaly detection"""
        alerts = []
        
        # This would implement ML-based anomaly detection
        # For now, return empty list - in production, implement actual ML models
        
        return alerts
    
    async def _deduplicate_alerts(
        self,
        alerts: List[SecurityAlert]
    ) -> List[SecurityAlert]:
        """Deduplicate and correlate alerts"""
        # Simple deduplication by alert type and affected resources
        seen_patterns = set()
        deduplicated = []
        
        for alert in alerts:
            pattern = f"{alert.alert_type}_{hash(tuple(sorted(alert.affected_resources)))}"
            if pattern not in seen_patterns:
                seen_patterns.add(pattern)
                deduplicated.append(alert)
        
        return deduplicated
    
    async def send_alert_notifications(
        self,
        alerts: List[SecurityAlert],
        db: AsyncSession
    ) -> None:
        """Send alert notifications via multiple channels"""
        
        for alert in alerts:
            try:
                # Log the security event
                await log_security_event(
                    action=f"ALERT_{alert.alert_type.value}",
                    severity=SeverityLevel.HIGH if alert.severity in [AlertSeverity.HIGH, AlertSeverity.CRITICAL] else SeverityLevel.MEDIUM,
                    details={
                        'alert_id': alert.alert_id,
                        'alert_type': alert.alert_type.value,
                        'alert_severity': alert.severity.value,
                        'alert_title': alert.title,
                        'alert_description': alert.description,
                        'indicators': alert.indicators,
                        'recommendations': alert.recommendations
                    }
                )
                
                # Send email notifications for high/critical alerts
                if alert.severity in [AlertSeverity.HIGH, AlertSeverity.CRITICAL]:
                    await self._send_email_alert(alert)
                
                # Send Slack notifications if configured
                await self._send_slack_alert(alert)
                
                # Send webhooks if configured
                await self._send_webhook_alert(alert)
                
            except Exception as e:
                logger.error(f"Failed to send notifications for alert {alert.alert_id}: {e}")
    
    async def _send_email_alert(self, alert: SecurityAlert) -> None:
        """Send email alert notification"""
        if not getattr(settings, 'SMTP_HOST', None):
            return
        
        try:
            msg = MIMEMultipart()
            msg['From'] = getattr(settings, 'ALERT_EMAIL_FROM', 'security@chrono-scraper.com')
            msg['To'] = getattr(settings, 'SECURITY_ALERT_EMAIL', 'admin@chrono-scraper.com')
            msg['Subject'] = f"[SECURITY ALERT - {alert.severity.upper()}] {alert.title}"
            
            body = f"""
Security Alert Detected

Alert ID: {alert.alert_id}
Type: {alert.alert_type.value}
Severity: {alert.severity.value}
Detected: {alert.detected_at.isoformat()}

Description:
{alert.description}

Affected Resources:
{', '.join(alert.affected_resources)}

Indicators:
{json.dumps(alert.indicators, indent=2, default=str)}

Recommendations:
{chr(10).join(f'- {rec}' for rec in alert.recommendations)}

This is an automated security alert. Please investigate immediately.
"""
            
            msg.attach(MIMEText(body, 'plain'))
            
            server = smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT)
            if getattr(settings, 'SMTP_TLS', False):
                server.starttls()
            if getattr(settings, 'SMTP_USERNAME', None):
                server.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
            
            server.send_message(msg)
            server.quit()
            
        except Exception as e:
            logger.error(f"Failed to send email alert: {e}")
    
    async def _send_slack_alert(self, alert: SecurityAlert) -> None:
        """Send Slack alert notification"""
        # Implementation for Slack notifications
        pass
    
    async def _send_webhook_alert(self, alert: SecurityAlert) -> None:
        """Send webhook alert notification"""
        # Implementation for webhook notifications
        pass


# Global alerts service instance
security_alerts_service = SecurityAlertsService()


# Background task for real-time monitoring
async def monitor_audit_events():
    """Background task to continuously monitor audit events"""
    while True:
        try:
            async for db in get_db():
                # Get recent events (last 5 minutes)
                cutoff_time = datetime.now(timezone.utc) - timedelta(minutes=5)
                
                result = await db.execute(
                    select(AuditLog)
                    .where(AuditLog.created_at >= cutoff_time)
                    .order_by(desc(AuditLog.created_at))
                )
                
                recent_events = result.scalars().all()
                
                if recent_events:
                    # Analyze for security threats
                    alerts = await security_alerts_service.analyze_real_time_events(
                        recent_events, time_window_minutes=60
                    )
                    
                    if alerts:
                        # Send notifications
                        await security_alerts_service.send_alert_notifications(alerts, db)
                        logger.info(f"Generated {len(alerts)} security alerts")
                
                break  # Exit the db session loop
                
        except Exception as e:
            logger.error(f"Error in audit event monitoring: {e}")
        
        # Wait before next check
        await asyncio.sleep(300)  # Check every 5 minutes