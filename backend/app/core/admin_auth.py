"""
Admin API authentication middleware and security utilities
"""
import time
from typing import Optional, Dict, Any, List
from datetime import datetime
from fastapi import Request, HTTPException, status, Depends
from sqlalchemy.ext.asyncio import AsyncSession
import logging
import hashlib
import ipaddress
from contextlib import asynccontextmanager

from app.core.config import settings
from app.core.database import get_db
from app.models.user import User
from app.models.audit_log import AuditLog
from app.services.rate_limiter import RateLimiter
from app.services.session_store import get_session_store, SessionStore

logger = logging.getLogger(__name__)


class AdminRateLimitConfig:
    """Rate limiting configurations for admin APIs"""
    
    # Standard admin operations
    ADMIN_READ = {"requests": 100, "window": 60}  # 100 req/min
    ADMIN_WRITE = {"requests": 50, "window": 60}  # 50 req/min
    ADMIN_BULK = {"requests": 10, "window": 60}   # 10 req/min
    
    # Sensitive operations
    USER_DELETE = {"requests": 5, "window": 300}  # 5 req/5min
    BULK_DELETE = {"requests": 2, "window": 300}  # 2 req/5min
    CONFIG_CHANGE = {"requests": 10, "window": 300}  # 10 req/5min
    
    # Export/backup operations
    EXPORT_DATA = {"requests": 5, "window": 300}  # 5 req/5min
    BACKUP_CREATE = {"requests": 2, "window": 900}  # 2 req/15min
    
    # Security operations
    SECURITY_AUDIT = {"requests": 20, "window": 300}  # 20 req/5min


class AdminSecurityHeaders:
    """Security headers for admin API responses"""
    
    @staticmethod
    def get_headers() -> Dict[str, str]:
        return {
            "X-Admin-API": "true",
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY",
            "X-XSS-Protection": "1; mode=block",
            "Referrer-Policy": "strict-origin-when-cross-origin",
            "Content-Security-Policy": "default-src 'self'",
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0"
        }


class AdminAuthenticationError(HTTPException):
    """Custom exception for admin authentication failures"""
    
    def __init__(self, detail: str = "Insufficient admin privileges"):
        super().__init__(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=detail,
            headers=AdminSecurityHeaders.get_headers()
        )


class AdminRateLimitExceeded(HTTPException):
    """Custom exception for admin rate limit exceeded"""
    
    def __init__(self, detail: str = "Admin API rate limit exceeded"):
        super().__init__(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=detail,
            headers={
                **AdminSecurityHeaders.get_headers(),
                "Retry-After": "60"
            }
        )


class AdminIPValidator:
    """IP address validation for admin access"""
    
    def __init__(self):
        self.allowed_networks = self._parse_allowed_networks()
    
    def _parse_allowed_networks(self) -> List[ipaddress.IPv4Network]:
        """Parse allowed IP networks from settings"""
        networks = []
        
        # Add default allowed networks (can be configured via environment)
        default_networks = [
            "127.0.0.0/8",    # localhost
            "10.0.0.0/8",     # private class A
            "172.16.0.0/12",  # private class B
            "192.168.0.0/16"  # private class C
        ]
        
        # Get from settings if available
        admin_allowed_ips = getattr(settings, 'ADMIN_ALLOWED_IPS', None)
        if admin_allowed_ips:
            if isinstance(admin_allowed_ips, str):
                admin_allowed_ips = admin_allowed_ips.split(',')
            default_networks.extend([ip.strip() for ip in admin_allowed_ips])
        
        for network_str in default_networks:
            try:
                networks.append(ipaddress.IPv4Network(network_str.strip(), strict=False))
            except ValueError as e:
                logger.warning(f"Invalid IP network format: {network_str} - {e}")
        
        return networks
    
    def is_allowed(self, ip_address: str) -> bool:
        """Check if IP address is allowed for admin access"""
        # Skip IP validation in development
        if settings.ENVIRONMENT == "development":
            return True
        
        try:
            ip = ipaddress.IPv4Address(ip_address)
            return any(ip in network for network in self.allowed_networks)
        except ValueError:
            logger.warning(f"Invalid IP address format: {ip_address}")
            return False


class AdminAuditLogger:
    """Audit logging for admin operations"""
    
    @staticmethod
    async def log_admin_action(
        db: AsyncSession,
        admin_user: User,
        action: str,
        resource_type: str,
        resource_id: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        success: bool = True,
        error_message: Optional[str] = None,
        affected_count: Optional[int] = None,
        request: Optional[Request] = None
    ):
        """Log admin action to audit log"""
        try:
            # Extract request metadata
            ip_address = None
            user_agent = None
            
            if request:
                ip_address = getattr(request.client, 'host', None)
                user_agent = request.headers.get('user-agent')
            
            # Create audit log entry
            audit_log = AuditLog(
                admin_user_id=admin_user.id,
                action=action,
                resource_type=resource_type,
                resource_id=resource_id,
                details=details or {},
                ip_address=ip_address,
                user_agent=user_agent,
                success=success,
                error_message=error_message,
                affected_count=affected_count
            )
            
            db.add(audit_log)
            await db.commit()
            
            # Log to application logger as well
            logger.info(
                f"Admin action: {admin_user.email} performed {action} on {resource_type}"
                f"{f' (ID: {resource_id})' if resource_id else ''} "
                f"- {'SUCCESS' if success else 'FAILED'}"
            )
            
        except Exception as e:
            logger.error(f"Failed to log admin action: {e}")
            # Don't raise exception to avoid breaking the original operation


class AdminAuthMiddleware:
    """Authentication and security middleware for admin APIs"""
    
    def __init__(self):
        self.rate_limiter = RateLimiter()
        self.ip_validator = AdminIPValidator()
        self.audit_logger = AdminAuditLogger()
    
    async def verify_admin_access(
        self,
        request: Request,
        db: AsyncSession,
        operation_type: str = "read",
        session_store: Optional[SessionStore] = None
    ) -> User:
        """
        Comprehensive admin access verification
        
        Args:
            request: FastAPI request object
            db: Database session
            operation_type: Type of operation (read, write, bulk, delete, etc.)
        
        Returns:
            User: Authenticated admin user
            
        Raises:
            AdminAuthenticationError: If authentication fails
            AdminRateLimitExceeded: If rate limits are exceeded
        """
        # 1. IP Address validation
        client_ip = getattr(request.client, 'host', '127.0.0.1')
        if not self.ip_validator.is_allowed(client_ip):
            logger.warning(f"Admin API access denied from IP: {client_ip}")
            await self.audit_logger.log_admin_action(
                db=db,
                admin_user=None,
                action="admin_access_denied",
                resource_type="admin_api",
                details={"reason": "IP not allowed", "ip": client_ip},
                success=False,
                error_message="IP address not in allowed list",
                request=request
            )
            raise AdminAuthenticationError("Access denied: IP address not allowed")
        
        # 2. Get current user (this handles JWT/session authentication)
        try:
            from app.api.deps import get_current_user_from_session
            if not session_store:
                session_store = await get_session_store()
            current_user = await get_current_user_from_session(request, db, session_store)
            if not current_user:
                raise AdminAuthenticationError("Authentication required")
        except Exception:
            logger.warning(f"Admin authentication failed from IP: {client_ip}")
            raise AdminAuthenticationError("Invalid or missing admin credentials")
        
        # 3. Additional admin privilege verification
        if not current_user.is_superuser:
            logger.warning(f"Non-admin user attempted admin access: {current_user.email}")
            await self.audit_logger.log_admin_action(
                db=db,
                admin_user=current_user,
                action="admin_access_denied",
                resource_type="admin_api",
                details={"reason": "Insufficient privileges"},
                success=False,
                error_message="User is not a superuser",
                request=request
            )
            raise AdminAuthenticationError("Insufficient admin privileges")
        
        # 4. Rate limiting based on operation type
        await self._check_rate_limits(current_user, operation_type, client_ip)
        
        # 5. Log successful authentication
        logger.info(f"Admin API access granted to {current_user.email} from {client_ip}")
        
        return current_user
    
    async def _check_rate_limits(self, user: User, operation_type: str, ip_address: str):
        """Check rate limits for admin operations"""
        rate_limit_key = f"admin_{operation_type}:{user.id}:{ip_address}"
        
        # Get rate limit config based on operation type
        config_map = {
            "read": AdminRateLimitConfig.ADMIN_READ,
            "write": AdminRateLimitConfig.ADMIN_WRITE,
            "bulk": AdminRateLimitConfig.ADMIN_BULK,
            "delete": AdminRateLimitConfig.USER_DELETE,
            "bulk_delete": AdminRateLimitConfig.BULK_DELETE,
            "config": AdminRateLimitConfig.CONFIG_CHANGE,
            "export": AdminRateLimitConfig.EXPORT_DATA,
            "backup": AdminRateLimitConfig.BACKUP_CREATE,
            "audit": AdminRateLimitConfig.SECURITY_AUDIT
        }
        
        rate_config = config_map.get(operation_type, AdminRateLimitConfig.ADMIN_READ)
        
        try:
            await self.rate_limiter.check_rate_limit(rate_limit_key, **rate_config)
        except HTTPException:
            logger.warning(
                f"Rate limit exceeded for admin user {user.email} "
                f"on operation {operation_type} from {ip_address}"
            )
            raise AdminRateLimitExceeded(
                f"Rate limit exceeded for {operation_type} operations"
            )
    
    @asynccontextmanager
    async def audit_context(
        self,
        db: AsyncSession,
        admin_user: User,
        action: str,
        resource_type: str,
        resource_id: Optional[str] = None,
        request: Optional[Request] = None
    ):
        """Context manager for automatic audit logging"""
        start_time = time.time()
        details = {"start_time": datetime.utcnow().isoformat()}
        success = False
        error_message = None
        affected_count = None
        
        try:
            yield
            success = True
            details["duration_ms"] = round((time.time() - start_time) * 1000, 2)
        except Exception as e:
            error_message = str(e)
            details["duration_ms"] = round((time.time() - start_time) * 1000, 2)
            details["error_type"] = type(e).__name__
            raise
        finally:
            await self.audit_logger.log_admin_action(
                db=db,
                admin_user=admin_user,
                action=action,
                resource_type=resource_type,
                resource_id=resource_id,
                details=details,
                success=success,
                error_message=error_message,
                affected_count=affected_count,
                request=request
            )


# Global admin middleware instance
admin_middleware = AdminAuthMiddleware()


# ===== DEPENDENCY FUNCTIONS =====

async def get_admin_user_read(
    request: Request,
    db: AsyncSession = Depends(get_db),
    session_store: SessionStore = Depends(get_session_store)
) -> User:
    """Get authenticated admin user for read operations"""
    return await admin_middleware.verify_admin_access(request, db, "read", session_store)


async def get_admin_user_write(
    request: Request,
    db: AsyncSession = Depends(get_db),
    session_store: SessionStore = Depends(get_session_store)
) -> User:
    """Get authenticated admin user for write operations"""
    return await admin_middleware.verify_admin_access(request, db, "write", session_store)


async def get_admin_user_bulk(
    request: Request,
    db: AsyncSession = Depends(get_db),
    session_store: SessionStore = Depends(get_session_store)
) -> User:
    """Get authenticated admin user for bulk operations"""
    return await admin_middleware.verify_admin_access(request, db, "bulk", session_store)


async def get_admin_user_delete(
    request: Request,
    db: AsyncSession = Depends(get_db),
    session_store: SessionStore = Depends(get_session_store)
) -> User:
    """Get authenticated admin user for delete operations"""
    return await admin_middleware.verify_admin_access(request, db, "delete", session_store)


async def get_admin_user_config(
    request: Request,
    db: AsyncSession = Depends(get_db),
    session_store: SessionStore = Depends(get_session_store)
) -> User:
    """Get authenticated admin user for configuration changes"""
    return await admin_middleware.verify_admin_access(request, db, "config", session_store)


async def get_admin_user_export(
    request: Request,
    db: AsyncSession = Depends(get_db),
    session_store: SessionStore = Depends(get_session_store)
) -> User:
    """Get authenticated admin user for export operations"""
    return await admin_middleware.verify_admin_access(request, db, "export", session_store)


async def get_admin_user_backup(
    request: Request,
    db: AsyncSession = Depends(get_db),
    session_store: SessionStore = Depends(get_session_store)
) -> User:
    """Get authenticated admin user for backup operations"""
    return await admin_middleware.verify_admin_access(request, db, "backup", session_store)


# ===== UTILITY FUNCTIONS =====

def get_operation_signature(request: Request, user: User) -> str:
    """Generate a unique signature for the current operation"""
    content = f"{request.method}:{request.url.path}:{user.id}:{time.time()}"
    return hashlib.sha256(content.encode()).hexdigest()[:16]


def require_confirmation(
    confirmation_token: Optional[str],
    expected_token: str,
    operation_name: str
) -> None:
    """Require confirmation token for destructive operations"""
    if not confirmation_token or confirmation_token != expected_token:
        raise AdminAuthenticationError(
            f"Confirmation required for {operation_name}. "
            f"Include confirmation_token parameter."
        )


def mask_sensitive_data(data: Dict[str, Any]) -> Dict[str, Any]:
    """Mask sensitive data in audit logs"""
    masked_data = data.copy()
    sensitive_fields = ['password', 'token', 'secret', 'key', 'credentials']
    
    def mask_recursive(obj):
        if isinstance(obj, dict):
            for key, value in obj.items():
                if any(sensitive in key.lower() for sensitive in sensitive_fields):
                    obj[key] = "***MASKED***"
                elif isinstance(value, (dict, list)):
                    mask_recursive(value)
        elif isinstance(obj, list):
            for item in obj:
                if isinstance(item, (dict, list)):
                    mask_recursive(item)
    
    mask_recursive(masked_data)
    return masked_data