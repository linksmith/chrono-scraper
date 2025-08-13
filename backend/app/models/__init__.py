"""Database models module"""

# Import all models for Alembic to discover them
from .user import User, UserCreate, UserUpdate, UserRead, UserReadWithStats
from .project import (
    Project,
    Domain, 
    ScrapeSession,
    Page,
    ProjectCreate,
    ProjectUpdate,
    ProjectRead,
    ProjectReadWithStats,
    DomainCreate,
    DomainUpdate,
    DomainRead,
    ProjectStatus,
    DomainStatus,
    MatchType,
    ScrapeSessionStatus
)
from .api_config import (
    APIConfig,
    APIKey,
    APIConfigCreate,
    APIConfigUpdate,
    APIConfigRead,
    APIKeyCreate,
    APIKeyRead,
    APIKeyCreateResponse,
    APIServiceType
)
from .plans import (
    UserPlan,
    UserRateLimit,
    UserPlanUsage,
    PlanFeature,
    PlanTier
)
from .library import (
    StarredItem,
    SavedSearch,
    SearchHistory,
    SearchSuggestion,
    UserCollection,
    ItemType,
    AlertFrequency
)
from .entities import (
    CanonicalEntity,
    ExtractedEntity,
    EntityRelationship,
    EntityMention,
    EntityResolution,
    EntityType,
    EntityStatus
)
from .extraction_schemas import (
    ContentExtractionSchema,
    ContentExtraction,
    ExtractionTemplate,
    ExtractionJob,
    ContentExtractionSchemaCreate,
    ContentExtractionSchemaUpdate,
    ContentExtractionSchemaRead,
    ContentExtractionCreate,
    ContentExtractionRead,
    ExtractionTemplateCreate,
    ExtractionTemplateRead,
    ExtractionJobCreate,
    ExtractionJobRead,
    SchemaType,
    ExtractionStatus,
    ExtractionMethod
)
from .investigations import (
    Investigation,
    Evidence,
    PageComparison,
    InvestigationTimeline,
    InvestigationFinding,
    InvestigationCreate,
    InvestigationUpdate,
    InvestigationRead,
    EvidenceCreate,
    EvidenceRead,
    PageComparisonCreate,
    PageComparisonRead,
    InvestigationTimelineCreate,
    InvestigationTimelineRead,
    InvestigationFindingCreate,
    InvestigationFindingRead,
    InvestigationStatus,
    InvestigationPriority,
    EvidenceType,
    EvidenceStatus
)

__all__ = [
    # User models
    "User",
    "UserCreate", 
    "UserUpdate",
    "UserRead",
    "UserReadWithStats",
    
    # Project models
    "Project",
    "Domain",
    "ScrapeSession", 
    "Page",
    "ProjectCreate",
    "ProjectUpdate", 
    "ProjectRead",
    "ProjectReadWithStats",
    "DomainCreate",
    "DomainUpdate",
    "DomainRead",
    
    # API Config models
    "APIConfig",
    "APIKey",
    "APIConfigCreate",
    "APIConfigUpdate", 
    "APIConfigRead",
    "APIKeyCreate",
    "APIKeyRead",
    "APIKeyCreateResponse",
    
    # Plan models
    "UserPlan",
    "UserRateLimit", 
    "UserPlanUsage",
    "PlanFeature",
    
    # Library models
    "StarredItem",
    "SavedSearch",
    "SearchHistory", 
    "SearchSuggestion",
    "UserCollection",
    
    # Entity models
    "CanonicalEntity",
    "ExtractedEntity",
    "EntityRelationship",
    "EntityMention", 
    "EntityResolution",
    
    # Extraction Schema models
    "ContentExtractionSchema",
    "ContentExtraction",
    "ExtractionTemplate",
    "ExtractionJob",
    "ContentExtractionSchemaCreate",
    "ContentExtractionSchemaUpdate",
    "ContentExtractionSchemaRead",
    "ContentExtractionCreate",
    "ContentExtractionRead",
    "ExtractionTemplateCreate",
    "ExtractionTemplateRead",
    "ExtractionJobCreate",
    "ExtractionJobRead",
    
    # Investigation models
    "Investigation",
    "Evidence",
    "PageComparison",
    "InvestigationTimeline",
    "InvestigationFinding",
    "InvestigationCreate",
    "InvestigationUpdate",
    "InvestigationRead",
    "EvidenceCreate",
    "EvidenceRead",
    "PageComparisonCreate",
    "PageComparisonRead",
    "InvestigationTimelineCreate",
    "InvestigationTimelineRead",
    "InvestigationFindingCreate",
    "InvestigationFindingRead",
    
    # Enums
    "ProjectStatus",
    "DomainStatus", 
    "MatchType",
    "ScrapeSessionStatus",
    "APIServiceType",
    "PlanTier",
    "ItemType",
    "AlertFrequency", 
    "EntityType",
    "EntityStatus",
    "SchemaType",
    "ExtractionStatus",
    "ExtractionMethod",
    "InvestigationStatus",
    "InvestigationPriority",
    "EvidenceType",
    "EvidenceStatus"
]