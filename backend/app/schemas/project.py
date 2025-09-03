"""
Project schemas
"""
from typing import Optional
from datetime import datetime
from pydantic import BaseModel


class ProjectBase(BaseModel):
    name: str
    description: Optional[str] = None
    index_name: Optional[str] = None
    process_documents: bool = True  # Always enabled for search indexing


class ProjectCreate(ProjectBase):
    pass


class ProjectUpdate(ProjectBase):
    name: Optional[str] = None
    # process_documents is always True and cannot be changed


class ProjectInDBBase(ProjectBase):
    id: int
    user_id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class Project(ProjectInDBBase):
    pass