"""
Project schemas
"""
from typing import Optional, Dict, Any, Literal
from datetime import datetime
from pydantic import BaseModel, Field
from enum import Enum


class ArchiveSource(str, Enum):
    """Archive source enumeration - matches frontend TypeScript interface"""
    WAYBACK_MACHINE = "wayback"
    COMMON_CRAWL = "commoncrawl"  
    HYBRID = "hybrid"


class ArchiveConfig(BaseModel):
    """Archive configuration schema - matches frontend TypeScript interface"""
    fallback_strategy: Literal['sequential', 'parallel'] = Field(default='sequential')
    circuit_breaker_threshold: int = Field(default=3, ge=1, le=10)
    fallback_delay: float = Field(default=2.0, ge=0, le=30)
    recovery_time: int = Field(default=300, ge=30, le=3600)


class ProjectBase(BaseModel):
    name: str
    description: Optional[str] = None
    index_name: Optional[str] = None
    process_documents: bool = True  # Always enabled for search indexing
    
    # Archive Source Configuration - matches frontend TypeScript interface
    archive_source: ArchiveSource = Field(default=ArchiveSource.WAYBACK_MACHINE)
    fallback_enabled: bool = Field(default=True)
    archive_config: Optional[ArchiveConfig] = Field(default=None)


class ProjectCreate(ProjectBase):
    """Schema for creating projects - includes archive source configuration"""
    pass


class ProjectUpdate(ProjectBase):
    name: Optional[str] = None
    # process_documents is always True and cannot be changed
    
    # Archive Source Configuration (for updates) - all optional
    archive_source: Optional[ArchiveSource] = None
    fallback_enabled: Optional[bool] = None
    archive_config: Optional[ArchiveConfig] = None


class ProjectInDBBase(ProjectBase):
    id: int
    user_id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class Project(ProjectInDBBase):
    pass