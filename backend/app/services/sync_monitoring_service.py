"""
Sync Monitoring and Observability Service

This module provides comprehensive monitoring, metrics collection, and alerting
for data synchronization operations between PostgreSQL and DuckDB.
"""
import asyncio
import json
import logging
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional, Any, Deque, Callable
from uuid import uuid4

import aiohttp
from prometheus_client import Counter, Histogram, Gauge, Info, generate_latest, CONTENT_TYPE_LATEST

from app.core.config import settings
from app.services.data_sync_service import data_sync_service
from app.services.change_data_capture import cdc_service
from app.services.data_consistency_validator import data_consistency_service


# Logging configuration
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class AlertSeverity(str, Enum):
    """Alert severity levels"""
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"
    EMERGENCY = "emergency"


class MetricType(str, Enum):
    """Types of metrics"""
    COUNTER = "counter"
    GAUGE = "gauge"
    HISTOGRAM = "histogram"
    SUMMARY = "summary"


@dataclass
class Alert:
    """Represents a monitoring alert"""
    alert_id: str
    alert_type: str
    severity: AlertSeverity
    title: str
    description: str
    service: str
    timestamp: datetime = field(default_factory=datetime.utcnow)
    resolved: bool = False
    resolved_at: Optional[datetime] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert alert to dictionary"""
        return {
            "alert_id": self.alert_id,
            "alert_type": self.alert_type,
            "severity": self.severity.value,
            "title": self.title,
            "description": self.description,
            "service": self.service,
            "timestamp": self.timestamp.isoformat(),
            "resolved": self.resolved,
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
            "metadata": self.metadata
        }


@dataclass
class MetricSample:
    """A single metric sample"""
    name: str
    value: float
    labels: Dict[str, str] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.utcnow)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "name": self.name,
            "value": self.value,
            "labels": self.labels,
            "timestamp": self.timestamp.isoformat()
        }


class PrometheusMetrics:
    """Prometheus metrics for sync operations"""
    
    def __init__(self):
        # Sync operation metrics
        self.sync_operations_total = Counter(
            'sync_operations_total',
            'Total number of sync operations',
            ['operation_type', 'table_name', 'status']
        )
        
        self.sync_operation_duration = Histogram(
            'sync_operation_duration_seconds',
            'Duration of sync operations',
            ['operation_type', 'table_name']
        )
        
        self.sync_queue_size = Gauge(
            'sync_queue_size',
            'Size of sync queues',
            ['queue_type']
        )
        
        self.sync_lag_seconds = Gauge(
            'sync_lag_seconds',
            'Sync lag between PostgreSQL and DuckDB'
        )
        
        # Consistency metrics
        self.consistency_checks_total = Counter(
            'consistency_checks_total',
            'Total consistency checks performed',
            ['check_type', 'table_name', 'status']
        )
        
        self.consistency_score = Gauge(
            'consistency_score',
            'Overall consistency score percentage',
            ['table_name']
        )
        
        self.data_inconsistencies_total = Counter(
            'data_inconsistencies_total',
            'Total data inconsistencies detected',
            ['table_name', 'inconsistency_type']
        )
        
        # CDC metrics
        self.cdc_events_processed_total = Counter(
            'cdc_events_processed_total',
            'Total CDC events processed',
            ['event_type', 'table_name', 'status']
        )
        
        self.cdc_replication_lag_bytes = Gauge(
            'cdc_replication_lag_bytes',
            'CDC replication lag in bytes'
        )
        
        # Database health metrics
        self.database_health_status = Gauge(
            'database_health_status',
            'Database health status (1=healthy, 0=unhealthy)',
            ['database']
        )
        
        self.database_connection_pool_size = Gauge(
            'database_connection_pool_size',
            'Database connection pool size',
            ['database', 'pool_type']
        )
        
        # Service info
        self.service_info = Info(
            'sync_service_info',
            'Sync service information'
        )
        
        # Initialize service info
        self.service_info.info({
            'version': settings.VERSION,
            'sync_strategy': settings.DATA_SYNC_STRATEGY,
            'consistency_level': settings.DATA_SYNC_CONSISTENCY_LEVEL,
            'cdc_enabled': str(settings.CDC_ENABLED),
            'dual_write_enabled': str(settings.ENABLE_DUAL_WRITE)
        })


class AlertManager:
    """Manages alerts and notifications"""
    
    def __init__(self):
        self.active_alerts: Dict[str, Alert] = {}
        self.alert_history: Deque[Alert] = deque(maxlen=10000)
        self.alert_rules: List[Callable] = []
        self.notification_channels: List[Callable] = []
        
        # Alert suppression (prevent spam)
        self.alert_suppression: Dict[str, datetime] = {}
        self.suppression_duration = timedelta(minutes=15)
    
    def add_alert_rule(self, rule_func: Callable):
        """Add an alert rule function"""
        self.alert_rules.append(rule_func)
    
    def add_notification_channel(self, channel_func: Callable):
        """Add a notification channel function"""
        self.notification_channels.append(channel_func)
    
    async def create_alert(
        self,
        alert_type: str,
        severity: AlertSeverity,
        title: str,
        description: str,
        service: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Alert:
        """Create and process a new alert"""
        alert = Alert(
            alert_id=str(uuid4()),
            alert_type=alert_type,
            severity=severity,
            title=title,
            description=description,
            service=service,
            metadata=metadata or {}
        )
        
        # Check if alert should be suppressed
        suppression_key = f"{alert_type}_{service}"
        if suppression_key in self.alert_suppression:
            last_alert_time = self.alert_suppression[suppression_key]
            if datetime.utcnow() - last_alert_time < self.suppression_duration:
                logger.debug(f"Alert suppressed: {alert.title}")
                return alert
        
        # Update suppression timestamp
        self.alert_suppression[suppression_key] = datetime.utcnow()
        
        # Add to active alerts
        self.active_alerts[alert.alert_id] = alert
        self.alert_history.append(alert)
        
        # Send notifications
        await self._send_notifications(alert)
        
        logger.info(f"Alert created: {alert.title} ({alert.severity.value})")
        return alert
    
    async def resolve_alert(self, alert_id: str) -> bool:
        """Resolve an active alert"""
        if alert_id in self.active_alerts:
            alert = self.active_alerts[alert_id]
            alert.resolved = True
            alert.resolved_at = datetime.utcnow()
            
            # Remove from active alerts
            del self.active_alerts[alert_id]
            
            logger.info(f"Alert resolved: {alert.title}")
            return True
        
        return False
    
    async def _send_notifications(self, alert: Alert):
        """Send alert notifications through configured channels"""
        for channel_func in self.notification_channels:
            try:
                await channel_func(alert)
            except Exception as e:
                logger.error(f"Failed to send notification: {str(e)}")
    
    def get_active_alerts(self) -> List[Dict[str, Any]]:
        """Get all active alerts"""
        return [alert.to_dict() for alert in self.active_alerts.values()]
    
    def get_alert_history(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Get alert history"""
        recent_alerts = list(self.alert_history)[-limit:]
        return [alert.to_dict() for alert in recent_alerts]


class MetricsCollector:
    """Collects and aggregates metrics from various services"""
    
    def __init__(self):
        self.metrics_buffer: Dict[str, List[MetricSample]] = defaultdict(list)
        self.prometheus_metrics = PrometheusMetrics()
        self.collection_interval = timedelta(seconds=30)
        self.last_collection = datetime.utcnow()
    
    async def collect_sync_metrics(self):
        """Collect metrics from data sync service"""
        try:
            status = await data_sync_service.get_sync_status()
            
            # Update Prometheus metrics
            self.prometheus_metrics.sync_lag_seconds.set(
                status['metrics']['sync_lag_seconds']
            )
            
            # Update queue sizes
            queue_status = status['queue_status']
            for queue_type, size in queue_status.items():
                self.prometheus_metrics.sync_queue_size.labels(
                    queue_type=queue_type
                ).set(size)
            
            # Update database health
            db_health = status['database_health']
            for db_name, health_info in db_health.items():
                health_value = 1 if health_info.get('status') == 'healthy' else 0
                self.prometheus_metrics.database_health_status.labels(
                    database=db_name
                ).set(health_value)
            
            # Store raw metrics
            timestamp = datetime.utcnow()
            self.metrics_buffer['sync_lag_seconds'].append(
                MetricSample('sync_lag_seconds', status['metrics']['sync_lag_seconds'], {}, timestamp)
            )
            
            self.metrics_buffer['consistency_score'].append(
                MetricSample('consistency_score', status['metrics']['consistency_score'], {}, timestamp)
            )
            
        except Exception as e:
            logger.error(f"Failed to collect sync metrics: {str(e)}")
    
    async def collect_cdc_metrics(self):
        """Collect metrics from CDC service"""
        try:
            status = await cdc_service.get_status()
            
            # Update CDC metrics
            if status['replication_lag_bytes']:
                self.prometheus_metrics.cdc_replication_lag_bytes.set(
                    status['replication_lag_bytes']
                )
            
            # Store raw metrics
            timestamp = datetime.utcnow()
            self.metrics_buffer['cdc_events_processed'].append(
                MetricSample(
                    'cdc_events_processed', 
                    status['events_processed'], 
                    {'service': 'cdc'}, 
                    timestamp
                )
            )
            
        except Exception as e:
            logger.error(f"Failed to collect CDC metrics: {str(e)}")
    
    async def collect_consistency_metrics(self):
        """Collect metrics from consistency validation service"""
        try:
            status = await data_consistency_service.get_service_status()
            
            # Store consistency metrics
            timestamp = datetime.utcnow()
            recent_stats = status['recent_statistics']
            
            self.metrics_buffer['consistency_average_score'].append(
                MetricSample(
                    'consistency_average_score',
                    recent_stats['average_consistency_score'],
                    {},
                    timestamp
                )
            )
            
            self.metrics_buffer['consistency_failure_rate'].append(
                MetricSample(
                    'consistency_failure_rate',
                    recent_stats['failure_rate_percent'],
                    {},
                    timestamp
                )
            )
            
        except Exception as e:
            logger.error(f"Failed to collect consistency metrics: {str(e)}")
    
    def record_sync_operation(
        self,
        operation_type: str,
        table_name: str,
        duration_seconds: float,
        status: str
    ):
        """Record a sync operation for metrics"""
        # Update Prometheus metrics
        self.prometheus_metrics.sync_operations_total.labels(
            operation_type=operation_type,
            table_name=table_name,
            status=status
        ).inc()
        
        self.prometheus_metrics.sync_operation_duration.labels(
            operation_type=operation_type,
            table_name=table_name
        ).observe(duration_seconds)
        
        # Store raw metric
        timestamp = datetime.utcnow()
        self.metrics_buffer['sync_operation_duration'].append(
            MetricSample(
                'sync_operation_duration',
                duration_seconds,
                {
                    'operation_type': operation_type,
                    'table_name': table_name,
                    'status': status
                },
                timestamp
            )
        )
    
    def record_consistency_check(
        self,
        check_type: str,
        table_name: str,
        status: str,
        consistency_score: float
    ):
        """Record a consistency check for metrics"""
        # Update Prometheus metrics
        self.prometheus_metrics.consistency_checks_total.labels(
            check_type=check_type,
            table_name=table_name,
            status=status
        ).inc()
        
        self.prometheus_metrics.consistency_score.labels(
            table_name=table_name
        ).set(consistency_score)
        
        # Store raw metric
        timestamp = datetime.utcnow()
        self.metrics_buffer['consistency_check'].append(
            MetricSample(
                'consistency_check',
                consistency_score,
                {
                    'check_type': check_type,
                    'table_name': table_name,
                    'status': status
                },
                timestamp
            )
        )
    
    def record_cdc_event(
        self,
        event_type: str,
        table_name: str,
        status: str
    ):
        """Record a CDC event for metrics"""
        # Update Prometheus metrics
        self.prometheus_metrics.cdc_events_processed_total.labels(
            event_type=event_type,
            table_name=table_name,
            status=status
        ).inc()
    
    def get_prometheus_metrics(self) -> str:
        """Get Prometheus metrics in text format"""
        return generate_latest().decode('utf-8')
    
    def get_recent_metrics(self, metric_name: str, limit: int = 100) -> List[Dict[str, Any]]:
        """Get recent metrics for a specific metric"""
        if metric_name in self.metrics_buffer:
            recent_samples = self.metrics_buffer[metric_name][-limit:]
            return [sample.to_dict() for sample in recent_samples]
        return []
    
    def cleanup_old_metrics(self, retention_hours: int = 24):
        """Clean up old metrics from buffer"""
        cutoff_time = datetime.utcnow() - timedelta(hours=retention_hours)
        
        for metric_name in self.metrics_buffer:
            self.metrics_buffer[metric_name] = [
                sample for sample in self.metrics_buffer[metric_name]
                if sample.timestamp >= cutoff_time
            ]


class SyncMonitoringService:
    """
    Main monitoring service for data synchronization operations
    """
    
    def __init__(self):
        self.alert_manager = AlertManager()
        self.metrics_collector = MetricsCollector()
        self.is_running = False
        self.background_tasks: List[asyncio.Task] = []
        
        # Setup default alert rules
        self._setup_default_alert_rules()
        
        # Setup notification channels
        self._setup_notification_channels()
    
    async def initialize(self):
        """Initialize the monitoring service"""
        logger.info("Initializing Sync Monitoring Service")
        
        if not settings.ENABLE_SYNC_MONITORING:
            logger.info("Sync monitoring is disabled")
            return
        
        self.is_running = True
        
        # Start background monitoring tasks
        self.background_tasks = [
            asyncio.create_task(self._metrics_collection_worker()),
            asyncio.create_task(self._alert_evaluation_worker()),
            asyncio.create_task(self._health_check_worker()),
            asyncio.create_task(self._cleanup_worker())
        ]
        
        logger.info("Sync Monitoring Service initialized")
    
    async def shutdown(self):
        """Shutdown the monitoring service"""
        logger.info("Shutting down Sync Monitoring Service")
        
        self.is_running = False
        
        # Cancel background tasks
        for task in self.background_tasks:
            task.cancel()
        
        # Wait for tasks to complete
        if self.background_tasks:
            await asyncio.gather(*self.background_tasks, return_exceptions=True)
        
        logger.info("Sync Monitoring Service shutdown completed")
    
    def _setup_default_alert_rules(self):
        """Setup default alerting rules"""
        
        async def high_sync_lag_rule():
            """Alert on high sync lag"""
            try:
                status = await data_sync_service.get_sync_status()
                sync_lag = status['metrics']['sync_lag_seconds']
                threshold = settings.SYNC_LAG_ALERT_THRESHOLD_MINUTES * 60
                
                if sync_lag > threshold:
                    await self.alert_manager.create_alert(
                        alert_type="high_sync_lag",
                        severity=AlertSeverity.WARNING,
                        title="High Sync Lag Detected",
                        description=f"Sync lag is {sync_lag}s, exceeding threshold of {threshold}s",
                        service="data_sync",
                        metadata={"sync_lag": sync_lag, "threshold": threshold}
                    )
            except Exception as e:
                logger.error(f"High sync lag rule failed: {str(e)}")
        
        async def low_consistency_score_rule():
            """Alert on low consistency score"""
            try:
                status = await data_sync_service.get_sync_status()
                consistency_score = status['metrics']['consistency_score']
                threshold = settings.CONSISTENCY_SCORE_ALERT_THRESHOLD
                
                if consistency_score < threshold:
                    await self.alert_manager.create_alert(
                        alert_type="low_consistency_score",
                        severity=AlertSeverity.CRITICAL,
                        title="Low Data Consistency Score",
                        description=f"Consistency score is {consistency_score}%, below threshold of {threshold}%",
                        service="data_consistency",
                        metadata={"consistency_score": consistency_score, "threshold": threshold}
                    )
            except Exception as e:
                logger.error(f"Low consistency score rule failed: {str(e)}")
        
        async def dead_letter_queue_full_rule():
            """Alert on dead letter queue buildup"""
            try:
                status = await data_sync_service.get_sync_status()
                dlq_size = status['queue_status']['dead_letter']
                threshold = settings.DEAD_LETTER_QUEUE_ALERT_THRESHOLD
                
                if dlq_size > threshold:
                    await self.alert_manager.create_alert(
                        alert_type="dead_letter_queue_full",
                        severity=AlertSeverity.CRITICAL,
                        title="Dead Letter Queue Full",
                        description=f"Dead letter queue has {dlq_size} items, exceeding threshold of {threshold}",
                        service="data_sync",
                        metadata={"dlq_size": dlq_size, "threshold": threshold}
                    )
            except Exception as e:
                logger.error(f"Dead letter queue rule failed: {str(e)}")
        
        async def database_health_rule():
            """Alert on database health issues"""
            try:
                status = await data_sync_service.get_sync_status()
                db_health = status['database_health']
                
                for db_name, health_info in db_health.items():
                    if health_info.get('status') != 'healthy':
                        await self.alert_manager.create_alert(
                            alert_type="database_unhealthy",
                            severity=AlertSeverity.EMERGENCY,
                            title=f"Database Health Issue: {db_name}",
                            description=f"Database {db_name} is unhealthy: {health_info.get('error', 'Unknown error')}",
                            service="database",
                            metadata={"database": db_name, "health_info": health_info}
                        )
            except Exception as e:
                logger.error(f"Database health rule failed: {str(e)}")
        
        # Add rules to alert manager
        self.alert_manager.add_alert_rule(high_sync_lag_rule)
        self.alert_manager.add_alert_rule(low_consistency_score_rule)
        self.alert_manager.add_alert_rule(dead_letter_queue_full_rule)
        self.alert_manager.add_alert_rule(database_health_rule)
    
    def _setup_notification_channels(self):
        """Setup notification channels"""
        
        async def webhook_notification(alert: Alert):
            """Send webhook notification"""
            webhook_url = None
            
            if alert.service == "data_sync" and settings.SYNC_ALERT_WEBHOOK_URL:
                webhook_url = settings.SYNC_ALERT_WEBHOOK_URL
            elif alert.service == "data_consistency" and settings.CONSISTENCY_ALERT_WEBHOOK_URL:
                webhook_url = settings.CONSISTENCY_ALERT_WEBHOOK_URL
            elif alert.severity == AlertSeverity.EMERGENCY and settings.RECOVERY_ALERT_WEBHOOK_URL:
                webhook_url = settings.RECOVERY_ALERT_WEBHOOK_URL
            
            if webhook_url:
                try:
                    async with aiohttp.ClientSession() as session:
                        payload = {
                            "alert": alert.to_dict(),
                            "timestamp": datetime.utcnow().isoformat(),
                            "service": "chrono_scraper_sync"
                        }
                        
                        async with session.post(
                            webhook_url,
                            json=payload,
                            timeout=aiohttp.ClientTimeout(total=10)
                        ) as response:
                            if response.status == 200:
                                logger.info(f"Webhook notification sent for alert: {alert.title}")
                            else:
                                logger.warning(f"Webhook notification failed: HTTP {response.status}")
                                
                except Exception as e:
                    logger.error(f"Webhook notification error: {str(e)}")
        
        async def email_notification(alert: Alert):
            """Send email notification"""
            email_address = None
            
            if alert.service in ("data_sync", "data_consistency") and settings.SYNC_ALERT_EMAIL:
                email_address = settings.SYNC_ALERT_EMAIL
            elif alert.severity in (AlertSeverity.CRITICAL, AlertSeverity.EMERGENCY) and settings.CRITICAL_ERROR_EMAIL:
                email_address = settings.CRITICAL_ERROR_EMAIL
            
            if email_address:
                # In production, would integrate with actual email service
                logger.warning(f"EMAIL ALERT to {email_address}: {alert.title} - {alert.description}")
        
        # Add notification channels
        self.alert_manager.add_notification_channel(webhook_notification)
        self.alert_manager.add_notification_channel(email_notification)
    
    async def _metrics_collection_worker(self):
        """Background worker for metrics collection"""
        logger.info("Starting metrics collection worker")
        
        while self.is_running:
            try:
                # Collect metrics from all services
                await self.metrics_collector.collect_sync_metrics()
                await self.metrics_collector.collect_cdc_metrics()
                await self.metrics_collector.collect_consistency_metrics()
                
                # Wait for next collection interval
                await asyncio.sleep(settings.SYNC_MONITORING_INTERVAL)
                
            except Exception as e:
                logger.error(f"Metrics collection error: {str(e)}")
                await asyncio.sleep(30)  # Wait before retrying
        
        logger.info("Metrics collection worker stopped")
    
    async def _alert_evaluation_worker(self):
        """Background worker for alert evaluation"""
        logger.info("Starting alert evaluation worker")
        
        while self.is_running:
            try:
                # Evaluate all alert rules
                for rule_func in self.alert_manager.alert_rules:
                    try:
                        await rule_func()
                    except Exception as e:
                        logger.error(f"Alert rule evaluation failed: {str(e)}")
                
                # Wait before next evaluation
                await asyncio.sleep(settings.HEALTH_CHECK_INTERVAL_SECONDS)
                
            except Exception as e:
                logger.error(f"Alert evaluation error: {str(e)}")
                await asyncio.sleep(60)  # Wait before retrying
        
        logger.info("Alert evaluation worker stopped")
    
    async def _health_check_worker(self):
        """Background worker for health checks"""
        logger.info("Starting health check worker")
        
        while self.is_running:
            try:
                # Perform health checks on all services
                health_status = await self.get_overall_health_status()
                
                # Log health status
                if health_status['status'] != 'healthy':
                    logger.warning(f"Health check failed: {health_status}")
                else:
                    logger.debug("Health check passed")
                
                # Wait for next health check
                await asyncio.sleep(settings.HEALTH_CHECK_INTERVAL_SECONDS)
                
            except Exception as e:
                logger.error(f"Health check error: {str(e)}")
                await asyncio.sleep(60)  # Wait before retrying
        
        logger.info("Health check worker stopped")
    
    async def _cleanup_worker(self):
        """Background worker for cleanup operations"""
        logger.info("Starting cleanup worker")
        
        while self.is_running:
            try:
                # Clean up old metrics
                self.metrics_collector.cleanup_old_metrics()
                
                # Clean up resolved alerts (keep for 7 days)
                cutoff_time = datetime.utcnow() - timedelta(days=7)
                
                # Remove old resolved alerts from history
                self.alert_manager.alert_history = deque(
                    [alert for alert in self.alert_manager.alert_history
                     if not alert.resolved or alert.resolved_at >= cutoff_time],
                    maxlen=10000
                )
                
                logger.debug("Cleanup completed")
                
                # Wait 24 hours before next cleanup
                await asyncio.sleep(24 * 3600)
                
            except Exception as e:
                logger.error(f"Cleanup error: {str(e)}")
                await asyncio.sleep(3600)  # Wait 1 hour before retrying
        
        logger.info("Cleanup worker stopped")
    
    async def get_overall_health_status(self) -> Dict[str, Any]:
        """Get overall health status of all sync services"""
        try:
            health_checks = {}
            overall_healthy = True
            
            # Check data sync service
            try:
                sync_status = await data_sync_service.get_sync_status()
                health_checks['data_sync'] = {
                    'status': 'healthy' if sync_status['service_status'] == 'running' else 'unhealthy',
                    'details': sync_status
                }
                if sync_status['service_status'] != 'running':
                    overall_healthy = False
            except Exception as e:
                health_checks['data_sync'] = {
                    'status': 'unhealthy',
                    'error': str(e)
                }
                overall_healthy = False
            
            # Check CDC service
            try:
                cdc_status = await cdc_service.get_status()
                health_checks['cdc'] = {
                    'status': 'healthy' if cdc_status['service_status'] == 'running' else 'unhealthy',
                    'details': cdc_status
                }
                if cdc_status['service_status'] != 'running':
                    overall_healthy = False
            except Exception as e:
                health_checks['cdc'] = {
                    'status': 'unhealthy',
                    'error': str(e)
                }
                overall_healthy = False
            
            # Check consistency service
            try:
                consistency_status = await data_consistency_service.get_service_status()
                health_checks['consistency'] = {
                    'status': 'healthy' if consistency_status['service_status'] == 'running' else 'unhealthy',
                    'details': consistency_status
                }
                if consistency_status['service_status'] != 'running':
                    overall_healthy = False
            except Exception as e:
                health_checks['consistency'] = {
                    'status': 'unhealthy',
                    'error': str(e)
                }
                overall_healthy = False
            
            return {
                'status': 'healthy' if overall_healthy else 'unhealthy',
                'timestamp': datetime.utcnow().isoformat(),
                'services': health_checks,
                'monitoring_service': {
                    'status': 'running' if self.is_running else 'stopped',
                    'background_tasks': len(self.background_tasks),
                    'active_alerts': len(self.alert_manager.active_alerts),
                    'metrics_buffer_size': sum(len(samples) for samples in self.metrics_collector.metrics_buffer.values())
                }
            }
            
        except Exception as e:
            logger.error(f"Health status check failed: {str(e)}")
            return {
                'status': 'unhealthy',
                'error': str(e),
                'timestamp': datetime.utcnow().isoformat()
            }
    
    async def get_monitoring_dashboard_data(self) -> Dict[str, Any]:
        """Get comprehensive monitoring dashboard data"""
        try:
            # Get current health status
            health_status = await self.get_overall_health_status()
            
            # Get recent metrics
            sync_metrics = self.metrics_collector.get_recent_metrics('sync_lag_seconds', 100)
            consistency_metrics = self.metrics_collector.get_recent_metrics('consistency_score', 100)
            cdc_metrics = self.metrics_collector.get_recent_metrics('cdc_events_processed', 100)
            
            # Get alerts
            active_alerts = self.alert_manager.get_active_alerts()
            alert_history = self.alert_manager.get_alert_history(50)
            
            # Calculate summary statistics
            if sync_metrics:
                avg_sync_lag = sum(m['value'] for m in sync_metrics) / len(sync_metrics)
                max_sync_lag = max(m['value'] for m in sync_metrics)
            else:
                avg_sync_lag = max_sync_lag = 0
            
            if consistency_metrics:
                avg_consistency = sum(m['value'] for m in consistency_metrics) / len(consistency_metrics)
                min_consistency = min(m['value'] for m in consistency_metrics)
            else:
                avg_consistency = min_consistency = 100
            
            return {
                'timestamp': datetime.utcnow().isoformat(),
                'health_status': health_status,
                'summary_statistics': {
                    'average_sync_lag_seconds': avg_sync_lag,
                    'maximum_sync_lag_seconds': max_sync_lag,
                    'average_consistency_score': avg_consistency,
                    'minimum_consistency_score': min_consistency,
                    'active_alerts_count': len(active_alerts),
                    'critical_alerts_count': len([a for a in active_alerts if a['severity'] == 'critical'])
                },
                'metrics': {
                    'sync_lag': sync_metrics[-20:],  # Last 20 samples
                    'consistency_score': consistency_metrics[-20:],
                    'cdc_events': cdc_metrics[-20:]
                },
                'alerts': {
                    'active': active_alerts,
                    'recent': alert_history[:10]  # Last 10 alerts
                },
                'configuration': {
                    'sync_enabled': settings.DATA_SYNC_ENABLED,
                    'cdc_enabled': settings.CDC_ENABLED,
                    'consistency_checks_enabled': settings.CONSISTENCY_CHECK_ENABLED,
                    'sync_strategy': settings.DATA_SYNC_STRATEGY,
                    'consistency_level': settings.DATA_SYNC_CONSISTENCY_LEVEL
                }
            }
            
        except Exception as e:
            logger.error(f"Dashboard data generation failed: {str(e)}")
            return {
                'error': str(e),
                'timestamp': datetime.utcnow().isoformat()
            }
    
    def record_sync_operation(self, operation_type: str, table_name: str, duration_seconds: float, status: str):
        """Record a sync operation for monitoring"""
        self.metrics_collector.record_sync_operation(operation_type, table_name, duration_seconds, status)
    
    def record_consistency_check(self, check_type: str, table_name: str, status: str, consistency_score: float):
        """Record a consistency check for monitoring"""
        self.metrics_collector.record_consistency_check(check_type, table_name, status, consistency_score)
    
    def record_cdc_event(self, event_type: str, table_name: str, status: str):
        """Record a CDC event for monitoring"""
        self.metrics_collector.record_cdc_event(event_type, table_name, status)
    
    async def create_manual_alert(
        self,
        alert_type: str,
        severity: str,
        title: str,
        description: str,
        service: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """Create a manual alert (for testing or external triggers)"""
        alert = await self.alert_manager.create_alert(
            alert_type=alert_type,
            severity=AlertSeverity(severity),
            title=title,
            description=description,
            service=service,
            metadata=metadata
        )
        return alert.alert_id
    
    async def resolve_alert(self, alert_id: str) -> bool:
        """Resolve an active alert"""
        return await self.alert_manager.resolve_alert(alert_id)
    
    def get_prometheus_metrics(self) -> str:
        """Get Prometheus metrics for external monitoring systems"""
        return self.metrics_collector.get_prometheus_metrics()


# Global monitoring service instance
sync_monitoring_service = SyncMonitoringService()


async def initialize_monitoring() -> None:
    """Initialize monitoring service"""
    await sync_monitoring_service.initialize()


async def shutdown_monitoring() -> None:
    """Shutdown monitoring service"""
    await sync_monitoring_service.shutdown()