"""
SQLAdmin model views for Chrono Scraper
"""
# Optional dependency: sqladmin
try:  # pragma: no cover
	from sqladmin import ModelView
	_HAS_SQLADMIN = True
except Exception:  # pragma: no cover
	# Provide a permissive stub that accepts the same class declaration
	class _ModelViewStub:
		def __init_subclass__(cls, **kwargs):
			return super().__init_subclass__()
	ModelView = _ModelViewStub  # type: ignore
	_HAS_SQLADMIN = False

from typing import Any, Dict
from starlette.requests import Request

from app.models.user import User
from app.models.project import Project, Domain, ScrapeSession
from app.models.invitation import InvitationToken
from app.models.scraping import ScrapePage
from app.models.entities import CanonicalEntity, ExtractedEntity, EntityRelationship, EntityMention, EntityResolution
from app.models.shared_pages import PageV2, ProjectPage


class BaseChronoAdmin(ModelView):
	"""Base admin class with common configuration and error handling"""
	
	# Common configuration
	can_create = True
	can_edit = True
	can_delete = True
	can_view_details = True
	can_export = True
	
	# Pagination settings
	page_size = 50
	page_size_options = [25, 50, 100, 200]
	
	# Common error handling and validation
	async def on_model_change(self, data: Dict[str, Any], model: Any, is_created: bool, request: Request) -> None:
		"""Handle model changes with proper error handling"""
		try:
			await super().on_model_change(data, model, is_created, request)
		except Exception as e:
			# Log the error (in production, use proper logging)
			print(f"Error in {self.__class__.__name__}: {str(e)}")
			raise
	
	async def on_model_delete(self, model: Any, request: Request) -> None:
		"""Handle model deletion with proper error handling"""
		try:
			await super().on_model_delete(model, request)
		except Exception as e:
			# Log the error (in production, use proper logging)
			print(f"Error deleting in {self.__class__.__name__}: {str(e)}")
			raise


class UserAdmin(ModelView, model=User):
	"""Admin view for User model"""
	column_list = [
		User.id,
		User.email,
		User.full_name,
		User.is_active,
		User.is_verified,
		User.is_superuser,
		User.approval_status,
		User.created_at,
		User.last_login
	]
	column_searchable_list = [User.email, User.full_name]
	column_sortable_list = [
		User.id,
		User.email,
		User.created_at,
		User.last_login,
		User.approval_status
	]
	column_default_sort = [(User.created_at, True)]  # Sort by created_at desc
	
	# Fields to show in create/edit forms (cannot use both form_columns and form_excluded_columns)
	form_columns = [
		User.email,
		User.full_name,
		User.is_active,
		User.is_verified,
		User.is_superuser,
		User.approval_status,
		User.research_interests,
		User.academic_affiliation,
		User.professional_title,
		User.organization_website,
		User.research_purpose,
		User.expected_usage
	]
	
	name = "User"
	name_plural = "Users"
	icon = "fas fa-users"
	identity = "user"  # Explicit identity for SQLAdmin routing


class ProjectAdmin(ModelView, model=Project):
	"""Admin view for Project model"""
	column_list = [
		Project.id,
		Project.name,
		Project.description,
		Project.status,
		Project.user_id,
		Project.created_at
	]
	column_searchable_list = [Project.name, Project.description]
	column_sortable_list = [
		Project.id,
		Project.name,
		Project.created_at,
		Project.status
	]
	column_default_sort = [(Project.created_at, True)]
	
	form_columns = [
		Project.name,
		Project.description,
		Project.user_id
	]
	
	name = "Project"
	name_plural = "Projects"
	icon = "fas fa-folder"
	identity = "project"  # Explicit identity for SQLAdmin routing


class DomainAdmin(ModelView, model=Domain):
	"""Admin view for Domain model"""
	column_list = [
		Domain.id,
		Domain.domain_name,
		Domain.project_id,
		Domain.created_at
	]
	column_searchable_list = [Domain.domain_name]
	
	name = "Domain"
	name_plural = "Domains"
	icon = "fas fa-globe"
	identity = "domain"  # Explicit identity for SQLAdmin routing


class InvitationTokenAdmin(ModelView, model=InvitationToken):
	"""Admin view for InvitationToken model"""
	column_list = [
		InvitationToken.id,
		InvitationToken.token,
		InvitationToken.creator_user_id,
		InvitationToken.expires_at,
		InvitationToken.is_used,
		InvitationToken.created_at
	]
	column_searchable_list = [InvitationToken.token]
	
	name = "Invitation Token"
	name_plural = "Invitation Tokens"
	icon = "fas fa-ticket-alt"
	identity = "invitation_token"  # Explicit identity for SQLAdmin routing


class ScrapeSessionAdmin(ModelView, model=ScrapeSession):
	"""Admin view for ScrapeSession model"""
	column_list = [
		ScrapeSession.id,
		ScrapeSession.project_id,
		ScrapeSession.created_at
	]
	
	name = "Scrape Session"
	name_plural = "Scrape Sessions"
	icon = "fas fa-spider"
	identity = "scrape_session"  # Explicit identity for SQLAdmin routing


class ScrapePageAdmin(ModelView, model=ScrapePage):
	"""Admin view for ScrapePage model"""
	column_list = [
		ScrapePage.id,
		ScrapePage.original_url,
		ScrapePage.status,
		ScrapePage.created_at
	]
	column_searchable_list = [ScrapePage.original_url]
	
	name = "Scrape Page"
	name_plural = "Scrape Pages"
	icon = "fas fa-file-alt"
	identity = "scrape_page"  # Explicit identity for SQLAdmin routing


# LEGACY PageAdmin - DISABLED
# The legacy Page model has been removed. Use shared pages system instead.
# class PageAdmin(BaseChronoAdmin, model=Page):
# 	"""DEPRECATED: Admin view for removed Page model - use shared pages system instead"""
# 	pass


class CanonicalEntityAdmin(BaseChronoAdmin, model=CanonicalEntity):
	"""Admin view for CanonicalEntity model - Deduplicated and verified entities"""
	column_list = [
		CanonicalEntity.id,
		CanonicalEntity.primary_name,
		CanonicalEntity.entity_type,
		CanonicalEntity.status,
		CanonicalEntity.confidence_score,
		CanonicalEntity.occurrence_count,
		CanonicalEntity.verified_by_user_id,
		CanonicalEntity.created_at,
		CanonicalEntity.updated_at
	]
	
	column_searchable_list = [
		CanonicalEntity.primary_name,
		CanonicalEntity.normalized_name,
		CanonicalEntity.description,
		CanonicalEntity.disambiguation
	]
	
	column_sortable_list = [
		CanonicalEntity.id,
		CanonicalEntity.primary_name,
		CanonicalEntity.entity_type,
		CanonicalEntity.confidence_score,
		CanonicalEntity.occurrence_count,
		CanonicalEntity.created_at,
		CanonicalEntity.updated_at
	]
	
	column_default_sort = [(CanonicalEntity.occurrence_count, True)]
	
	column_filters = [
		CanonicalEntity.entity_type,
		CanonicalEntity.status,
		CanonicalEntity.confidence_score,
		CanonicalEntity.verified_by_user_id
	]
	
	form_columns = [
		CanonicalEntity.primary_name,
		CanonicalEntity.entity_type,
		CanonicalEntity.normalized_name,
		CanonicalEntity.aliases,
		CanonicalEntity.acronyms,
		CanonicalEntity.alternate_spellings,
		CanonicalEntity.description,
		CanonicalEntity.disambiguation,
		CanonicalEntity.attributes,
		CanonicalEntity.external_ids,
		CanonicalEntity.status,
		CanonicalEntity.confidence_score,
		CanonicalEntity.verification_sources
	]
	
	form_widget_args = {
		"description": {"rows": 5},
		"attributes": {"rows": 8},
		"external_ids": {"rows": 4},
		"aliases": {"rows": 3},
		"verification_sources": {"rows": 3}
	}
	
	column_formatters = {
		"description": lambda m, a: f"{a[:100]}..." if a else "",
		"confidence_score": lambda m, a: f"{a:.3f}" if a else "0.000",
		"occurrence_count": lambda m, a: f"{a:,}" if a else "0",
		"aliases": lambda m, a: ", ".join(a[:3]) + ("..." if len(a) > 3 else "") if a else "",
		"attributes": lambda m, a: f"{len(a)} attributes" if a else "No attributes"
	}
	
	name = "Canonical Entity"
	name_plural = "Canonical Entities"
	icon = "fas fa-tags"
	identity = "canonical_entity"  # Explicit identity for SQLAdmin routing


class ExtractedEntityAdmin(ModelView, model=ExtractedEntity):
	"""Admin view for ExtractedEntity model - Entities extracted from specific pages"""
	column_list = [
		ExtractedEntity.id,
		ExtractedEntity.text,
		ExtractedEntity.entity_type,
		ExtractedEntity.page_id,
		ExtractedEntity.project_id,
		ExtractedEntity.canonical_entity_id,
		ExtractedEntity.extraction_confidence,
		ExtractedEntity.linking_confidence,
		ExtractedEntity.extraction_method,
		ExtractedEntity.extracted_at
	]
	
	column_searchable_list = [
		ExtractedEntity.text,
		ExtractedEntity.normalized_text,
		ExtractedEntity.context,
		ExtractedEntity.extraction_method
	]
	
	column_sortable_list = [
		ExtractedEntity.id,
		ExtractedEntity.text,
		ExtractedEntity.entity_type,
		ExtractedEntity.extraction_confidence,
		ExtractedEntity.linking_confidence,
		ExtractedEntity.extracted_at
	]
	
	column_default_sort = [(ExtractedEntity.extracted_at, True)]
	
	column_filters = [
		ExtractedEntity.entity_type,
		ExtractedEntity.extraction_method,
		ExtractedEntity.linking_method,
		ExtractedEntity.page_id,
		ExtractedEntity.project_id,
		ExtractedEntity.canonical_entity_id
	]
	
	form_columns = [
		ExtractedEntity.text,
		ExtractedEntity.normalized_text,
		ExtractedEntity.entity_type,
		ExtractedEntity.page_id,
		ExtractedEntity.project_id,
		ExtractedEntity.canonical_entity_id,
		ExtractedEntity.start_position,
		ExtractedEntity.end_position,
		ExtractedEntity.context,
		ExtractedEntity.linking_confidence,
		ExtractedEntity.linking_method,
		ExtractedEntity.extraction_method,
		ExtractedEntity.extraction_confidence,
		ExtractedEntity.sentiment,
		ExtractedEntity.salience
	]
	
	form_widget_args = {
		"context": {"rows": 4},
		"text": {"rows": 2}
	}
	
	column_formatters = {
		"text": lambda m, a: f"{a[:50]}..." if len(a) > 50 else a,
		"context": lambda m, a: f"{a[:80]}..." if a and len(a) > 80 else (a or ""),
		"extraction_confidence": lambda m, a: f"{a:.3f}" if a else "N/A",
		"linking_confidence": lambda m, a: f"{a:.3f}" if a else "N/A",
		"sentiment": lambda m, a: f"{a:+.2f}" if a is not None else "N/A",
		"salience": lambda m, a: f"{a:.3f}" if a else "N/A"
	}
	
	name = "Extracted Entity"
	name_plural = "Extracted Entities"
	icon = "fas fa-search"
	identity = "extracted_entity"  # Explicit identity for SQLAdmin routing


class PageV2Admin(BaseChronoAdmin, model=PageV2):
	"""Admin view for PageV2 model - Independent shared pages"""
	column_list = [
		PageV2.id,
		PageV2.title,
		PageV2.url,
		PageV2.unix_timestamp,
		PageV2.quality_score,
		PageV2.word_count,
		PageV2.content_type,
		PageV2.processed,
		PageV2.indexed,
		PageV2.created_at,
		PageV2.updated_at
	]
	
	column_searchable_list = [
		PageV2.title,
		PageV2.url,
		PageV2.extracted_title,
		PageV2.author,
		PageV2.meta_description,
		PageV2.content_type
	]
	
	column_sortable_list = [
		PageV2.title,
		PageV2.unix_timestamp,
		PageV2.quality_score,
		PageV2.word_count,
		PageV2.created_at,
		PageV2.updated_at
	]
	
	column_default_sort = [(PageV2.created_at, True)]
	
	column_filters = [
		PageV2.processed,
		PageV2.indexed,
		PageV2.content_type,
		PageV2.language,
		PageV2.mime_type
	]
	
	form_columns = [
		PageV2.url,
		PageV2.unix_timestamp,
		PageV2.content_url,
		PageV2.title,
		PageV2.extracted_title,
		PageV2.meta_description,
		PageV2.meta_keywords,
		PageV2.author,
		PageV2.published_date,
		PageV2.language,
		PageV2.content_type,
		PageV2.mime_type,
		PageV2.quality_score
	]
	
	form_widget_args = {
		"content": {"rows": 15},
		"markdown_content": {"rows": 15},
		"extracted_text": {"rows": 10},
		"meta_description": {"rows": 3},
		"meta_keywords": {"rows": 2}
	}
	
	column_formatters = {
		"url": lambda m, a: f'<a href="{a}" target="_blank">{a[:60]}...</a>' if a else "",
		"content_url": lambda m, a: f'<a href="{a}" target="_blank">View Archive</a>' if a else "",
		"quality_score": lambda m, a: f"{a:.2f}" if a else "N/A",
		"word_count": lambda m, a: f"{a:,}" if a else "0",
		"unix_timestamp": lambda m, a: f"{a}" if a else "N/A",
		"id": lambda m, a: str(a)[:8] + "..." if a else ""
	}
	
	name = "Shared Page (V2)"
	name_plural = "Shared Pages (V2)"
	icon = "fas fa-share-alt"
	identity = "page_v2"  # Explicit identity for SQLAdmin routing


class ProjectPageAdmin(ModelView, model=ProjectPage):
	"""Admin view for ProjectPage model - Many-to-many page-project relationships"""
	column_list = [
		ProjectPage.id,
		ProjectPage.project_id,
		ProjectPage.page_id,
		ProjectPage.added_by,
		ProjectPage.review_status,
		ProjectPage.priority_level,
		ProjectPage.reviewed_by,
		ProjectPage.added_at,
		ProjectPage.reviewed_at
	]
	
	column_searchable_list = [
		ProjectPage.review_notes,
		ProjectPage.notes
	]
	
	column_sortable_list = [
		ProjectPage.id,
		ProjectPage.project_id,
		ProjectPage.page_id,
		ProjectPage.review_status,
		ProjectPage.priority_level,
		ProjectPage.added_at,
		ProjectPage.reviewed_at
	]
	
	column_default_sort = [(ProjectPage.added_at, True)]
	
	column_filters = [
		ProjectPage.review_status,
		ProjectPage.priority_level,
		ProjectPage.page_category,
		ProjectPage.project_id,
		ProjectPage.added_by,
		ProjectPage.reviewed_by,
		ProjectPage.is_starred,
		ProjectPage.is_duplicate
	]
	
	form_columns = [
		ProjectPage.project_id,
		ProjectPage.page_id,
		ProjectPage.added_by,
		ProjectPage.review_status,
		ProjectPage.priority_level,
		ProjectPage.page_category,
		ProjectPage.review_notes,
		ProjectPage.notes,
		ProjectPage.quick_notes,
		ProjectPage.tags,
		ProjectPage.reviewed_by,
		ProjectPage.is_starred,
		ProjectPage.is_duplicate
	]
	
	form_widget_args = {
		"review_notes": {"rows": 4},
		"notes": {"rows": 3},
		"quick_notes": {"rows": 2},
		"tags": {"rows": 2}
	}
	
	column_formatters = {
		"review_notes": lambda m, a: f"{a[:60]}..." if a and len(a) > 60 else (a or ""),
		"tags": lambda m, a: ", ".join(a[:3]) + ("..." if len(a) > 3 else "") if a else "",
	}
	
	name = "Project Page"
	name_plural = "Project Pages"
	icon = "fas fa-link"
	identity = "project_page"  # Explicit identity for SQLAdmin routing


class EntityRelationshipAdmin(ModelView, model=EntityRelationship):
	"""Admin view for EntityRelationship model - Relationships between entities"""
	column_list = [
		EntityRelationship.id,
		EntityRelationship.source_entity_id,
		EntityRelationship.target_entity_id,
		EntityRelationship.relationship_type,
		EntityRelationship.relationship_subtype,
		EntityRelationship.confidence_score,
		EntityRelationship.evidence_count,
		EntityRelationship.is_current,
		EntityRelationship.created_at,
		EntityRelationship.updated_at
	]
	
	column_searchable_list = [
		EntityRelationship.relationship_type,
		EntityRelationship.relationship_subtype
	]
	
	column_sortable_list = [
		EntityRelationship.id,
		EntityRelationship.relationship_type,
		EntityRelationship.confidence_score,
		EntityRelationship.evidence_count,
		EntityRelationship.created_at,
		EntityRelationship.updated_at
	]
	
	column_default_sort = [(EntityRelationship.confidence_score, True)]
	
	column_filters = [
		EntityRelationship.relationship_type,
		EntityRelationship.is_current,
		EntityRelationship.source_entity_id,
		EntityRelationship.target_entity_id
	]
	
	form_columns = [
		EntityRelationship.source_entity_id,
		EntityRelationship.target_entity_id,
		EntityRelationship.relationship_type,
		EntityRelationship.relationship_subtype,
		EntityRelationship.properties,
		EntityRelationship.confidence_score,
		EntityRelationship.evidence_sources,
		EntityRelationship.is_current,
		EntityRelationship.start_date,
		EntityRelationship.end_date
	]
	
	form_widget_args = {
		"properties": {"rows": 6},
		"evidence_sources": {"rows": 4}
	}
	
	column_formatters = {
		"confidence_score": lambda m, a: f"{a:.3f}" if a else "0.000",
		"evidence_count": lambda m, a: f"{a:,}" if a else "0",
		"properties": lambda m, a: f"{len(a)} properties" if a else "No properties",
		"evidence_sources": lambda m, a: f"{len(a)} sources" if a else "No sources"
	}
	
	name = "Entity Relationship"
	name_plural = "Entity Relationships"
	icon = "fas fa-project-diagram"
	identity = "entity_relationship"  # Explicit identity for SQLAdmin routing


class EntityMentionAdmin(ModelView, model=EntityMention):
	"""Admin view for EntityMention model - Entity mentions and co-occurrences"""
	column_list = [
		EntityMention.id,
		EntityMention.page_id,
		EntityMention.entity_id,
		EntityMention.mention_count,
		EntityMention.prominence_score,
		EntityMention.mentioned_with_entity_id,
		EntityMention.co_occurrence_count,
		EntityMention.proximity_score,
		EntityMention.created_at,
		EntityMention.updated_at
	]
	
	column_sortable_list = [
		EntityMention.id,
		EntityMention.mention_count,
		EntityMention.prominence_score,
		EntityMention.co_occurrence_count,
		EntityMention.proximity_score,
		EntityMention.created_at,
		EntityMention.updated_at
	]
	
	column_default_sort = [(EntityMention.mention_count, True)]
	
	column_filters = [
		EntityMention.page_id,
		EntityMention.entity_id,
		EntityMention.mentioned_with_entity_id
	]
	
	form_columns = [
		EntityMention.page_id,
		EntityMention.entity_id,
		EntityMention.mention_count,
		EntityMention.prominence_score,
		EntityMention.mentioned_with_entity_id,
		EntityMention.co_occurrence_count,
		EntityMention.proximity_score,
		EntityMention.contexts,
		EntityMention.sentiment_scores
	]
	
	form_widget_args = {
		"contexts": {"rows": 5},
		"sentiment_scores": {"rows": 2}
	}
	
	column_formatters = {
		"mention_count": lambda m, a: f"{a:,}" if a else "0",
		"prominence_score": lambda m, a: f"{a:.3f}" if a else "0.000",
		"co_occurrence_count": lambda m, a: f"{a:,}" if a else "0",
		"proximity_score": lambda m, a: f"{a:.3f}" if a else "0.000",
		"contexts": lambda m, a: f"{len(a)} contexts" if a else "No contexts",
		"sentiment_scores": lambda m, a: f"{len(a)} scores" if a else "No scores"
	}
	
	name = "Entity Mention"
	name_plural = "Entity Mentions"
	icon = "fas fa-at"
	identity = "entity_mention"  # Explicit identity for SQLAdmin routing


class EntityResolutionAdmin(ModelView, model=EntityResolution):
	"""Admin view for EntityResolution model - Entity resolution decisions and merges"""
	column_list = [
		EntityResolution.id,
		EntityResolution.canonical_entity_id,
		EntityResolution.resolution_method,
		EntityResolution.resolution_confidence,
		EntityResolution.resolved_by_user_id,
		EntityResolution.is_active,
		EntityResolution.resolved_at,
		EntityResolution.rolled_back_at
	]
	
	column_searchable_list = [
		EntityResolution.resolution_method,
		EntityResolution.resolution_notes
	]
	
	column_sortable_list = [
		EntityResolution.id,
		EntityResolution.resolution_method,
		EntityResolution.resolution_confidence,
		EntityResolution.resolved_at,
		EntityResolution.rolled_back_at
	]
	
	column_default_sort = [(EntityResolution.resolved_at, True)]
	
	column_filters = [
		EntityResolution.resolution_method,
		EntityResolution.is_active,
		EntityResolution.resolved_by_user_id,
		EntityResolution.canonical_entity_id
	]
	
	form_columns = [
		EntityResolution.merged_entity_ids,
		EntityResolution.canonical_entity_id,
		EntityResolution.resolution_method,
		EntityResolution.resolution_confidence,
		EntityResolution.resolution_rules,
		EntityResolution.resolved_by_user_id,
		EntityResolution.resolution_notes,
		EntityResolution.is_active
	]
	
	form_widget_args = {
		"resolution_rules": {"rows": 8},
		"resolution_notes": {"rows": 5},
		"merged_entity_ids": {"rows": 2}
	}
	
	column_formatters = {
		"resolution_confidence": lambda m, a: f"{a:.3f}" if a else "0.000",
		"merged_entity_ids": lambda m, a: f"{len(a)} entities" if a else "No entities",
		"resolution_rules": lambda m, a: f"{len(a)} rules" if a else "No rules",
		"resolution_notes": lambda m, a: f"{a[:60]}..." if a and len(a) > 60 else (a or "")
	}
	
	name = "Entity Resolution"
	name_plural = "Entity Resolutions"
	icon = "fas fa-sitemap"
	identity = "entity_resolution"  # Explicit identity for SQLAdmin routing


# List of all admin views to register
ADMIN_VIEWS = [
	# Core application models
	UserAdmin,
	ProjectAdmin,
	DomainAdmin,
	InvitationTokenAdmin,
	
	# Scraping workflow models
	ScrapeSessionAdmin,
	ScrapePageAdmin,
	
	# Content management models
	# PageAdmin,  # DISABLED: Legacy page model removed - use shared pages instead
	PageV2Admin,  # Shared pages model
	ProjectPageAdmin,  # Page-project relationships
	
	# Entity extraction and management
	CanonicalEntityAdmin,  # Deduplicated entities
	ExtractedEntityAdmin,  # Raw extracted entities
	EntityRelationshipAdmin,  # Entity relationships
	EntityMentionAdmin,  # Entity mentions and co-occurrences
	EntityResolutionAdmin,  # Entity resolution tracking
]