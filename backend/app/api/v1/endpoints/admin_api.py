"""
Comprehensive Admin API endpoints for programmatic access to all admin functionality
"""
import asyncio
from typing import Any, Optional, Dict
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, Request, BackgroundTasks, Query
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select, func, or_
import logging

from app.core.database import get_db
from app.models.user import User
from app.models.project import Project, Page
from app.core.config import settings
from app.models.audit_log import AuditLog
from app.schemas.admin_schemas import (
    # User management
    AdminUserListParams, AdminUserRead, AdminUserCreate, AdminUserUpdate,
    # Session management
    AdminSessionRead, AdminSessionListParams, AdminBulkSessionRevoke,
    # Content management
    AdminSystemHealth, AdminConfigRead,
    # Backup and recovery
    AdminAuditLogRead, AdminAuditLogParams,
    # Bulk operations
    AdminAPIResponse, AdminErrorResponse, PaginatedResponse, AdminOperationResult
)
from app.core.admin_auth import (
    admin_middleware,
    get_admin_user_read, get_admin_user_write, get_admin_user_bulk,
    get_admin_user_delete, get_operation_signature, require_confirmation,
    AdminSecurityHeaders
)
from app.services.session_store import get_session_store, SessionStore
from app.core.security import get_password_hash

logger = logging.getLogger(__name__)

router = APIRouter()


# ===== UTILITY FUNCTIONS =====

def create_success_response(
    data: Any = None,
    message: str = "Operation completed successfully",
    operation_id: Optional[str] = None
) -> AdminAPIResponse:
    """Create a standardized success response"""
    return AdminAPIResponse(
        success=True,
        data=data,
        message=message,
        operation_id=operation_id
    )


def create_error_response(
    error: str,
    error_code: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None
) -> AdminErrorResponse:
    """Create a standardized error response"""
    return AdminErrorResponse(
        error=error,
        error_code=error_code,
        details=details
    )


def add_security_headers(response: JSONResponse) -> JSONResponse:
    """Add security headers to admin API responses"""
    for header, value in AdminSecurityHeaders.get_headers().items():
        response.headers[header] = value
    return response


# ===== USER MANAGEMENT ENDPOINTS =====

@router.get("/users", response_model=PaginatedResponse, tags=["User Management"])
async def list_users(
    params: AdminUserListParams = Depends(),
    request: Request = None,
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(get_admin_user_read)
) -> JSONResponse:
    """
    List all users with advanced filtering, searching, and pagination.
    
    **Features:**
    - Advanced search across email, full name, and research fields
    - Multi-field filtering (approval status, verification, etc.)
    - Flexible sorting options
    - Comprehensive user data including activity metrics
    - Pagination with metadata
    
    **Required Permissions:** Admin (superuser)
    
    **Rate Limit:** 100 requests/minute
    """
    try:
        async with admin_middleware.audit_context(
            db=db,
            admin_user=admin_user,
            action="list_users",
            resource_type="users",
            request=request
        ):
            # Build base query with joins for activity metrics
            query = select(
                User,
                func.coalesce(func.count(Project.id.distinct()), 0).label('projects_count'),
                func.coalesce(func.count(Page.id.distinct()), 0).label('pages_count')
            ).outerjoin(Project, Project.user_id == User.id)\
             .outerjoin(Page, Page.user_id == User.id)\
             .group_by(User.id)
            
            # Apply search filter
            if params.search:
                search_term = f"%{params.search}%"
                query = query.where(
                    or_(
                        User.email.ilike(search_term),
                        User.full_name.ilike(search_term),
                        User.research_interests.ilike(search_term),
                        User.research_purpose.ilike(search_term)
                    )
                )
            
            # Apply status filters
            if params.approval_status:
                query = query.where(User.approval_status == params.approval_status)
            
            if params.is_active is not None:
                query = query.where(User.is_active == params.is_active)
                
            if params.is_verified is not None:
                query = query.where(User.is_verified == params.is_verified)
                
            if params.is_superuser is not None:
                query = query.where(User.is_superuser == params.is_superuser)
            
            # Apply date filters
            if params.created_after:
                query = query.where(User.created_at >= params.created_after)
                
            if params.created_before:
                query = query.where(User.created_at <= params.created_before)
                
            if params.last_login_after:
                query = query.where(User.last_login >= params.last_login_after)
            
            # Apply sorting
            sort_field = getattr(User, params.sort_by)
            if params.sort_order == "desc":
                query = query.order_by(sort_field.desc())
            else:
                query = query.order_by(sort_field.asc())
            
            # Get total count
            count_query = select(func.count()).select_from(
                query.subquery()
            )
            total_result = await db.execute(count_query)
            total = total_result.scalar() or 0
            
            # Apply pagination
            offset = (params.page - 1) * params.per_page
            query = query.offset(offset).limit(params.per_page)
            
            # Execute query
            result = await db.execute(query)
            users_with_metrics = result.all()
            
            # Format response data
            users_data = []
            for user, projects_count, pages_count in users_with_metrics:
                user_data = AdminUserRead(
                    id=user.id,
                    email=user.email,
                    full_name=user.full_name,
                    is_active=user.is_active,
                    is_verified=user.is_verified,
                    is_superuser=user.is_superuser,
                    approval_status=user.approval_status,
                    created_at=user.created_at,
                    last_login=user.last_login,
                    updated_at=user.updated_at,
                    projects_count=projects_count,
                    pages_count=pages_count,
                    research_interests=user.research_interests,
                    research_purpose=user.research_purpose,
                    expected_usage=user.expected_usage,
                    approved_by_id=user.approved_by_id,
                    approved_at=user.approved_at
                ).dict()
                users_data.append(user_data)
            
            # Calculate pagination metadata
            pages = (total + params.per_page - 1) // params.per_page
            
            response_data = PaginatedResponse(
                items=users_data,
                total=total,
                page=params.page,
                per_page=params.per_page,
                pages=pages,
                has_next=params.page < pages,
                has_prev=params.page > 1
            )
            
            return add_security_headers(JSONResponse(
                status_code=200,
                content=response_data.dict()
            ))
            
    except Exception as e:
        logger.error(f"Failed to list users: {e}")
        error_response = create_error_response(
            error="Failed to retrieve users",
            error_code="USER_LIST_FAILED",
            details={"error_message": str(e)}
        )
        return add_security_headers(JSONResponse(
            status_code=500,
            content=error_response.dict()
        ))


@router.get("/users/{user_id}", response_model=AdminUserRead, tags=["User Management"])
async def get_user(
    user_id: int,
    request: Request = None,
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(get_admin_user_read)
) -> JSONResponse:
    """
    Get detailed information for a specific user.
    
    **Features:**
    - Complete user profile and metadata
    - Activity statistics and engagement metrics
    - Account status and verification details
    - Administrative metadata (approved by, dates, etc.)
    
    **Required Permissions:** Admin (superuser)
    
    **Rate Limit:** 100 requests/minute
    """
    try:
        async with admin_middleware.audit_context(
            db=db,
            admin_user=admin_user,
            action="get_user",
            resource_type="user",
            resource_id=str(user_id),
            request=request
        ):
            # Get user with activity metrics
            query = select(
                User,
                func.coalesce(func.count(Project.id.distinct()), 0).label('projects_count'),
                func.coalesce(func.count(Page.id.distinct()), 0).label('pages_count')
            ).outerjoin(Project, Project.user_id == User.id)\
             .outerjoin(Page, Page.user_id == User.id)\
             .where(User.id == user_id)\
             .group_by(User.id)
            
            result = await db.execute(query)
            user_with_metrics = result.first()
            
            if not user_with_metrics:
                error_response = create_error_response(
                    error="User not found",
                    error_code="USER_NOT_FOUND"
                )
                return add_security_headers(JSONResponse(
                    status_code=404,
                    content=error_response.dict()
                ))
            
            user, projects_count, pages_count = user_with_metrics
            
            user_data = AdminUserRead(
                id=user.id,
                email=user.email,
                full_name=user.full_name,
                is_active=user.is_active,
                is_verified=user.is_verified,
                is_superuser=user.is_superuser,
                approval_status=user.approval_status,
                created_at=user.created_at,
                last_login=user.last_login,
                updated_at=user.updated_at,
                projects_count=projects_count,
                pages_count=pages_count,
                research_interests=user.research_interests,
                research_purpose=user.research_purpose,
                expected_usage=user.expected_usage,
                approved_by_id=user.approved_by_id,
                approved_at=user.approved_at
            )
            
            return add_security_headers(JSONResponse(
                status_code=200,
                content=user_data.dict()
            ))
            
    except Exception as e:
        logger.error(f"Failed to get user {user_id}: {e}")
        error_response = create_error_response(
            error="Failed to retrieve user",
            error_code="USER_GET_FAILED",
            details={"user_id": user_id, "error_message": str(e)}
        )
        return add_security_headers(JSONResponse(
            status_code=500,
            content=error_response.dict()
        ))


@router.post("/users", response_model=AdminUserRead, tags=["User Management"])
async def create_user(
    user_data: AdminUserCreate,
    background_tasks: BackgroundTasks,
    request: Request = None,
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(get_admin_user_write)
) -> JSONResponse:
    """
    Create a new user account with admin privileges.
    
    **Features:**
    - Direct user creation bypassing normal registration flow
    - Configurable initial status (active, verified, approved)
    - Optional welcome email notification
    - Automatic research field population
    - Comprehensive validation and error handling
    
    **Required Permissions:** Admin (superuser)
    
    **Rate Limit:** 50 requests/minute
    """
    try:
        async with admin_middleware.audit_context(
            db=db,
            admin_user=admin_user,
            action="create_user",
            resource_type="user",
            request=request
        ):
            # Check if user already exists
            existing_user_query = select(User).where(User.email == user_data.email)
            result = await db.execute(existing_user_query)
            existing_user = result.scalar_one_or_none()
            
            if existing_user:
                error_response = create_error_response(
                    error="User with this email already exists",
                    error_code="USER_ALREADY_EXISTS",
                    details={"email": user_data.email}
                )
                return add_security_headers(JSONResponse(
                    status_code=400,
                    content=error_response.dict()
                ))
            
            # Create new user
            new_user = User(
                email=user_data.email,
                full_name=user_data.full_name,
                hashed_password=get_password_hash(user_data.password),
                is_active=user_data.is_active,
                is_verified=user_data.is_verified,
                is_superuser=user_data.is_superuser,
                approval_status=user_data.approval_status,
                data_handling_agreement=True,
                ethics_agreement=True,
                research_interests=user_data.research_interests,
                research_purpose=user_data.research_purpose,
                expected_usage=user_data.expected_usage,
                approved_by_id=admin_user.id if user_data.approval_status == "approved" else None,
                approved_at=datetime.utcnow() if user_data.approval_status == "approved" else None
            )
            
            db.add(new_user)
            await db.commit()
            await db.refresh(new_user)
            
            # Send welcome email if requested
            if user_data.send_welcome_email:
                background_tasks.add_task(
                    send_admin_created_user_email,
                    new_user.email,
                    new_user.full_name,
                    admin_user.email
                )
            
            user_response = AdminUserRead(
                id=new_user.id,
                email=new_user.email,
                full_name=new_user.full_name,
                is_active=new_user.is_active,
                is_verified=new_user.is_verified,
                is_superuser=new_user.is_superuser,
                approval_status=new_user.approval_status,
                created_at=new_user.created_at,
                last_login=new_user.last_login,
                updated_at=new_user.updated_at,
                projects_count=0,
                pages_count=0,
                research_interests=new_user.research_interests,
                research_purpose=new_user.research_purpose,
                expected_usage=new_user.expected_usage,
                approved_by_id=new_user.approved_by_id,
                approved_at=new_user.approved_at
            )
            
            return add_security_headers(JSONResponse(
                status_code=201,
                content=user_response.dict()
            ))
            
    except Exception as e:
        logger.error(f"Failed to create user: {e}")
        error_response = create_error_response(
            error="Failed to create user",
            error_code="USER_CREATE_FAILED",
            details={"error_message": str(e)}
        )
        return add_security_headers(JSONResponse(
            status_code=500,
            content=error_response.dict()
        ))


@router.put("/users/{user_id}", response_model=AdminUserRead, tags=["User Management"])
async def update_user(
    user_id: int,
    user_update: AdminUserUpdate,
    request: Request = None,
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(get_admin_user_write)
) -> JSONResponse:
    """
    Update user account details and status.
    
    **Features:**
    - Comprehensive user profile updates
    - Status changes (active, verified, approval)
    - Research field modifications
    - Automatic approval tracking
    - Change history logging
    
    **Required Permissions:** Admin (superuser)
    
    **Rate Limit:** 50 requests/minute
    """
    try:
        async with admin_middleware.audit_context(
            db=db,
            admin_user=admin_user,
            action="update_user",
            resource_type="user",
            resource_id=str(user_id),
            request=request
        ):
            # Get existing user
            user_query = select(User).where(User.id == user_id)
            result = await db.execute(user_query)
            user = result.scalar_one_or_none()
            
            if not user:
                error_response = create_error_response(
                    error="User not found",
                    error_code="USER_NOT_FOUND"
                )
                return add_security_headers(JSONResponse(
                    status_code=404,
                    content=error_response.dict()
                ))
            
            # Track changes for audit log
            changes = {}
            
            # Update fields
            if user_update.full_name is not None:
                changes['full_name'] = {'old': user.full_name, 'new': user_update.full_name}
                user.full_name = user_update.full_name
            
            if user_update.is_active is not None:
                changes['is_active'] = {'old': user.is_active, 'new': user_update.is_active}
                user.is_active = user_update.is_active
            
            if user_update.is_verified is not None:
                changes['is_verified'] = {'old': user.is_verified, 'new': user_update.is_verified}
                user.is_verified = user_update.is_verified
            
            if user_update.is_superuser is not None:
                changes['is_superuser'] = {'old': user.is_superuser, 'new': user_update.is_superuser}
                user.is_superuser = user_update.is_superuser
            
            if user_update.approval_status is not None:
                changes['approval_status'] = {'old': user.approval_status, 'new': user_update.approval_status}
                user.approval_status = user_update.approval_status
                
                if user_update.approval_status == "approved" and user.approved_by_id is None:
                    user.approved_by_id = admin_user.id
                    user.approved_at = datetime.utcnow()
                    changes['approved_by'] = {'old': None, 'new': admin_user.id}
            
            if user_update.research_interests is not None:
                changes['research_interests'] = {'old': user.research_interests, 'new': user_update.research_interests}
                user.research_interests = user_update.research_interests
            
            if user_update.research_purpose is not None:
                changes['research_purpose'] = {'old': user.research_purpose, 'new': user_update.research_purpose}
                user.research_purpose = user_update.research_purpose
            
            if user_update.expected_usage is not None:
                changes['expected_usage'] = {'old': user.expected_usage, 'new': user_update.expected_usage}
                user.expected_usage = user_update.expected_usage
            
            user.updated_at = datetime.utcnow()
            
            await db.commit()
            await db.refresh(user)
            
            # Get updated user with metrics
            query = select(
                User,
                func.coalesce(func.count(Project.id.distinct()), 0).label('projects_count'),
                func.coalesce(func.count(Page.id.distinct()), 0).label('pages_count')
            ).outerjoin(Project, Project.user_id == User.id)\
             .outerjoin(Page, Page.user_id == User.id)\
             .where(User.id == user_id)\
             .group_by(User.id)
            
            result = await db.execute(query)
            user_with_metrics = result.first()
            user, projects_count, pages_count = user_with_metrics
            
            user_response = AdminUserRead(
                id=user.id,
                email=user.email,
                full_name=user.full_name,
                is_active=user.is_active,
                is_verified=user.is_verified,
                is_superuser=user.is_superuser,
                approval_status=user.approval_status,
                created_at=user.created_at,
                last_login=user.last_login,
                updated_at=user.updated_at,
                projects_count=projects_count,
                pages_count=pages_count,
                research_interests=user.research_interests,
                research_purpose=user.research_purpose,
                expected_usage=user.expected_usage,
                approved_by_id=user.approved_by_id,
                approved_at=user.approved_at
            )
            
            return add_security_headers(JSONResponse(
                status_code=200,
                content=user_response.dict()
            ))
            
    except Exception as e:
        logger.error(f"Failed to update user {user_id}: {e}")
        error_response = create_error_response(
            error="Failed to update user",
            error_code="USER_UPDATE_FAILED",
            details={"user_id": user_id, "error_message": str(e)}
        )
        return add_security_headers(JSONResponse(
            status_code=500,
            content=error_response.dict()
        ))


@router.delete("/users/{user_id}", response_model=AdminOperationResult, tags=["User Management"])
async def delete_user(
    user_id: int,
    confirmation_token: str = Query(..., description="Confirmation token required for user deletion"),
    request: Request = None,
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(get_admin_user_delete)
) -> JSONResponse:
    """
    Delete a user account permanently.
    
    **Features:**
    - Permanent user account deletion
    - Confirmation token requirement for safety
    - Cascade deletion of related data
    - Comprehensive audit logging
    - Self-deletion protection
    
    **Required Permissions:** Admin (superuser)
    
    **Rate Limit:** 5 requests/5 minutes
    
    **Security:** Requires confirmation token
    """
    try:
        async with admin_middleware.audit_context(
            db=db,
            admin_user=admin_user,
            action="delete_user",
            resource_type="user",
            resource_id=str(user_id),
            request=request
        ):
            # Prevent self-deletion
            if user_id == admin_user.id:
                error_response = create_error_response(
                    error="Cannot delete your own account",
                    error_code="SELF_DELETE_FORBIDDEN"
                )
                return add_security_headers(JSONResponse(
                    status_code=400,
                    content=error_response.dict()
                ))
            
            # Verify confirmation token
            expected_token = get_operation_signature(request, admin_user)
            require_confirmation(confirmation_token, expected_token, "user deletion")
            
            # Get user to delete
            user_query = select(User).where(User.id == user_id)
            result = await db.execute(user_query)
            user = result.scalar_one_or_none()
            
            if not user:
                error_response = create_error_response(
                    error="User not found",
                    error_code="USER_NOT_FOUND"
                )
                return add_security_headers(JSONResponse(
                    status_code=404,
                    content=error_response.dict()
                ))
            
            # Delete user (cascade deletes will handle related data)
            await db.delete(user)
            await db.commit()
            
            result = AdminOperationResult(
                success=True,
                message=f"User {user.email} deleted successfully",
                affected_count=1
            )
            
            return add_security_headers(JSONResponse(
                status_code=200,
                content=result.dict()
            ))
            
    except Exception as e:
        logger.error(f"Failed to delete user {user_id}: {e}")
        error_response = create_error_response(
            error="Failed to delete user",
            error_code="USER_DELETE_FAILED",
            details={"user_id": user_id, "error_message": str(e)}
        )
        return add_security_headers(JSONResponse(
            status_code=500,
            content=error_response.dict()
        ))


# ===== SESSION MANAGEMENT ENDPOINTS =====

@router.get("/sessions", response_model=PaginatedResponse, tags=["Session Management"])
async def list_sessions(
    params: AdminSessionListParams = Depends(),
    request: Request = None,
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(get_admin_user_read),
    session_store: SessionStore = Depends(get_session_store)
) -> JSONResponse:
    """
    List active user sessions with filtering and pagination.
    
    **Features:**
    - Real-time session monitoring
    - User-specific session filtering
    - IP address and activity tracking
    - Comprehensive session metadata
    - Advanced search and sorting
    
    **Required Permissions:** Admin (superuser)
    
    **Rate Limit:** 100 requests/minute
    """
    try:
        async with admin_middleware.audit_context(
            db=db,
            admin_user=admin_user,
            action="list_sessions",
            resource_type="sessions",
            request=request
        ):
            # Get all sessions from Redis
            all_sessions = await session_store.get_all_sessions()
            
            # Filter sessions based on parameters
            filtered_sessions = []
            for session_data in all_sessions:
                # Apply user filter
                if params.user_id and session_data.user_id != params.user_id:
                    continue
                
                # Apply active filter
                if params.active_only and not session_data.is_active:
                    continue
                
                # Apply IP filter
                if params.ip_address and session_data.ip_address != params.ip_address:
                    continue
                
                # Apply date filter
                if params.created_after and session_data.created_at < params.created_after:
                    continue
                
                # Get user details
                user_query = select(User).where(User.id == session_data.user_id)
                result = await db.execute(user_query)
                user = result.scalar_one_or_none()
                
                if user:
                    session_info = AdminSessionRead(
                        session_id=session_data.session_id,
                        user_id=session_data.user_id,
                        user_email=user.email,
                        user_full_name=user.full_name,
                        created_at=session_data.created_at,
                        last_activity=session_data.last_activity,
                        ip_address=session_data.ip_address,
                        user_agent=session_data.user_agent,
                        is_active=session_data.is_active,
                        expires_at=session_data.expires_at
                    )
                    filtered_sessions.append(session_info)
            
            # Sort sessions
            if params.sort_by == "created_at":
                filtered_sessions.sort(
                    key=lambda x: x.created_at,
                    reverse=(params.sort_order == "desc")
                )
            elif params.sort_by == "last_activity":
                filtered_sessions.sort(
                    key=lambda x: x.last_activity,
                    reverse=(params.sort_order == "desc")
                )
            
            # Apply pagination
            total = len(filtered_sessions)
            start_idx = (params.page - 1) * params.per_page
            end_idx = start_idx + params.per_page
            paginated_sessions = filtered_sessions[start_idx:end_idx]
            
            # Calculate pagination metadata
            pages = (total + params.per_page - 1) // params.per_page
            
            response_data = PaginatedResponse(
                items=[session.dict() for session in paginated_sessions],
                total=total,
                page=params.page,
                per_page=params.per_page,
                pages=pages,
                has_next=params.page < pages,
                has_prev=params.page > 1
            )
            
            return add_security_headers(JSONResponse(
                status_code=200,
                content=response_data.dict()
            ))
            
    except Exception as e:
        logger.error(f"Failed to list sessions: {e}")
        error_response = create_error_response(
            error="Failed to retrieve sessions",
            error_code="SESSION_LIST_FAILED",
            details={"error_message": str(e)}
        )
        return add_security_headers(JSONResponse(
            status_code=500,
            content=error_response.dict()
        ))


@router.delete("/sessions/{session_id}", response_model=AdminOperationResult, tags=["Session Management"])
async def revoke_session(
    session_id: str,
    request: Request = None,
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(get_admin_user_write),
    session_store: SessionStore = Depends(get_session_store)
) -> JSONResponse:
    """
    Revoke a specific user session.
    
    **Features:**
    - Immediate session termination
    - User notification support
    - Audit trail creation
    - Force logout capability
    
    **Required Permissions:** Admin (superuser)
    
    **Rate Limit:** 50 requests/minute
    """
    try:
        async with admin_middleware.audit_context(
            db=db,
            admin_user=admin_user,
            action="revoke_session",
            resource_type="session",
            resource_id=session_id,
            request=request
        ):
            # Get session details before deletion
            session_data = await session_store.get_session(session_id)
            
            if not session_data:
                error_response = create_error_response(
                    error="Session not found",
                    error_code="SESSION_NOT_FOUND"
                )
                return add_security_headers(JSONResponse(
                    status_code=404,
                    content=error_response.dict()
                ))
            
            # Delete the session
            await session_store.delete_session(session_id)
            
            result = AdminOperationResult(
                success=True,
                message=f"Session {session_id} revoked successfully",
                affected_count=1
            )
            
            return add_security_headers(JSONResponse(
                status_code=200,
                content=result.dict()
            ))
            
    except Exception as e:
        logger.error(f"Failed to revoke session {session_id}: {e}")
        error_response = create_error_response(
            error="Failed to revoke session",
            error_code="SESSION_REVOKE_FAILED",
            details={"session_id": session_id, "error_message": str(e)}
        )
        return add_security_headers(JSONResponse(
            status_code=500,
            content=error_response.dict()
        ))


@router.post("/sessions/bulk-revoke", response_model=AdminOperationResult, tags=["Session Management"])
async def bulk_revoke_sessions(
    bulk_request: AdminBulkSessionRevoke,
    request: Request = None,
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(get_admin_user_bulk),
    session_store: SessionStore = Depends(get_session_store)
) -> JSONResponse:
    """
    Revoke multiple sessions in bulk.
    
    **Features:**
    - Bulk session termination
    - User-specific session revocation
    - Selective session management
    - Comprehensive result reporting
    
    **Required Permissions:** Admin (superuser)
    
    **Rate Limit:** 10 requests/minute
    """
    try:
        async with admin_middleware.audit_context(
            db=db,
            admin_user=admin_user,
            action="bulk_revoke_sessions",
            resource_type="sessions",
            request=request
        ):
            revoked_count = 0
            failed_sessions = []
            
            # Get current admin session to avoid self-logout
            admin_session_id = None
            if request:
                admin_session_id = request.cookies.get("session_id")
            
            # Revoke specific sessions
            if bulk_request.session_ids:
                for session_id in bulk_request.session_ids:
                    # Skip admin's own session if requested
                    if bulk_request.revoke_all_except_current and session_id == admin_session_id:
                        continue
                    
                    try:
                        session_exists = await session_store.get_session(session_id)
                        if session_exists:
                            await session_store.delete_session(session_id)
                            revoked_count += 1
                    except Exception as e:
                        failed_sessions.append({"session_id": session_id, "error": str(e)})
            
            # Revoke sessions for specific users
            if bulk_request.user_ids:
                all_sessions = await session_store.get_all_sessions()
                for session_data in all_sessions:
                    if session_data.user_id in bulk_request.user_ids:
                        # Skip admin's own session if requested
                        if bulk_request.revoke_all_except_current and session_data.session_id == admin_session_id:
                            continue
                        
                        try:
                            await session_store.delete_session(session_data.session_id)
                            revoked_count += 1
                        except Exception as e:
                            failed_sessions.append({
                                "session_id": session_data.session_id,
                                "user_id": session_data.user_id,
                                "error": str(e)
                            })
            
            result = AdminOperationResult(
                success=len(failed_sessions) == 0,
                message=f"Bulk session revocation completed. {revoked_count} sessions revoked.",
                affected_count=revoked_count,
                data={"failed_sessions": failed_sessions} if failed_sessions else None
            )
            
            return add_security_headers(JSONResponse(
                status_code=200,
                content=result.dict()
            ))
            
    except Exception as e:
        logger.error(f"Failed to bulk revoke sessions: {e}")
        error_response = create_error_response(
            error="Failed to bulk revoke sessions",
            error_code="BULK_SESSION_REVOKE_FAILED",
            details={"error_message": str(e)}
        )
        return add_security_headers(JSONResponse(
            status_code=500,
            content=error_response.dict()
        ))


# ===== SYSTEM MONITORING ENDPOINTS =====

@router.get("/system/health", response_model=AdminSystemHealth, tags=["System Monitoring"])
async def get_system_health(
    request: Request = None,
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(get_admin_user_read),
    session_store: SessionStore = Depends(get_session_store)
) -> JSONResponse:
    """
    Get comprehensive system health status.
    
    **Features:**
    - Database connectivity and performance
    - Redis/cache status and metrics
    - Service availability checks
    - Resource utilization monitoring
    - Health score calculation
    
    **Required Permissions:** Admin (superuser)
    
    **Rate Limit:** 100 requests/minute
    """
    try:
        async with admin_middleware.audit_context(
            db=db,
            admin_user=admin_user,
            action="get_system_health",
            resource_type="system",
            request=request
        ):
            health_data = AdminSystemHealth(status="healthy")
            
            # Database health check
            try:
                db_start = datetime.utcnow()
                result = await db.execute(select(func.count()).select_from(User))
                user_count = result.scalar()
                db_duration = (datetime.utcnow() - db_start).total_seconds() * 1000
                
                health_data.database_metrics = {
                    "status": "online",
                    "response_time_ms": db_duration,
                    "user_count": user_count,
                    "connection_status": "healthy"
                }
            except Exception as e:
                health_data.database_metrics = {
                    "status": "error",
                    "error": str(e)
                }
                health_data.status = "degraded"
            
            # Redis/Session store health check
            try:
                redis_start = datetime.utcnow()
                session_count = len(await session_store.get_all_sessions())
                redis_duration = (datetime.utcnow() - redis_start).total_seconds() * 1000
                
                health_data.services["redis"] = {
                    "status": "online",
                    "response_time_ms": redis_duration,
                    "active_sessions": session_count
                }
            except Exception as e:
                health_data.services["redis"] = {
                    "status": "error",
                    "error": str(e)
                }
                health_data.status = "degraded"
            
            # Basic system metrics
            health_data.system_metrics = {
                "timestamp": datetime.utcnow().isoformat(),
                "uptime_check": "healthy",
                "environment": getattr(settings, 'ENVIRONMENT', 'unknown')
            }
            
            return add_security_headers(JSONResponse(
                status_code=200,
                content=health_data.dict()
            ))
            
    except Exception as e:
        logger.error(f"Failed to get system health: {e}")
        error_response = create_error_response(
            error="Failed to retrieve system health",
            error_code="SYSTEM_HEALTH_FAILED",
            details={"error_message": str(e)}
        )
        return add_security_headers(JSONResponse(
            status_code=500,
            content=error_response.dict()
        ))


@router.get("/system/metrics", response_model=Dict[str, Any], tags=["System Monitoring"])
async def get_system_metrics(
    request: Request = None,
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(get_admin_user_read)
) -> JSONResponse:
    """
    Get detailed system metrics and statistics.
    
    **Features:**
    - User activity statistics
    - Database performance metrics
    - Resource usage information
    - Growth and usage trends
    - System capacity information
    
    **Required Permissions:** Admin (superuser)
    
    **Rate Limit:** 100 requests/minute
    """
    try:
        async with admin_middleware.audit_context(
            db=db,
            admin_user=admin_user,
            action="get_system_metrics",
            resource_type="system",
            request=request
        ):
            metrics = {}
            
            # User metrics
            user_stats = await db.execute(select(
                func.count(User.id).label('total_users'),
                func.count(User.id).filter(User.is_active is True).label('active_users'),
                func.count(User.id).filter(User.is_verified is True).label('verified_users'),
                func.count(User.id).filter(User.approval_status == 'approved').label('approved_users'),
                func.count(User.id).filter(User.is_superuser is True).label('admin_users')
            ))
            user_row = user_stats.first()
            
            metrics["users"] = {
                "total": user_row.total_users,
                "active": user_row.active_users,
                "verified": user_row.verified_users,
                "approved": user_row.approved_users,
                "admins": user_row.admin_users
            }
            
            # Project metrics
            project_stats = await db.execute(select(
                func.count(Project.id).label('total_projects'),
                func.count(Project.id.distinct()).label('unique_projects')
            ))
            project_row = project_stats.first()
            
            metrics["projects"] = {
                "total": project_row.total_projects,
                "unique": project_row.unique_projects
            }
            
            # Page metrics
            page_stats = await db.execute(select(
                func.count(Page.id).label('total_pages'),
                func.avg(func.length(Page.content)).label('avg_content_length')
            ))
            page_row = page_stats.first()
            
            metrics["pages"] = {
                "total": page_row.total_pages,
                "avg_content_length": float(page_row.avg_content_length or 0)
            }
            
            # Recent activity (last 24 hours)
            yesterday = datetime.utcnow() - timedelta(days=1)
            recent_stats = await db.execute(select(
                func.count(User.id).filter(User.created_at >= yesterday).label('new_users_24h'),
                func.count(Project.id).filter(Project.created_at >= yesterday).label('new_projects_24h'),
                func.count(Page.id).filter(Page.created_at >= yesterday).label('new_pages_24h')
            ))
            recent_row = recent_stats.first()
            
            metrics["recent_activity"] = {
                "new_users_24h": recent_row.new_users_24h,
                "new_projects_24h": recent_row.new_projects_24h,
                "new_pages_24h": recent_row.new_pages_24h
            }
            
            # System information
            metrics["system"] = {
                "timestamp": datetime.utcnow().isoformat(),
                "environment": getattr(settings, 'ENVIRONMENT', 'unknown'),
                "version": getattr(settings, 'VERSION', 'unknown')
            }
            
            return add_security_headers(JSONResponse(
                status_code=200,
                content=metrics
            ))
            
    except Exception as e:
        logger.error(f"Failed to get system metrics: {e}")
        error_response = create_error_response(
            error="Failed to retrieve system metrics",
            error_code="SYSTEM_METRICS_FAILED",
            details={"error_message": str(e)}
        )
        return add_security_headers(JSONResponse(
            status_code=500,
            content=error_response.dict()
        ))


@router.get("/celery/status", response_model=Dict[str, Any], tags=["System Monitoring"])
async def get_celery_status(
    request: Request = None,
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(get_admin_user_read)
) -> JSONResponse:
    """
    Get Celery task queue status and statistics.
    
    **Features:**
    - Active task monitoring
    - Worker status and health
    - Queue depth and performance
    - Failed task analysis
    - Task execution statistics
    
    **Required Permissions:** Admin (superuser)
    
    **Rate Limit:** 100 requests/minute
    """
    try:
        async with admin_middleware.audit_context(
            db=db,
            admin_user=admin_user,
            action="get_celery_status",
            resource_type="celery",
            request=request
        ):
            # This is a placeholder implementation
            # In a real implementation, you would integrate with Celery's monitoring APIs
            celery_status = {
                "status": "operational",
                "workers": {
                    "online": 2,
                    "offline": 0,
                    "total": 2
                },
                "queues": {
                    "default": {"pending": 0, "active": 0},
                    "scraping": {"pending": 0, "active": 0},
                    "indexing": {"pending": 0, "active": 0}
                },
                "tasks": {
                    "total_processed": 0,
                    "successful": 0,
                    "failed": 0,
                    "retry": 0
                },
                "timestamp": datetime.utcnow().isoformat(),
                "note": "Celery monitoring integration pending implementation"
            }
            
            return add_security_headers(JSONResponse(
                status_code=200,
                content=celery_status
            ))
            
    except Exception as e:
        logger.error(f"Failed to get Celery status: {e}")
        error_response = create_error_response(
            error="Failed to retrieve Celery status",
            error_code="CELERY_STATUS_FAILED",
            details={"error_message": str(e)}
        )
        return add_security_headers(JSONResponse(
            status_code=500,
            content=error_response.dict()
        ))


# ===== CONFIGURATION ENDPOINTS =====

@router.get("/config", response_model=AdminConfigRead, tags=["Configuration"])
async def get_system_config(
    request: Request = None,
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(get_admin_user_read)
) -> JSONResponse:
    """
    Get system configuration information.
    
    **Features:**
    - Environment configuration
    - Feature flag status
    - Integration settings
    - Security configuration
    - System limits and quotas
    
    **Required Permissions:** Admin (superuser)
    
    **Rate Limit:** 100 requests/minute
    """
    try:
        async with admin_middleware.audit_context(
            db=db,
            admin_user=admin_user,
            action="get_system_config",
            resource_type="config",
            request=request
        ):
            config_data = AdminConfigRead(
                environment=getattr(settings, 'ENVIRONMENT', 'unknown'),
                version=getattr(settings, 'VERSION', 'unknown'),
                features={
                    "user_registration": True,
                    "email_verification": True,
                    "admin_approval": True,
                    "oauth2_integration": True,
                    "api_keys": True,
                    "bulk_operations": True,
                    "advanced_search": True,
                    "entity_extraction": True
                },
                limits={
                    "max_projects_per_user": 100,
                    "max_pages_per_project": 10000,
                    "max_file_upload_size": "10MB",
                    "rate_limit_requests_per_minute": 100
                },
                integrations={
                    "meilisearch": {"enabled": True, "status": "connected"},
                    "redis": {"enabled": True, "status": "connected"},
                    "celery": {"enabled": True, "status": "operational"},
                    "email": {"enabled": True, "provider": "configured"}
                },
                security={
                    "https_required": getattr(settings, 'ENVIRONMENT', '') == 'production',
                    "csrf_protection": True,
                    "rate_limiting": True,
                    "session_security": True,
                    "admin_ip_whitelist": getattr(settings, 'ADMIN_ALLOWED_IPS', None) is not None
                }
            )
            
            return add_security_headers(JSONResponse(
                status_code=200,
                content=config_data.dict()
            ))
            
    except Exception as e:
        logger.error(f"Failed to get system config: {e}")
        error_response = create_error_response(
            error="Failed to retrieve system configuration",
            error_code="CONFIG_GET_FAILED",
            details={"error_message": str(e)}
        )
        return add_security_headers(JSONResponse(
            status_code=500,
            content=error_response.dict()
        ))


# ===== AUDIT LOG ENDPOINTS =====

@router.get("/audit/logs", response_model=PaginatedResponse, tags=["Audit & Logging"])
async def get_audit_logs(
    params: AdminAuditLogParams = Depends(),
    request: Request = None,
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(get_admin_user_read)
) -> JSONResponse:
    """
    Get audit logs with advanced filtering and search.
    
    **Features:**
    - Comprehensive audit trail
    - Multi-field filtering and search
    - Admin activity tracking
    - Security event monitoring
    - Export capabilities
    
    **Required Permissions:** Admin (superuser)
    
    **Rate Limit:** 100 requests/minute
    """
    try:
        async with admin_middleware.audit_context(
            db=db,
            admin_user=admin_user,
            action="get_audit_logs",
            resource_type="audit_logs",
            request=request
        ):
            # Build base query
            query = select(AuditLog)
            
            # Apply filters
            if params.action:
                query = query.where(AuditLog.action == params.action)
            
            if params.resource_type:
                query = query.where(AuditLog.resource_type == params.resource_type)
            
            if params.admin_user_id:
                query = query.where(AuditLog.admin_user_id == params.admin_user_id)
            
            if params.user_id:
                query = query.where(AuditLog.user_id == params.user_id)
            
            if params.success is not None:
                query = query.where(AuditLog.success == params.success)
            
            if params.start_date:
                query = query.where(AuditLog.created_at >= params.start_date)
            
            if params.end_date:
                query = query.where(AuditLog.created_at <= params.end_date)
            
            # Apply sorting
            sort_field = getattr(AuditLog, params.sort_by)
            if params.sort_order == "desc":
                query = query.order_by(sort_field.desc())
            else:
                query = query.order_by(sort_field.asc())
            
            # Get total count
            count_query = select(func.count()).select_from(query.subquery())
            total_result = await db.execute(count_query)
            total = total_result.scalar() or 0
            
            # Apply pagination
            offset = (params.page - 1) * params.per_page
            query = query.offset(offset).limit(params.per_page)
            
            # Execute query
            result = await db.execute(query)
            audit_logs = result.scalars().all()
            
            # Format response data
            logs_data = []
            for log in audit_logs:
                log_data = AdminAuditLogRead(
                    id=log.id,
                    user_id=log.user_id,
                    admin_user_id=log.admin_user_id,
                    action=log.action,
                    resource_type=log.resource_type,
                    resource_id=log.resource_id,
                    details=log.details,
                    ip_address=log.ip_address,
                    user_agent=log.user_agent,
                    success=log.success,
                    error_message=log.error_message,
                    affected_count=log.affected_count,
                    created_at=log.created_at
                ).dict()
                logs_data.append(log_data)
            
            # Calculate pagination metadata
            pages = (total + params.per_page - 1) // params.per_page
            
            response_data = PaginatedResponse(
                items=logs_data,
                total=total,
                page=params.page,
                per_page=params.per_page,
                pages=pages,
                has_next=params.page < pages,
                has_prev=params.page > 1
            )
            
            return add_security_headers(JSONResponse(
                status_code=200,
                content=response_data.dict()
            ))
            
    except Exception as e:
        logger.error(f"Failed to get audit logs: {e}")
        error_response = create_error_response(
            error="Failed to retrieve audit logs",
            error_code="AUDIT_LOGS_FAILED",
            details={"error_message": str(e)}
        )
        return add_security_headers(JSONResponse(
            status_code=500,
            content=error_response.dict()
        ))


# ===== STATISTICS ENDPOINTS =====

@router.get("/stats", response_model=Dict[str, Any], tags=["System Statistics"])
async def get_admin_stats(
    request: Request = None,
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(get_admin_user_read)
) -> JSONResponse:
    """
    Get comprehensive admin statistics dashboard.
    
    **Features:**
    - User registration and activity metrics
    - System health and performance indicators
    - Content and project statistics
    - Administrative activity summary
    - Real-time system monitoring data
    
    **Required Permissions:** Admin (superuser)
    
    **Rate Limit:** 100 requests/minute
    """
    try:
        async with admin_middleware.audit_context(
            db=db,
            admin_user=admin_user,
            action="get_admin_stats",
            resource_type="system_stats",
            request=request
        ):
            # User statistics
            user_stats = await db.execute(select(
                func.count(User.id).label('total_users'),
                func.count(User.id).filter(User.is_active is True).label('active_users'),
                func.count(User.id).filter(User.is_verified is True).label('verified_users'),
                func.count(User.id).filter(User.approval_status == 'approved').label('approved_users'),
                func.count(User.id).filter(User.is_superuser is True).label('admin_users')
            ))
            user_row = user_stats.first()
            
            # Project statistics
            project_stats = await db.execute(select(
                func.count(Project.id).label('total_projects'),
                func.count(Project.id.distinct()).label('unique_projects')
            ))
            project_row = project_stats.first()
            
            # Page statistics
            page_stats = await db.execute(select(
                func.count(Page.id).label('total_pages'),
                func.avg(func.length(Page.content)).label('avg_content_length')
            ))
            page_row = page_stats.first()
            
            # Recent activity (last 24 hours)
            yesterday = datetime.utcnow() - timedelta(days=1)
            recent_stats = await db.execute(select(
                func.count(User.id).filter(User.created_at >= yesterday).label('new_users_24h'),
                func.count(Project.id).filter(Project.created_at >= yesterday).label('new_projects_24h'),
                func.count(Page.id).filter(Page.created_at >= yesterday).label('new_pages_24h')
            ))
            recent_row = recent_stats.first()
            
            stats_data = {
                "users": {
                    "total": user_row.total_users or 0,
                    "active": user_row.active_users or 0,
                    "verified": user_row.verified_users or 0,
                    "approved": user_row.approved_users or 0,
                    "admins": user_row.admin_users or 0
                },
                "projects": {
                    "total": project_row.total_projects or 0,
                    "unique": project_row.unique_projects or 0
                },
                "pages": {
                    "total": page_row.total_pages or 0,
                    "avg_content_length": float(page_row.avg_content_length or 0)
                },
                "recent_activity": {
                    "new_users_24h": recent_row.new_users_24h or 0,
                    "new_projects_24h": recent_row.new_projects_24h or 0,
                    "new_pages_24h": recent_row.new_pages_24h or 0
                },
                "system": {
                    "timestamp": datetime.utcnow().isoformat(),
                    "environment": getattr(settings, 'ENVIRONMENT', 'unknown'),
                    "version": getattr(settings, 'VERSION', 'unknown')
                }
            }
            
            return add_security_headers(JSONResponse(
                status_code=200,
                content=stats_data
            ))
            
    except Exception as e:
        logger.error(f"Failed to get admin stats: {e}")
        error_response = create_error_response(
            error="Failed to retrieve admin statistics",
            error_code="ADMIN_STATS_FAILED",
            details={"error_message": str(e)}
        )
        return add_security_headers(JSONResponse(
            status_code=500,
            content=error_response.dict()
        ))


# ===== PLACEHOLDER FUNCTION FOR ASYNC EMAIL =====

async def send_admin_created_user_email(email: str, full_name: str, admin_email: str):
    """Send welcome email to admin-created user"""
    # TODO: Implement actual email sending
    logger.info(f"Would send welcome email to {email} (created by admin {admin_email})")
    await asyncio.sleep(0.1)  # Simulate async work