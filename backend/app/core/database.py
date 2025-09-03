"""
Database configuration and session management
"""
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlmodel import SQLModel

from app.core.config import settings

# Import all models to ensure they are registered with SQLModel metadata
from app.models.user import User  # noqa
from app.models.project import Project, Domain, ScrapeSession  # noqa
from app.models.api_config import APIConfig, APIKey  # noqa
from app.models.rbac import Permission, Role, role_permissions, user_roles  # noqa
from app.models.user_approval import UserApprovalMessage, LLMConfiguration, LLMEvaluationLog, UserEvaluation, ApprovalToken  # noqa
from app.models.plans import UserPlan, UserRateLimit, UserPlanUsage  # noqa
from app.models.library import StarredItem, SavedSearch, SearchHistory, SearchSuggestion, UserCollection  # noqa
from app.models.entities import CanonicalEntity, ExtractedEntity, EntityRelationship, EntityMention, EntityResolution  # noqa
from app.models.extraction_schemas import ContentExtractionSchema, ContentExtraction, ExtractionTemplate, ExtractionJob  # noqa
from app.models.investigations import Investigation, Evidence, PageComparison, InvestigationTimeline, InvestigationFinding  # noqa
from app.models.sharing import ProjectShare, PublicSearchConfig, ShareInvitation, ShareAccessLog  # noqa
from app.models.user_config import UserEntityConfig  # noqa

# Create async engine
engine = create_async_engine(
    settings.ASYNC_DATABASE_URL,
    echo=False,
    future=True,
    pool_size=20,
    max_overflow=40,
    pool_pre_ping=True,
)

# Create async session factory
AsyncSessionLocal = sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

# Create synchronous engine for Celery tasks
sync_engine = create_engine(
    settings.DATABASE_URL,  # Use sync database URL
    echo=False,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,
)

# Create synchronous session factory for Celery tasks
SyncSessionLocal = sessionmaker(
    sync_engine,
    class_=Session,
    expire_on_commit=False,
)


async def init_db() -> None:
    """
    Initialize database tables
    """
    async with engine.begin() as conn:
        # Create all SQLModel tables (including RBAC association tables)
        await conn.run_sync(SQLModel.metadata.create_all)


async def get_db() -> AsyncSession:
    """
    Dependency to get database session
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()