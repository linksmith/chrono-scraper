"""
Entity extraction and linking models
"""
from typing import Optional, List, Dict, Any, TYPE_CHECKING
from datetime import datetime
from enum import Enum
from sqlmodel import Field, SQLModel, Relationship, Column, JSON, Text
from sqlalchemy import UniqueConstraint, Index, CheckConstraint

if TYPE_CHECKING:
    from app.models.project import Project


class EntityType(str, Enum):
    """Types of entities that can be extracted"""
    PERSON = "person"
    ORGANIZATION = "organization"
    LOCATION = "location"
    EVENT = "event"
    PRODUCT = "product"
    DATE = "date"
    MONEY = "money"
    EMAIL = "email"
    PHONE = "phone"
    URL = "url"
    HASHTAG = "hashtag"
    MENTION = "mention"
    CUSTOM = "custom"


class EntityStatus(str, Enum):
    """Entity verification status"""
    UNVERIFIED = "unverified"
    VERIFIED = "verified"
    DISPUTED = "disputed"
    MERGED = "merged"


class CanonicalEntity(SQLModel, table=True):
    """Canonical entities - deduplicated and verified entities"""
    __tablename__ = "canonical_entities"
    __table_args__ = (
        UniqueConstraint("entity_type", "normalized_name"),
        Index("idx_canonical_entity_type_name", "entity_type", "primary_name"),
        Index("idx_canonical_entity_confidence", "confidence_score"),
        CheckConstraint("confidence_score >= 0.0 AND confidence_score <= 1.0", name="ck_confidence_score_range"),
    )
    
    id: Optional[int] = Field(default=None, primary_key=True)
    
    # Entity identification
    entity_type: EntityType
    primary_name: str = Field(index=True)
    normalized_name: str = Field(index=True)  # Lowercase, stripped, etc.
    
    # Alternative names and aliases
    aliases: List[str] = Field(default=[], sa_column=Column(JSON))
    acronyms: List[str] = Field(default=[], sa_column=Column(JSON))
    alternate_spellings: List[str] = Field(default=[], sa_column=Column(JSON))
    
    # Entity details
    description: str = Field(default="", sa_column=Column(Text))
    disambiguation: Optional[str] = Field(default=None)  # e.g., "Apple Inc." vs "Apple (fruit)"
    
    # Structured attributes based on entity type
    attributes: Dict[str, Any] = Field(default={}, sa_column=Column(JSON))
    # For PERSON: {title, role, organization, birth_date, etc.}
    # For ORGANIZATION: {industry, founded, headquarters, website, etc.}
    # For LOCATION: {country, region, coordinates, timezone, etc.}
    
    # External identifiers
    external_ids: Dict[str, str] = Field(default={}, sa_column=Column(JSON))
    # {wikidata: Q123, dbpedia: Apple_Inc, linkedin: /company/apple, etc.}
    
    # Verification and confidence
    status: EntityStatus = Field(default=EntityStatus.UNVERIFIED)
    confidence_score: float = Field(default=0.5, ge=0.0, le=1.0)
    verification_sources: List[str] = Field(default=[], sa_column=Column(JSON))
    verified_by_user_id: Optional[int] = Field(default=None, foreign_key="users.id")
    verified_at: Optional[datetime] = None
    
    # Statistics
    occurrence_count: int = Field(default=0)
    first_seen: datetime = Field(default_factory=datetime.utcnow)
    last_seen: datetime = Field(default_factory=datetime.utcnow)
    
    # Relationships tracking
    related_entities: List[int] = Field(default=[], sa_column=Column(JSON))  # IDs of related entities
    
    # Metadata
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    # Relationships
    extracted_entities: List["ExtractedEntity"] = Relationship(back_populates="canonical_entity")
    entity_relationships: List["EntityRelationship"] = Relationship(
        back_populates="source_entity",
        sa_relationship_kwargs={"foreign_keys": "EntityRelationship.source_entity_id"}
    )
    # Note: starred_by relationship handled through StarredItem.item_id + item_type polymorphic pattern


class ExtractedEntity(SQLModel, table=True):
    """Entities extracted from specific pages/content"""
    __tablename__ = "extracted_entities"
    __table_args__ = (
        Index("idx_extracted_entity_page", "page_id", "entity_type"),
        Index("idx_extracted_entity_canonical", "canonical_entity_id"),
    )
    
    id: Optional[int] = Field(default=None, primary_key=True)
    
    # Source reference - page_id legacy field (no longer references pages table)
    page_id: Optional[int] = Field(default=None, index=True)
    project_id: int = Field(foreign_key="projects.id", index=True)
    
    # Extracted entity details
    entity_type: EntityType
    text: str  # Original text as found in content
    normalized_text: str  # Normalized version
    
    # Position in source
    start_position: Optional[int] = Field(default=None)  # Character position in text
    end_position: Optional[int] = Field(default=None)
    context: Optional[str] = Field(default=None, sa_column=Column(Text))  # Surrounding text
    
    # Linking to canonical entity
    canonical_entity_id: Optional[int] = Field(default=None, foreign_key="canonical_entities.id")
    linking_confidence: float = Field(default=0.0)
    linking_method: Optional[str] = Field(default=None)  # exact, fuzzy, ml_model, manual
    
    # Extraction metadata
    extraction_method: str = Field(default="ner")  # ner, regex, rule, manual
    extraction_confidence: float = Field(default=0.5)
    extractor_version: str = Field(default="1.0")
    
    # Additional extracted info
    sentiment: Optional[float] = Field(default=None)  # -1.0 to 1.0
    salience: Optional[float] = Field(default=None)  # 0.0 to 1.0 importance score
    
    # Timestamps
    extracted_at: datetime = Field(default_factory=datetime.utcnow)
    
    # Relationships - page relationship removed due to legacy Page model removal
    project: Optional["Project"] = Relationship(back_populates="extracted_entities")
    canonical_entity: Optional["CanonicalEntity"] = Relationship(back_populates="extracted_entities")


class EntityRelationship(SQLModel, table=True):
    """Relationships between entities"""
    __tablename__ = "entity_relationships"
    __table_args__ = (
        UniqueConstraint("source_entity_id", "target_entity_id", "relationship_type"),
        Index("idx_entity_rel_source", "source_entity_id", "relationship_type"),
        Index("idx_entity_rel_target", "target_entity_id", "relationship_type"),
    )
    
    id: Optional[int] = Field(default=None, primary_key=True)
    
    # Relationship entities
    source_entity_id: int = Field(foreign_key="canonical_entities.id")
    target_entity_id: int = Field(foreign_key="canonical_entities.id")
    
    # Relationship details
    relationship_type: str  # employs, located_in, owns, partners_with, etc.
    relationship_subtype: Optional[str] = Field(default=None)
    
    # Relationship properties
    properties: Dict[str, Any] = Field(default={}, sa_column=Column(JSON))
    # {start_date, end_date, role, title, etc.}
    
    # Confidence and verification
    confidence_score: float = Field(default=0.5)
    evidence_count: int = Field(default=1)
    evidence_sources: List[str] = Field(default=[], sa_column=Column(JSON))
    
    # Temporal aspects
    is_current: bool = Field(default=True)
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    
    # Metadata
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    first_observed: datetime = Field(default_factory=datetime.utcnow)
    last_observed: datetime = Field(default_factory=datetime.utcnow)
    
    # Relationships
    source_entity: Optional["CanonicalEntity"] = Relationship(
        back_populates="entity_relationships",
        sa_relationship_kwargs={"foreign_keys": "[EntityRelationship.source_entity_id]"}
    )
    target_entity: Optional["CanonicalEntity"] = Relationship(
        sa_relationship_kwargs={"foreign_keys": "[EntityRelationship.target_entity_id]"}
    )


class EntityMention(SQLModel, table=True):
    """Track entity mentions and co-occurrences for relationship inference"""
    __tablename__ = "entity_mentions"
    __table_args__ = (
        Index("idx_entity_mention_page", "page_id", "entity_id"),
        Index("idx_entity_mention_cooccurrence", "entity_id", "mentioned_with_entity_id"),
    )
    
    id: Optional[int] = Field(default=None, primary_key=True)
    
    # Mention context - page_id legacy field (no longer references pages table)
    page_id: Optional[int] = Field(default=None)
    entity_id: int = Field(foreign_key="canonical_entities.id")
    
    # Mention details
    mention_count: int = Field(default=1)
    prominence_score: float = Field(default=0.5)  # How prominent in the content
    
    # Co-occurrence tracking
    mentioned_with_entity_id: Optional[int] = Field(default=None, foreign_key="canonical_entities.id")
    co_occurrence_count: int = Field(default=0)
    proximity_score: float = Field(default=0.0)  # How close they appear
    
    # Context
    contexts: List[str] = Field(default=[], sa_column=Column(JSON))
    sentiment_scores: List[float] = Field(default=[], sa_column=Column(JSON))
    
    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class EntityResolution(SQLModel, table=True):
    """Track entity resolution decisions and merges"""
    __tablename__ = "entity_resolutions"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    
    # Resolution details
    merged_entity_ids: List[int] = Field(sa_column=Column(JSON))
    canonical_entity_id: int = Field(foreign_key="canonical_entities.id")
    
    # Resolution metadata
    resolution_method: str  # manual, automatic, ml_model
    resolution_confidence: float = Field(default=0.5)
    resolution_rules: Dict[str, Any] = Field(default={}, sa_column=Column(JSON))
    
    # User action
    resolved_by_user_id: Optional[int] = Field(default=None, foreign_key="users.id")
    resolution_notes: str = Field(default="", sa_column=Column(Text))
    
    # Timestamps
    resolved_at: datetime = Field(default_factory=datetime.utcnow)
    
    # Rollback capability
    is_active: bool = Field(default=True)
    rolled_back_at: Optional[datetime] = None
    rolled_back_by_user_id: Optional[int] = Field(default=None, foreign_key="users.id")