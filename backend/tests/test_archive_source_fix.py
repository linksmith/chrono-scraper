"""
Test suite for archive source fix - verifies enum handling and persistence.

This test ensures that the archive source enum mismatch between frontend 
TypeScript and backend Python has been resolved.
"""
import pytest
from sqlmodel import Session, select
from app.models.project import Project, ArchiveSource
from app.schemas.project import ProjectCreate, ArchiveConfig
from app.core.database import get_db
from app.crud.project import project as project_crud
from tests.utils import TestUser, create_random_user
from app.models.user import User


class TestArchiveSourceFix:
    """Test archive source enum handling and database persistence."""

    @pytest.mark.asyncio
    async def test_archive_source_enum_values(self, db: Session):
        """Test that ArchiveSource enum has correct values matching frontend."""
        # Verify enum values match frontend TypeScript
        assert ArchiveSource.WAYBACK_MACHINE.value == "wayback"
        assert ArchiveSource.COMMON_CRAWL.value == "commoncrawl"
        assert ArchiveSource.HYBRID.value == "hybrid"
        
        # Verify all expected values are present
        expected_values = {"wayback", "commoncrawl", "hybrid"}
        actual_values = {source.value for source in ArchiveSource}
        assert actual_values == expected_values

    @pytest.mark.asyncio
    async def test_create_project_with_wayback_machine(self, db: Session, test_user: TestUser):
        """Test creating project with Wayback Machine archive source."""
        project_data = ProjectCreate(
            name="Test Wayback Project",
            description="Testing wayback machine",
            archive_source=ArchiveSource.WAYBACK_MACHINE,
            fallback_enabled=True,
            archive_config=ArchiveConfig()
        )
        
        # Create project
        project = await project_crud.create(db, obj_in=project_data, user_id=test_user.user.id)
        
        # Verify database persistence
        assert project.archive_source == ArchiveSource.WAYBACK_MACHINE
        assert project.archive_source.value == "wayback"
        assert project.fallback_enabled is True
        
        # Verify it can be retrieved from database
        db_project = await db.get(Project, project.id)
        assert db_project.archive_source == ArchiveSource.WAYBACK_MACHINE
        assert db_project.archive_source.value == "wayback"

    @pytest.mark.asyncio
    async def test_create_project_with_common_crawl(self, db: Session, test_user: TestUser):
        """Test creating project with Common Crawl archive source."""
        project_data = ProjectCreate(
            name="Test CommonCrawl Project",
            description="Testing common crawl",
            archive_source=ArchiveSource.COMMON_CRAWL,
            fallback_enabled=False,
            archive_config=ArchiveConfig()
        )
        
        # Create project
        project = await project_crud.create(db, obj_in=project_data, user_id=test_user.user.id)
        
        # Verify database persistence
        assert project.archive_source == ArchiveSource.COMMON_CRAWL
        assert project.archive_source.value == "commoncrawl"
        assert project.fallback_enabled is False
        
        # Verify it can be retrieved from database
        db_project = await db.get(Project, project.id)
        assert db_project.archive_source == ArchiveSource.COMMON_CRAWL
        assert db_project.archive_source.value == "commoncrawl"

    @pytest.mark.asyncio
    async def test_create_project_with_hybrid(self, db: Session, test_user: TestUser):
        """Test creating project with Hybrid archive source."""
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
        
        # Create project
        project = await project_crud.create(db, obj_in=project_data, user_id=test_user.user.id)
        
        # Verify database persistence
        assert project.archive_source == ArchiveSource.HYBRID
        assert project.archive_source.value == "hybrid"
        assert project.fallback_enabled is True
        assert project.archive_config is not None
        assert project.archive_config["fallback_strategy"] == "sequential"
        assert project.archive_config["circuit_breaker_threshold"] == 5

    @pytest.mark.asyncio
    async def test_archive_source_string_validation(self, db: Session, test_user: TestUser):
        """Test that string values are properly converted to enum."""
        # Create project with string value (simulating API input)
        project = Project(
            name="String Test Project",
            description="Testing string conversion",
            user_id=test_user.user.id,
            archive_source="commoncrawl"  # String input
        )
        
        # Add to database
        db.add(project)
        await db.commit()
        await db.refresh(project)
        
        # Verify it's converted to enum
        assert isinstance(project.archive_source, ArchiveSource)
        assert project.archive_source == ArchiveSource.COMMON_CRAWL
        assert project.archive_source.value == "commoncrawl"

    @pytest.mark.asyncio
    async def test_invalid_archive_source_defaults_to_wayback(self, db: Session, test_user: TestUser):
        """Test that invalid archive source values default to wayback machine."""
        # Create project with invalid string value
        project = Project(
            name="Invalid Test Project",
            description="Testing invalid value handling",
            user_id=test_user.user.id,
            archive_source="invalid_source"  # Invalid input
        )
        
        # Add to database
        db.add(project)
        await db.commit()
        await db.refresh(project)
        
        # Verify it defaults to wayback machine
        assert project.archive_source == ArchiveSource.WAYBACK_MACHINE
        assert project.archive_source.value == "wayback"

    @pytest.mark.asyncio
    async def test_archive_source_serialization(self, db: Session, test_user: TestUser):
        """Test that archive source is properly serialized in API responses."""
        # Create project with Common Crawl
        project_data = ProjectCreate(
            name="Serialization Test",
            description="Testing serialization",
            archive_source=ArchiveSource.COMMON_CRAWL
        )
        
        project = await project_crud.create(db, obj_in=project_data, user_id=test_user.user.id)
        
        # Test serialization using the model's dict method
        project_dict = project.model_dump()
        
        # Verify archive_source is serialized as string
        assert project_dict["archive_source"] == "commoncrawl"
        assert isinstance(project_dict["archive_source"], str)

    @pytest.mark.asyncio
    async def test_all_archive_sources_create_successfully(self, db: Session, test_user: TestUser):
        """Test that all archive source values can be used to create projects."""
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
            
            project = await project_crud.create(db, obj_in=project_data, user_id=test_user.user.id)
            
            # Verify correct storage and retrieval
            assert project.archive_source == source_enum
            assert project.archive_source.value == source_string
            
            # Verify database roundtrip
            db_project = await db.get(Project, project.id)
            assert db_project.archive_source == source_enum
            assert db_project.archive_source.value == source_string

    @pytest.mark.asyncio
    async def test_archive_config_with_different_sources(self, db: Session, test_user: TestUser):
        """Test that archive_config is properly stored for different archive sources."""
        test_config = {
            "fallback_strategy": "parallel",
            "circuit_breaker_threshold": 3,
            "fallback_delay": 2.5,
            "recovery_time": 300
        }
        
        # Test config storage for each archive source
        for archive_source in ArchiveSource:
            project_data = ProjectCreate(
                name=f"Config Test {archive_source.value}",
                description="Testing config storage",
                archive_source=archive_source,
                archive_config=test_config
            )
            
            project = await project_crud.create(db, obj_in=project_data, user_id=test_user.user.id)
            
            # Verify config is stored correctly
            assert project.archive_config == test_config
            assert project.archive_config["fallback_strategy"] == "parallel"
            assert project.archive_config["circuit_breaker_threshold"] == 3


@pytest.fixture
async def test_user(db: Session) -> TestUser:
    """Create a test user for the tests."""
    return await create_random_user(db)