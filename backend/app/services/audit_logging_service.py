"""
Comprehensive Audit Logging Service for Phase 2 DuckDB Analytics System
====================================================================

Advanced audit logging system with structured logging, security event tracking,
and comprehensive audit trail for the complete Phase 2 analytics platform.

Features:
- Structured JSON logging with correlation IDs
- Security event detection and logging
- User activity tracking and session management
- Administrative action logging
- Data processing audit trail
- System change logging (deployments, configuration)
- PCI/SOC2 compliance logging
- Log aggregation and search capabilities
- Sensitive data redaction and privacy protection
- Log retention and archival policies
- Real-time security monitoring integration
"""

import asyncio
import hashlib
import json
import logging
import os
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Any, Set, Union
from uuid import uuid4
import re

import aiofiles
import redis.asyncio as aioredis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.services.monitoring_service import monitoring_service

logger = logging.getLogger(__name__)


class AuditEventType(str, Enum):
    """Types of audit events"""
    # Authentication and Authorization
    USER_LOGIN = "user_login"
    USER_LOGOUT = "user_logout"
    USER_LOGIN_FAILED = "user_login_failed"
    USER_PASSWORD_CHANGED = "user_password_changed"
    USER_LOCKED = "user_locked"
    USER_UNLOCKED = "user_unlocked"
    SESSION_EXPIRED = "session_expired"
    SESSION_INVALIDATED = "session_invalidated"
    
    # User Management
    USER_CREATED = "user_created"
    USER_UPDATED = "user_updated"
    USER_DELETED = "user_deleted"
    USER_ROLE_CHANGED = "user_role_changed"
    USER_PERMISSIONS_CHANGED = "user_permissions_changed"
    USER_APPROVED = "user_approved"
    USER_REJECTED = "user_rejected"
    
    # Data Access and Manipulation
    DATA_ACCESSED = "data_accessed"
    DATA_CREATED = "data_created"
    DATA_UPDATED = "data_updated"
    DATA_DELETED = "data_deleted"
    DATA_EXPORTED = "data_exported"
    DATA_IMPORTED = "data_imported"
    BULK_OPERATION = "bulk_operation"
    
    # Project and Resource Management
    PROJECT_CREATED = "project_created"
    PROJECT_UPDATED = "project_updated"
    PROJECT_DELETED = "project_deleted"
    PROJECT_SHARED = "project_shared"
    PROJECT_ACCESS_GRANTED = "project_access_granted"
    PROJECT_ACCESS_REVOKED = "project_access_revoked"
    
    # System Operations
    SYSTEM_STARTUP = "system_startup"
    SYSTEM_SHUTDOWN = "system_shutdown"
    SERVICE_STARTED = "service_started"
    SERVICE_STOPPED = "service_stopped"
    CONFIGURATION_CHANGED = "configuration_changed"
    DATABASE_MIGRATION = "database_migration"
    BACKUP_CREATED = "backup_created"
    BACKUP_RESTORED = "backup_restored"
    
    # Security Events
    SECURITY_BREACH_DETECTED = "security_breach_detected"
    SUSPICIOUS_ACTIVITY = "suspicious_activity"
    UNAUTHORIZED_ACCESS_ATTEMPT = "unauthorized_access_attempt"
    PRIVILEGE_ESCALATION_ATTEMPT = "privilege_escalation_attempt"
    MULTIPLE_FAILED_LOGINS = "multiple_failed_logins"
    IP_BLOCKED = "ip_blocked"
    RATE_LIMIT_EXCEEDED = "rate_limit_exceeded"
    
    # Analytics and DuckDB Events
    ANALYTICS_QUERY_EXECUTED = "analytics_query_executed"
    DUCKDB_CONNECTION_CREATED = "duckdb_connection_created"
    DUCKDB_QUERY_FAILED = "duckdb_query_failed"
    DATA_SYNC_STARTED = "data_sync_started"
    DATA_SYNC_COMPLETED = "data_sync_completed"
    DATA_SYNC_FAILED = "data_sync_failed"
    PARQUET_PROCESSING_STARTED = "parquet_processing_started"
    PARQUET_PROCESSING_COMPLETED = "parquet_processing_completed"
    
    # API and WebSocket Events
    API_REQUEST = "api_request"
    API_RESPONSE = "api_response"
    WEBSOCKET_CONNECTED = "websocket_connected"
    WEBSOCKET_DISCONNECTED = "websocket_disconnected"
    WEBHOOK_SENT = "webhook_sent"
    WEBHOOK_RECEIVED = "webhook_received"


class AuditSeverity(str, Enum):
    """Severity levels for audit events"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class AuditOutcome(str, Enum):
    """Outcome of audited operations"""
    SUCCESS = "success"
    FAILURE = "failure"
    PARTIAL = "partial"
    UNKNOWN = "unknown"


@dataclass
class AuditEvent:
    """Structured audit event"""
    event_id: str = field(default_factory=lambda: uuid4().hex)
    timestamp: datetime = field(default_factory=datetime.utcnow)
    event_type: AuditEventType = AuditEventType.API_REQUEST
    severity: AuditSeverity = AuditSeverity.LOW
    outcome: AuditOutcome = AuditOutcome.SUCCESS
    
    # Actor information
    user_id: Optional[str] = None
    username: Optional[str] = None
    session_id: Optional[str] = None
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    
    # Resource information
    resource_type: Optional[str] = None
    resource_id: Optional[str] = None
    resource_name: Optional[str] = None
    
    # Operation details
    operation: Optional[str] = None
    description: str = ""
    details: Dict[str, Any] = field(default_factory=dict)
    
    # Context and correlation
    correlation_id: Optional[str] = None
    parent_event_id: Optional[str] = None
    request_id: Optional[str] = None
    
    # Compliance and classification
    sensitive_data: bool = False
    compliance_tags: Set[str] = field(default_factory=set)
    data_classification: Optional[str] = None
    
    # Technical details
    component: str = "unknown"
    service_version: Optional[str] = None
    environment: str = getattr(settings, 'ENVIRONMENT', 'development')
    
    # Performance metrics
    duration_ms: Optional[float] = None
    bytes_processed: Optional[int] = None
    records_affected: Optional[int] = None
    
    # Error information
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    stack_trace: Optional[str] = None


@dataclass
class SecurityEvent:
    """Specialized security event"""
    event_id: str = field(default_factory=lambda: uuid4().hex)
    timestamp: datetime = field(default_factory=datetime.utcnow)
    event_type: str = ""
    severity: AuditSeverity = AuditSeverity.MEDIUM
    
    # Threat information
    threat_level: str = "low"  # low, medium, high, critical
    attack_type: Optional[str] = None
    indicators: List[str] = field(default_factory=list)
    
    # Source information
    source_ip: Optional[str] = None
    source_country: Optional[str] = None
    source_asn: Optional[str] = None
    user_agent: Optional[str] = None
    
    # Target information
    target_resource: Optional[str] = None
    target_endpoint: Optional[str] = None
    
    # Detection information
    detection_rule: Optional[str] = None
    detection_confidence: float = 0.0
    false_positive_probability: float = 0.0
    
    # Response information
    action_taken: Optional[str] = None
    blocked: bool = False
    investigation_required: bool = False
    
    # Context
    context: Dict[str, Any] = field(default_factory=dict)
    related_events: List[str] = field(default_factory=list)


class AuditLoggingService:
    """
    Comprehensive audit logging service for Phase 2 DuckDB analytics system
    
    Provides structured audit logging with security event detection, compliance
    tracking, and integration with monitoring and alerting systems.
    """
    
    def __init__(self):
        self.redis_client: Optional[aioredis.Redis] = None
        self._audit_buffer: List[AuditEvent] = []
        self._security_buffer: List[SecurityEvent] = []
        self._max_buffer_size = 1000
        self._buffer_flush_interval = 60  # seconds
        
        # Log files
        self._audit_log_path = Path(getattr(settings, 'AUDIT_LOG_PATH', 'logs/audit.jsonl'))
        self._security_log_path = Path(getattr(settings, 'SECURITY_LOG_PATH', 'logs/security.jsonl'))
        
        # Sensitive data patterns for redaction
        self._sensitive_patterns = [
            r'password["\']?\s*:\s*["\'][^"\']+["\']',  # passwords
            r'token["\']?\s*:\s*["\'][^"\']+["\']',     # tokens
            r'key["\']?\s*:\s*["\'][^"\']+["\']',       # keys
            r'secret["\']?\s*:\s*["\'][^"\']+["\']',    # secrets
            r'\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b',  # credit cards
            r'\b\d{3}-\d{2}-\d{4}\b',                  # SSNs
            r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'  # emails (optional)
        ]
        
        # Compliance frameworks
        self._compliance_frameworks = {
            'PCI_DSS',
            'SOC2',
            'GDPR',
            'HIPAA',
            'SOX'
        }
        
        # Background tasks
        self._background_tasks: Set[asyncio.Task] = set()
        self._shutdown_event = asyncio.Event()
        
        # Security monitoring
        self._failed_login_attempts: Dict[str, List[datetime]] = {}
        self._suspicious_ips: Set[str] = set()
        self._rate_limit_violations: Dict[str, List[datetime]] = {}
        
        logger.info("AuditLoggingService initialized")
    
    async def initialize(self):
        """Initialize audit logging service and background tasks"""
        try:
            # Initialize Redis connection
            self.redis_client = aioredis.Redis(
                host=settings.REDIS_HOST,
                port=6379,
                db=5,  # Dedicated DB for audit logging
                decode_responses=True,
                socket_timeout=5.0
            )
            
            # Test Redis connection
            await self.redis_client.ping()
            logger.info("AuditLoggingService Redis connection established")
            
            # Ensure log directories exist
            self._audit_log_path.parent.mkdir(parents=True, exist_ok=True)
            self._security_log_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Start background tasks
            await self._start_background_tasks()
            
            # Log service startup
            await self.log_system_event(
                AuditEventType.SERVICE_STARTED,
                "Audit Logging Service started",
                component="audit_logging_service"
            )
            
        except Exception as e:
            logger.error(f"Failed to initialize AuditLoggingService: {e}")
            raise
    
    async def _start_background_tasks(self):
        """Start background tasks for audit processing"""
        # Buffer flush task
        flush_task = asyncio.create_task(self._buffer_flush_loop())
        self._background_tasks.add(flush_task)
        flush_task.add_done_callback(self._background_tasks.discard)
        
        # Log rotation task
        rotation_task = asyncio.create_task(self._log_rotation_loop())
        self._background_tasks.add(rotation_task)
        rotation_task.add_done_callback(self._background_tasks.discard)
        
        # Security monitoring task
        security_task = asyncio.create_task(self._security_monitoring_loop())
        self._background_tasks.add(security_task)
        security_task.add_done_callback(self._background_tasks.discard)
        
        logger.info("AuditLoggingService background tasks started")
    
    async def _buffer_flush_loop(self):
        """Background loop for flushing audit buffers to storage"""
        while not self._shutdown_event.is_set():
            try:
                await self._flush_buffers()
                await asyncio.sleep(self._buffer_flush_interval)
                
            except Exception as e:
                logger.error(f"Error in buffer flush loop: {e}")
                await asyncio.sleep(60)
    
    async def _log_rotation_loop(self):
        """Background loop for log file rotation"""
        while not self._shutdown_event.is_set():
            try:
                await self._rotate_logs_if_needed()
                await asyncio.sleep(3600)  # Check hourly
                
            except Exception as e:
                logger.error(f"Error in log rotation loop: {e}")
                await asyncio.sleep(3600)
    
    async def _security_monitoring_loop(self):
        """Background loop for security monitoring and threat detection"""
        while not self._shutdown_event.is_set():
            try:
                await self._analyze_security_patterns()
                await asyncio.sleep(300)  # Check every 5 minutes
                
            except Exception as e:
                logger.error(f"Error in security monitoring loop: {e}")
                await asyncio.sleep(300)
    
    # Public API methods for logging different types of events
    
    async def log_user_activity(
        self,
        user_id: str,
        username: str,
        event_type: AuditEventType,
        description: str,
        session_id: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
        operation: Optional[str] = None,
        outcome: AuditOutcome = AuditOutcome.SUCCESS,
        details: Optional[Dict[str, Any]] = None,
        correlation_id: Optional[str] = None
    ) -> str:
        """Log user activity event"""
        
        event = AuditEvent(
            event_type=event_type,
            severity=self._get_event_severity(event_type),
            outcome=outcome,
            user_id=user_id,
            username=username,
            session_id=session_id,
            ip_address=ip_address,
            user_agent=user_agent,
            resource_type=resource_type,
            resource_id=resource_id,
            operation=operation,
            description=description,
            details=details or {},
            correlation_id=correlation_id,
            component="user_activity",
            sensitive_data=self._contains_sensitive_data(description, details or {})
        )
        
        await self._add_audit_event(event)
        
        # Check for security implications
        await self._analyze_user_activity(event)
        
        return event.event_id
    
    async def log_system_event(
        self,
        event_type: AuditEventType,
        description: str,
        component: str = "system",
        severity: Optional[AuditSeverity] = None,
        outcome: AuditOutcome = AuditOutcome.SUCCESS,
        details: Optional[Dict[str, Any]] = None,
        duration_ms: Optional[float] = None,
        correlation_id: Optional[str] = None
    ) -> str:
        """Log system-level event"""
        
        event = AuditEvent(
            event_type=event_type,
            severity=severity or self._get_event_severity(event_type),
            outcome=outcome,
            component=component,
            description=description,
            details=details or {},
            duration_ms=duration_ms,
            correlation_id=correlation_id,
            service_version=getattr(settings, 'VERSION', '1.0.0')
        )
        
        await self._add_audit_event(event)
        return event.event_id
    
    async def log_data_access(
        self,
        user_id: str,
        username: str,
        operation: str,
        resource_type: str,
        resource_id: str,
        resource_name: Optional[str] = None,
        outcome: AuditOutcome = AuditOutcome.SUCCESS,
        records_affected: Optional[int] = None,
        bytes_processed: Optional[int] = None,
        duration_ms: Optional[float] = None,
        ip_address: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        correlation_id: Optional[str] = None
    ) -> str:
        """Log data access event"""
        
        event_type = self._get_data_event_type(operation)
        
        event = AuditEvent(
            event_type=event_type,
            severity=self._get_data_access_severity(operation, records_affected),
            outcome=outcome,
            user_id=user_id,
            username=username,
            ip_address=ip_address,
            resource_type=resource_type,
            resource_id=resource_id,
            resource_name=resource_name,
            operation=operation,
            description=f"Data {operation} operation on {resource_type}",
            details=details or {},
            correlation_id=correlation_id,
            component="data_access",
            duration_ms=duration_ms,
            bytes_processed=bytes_processed,
            records_affected=records_affected,
            sensitive_data=True,  # Assume data access involves sensitive data
            compliance_tags={'PCI_DSS', 'SOC2', 'GDPR'}
        )
        
        await self._add_audit_event(event)
        return event.event_id
    
    async def log_analytics_event(
        self,
        user_id: Optional[str],
        username: Optional[str],
        query_type: str,
        query_text: Optional[str] = None,
        duration_ms: Optional[float] = None,
        records_returned: Optional[int] = None,
        outcome: AuditOutcome = AuditOutcome.SUCCESS,
        error_message: Optional[str] = None,
        component: str = "analytics",
        correlation_id: Optional[str] = None
    ) -> str:
        """Log analytics query event"""
        
        # Redact sensitive information from query text
        redacted_query = self._redact_sensitive_data(query_text) if query_text else None
        
        event = AuditEvent(
            event_type=AuditEventType.ANALYTICS_QUERY_EXECUTED,
            severity=AuditSeverity.LOW if outcome == AuditOutcome.SUCCESS else AuditSeverity.MEDIUM,
            outcome=outcome,
            user_id=user_id,
            username=username,
            operation="analytics_query",
            description=f"Analytics query executed: {query_type}",
            details={
                "query_type": query_type,
                "query_text": redacted_query,
                "records_returned": records_returned,
                "error_message": error_message
            },
            correlation_id=correlation_id,
            component=component,
            duration_ms=duration_ms,
            records_affected=records_returned,
            error_message=error_message if outcome == AuditOutcome.FAILURE else None
        )
        
        await self._add_audit_event(event)
        return event.event_id
    
    async def log_security_event(
        self,
        event_type: str,
        description: str,
        severity: AuditSeverity = AuditSeverity.MEDIUM,
        source_ip: Optional[str] = None,
        user_id: Optional[str] = None,
        threat_level: str = "medium",
        attack_type: Optional[str] = None,
        indicators: Optional[List[str]] = None,
        action_taken: Optional[str] = None,
        blocked: bool = False,
        context: Optional[Dict[str, Any]] = None
    ) -> str:
        """Log security event"""
        
        security_event = SecurityEvent(
            event_type=event_type,
            severity=severity,
            threat_level=threat_level,
            attack_type=attack_type,
            indicators=indicators or [],
            source_ip=source_ip,
            action_taken=action_taken,
            blocked=blocked,
            investigation_required=severity in [AuditSeverity.HIGH, AuditSeverity.CRITICAL],
            context=context or {}
        )
        
        # Also create audit event
        audit_event = AuditEvent(
            event_type=AuditEventType.SECURITY_BREACH_DETECTED,
            severity=severity,
            outcome=AuditOutcome.SUCCESS if not blocked else AuditOutcome.FAILURE,
            user_id=user_id,
            ip_address=source_ip,
            description=description,
            details={
                "security_event_id": security_event.event_id,
                "threat_level": threat_level,
                "attack_type": attack_type,
                "action_taken": action_taken,
                "blocked": blocked
            },
            component="security",
            sensitive_data=True,
            compliance_tags={'SOC2', 'PCI_DSS'}
        )
        
        await self._add_security_event(security_event)
        await self._add_audit_event(audit_event)
        
        # Send alert for high-severity security events
        if severity in [AuditSeverity.HIGH, AuditSeverity.CRITICAL]:
            await self._send_security_alert(security_event)
        
        return security_event.event_id
    
    async def log_api_request(
        self,
        method: str,
        endpoint: str,
        status_code: int,
        duration_ms: float,
        user_id: Optional[str] = None,
        username: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        request_size: Optional[int] = None,
        response_size: Optional[int] = None,
        correlation_id: Optional[str] = None
    ) -> str:
        """Log API request"""
        
        outcome = AuditOutcome.SUCCESS if status_code < 400 else AuditOutcome.FAILURE
        severity = AuditSeverity.LOW
        
        # Increase severity for errors or suspicious patterns
        if status_code >= 500:
            severity = AuditSeverity.HIGH
        elif status_code >= 400:
            severity = AuditSeverity.MEDIUM
        elif duration_ms > 10000:  # > 10 seconds
            severity = AuditSeverity.MEDIUM
        
        event = AuditEvent(
            event_type=AuditEventType.API_REQUEST,
            severity=severity,
            outcome=outcome,
            user_id=user_id,
            username=username,
            ip_address=ip_address,
            user_agent=user_agent,
            operation=f"{method} {endpoint}",
            description=f"API request: {method} {endpoint} -> {status_code}",
            details={
                "method": method,
                "endpoint": endpoint,
                "status_code": status_code,
                "request_size": request_size,
                "response_size": response_size
            },
            correlation_id=correlation_id,
            component="api",
            duration_ms=duration_ms,
            bytes_processed=response_size
        )
        
        await self._add_audit_event(event)
        
        # Analyze for suspicious API usage patterns
        await self._analyze_api_patterns(event)
        
        return event.event_id
    
    # Internal helper methods
    
    async def _add_audit_event(self, event: AuditEvent):
        """Add audit event to buffer"""
        self._audit_buffer.append(event)
        
        # Flush buffer if it's getting full
        if len(self._audit_buffer) >= self._max_buffer_size:
            await self._flush_audit_buffer()
    
    async def _add_security_event(self, event: SecurityEvent):
        """Add security event to buffer"""
        self._security_buffer.append(event)
        
        # Flush security events immediately for high severity
        if event.severity in [AuditSeverity.HIGH, AuditSeverity.CRITICAL]:
            await self._flush_security_buffer()
        elif len(self._security_buffer) >= self._max_buffer_size:
            await self._flush_security_buffer()
    
    async def _flush_buffers(self):
        """Flush all buffers to storage"""
        await self._flush_audit_buffer()
        await self._flush_security_buffer()
    
    async def _flush_audit_buffer(self):
        """Flush audit buffer to log file and Redis"""
        if not self._audit_buffer:
            return
        
        try:
            # Write to log file
            async with aiofiles.open(self._audit_log_path, 'a') as f:
                for event in self._audit_buffer:
                    redacted_event = self._redact_event_sensitive_data(event)
                    json_line = json.dumps(asdict(redacted_event), default=str) + '\n'
                    await f.write(json_line)
            
            # Store recent events in Redis for fast access
            if self.redis_client:
                for event in self._audit_buffer[-100:]:  # Keep last 100 events
                    await self.redis_client.setex(
                        f"audit_event:{event.event_id}",
                        3600,  # 1 hour TTL
                        json.dumps(asdict(event), default=str)
                    )
                
                # Update audit statistics
                await self._update_audit_statistics(self._audit_buffer)
            
            logger.debug(f"Flushed {len(self._audit_buffer)} audit events to storage")
            self._audit_buffer.clear()
            
        except Exception as e:
            logger.error(f"Error flushing audit buffer: {e}")
    
    async def _flush_security_buffer(self):
        """Flush security buffer to log file and Redis"""
        if not self._security_buffer:
            return
        
        try:
            # Write to security log file
            async with aiofiles.open(self._security_log_path, 'a') as f:
                for event in self._security_buffer:
                    json_line = json.dumps(asdict(event), default=str) + '\n'
                    await f.write(json_line)
            
            # Store in Redis for real-time security monitoring
            if self.redis_client:
                for event in self._security_buffer:
                    await self.redis_client.setex(
                        f"security_event:{event.event_id}",
                        86400,  # 24 hours TTL
                        json.dumps(asdict(event), default=str)
                    )
                    
                    # Add to security alerts if high severity
                    if event.severity in [AuditSeverity.HIGH, AuditSeverity.CRITICAL]:
                        await self.redis_client.lpush("security_alerts", event.event_id)
                        await self.redis_client.ltrim("security_alerts", 0, 999)  # Keep 1000 alerts
            
            logger.info(f"Flushed {len(self._security_buffer)} security events to storage")
            self._security_buffer.clear()
            
        except Exception as e:
            logger.error(f"Error flushing security buffer: {e}")
    
    async def _update_audit_statistics(self, events: List[AuditEvent]):
        """Update audit statistics in Redis"""
        try:
            if not self.redis_client:
                return
            
            # Count by event type
            event_type_counts = {}
            severity_counts = {}
            component_counts = {}
            
            for event in events:
                event_type_counts[event.event_type.value] = event_type_counts.get(event.event_type.value, 0) + 1
                severity_counts[event.severity.value] = severity_counts.get(event.severity.value, 0) + 1
                component_counts[event.component] = component_counts.get(event.component, 0) + 1
            
            # Update Redis counters
            for event_type, count in event_type_counts.items():
                await self.redis_client.incrby(f"audit_stats:event_type:{event_type}", count)
            
            for severity, count in severity_counts.items():
                await self.redis_client.incrby(f"audit_stats:severity:{severity}", count)
            
            for component, count in component_counts.items():
                await self.redis_client.incrby(f"audit_stats:component:{component}", count)
            
            # Update total count
            await self.redis_client.incrby("audit_stats:total_events", len(events))
            
        except Exception as e:
            logger.error(f"Error updating audit statistics: {e}")
    
    def _get_event_severity(self, event_type: AuditEventType) -> AuditSeverity:
        """Get appropriate severity for event type"""
        high_severity_events = {
            AuditEventType.USER_LOGIN_FAILED,
            AuditEventType.USER_LOCKED,
            AuditEventType.UNAUTHORIZED_ACCESS_ATTEMPT,
            AuditEventType.PRIVILEGE_ESCALATION_ATTEMPT,
            AuditEventType.SYSTEM_SHUTDOWN,
            AuditEventType.CONFIGURATION_CHANGED,
            AuditEventType.DATA_DELETED,
            AuditEventType.SECURITY_BREACH_DETECTED
        }
        
        critical_severity_events = {
            AuditEventType.MULTIPLE_FAILED_LOGINS,
            AuditEventType.SUSPICIOUS_ACTIVITY,
            AuditEventType.USER_DELETED
        }
        
        if event_type in critical_severity_events:
            return AuditSeverity.CRITICAL
        elif event_type in high_severity_events:
            return AuditSeverity.HIGH
        elif event_type.value.endswith('_failed') or event_type.value.endswith('_error'):
            return AuditSeverity.MEDIUM
        else:
            return AuditSeverity.LOW
    
    def _get_data_event_type(self, operation: str) -> AuditEventType:
        """Map data operation to appropriate event type"""
        operation_lower = operation.lower()
        
        if 'create' in operation_lower or 'insert' in operation_lower:
            return AuditEventType.DATA_CREATED
        elif 'update' in operation_lower or 'modify' in operation_lower:
            return AuditEventType.DATA_UPDATED
        elif 'delete' in operation_lower or 'remove' in operation_lower:
            return AuditEventType.DATA_DELETED
        elif 'export' in operation_lower:
            return AuditEventType.DATA_EXPORTED
        elif 'import' in operation_lower:
            return AuditEventType.DATA_IMPORTED
        else:
            return AuditEventType.DATA_ACCESSED
    
    def _get_data_access_severity(self, operation: str, records_affected: Optional[int]) -> AuditSeverity:
        """Get severity for data access operations"""
        operation_lower = operation.lower()
        
        # High severity for destructive operations
        if 'delete' in operation_lower or 'remove' in operation_lower:
            return AuditSeverity.HIGH
        
        # Medium severity for modifications or large data access
        if ('update' in operation_lower or 
            'modify' in operation_lower or
            'export' in operation_lower or
            (records_affected and records_affected > 1000)):
            return AuditSeverity.MEDIUM
        
        return AuditSeverity.LOW
    
    def _contains_sensitive_data(self, description: str, details: Dict[str, Any]) -> bool:
        """Check if event contains sensitive data"""
        # Check description
        for pattern in self._sensitive_patterns:
            if re.search(pattern, description, re.IGNORECASE):
                return True
        
        # Check details
        details_str = json.dumps(details, default=str)
        for pattern in self._sensitive_patterns:
            if re.search(pattern, details_str, re.IGNORECASE):
                return True
        
        return False
    
    def _redact_sensitive_data(self, text: Optional[str]) -> Optional[str]:
        """Redact sensitive data from text"""
        if not text:
            return text
        
        redacted_text = text
        for pattern in self._sensitive_patterns:
            redacted_text = re.sub(pattern, '[REDACTED]', redacted_text, flags=re.IGNORECASE)
        
        return redacted_text
    
    def _redact_event_sensitive_data(self, event: AuditEvent) -> AuditEvent:
        """Create redacted copy of audit event"""
        if not event.sensitive_data:
            return event
        
        # Create copy
        redacted_event = AuditEvent(**asdict(event))
        
        # Redact description
        redacted_event.description = self._redact_sensitive_data(event.description)
        
        # Redact details
        redacted_details = {}
        for key, value in event.details.items():
            if isinstance(value, str):
                redacted_details[key] = self._redact_sensitive_data(value)
            else:
                redacted_details[key] = value
        redacted_event.details = redacted_details
        
        return redacted_event
    
    async def _rotate_logs_if_needed(self):
        """Rotate log files if they exceed size limits"""
        try:
            max_size = getattr(settings, 'AUDIT_LOG_MAX_SIZE_MB', 100) * 1024 * 1024  # Default 100MB
            
            for log_path in [self._audit_log_path, self._security_log_path]:
                if log_path.exists() and log_path.stat().st_size > max_size:
                    # Rotate log file
                    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                    rotated_path = log_path.with_name(f"{log_path.stem}_{timestamp}{log_path.suffix}")
                    
                    os.rename(log_path, rotated_path)
                    
                    # Compress old log if compression is enabled
                    if getattr(settings, 'AUDIT_LOG_COMPRESS', True):
                        import gzip
                        with open(rotated_path, 'rb') as f_in:
                            with gzip.open(f"{rotated_path}.gz", 'wb') as f_out:
                                f_out.writelines(f_in)
                        os.remove(rotated_path)
                    
                    logger.info(f"Rotated log file: {log_path}")
            
        except Exception as e:
            logger.error(f"Error rotating logs: {e}")
    
    async def _analyze_user_activity(self, event: AuditEvent):
        """Analyze user activity for security patterns"""
        try:
            if event.event_type == AuditEventType.USER_LOGIN_FAILED:
                await self._track_failed_login(event.ip_address, event.username)
            
            elif event.event_type == AuditEventType.USER_LOGIN and event.ip_address:
                # Check for login from new location
                await self._check_login_location(event.user_id, event.ip_address)
            
            elif event.severity == AuditSeverity.HIGH:
                # Log high-severity user activities for review
                await self._flag_for_review(event)
                
        except Exception as e:
            logger.error(f"Error analyzing user activity: {e}")
    
    async def _track_failed_login(self, ip_address: Optional[str], username: Optional[str]):
        """Track failed login attempts"""
        if not ip_address:
            return
        
        current_time = datetime.utcnow()
        
        # Track by IP
        if ip_address not in self._failed_login_attempts:
            self._failed_login_attempts[ip_address] = []
        
        self._failed_login_attempts[ip_address].append(current_time)
        
        # Remove old attempts (older than 1 hour)
        cutoff_time = current_time - timedelta(hours=1)
        self._failed_login_attempts[ip_address] = [
            attempt for attempt in self._failed_login_attempts[ip_address]
            if attempt > cutoff_time
        ]
        
        # Check if IP should be flagged
        recent_failures = len(self._failed_login_attempts[ip_address])
        if recent_failures >= 10:  # 10 failures in 1 hour
            await self.log_security_event(
                "multiple_failed_logins",
                f"Multiple failed login attempts from IP: {ip_address}",
                AuditSeverity.HIGH,
                source_ip=ip_address,
                threat_level="high",
                attack_type="brute_force",
                indicators=[f"failed_logins:{recent_failures}"],
                action_taken="ip_monitoring",
                investigation_required=True
            )
            
            self._suspicious_ips.add(ip_address)
    
    async def _analyze_api_patterns(self, event: AuditEvent):
        """Analyze API usage patterns for anomalies"""
        try:
            if not event.ip_address:
                return
            
            # Track rate limiting violations
            if event.details.get('status_code') == 429:  # Too Many Requests
                current_time = datetime.utcnow()
                
                if event.ip_address not in self._rate_limit_violations:
                    self._rate_limit_violations[event.ip_address] = []
                
                self._rate_limit_violations[event.ip_address].append(current_time)
                
                # Check for persistent rate limit violations
                hour_ago = current_time - timedelta(hours=1)
                recent_violations = [
                    violation for violation in self._rate_limit_violations[event.ip_address]
                    if violation > hour_ago
                ]
                
                if len(recent_violations) >= 50:  # 50 rate limit violations in 1 hour
                    await self.log_security_event(
                        "persistent_rate_limit_violations",
                        f"Persistent rate limit violations from IP: {event.ip_address}",
                        AuditSeverity.MEDIUM,
                        source_ip=event.ip_address,
                        threat_level="medium",
                        attack_type="dos_attempt",
                        indicators=[f"rate_limit_violations:{len(recent_violations)}"],
                        action_taken="monitoring"
                    )
            
        except Exception as e:
            logger.error(f"Error analyzing API patterns: {e}")
    
    async def _analyze_security_patterns(self):
        """Analyze stored events for security patterns"""
        try:
            # This would implement more sophisticated pattern analysis
            # For now, we'll do basic checks on tracked metrics
            
            current_time = datetime.utcnow()
            
            # Clean up old tracking data
            hour_ago = current_time - timedelta(hours=1)
            
            for ip in list(self._failed_login_attempts.keys()):
                self._failed_login_attempts[ip] = [
                    attempt for attempt in self._failed_login_attempts[ip]
                    if attempt > hour_ago
                ]
                if not self._failed_login_attempts[ip]:
                    del self._failed_login_attempts[ip]
            
            for ip in list(self._rate_limit_violations.keys()):
                self._rate_limit_violations[ip] = [
                    violation for violation in self._rate_limit_violations[ip]
                    if violation > hour_ago
                ]
                if not self._rate_limit_violations[ip]:
                    del self._rate_limit_violations[ip]
            
        except Exception as e:
            logger.error(f"Error in security pattern analysis: {e}")
    
    async def _send_security_alert(self, security_event: SecurityEvent):
        """Send security alert to monitoring system"""
        try:
            # Integration with alerting service
            from app.services.alerting_service import alerting_service
            
            await alerting_service.create_alert(
                title=f"Security Event: {security_event.event_type}",
                description=f"Threat level: {security_event.threat_level}",
                severity="critical" if security_event.severity == AuditSeverity.CRITICAL else "high",
                component="security",
                metric="security_event",
                current_value=security_event.threat_level,
                correlation_id=security_event.event_id,
                context=security_event.context
            )
            
        except Exception as e:
            logger.error(f"Error sending security alert: {e}")
    
    async def _flag_for_review(self, event: AuditEvent):
        """Flag event for manual review"""
        try:
            if self.redis_client:
                await self.redis_client.lpush("events_for_review", event.event_id)
                await self.redis_client.ltrim("events_for_review", 0, 999)  # Keep 1000 events
                
        except Exception as e:
            logger.error(f"Error flagging event for review: {e}")
    
    # Public query methods
    
    async def search_events(
        self,
        event_types: Optional[List[AuditEventType]] = None,
        severity: Optional[AuditSeverity] = None,
        user_id: Optional[str] = None,
        component: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Search audit events with filters"""
        try:
            if not self.redis_client:
                return []
            
            # For now, return recent events from Redis
            # In production, this would query a proper search backend like Elasticsearch
            recent_events = []
            
            keys = await self.redis_client.keys("audit_event:*")
            for key in keys[:limit]:
                event_data = await self.redis_client.get(key)
                if event_data:
                    event = json.loads(event_data)
                    recent_events.append(event)
            
            return recent_events
            
        except Exception as e:
            logger.error(f"Error searching events: {e}")
            return []
    
    async def get_audit_statistics(self) -> Dict[str, Any]:
        """Get audit logging statistics"""
        try:
            if not self.redis_client:
                return {}
            
            stats = {}
            
            # Get total events
            total_events = await self.redis_client.get("audit_stats:total_events")
            stats["total_events"] = int(total_events) if total_events else 0
            
            # Get event type breakdown
            event_type_keys = await self.redis_client.keys("audit_stats:event_type:*")
            event_type_stats = {}
            for key in event_type_keys:
                event_type = key.split(":")[-1]
                count = await self.redis_client.get(key)
                event_type_stats[event_type] = int(count) if count else 0
            stats["event_types"] = event_type_stats
            
            # Get severity breakdown
            severity_keys = await self.redis_client.keys("audit_stats:severity:*")
            severity_stats = {}
            for key in severity_keys:
                severity = key.split(":")[-1]
                count = await self.redis_client.get(key)
                severity_stats[severity] = int(count) if count else 0
            stats["severities"] = severity_stats
            
            # Get component breakdown
            component_keys = await self.redis_client.keys("audit_stats:component:*")
            component_stats = {}
            for key in component_keys:
                component = key.split(":")[-1]
                count = await self.redis_client.get(key)
                component_stats[component] = int(count) if count else 0
            stats["components"] = component_stats
            
            # Additional metrics
            stats["buffer_sizes"] = {
                "audit_buffer": len(self._audit_buffer),
                "security_buffer": len(self._security_buffer)
            }
            
            stats["security_metrics"] = {
                "suspicious_ips": len(self._suspicious_ips),
                "failed_login_tracking": len(self._failed_login_attempts),
                "rate_limit_violations": len(self._rate_limit_violations)
            }
            
            return stats
            
        except Exception as e:
            logger.error(f"Error getting audit statistics: {e}")
            return {"error": str(e)}
    
    async def shutdown(self):
        """Cleanup audit logging service resources"""
        try:
            # Signal shutdown to background tasks
            self._shutdown_event.set()
            
            # Wait for background tasks to complete
            if self._background_tasks:
                await asyncio.gather(*self._background_tasks, return_exceptions=True)
            
            # Flush remaining events
            await self._flush_buffers()
            
            # Log service shutdown
            await self.log_system_event(
                AuditEventType.SERVICE_STOPPED,
                "Audit Logging Service stopped",
                component="audit_logging_service"
            )
            
            # Final flush
            await self._flush_buffers()
            
            # Close Redis connection
            if self.redis_client:
                await self.redis_client.close()
            
            logger.info("AuditLoggingService shutdown completed")
            
        except Exception as e:
            logger.error(f"Error during AuditLoggingService shutdown: {e}")


# Global audit logging service instance
audit_logging_service = AuditLoggingService()


# FastAPI dependency
async def get_audit_logging_service() -> AuditLoggingService:
    """FastAPI dependency for audit logging service"""
    if not audit_logging_service.redis_client:
        await audit_logging_service.initialize()
    return audit_logging_service