"""
Monitoring and alerting service for backup operations.

This service provides:
- Real-time backup operation monitoring
- Performance metrics collection and analysis
- Automated alerting for backup failures and issues
- Health checks for backup infrastructure
- SLA monitoring and reporting
- Integration with external monitoring systems
- Backup trend analysis and predictions
"""

import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from enum import Enum
import redis.asyncio as aioredis
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select, func, and_

from app.core.config import settings
from app.core.database import get_db
from app.models.backup import (
    BackupExecution, StorageBackendConfig,
    BackupSchedule, BackupStatusEnum
)
from app.services.monitoring import MonitoringService
from app.core.email_service import EmailService


class AlertSeverity(str, Enum):
    """Alert severity levels."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class AlertType(str, Enum):
    """Types of backup alerts."""
    BACKUP_FAILED = "backup_failed"
    BACKUP_OVERDUE = "backup_overdue"
    STORAGE_UNHEALTHY = "storage_unhealthy"
    LOW_SUCCESS_RATE = "low_success_rate"
    STORAGE_FULL = "storage_full"
    RECOVERY_FAILED = "recovery_failed"
    INTEGRITY_CHECK_FAILED = "integrity_check_failed"
    SCHEDULE_DISABLED = "schedule_disabled"
    RETENTION_POLICY_VIOLATED = "retention_policy_violated"
    PERFORMANCE_DEGRADATION = "performance_degradation"


@dataclass
class BackupAlert:
    """Backup alert information."""
    alert_id: str
    alert_type: AlertType
    severity: AlertSeverity
    title: str
    message: str
    timestamp: datetime
    source: str = ""
    source_id: str = ""
    metadata: Dict[str, Any] = None
    resolved: bool = False
    resolved_at: Optional[datetime] = None
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


@dataclass
class BackupMetrics:
    """Backup system metrics."""
    timestamp: datetime
    total_backups_24h: int
    successful_backups_24h: int
    failed_backups_24h: int
    success_rate_24h: float
    avg_backup_duration_24h: float
    total_storage_used_gb: float
    storage_growth_rate_gb_per_day: float
    active_schedules: int
    healthy_storage_backends: int
    unhealthy_storage_backends: int
    pending_verifications: int
    overdue_backups: int


class BackupMonitoringService:
    """Service for monitoring backup operations and generating alerts."""
    
    def __init__(self):
        self.redis_client = None
        self.email_service = EmailService()
        self.monitoring = MonitoringService()
        self.alert_channels = []
        self.alert_cache_ttl = 3600  # 1 hour
        
        # Initialize alert thresholds
        self.thresholds = {
            'success_rate_warning': 0.85,  # Alert if success rate drops below 85%
            'success_rate_critical': 0.70,  # Critical if below 70%
            'backup_overdue_hours': 26,     # Alert if scheduled backup is 2+ hours overdue
            'storage_usage_warning': 0.80,  # Alert at 80% storage usage
            'storage_usage_critical': 0.95,  # Critical at 95% storage usage
            'avg_duration_increase': 2.0,   # Alert if avg duration increases by 2x
            'failed_backups_threshold': 3   # Alert after 3 consecutive failures
        }
    
    async def initialize(self):
        """Initialize the monitoring service."""
        self.redis_client = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
        
        # Initialize alert channels
        await self._initialize_alert_channels()
    
    async def _initialize_alert_channels(self):
        """Initialize available alert channels."""
        # Email alerts
        if settings.SMTP_HOST or settings.MAILGUN_API_KEY:
            self.alert_channels.append({
                'type': 'email',
                'config': {
                    'recipients': [settings.ADMIN_EMAIL] if settings.ADMIN_EMAIL else []
                }
            })
        
        # Slack alerts
        if hasattr(settings, 'SLACK_WEBHOOK_URL') and settings.SLACK_WEBHOOK_URL:
            self.alert_channels.append({
                'type': 'slack',
                'config': {
                    'webhook_url': settings.SLACK_WEBHOOK_URL
                }
            })
        
        # Add other alert channels as needed (PagerDuty, Discord, etc.)
    
    async def collect_metrics(self) -> BackupMetrics:
        """Collect current backup system metrics."""
        try:
            async for db in get_db():
                now = datetime.utcnow()
                twenty_four_hours_ago = now - timedelta(hours=24)
                
                # Backup statistics for last 24 hours
                backup_stats_stmt = select(
                    func.count(BackupExecution.id).label("total"),
                    func.sum(
                        func.case(
                            (BackupExecution.status == BackupStatusEnum.COMPLETED, 1),
                            else_=0
                        )
                    ).label("successful"),
                    func.sum(
                        func.case(
                            (BackupExecution.status == BackupStatusEnum.FAILED, 1),
                            else_=0
                        )
                    ).label("failed"),
                    func.avg(BackupExecution.duration_seconds).label("avg_duration"),
                    func.sum(BackupExecution.size_bytes).label("total_size")
                ).where(BackupExecution.started_at >= twenty_four_hours_ago)
                
                backup_stats_result = await db.execute(backup_stats_stmt)
                backup_stats = backup_stats_result.first()
                
                # Storage backend health
                storage_stmt = select(
                    func.count(StorageBackendConfig.id).label("total"),
                    func.sum(
                        func.case(
                            (StorageBackendConfig.is_healthy is True, 1),
                            else_=0
                        )
                    ).label("healthy"),
                    func.sum(StorageBackendConfig.total_size_bytes).label("total_storage")
                ).where(StorageBackendConfig.is_active is True)
                
                storage_result = await db.execute(storage_stmt)
                storage_stats = storage_result.first()
                
                # Active schedules
                active_schedules_stmt = select(func.count(BackupSchedule.id)).where(
                    BackupSchedule.is_active is True
                )
                active_schedules_result = await db.execute(active_schedules_stmt)
                active_schedules_count = active_schedules_result.scalar()
                
                # Pending verifications
                pending_verifications_stmt = select(func.count(BackupExecution.id)).where(
                    BackupExecution.verification_status == "pending"
                )
                pending_verifications_result = await db.execute(pending_verifications_stmt)
                pending_verifications_count = pending_verifications_result.scalar()
                
                # Overdue backups (schedules that should have run but haven't)
                overdue_stmt = select(func.count(BackupSchedule.id)).where(
                    and_(
                        BackupSchedule.is_active is True,
                        BackupSchedule.next_run_at < now,
                        BackupSchedule.last_run_at < now - timedelta(hours=24)
                    )
                )
                overdue_result = await db.execute(overdue_stmt)
                overdue_count = overdue_result.scalar()
                
                # Calculate metrics
                total_backups = backup_stats.total or 0
                successful_backups = backup_stats.successful or 0
                failed_backups = backup_stats.failed or 0
                success_rate = successful_backups / max(total_backups, 1)
                avg_duration = float(backup_stats.avg_duration or 0)
                total_storage_gb = (storage_stats.total_storage or 0) / (1024 ** 3)
                healthy_backends = storage_stats.healthy or 0
                total_backends = storage_stats.total or 0
                unhealthy_backends = total_backends - healthy_backends
                
                # Calculate storage growth rate (simplified - would use historical data in production)
                storage_growth_rate = await self._calculate_storage_growth_rate(db)
                
                metrics = BackupMetrics(
                    timestamp=now,
                    total_backups_24h=total_backups,
                    successful_backups_24h=successful_backups,
                    failed_backups_24h=failed_backups,
                    success_rate_24h=success_rate,
                    avg_backup_duration_24h=avg_duration,
                    total_storage_used_gb=total_storage_gb,
                    storage_growth_rate_gb_per_day=storage_growth_rate,
                    active_schedules=active_schedules_count,
                    healthy_storage_backends=healthy_backends,
                    unhealthy_storage_backends=unhealthy_backends,
                    pending_verifications=pending_verifications_count,
                    overdue_backups=overdue_count
                )
                
                # Store metrics in Redis for trending
                await self._store_metrics(metrics)
                
                return metrics
                
        except Exception as e:
            # Log error and return default metrics
            await self.monitoring.log_error("Failed to collect backup metrics", str(e))
            return BackupMetrics(
                timestamp=datetime.utcnow(),
                total_backups_24h=0,
                successful_backups_24h=0,
                failed_backups_24h=0,
                success_rate_24h=0.0,
                avg_backup_duration_24h=0.0,
                total_storage_used_gb=0.0,
                storage_growth_rate_gb_per_day=0.0,
                active_schedules=0,
                healthy_storage_backends=0,
                unhealthy_storage_backends=0,
                pending_verifications=0,
                overdue_backups=0
            )
    
    async def _calculate_storage_growth_rate(self, db: AsyncSession) -> float:
        """Calculate storage growth rate in GB per day."""
        try:
            # Get storage usage from 7 days ago and now
            seven_days_ago = datetime.utcnow() - timedelta(days=7)
            
            # This is simplified - in production, you'd have historical storage metrics
            # For now, estimate based on backup sizes in the last week
            recent_backups_stmt = select(
                func.sum(BackupExecution.size_bytes)
            ).where(BackupExecution.started_at >= seven_days_ago)
            
            result = await db.execute(recent_backups_stmt)
            recent_size_bytes = result.scalar() or 0
            
            # Estimate growth rate (very rough approximation)
            growth_rate_gb = (recent_size_bytes / (1024 ** 3)) / 7  # GB per day
            
            return growth_rate_gb
        
        except Exception:
            return 0.0
    
    async def _store_metrics(self, metrics: BackupMetrics):
        """Store metrics in Redis for historical trending."""
        try:
            metrics_key = f"backup_metrics:{metrics.timestamp.strftime('%Y%m%d_%H%M')}"
            metrics_data = {
                "timestamp": metrics.timestamp.isoformat(),
                "total_backups_24h": metrics.total_backups_24h,
                "successful_backups_24h": metrics.successful_backups_24h,
                "failed_backups_24h": metrics.failed_backups_24h,
                "success_rate_24h": metrics.success_rate_24h,
                "avg_backup_duration_24h": metrics.avg_backup_duration_24h,
                "total_storage_used_gb": metrics.total_storage_used_gb,
                "storage_growth_rate_gb_per_day": metrics.storage_growth_rate_gb_per_day,
                "active_schedules": metrics.active_schedules,
                "healthy_storage_backends": metrics.healthy_storage_backends,
                "unhealthy_storage_backends": metrics.unhealthy_storage_backends,
                "pending_verifications": metrics.pending_verifications,
                "overdue_backups": metrics.overdue_backups
            }
            
            await self.redis_client.setex(
                metrics_key, 
                86400 * 7,  # Keep for 7 days
                json.dumps(metrics_data)
            )
            
            # Keep a list of recent metrics keys for cleanup
            await self.redis_client.lpush("backup_metrics_keys", metrics_key)
            await self.redis_client.ltrim("backup_metrics_keys", 0, 167)  # Keep ~1 week of hourly metrics
            
        except Exception as e:
            await self.monitoring.log_error("Failed to store backup metrics", str(e))
    
    async def check_for_alerts(self) -> List[BackupAlert]:
        """Check for conditions that should generate alerts."""
        alerts = []
        
        try:
            metrics = await self.collect_metrics()
            
            # Check success rate
            alerts.extend(await self._check_success_rate_alerts(metrics))
            
            # Check for overdue backups
            alerts.extend(await self._check_overdue_backup_alerts(metrics))
            
            # Check storage backend health
            alerts.extend(await self._check_storage_health_alerts(metrics))
            
            # Check for failed backups
            alerts.extend(await self._check_failed_backup_alerts())
            
            # Check storage usage
            alerts.extend(await self._check_storage_usage_alerts(metrics))
            
            # Check performance degradation
            alerts.extend(await self._check_performance_alerts(metrics))
            
            # Filter out duplicate alerts
            alerts = await self._deduplicate_alerts(alerts)
            
            # Send alerts
            for alert in alerts:
                await self._send_alert(alert)
            
            return alerts
            
        except Exception as e:
            await self.monitoring.log_error("Failed to check for backup alerts", str(e))
            return []
    
    async def _check_success_rate_alerts(self, metrics: BackupMetrics) -> List[BackupAlert]:
        """Check for success rate related alerts."""
        alerts = []
        
        if metrics.success_rate_24h < self.thresholds['success_rate_critical']:
            alerts.append(BackupAlert(
                alert_id=f"success_rate_critical_{int(datetime.utcnow().timestamp())}",
                alert_type=AlertType.LOW_SUCCESS_RATE,
                severity=AlertSeverity.CRITICAL,
                title="Critical: Backup Success Rate Below 70%",
                message=(
                    f"Backup success rate has dropped to {metrics.success_rate_24h:.1%} "
                    f"in the last 24 hours. Only {metrics.successful_backups_24h} out of "
                    f"{metrics.total_backups_24h} backups completed successfully."
                ),
                timestamp=datetime.utcnow(),
                source="backup_monitoring",
                metadata={
                    "success_rate": metrics.success_rate_24h,
                    "successful_backups": metrics.successful_backups_24h,
                    "total_backups": metrics.total_backups_24h,
                    "threshold": self.thresholds['success_rate_critical']
                }
            ))
        elif metrics.success_rate_24h < self.thresholds['success_rate_warning']:
            alerts.append(BackupAlert(
                alert_id=f"success_rate_warning_{int(datetime.utcnow().timestamp())}",
                alert_type=AlertType.LOW_SUCCESS_RATE,
                severity=AlertSeverity.HIGH,
                title="Warning: Low Backup Success Rate",
                message=(
                    f"Backup success rate has dropped to {metrics.success_rate_24h:.1%} "
                    f"in the last 24 hours. This is below the warning threshold of "
                    f"{self.thresholds['success_rate_warning']:.1%}."
                ),
                timestamp=datetime.utcnow(),
                source="backup_monitoring",
                metadata={
                    "success_rate": metrics.success_rate_24h,
                    "threshold": self.thresholds['success_rate_warning']
                }
            ))
        
        return alerts
    
    async def _check_overdue_backup_alerts(self, metrics: BackupMetrics) -> List[BackupAlert]:
        """Check for overdue backup schedules."""
        alerts = []
        
        if metrics.overdue_backups > 0:
            alerts.append(BackupAlert(
                alert_id=f"overdue_backups_{int(datetime.utcnow().timestamp())}",
                alert_type=AlertType.BACKUP_OVERDUE,
                severity=AlertSeverity.HIGH,
                title=f"{metrics.overdue_backups} Backup Schedule(s) Overdue",
                message=(
                    f"{metrics.overdue_backups} backup schedule(s) are overdue and haven't "
                    f"executed in the expected timeframe. Please check the backup scheduler."
                ),
                timestamp=datetime.utcnow(),
                source="backup_monitoring",
                metadata={
                    "overdue_count": metrics.overdue_backups
                }
            ))
        
        return alerts
    
    async def _check_storage_health_alerts(self, metrics: BackupMetrics) -> List[BackupAlert]:
        """Check for storage backend health issues."""
        alerts = []
        
        if metrics.unhealthy_storage_backends > 0:
            severity = AlertSeverity.CRITICAL if metrics.healthy_storage_backends == 0 else AlertSeverity.HIGH
            
            alerts.append(BackupAlert(
                alert_id=f"unhealthy_storage_{int(datetime.utcnow().timestamp())}",
                alert_type=AlertType.STORAGE_UNHEALTHY,
                severity=severity,
                title=f"{metrics.unhealthy_storage_backends} Storage Backend(s) Unhealthy",
                message=(
                    f"{metrics.unhealthy_storage_backends} storage backend(s) are reporting "
                    f"as unhealthy. This may affect backup operations. "
                    f"{metrics.healthy_storage_backends} backend(s) remain healthy."
                ),
                timestamp=datetime.utcnow(),
                source="backup_monitoring",
                metadata={
                    "unhealthy_backends": metrics.unhealthy_storage_backends,
                    "healthy_backends": metrics.healthy_storage_backends
                }
            ))
        
        return alerts
    
    async def _check_failed_backup_alerts(self) -> List[BackupAlert]:
        """Check for recent backup failures."""
        alerts = []
        
        try:
            async for db in get_db():
                # Get recent failed backups
                recent_failures_stmt = select(BackupExecution).where(
                    and_(
                        BackupExecution.status == BackupStatusEnum.FAILED,
                        BackupExecution.started_at >= datetime.utcnow() - timedelta(hours=6)
                    )
                ).order_by(BackupExecution.started_at.desc()).limit(5)
                
                result = await db.execute(recent_failures_stmt)
                failed_backups = result.scalars().all()
                
                for backup in failed_backups:
                    # Check if we already alerted for this backup
                    alert_key = f"backup_failed:{backup.backup_id}"
                    if not await self.redis_client.exists(alert_key):
                        alerts.append(BackupAlert(
                            alert_id=f"backup_failed_{backup.backup_id}_{int(datetime.utcnow().timestamp())}",
                            alert_type=AlertType.BACKUP_FAILED,
                            severity=AlertSeverity.HIGH,
                            title=f"Backup Failed: {backup.backup_id}",
                            message=(
                                f"Backup {backup.backup_id} ({backup.backup_type.value}) failed. "
                                f"Error: {backup.error_message or 'Unknown error'}"
                            ),
                            timestamp=datetime.utcnow(),
                            source="backup_execution",
                            source_id=backup.backup_id,
                            metadata={
                                "backup_id": backup.backup_id,
                                "backup_type": backup.backup_type.value,
                                "error_message": backup.error_message,
                                "started_at": backup.started_at.isoformat()
                            }
                        ))
                        
                        # Mark as alerted to avoid duplicates
                        await self.redis_client.setex(alert_key, self.alert_cache_ttl, "1")
                
                break
                
        except Exception as e:
            await self.monitoring.log_error("Failed to check failed backup alerts", str(e))
        
        return alerts
    
    async def _check_storage_usage_alerts(self, metrics: BackupMetrics) -> List[BackupAlert]:
        """Check for storage usage alerts."""
        alerts = []
        
        # This is simplified - in production you'd track actual storage usage per backend
        # For now, we'll use growth rate to predict potential issues
        
        if metrics.storage_growth_rate_gb_per_day > 10:  # More than 10GB per day growth
            alerts.append(BackupAlert(
                alert_id=f"storage_growth_{int(datetime.utcnow().timestamp())}",
                alert_type=AlertType.STORAGE_FULL,
                severity=AlertSeverity.MEDIUM,
                title="High Storage Growth Rate Detected",
                message=(
                    f"Storage is growing at {metrics.storage_growth_rate_gb_per_day:.1f}GB per day. "
                    f"Current usage: {metrics.total_storage_used_gb:.1f}GB. "
                    f"Please review retention policies."
                ),
                timestamp=datetime.utcnow(),
                source="backup_monitoring",
                metadata={
                    "growth_rate_gb_per_day": metrics.storage_growth_rate_gb_per_day,
                    "current_usage_gb": metrics.total_storage_used_gb
                }
            ))
        
        return alerts
    
    async def _check_performance_alerts(self, metrics: BackupMetrics) -> List[BackupAlert]:
        """Check for performance degradation alerts."""
        alerts = []
        
        try:
            # Get historical average duration for comparison
            historical_avg = await self._get_historical_average_duration()
            
            if (historical_avg > 0 and 
                metrics.avg_backup_duration_24h > historical_avg * self.thresholds['avg_duration_increase']):
                
                alerts.append(BackupAlert(
                    alert_id=f"performance_degradation_{int(datetime.utcnow().timestamp())}",
                    alert_type=AlertType.PERFORMANCE_DEGRADATION,
                    severity=AlertSeverity.MEDIUM,
                    title="Backup Performance Degradation Detected",
                    message=(
                        f"Average backup duration has increased significantly. "
                        f"Current: {metrics.avg_backup_duration_24h/60:.1f} minutes, "
                        f"Historical: {historical_avg/60:.1f} minutes "
                        f"({((metrics.avg_backup_duration_24h/historical_avg)-1)*100:.1f}% increase)"
                    ),
                    timestamp=datetime.utcnow(),
                    source="backup_monitoring",
                    metadata={
                        "current_avg_duration": metrics.avg_backup_duration_24h,
                        "historical_avg_duration": historical_avg,
                        "increase_ratio": metrics.avg_backup_duration_24h / historical_avg
                    }
                ))
        
        except Exception as e:
            await self.monitoring.log_error("Failed to check performance alerts", str(e))
        
        return alerts
    
    async def _get_historical_average_duration(self) -> float:
        """Get historical average backup duration for comparison."""
        try:
            # Get metrics from Redis for the past week
            keys = await self.redis_client.lrange("backup_metrics_keys", 0, -1)
            durations = []
            
            for key in keys[-168:]:  # Last week (hourly metrics)
                metrics_data = await self.redis_client.get(key)
                if metrics_data:
                    data = json.loads(metrics_data)
                    if data.get("avg_backup_duration_24h", 0) > 0:
                        durations.append(data["avg_backup_duration_24h"])
            
            if durations:
                return sum(durations) / len(durations)
            
            return 0.0
        
        except Exception:
            return 0.0
    
    async def _deduplicate_alerts(self, alerts: List[BackupAlert]) -> List[BackupAlert]:
        """Remove duplicate alerts based on type and recent history."""
        deduplicated = []
        
        for alert in alerts:
            # Check if similar alert was sent recently
            recent_alert_key = f"recent_alert:{alert.alert_type.value}"
            
            if not await self.redis_client.exists(recent_alert_key):
                deduplicated.append(alert)
                
                # Mark this alert type as recently sent
                await self.redis_client.setex(
                    recent_alert_key, 
                    self.alert_cache_ttl, 
                    alert.alert_id
                )
        
        return deduplicated
    
    async def _send_alert(self, alert: BackupAlert):
        """Send alert through configured channels."""
        try:
            for channel in self.alert_channels:
                if channel['type'] == 'email':
                    await self._send_email_alert(alert, channel['config'])
                elif channel['type'] == 'slack':
                    await self._send_slack_alert(alert, channel['config'])
            
            # Log the alert
            await self.monitoring.log_event(
                f"Backup alert sent: {alert.title}",
                {
                    "alert_id": alert.alert_id,
                    "alert_type": alert.alert_type.value,
                    "severity": alert.severity.value,
                    "source": alert.source
                }
            )
        
        except Exception as e:
            await self.monitoring.log_error(f"Failed to send alert {alert.alert_id}", str(e))
    
    async def _send_email_alert(self, alert: BackupAlert, config: Dict[str, Any]):
        """Send alert via email."""
        try:
            if not config.get('recipients'):
                return
            
            subject = f"[{alert.severity.upper()}] {alert.title}"
            
            # Create HTML email body
            html_body = f"""
            <html>
            <body>
                <h2 style="color: {'#dc3545' if alert.severity == AlertSeverity.CRITICAL else '#fd7e14' if alert.severity == AlertSeverity.HIGH else '#28a745'}">
                    Backup System Alert
                </h2>
                <p><strong>Severity:</strong> {alert.severity.upper()}</p>
                <p><strong>Alert Type:</strong> {alert.alert_type.value.replace('_', ' ').title()}</p>
                <p><strong>Time:</strong> {alert.timestamp.strftime('%Y-%m-%d %H:%M:%S UTC')}</p>
                
                <h3>Description</h3>
                <p>{alert.message}</p>
                
                {"<h3>Additional Details</h3><pre>" + json.dumps(alert.metadata, indent=2) + "</pre>" if alert.metadata else ""}
                
                <hr>
                <p><small>This alert was generated by the Chrono Scraper backup monitoring system.</small></p>
            </body>
            </html>
            """
            
            # Send via email service
            await self.email_service.send_email(
                to_emails=config['recipients'],
                subject=subject,
                html_content=html_body
            )
        
        except Exception as e:
            await self.monitoring.log_error("Failed to send email alert", str(e))
    
    async def _send_slack_alert(self, alert: BackupAlert, config: Dict[str, Any]):
        """Send alert via Slack webhook."""
        try:
            webhook_url = config.get('webhook_url')
            if not webhook_url:
                return
            
            # Determine color based on severity
            colors = {
                AlertSeverity.LOW: "#28a745",      # Green
                AlertSeverity.MEDIUM: "#ffc107",   # Yellow
                AlertSeverity.HIGH: "#fd7e14",     # Orange
                AlertSeverity.CRITICAL: "#dc3545"  # Red
            }
            
            payload = {
                "attachments": [
                    {
                        "color": colors.get(alert.severity, "#6c757d"),
                        "title": alert.title,
                        "text": alert.message,
                        "fields": [
                            {
                                "title": "Severity",
                                "value": alert.severity.upper(),
                                "short": True
                            },
                            {
                                "title": "Alert Type",
                                "value": alert.alert_type.value.replace('_', ' ').title(),
                                "short": True
                            },
                            {
                                "title": "Time",
                                "value": alert.timestamp.strftime('%Y-%m-%d %H:%M:%S UTC'),
                                "short": True
                            }
                        ],
                        "footer": "Chrono Scraper Backup Monitor",
                        "ts": int(alert.timestamp.timestamp())
                    }
                ]
            }
            
            # Send to Slack
            async with aiohttp.ClientSession() as session:
                async with session.post(webhook_url, json=payload) as response:
                    if response.status != 200:
                        raise Exception(f"Slack webhook returned status {response.status}")
        
        except Exception as e:
            await self.monitoring.log_error("Failed to send Slack alert", str(e))
    
    async def get_alert_history(self, days: int = 7) -> List[Dict[str, Any]]:
        """Get alert history from the monitoring logs."""
        try:
            # This would query your monitoring/logging system for alert history
            # For now, return empty list as placeholder
            return []
        
        except Exception as e:
            await self.monitoring.log_error("Failed to get alert history", str(e))
            return []
    
    async def get_metrics_history(self, hours: int = 24) -> List[Dict[str, Any]]:
        """Get historical metrics data."""
        try:
            metrics_history = []
            keys = await self.redis_client.lrange("backup_metrics_keys", 0, hours)
            
            for key in keys:
                metrics_data = await self.redis_client.get(key)
                if metrics_data:
                    metrics_history.append(json.loads(metrics_data))
            
            # Sort by timestamp
            metrics_history.sort(key=lambda x: x.get('timestamp', ''))
            
            return metrics_history
        
        except Exception as e:
            await self.monitoring.log_error("Failed to get metrics history", str(e))
            return []


# Global monitoring service instance
backup_monitoring_service = BackupMonitoringService()