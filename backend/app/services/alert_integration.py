"""
Alert system integration with existing monitoring services.

This module provides seamless integration between the alert management system
and existing monitoring infrastructure, including:
- System health monitoring integration
- Backup system alert forwarding  
- Security incident alert forwarding
- Performance monitoring integration
- Custom metric collection and forwarding
"""

import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Any, Callable, Set

from sqlmodel import select, and_, func

from app.core.database import get_db
from app.services.alert_management import (
    alert_manager,
    AlertRule,
    AlertSeverity,
    AlertCategory, 
    AlertMetric,
    NotificationChannel
)
from app.services.monitoring import MonitoringService
from app.models.audit_log import AuditLog
from app.models.backup import BackupExecution


logger = logging.getLogger(__name__)


class AlertIntegrationService:
    """
    Service that integrates the alert management system with existing 
    monitoring and notification services throughout the application.
    """
    
    def __init__(self):
        self.integration_tasks: Set[asyncio.Task] = set()
        self.metrics_collectors: Dict[str, Callable] = {}
        self.alert_forwarders: Dict[str, Callable] = {}
        
    async def initialize(self) -> None:
        """Initialize alert system integrations"""
        try:
            logger.info("Initializing alert system integrations...")
            
            # Initialize the main alert manager first
            await alert_manager.initialize()
            
            # Set up metric collectors
            await self._setup_metric_collectors()
            
            # Set up alert forwarders
            await self._setup_alert_forwarders()
            
            # Start integration background tasks
            await self._start_integration_tasks()
            
            logger.info("Alert system integrations initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize alert integrations: {e}")
            raise
    
    async def shutdown(self) -> None:
        """Graceful shutdown of integrations"""
        logger.info("Shutting down alert system integrations...")
        
        # Cancel integration tasks
        for task in self.integration_tasks:
            task.cancel()
        
        if self.integration_tasks:
            await asyncio.gather(*self.integration_tasks, return_exceptions=True)
        
        # Shutdown main alert manager
        await alert_manager.shutdown()
        
        logger.info("Alert system integrations shutdown complete")
    
    async def _setup_metric_collectors(self) -> None:
        """Set up metric collection from various services"""
        
        # System health metrics collector
        self.metrics_collectors['system_health'] = self._collect_system_health_metrics
        
        # Backup system metrics collector  
        self.metrics_collectors['backup_system'] = self._collect_backup_metrics
        
        # Security metrics collector
        self.metrics_collectors['security'] = self._collect_security_metrics
        
        # Performance metrics collector
        self.metrics_collectors['performance'] = self._collect_performance_metrics
        
        # Database metrics collector
        self.metrics_collectors['database'] = self._collect_database_metrics
        
        logger.info(f"Set up {len(self.metrics_collectors)} metric collectors")
    
    async def _setup_alert_forwarders(self) -> None:
        """Set up alert forwarding to existing notification systems"""
        
        # Forward security alerts from existing audit system
        self.alert_forwarders['security'] = self._forward_security_alerts
        
        # Forward backup system alerts
        self.alert_forwarders['backup'] = self._forward_backup_alerts
        
        # Forward system health alerts
        self.alert_forwarders['system'] = self._forward_system_alerts
        
        logger.info(f"Set up {len(self.alert_forwarders)} alert forwarders")
    
    async def _start_integration_tasks(self) -> None:
        """Start background tasks for integrations"""
        
        # Metric collection task
        task = asyncio.create_task(self._metric_collection_loop())
        self.integration_tasks.add(task)
        task.add_done_callback(self.integration_tasks.discard)
        
        # Alert forwarding task
        task = asyncio.create_task(self._alert_forwarding_loop())
        self.integration_tasks.add(task)
        task.add_done_callback(self.integration_tasks.discard)
        
        # System health monitoring task
        task = asyncio.create_task(self._system_health_monitoring_loop())
        self.integration_tasks.add(task)
        task.add_done_callback(self.integration_tasks.discard)
        
        # Backup monitoring integration task
        task = asyncio.create_task(self._backup_monitoring_loop())
        self.integration_tasks.add(task)
        task.add_done_callback(self.integration_tasks.discard)
        
        logger.info(f"Started {len(self.integration_tasks)} integration tasks")
    
    async def _metric_collection_loop(self) -> None:
        """Main loop for collecting metrics from all sources"""
        while True:
            try:
                # Collect metrics from all collectors
                all_metrics = []
                
                for collector_name, collector_func in self.metrics_collectors.items():
                    try:
                        metrics = await collector_func()
                        all_metrics.extend(metrics)
                        logger.debug(f"Collected {len(metrics)} metrics from {collector_name}")
                    except Exception as e:
                        logger.error(f"Error collecting metrics from {collector_name}: {e}")
                
                # Process metrics through alert manager
                for metric in all_metrics:
                    try:
                        await alert_manager.process_metric(metric)
                    except Exception as e:
                        logger.error(f"Error processing metric {metric.name}: {e}")
                
                logger.debug(f"Processed {len(all_metrics)} total metrics")
                
                # Wait before next collection
                await asyncio.sleep(60)  # Collect every minute
                
            except Exception as e:
                logger.error(f"Error in metric collection loop: {e}")
                await asyncio.sleep(30)  # Shorter wait on error
    
    async def _alert_forwarding_loop(self) -> None:
        """Main loop for forwarding alerts to existing systems"""
        while True:
            try:
                # Process alert forwarding
                for forwarder_name, forwarder_func in self.alert_forwarders.items():
                    try:
                        await forwarder_func()
                    except Exception as e:
                        logger.error(f"Error in alert forwarder {forwarder_name}: {e}")
                
                # Wait before next forwarding cycle
                await asyncio.sleep(30)  # Forward every 30 seconds
                
            except Exception as e:
                logger.error(f"Error in alert forwarding loop: {e}")
                await asyncio.sleep(30)
    
    async def _system_health_monitoring_loop(self) -> None:
        """Monitor overall system health and generate alerts"""
        while True:
            try:
                # Get comprehensive system health
                health_data = await MonitoringService.get_comprehensive_system_health()
                
                # Generate metrics from health data
                await self._process_health_data(health_data)
                
                # Wait before next health check
                await asyncio.sleep(300)  # Check every 5 minutes
                
            except Exception as e:
                logger.error(f"Error in system health monitoring: {e}")
                await asyncio.sleep(60)
    
    async def _backup_monitoring_loop(self) -> None:
        """Monitor backup system and integrate alerts"""
        while True:
            try:
                # Check for recent backup operations that need alerting
                await self._check_backup_alerts()
                
                # Wait before next check
                await asyncio.sleep(600)  # Check every 10 minutes
                
            except Exception as e:
                logger.error(f"Error in backup monitoring loop: {e}")
                await asyncio.sleep(60)
    
    # Metric Collection Methods
    
    async def _collect_system_health_metrics(self) -> List[AlertMetric]:
        """Collect system health metrics"""
        metrics = []
        current_time = datetime.now(timezone.utc)
        
        try:
            # Get system health data
            health_data = await MonitoringService.get_comprehensive_system_health()
            
            # Service health metrics
            services = health_data.get('services', {})
            for service_name, service_data in services.items():
                if isinstance(service_data, dict):
                    # Service status (1 = healthy, 0 = unhealthy)
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
            
            # Infrastructure metrics
            infrastructure = health_data.get('infrastructure', {})
            system_data = infrastructure.get('system', {})
            
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
            
        except Exception as e:
            logger.error(f"Error collecting system health metrics: {e}")
        
        return metrics
    
    async def _collect_backup_metrics(self) -> List[AlertMetric]:
        """Collect backup system metrics"""
        metrics = []
        current_time = datetime.now(timezone.utc)
        
        try:
            async for db in get_db():
                # Recent backup success rate
                day_ago = current_time - timedelta(days=1)
                
                total_backups = await db.execute(
                    select(func.count(BackupExecution.id))
                    .where(BackupExecution.started_at >= day_ago)
                )
                
                successful_backups = await db.execute(
                    select(func.count(BackupExecution.id))
                    .where(
                        and_(
                            BackupExecution.started_at >= day_ago,
                            BackupExecution.status == 'completed'
                        )
                    )
                )
                
                total_count = total_backups.scalar() or 0
                success_count = successful_backups.scalar() or 0
                
                if total_count > 0:
                    success_rate = (success_count / total_count) * 100
                    metrics.append(AlertMetric(
                        name="backup_success_rate_24h",
                        value=success_rate,
                        unit='percent',
                        timestamp=current_time,
                        labels={'type': 'backup', 'period': '24h'}
                    ))
                
                # Time since last successful backup
                last_backup = await db.execute(
                    select(func.max(BackupExecution.completed_at))
                    .where(BackupExecution.status == 'completed')
                )
                
                last_backup_time = last_backup.scalar()
                if last_backup_time:
                    hours_since_backup = (current_time - last_backup_time).total_seconds() / 3600
                    metrics.append(AlertMetric(
                        name="hours_since_last_backup",
                        value=hours_since_backup,
                        unit='hours',
                        timestamp=current_time,
                        labels={'type': 'backup', 'metric': 'recency'}
                    ))
                
                break
            
        except Exception as e:
            logger.error(f"Error collecting backup metrics: {e}")
        
        return metrics
    
    async def _collect_security_metrics(self) -> List[AlertMetric]:
        """Collect security-related metrics"""
        metrics = []
        current_time = datetime.now(timezone.utc)
        
        try:
            async for db in get_db():
                # Failed login attempts in last hour
                hour_ago = current_time - timedelta(hours=1)
                
                failed_logins = await db.execute(
                    select(func.count(AuditLog.id))
                    .where(
                        and_(
                            AuditLog.action == 'USER_LOGIN_FAILED',
                            AuditLog.created_at >= hour_ago
                        )
                    )
                )
                
                metrics.append(AlertMetric(
                    name="failed_logins_1h",
                    value=failed_logins.scalar() or 0,
                    timestamp=current_time,
                    labels={'type': 'security', 'period': '1h'}
                ))
                
                # High severity audit events in last hour
                high_severity_events = await db.execute(
                    select(func.count(AuditLog.id))
                    .where(
                        and_(
                            AuditLog.severity.in_(['HIGH', 'CRITICAL']),
                            AuditLog.created_at >= hour_ago
                        )
                    )
                )
                
                metrics.append(AlertMetric(
                    name="high_severity_security_events_1h",
                    value=high_severity_events.scalar() or 0,
                    timestamp=current_time,
                    labels={'type': 'security', 'severity': 'high', 'period': '1h'}
                ))
                
                break
                
        except Exception as e:
            logger.error(f"Error collecting security metrics: {e}")
        
        return metrics
    
    async def _collect_performance_metrics(self) -> List[AlertMetric]:
        """Collect performance metrics"""
        metrics = []
        current_time = datetime.now(timezone.utc)
        
        try:
            # Get performance metrics from monitoring service
            performance_data = await MonitoringService._get_performance_metrics()
            
            # API response times
            api_times = performance_data.get('api_response_times', {})
            for endpoint, data in api_times.items():
                if isinstance(data, dict) and 'response_time_ms' in data:
                    metrics.append(AlertMetric(
                        name=f"api_response_time_{endpoint}",
                        value=data['response_time_ms'],
                        unit='ms',
                        timestamp=current_time,
                        labels={'type': 'performance', 'endpoint': endpoint}
                    ))
            
        except Exception as e:
            logger.error(f"Error collecting performance metrics: {e}")
        
        return metrics
    
    async def _collect_database_metrics(self) -> List[AlertMetric]:
        """Collect database metrics"""
        metrics = []
        current_time = datetime.now(timezone.utc)
        
        try:
            # Get database health from monitoring service
            db_health = await MonitoringService._check_database_health()
            
            # Database response time
            if 'response_time_ms' in db_health:
                metrics.append(AlertMetric(
                    name="database_response_time",
                    value=db_health['response_time_ms'],
                    unit='ms',
                    timestamp=current_time,
                    labels={'type': 'database', 'metric': 'response_time'}
                ))
            
            # Active connections
            if 'metrics' in db_health and 'active_connections' in db_health['metrics']:
                metrics.append(AlertMetric(
                    name="database_active_connections",
                    value=db_health['metrics']['active_connections'],
                    timestamp=current_time,
                    labels={'type': 'database', 'metric': 'connections'}
                ))
            
        except Exception as e:
            logger.error(f"Error collecting database metrics: {e}")
        
        return metrics
    
    # Alert Forwarding Methods
    
    async def _forward_security_alerts(self) -> None:
        """Forward security alerts from existing audit system"""
        try:
            # Get recent security alerts from the existing security alerts service
            # This would integrate with the existing audit_alerts.py service
            
            # For now, we'll check for new alerts that haven't been forwarded
            # In practice, you might want to modify the existing security alerts
            # service to call the alert manager directly
            
            pass  # Integration point for existing security alerts
            
        except Exception as e:
            logger.error(f"Error forwarding security alerts: {e}")
    
    async def _forward_backup_alerts(self) -> None:
        """Forward backup alerts to centralized alert system"""
        try:
            # Integration with existing backup notification service
            # This would modify the backup service to also send alerts
            # to the centralized alert system
            
            pass  # Integration point for backup alerts
            
        except Exception as e:
            logger.error(f"Error forwarding backup alerts: {e}")
    
    async def _forward_system_alerts(self) -> None:
        """Forward system health alerts"""
        try:
            # This method would process system health issues and 
            # create alerts in the centralized system
            
            pass  # Integration point for system alerts
            
        except Exception as e:
            logger.error(f"Error forwarding system alerts: {e}")
    
    # Health Processing Methods
    
    async def _process_health_data(self, health_data: Dict[str, Any]) -> None:
        """Process health data and generate appropriate alerts"""
        try:
            current_time = datetime.now(timezone.utc)
            
            # Check overall system health
            overall_status = health_data.get('overall', 'healthy')
            if overall_status != 'healthy':
                # Create system health alert
                await self._create_system_health_alert(overall_status, health_data, current_time)
            
            # Check individual service health
            services = health_data.get('services', {})
            for service_name, service_data in services.items():
                if isinstance(service_data, dict):
                    status = service_data.get('status')
                    if status and status != 'healthy':
                        await self._create_service_health_alert(
                            service_name, status, service_data, current_time
                        )
            
        except Exception as e:
            logger.error(f"Error processing health data: {e}")
    
    async def _create_system_health_alert(
        self,
        status: str,
        health_data: Dict[str, Any],
        timestamp: datetime
    ) -> None:
        """Create system health alert"""
        try:
            # Create alert metric
            metric = AlertMetric(
                name="system_overall_health",
                value=0 if status in ['critical', 'unhealthy'] else 1,
                timestamp=timestamp,
                labels={'type': 'system', 'status': status}
            )
            
            # Process through alert manager
            await alert_manager.process_metric(metric)
            
        except Exception as e:
            logger.error(f"Error creating system health alert: {e}")
    
    async def _create_service_health_alert(
        self,
        service_name: str,
        status: str,
        service_data: Dict[str, Any],
        timestamp: datetime
    ) -> None:
        """Create service health alert"""
        try:
            # Create alert metric for service
            metric = AlertMetric(
                name=f"service_health_{service_name}",
                value=0,  # Unhealthy
                timestamp=timestamp,
                labels={
                    'type': 'service',
                    'service': service_name,
                    'status': status
                }
            )
            
            # Process through alert manager
            await alert_manager.process_metric(metric)
            
        except Exception as e:
            logger.error(f"Error creating service health alert for {service_name}: {e}")
    
    async def _check_backup_alerts(self) -> None:
        """Check backup system for alerts that need to be forwarded"""
        try:
            async for db in get_db():
                # Check for recent backup failures
                hour_ago = datetime.now(timezone.utc) - timedelta(hours=1)
                
                failed_backups = await db.execute(
                    select(BackupExecution)
                    .where(
                        and_(
                            BackupExecution.status == 'failed',
                            BackupExecution.started_at >= hour_ago
                        )
                    )
                )
                
                for backup in failed_backups.scalars():
                    # Create backup failure metric
                    metric = AlertMetric(
                        name="backup_failure",
                        value=1,
                        timestamp=backup.started_at or datetime.now(timezone.utc),
                        labels={
                            'type': 'backup',
                            'backup_id': backup.backup_id,
                            'backup_type': backup.backup_type.value if backup.backup_type else 'unknown'
                        }
                    )
                    
                    await alert_manager.process_metric(metric)
                
                break
                
        except Exception as e:
            logger.error(f"Error checking backup alerts: {e}")


# Global integration service instance
alert_integration_service = AlertIntegrationService()


async def initialize_alert_integrations():
    """Initialize alert system integrations"""
    await alert_integration_service.initialize()


async def shutdown_alert_integrations():
    """Shutdown alert system integrations"""
    await alert_integration_service.shutdown()


# Default alert rules for common scenarios
DEFAULT_ALERT_RULES = [
    {
        "name": "High CPU Usage",
        "description": "CPU usage exceeds 85% for sustained period",
        "category": "system_health",
        "severity": "warning",
        "condition": "",
        "threshold_value": 85.0,
        "comparison_operator": ">",
        "evaluation_window_minutes": 5,
        "consecutive_violations": 2,
        "notification_channels": ["email", "slack"],
        "enabled": True
    },
    {
        "name": "Critical CPU Usage",
        "description": "CPU usage exceeds 95% - immediate attention required",
        "category": "system_health", 
        "severity": "critical",
        "condition": "",
        "threshold_value": 95.0,
        "comparison_operator": ">",
        "evaluation_window_minutes": 2,
        "consecutive_violations": 1,
        "notification_channels": ["email", "slack", "pagerduty"],
        "enabled": True
    },
    {
        "name": "High Memory Usage",
        "description": "Memory usage exceeds 90%",
        "category": "system_health",
        "severity": "warning", 
        "condition": "",
        "threshold_value": 90.0,
        "comparison_operator": ">",
        "evaluation_window_minutes": 5,
        "consecutive_violations": 2,
        "notification_channels": ["email", "slack"],
        "enabled": True
    },
    {
        "name": "Disk Space Critical",
        "description": "Disk usage exceeds 95% - critical space shortage",
        "category": "capacity",
        "severity": "critical",
        "condition": "",
        "threshold_value": 95.0,
        "comparison_operator": ">",
        "evaluation_window_minutes": 1,
        "consecutive_violations": 1,
        "notification_channels": ["email", "slack", "pagerduty"],
        "enabled": True
    },
    {
        "name": "Service Down",
        "description": "Critical service is not responding",
        "category": "system_health",
        "severity": "critical",
        "condition": "",
        "threshold_value": 0,
        "comparison_operator": "==",
        "evaluation_window_minutes": 1,
        "consecutive_violations": 1,
        "notification_channels": ["email", "slack", "pagerduty"],
        "enabled": True
    },
    {
        "name": "Database Response Time High", 
        "description": "Database response time exceeds 1 second",
        "category": "performance",
        "severity": "warning",
        "condition": "",
        "threshold_value": 1000.0,
        "comparison_operator": ">",
        "evaluation_window_minutes": 3,
        "consecutive_violations": 2,
        "notification_channels": ["email", "slack"],
        "enabled": True
    },
    {
        "name": "Backup Failure",
        "description": "Backup operation failed",
        "category": "backup_system",
        "severity": "critical",
        "condition": "",
        "threshold_value": 1,
        "comparison_operator": ">=",
        "evaluation_window_minutes": 1,
        "consecutive_violations": 1,
        "notification_channels": ["email", "slack", "pagerduty"],
        "enabled": True
    },
    {
        "name": "Failed Login Attempts",
        "description": "High number of failed login attempts detected",
        "category": "security_incident",
        "severity": "warning",
        "condition": "",
        "threshold_value": 10.0,
        "comparison_operator": ">",
        "evaluation_window_minutes": 10,
        "consecutive_violations": 1,
        "notification_channels": ["email", "slack"],
        "enabled": True
    },
    {
        "name": "Security Event Critical",
        "description": "Critical security events detected",
        "category": "security_incident",
        "severity": "critical",
        "condition": "",
        "threshold_value": 1.0,
        "comparison_operator": ">=",
        "evaluation_window_minutes": 1,
        "consecutive_violations": 1,
        "notification_channels": ["email", "slack", "pagerduty"],
        "enabled": True
    }
]


async def create_default_alert_rules(admin_user_id: int) -> None:
    """Create default alert rules for new installations"""
    try:
        from uuid import uuid4
        
        logger.info("Creating default alert rules...")
        
        for rule_data in DEFAULT_ALERT_RULES:
            # Check if rule already exists (by name)
            existing_rules = alert_manager.get_alert_rules()
            if any(rule.name == rule_data["name"] for rule in existing_rules.values()):
                continue
            
            # Create rule
            rule = AlertRule(
                id=str(uuid4()),
                name=rule_data["name"],
                description=rule_data["description"],
                category=AlertCategory(rule_data["category"]),
                severity=AlertSeverity(rule_data["severity"]),
                condition=rule_data["condition"],
                threshold_value=rule_data["threshold_value"],
                comparison_operator=rule_data["comparison_operator"],
                evaluation_window_minutes=rule_data["evaluation_window_minutes"],
                consecutive_violations=rule_data["consecutive_violations"],
                enabled=rule_data["enabled"],
                notification_channels=[
                    NotificationChannel(ch) for ch in rule_data["notification_channels"]
                ],
                created_at=datetime.now(timezone.utc),
                created_by=admin_user_id
            )
            
            await alert_manager.create_alert_rule(rule, admin_user_id)
            logger.info(f"Created default alert rule: {rule.name}")
        
        logger.info("Default alert rules creation completed")
        
    except Exception as e:
        logger.error(f"Error creating default alert rules: {e}")
        raise