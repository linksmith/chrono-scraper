"""
Role-Based Access Control (RBAC) services
"""
from typing import List, Optional, Set
from sqlmodel import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.rbac import (
    Permission, 
    Role, 
    PermissionCreate,
    RoleCreate,
    RoleUpdate,
    DefaultRole,
    DEFAULT_ROLES,
    PermissionType,
    role_permissions,
    user_roles
)
from app.models.user import User


class RBACService:
    """Service for RBAC operations"""
    
    @staticmethod
    async def create_permission(
        db: AsyncSession, 
        permission_create: PermissionCreate
    ) -> Permission:
        """Create a new permission"""
        permission = Permission(**permission_create.model_dump())
        db.add(permission)
        await db.commit()
        await db.refresh(permission)
        return permission
    
    @staticmethod
    async def get_permission_by_name(
        db: AsyncSession, 
        name: str
    ) -> Optional[Permission]:
        """Get permission by name"""
        result = await db.execute(select(Permission).where(Permission.name == name))
        return result.scalar_one_or_none()
    
    @staticmethod
    async def get_permissions(db: AsyncSession) -> List[Permission]:
        """Get all permissions"""
        result = await db.execute(select(Permission))
        return result.scalars().all()
    
    @staticmethod
    async def create_role(
        db: AsyncSession, 
        role_create: RoleCreate
    ) -> Role:
        """Create a new role with permissions"""
        # Create role
        role_data = role_create.model_dump(exclude={"permission_ids"})
        role = Role(**role_data)
        db.add(role)
        await db.commit()
        await db.refresh(role)
        
        # Assign permissions
        if role_create.permission_ids:
            await RBACService.assign_permissions_to_role(
                db, role.id, role_create.permission_ids
            )
        
        return role
    
    @staticmethod
    async def get_role_by_name(db: AsyncSession, name: str) -> Optional[Role]:
        """Get role by name"""
        result = await db.execute(select(Role).where(Role.name == name))
        return result.scalar_one_or_none()
    
    @staticmethod
    async def get_role_by_id(db: AsyncSession, role_id: int) -> Optional[Role]:
        """Get role by ID"""
        result = await db.execute(select(Role).where(Role.id == role_id))
        return result.scalar_one_or_none()
    
    @staticmethod
    async def get_roles(db: AsyncSession) -> List[Role]:
        """Get all roles"""
        result = await db.execute(select(Role))
        return result.scalars().all()
    
    @staticmethod
    async def update_role(
        db: AsyncSession, 
        role_id: int, 
        role_update: RoleUpdate
    ) -> Optional[Role]:
        """Update role"""
        role = await RBACService.get_role_by_id(db, role_id)
        if not role:
            return None
        
        # Update basic fields
        update_data = role_update.model_dump(exclude_unset=True, exclude={"permission_ids"})
        for field, value in update_data.items():
            setattr(role, field, value)
        
        # Update permissions if provided
        if role_update.permission_ids is not None:
            await RBACService.assign_permissions_to_role(
                db, role_id, role_update.permission_ids
            )
        
        await db.commit()
        await db.refresh(role)
        return role
    
    @staticmethod
    async def delete_role(db: AsyncSession, role_id: int) -> bool:
        """Delete role (only if not system role)"""
        role = await RBACService.get_role_by_id(db, role_id)
        if not role or role.is_system_role:
            return False
        
        await db.delete(role)
        await db.commit()
        return True
    
    @staticmethod
    async def assign_permissions_to_role(
        db: AsyncSession, 
        role_id: int, 
        permission_ids: List[int]
    ) -> None:
        """Assign permissions to role"""
        # Clear existing permissions
        await db.execute(
            role_permissions.delete().where(role_permissions.c.role_id == role_id)
        )
        
        # Add new permissions
        if permission_ids:
            values = [
                {"role_id": role_id, "permission_id": perm_id} 
                for perm_id in permission_ids
            ]
            await db.execute(role_permissions.insert(), values)
        
        await db.commit()
    
    @staticmethod
    async def assign_roles_to_user(
        db: AsyncSession, 
        user_id: int, 
        role_ids: List[int]
    ) -> None:
        """Assign roles to user"""
        # Clear existing roles
        await db.execute(
            user_roles.delete().where(user_roles.c.user_id == user_id)
        )
        
        # Add new roles
        if role_ids:
            values = [
                {"user_id": user_id, "role_id": role_id} 
                for role_id in role_ids
            ]
            await db.execute(user_roles.insert(), values)
        
        await db.commit()
    
    @staticmethod
    async def get_user_roles(db: AsyncSession, user_id: int) -> List[Role]:
        """Get user's roles"""
        result = await db.execute(
            select(Role)
            .join(user_roles)
            .where(user_roles.c.user_id == user_id)
        )
        return result.scalars().all()
    
    @staticmethod
    async def get_user_permissions(db: AsyncSession, user_id: int) -> Set[str]:
        """Get user's permissions"""
        # Get user's roles and their permissions
        result = await db.execute(
            select(Permission.name)
            .join(role_permissions)
            .join(Role)
            .join(user_roles)
            .where(user_roles.c.user_id == user_id)
        )
        
        permissions = set(result.scalars().all())
        
        # Add superuser permissions
        user_result = await db.execute(select(User).where(User.id == user_id))
        user = user_result.scalar_one_or_none()
        
        if user and user.is_superuser:
            permissions.update([perm.value for perm in PermissionType])
        
        return permissions
    
    @staticmethod
    async def user_has_permission(
        db: AsyncSession, 
        user_id: int, 
        permission: str,
        resource_id: Optional[int] = None
    ) -> bool:
        """Check if user has specific permission"""
        user_permissions = await RBACService.get_user_permissions(db, user_id)
        
        # Check direct permission
        if permission in user_permissions:
            return True
        
        # For resource-specific checks, we might need additional logic
        # For now, we'll keep it simple
        return False
    
    @staticmethod
    async def initialize_default_permissions(db: AsyncSession) -> None:
        """Initialize default permissions"""
        for perm_type in PermissionType:
            existing = await RBACService.get_permission_by_name(db, perm_type.value)
            if not existing:
                # Parse permission name to get resource and action
                resource, action = perm_type.value.split(":", 1)
                
                permission_create = PermissionCreate(
                    name=perm_type.value,
                    description=f"{action.title()} {resource.replace('_', ' ').title()}",
                    resource=resource,
                    action=action
                )
                await RBACService.create_permission(db, permission_create)
    
    @staticmethod
    async def initialize_default_roles(db: AsyncSession) -> None:
        """Initialize default roles"""
        await RBACService.initialize_default_permissions(db)
        
        for role_key, role_data in DEFAULT_ROLES.items():
            existing_role = await RBACService.get_role_by_name(db, role_key.value)
            if not existing_role:
                # Get permission IDs
                permission_ids = []
                for perm_name in role_data["permissions"]:
                    permission = await RBACService.get_permission_by_name(db, perm_name)
                    if permission:
                        permission_ids.append(permission.id)
                
                role_create = RoleCreate(
                    name=role_key.value,
                    description=role_data["description"],
                    is_system_role=role_data["is_system_role"],
                    permission_ids=permission_ids
                )
                await RBACService.create_role(db, role_create)
    
    @staticmethod
    async def assign_default_role_to_user(
        db: AsyncSession, 
        user: User, 
        role_name: str = DefaultRole.RESEARCHER
    ) -> None:
        """Assign default role to user"""
        role = await RBACService.get_role_by_name(db, role_name)
        if role:
            await RBACService.assign_roles_to_user(db, user.id, [role.id])
    
    @staticmethod
    async def get_role_permissions(db: AsyncSession, role_id: int) -> List[Permission]:
        """Get permissions for a role"""
        result = await db.execute(
            select(Permission)
            .join(role_permissions)
            .where(role_permissions.c.role_id == role_id)
        )
        return result.scalars().all()