"""
User approval system models
"""
from datetime import datetime
from typing import Optional
from sqlmodel import SQLModel, Field, Column, DateTime, Text, Boolean, Integer
from sqlalchemy import func
from enum import Enum


class ApprovalStatus(str, Enum):
    """User approval status enumeration"""
    PENDING = "pending"
    APPROVED = "approved"
    DENIED = "denied"
    UNDER_REVIEW = "under_review"


class EvaluationProvider(str, Enum):
    """LLM provider for user evaluation"""
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    OPENROUTER = "openrouter"


class ApprovalTokenAction(str, Enum):
    """Actions that can be performed with approval tokens"""
    APPROVE = "approve"
    DENY = "deny"
    REQUEST_INFO = "request_info"


class UserApprovalMessageBase(SQLModel):
    """Base model for user approval messages"""
    user_id: int = Field(foreign_key="user.id", index=True)
    message: str = Field(sa_column=Column(Text))
    is_admin_message: bool = Field(default=True)
    is_read: bool = Field(default=False)


class UserApprovalMessage(UserApprovalMessageBase, table=True):
    """Messages sent to users during approval process"""
    __tablename__ = "user_approval_messages"
    
    id: Optional[int] = Field(default=None, primary_key=True)
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


class LLMConfigurationBase(SQLModel):
    """Base model for LLM configuration"""
    model_config = {"protected_namespaces": ()}
    
    provider: EvaluationProvider
    model_name: str
    api_key: Optional[str] = Field(default=None)
    base_url: Optional[str] = Field(default=None)
    is_active: bool = Field(default=True)
    max_tokens: int = Field(default=1000)
    temperature: float = Field(default=0.1)
    evaluation_prompt: str = Field(sa_column=Column(Text))


class LLMConfiguration(LLMConfigurationBase, table=True):
    """LLM configuration for user evaluation"""
    __tablename__ = "llm_configurations"
    
    id: Optional[int] = Field(default=None, primary_key=True)
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


class LLMEvaluationLogBase(SQLModel):
    """Base model for LLM evaluation logs"""
    user_id: int = Field(foreign_key="user.id", index=True)
    llm_configuration_id: int = Field(foreign_key="llm_configurations.id")
    evaluation_input: str = Field(sa_column=Column(Text))
    evaluation_output: str = Field(sa_column=Column(Text))
    confidence_score: Optional[float] = Field(default=None)
    recommended_action: Optional[str] = Field(default=None)
    processing_time_ms: Optional[int] = Field(default=None)
    error_message: Optional[str] = Field(default=None)
    success: bool = Field(default=True)


class LLMEvaluationLog(LLMEvaluationLogBase, table=True):
    """Log of LLM evaluations for user registrations"""
    __tablename__ = "llm_evaluation_logs"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    created_at: datetime = Field(
        default_factory=datetime.utcnow,
        sa_column=Column(DateTime(timezone=True), server_default=func.now())
    )


class UserEvaluationBase(SQLModel):
    """Base model for user evaluations"""
    user_id: int = Field(foreign_key="user.id", index=True, unique=True)
    overall_score: Optional[float] = Field(default=None)
    legitimacy_score: Optional[float] = Field(default=None)
    research_intent_score: Optional[float] = Field(default=None)
    risk_score: Optional[float] = Field(default=None)
    recommendation: Optional[str] = Field(default=None)
    reasoning: Optional[str] = Field(sa_column=Column(Text))
    confidence: Optional[float] = Field(default=None)
    red_flags: Optional[str] = Field(sa_column=Column(Text))
    positive_indicators: Optional[str] = Field(sa_column=Column(Text))
    additional_checks_needed: bool = Field(default=False)
    manual_review_required: bool = Field(default=False)


class UserEvaluation(UserEvaluationBase, table=True):
    """LLM-based evaluation of user registrations"""
    __tablename__ = "user_evaluations"
    
    id: Optional[int] = Field(default=None, primary_key=True)
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


class ApprovalTokenBase(SQLModel):
    """Base model for approval tokens"""
    user_id: int = Field(foreign_key="user.id", index=True)
    token: str = Field(unique=True, index=True)
    action: ApprovalTokenAction
    expires_at: datetime
    is_used: bool = Field(default=False)
    admin_message: Optional[str] = Field(sa_column=Column(Text))


class ApprovalToken(ApprovalTokenBase, table=True):
    """Secure one-click approval/denial tokens for admin use"""
    __tablename__ = "approval_tokens"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    created_at: datetime = Field(
        default_factory=datetime.utcnow,
        sa_column=Column(DateTime(timezone=True), server_default=func.now())
    )
    used_at: Optional[datetime] = Field(default=None)
    admin_ip: Optional[str] = Field(default=None)
    admin_user_agent: Optional[str] = Field(default=None)


# Pydantic schemas for API
class UserApprovalMessageCreate(SQLModel):
    """Schema for creating user approval messages"""
    user_id: int
    message: str
    is_admin_message: bool = True


class UserApprovalMessageRead(UserApprovalMessageBase):
    """Schema for reading user approval messages"""
    id: int
    created_at: datetime
    updated_at: datetime


class LLMConfigurationCreate(SQLModel):
    """Schema for creating LLM configurations"""
    provider: EvaluationProvider
    model_name: str
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    is_active: bool = True
    max_tokens: int = 1000
    temperature: float = 0.1
    evaluation_prompt: str


class LLMConfigurationUpdate(SQLModel):
    """Schema for updating LLM configurations"""
    model_name: Optional[str] = None
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    is_active: Optional[bool] = None
    max_tokens: Optional[int] = None
    temperature: Optional[float] = None
    evaluation_prompt: Optional[str] = None


class LLMConfigurationRead(LLMConfigurationBase):
    """Schema for reading LLM configurations"""
    id: int
    created_at: datetime
    updated_at: datetime


class UserEvaluationCreate(SQLModel):
    """Schema for creating user evaluations"""
    user_id: int
    overall_score: Optional[float] = None
    legitimacy_score: Optional[float] = None
    research_intent_score: Optional[float] = None
    risk_score: Optional[float] = None
    recommendation: Optional[str] = None
    reasoning: Optional[str] = None
    confidence: Optional[float] = None
    red_flags: Optional[str] = None
    positive_indicators: Optional[str] = None
    additional_checks_needed: bool = False
    manual_review_required: bool = False


class UserEvaluationRead(UserEvaluationBase):
    """Schema for reading user evaluations"""
    id: int
    created_at: datetime
    updated_at: datetime


class ApprovalTokenCreate(SQLModel):
    """Schema for creating approval tokens"""
    user_id: int
    action: ApprovalTokenAction
    expires_at: datetime
    admin_message: Optional[str] = None


class ApprovalTokenRead(ApprovalTokenBase):
    """Schema for reading approval tokens"""
    id: int
    created_at: datetime
    used_at: Optional[datetime] = None
    admin_ip: Optional[str] = None
    admin_user_agent: Optional[str] = None


class ApprovalTokenUse(SQLModel):
    """Schema for using approval tokens"""
    token: str
    admin_ip: Optional[str] = None
    admin_user_agent: Optional[str] = None