"""
Role-Based Access Control (RBAC) models
"""
from datetime import datetime
from typing import Optional, List
from sqlmodel import SQLModel, Field, Column, String, DateTime, ForeignKey
from sqlalchemy import func, Table, Integer
from enum import Enum


class PermissionType(str, Enum):
    """Permission types"""
    # User management
    USER_CREATE = "user:create"
    USER_READ = "user:read"
    USER_UPDATE = "user:update"
    USER_DELETE = "user:delete"
    USER_APPROVE = "user:approve"
    
    # Project management
    PROJECT_CREATE = "project:create"
    PROJECT_READ = "project:read"
    PROJECT_UPDATE = "project:update"
    PROJECT_DELETE = "project:delete"
    PROJECT_MANAGE = "project:manage"
    
    # Domain management
    DOMAIN_CREATE = "domain:create"
    DOMAIN_READ = "domain:read"
    DOMAIN_UPDATE = "domain:update"
    DOMAIN_DELETE = "domain:delete"
    
    # Scraping operations
    SCRAPE_START = "scrape:start"
    SCRAPE_STOP = "scrape:stop"
    SCRAPE_VIEW = "scrape:view"
    
    # API configuration
    API_CONFIG_CREATE = "api_config:create"
    API_CONFIG_READ = "api_config:read"
    API_CONFIG_UPDATE = "api_config:update"
    API_CONFIG_DELETE = "api_config:delete"
    
    # API keys
    API_KEY_CREATE = "api_key:create"
    API_KEY_READ = "api_key:read"
    API_KEY_DELETE = "api_key:delete"
    
    # System administration
    ADMIN_VIEW = "admin:view"
    ADMIN_MANAGE = "admin:manage"
    ADMIN_USERS = "admin:users"


class DefaultRole(str, Enum):
    """Default system roles"""
    SUPER_ADMIN = "super_admin"
    ADMIN = "admin"
    RESEARCHER = "researcher"
    VIEWER = "viewer"


# Association table for many-to-many relationship between roles and permissions
role_permissions = Table(
    "role_permissions",
    SQLModel.metadata,
    Column("role_id", Integer, ForeignKey("roles.id"), primary_key=True),
    Column("permission_id", Integer, ForeignKey("permissions.id"), primary_key=True),
)

# Association table for many-to-many relationship between users and roles
user_roles = Table(
    "user_roles",
    SQLModel.metadata,
    Column("user_id", Integer, ForeignKey("users.id"), primary_key=True),
    Column("role_id", Integer, ForeignKey("roles.id"), primary_key=True),
)


class PermissionBase(SQLModel):
    """Base permission model"""
    name: str = Field(sa_column=Column(String(100), unique=True, index=True))
    description: Optional[str] = Field(default=None, sa_column=Column(String(500)))
    resource: str = Field(sa_column=Column(String(50)))  # user, project, domain, etc.
    action: str = Field(sa_column=Column(String(50)))    # create, read, update, delete, etc.


class Permission(PermissionBase, table=True):
    """Permission model for database"""
    __tablename__ = "permissions"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    
    # Timestamps
    created_at: datetime = Field(
        default_factory=datetime.utcnow,
        sa_column=Column(DateTime(timezone=True), server_default=func.now())
    )


class RoleBase(SQLModel):
    """Base role model"""
    name: str = Field(sa_column=Column(String(100), unique=True, index=True))
    description: Optional[str] = Field(default=None, sa_column=Column(String(500)))
    is_system_role: bool = Field(default=False)  # System roles cannot be deleted


class Role(RoleBase, table=True):
    """Role model for database"""
    __tablename__ = "roles"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    
    # Timestamps
    created_at: datetime = Field(
        default_factory=datetime.utcnow,
        sa_column=Column(DateTime(timezone=True), server_default=func.now())
    )
    updated_at: datetime = Field(
        default_factory=datetime.utcnow,
        sa_column=Column(
            DateTime(timezone=True),
            server_default=func.now(),
            onupdate=func.now()
        )
    )


# Pydantic schemas for API
class PermissionCreate(PermissionBase):
    """Schema for creating permissions"""
    pass


class PermissionRead(PermissionBase):
    """Schema for reading permissions"""
    id: int
    created_at: datetime


class RoleCreate(RoleBase):
    """Schema for creating roles"""
    permission_ids: Optional[List[int]] = []


class RoleUpdate(SQLModel):
    """Schema for updating roles"""
    name: Optional[str] = None
    description: Optional[str] = None
    permission_ids: Optional[List[int]] = None


class RoleRead(RoleBase):
    """Schema for reading roles"""
    id: int
    created_at: datetime
    updated_at: datetime


class RoleReadWithPermissions(RoleRead):
    """Role schema with permissions"""
    permissions: List[PermissionRead] = []


class UserRoleAssignment(SQLModel):
    """Schema for assigning roles to users"""
    user_id: int
    role_ids: List[int]


class UserPermissionCheck(SQLModel):
    """Schema for checking user permissions"""
    user_id: int
    permission: str
    resource_id: Optional[int] = None  # For resource-specific permissions


# Default role definitions
DEFAULT_ROLES = {
    DefaultRole.SUPER_ADMIN: {
        "name": "Super Administrator",
        "description": "Full system access with all permissions",
        "permissions": [perm.value for perm in PermissionType],
        "is_system_role": True
    },
    DefaultRole.ADMIN: {
        "name": "Administrator", 
        "description": "Administrative access with user and project management",
        "permissions": [
            PermissionType.USER_READ,
            PermissionType.USER_UPDATE,
            PermissionType.USER_APPROVE,
            PermissionType.PROJECT_CREATE,
            PermissionType.PROJECT_READ,
            PermissionType.PROJECT_UPDATE,
            PermissionType.PROJECT_DELETE,
            PermissionType.PROJECT_MANAGE,
            PermissionType.DOMAIN_CREATE,
            PermissionType.DOMAIN_READ,
            PermissionType.DOMAIN_UPDATE,
            PermissionType.DOMAIN_DELETE,
            PermissionType.SCRAPE_START,
            PermissionType.SCRAPE_STOP,
            PermissionType.SCRAPE_VIEW,
            PermissionType.API_CONFIG_READ,
            PermissionType.API_KEY_CREATE,
            PermissionType.API_KEY_READ,
            PermissionType.API_KEY_DELETE,
            PermissionType.ADMIN_VIEW,
            PermissionType.ADMIN_USERS,
        ],
        "is_system_role": True
    },
    DefaultRole.RESEARCHER: {
        "name": "Researcher",
        "description": "Research access with project creation and management",
        "permissions": [
            PermissionType.USER_READ,  # Own profile only
            PermissionType.PROJECT_CREATE,
            PermissionType.PROJECT_READ,
            PermissionType.PROJECT_UPDATE,
            PermissionType.PROJECT_DELETE,
            PermissionType.DOMAIN_CREATE,
            PermissionType.DOMAIN_READ,
            PermissionType.DOMAIN_UPDATE,
            PermissionType.DOMAIN_DELETE,
            PermissionType.SCRAPE_START,
            PermissionType.SCRAPE_STOP,
            PermissionType.SCRAPE_VIEW,
            PermissionType.API_CONFIG_READ,
            PermissionType.API_KEY_CREATE,
            PermissionType.API_KEY_READ,
            PermissionType.API_KEY_DELETE,
        ],
        "is_system_role": True
    },
    DefaultRole.VIEWER: {
        "name": "Viewer",
        "description": "Read-only access to projects and data",
        "permissions": [
            PermissionType.USER_READ,  # Own profile only
            PermissionType.PROJECT_READ,
            PermissionType.DOMAIN_READ,
            PermissionType.SCRAPE_VIEW,
            PermissionType.API_CONFIG_READ,
            PermissionType.API_KEY_READ,
        ],
        "is_system_role": True
    }
}