"""
User plans and subscription management models
"""
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum
from sqlmodel import Field, SQLModel, Relationship, Column, JSON
from sqlalchemy import UniqueConstraint, Index


class PlanTier(str, Enum):
    """Available subscription tiers"""
    SPARK = "spark"  # Entry level
    FLASH = "flash"  # Standard
    LIGHTNING = "lightning"  # Professional
    UNLIMITED = "unlimited"  # Admin/Enterprise


class Plan(SQLModel, table=True):
    """Available subscription plans"""
    __tablename__ = "plans"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(unique=True, index=True)  # free, flash, blaze, lightning
    display_name: str
    price_monthly: float = Field(default=0.0)
    price_yearly: Optional[float] = None
    
    # Limits
    pages_per_month: int
    projects_limit: int
    rate_limit_per_minute: int
    concurrent_jobs: int = Field(default=1)
    
    # Features
    features: List[str] = Field(default=[], sa_column=Column(JSON))
    api_access: bool = Field(default=False)
    priority_support: bool = Field(default=False)
    custom_extraction: bool = Field(default=False)
    
    # Metadata
    is_active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class UserPlan(SQLModel, table=True):
    """User subscription plan with performance tiers"""
    __tablename__ = "user_plans"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", unique=True, index=True)
    
    # Plan configuration
    tier: PlanTier = Field(default=PlanTier.SPARK)
    
    # Performance limits
    max_pages_per_minute: int = Field(default=10)
    max_concurrent_jobs: int = Field(default=1)
    max_pages_per_session: int = Field(default=500)
    max_pages_per_day: int = Field(default=2500)
    max_projects: int = Field(default=2)
    
    # Advanced features
    priority_processing: bool = Field(default=False)
    advanced_extraction: bool = Field(default=False)
    api_access: bool = Field(default=False)
    bulk_operations: bool = Field(default=False)
    custom_timeout_limits: bool = Field(default=False)
    entity_extraction: bool = Field(default=False)
    osint_features: bool = Field(default=False)
    
    # Plan status
    is_active: bool = Field(default=True)
    started_at: datetime = Field(default_factory=datetime.utcnow)
    expires_at: Optional[datetime] = None
    
    # Metadata
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    # Relationships
    user: Optional["User"] = Relationship(back_populates="plan")
    rate_limit: Optional["UserRateLimit"] = Relationship(back_populates="plan")
    usage_records: List["UserPlanUsage"] = Relationship(back_populates="plan")
    
    @staticmethod
    def get_plan_defaults(tier: PlanTier) -> dict:
        """Get default settings for each plan tier"""
        configs = {
            PlanTier.SPARK: {
                "max_pages_per_minute": 10,
                "max_concurrent_jobs": 1,
                "max_pages_per_session": 500,
                "max_pages_per_day": 2500,
                "max_projects": 2,
                "priority_processing": False,
                "advanced_extraction": False,
                "api_access": False,
                "bulk_operations": False,
                "custom_timeout_limits": False,
                "entity_extraction": False,
                "osint_features": False,
            },
            PlanTier.FLASH: {
                "max_pages_per_minute": 25,
                "max_concurrent_jobs": 2,
                "max_pages_per_session": 2000,
                "max_pages_per_day": 10000,
                "max_projects": 5,
                "priority_processing": False,
                "advanced_extraction": True,
                "api_access": False,
                "bulk_operations": False,
                "custom_timeout_limits": False,
                "entity_extraction": True,
                "osint_features": False,
            },
            PlanTier.LIGHTNING: {
                "max_pages_per_minute": 75,
                "max_concurrent_jobs": 5,
                "max_pages_per_session": 10000,
                "max_pages_per_day": 50000,
                "max_projects": 15,
                "priority_processing": True,
                "advanced_extraction": True,
                "api_access": True,
                "bulk_operations": True,
                "custom_timeout_limits": True,
                "entity_extraction": True,
                "osint_features": True,
            },
            PlanTier.UNLIMITED: {
                "max_pages_per_minute": 200,
                "max_concurrent_jobs": 10,
                "max_pages_per_session": 100000,
                "max_pages_per_day": 1000000,
                "max_projects": 100,
                "priority_processing": True,
                "advanced_extraction": True,
                "api_access": True,
                "bulk_operations": True,
                "custom_timeout_limits": True,
                "entity_extraction": True,
                "osint_features": True,
            },
        }
        return configs.get(tier, configs[PlanTier.SPARK])
    
    def get_priority_level(self) -> int:
        """Get numeric priority level for queue processing"""
        priority_map = {
            PlanTier.SPARK: 6,  # Low priority
            PlanTier.FLASH: 4,  # Normal priority
            PlanTier.LIGHTNING: 2,  # High priority
            PlanTier.UNLIMITED: 1,  # Highest priority
        }
        return priority_map.get(self.tier, 5)
    
    def can_create_project(self, current_count: int) -> tuple[bool, str]:
        """Check if user can create another project"""
        if current_count >= self.max_projects:
            return False, f"Plan limit: {self.max_projects} projects maximum"
        return True, "Can create project"


class UserRateLimit(SQLModel, table=True):
    """User-specific rate limiting configuration"""
    __tablename__ = "user_rate_limits"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", unique=True, index=True)
    plan_id: int = Field(foreign_key="user_plans.id", unique=True)
    
    # Rate limits (synced with plan)
    max_pages_per_minute: int = Field(default=20)
    max_concurrent_jobs: int = Field(default=2)
    max_pages_per_session: int = Field(default=1000)
    max_pages_per_day: int = Field(default=10000)
    
    # Priority settings
    priority_level: int = Field(default=5)  # 1=highest, 7=lowest
    
    # Timeout settings
    default_timeout_seconds: int = Field(default=60)
    max_timeout_seconds: int = Field(default=120)
    
    # Current usage tracking
    pages_scraped_today: int = Field(default=0)
    last_reset_date: datetime = Field(default_factory=datetime.utcnow)
    current_concurrent_jobs: int = Field(default=0)
    
    # System controls
    is_active: bool = Field(default=True)
    bypass_rate_limits: bool = Field(default=False)  # Admin override
    
    # Metadata
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    # Relationships
    user: Optional["User"] = Relationship(back_populates="rate_limit")
    plan: Optional["UserPlan"] = Relationship(back_populates="rate_limit")
    
    def sync_with_plan(self, plan: UserPlan):
        """Synchronize rate limits with user's plan"""
        self.max_pages_per_minute = plan.max_pages_per_minute
        self.max_concurrent_jobs = plan.max_concurrent_jobs
        self.max_pages_per_session = plan.max_pages_per_session
        self.max_pages_per_day = plan.max_pages_per_day
        self.priority_level = plan.get_priority_level()
        
        if plan.custom_timeout_limits:
            self.default_timeout_seconds = 30
            self.max_timeout_seconds = 300
        else:
            self.default_timeout_seconds = 60
            self.max_timeout_seconds = 120
        
        self.updated_at = datetime.utcnow()
    
    def check_rate_limit(self) -> tuple[bool, str]:
        """Check if current rate limits allow new operation"""
        # Reset daily counter if needed
        today = datetime.utcnow().date()
        if self.last_reset_date.date() < today:
            self.pages_scraped_today = 0
            self.last_reset_date = datetime.utcnow()
        
        # Check daily limit
        if self.pages_scraped_today >= self.max_pages_per_day:
            return False, f"Daily limit reached: {self.max_pages_per_day} pages"
        
        # Check concurrent jobs
        if self.current_concurrent_jobs >= self.max_concurrent_jobs:
            return False, f"Concurrent job limit reached: {self.max_concurrent_jobs}"
        
        return True, "Within rate limits"


class UserPlanUsage(SQLModel, table=True):
    """Track daily usage statistics for user plans"""
    __tablename__ = "user_plan_usage"
    __table_args__ = (
        UniqueConstraint("user_id", "date"),
        Index("idx_user_plan_usage_date", "user_id", "date"),
    )
    
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id")
    plan_id: int = Field(foreign_key="user_plans.id")
    
    # Time period
    date: datetime = Field(index=True)
    
    # Usage metrics
    pages_scraped: int = Field(default=0)
    projects_created: int = Field(default=0)
    concurrent_jobs_peak: int = Field(default=0)
    api_calls: int = Field(default=0)
    searches_performed: int = Field(default=0)
    entities_extracted: int = Field(default=0)
    
    # Performance metrics
    average_pages_per_minute: float = Field(default=0.0)
    total_scrape_time_seconds: int = Field(default=0)
    
    # Quality metrics
    success_rate: float = Field(default=0.0)
    extraction_success_rate: float = Field(default=0.0)
    
    # Metadata
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
    # Relationships
    user: Optional["User"] = Relationship(back_populates="usage_records")
    plan: Optional["UserPlan"] = Relationship(back_populates="usage_records")


class PlanFeature(SQLModel, table=True):
    """Individual features available in plans"""
    __tablename__ = "plan_features"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(unique=True, index=True)
    description: str
    code_name: str = Field(unique=True, index=True)
    
    # Feature categorization
    category: str  # performance, extraction, analytics, integration, support
    
    # Availability per tier
    available_in_spark: bool = Field(default=False)
    available_in_flash: bool = Field(default=False)
    available_in_lightning: bool = Field(default=True)
    available_in_unlimited: bool = Field(default=True)
    
    # Metadata
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
    def is_available_for_tier(self, tier: PlanTier) -> bool:
        """Check if feature is available for a given tier"""
        tier_map = {
            PlanTier.SPARK: self.available_in_spark,
            PlanTier.FLASH: self.available_in_flash,
            PlanTier.LIGHTNING: self.available_in_lightning,
            PlanTier.UNLIMITED: self.available_in_unlimited,
        }
        return tier_map.get(tier, False)