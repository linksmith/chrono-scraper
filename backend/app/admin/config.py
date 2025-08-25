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
					"id": user.id,
					"email": user.email,
					"username": user.email,  # Use email as username
					"is_active": user.is_active,
					"is_verified": getattr(user, 'is_verified', True),
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
	print("create_admin function called")
	
	if not _HAS_SQLADMIN:  # pragma: no cover
		print("SQLAdmin not available, returning stub")
		class _StubAdmin:
			def __init__(self, *_, **__):
				pass
			def add_view(self, *_):
				pass
		return _StubAdmin()
	
	print("SQLAdmin available, creating admin instance")
	authentication_backend = AdminAuth()
	
	admin = Admin(
		app=app,
		engine=engine,
		title="Chrono Scraper Admin",
		logo_url="/static/logo.png",
		authentication_backend=authentication_backend,
		debug=settings.ENVIRONMENT == "development",
		base_url="/admin"  # Ensure proper base URL
	)
	print("Admin instance created successfully")
	
	# Add session management and analytics views
	try:
		from app.admin.session_views import SessionManagementView, UserAnalyticsView
		admin.add_view(SessionManagementView)
		admin.add_view(UserAnalyticsView)
		print("Successfully loaded session management views")
	except Exception as e:
		print(f"Could not load session views: {e}")
	
	# Add monitoring views (temporarily disabled due to recursion issue)
	try:
		# TODO: Re-enable monitoring views after fixing recursion issue
		# from app.admin.monitoring_views import MONITORING_VIEWS
		# for monitoring_view in MONITORING_VIEWS:
		#     admin.add_view(monitoring_view)
		# print(f"Successfully loaded {len(MONITORING_VIEWS)} monitoring views")
		print("Monitoring views temporarily disabled")
	except Exception as e:
		print(f"Could not load monitoring views: {e}")
	
	# Add alert management views
	try:
		from app.admin.views.alert_views import router as alert_router
		app.include_router(alert_router, prefix="/admin", tags=["admin-alerts"])
	except Exception as e:
		# Alert system is optional - continue without it if there are issues
		print(f"Could not initialize alert admin views: {e}")
	
	# Add all model admin views first - these are the core views with proper identities
	try:
		print("Starting admin views loading...")
		# Import directly from the views.py file, not the views package
		import sys
		import importlib.util
		import os
		
		# Load views.py directly to avoid conflict with views/ directory
		views_py_path = os.path.join(os.path.dirname(__file__), 'views.py')
		print(f"Loading admin views from: {views_py_path}")
		spec = importlib.util.spec_from_file_location("admin_views", views_py_path)
		views_module = importlib.util.module_from_spec(spec)
		spec.loader.exec_module(views_module)
		
		ADMIN_VIEWS = getattr(views_module, 'ADMIN_VIEWS', [])
		print(f"Found {len(ADMIN_VIEWS)} admin views to register")
		
		for i, admin_view in enumerate(ADMIN_VIEWS):
			print(f"Registering view {i+1}: {admin_view.__name__}")
			admin.add_view(admin_view)
			
		print(f"Successfully loaded {len(ADMIN_VIEWS)} model admin views")
	except Exception as e:
		print(f"Could not load ADMIN_VIEWS: {e}")
		import traceback
		traceback.print_exc()
		# Continue without admin views
	
	return admin