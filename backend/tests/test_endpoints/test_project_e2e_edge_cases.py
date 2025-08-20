"""
End-to-end tests for project creation edge cases using session auth (no JWT).
This module spins up the real FastAPI app with dependency overrides:
- SQLite (aiosqlite) async DB for isolation
- In-memory session store (no Redis)
and performs a login to obtain a session and CSRF token before POST requests.
"""
import asyncio
from typing import Tuple

import pytest
from fastapi.testclient import TestClient
from sqlmodel import SQLModel
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from app.main import app as fastapi_app
from app.api.deps import get_db, get_session_store
from app.core.security import get_password_hash
from app.models.user import User


# ---- Test infrastructure (DB + session store overrides) ----
TEST_DB_URL = "sqlite+aiosqlite:///./test_e2e_projects.db"
_engine = create_async_engine(TEST_DB_URL, echo=False, future=True)
_AsyncSessionLocal = sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)


class FakeSessionStore:
    def __init__(self):
        self._store = {}

    async def create_session(self, user_data, ttl_seconds=None) -> str:
        import secrets
        session_id = f"sess_{secrets.token_urlsafe(16)}"
        from app.services.session_store import SessionData
        self._store[session_id] = SessionData(
            user_id=user_data["id"],
            email=user_data["email"],
            username=user_data.get("username", user_data["email"]),
            is_active=user_data.get("is_active", True),
            is_verified=user_data.get("is_verified", True),
            is_admin=user_data.get("is_admin", False),
            is_superuser=user_data.get("is_superuser", False),
            approval_status=user_data.get("approval_status", "approved"),
            created_at=__import__("datetime").datetime.utcnow(),
            last_activity=__import__("datetime").datetime.utcnow(),
        )
        return session_id

    async def get_session(self, session_id: str):
        return self._store.get(session_id)

    async def delete_session(self, session_id: str) -> bool:
        return self._store.pop(session_id, None) is not None


_fake_session_store = FakeSessionStore()


async def _init_db():
    async with _engine.begin() as conn:
        # Ensure fresh schema for each run
        await conn.run_sync(SQLModel.metadata.drop_all)
        await conn.run_sync(SQLModel.metadata.create_all)


async def _create_superuser():
    async with _AsyncSessionLocal() as session:
        # Idempotent create
        result = await session.execute(
            __import__("sqlmodel").select(User).where(User.email == "test@example.com")
        )
        user = result.scalar_one_or_none()
        if user:
            return
        user = User(
            email="test@example.com",
            full_name="Test User",
            hashed_password=get_password_hash("testpassword123"),
            is_active=True,
            is_verified=True,
            is_superuser=True,
            approval_status="approved",
        )
        session.add(user)
        await session.commit()


async def _override_get_db():
    async with _AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def _override_get_session_store():
    return _fake_session_store


def build_client_and_csrf() -> Tuple[TestClient, str]:
    # One-time init
    asyncio.get_event_loop().run_until_complete(_init_db())
    asyncio.get_event_loop().run_until_complete(_create_superuser())

    # Apply dependency overrides
    fastapi_app.dependency_overrides[get_db] = _override_get_db
    fastapi_app.dependency_overrides[get_session_store] = _override_get_session_store

    client = TestClient(fastapi_app)

    # Ensure global session_store used by CSRF middleware points to our fake
    from app.services import session_store as _ss_module
    _ss_module.session_store = _fake_session_store  # type: ignore

    # Login to obtain session cookie
    resp = client.post(
        "/api/v1/auth/login",
        json={"email": "test@example.com", "password": "testpassword123"},
    )
    assert resp.status_code == 200, f"login failed: {resp.text}"

    # Fetch CSRF token via a GET to any API endpoint
    resp2 = client.get("/api/v1/projects/")
    assert resp2.status_code in (200, 204), f"csrf fetch failed: {resp2.text}"
    csrf_token = resp2.headers.get("X-CSRF-Token")
    assert csrf_token, "Missing X-CSRF-Token header"
    return client, csrf_token


class TestProjectCreationEdgeCases:
    def test_create_project_minimal(self):
        client, csrf = build_client_and_csrf()
        payload = {"name": "Edge Minimal"}
        resp = client.post(
            "/api/v1/projects/",
            json=payload,
            headers={"X-CSRF-Token": csrf},
        )
        assert resp.status_code in (200, 201)
        data = resp.json()
        assert data["name"] == "Edge Minimal"
        assert "id" in data

    def test_create_project_long_name_description(self):
        client, csrf = build_client_and_csrf()
        long_name = "N" * 180
        long_desc = "D" * 480
        payload = {"name": long_name, "description": long_desc}
        resp = client.post(
            "/api/v1/projects/",
            json=payload,
            headers={"X-CSRF-Token": csrf},
        )
        assert resp.status_code in (200, 201)
        data = resp.json()
        assert data["name"] == long_name
        assert data.get("description") == long_desc

    def test_create_project_invalid_types(self):
        client, csrf = build_client_and_csrf()
        payload = {"name": 123, "description": {"oops": True}}
        resp = client.post(
            "/api/v1/projects/",
            json=payload,
            headers={"X-CSRF-Token": csrf},
        )
        assert resp.status_code in (400, 422)

    def test_create_project_with_langextract_config(self):
        client, csrf = build_client_and_csrf()
        payload = {
            "name": "Edge LLM",
            "langextract_enabled": True,
            "langextract_provider": "openrouter",
            "langextract_model": "openrouter/deepseek-chat",
            "langextract_estimated_cost_per_1k": 0.52,
        }
        resp = client.post(
            "/api/v1/projects/",
            json=payload,
            headers={"X-CSRF-Token": csrf},
        )
        assert resp.status_code in (200, 201)
        data = resp.json()
        assert data["name"] == "Edge LLM"
        assert data.get("langextract_provider") in ("openrouter", "disabled")

    def test_create_project_with_domains_simplified(self):
        client, csrf = build_client_and_csrf()
        payload = {
            "process_documents": True,
            "enable_attachment_download": False,
            "langextract_enabled": False,
        }
        domains = ["example.com", "https://second.example.com/path"]
        resp = client.post(
            "/api/v1/projects/create-with-domains",
            json={"project_in": payload, "domains": domains},
            headers={"X-CSRF-Token": csrf},
        )
        assert resp.status_code in (200, 201)
        data = resp.json()
        assert "id" in data
        assert data.get("process_documents") is True
        assert data.get("enable_attachment_download") is False


