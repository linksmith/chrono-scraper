"""
Test configuration and fixtures for backend tests
"""
import asyncio
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel import SQLModel, create_engine, Session
from sqlmodel.pool import StaticPool
import os
import sys
from typing import Tuple
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

# Add the app directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


# Test database setup
TEST_DATABASE_URL = "sqlite:///./test.db"

# Synchronous engine for unit tests requiring direct Session
test_engine = create_engine(
	TEST_DATABASE_URL,
	connect_args={"check_same_thread": False},
	poolclass=StaticPool,
)

# Use file-based async SQLite so sync & async sessions share the same DB
ASYNC_TEST_DATABASE_URL = "sqlite+aiosqlite:///./test.db"
async_engine = create_async_engine(
	ASYNC_TEST_DATABASE_URL,
	future=True,
	echo=False,
	poolclass=StaticPool,
)
AsyncSessionLocal = sessionmaker(
	bind=async_engine,
	class_=AsyncSession,
	expire_on_commit=False,
)


@pytest.fixture(scope="session")
def event_loop():
	"""Create an instance of the default event loop for the test session."""
	loop = asyncio.get_event_loop_policy().new_event_loop()
	yield loop
	loop.close()


@pytest.fixture(name="session")
def session_fixture():
	"""Create a test database session."""
	SQLModel.metadata.create_all(test_engine)
	with Session(test_engine) as session:
		yield session
	SQLModel.metadata.drop_all(test_engine)


@pytest.fixture(name="app")
def app_fixture():
	"""Use the real FastAPI app for endpoint tests with test overrides."""
	from app.main import app as fastapi_app
	# Ensure non-production for relaxed CSRF
	from app.core.config import settings
	settings.ENVIRONMENT = "test"

	# Initialize async test DB and override get_db dependency
	async def _init_models():
		async with async_engine.begin() as conn:
			await conn.run_sync(SQLModel.metadata.drop_all)
			await conn.run_sync(SQLModel.metadata.create_all)
	asyncio.get_event_loop().run_until_complete(_init_models())

	from app.core.database import get_db as real_get_db
	from app.api.deps import get_current_user, get_current_approved_user, require_permission
	from app.models.rbac import PermissionType
	async def override_get_db():
		async with AsyncSessionLocal() as session:
			try:
				yield session
				await session.commit()
			except Exception:
				await session.rollback()
				raise
	fastapi_app.dependency_overrides[real_get_db] = override_get_db
	# Bypass approval and permission checks in tests; rely on session auth only
	fastapi_app.dependency_overrides[get_current_approved_user] = get_current_user
	fastapi_app.dependency_overrides[require_permission(PermissionType.PROJECT_CREATE)] = get_current_user
	fastapi_app.dependency_overrides[require_permission(PermissionType.DOMAIN_CREATE)] = get_current_user
	fastapi_app.dependency_overrides[require_permission(PermissionType.PROJECT_MANAGE)] = get_current_user
	return fastapi_app


def _install_fake_session_store(app: FastAPI) -> Tuple[dict, str]:
	"""Install a fake in-memory session store and return headers and session id."""
	from app.services.session_store import SessionStore
	from app.services import session_store as _session_store_mod

	class FakeRedis:
		def __init__(self):
			self.store = {}

		async def setex(self, key, ttl, value):
			self.store[key] = value

		async def get(self, key):
			return self.store.get(key)

		async def delete(self, key):
			return 1 if self.store.pop(key, None) is not None else 0

		async def exists(self, key):
			return 1 if key in self.store else 0

		def pipeline(self):
			class Pipe:
				async def execute(self):
					return [None, 0, None, None]
				def zremrangebyscore(self, *args, **kwargs):
					return self
				def zcard(self, *args, **kwargs):
					return self
				def zadd(self, *args, **kwargs):
					return self
				def expire(self, *args, **kwargs):
					return self
			return Pipe()

		async def zrange(self, *args, **kwargs):
			return []

		async def ttl(self, *args, **kwargs):
			return -2

		async def scan_iter(self, match=None):
			for key in list(self.store.keys()):
				yield key

		async def close(self):
			self.store.clear()

	fake_store = SessionStore()
	fake_store.redis = FakeRedis()
	_session_store_mod.session_store = fake_store  # inject
	return {}, ""


@pytest.fixture(name="client")
def client_fixture(app: FastAPI):
	"""Create a test client and install fake session store."""
	_install_fake_session_store(app)
	return TestClient(app)


@pytest.fixture
def mock_user():
	"""Create a mock user for testing."""
	from passlib.context import CryptContext
	pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
	
	return {
		"id": 1,
		"email": "test@example.com",
		"hashed_password": pwd_context.hash("testpassword123"),
		"full_name": "Test User",
		"is_active": True,
		"is_verified": True
	}


@pytest.fixture
def mock_project(mock_user):
	"""Create a mock project for testing."""
	return {
		"id": 1,
		"name": "Test Project",
		"description": "A test project",
		"owner_id": mock_user["id"],
		"config": {"test": True}
	}


@pytest.fixture
def auth_headers(client: TestClient):
	"""Perform session login and return cookie headers for authenticated requests."""
	# Ensure a user exists via registration
	resp = client.post(
		"/api/v1/auth/register",
		json={
			"email": "tester@example.com",
			"password": "StrongPass1!",
			"full_name": "Tester"
		},
	)
	# Some envs may return 201 or 200 if already exists
	assert resp.status_code in (200, 201)

	# Initialize RBAC defaults and assign researcher role
	async def _init_rbac_and_assign():
		async with AsyncSessionLocal() as session:
			from app.services.rbac import RBACService
			from app.models.rbac import DefaultRole
			from app.services.auth import get_user_by_email
			user = await get_user_by_email(session, "tester@example.com")
			await RBACService.initialize_default_roles(session)
			if user:
				await RBACService.assign_default_role_to_user(session, user, DefaultRole.RESEARCHER)
	asyncio.get_event_loop().run_until_complete(_init_rbac_and_assign())

	# Login with session auth
	resp2 = client.post(
		"/api/v1/auth/login",
		json={"email": "tester@example.com", "password": "StrongPass1!"},
	)
	assert resp2.status_code == 200
	# TestClient manages cookies automatically; return empty headers as endpoints rely on cookie
	return {}


@pytest.fixture
def test_user(session: Session):
	"""Create a persistent test user in sync test DB for model tests depending on Session."""
	from app.models.user import User
	from app.core.security import get_password_hash
	user = User(
		email="projecttester@example.com",
		hashed_password=get_password_hash("StrongPass1!"),
		full_name="Project Tester",
		is_active=True,
		is_verified=True,
	)
	session.add(user)
	session.commit()
	session.refresh(user)
	return user


@pytest.fixture
def test_project(app: FastAPI):
	"""Create a project in the async app DB for a known user without logging in the client."""
	async def _create_project():
		from app.models.user import User
		from app.core.security import get_password_hash
		from app.models.project import Project
		from sqlalchemy import select
		async with AsyncSessionLocal() as session:
			# Ensure a deterministic owner user exists
			result = await session.execute(select(User).where(User.email == "tester@example.com"))
			user = result.scalar_one_or_none()
			if not user:
				user = User(
					email="tester@example.com",
					hashed_password=get_password_hash("StrongPass1!"),
					full_name="Tester",
					is_active=True,
					is_verified=True,
					approval_status="approved",
				)
				session.add(user)
				await session.commit()
				await session.refresh(user)

			proj = Project(
				name="Fixture Project",
				description="Fixture project for tests",
				user_id=user.id,
			)
			session.add(proj)
			await session.commit()
			await session.refresh(proj)
			return proj
	return asyncio.get_event_loop().run_until_complete(_create_project())