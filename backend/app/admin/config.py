"""
SQLAdmin configuration for Chrono Scraper
"""
from typing import Optional

# Optional dependency: sqladmin
try:  # pragma: no cover
	from sqladmin import Admin
	from sqladmin.authentication import AuthenticationBackend
	_HAS_SQLADMIN = True
except Exception:  # pragma: no cover
	Admin = object  # type: ignore
	class AuthenticationBackend:  # type: ignore
		pass
	_HAS_SQLADMIN = False

from starlette.requests import Request
from starlette.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import engine, get_db
from app.core.config import settings
from app.services.auth import authenticate_user, get_user_by_id
from app.services.session_store import SessionStore, get_session_store


class AdminAuth(AuthenticationBackend):
	"""Authentication backend for SQLAdmin"""
	
	def __init__(self):
		super().__init__(secret_key=settings.SECRET_KEY)
	
	async def login(self, request: Request) -> bool:  # pragma: no cover - not used in tests
		form = await request.form()
		email = form.get("username")  # SQLAdmin uses 'username' field
		password = form.get("password")
		
		if not email or not password:
			return False
		
		# Get database session
		async for db in get_db():
			user = await authenticate_user(db, email, password)
			
			if user and user.is_active and user.is_superuser:
				# Create session for admin user
				session_store = SessionStore()
				session_id = await session_store.create_session({
					"user_id": user.id,
					"email": user.email,
					"is_admin": True,
					"is_superuser": user.is_superuser
				})
				
				# Set session cookie
				request.session["admin_user_id"] = user.id
				request.session["session_id"] = session_id
				return True
			break
		
		return False
	
	async def logout(self, request: Request) -> bool:  # pragma: no cover - not used in tests
		"""Handle admin logout"""
		session_id = request.session.get("session_id")
		if session_id:
			session_store = SessionStore()
			await session_store.delete_session(session_id)
		
		request.session.clear()
		return True
	
	async def authenticate(self, request: Request) -> bool:  # pragma: no cover - not used in tests
		"""Check if user is authenticated admin"""
		user_id = request.session.get("admin_user_id")
		
		if not user_id:
			return False
		
		# Verify user is still valid and is superuser
		async for db in get_db():
			user = await get_user_by_id(db, user_id)
			if user and user.is_active and user.is_superuser:
				return True
			break
		
		return False


def create_admin(app):
	"""Create and configure SQLAdmin instance. Returns a stub when sqladmin is unavailable."""
	if not _HAS_SQLADMIN:  # pragma: no cover
		class _StubAdmin:
			def __init__(self, *_, **__):
				pass
			def add_view(self, *_):
				pass
		return _StubAdmin()
	
	authentication_backend = AdminAuth()
	
	admin = Admin(
		app=app,
		engine=engine,
		title="Chrono Scraper Admin",
		logo_url="/static/logo.png",
		authentication_backend=authentication_backend,
		debug=settings.ENVIRONMENT == "development",
	)
	
	# Add session management and analytics views
	from app.admin.session_views import SessionManagementView, UserAnalyticsView
	admin.add_view(SessionManagementView)
	admin.add_view(UserAnalyticsView)
	
	return admin