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

from app.models.user import User
from app.models.project import Project, Domain, ScrapeSession
from app.models.invitation import InvitationToken
from app.models.scraping import ScrapePage


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


# List of all admin views to register
ADMIN_VIEWS = [
	UserAdmin,
	ProjectAdmin,
	DomainAdmin,
	InvitationTokenAdmin,
	ScrapeSessionAdmin,
	ScrapePageAdmin,
]