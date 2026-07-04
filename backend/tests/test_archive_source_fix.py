"""
Test suite for archive source fix - verifies enum handling and persistence.
"""
import pytest
from sqlmodel import SQLModel
from app.models.project import Project, ArchiveSource
from app.models.user import User
from app.schemas.project import ProjectCreate, ArchiveConfig
from app.services.projects import ProjectService
from tests.conftest import AsyncSessionLocal, async_engine
from app.core.security import get_password_hash

# Import all models to ensure they're registered with SQLModel metadata
from app.models import shared_pages, scraping, entities, library, audit_log, rbac


async def setup_test_db():
    """Create tables for test."""
    async with async_engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.drop_all)
        await conn.run_sync(SQLModel.metadata.create_all)


async def teardown_test_db():
    """Drop tables after test."""
    async with async_engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.drop_all)


async def create_test_user(session) -> User:
    """Helper function to create a test user with unique email."""
    import time
    import random
    # Use timestamp + random to ensure unique emails across all test runs
    unique_id = f"{int(time.time() * 1000)}{random.randint(1000, 9999)}"
    user = User(
        email=f"archivetest_{unique_id}@example.com",
        hashed_password=get_password_hash("TestPassword123!"),
        full_name="Archive Test User",
        is_active=True,
        is_verified=True,
        approval_status="approved",
        data_handling_agreement=True,
        ethics_agreement=True,
        research_interests="Archive testing",
        research_purpose="Testing archive functionality",
        expected_usage="Archive testing"
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


def assert_archive_source(actual_value, expected_enum: ArchiveSource):
    """Helper to assert archive source matches expected value (handles both string and enum)."""
    if isinstance(actual_value, str):
        assert actual_value == expected_enum.value
    else:
        assert actual_value == expected_enum
        assert actual_value.value == expected_enum.value


@pytest.mark.asyncio
async def test_archive_source_enum_values():
    """Test that ArchiveSource enum has correct values matching frontend."""
    assert ArchiveSource.WAYBACK_MACHINE.value == "wayback"
    assert ArchiveSource.COMMON_CRAWL.value == "commoncrawl"
    assert ArchiveSource.HYBRID.value == "hybrid"

    expected_values = {"wayback", "commoncrawl", "hybrid"}
    actual_values = {source.value for source in ArchiveSource}
    assert actual_values == expected_values


@pytest.mark.asyncio
async def test_create_project_with_wayback_machine():
    """Test creating project with Wayback Machine archive source."""
    await setup_test_db()
    try:
        async with AsyncSessionLocal() as session:
            test_user = await create_test_user(session)

            project_data = ProjectCreate(
                name="Test Wayback Project",
                description="Testing wayback machine",
                archive_source=ArchiveSource.WAYBACK_MACHINE,
                fallback_enabled=True,
                archive_config=ArchiveConfig()
            )

            project = await ProjectService.create_project(session, project_create=project_data, user_id=test_user.id)

            assert_archive_source(project.archive_source, ArchiveSource.WAYBACK_MACHINE)
            assert project.fallback_enabled is True

            await session.refresh(project)
            assert_archive_source(project.archive_source, ArchiveSource.WAYBACK_MACHINE)
    finally:
        await teardown_test_db()


@pytest.mark.asyncio
async def test_create_project_with_common_crawl():
    """Test creating project with Common Crawl archive source."""
    await setup_test_db()
    try:
        async with AsyncSessionLocal() as session:
            test_user = await create_test_user(session)

            project_data = ProjectCreate(
                name="Test CommonCrawl Project",
                description="Testing common crawl",
                archive_source=ArchiveSource.COMMON_CRAWL,
                fallback_enabled=False,
                archive_config=ArchiveConfig()
            )

            project = await ProjectService.create_project(session, project_create=project_data, user_id=test_user.id)

            assert_archive_source(project.archive_source, ArchiveSource.COMMON_CRAWL)
            assert project.fallback_enabled is False

            await session.refresh(project)
            assert_archive_source(project.archive_source, ArchiveSource.COMMON_CRAWL)
    finally:
        await teardown_test_db()


@pytest.mark.asyncio
async def test_create_project_with_hybrid():
    """Test creating project with Hybrid archive source."""
    await setup_test_db()
    try:
        async with AsyncSessionLocal() as session:
            test_user = await create_test_user(session)

            project_data = ProjectCreate(
                name="Test Hybrid Project",
                description="Testing hybrid mode",
                archive_source=ArchiveSource.HYBRID,
                fallback_enabled=True,
                archive_config=ArchiveConfig(
                    fallback_strategy="sequential",
                    circuit_breaker_threshold=5,
                    fallback_delay=3.0,
                    recovery_time=600
                )
            )

            project = await ProjectService.create_project(session, project_create=project_data, user_id=test_user.id)

            assert_archive_source(project.archive_source, ArchiveSource.HYBRID)
            assert project.fallback_enabled is True
            assert project.archive_config is not None
            assert project.archive_config["fallback_strategy"] == "sequential"
            assert project.archive_config["circuit_breaker_threshold"] == 5
    finally:
        await teardown_test_db()


@pytest.mark.asyncio
async def test_archive_source_string_validation():
    """Test that string values are properly converted to enum."""
    await setup_test_db()
    try:
        async with AsyncSessionLocal() as session:
            test_user = await create_test_user(session)

            project = Project(
                name="String Test Project",
                description="Testing string conversion",
                user_id=test_user.id,
                archive_source="commoncrawl"
            )

            session.add(project)
            await session.commit()
            await session.refresh(project)

            assert_archive_source(project.archive_source, ArchiveSource.COMMON_CRAWL)
    finally:
        await teardown_test_db()


@pytest.mark.asyncio
@pytest.mark.skip(reason="Validator not applied in direct SQLModel instantiation with SQLite")
async def test_invalid_archive_source_defaults():
    """Test that invalid archive source values default to common crawl."""
    await setup_test_db()
    try:
        async with AsyncSessionLocal() as session:
            test_user = await create_test_user(session)

            project = Project(
                name="Invalid Test Project",
                description="Testing invalid value handling",
                user_id=test_user.id,
                archive_source="invalid_source"
            )

            session.add(project)
            await session.commit()
            await session.refresh(project)

            # Note: Validator defaults to COMMON_CRAWL for invalid strings
            assert_archive_source(project.archive_source, ArchiveSource.COMMON_CRAWL)
    finally:
        await teardown_test_db()


@pytest.mark.asyncio
async def test_archive_source_serialization():
    """Test that archive source is properly serialized in API responses."""
    await setup_test_db()
    try:
        async with AsyncSessionLocal() as session:
            test_user = await create_test_user(session)

            project_data = ProjectCreate(
                name="Serialization Test",
                description="Testing serialization",
                archive_source=ArchiveSource.COMMON_CRAWL
            )

            project = await ProjectService.create_project(session, project_create=project_data, user_id=test_user.id)

            project_dict = project.model_dump()

            assert project_dict["archive_source"] == "commoncrawl"
            assert isinstance(project_dict["archive_source"], str)
    finally:
        await teardown_test_db()


@pytest.mark.asyncio
async def test_all_archive_sources_create_successfully():
    """Test that all archive source values can be used to create projects."""
    await setup_test_db()
    try:
        async with AsyncSessionLocal() as session:
            test_user = await create_test_user(session)

            archive_sources = [
                ("wayback", ArchiveSource.WAYBACK_MACHINE),
                ("commoncrawl", ArchiveSource.COMMON_CRAWL),
                ("hybrid", ArchiveSource.HYBRID),
            ]

            for source_string, source_enum in archive_sources:
                project_data = ProjectCreate(
                    name=f"Test {source_string.title()} Project",
                    description=f"Testing {source_string}",
                    archive_source=source_enum
                )

                project = await ProjectService.create_project(session, project_create=project_data, user_id=test_user.id)

                assert_archive_source(project.archive_source, source_enum)

                await session.refresh(project)
                assert_archive_source(project.archive_source, source_enum)
    finally:
        await teardown_test_db()


@pytest.mark.asyncio
async def test_archive_config_with_different_sources():
    """Test that archive_config is properly stored for different archive sources."""
    await setup_test_db()
    try:
        async with AsyncSessionLocal() as session:
            test_user = await create_test_user(session)

            test_config = {
                "fallback_strategy": "parallel",
                "circuit_breaker_threshold": 3,
                "fallback_delay": 2.5,
                "recovery_time": 300
            }

            for archive_source in ArchiveSource:
                project_data = ProjectCreate(
                    name=f"Config Test {archive_source.value}",
                    description="Testing config storage",
                    archive_source=archive_source,
                    archive_config=test_config
                )

                project = await ProjectService.create_project(session, project_create=project_data, user_id=test_user.id)

                assert project.archive_config == test_config
                assert project.archive_config["fallback_strategy"] == "parallel"
                assert project.archive_config["circuit_breaker_threshold"] == 3
    finally:
        await teardown_test_db()
