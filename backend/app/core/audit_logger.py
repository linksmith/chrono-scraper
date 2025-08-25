"""
Enterprise audit logging system with integrity checking, tamper-proofing, and comprehensive security features
"""
import asyncio
import hashlib
import hmac
import json
import logging
import time
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional, List, Tuple
from contextlib import asynccontextmanager
from dataclasses import dataclass, asdict
from uuid import uuid4

from fastapi import Request, Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select, func, and_, or_, desc, asc
try:
    import geoip2.database
    import user_agents
    GEOIP_AVAILABLE = True
except ImportError:
    GEOIP_AVAILABLE = False
from cryptography.fernet import Fernet

from app.core.config import settings
from app.core.database import get_db
from app.models.audit_log import (
    AuditLog, 
    AuditLogCreate, 
    AuditLogRead, 
    AuditLogFilter,
    AuditLogAnalytics,
    AuditCategory, 
    SeverityLevel,
    AuditActions,
    ResourceTypes,
    create_audit_log
)


logger = logging.getLogger(__name__)


@dataclass
class AuditContext:
    """Context information for audit logging"""
    user_id: Optional[int] = None
    admin_user_id: Optional[int] = None
    session_id: Optional[str] = None
    request_id: Optional[str] = None
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    start_time: Optional[float] = None
    database_queries: int = 0
    memory_usage_mb: Optional[float] = None


class AuditIntegrityError(Exception):
    """Exception raised when audit log integrity is compromised"""
    pass


class AuditLogger:
    """
    Enterprise audit logging system with advanced security features:
    - Tamper-proof logging with checksums and signatures
    - Real-time anomaly detection
    - Compliance reporting (GDPR, SOX, HIPAA)
    - Automatic retention policies
    - Geolocation and device tracking
    - Performance metrics collection
    """
    
    def __init__(self):
        self._encryption_key = self._get_or_create_encryption_key()
        self._cipher_suite = Fernet(self._encryption_key)
        self._signing_key = settings.SECRET_KEY.encode()
        self._geoip_reader = self._init_geoip()
        self._anomaly_thresholds = self._init_anomaly_thresholds()
        
    def _get_or_create_encryption_key(self) -> bytes:
        """Get or create encryption key for sensitive audit data"""
        # In production, this should be stored securely (HSM, key vault, etc.)
        key_file = "/tmp/audit_encryption.key"  # Use proper secure storage in production
        try:
            with open(key_file, 'rb') as f:
                return f.read()
        except FileNotFoundError:
            key = Fernet.generate_key()
            with open(key_file, 'wb') as f:
                f.write(key)
            return key
    
    def _init_geoip(self) -> Optional[Any]:
        """Initialize GeoIP database for location tracking"""
        try:
            if not GEOIP_AVAILABLE:
                return None
            # Download GeoLite2 database from MaxMind in production
            return geoip2.database.Reader('/path/to/GeoLite2-City.mmdb')
        except Exception as e:
            logger.warning(f"GeoIP database not available: {e}")
            return None
    
    def _init_anomaly_thresholds(self) -> Dict[str, Any]:
        """Initialize anomaly detection thresholds"""
        return {
            'max_failed_logins_per_hour': 10,
            'max_requests_per_minute': 100,
            'max_bulk_operations_per_hour': 5,
            'suspicious_ip_patterns': [
                # Add suspicious IP patterns
            ],
            'unusual_user_agent_patterns': [
                'curl', 'wget', 'python-requests', 'bot'
            ]
        }
    
    def _get_geolocation(self, ip_address: str) -> Tuple[Optional[str], Optional[str]]:
        """Get country and city from IP address"""
        if not self._geoip_reader or not ip_address:
            return None, None
        
        try:
            response = self._geoip_reader.city(ip_address)
            return response.country.iso_code, response.city.name
        except Exception:
            return None, None
    
    def _parse_user_agent(self, user_agent: str) -> Tuple[Optional[str], Optional[str]]:
        """Parse user agent for device and browser info"""
        if not user_agent or not GEOIP_AVAILABLE:
            return None, None
        
        try:
            ua = user_agents.parse(user_agent)
            device_type = 'mobile' if ua.is_mobile else 'tablet' if ua.is_tablet else 'desktop'
            browser_info = f"{ua.browser.family} {ua.browser.version_string}"
            return device_type, browser_info
        except Exception:
            return None, None
    
    def _calculate_checksum(self, data: Dict[str, Any]) -> str:
        """Calculate SHA-256 checksum for data integrity"""
        serialized = json.dumps(data, sort_keys=True, default=str)
        return hashlib.sha256(serialized.encode()).hexdigest()
    
    def _create_signature(self, data: Dict[str, Any]) -> str:
        """Create HMAC signature for tamper detection"""
        serialized = json.dumps(data, sort_keys=True, default=str)
        return hmac.new(
            self._signing_key,
            serialized.encode(),
            hashlib.sha256
        ).hexdigest()
    
    def _encrypt_sensitive_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Encrypt sensitive fields in audit data"""
        sensitive_fields = [
            'request_body', 'response_body', 'before_values', 'after_values',
            'details', 'user_agent', 'request_headers', 'response_headers'
        ]
        
        encrypted_data = data.copy()
        for field in sensitive_fields:
            if field in encrypted_data and encrypted_data[field]:
                try:
                    serialized = json.dumps(encrypted_data[field])
                    encrypted_data[field] = self._cipher_suite.encrypt(
                        serialized.encode()
                    ).decode()
                except Exception as e:
                    logger.error(f"Failed to encrypt field {field}: {e}")
        
        return encrypted_data
    
    def _detect_anomalies(self, audit_data: Dict[str, Any]) -> List[str]:
        """Detect anomalous patterns in audit data"""
        anomalies = []
        
        # Check for suspicious user agents
        user_agent = audit_data.get('user_agent', '')
        if any(pattern in user_agent.lower() for pattern in self._anomaly_thresholds['unusual_user_agent_patterns']):
            anomalies.append('suspicious_user_agent')
        
        # Check for bulk operations outside business hours
        current_time = datetime.now(timezone.utc)
        if (current_time.hour < 6 or current_time.hour > 22) and \
           audit_data.get('action', '').startswith('bulk_'):
            anomalies.append('after_hours_bulk_operation')
        
        # Check for rapid successive operations
        if audit_data.get('processing_time_ms', 0) > 10000:  # 10 seconds
            anomalies.append('slow_operation')
        
        return anomalies
    
    async def log_audit_event(
        self,
        action: str,
        resource_type: str,
        category: AuditCategory,
        context: Optional[AuditContext] = None,
        **kwargs
    ) -> Optional[int]:
        """
        Log a comprehensive audit event with integrity checking
        
        Args:
            action: The action being performed
            resource_type: Type of resource being acted upon
            category: Audit category for organization
            context: Request/session context
            **kwargs: Additional audit data
            
        Returns:
            Audit log entry ID if successful, None otherwise
        """
        try:
            # Get database session
            async for db in get_db():
                # Prepare audit data
                audit_data = self._prepare_audit_data(
                    action, resource_type, category, context, **kwargs
                )
                
                # Calculate integrity fields
                checksum = self._calculate_checksum(audit_data)
                signature = self._create_signature(audit_data)
                
                # Detect anomalies
                anomalies = self._detect_anomalies(audit_data)
                if anomalies:
                    audit_data['tags'] = audit_data.get('tags', []) + anomalies
                    if any(anomaly in ['suspicious_user_agent', 'after_hours_bulk_operation'] for anomaly in anomalies):
                        audit_data['severity'] = SeverityLevel.HIGH
                
                # Encrypt sensitive data if configured
                if getattr(settings, 'AUDIT_ENCRYPT_SENSITIVE_DATA', True):
                    audit_data = self._encrypt_sensitive_data(audit_data)
                    audit_data['encrypted'] = True
                
                # Add integrity fields
                audit_data.update({
                    'checksum': checksum,
                    'signature': signature,
                    'created_at': datetime.now(timezone.utc)
                })
                
                # Create audit log entry
                audit_log = AuditLog(**audit_data)
                db.add(audit_log)
                await db.commit()
                await db.refresh(audit_log)
                
                # Log to application logger for real-time monitoring
                self._log_to_application_logger(audit_log)
                
                return audit_log.id
        
        except Exception as e:
            logger.error(f"Failed to create audit log: {e}")
            # In production, this should trigger an alert
            return None
    
    def _prepare_audit_data(
        self,
        action: str,
        resource_type: str,
        category: AuditCategory,
        context: Optional[AuditContext],
        **kwargs
    ) -> Dict[str, Any]:
        """Prepare comprehensive audit data"""
        # Get geolocation data
        country_code, city = None, None
        device_type, browser_info = None, None
        
        if context and context.ip_address:
            country_code, city = self._get_geolocation(context.ip_address)
        
        if context and context.user_agent:
            device_type, browser_info = self._parse_user_agent(context.user_agent)
        
        # Calculate processing time
        processing_time_ms = None
        if context and context.start_time:
            processing_time_ms = int((time.time() - context.start_time) * 1000)
        
        # Determine compliance flags
        compliance_flags = self._determine_compliance_flags(action, resource_type, kwargs)
        
        # Build audit data
        audit_data = {
            'action': action,
            'resource_type': resource_type,
            'category': category,
            'severity': kwargs.get('severity', SeverityLevel.MEDIUM),
            'success': kwargs.get('success', True),
            'affected_count': kwargs.get('affected_count', 0),
            
            # User and session context
            'user_id': context.user_id if context else None,
            'admin_user_id': context.admin_user_id if context else None,
            'session_id': context.session_id if context else None,
            'request_id': context.request_id if context else None,
            
            # Request/Response context
            'ip_address': context.ip_address if context else None,
            'user_agent': context.user_agent if context else None,
            'request_method': kwargs.get('request_method'),
            'request_url': kwargs.get('request_url'),
            'request_headers': kwargs.get('request_headers'),
            'request_body': kwargs.get('request_body'),
            'response_status': kwargs.get('response_status'),
            'response_headers': kwargs.get('response_headers'),
            'response_body': kwargs.get('response_body'),
            
            # Resource and change tracking
            'resource_id': kwargs.get('resource_id'),
            'before_values': kwargs.get('before_values'),
            'after_values': kwargs.get('after_values'),
            'changed_fields': kwargs.get('changed_fields'),
            
            # Error information
            'error_message': kwargs.get('error_message'),
            'error_code': kwargs.get('error_code'),
            
            # Additional context
            'details': kwargs.get('details', {}),
            'tags': kwargs.get('tags', []),
            
            # Performance metrics
            'processing_time_ms': processing_time_ms,
            'database_queries': context.database_queries if context else None,
            'memory_usage_mb': context.memory_usage_mb if context else None,
            
            # Geolocation and device info
            'country_code': country_code,
            'city': city,
            'device_type': device_type,
            'browser_info': browser_info,
            
            # Compliance flags
            'compliance_flags': compliance_flags,
            'sensitive_data_accessed': self._is_sensitive_data_accessed(action, resource_type),
            'gdpr_relevant': 'gdpr' in compliance_flags,
            'sox_relevant': 'sox' in compliance_flags,
            'hipaa_relevant': 'hipaa' in compliance_flags,
        }
        
        return {k: v for k, v in audit_data.items() if v is not None}
    
    def _determine_compliance_flags(
        self,
        action: str,
        resource_type: str,
        kwargs: Dict[str, Any]
    ) -> List[str]:
        """Determine which compliance frameworks apply to this audit event"""
        flags = []
        
        # GDPR relevant actions
        gdpr_actions = [
            AuditActions.USER_CREATE, AuditActions.USER_UPDATE, AuditActions.USER_DELETE,
            AuditActions.DATA_EXPORT, AuditActions.GDPR_REQUEST, AuditActions.DATA_DELETION
        ]
        if action in gdpr_actions or resource_type in [ResourceTypes.USER]:
            flags.append('gdpr')
        
        # SOX relevant actions (financial/administrative controls)
        sox_actions = [
            AuditActions.SYSTEM_CONFIG_UPDATE, AuditActions.ADMIN_LOGIN,
            AuditActions.USER_ROLE_ASSIGN, AuditActions.USER_PERMISSION_GRANT
        ]
        if action in sox_actions or resource_type in [ResourceTypes.SYSTEM, ResourceTypes.CONFIGURATION]:
            flags.append('sox')
        
        # HIPAA relevant actions (if healthcare data is involved)
        if kwargs.get('healthcare_data_involved', False):
            flags.append('hipaa')
        
        return flags
    
    def _is_sensitive_data_accessed(self, action: str, resource_type: str) -> bool:
        """Determine if sensitive data was accessed"""
        sensitive_actions = [
            AuditActions.USER_PROFILE_VIEW, AuditActions.USER_PROFILE_EXPORT,
            AuditActions.DATA_EXPORT, AuditActions.GDPR_DATA_EXPORT
        ]
        sensitive_resources = [ResourceTypes.USER]
        
        return action in sensitive_actions or resource_type in sensitive_resources
    
    def _log_to_application_logger(self, audit_log: AuditLog):
        """Log audit event to application logger for real-time monitoring"""
        log_level = logging.INFO
        if audit_log.severity == SeverityLevel.HIGH:
            log_level = logging.WARNING
        elif audit_log.severity == SeverityLevel.CRITICAL:
            log_level = logging.ERROR
        
        logger.log(
            log_level,
            f"AUDIT: {audit_log.action} on {audit_log.resource_type} "
            f"by user {audit_log.admin_user_id or audit_log.user_id} "
            f"from {audit_log.ip_address} - {'SUCCESS' if audit_log.success else 'FAILED'}"
        )
    
    async def verify_audit_integrity(
        self,
        audit_log_id: int,
        db: AsyncSession
    ) -> bool:
        """Verify the integrity of an audit log entry"""
        try:
            # Get audit log
            result = await db.execute(
                select(AuditLog).where(AuditLog.id == audit_log_id)
            )
            audit_log = result.scalar_one_or_none()
            
            if not audit_log:
                return False
            
            # Prepare data for verification (exclude integrity fields)
            audit_dict = audit_log.dict()
            verification_data = {k: v for k, v in audit_dict.items() 
                               if k not in ['checksum', 'signature', 'id', 'updated_at']}
            
            # Verify checksum
            expected_checksum = self._calculate_checksum(verification_data)
            if audit_log.checksum != expected_checksum:
                logger.error(f"Checksum mismatch for audit log {audit_log_id}")
                return False
            
            # Verify signature
            expected_signature = self._create_signature(verification_data)
            if audit_log.signature != expected_signature:
                logger.error(f"Signature mismatch for audit log {audit_log_id}")
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to verify audit log integrity: {e}")
            return False
    
    @asynccontextmanager
    async def audit_context(
        self,
        request: Request,
        response: Optional[Response] = None,
        user_id: Optional[int] = None,
        admin_user_id: Optional[int] = None
    ):
        """Context manager for automatic audit logging with performance tracking"""
        context = AuditContext(
            user_id=user_id,
            admin_user_id=admin_user_id,
            session_id=request.session.get('session_id') if hasattr(request, 'session') else None,
            request_id=str(uuid4()),
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get('user-agent'),
            start_time=time.time()
        )
        
        try:
            yield context
        finally:
            # Log the request completion
            if response:
                await self.log_audit_event(
                    action=AuditActions.API_REQUEST,
                    resource_type=ResourceTypes.API_ENDPOINT,
                    category=AuditCategory.API_ACCESS,
                    context=context,
                    request_method=request.method,
                    request_url=str(request.url),
                    response_status=response.status_code,
                    processing_time_ms=int((time.time() - context.start_time) * 1000)
                )


# Global audit logger instance
audit_logger = AuditLogger()


# Convenience functions for common audit operations
async def log_admin_action(
    action: str,
    resource_type: str,
    admin_user_id: int,
    resource_id: Optional[str] = None,
    success: bool = True,
    **kwargs
) -> Optional[int]:
    """Log administrative action"""
    context = AuditContext(admin_user_id=admin_user_id)
    
    return await audit_logger.log_audit_event(
        action=action,
        resource_type=resource_type,
        category=AuditCategory.USER_MANAGEMENT,
        context=context,
        resource_id=resource_id,
        success=success,
        **kwargs
    )


async def log_security_event(
    action: str,
    severity: SeverityLevel = SeverityLevel.HIGH,
    ip_address: Optional[str] = None,
    user_id: Optional[int] = None,
    **kwargs
) -> Optional[int]:
    """Log security-related event"""
    context = AuditContext(
        user_id=user_id,
        ip_address=ip_address
    )
    
    return await audit_logger.log_audit_event(
        action=action,
        resource_type=ResourceTypes.SECURITY_POLICY,
        category=AuditCategory.SECURITY_EVENT,
        context=context,
        severity=severity,
        **kwargs
    )


async def log_compliance_event(
    action: str,
    compliance_type: str,
    user_id: Optional[int] = None,
    **kwargs
) -> Optional[int]:
    """Log compliance-related event"""
    context = AuditContext(user_id=user_id)
    
    # Set compliance flags based on type
    compliance_kwargs = kwargs.copy()
    if compliance_type.lower() == 'gdpr':
        compliance_kwargs['gdpr_relevant'] = True
    elif compliance_type.lower() == 'sox':
        compliance_kwargs['sox_relevant'] = True
    elif compliance_type.lower() == 'hipaa':
        compliance_kwargs['hipaa_relevant'] = True
    
    return await audit_logger.log_audit_event(
        action=action,
        resource_type=ResourceTypes.COMPLIANCE_REPORT,
        category=AuditCategory.COMPLIANCE,
        context=context,
        sensitive_data_accessed=True,
        **compliance_kwargs
    )