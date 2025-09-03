"""
Admin user management endpoints for the admin dashboard with comprehensive bulk operations
"""
from typing import Any, List, Optional, Dict
from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select
import io
from datetime import datetime, timedelta

from app.api.deps import get_db, get_current_superuser
from app.models.user import User
from app.models.bulk_operations import (
    UserBulkOperationRequest, BulkOperationResult, UserExportRequest,
    UserImportRequest, BulkEmailRequest, InvitationBulkRequest,
    UserAnalyticsRequest, BulkOperationProgress
)
from app.models.audit_log import AuditLog
from app.services.bulk_operations import BulkOperationsService
from app.services.user_analytics import UserAnalyticsService
from app.services.rate_limiter import RateLimiter, RateLimitConfig
from app.core.security import get_password_hash

router = APIRouter()


@router.get("/users", response_model=List[dict])
async def get_all_users(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_superuser)
) -> Any:
    """
    Get all users for admin management.
    
    Requires superuser permissions.
    """
    stmt = select(User).order_by(User.created_at.desc())
    result = await db.execute(stmt)
    users = result.scalars().all()
    
    # Convert to dict format expected by frontend
    user_list = []
    for user in users:
        user_dict = {
            "id": user.id,
            "email": user.email,
            "username": user.email,  # Use email as username for compatibility
            "full_name": user.full_name,
            "is_active": user.is_active,
            "is_admin": user.is_superuser,
            "created_at": user.created_at.isoformat() if user.created_at else None,
            "last_login": user.last_login.isoformat() if user.last_login else None,
            "approval_status": user.approval_status,
            "is_verified": user.is_verified
        }
        user_list.append(user_dict)
    
    return user_list


@router.post("/users", response_model=dict)
async def create_user(
    *,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_superuser),
    user_data: dict
) -> Any:
    """
    Create a new user (admin only).
    
    Requires superuser permissions.
    """
    # Check if user already exists
    stmt = select(User).where(User.email == user_data["email"])
    result = await db.execute(stmt)
    existing_user = result.scalar_one_or_none()
    
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User with this email already exists"
        )
    
    # Create new user
    new_user = User(
        email=user_data["email"],
        full_name=user_data.get("full_name", ""),
        hashed_password=get_password_hash(user_data["password"]),
        is_active=user_data.get("is_active", True),
        is_superuser=user_data.get("is_admin", False),
        is_verified=user_data.get("is_verified", True),
        approval_status=user_data.get("approval_status", "approved"),
        data_handling_agreement=True,
        ethics_agreement=True,
        research_interests=user_data.get("research_interests", "Admin created user"),
        research_purpose=user_data.get("research_purpose", "Administrative"),
        expected_usage=user_data.get("expected_usage", "Standard usage")
    )
    
    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)
    
    return {
        "id": new_user.id,
        "email": new_user.email,
        "username": new_user.email,  # Use email as username for compatibility
        "full_name": new_user.full_name,
        "is_active": new_user.is_active,
        "is_admin": new_user.is_superuser,
        "created_at": new_user.created_at.isoformat() if new_user.created_at else None,
        "last_login": new_user.last_login.isoformat() if new_user.last_login else None,
        "approval_status": new_user.approval_status,
        "is_verified": new_user.is_verified
    }


@router.patch("/users/{user_id}", response_model=dict)
async def update_user(
    user_id: int,
    *,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_superuser),
    user_data: dict
) -> Any:
    """
    Update a user (admin only).
    
    Requires superuser permissions.
    """
    stmt = select(User).where(User.id == user_id)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    # Update user fields
    if "full_name" in user_data:
        user.full_name = user_data["full_name"]
    if "is_active" in user_data:
        user.is_active = user_data["is_active"]
    if "is_admin" in user_data:
        user.is_superuser = user_data["is_admin"]
    if "approval_status" in user_data:
        user.approval_status = user_data["approval_status"]
    
    await db.commit()
    await db.refresh(user)
    
    return {
        "id": user.id,
        "email": user.email,
        "username": user.email,  # Use email as username for compatibility
        "full_name": user.full_name,
        "is_active": user.is_active,
        "is_admin": user.is_superuser,
        "created_at": user.created_at.isoformat() if user.created_at else None,
        "last_login": user.last_login.isoformat() if user.last_login else None,
        "approval_status": user.approval_status,
        "is_verified": user.is_verified
    }


@router.delete("/users/{user_id}", response_model=dict)
async def delete_user(
    user_id: int,
    *,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_superuser)
) -> Any:
    """
    Delete a user (admin only).
    
    Requires superuser permissions.
    """
    if user_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete your own account"
        )
    
    stmt = select(User).where(User.id == user_id)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    await db.delete(user)
    await db.commit()
    
    return {
        "message": "User deleted successfully",
        "user_id": user_id
    }


@router.post("/users/{user_id}/toggle-status", response_model=dict)
async def toggle_user_status(
    user_id: int,
    *,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_superuser)
) -> Any:
    """
    Toggle user active status (admin only).
    
    Requires superuser permissions.
    """
    if user_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot modify your own status"
        )
    
    stmt = select(User).where(User.id == user_id)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    user.is_active = not user.is_active
    await db.commit()
    await db.refresh(user)
    
    return {
        "id": user.id,
        "email": user.email,
        "is_active": user.is_active,
        "message": f"User {'activated' if user.is_active else 'deactivated'} successfully"
    }


# Bulk Operations Endpoints

@router.post("/bulk-operation", response_model=BulkOperationResult)
async def perform_bulk_user_operation(
    *,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_superuser),
    request: Request,
    operation_request: UserBulkOperationRequest
) -> Any:
    """
    Perform bulk operations on users (approve, deny, activate, deactivate, delete, assign roles).
    
    Requires superuser permissions and implements rate limiting.
    """
    # Initialize services
    bulk_service = BulkOperationsService(db, current_user)
    rate_limiter = RateLimiter()
    
    # Rate limiting for bulk operations
    client_ip = getattr(request.client, 'host', '127.0.0.1')
    rate_limit_key = f"bulk_operation:{current_user.id}:{client_ip}"
    
    if operation_request.operation.value == "delete":
        await rate_limiter.check_rate_limit(rate_limit_key, **RateLimitConfig.BULK_DELETE)
    else:
        await rate_limiter.check_rate_limit(rate_limit_key, **RateLimitConfig.BULK_OPERATIONS)
    
    try:
        result = await bulk_service.perform_bulk_user_operation(
            user_ids=operation_request.user_ids,
            operation=operation_request.operation,
            reason=operation_request.reason,
            role=operation_request.role,
            custom_message=operation_request.custom_message
        )
        return result
    except PermissionError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e)
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Bulk operation failed: {str(e)}"
        )


@router.get("/bulk-operation/{operation_id}/progress", response_model=BulkOperationProgress)
async def get_bulk_operation_progress(
    operation_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_superuser)
) -> Any:
    """
    Get the progress status of a bulk operation.
    
    Requires superuser permissions.
    """
    bulk_service = BulkOperationsService(db, current_user)
    
    progress = await bulk_service.get_operation_progress(operation_id)
    if not progress:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Operation not found or already completed"
        )
    
    return progress


@router.post("/export")
async def export_users(
    *,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_superuser),
    request: Request,
    export_request: UserExportRequest
) -> Any:
    """
    Export user data in various formats (CSV, JSON, XLSX).
    
    Requires superuser permissions and implements rate limiting.
    """
    # Rate limiting for exports
    rate_limiter = RateLimiter()
    client_ip = getattr(request.client, 'host', '127.0.0.1')
    await rate_limiter.check_rate_limit(
        f"export:{current_user.id}:{client_ip}",
        **RateLimitConfig.EXPORT_OPERATIONS
    )
    
    try:
        bulk_service = BulkOperationsService(db, current_user)
        export_result = await bulk_service.export_users(export_request)
        
        # Return appropriate response based on format
        if export_request.format.value == "csv":
            return StreamingResponse(
                io.StringIO(export_result["content"]),
                media_type="text/csv",
                headers={
                    "Content-Disposition": f"attachment; filename={export_result['filename']}"
                }
            )
        else:  # JSON
            return StreamingResponse(
                io.StringIO(export_result["content"]),
                media_type="application/json",
                headers={
                    "Content-Disposition": f"attachment; filename={export_result['filename']}"
                }
            )
            
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Export failed: {str(e)}"
        )


@router.post("/import", response_model=Dict[str, Any])
async def import_users(
    *,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_superuser),
    import_request: UserImportRequest
) -> Any:
    """
    Import user data from structured data.
    
    Supports validation-only mode and updating existing users.
    Requires superuser permissions.
    """
    # For now, return a placeholder response
    # Full implementation would validate and import the user data
    return {
        "message": "User import feature is under development",
        "requested_count": len(import_request.data),
        "validate_only": import_request.validate_only,
        "update_existing": import_request.update_existing
    }


@router.post("/bulk-email", response_model=Dict[str, Any])
async def send_bulk_emails(
    *,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_superuser),
    request: Request,
    email_request: BulkEmailRequest
) -> Any:
    """
    Send bulk emails to users.
    
    Supports various email types and templates.
    Requires superuser permissions and implements rate limiting.
    """
    # Rate limiting for bulk emails
    rate_limiter = RateLimiter()
    client_ip = getattr(request.client, 'host', '127.0.0.1')
    await rate_limiter.check_rate_limit(
        f"bulk_email:{current_user.id}:{client_ip}",
        **RateLimitConfig.BULK_EMAIL
    )
    
    # For now, return a placeholder response
    # Full implementation would integrate with email service
    return {
        "message": "Bulk email feature is under development",
        "recipient_count": len(email_request.user_ids),
        "email_type": email_request.email_type,
        "send_immediately": email_request.send_immediately
    }


@router.post("/bulk-invitations", response_model=Dict[str, Any])
async def generate_bulk_invitations(
    *,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_superuser),
    invitation_request: InvitationBulkRequest
) -> Any:
    """
    Generate bulk invitation tokens.
    
    Creates multiple invitation tokens with specified settings.
    Requires superuser permissions.
    """
    try:
        bulk_service = BulkOperationsService(db, current_user)
        result = await bulk_service.generate_bulk_invitations(invitation_request)
        return result
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate invitations: {str(e)}"
        )


# User Analytics Endpoints

@router.post("/analytics", response_model=Dict[str, Any])
async def get_user_analytics(
    *,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_superuser),
    analytics_request: UserAnalyticsRequest
) -> Any:
    """
    Get comprehensive user analytics and reports.
    
    Includes registration trends, approval statistics, and activity metrics.
    Requires superuser permissions.
    """
    try:
        analytics_service = UserAnalyticsService(db)
        analytics = await analytics_service.generate_user_analytics(analytics_request)
        return analytics.dict()
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Analytics generation failed: {str(e)}"
        )


@router.get("/activity-summary", response_model=List[Dict[str, Any]])
async def get_user_activity_summary(
    *,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_superuser),
    user_ids: Optional[str] = None,  # Comma-separated user IDs
    limit: int = 100
) -> Any:
    """
    Get detailed activity summary for users.
    
    Includes engagement scores and activity metrics.
    Requires superuser permissions.
    """
    try:
        # Parse user IDs if provided
        parsed_user_ids = None
        if user_ids:
            try:
                parsed_user_ids = [int(uid.strip()) for uid in user_ids.split(',')]
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid user_ids format. Use comma-separated integers."
                )
        
        analytics_service = UserAnalyticsService(db)
        summaries = await analytics_service.get_user_activity_summary(
            user_ids=parsed_user_ids,
            limit=limit
        )
        
        return [summary.dict() for summary in summaries]
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get activity summary: {str(e)}"
        )


@router.get("/audit-logs", response_model=List[Dict[str, Any]])
async def get_audit_logs(
    *,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_superuser),
    limit: int = 50,
    offset: int = 0,
    action: Optional[str] = None,
    resource_type: Optional[str] = None,
    admin_user_id: Optional[int] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None
) -> Any:
    """
    Get audit logs with filtering options.
    
    Provides detailed audit trail of admin operations.
    Requires superuser permissions.
    """
    try:
        # Build query
        stmt = select(AuditLog).order_by(AuditLog.created_at.desc()).offset(offset).limit(limit)
        
        # Apply filters
        if action:
            stmt = stmt.where(AuditLog.action == action)
        if resource_type:
            stmt = stmt.where(AuditLog.resource_type == resource_type)
        if admin_user_id:
            stmt = stmt.where(AuditLog.admin_user_id == admin_user_id)
        if start_date:
            stmt = stmt.where(AuditLog.created_at >= start_date)
        if end_date:
            stmt = stmt.where(AuditLog.created_at <= end_date)
        
        result = await db.execute(stmt)
        audit_logs = list(result.scalars().all())
        
        # Convert to dict format
        logs_data = []
        for log in audit_logs:
            log_dict = {
                "id": log.id,
                "user_id": log.user_id,
                "admin_user_id": log.admin_user_id,
                "action": log.action,
                "resource_type": log.resource_type,
                "resource_id": log.resource_id,
                "details": log.details,
                "ip_address": log.ip_address,
                "user_agent": log.user_agent,
                "success": log.success,
                "error_message": log.error_message,
                "affected_count": log.affected_count,
                "created_at": log.created_at.isoformat() if log.created_at else None
            }
            logs_data.append(log_dict)
        
        return logs_data
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch audit logs: {str(e)}"
        )


@router.get("/audit-summary", response_model=Dict[str, Any])
async def get_audit_summary(
    *,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_superuser),
    days: int = 30
) -> Any:
    """
    Get audit summary for admin activities.
    
    Provides overview of admin operations and activity.
    Requires superuser permissions.
    """
    try:
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=days)
        
        analytics_service = UserAnalyticsService(db)
        summary = await analytics_service.get_admin_audit_summary(start_date, end_date)
        
        return summary
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get audit summary: {str(e)}"
        )


# Rate Limiting Management Endpoints

@router.get("/rate-limits/{user_id}", response_model=Dict[str, Any])
async def get_user_rate_limits(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_superuser)
) -> Any:
    """
    Get current rate limit status for a user.
    
    Shows current usage and limits across different operations.
    Requires superuser permissions.
    """
    try:
        rate_limiter = RateLimiter()
        
        # Check various rate limits for the user
        rate_limits = {}
        
        # Bulk operations
        bulk_key = f"bulk_operation:{user_id}"
        rate_limits["bulk_operations"] = await rate_limiter.get_rate_limit_info(
            bulk_key, **RateLimitConfig.BULK_OPERATIONS
        )
        
        # Export operations
        export_key = f"export:{user_id}"
        rate_limits["export_operations"] = await rate_limiter.get_rate_limit_info(
            export_key, **RateLimitConfig.EXPORT_OPERATIONS
        )
        
        # Email operations
        email_key = f"bulk_email:{user_id}"
        rate_limits["bulk_email"] = await rate_limiter.get_rate_limit_info(
            email_key, **RateLimitConfig.BULK_EMAIL
        )
        
        return {
            "user_id": user_id,
            "rate_limits": rate_limits,
            "checked_at": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get rate limits: {str(e)}"
        )


@router.post("/rate-limits/{user_id}/reset", response_model=Dict[str, Any])
async def reset_user_rate_limits(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_superuser)
) -> Any:
    """
    Reset rate limits for a user (emergency function).
    
    Clears all rate limiting counters for the specified user.
    Requires superuser permissions.
    """
    try:
        rate_limiter = RateLimiter()
        
        # Reset various rate limits
        patterns = [
            f"bulk_operation:{user_id}*",
            f"export:{user_id}*",
            f"bulk_email:{user_id}*"
        ]
        
        total_reset = 0
        for pattern in patterns:
            count = await rate_limiter.bulk_reset_rate_limits(pattern)
            total_reset += count
        
        return {
            "user_id": user_id,
            "rate_limits_reset": total_reset,
            "reset_at": datetime.utcnow().isoformat(),
            "message": f"Reset {total_reset} rate limit entries for user {user_id}"
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to reset rate limits: {str(e)}"
        )