"""
Secure Project Sharing API Endpoints with Multi-Tenant Meilisearch

This module provides endpoints for secure project sharing using tenant tokens
and project-specific API keys, ensuring proper isolation between shared projects.
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query, Request
from fastapi.security import HTTPBearer
from sqlmodel import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from ....core.database import get_db
from ....models.user import User
from ....models.project import Project
from ....models.sharing import (
    ProjectShare, ProjectShareCreate, ProjectShareRead, ProjectShareUpdate,
    PublicSearchConfig, PublicSearchConfigCreate, PublicSearchConfigRead,
    SharePermission, ShareStatus, PublicAccessLevel
)
from ....models.meilisearch_audit import MeilisearchKey, MeilisearchKeyType, MeilisearchSecurityEvent
from ....services.meilisearch_key_manager import meilisearch_key_manager
from ....api.deps import get_current_user, get_current_active_user
from ....core.config import settings
from ....core.rate_limiter import rate_limit_public_key_access, RateLimitResult

router = APIRouter()
security = HTTPBearer()
logger = logging.getLogger(__name__)


# Project Sharing with Tenant Tokens
@router.get("/projects/{project_id}/share-token", response_model=Dict[str, Any])
async def get_share_token(
    project_id: int,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get tenant token for shared project access
    
    This endpoint provides time-limited JWT tokens for users who have been granted
    access to a shared project. The token includes permission-based filtering.
    """
    try:
        # Verify user has share access to this project
        share_query = select(ProjectShare).where(
            and_(
                ProjectShare.project_id == project_id,
                ProjectShare.shared_with_user_id == current_user.id,
                ProjectShare.status == ShareStatus.ACTIVE
            )
        )
        
        result = await db.execute(share_query)
        share = result.scalar_one_or_none()
        
        if not share:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No active share found for this project"
            )
        
        # Check if share has expired
        if share.expires_at and share.expires_at < datetime.utcnow():
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Share access has expired"
            )
        
        # Get the project
        project_query = select(Project).where(Project.id == project_id)
        project_result = await db.execute(project_query)
        project = project_result.scalar_one_or_none()
        
        if not project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Project not found"
            )
        
        # Generate tenant token using the key manager
        tenant_token = await meilisearch_key_manager.create_tenant_token(project, share)
        
        # Update share access tracking
        share.access_count += 1
        share.last_accessed = datetime.utcnow()
        
        # Log security event
        security_event = MeilisearchSecurityEvent(
            event_type="tenant_token_issued",
            severity="info",
            description=f"Tenant token issued for user {current_user.id} on project {project_id}",
            user_id=current_user.id,
            automated=False,
            metadata={
                "project_id": project_id,
                "user_id": current_user.id,
                "permission": share.permission.value,
                "expires_at": share.expires_at.isoformat() if share.expires_at else None
            }
        )
        db.add(security_event)
        
        await db.commit()
        
        logger.info(f"Tenant token issued for user {current_user.id} on project {project_id}")
        
        return {
            "token": tenant_token,
            "expires_at": share.expires_at,
            "permissions": share.permission.value,
            "index_name": f"project_{project.id}",
            "project_name": project.name,
            "access_level": _get_access_description(share.permission)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to generate share token for project {project_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate share token"
        )


@router.get("/projects/{project_id}/owner-search-key", response_model=Dict[str, Any])
async def get_owner_search_key(
    project_id: int,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get project owner's dedicated search key
    
    This endpoint returns the project-specific search key for project owners,
    providing full search access to their own project index.
    """
    try:
        # Verify user owns this project
        project_query = select(Project).where(
            and_(
                Project.id == project_id,
                Project.user_id == current_user.id
            )
        )
        
        result = await db.execute(project_query)
        project = result.scalar_one_or_none()
        
        if not project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Project not found or access denied"
            )
        
        if not project.index_search_key:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Project search key not configured"
            )
        
        # Get key status for additional info
        key_status = await meilisearch_key_manager.get_key_status(project.index_search_key_uid)
        
        # Update key usage tracking
        if project.index_search_key_uid:
            audit_query = select(MeilisearchKey).where(
                MeilisearchKey.key_uid == project.index_search_key_uid
            )
            audit_result = await db.execute(audit_query)
            audit_record = audit_result.scalar_one_or_none()
            
            if audit_record:
                audit_record.usage_count += 1
                audit_record.last_used_at = datetime.utcnow()
                await db.commit()
        
        logger.info(f"Owner search key accessed for project {project_id} by user {current_user.id}")
        
        return {
            "key": project.index_search_key,
            "index_name": f"project_{project.id}",
            "permissions": ["search", "documents.get"],
            "created_at": project.key_created_at,
            "last_rotated": project.key_last_rotated,
            "key_status": key_status,
            "expires_at": key_status.get("expires_at")
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get owner search key for project {project_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve search key"
        )


# Public Search Configuration
@router.post("/projects/{project_id}/public-search", response_model=PublicSearchConfigRead)
async def create_public_search_config(
    project_id: int,
    config_data: PublicSearchConfigCreate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Configure public search access for a project
    
    This creates a public search configuration with a dedicated read-only key
    that allows public access to the project's search interface.
    """
    try:
        # Verify user owns this project
        project_query = select(Project).where(
            and_(
                Project.id == project_id,
                Project.user_id == current_user.id
            )
        )
        
        result = await db.execute(project_query)
        project = result.scalar_one_or_none()
        
        if not project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Project not found or access denied"
            )
        
        # Check if public config already exists
        existing_config_query = select(PublicSearchConfig).where(
            PublicSearchConfig.project_id == project_id
        )
        existing_result = await db.execute(existing_config_query)
        existing_config = existing_result.scalar_one_or_none()
        
        if existing_config:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Public search configuration already exists"
            )
        
        # Create public search key if enabling
        search_key = None
        search_key_uid = None
        
        if config_data.is_enabled:
            key_data = await meilisearch_key_manager.create_public_key(project)
            search_key = key_data['key']
            search_key_uid = key_data['uid']
            
            # Create audit record for public key
            public_key_audit = MeilisearchKey(
                project_id=project.id,
                key_uid=search_key_uid,
                key_type=MeilisearchKeyType.PUBLIC,
                key_name=f"public_search_project_{project.id}",
                key_description=f"Public search access for project: {project.name}",
                actions=["search"],
                indexes=[f"project_{project.id}"]
            )
            db.add(public_key_audit)
        
        # Create public search configuration
        config_dict = config_data.model_dump()
        config_dict.update({
            "search_key": search_key,
            "search_key_uid": search_key_uid,
            "key_created_at": datetime.utcnow() if search_key else None
        })
        
        public_config = PublicSearchConfig(**config_dict)
        db.add(public_config)
        
        # Log security event
        security_event = MeilisearchSecurityEvent(
            event_type="public_search_configured",
            severity="info",
            description=f"Public search configured for project {project_id}",
            user_id=current_user.id,
            automated=False,
            metadata={
                "project_id": project_id,
                "enabled": config_data.is_enabled,
                "rate_limit": config_data.rate_limit_per_hour
            }
        )
        db.add(security_event)
        
        await db.commit()
        await db.refresh(public_config)
        
        logger.info(f"Public search configured for project {project_id} by user {current_user.id}")
        
        return public_config
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create public search config for project {project_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create public search configuration"
        )


@router.get("/public/projects/{project_id}/search-key", response_model=Dict[str, Any])
async def get_public_search_key(
    project_id: int,
    db: AsyncSession = Depends(get_db),
    rate_limit_result: RateLimitResult = Depends(rate_limit_public_key_access)
):
    """
    Get public search key for anonymous access
    
    This endpoint provides public search keys for projects that have enabled
    public access. No authentication required.
    """
    try:
        # Get public search configuration
        config_query = select(PublicSearchConfig).where(
            and_(
                PublicSearchConfig.project_id == project_id,
                PublicSearchConfig.is_enabled == True
            )
        )
        
        result = await db.execute(config_query)
        public_config = result.scalar_one_or_none()
        
        if not public_config or not public_config.search_key:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Public search not available for this project"
            )
        
        # Get project info for display
        project_query = select(Project).where(Project.id == project_id)
        project_result = await db.execute(project_query)
        project = project_result.scalar_one_or_none()
        
        if not project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Project not found"
            )
        
        # Update usage tracking
        if public_config.search_key_uid:
            audit_query = select(MeilisearchKey).where(
                MeilisearchKey.key_uid == public_config.search_key_uid
            )
            audit_result = await db.execute(audit_query)
            audit_record = audit_result.scalar_one_or_none()
            
            if audit_record:
                audit_record.usage_count += 1
                audit_record.last_used_at = datetime.utcnow()
                await db.commit()
        
        logger.info(f"Public search key accessed for project {project_id}")
        
        return {
            "key": public_config.search_key,
            "index_name": f"project_{project.id}",
            "permissions": ["search"],
            "rate_limit_per_hour": public_config.rate_limit_per_hour,
            "project_title": public_config.custom_title or project.name,
            "project_description": public_config.custom_description or project.description,
            "allow_downloads": public_config.allow_downloads
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get public search key for project {project_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve public search key"
        )


# Key Management Endpoints
@router.post("/projects/{project_id}/rotate-key", response_model=Dict[str, Any])
async def rotate_project_key(
    project_id: int,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Manually rotate a project's search key
    
    This endpoint allows project owners to manually rotate their search key
    for security purposes.
    """
    try:
        # Verify user owns this project
        project_query = select(Project).where(
            and_(
                Project.id == project_id,
                Project.user_id == current_user.id
            )
        )
        
        result = await db.execute(project_query)
        project = result.scalar_one_or_none()
        
        if not project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Project not found or access denied"
            )
        
        # Rotate the key
        new_key_data = await meilisearch_key_manager.rotate_project_key(project)
        
        # Update project with new key
        project.index_search_key = new_key_data['key']
        project.index_search_key_uid = new_key_data['uid']
        project.key_last_rotated = datetime.utcnow()
        
        # Update audit records
        # Mark old key as revoked
        old_key_query = select(MeilisearchKey).where(
            and_(
                MeilisearchKey.project_id == project_id,
                MeilisearchKey.key_type == MeilisearchKeyType.PROJECT_OWNER,
                MeilisearchKey.is_active == True
            )
        )
        old_key_result = await db.execute(old_key_query)
        old_keys = old_key_result.scalars().all()
        
        for old_key in old_keys:
            old_key.is_active = False
            old_key.revoked_at = datetime.utcnow()
            old_key.revoked_reason = "Manual key rotation"
        
        # Create new audit record
        new_audit_record = MeilisearchKey(
            project_id=project.id,
            key_uid=new_key_data['uid'],
            key_type=MeilisearchKeyType.PROJECT_OWNER,
            key_name=f"project_owner_{project.id}_manual_rotation",
            key_description=f"Manually rotated owner key for project: {project.name}",
            actions=["search", "documents.get"],
            indexes=[f"project_{project.id}"]
        )
        db.add(new_audit_record)
        
        # Log security event
        security_event = MeilisearchSecurityEvent(
            key_id=new_audit_record.id,
            event_type="manual_key_rotation",
            severity="info",
            description=f"Manual key rotation for project {project_id}",
            user_id=current_user.id,
            automated=False,
            metadata={
                "project_id": project_id,
                "rotation_reason": "manual_user_request"
            }
        )
        db.add(security_event)
        
        await db.commit()
        
        logger.info(f"Manual key rotation completed for project {project_id} by user {current_user.id}")
        
        return {
            "message": "Key rotated successfully",
            "new_key": new_key_data['key'],
            "rotated_at": project.key_last_rotated,
            "index_name": f"project_{project.id}"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to rotate key for project {project_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to rotate project key"
        )


@router.get("/projects/{project_id}/key-status", response_model=Dict[str, Any])
async def get_project_key_status(
    project_id: int,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get detailed status information for a project's keys
    """
    try:
        # Verify user owns this project
        project_query = select(Project).where(
            and_(
                Project.id == project_id,
                Project.user_id == current_user.id
            )
        )
        
        result = await db.execute(project_query)
        project = result.scalar_one_or_none()
        
        if not project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Project not found or access denied"
            )
        
        # Get all keys for this project
        project_keys = await meilisearch_key_manager.list_project_keys(project_id)
        
        return {
            "project_id": project_id,
            "owner_key": {
                "key_uid": project.index_search_key_uid,
                "created_at": project.key_created_at,
                "last_rotated": project.key_last_rotated,
                "rotation_enabled": getattr(project, 'key_rotation_enabled', True)
            },
            "all_keys": project_keys,
            "key_count": len(project_keys)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get key status for project {project_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve key status"
        )


def _get_access_description(permission: SharePermission) -> str:
    """Get human-readable description of access level"""
    descriptions = {
        SharePermission.READ: "Full read access to all project content",
        SharePermission.LIMITED: "Limited access - irrelevant content hidden",
        SharePermission.RESTRICTED: "Restricted access - only relevant content visible",
        SharePermission.WRITE: "Read and write access to project content",
        SharePermission.ADMIN: "Full administrative access to project"
    }
    return descriptions.get(permission, "Unknown access level")