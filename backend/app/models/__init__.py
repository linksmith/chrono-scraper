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
from .user_approval import (
    UserApprovalMessage,
    LLMConfiguration,
    LLMEvaluationLog,
    UserEvaluation,
    ApprovalToken,
    UserApprovalMessageCreate,
    UserApprovalMessageRead,
    LLMConfigurationCreate,
    LLMConfigurationUpdate,
    LLMConfigurationRead,
    UserEvaluationCreate,
    UserEvaluationRead,
    ApprovalTokenCreate,
    ApprovalTokenRead,
    ApprovalTokenUse,
    ApprovalStatus,
    EvaluationProvider,
    ApprovalTokenAction
)
from .sharing import (
    ProjectShare,
    PublicSearchConfig,
    ShareInvitation,
    ShareAccessLog,
    ProjectShareCreate,
    ProjectShareUpdate,
    ProjectShareRead,
    PublicSearchConfigCreate,
    PublicSearchConfigUpdate,
    PublicSearchConfigRead,
    ShareInvitationCreate,
    ShareInvitationRead,
    ShareAccessLogCreate,
    ShareAccessLogRead,
    SharePermission,
    ShareStatus,
    PublicAccessLevel
)
from .scraping import (
    ScrapePage,
    CDXResumeState,
    ScrapeMonitoringLog,
    PageErrorLog,
    ScrapePageCreate,
    ScrapePageRead,
    CDXResumeStateRead,
    ScrapeProgressUpdate,
    ScrapePageStatus,
    CDXResumeStatus
)
from .rbac import (
    Permission,
    Role,
    PermissionCreate,
    PermissionRead,
    RoleCreate,
    RoleUpdate,
    RoleRead,
    RoleReadWithPermissions,
    UserRoleAssignment,
    UserPermissionCheck,
    PermissionType,
    DefaultRole
)
from .invitation import (
    InvitationToken,
    InvitationTokenCreate,
    InvitationTokenRead,
    InvitationTokenUpdate,
    InvitationTokenValidation,
    generate_invitation_token
)
from .admin_settings import (
    AdminSettings,
    AdminSettingsRead,
    AdminSettingsUpdate
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
    
    # User Approval models
    "UserApprovalMessage",
    "LLMConfiguration",
    "LLMEvaluationLog",
    "UserEvaluation",
    "ApprovalToken",
    "UserApprovalMessageCreate",
    "UserApprovalMessageRead",
    "LLMConfigurationCreate",
    "LLMConfigurationUpdate",
    "LLMConfigurationRead",
    "UserEvaluationCreate",
    "UserEvaluationRead",
    "ApprovalTokenCreate",
    "ApprovalTokenRead",
    "ApprovalTokenUse",
    
    # Sharing models
    "ProjectShare",
    "PublicSearchConfig",
    "ShareInvitation",
    "ShareAccessLog",
    "ProjectShareCreate",
    "ProjectShareUpdate",
    "ProjectShareRead",
    "PublicSearchConfigCreate",
    "PublicSearchConfigUpdate",
    "PublicSearchConfigRead",
    "ShareInvitationCreate",
    "ShareInvitationRead",
    "ShareAccessLogCreate",
    "ShareAccessLogRead",
    
    # Scraping models
    "ScrapePage",
    "CDXResumeState",
    "ScrapeMonitoringLog",
    "PageErrorLog",
    "ScrapePageCreate",
    "ScrapePageRead",
    "CDXResumeStateRead",
    "ScrapeProgressUpdate",
    
    # RBAC models
    "Permission",
    "Role",
    "PermissionCreate",
    "PermissionRead",
    "RoleCreate",
    "RoleUpdate",
    "RoleRead",
    "RoleReadWithPermissions",
    "UserRoleAssignment",
    "UserPermissionCheck",
    
    # Invitation models
    "InvitationToken",
    "InvitationTokenCreate",
    "InvitationTokenRead",
    "InvitationTokenUpdate",
    "InvitationTokenValidation",
    "generate_invitation_token",
    
    # Admin Settings models
    "AdminSettings",
    "AdminSettingsRead",
    "AdminSettingsUpdate",
    
    # Enums
    "ProjectStatus",
    "DomainStatus", 
    "MatchType",
    "ScrapeSessionStatus",
    "ScrapePageStatus",
    "CDXResumeStatus",
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
    "EvidenceStatus",
    "ApprovalStatus",
    "EvaluationProvider",
    "ApprovalTokenAction",
    "SharePermission",
    "ShareStatus",
    "PublicAccessLevel",
    "PermissionType",
    "DefaultRole"
]