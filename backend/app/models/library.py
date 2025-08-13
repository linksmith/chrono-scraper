"""
User library models for saved searches, starred items, and search history
"""
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum
from sqlmodel import Field, SQLModel, Relationship, Column, JSON
from sqlalchemy import UniqueConstraint, Index, Text


class ItemType(str, Enum):
    """Types of items that can be starred"""
    PAGE = "page"
    ENTITY = "entity"
    DOCUMENT = "document"
    PROJECT = "project"
    SEARCH = "search"


class AlertFrequency(str, Enum):
    """Frequency for saved search alerts"""
    REALTIME = "realtime"
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    NEVER = "never"


class StarredItem(SQLModel, table=True):
    """User-starred pages, entities, and other content"""
    __tablename__ = "starred_items"
    __table_args__ = (
        UniqueConstraint("user_id", "item_type", "item_id"),
        Index("idx_starred_user_type", "user_id", "item_type"),
    )
    
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    
    # Item identification
    item_type: ItemType
    item_id: int  # Generic ID that references different tables based on item_type
    
    # Optional direct references for performance
    page_id: Optional[int] = Field(default=None, foreign_key="pages.id")
    project_id: Optional[int] = Field(default=None, foreign_key="projects.id")
    
    # User annotations
    personal_note: str = Field(default="", sa_column=Column(Text))
    tags: List[str] = Field(default=[], sa_column=Column(JSON))
    color_label: Optional[str] = Field(default=None)  # For visual organization
    
    # Organization
    folder: Optional[str] = Field(default=None)
    is_pinned: bool = Field(default=False)
    sort_order: int = Field(default=0)
    
    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    last_accessed_at: Optional[datetime] = None
    
    # Relationships
    user: Optional["User"] = Relationship(back_populates="starred_items")
    page: Optional["Page"] = Relationship(back_populates="starred_by")
    project: Optional["Project"] = Relationship(back_populates="starred_by")
    # Note: entity relationship handled polymorphically via item_id + item_type
    
    def record_access(self):
        """Record that this starred item was accessed"""
        self.last_accessed_at = datetime.utcnow()
        self.updated_at = datetime.utcnow()


class SavedSearch(SQLModel, table=True):
    """Saved search queries with filters and alerts"""
    __tablename__ = "saved_searches"
    __table_args__ = (
        Index("idx_saved_search_user_folder", "user_id", "folder"),
        Index("idx_saved_search_alerts", "enable_alerts", "alert_frequency"),
    )
    
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    
    # Search configuration
    name: str = Field(index=True)
    description: str = Field(default="", sa_column=Column(Text))
    query_text: str = Field(sa_column=Column(Text))
    filters: Dict[str, Any] = Field(default={}, sa_column=Column(JSON))
    sort_options: Dict[str, Any] = Field(default={}, sa_column=Column(JSON))
    
    # Search scope
    project_ids: List[int] = Field(default=[], sa_column=Column(JSON))
    include_archived: bool = Field(default=False)
    search_type: str = Field(default="content")  # content, semantic, entity, etc.
    
    # Organization
    folder: str = Field(default="", index=True)
    tags: List[str] = Field(default=[], sa_column=Column(JSON))
    is_pinned: bool = Field(default=False)
    icon: Optional[str] = Field(default=None)
    color: Optional[str] = Field(default=None)
    
    # Alerts and notifications
    enable_alerts: bool = Field(default=False)
    alert_frequency: AlertFrequency = Field(default=AlertFrequency.DAILY)
    alert_email: Optional[str] = Field(default=None)
    last_alert_sent: Optional[datetime] = None
    alert_threshold: Optional[int] = Field(default=None)  # Min new results to trigger alert
    
    # Usage tracking
    last_result_count: int = Field(default=0)
    last_executed: Optional[datetime] = None
    execution_count: int = Field(default=0)
    average_result_count: float = Field(default=0.0)
    
    # Sharing
    is_public: bool = Field(default=False)
    shared_with_users: List[int] = Field(default=[], sa_column=Column(JSON))
    share_token: Optional[str] = Field(default=None, unique=True)
    
    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    # Relationships
    user: Optional["User"] = Relationship(back_populates="saved_searches")
    history_entries: List["SearchHistory"] = Relationship(back_populates="saved_search")
    
    def record_execution(self, result_count: int):
        """Record that this saved search was executed"""
        self.execution_count += 1
        self.last_executed = datetime.utcnow()
        self.last_result_count = result_count
        
        # Update rolling average
        if self.execution_count == 1:
            self.average_result_count = result_count
        else:
            self.average_result_count = (
                (self.average_result_count * (self.execution_count - 1) + result_count) 
                / self.execution_count
            )
    
    def should_send_alert(self) -> bool:
        """Check if an alert should be sent based on frequency"""
        if not self.enable_alerts or self.alert_frequency == AlertFrequency.NEVER:
            return False
        
        if not self.last_alert_sent:
            return True
        
        now = datetime.utcnow()
        time_since_last = now - self.last_alert_sent
        
        if self.alert_frequency == AlertFrequency.REALTIME:
            return True
        elif self.alert_frequency == AlertFrequency.DAILY:
            return time_since_last.days >= 1
        elif self.alert_frequency == AlertFrequency.WEEKLY:
            return time_since_last.days >= 7
        elif self.alert_frequency == AlertFrequency.MONTHLY:
            return time_since_last.days >= 30
        
        return False


class SearchHistory(SQLModel, table=True):
    """Track user search history for analytics and suggestions"""
    __tablename__ = "search_history"
    __table_args__ = (
        Index("idx_search_history_user_date", "user_id", "created_at"),
        Index("idx_search_history_project", "project_id", "created_at"),
    )
    
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    
    # Search context
    project_id: Optional[int] = Field(default=None, foreign_key="projects.id")
    saved_search_id: Optional[int] = Field(default=None, foreign_key="saved_searches.id")
    
    # Search details
    query_text: str = Field(sa_column=Column(Text))
    filters: Dict[str, Any] = Field(default={}, sa_column=Column(JSON))
    search_type: str = Field(default="content")
    
    # Results
    result_count: int = Field(default=0)
    top_results: List[Dict[str, Any]] = Field(default=[], sa_column=Column(JSON))
    execution_time_ms: Optional[int] = Field(default=None)
    
    # User interaction
    clicked_results: List[int] = Field(default=[], sa_column=Column(JSON))
    time_to_first_click_ms: Optional[int] = Field(default=None)
    session_id: Optional[str] = Field(default=None, index=True)
    
    # Timestamp
    created_at: datetime = Field(default_factory=datetime.utcnow, index=True)
    
    # Relationships
    user: Optional["User"] = Relationship(back_populates="search_history")
    project: Optional["Project"] = Relationship(back_populates="search_history")
    saved_search: Optional["SavedSearch"] = Relationship(back_populates="history_entries")


class SearchSuggestion(SQLModel, table=True):
    """Pre-computed search suggestions based on user behavior"""
    __tablename__ = "search_suggestions"
    __table_args__ = (
        UniqueConstraint("user_id", "suggestion_text"),
        Index("idx_search_suggestion_score", "user_id", "score"),
    )
    
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    
    # Suggestion details
    suggestion_text: str
    suggestion_type: str  # query, filter, entity, topic
    display_text: str  # Formatted for display
    
    # Scoring and ranking
    score: float = Field(default=0.0, index=True)
    frequency: int = Field(default=1)
    last_used: Optional[datetime] = None
    
    # Context
    related_projects: List[int] = Field(default=[], sa_column=Column(JSON))
    related_entities: List[str] = Field(default=[], sa_column=Column(JSON))
    
    # Metadata
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    # Relationships
    user: Optional["User"] = Relationship(back_populates="search_suggestions")


class UserCollection(SQLModel, table=True):
    """User-created collections for organizing content"""
    __tablename__ = "user_collections"
    __table_args__ = (
        UniqueConstraint("user_id", "name"),
        Index("idx_user_collection_type", "user_id", "collection_type"),
    )
    
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    
    # Collection details
    name: str
    description: str = Field(default="", sa_column=Column(Text))
    collection_type: str = Field(default="general")  # general, research, investigation, archive
    
    # Visual customization
    icon: Optional[str] = Field(default=None)
    color: Optional[str] = Field(default=None)
    cover_image: Optional[str] = Field(default=None)
    
    # Content
    item_count: int = Field(default=0)
    items: Dict[str, List[int]] = Field(default={}, sa_column=Column(JSON))  # {item_type: [ids]}
    
    # Organization
    parent_collection_id: Optional[int] = Field(default=None, foreign_key="user_collections.id")
    sort_order: int = Field(default=0)
    tags: List[str] = Field(default=[], sa_column=Column(JSON))
    
    # Sharing
    is_public: bool = Field(default=False)
    shared_with_users: List[int] = Field(default=[], sa_column=Column(JSON))
    share_token: Optional[str] = Field(default=None, unique=True)
    
    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    last_accessed: Optional[datetime] = None
    
    # Relationships
    user: Optional["User"] = Relationship(back_populates="collections")
    parent_collection: Optional["UserCollection"] = Relationship(
        back_populates="sub_collections",
        sa_relationship_kwargs={"remote_side": "UserCollection.id"}
    )
    sub_collections: List["UserCollection"] = Relationship(back_populates="parent_collection")