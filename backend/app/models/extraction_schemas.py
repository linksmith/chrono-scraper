"""
Advanced content extraction schemas for structured data extraction
"""
from datetime import datetime
from typing import Optional, List, Dict, Any, TYPE_CHECKING
from sqlmodel import SQLModel, Field, Column, String, DateTime, Boolean, Text, Integer, ForeignKey, Relationship, JSON
from sqlalchemy import func
from enum import Enum

if TYPE_CHECKING:
    from .user import User
    from .project import Page


class SchemaType(str, Enum):
    """Content extraction schema types"""
    ARTICLE = "article"
    PRODUCT = "product"
    EVENT = "event"
    PERSON = "person"
    ORGANIZATION = "organization"
    CONTACT = "contact"
    REVIEW = "review"
    FAQ = "faq"
    JOB_POSTING = "job_posting"
    RECIPE = "recipe"
    NEWS = "news"
    RESEARCH_PAPER = "research_paper"
    SOCIAL_POST = "social_post"
    LEGAL_DOCUMENT = "legal_document"
    FINANCIAL_REPORT = "financial_report"
    CUSTOM = "custom"


class ExtractionStatus(str, Enum):
    """Extraction status enumeration"""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    VALIDATED = "validated"
    DISPUTED = "disputed"


class ExtractionMethod(str, Enum):
    """Content extraction methods"""
    RULE_BASED = "rule_based"
    ML_MODEL = "ml_model"
    LLM_EXTRACT = "llm_extract"
    HYBRID = "hybrid"
    MANUAL = "manual"


class ContentExtractionSchemaBase(SQLModel):
    """Base content extraction schema model"""
    name: str = Field(sa_column=Column(String(200)))
    description: Optional[str] = Field(default=None, sa_column=Column(Text))
    schema_type: SchemaType = Field(sa_column=Column(String(50)))
    
    # Schema definition (JSON schema for validation)
    field_definitions: Dict[str, Any] = Field(default={}, sa_column=Column(JSON))
    
    # Extraction configuration
    extraction_method: ExtractionMethod = Field(default=ExtractionMethod.HYBRID, sa_column=Column(String(50)))
    extraction_rules: Dict[str, Any] = Field(default={}, sa_column=Column(JSON))
    
    # CSS/XPath selectors for rule-based extraction
    css_selectors: Dict[str, str] = Field(default={}, sa_column=Column(JSON))
    xpath_selectors: Dict[str, str] = Field(default={}, sa_column=Column(JSON))
    
    # LLM prompt templates
    llm_prompt_template: Optional[str] = Field(default=None, sa_column=Column(Text))
    llm_model: Optional[str] = Field(default=None, sa_column=Column(String(100)))
    
    # Validation rules
    validation_rules: Dict[str, Any] = Field(default={}, sa_column=Column(JSON))
    confidence_threshold: float = Field(default=0.7, ge=0.0, le=1.0)
    
    # Schema settings
    is_active: bool = Field(default=True)
    is_public: bool = Field(default=False)
    
    # Usage statistics
    usage_count: int = Field(default=0)
    success_rate: float = Field(default=0.0, ge=0.0, le=1.0)
    avg_confidence: float = Field(default=0.0, ge=0.0, le=1.0)


class ContentExtractionSchema(ContentExtractionSchemaBase, table=True):
    """Content extraction schema model for database"""
    __tablename__ = "content_extraction_schemas"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id")
    
    # Version control
    version: int = Field(default=1)
    parent_schema_id: Optional[int] = Field(default=None, foreign_key="content_extraction_schemas.id")
    
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
    
    # Relationships
    user: "User" = Relationship(back_populates="extraction_schemas")
    extractions: List["ContentExtraction"] = Relationship(back_populates="schema")
    child_schemas: List["ContentExtractionSchema"] = Relationship(
        back_populates="parent_schema",
        sa_relationship_kwargs={"foreign_keys": "[ContentExtractionSchema.parent_schema_id]"}
    )
    parent_schema: Optional["ContentExtractionSchema"] = Relationship(
        back_populates="child_schemas",
        sa_relationship_kwargs={"remote_side": "[ContentExtractionSchema.id]"}
    )


class ContentExtractionBase(SQLModel):
    """Base content extraction model"""
    model_config = {"protected_namespaces": ()}
    
    extracted_data: Dict[str, Any] = Field(default={}, sa_column=Column(JSON))
    extraction_metadata: Dict[str, Any] = Field(default={}, sa_column=Column(JSON))
    
    # Quality metrics
    confidence_score: float = Field(default=0.0, ge=0.0, le=1.0)
    completeness_score: float = Field(default=0.0, ge=0.0, le=1.0)
    validation_score: float = Field(default=0.0, ge=0.0, le=1.0)
    
    # Processing information
    extraction_time_ms: Optional[int] = Field(default=None)
    tokens_used: Optional[int] = Field(default=None)
    model_version: Optional[str] = Field(default=None, sa_column=Column(String(100)))
    
    # Quality flags
    requires_review: bool = Field(default=False)
    is_validated: bool = Field(default=False)
    validation_notes: Optional[str] = Field(default=None, sa_column=Column(Text))


class ContentExtraction(ContentExtractionBase, table=True):
    """Content extraction result model for database"""
    __tablename__ = "content_extractions"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    page_id: int = Field(foreign_key="pages.id")
    schema_id: int = Field(foreign_key="content_extraction_schemas.id")
    user_id: int = Field(foreign_key="users.id")
    
    status: ExtractionStatus = Field(default=ExtractionStatus.PENDING, sa_column=Column(String(50)))
    extraction_method: ExtractionMethod = Field(sa_column=Column(String(50)))
    
    # Error tracking
    error_message: Optional[str] = Field(default=None, sa_column=Column(Text))
    retry_count: int = Field(default=0)
    
    # Validation tracking
    validated_by_user_id: Optional[int] = Field(default=None, foreign_key="users.id")
    validated_at: Optional[datetime] = Field(default=None, sa_column=Column(DateTime(timezone=True)))
    
    # Timestamps
    extracted_at: datetime = Field(
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
    
    # Relationships
    page: "Page" = Relationship(back_populates="content_extractions")
    schema: ContentExtractionSchema = Relationship(back_populates="extractions")
    user: "User" = Relationship(
        back_populates="content_extractions",
        sa_relationship_kwargs={"foreign_keys": "[ContentExtraction.user_id]"}
    )
    validated_by: Optional["User"] = Relationship(
        sa_relationship_kwargs={"foreign_keys": "[ContentExtraction.validated_by_user_id]"}
    )


class ExtractionTemplateBase(SQLModel):
    """Base extraction template model"""
    name: str = Field(sa_column=Column(String(200)))
    description: Optional[str] = Field(default=None, sa_column=Column(Text))
    category: str = Field(sa_column=Column(String(100)))
    
    # Template configuration
    template_config: Dict[str, Any] = Field(default={}, sa_column=Column(JSON))
    example_data: Dict[str, Any] = Field(default={}, sa_column=Column(JSON))
    
    # Usage information
    use_cases: List[str] = Field(default=[], sa_column=Column(JSON))
    supported_domains: List[str] = Field(default=[], sa_column=Column(JSON))
    
    # Template metadata
    is_public: bool = Field(default=True)
    is_featured: bool = Field(default=False)
    download_count: int = Field(default=0)
    rating: float = Field(default=0.0, ge=0.0, le=5.0)


class ExtractionTemplate(ExtractionTemplateBase, table=True):
    """Extraction template model for reusable schemas"""
    __tablename__ = "extraction_templates"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    created_by_user_id: int = Field(foreign_key="users.id")
    
    # Schema reference
    schema_id: Optional[int] = Field(default=None, foreign_key="content_extraction_schemas.id")
    
    # Tags for categorization
    tags: List[str] = Field(default=[], sa_column=Column(JSON))
    
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
    
    # Relationships
    created_by: "User" = Relationship(back_populates="extraction_templates")
    schema: Optional[ContentExtractionSchema] = Relationship()


class ExtractionJobBase(SQLModel):
    """Base extraction job model for batch processing"""
    name: str = Field(sa_column=Column(String(200)))
    description: Optional[str] = Field(default=None, sa_column=Column(Text))
    
    # Job configuration
    page_filters: Dict[str, Any] = Field(default={}, sa_column=Column(JSON))
    batch_size: int = Field(default=10, gt=0, le=1000)
    max_retries: int = Field(default=3, ge=0, le=10)
    
    # Progress tracking
    total_pages: int = Field(default=0)
    processed_pages: int = Field(default=0)
    successful_extractions: int = Field(default=0)
    failed_extractions: int = Field(default=0)
    
    # Job status
    is_active: bool = Field(default=True)
    auto_validate: bool = Field(default=False)


class ExtractionJob(ExtractionJobBase, table=True):
    """Extraction job model for batch content extraction"""
    __tablename__ = "extraction_jobs"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id")
    schema_id: int = Field(foreign_key="content_extraction_schemas.id")
    
    status: ExtractionStatus = Field(default=ExtractionStatus.PENDING, sa_column=Column(String(50)))
    
    # Timing
    started_at: Optional[datetime] = Field(default=None, sa_column=Column(DateTime(timezone=True)))
    completed_at: Optional[datetime] = Field(default=None, sa_column=Column(DateTime(timezone=True)))
    estimated_completion: Optional[datetime] = Field(default=None, sa_column=Column(DateTime(timezone=True)))
    
    # Error tracking
    error_message: Optional[str] = Field(default=None, sa_column=Column(Text))
    
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
    
    # Relationships
    user: "User" = Relationship(back_populates="extraction_jobs")
    schema: ContentExtractionSchema = Relationship()


# Pydantic schemas for API
class ContentExtractionSchemaCreate(ContentExtractionSchemaBase):
    """Schema for creating content extraction schemas"""
    pass


class ContentExtractionSchemaUpdate(SQLModel):
    """Schema for updating content extraction schemas"""
    name: Optional[str] = None
    description: Optional[str] = None
    field_definitions: Optional[Dict[str, Any]] = None
    extraction_method: Optional[ExtractionMethod] = None
    extraction_rules: Optional[Dict[str, Any]] = None
    css_selectors: Optional[Dict[str, str]] = None
    xpath_selectors: Optional[Dict[str, str]] = None
    llm_prompt_template: Optional[str] = None
    llm_model: Optional[str] = None
    validation_rules: Optional[Dict[str, Any]] = None
    confidence_threshold: Optional[float] = None
    is_active: Optional[bool] = None
    is_public: Optional[bool] = None


class ContentExtractionSchemaRead(ContentExtractionSchemaBase):
    """Schema for reading content extraction schemas"""
    id: int
    user_id: int
    version: int
    created_at: datetime
    updated_at: datetime


class ContentExtractionCreate(ContentExtractionBase):
    """Schema for creating content extractions"""
    page_id: int
    schema_id: int
    extraction_method: ExtractionMethod


class ContentExtractionRead(ContentExtractionBase):
    """Schema for reading content extractions"""
    id: int
    page_id: int
    schema_id: int
    user_id: int
    status: ExtractionStatus
    extraction_method: ExtractionMethod
    extracted_at: datetime
    updated_at: datetime


class ExtractionTemplateCreate(ExtractionTemplateBase):
    """Schema for creating extraction templates"""
    pass


class ExtractionTemplateRead(ExtractionTemplateBase):
    """Schema for reading extraction templates"""
    id: int
    created_by_user_id: int
    schema_id: Optional[int]
    tags: List[str]
    created_at: datetime
    updated_at: datetime


class ExtractionJobCreate(ExtractionJobBase):
    """Schema for creating extraction jobs"""
    schema_id: int


class ExtractionJobRead(ExtractionJobBase):
    """Schema for reading extraction jobs"""
    id: int
    user_id: int
    schema_id: int
    status: ExtractionStatus
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime