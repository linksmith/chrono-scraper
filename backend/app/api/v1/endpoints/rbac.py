"""
RBAC (Role-Based Access Control) endpoints
"""
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, require_permission
from app.models.rbac import (
    PermissionRead,
    RoleRead,
    RoleCreate,
    RoleUpdate,
    RoleReadWithPermissions,
    UserRoleAssignment,
    PermissionType
)
from app.models.user import User
from app.services.rbac import RBACService
from app.services.auth import get_user_by_id

router = APIRouter()


@router.get("/permissions", response_model=List[PermissionRead])
async def get_permissions(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission(PermissionType.ADMIN_VIEW))
) -> List[PermissionRead]:
    """
    Get all permissions
    """
    permissions = await RBACService.get_permissions(db)
    return permissions


@router.get("/roles", response_model=List[RoleRead])
async def get_roles(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission(PermissionType.ADMIN_VIEW))
) -> List[RoleRead]:
    """
    Get all roles
    """
    roles = await RBACService.get_roles(db)
    return roles


@router.get("/roles/{role_id}", response_model=RoleReadWithPermissions)
async def get_role(
    role_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission(PermissionType.ADMIN_VIEW))
) -> RoleReadWithPermissions:
    """
    Get role by ID with permissions
    """
    role = await RBACService.get_role_by_id(db, role_id)
    if not role:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Role not found"
        )
    
    permissions = await RBACService.get_role_permissions(db, role_id)
    
    return RoleReadWithPermissions(
        **role.model_dump(),
        permissions=permissions
    )


@router.post("/roles", response_model=RoleRead)
async def create_role(
    role_create: RoleCreate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission(PermissionType.ADMIN_MANAGE))
) -> RoleRead:
    """
    Create a new role
    """
    # Check if role already exists
    existing_role = await RBACService.get_role_by_name(db, role_create.name)
    if existing_role:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Role with this name already exists"
        )
    
    role = await RBACService.create_role(db, role_create)
    return role


@router.put("/roles/{role_id}", response_model=RoleRead)
async def update_role(
    role_id: int,
    role_update: RoleUpdate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission(PermissionType.ADMIN_MANAGE))
) -> RoleRead:
    """
    Update a role
    """
    role = await RBACService.update_role(db, role_id, role_update)
    if not role:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Role not found"
        )
    
    return role


@router.delete("/roles/{role_id}")
async def delete_role(
    role_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission(PermissionType.ADMIN_MANAGE))
) -> dict:
    """
    Delete a role (only if not system role)
    """
    success = await RBACService.delete_role(db, role_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete system role or role not found"
        )
    
    return {"message": "Role deleted successfully"}


@router.post("/users/{user_id}/roles")
async def assign_user_roles(
    user_id: int,
    assignment: UserRoleAssignment,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission(PermissionType.ADMIN_USERS))
) -> dict:
    """
    Assign roles to a user
    """
    # Check if user exists
    user = await get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    # Validate role IDs
    for role_id in assignment.role_ids:
        role = await RBACService.get_role_by_id(db, role_id)
        if not role:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Role with ID {role_id} not found"
            )
    
    await RBACService.assign_roles_to_user(db, user_id, assignment.role_ids)
    
    return {"message": "Roles assigned successfully"}


@router.get("/users/{user_id}/roles", response_model=List[RoleRead])
async def get_user_roles(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission(PermissionType.ADMIN_USERS))
) -> List[RoleRead]:
    """
    Get user's roles
    """
    # Check if user exists
    user = await get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    roles = await RBACService.get_user_roles(db, user_id)
    return roles


@router.get("/users/{user_id}/permissions", response_model=List[str])
async def get_user_permissions(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission(PermissionType.ADMIN_USERS))
) -> List[str]:
    """
    Get user's permissions
    """
    # Check if user exists
    user = await get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    permissions = await RBACService.get_user_permissions(db, user_id)
    return list(permissions)


@router.post("/initialize")
async def initialize_rbac(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission(PermissionType.ADMIN_MANAGE))
) -> dict:
    """
    Initialize default RBAC roles and permissions
    """
    await RBACService.initialize_default_roles(db)
    return {"message": "RBAC system initialized successfully"}