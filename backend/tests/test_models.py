"""
Tests for database models
"""
import pytest
from sqlmodel import Session
from datetime import datetime

from app.models.user import User
from app.models.project import Project
from app.models.entities import CanonicalEntity, ExtractedEntity
from app.models.library import StarredItem
from app.models.plans import UserPlan
from app.core.security import get_password_hash


class TestUserModel:
    """Test User model functionality."""

    def test_create_user(self, session: Session):
        """Test user creation with valid data."""
        user = User(
            email="test@example.com",
            hashed_password=get_password_hash("password123"),
            full_name="Test User"
        )
        session.add(user)
        session.commit()
        session.refresh(user)

        assert user.id is not None
        assert user.email == "test@example.com"
        assert user.full_name == "Test User"
        assert user.is_active is True
        assert user.is_verified is False
        assert user.created_at is not None

    def test_user_email_uniqueness(self, session: Session):
        """Test that email must be unique."""
        user1 = User(
            email="unique@example.com",
            hashed_password=get_password_hash("password123"),
            full_name="User One"
        )
        user2 = User(
            email="unique@example.com",
            hashed_password=get_password_hash("password456"),
            full_name="User Two"
        )
        
        session.add(user1)
        session.commit()
        
        session.add(user2)
        with pytest.raises(Exception):  # SQLIntegrityError
            session.commit()

    def test_user_password_hashing(self, session: Session):
        """Test that password is properly hashed."""
        password = "plaintext_password"
        user = User(
            email="hash@example.com",
            hashed_password=get_password_hash(password),
            full_name="Hash User"
        )
        session.add(user)
        session.commit()

        # Password should be hashed, not stored as plaintext
        assert user.hashed_password != password
        assert len(user.hashed_password) > 50  # Bcrypt hashes are longer


class TestProjectModel:
    """Test Project model functionality."""

    def test_create_project(self, session: Session, test_user: User):
        """Test project creation with valid data."""
        project = Project(
            name="Test Project",
            description="A test project for validation",
            owner_id=test_user.id,
            config={"scraping_interval": 3600}
        )
        session.add(project)
        session.commit()
        session.refresh(project)

        assert project.id is not None
        assert project.name == "Test Project"
        assert project.description == "A test project for validation"
        assert project.owner_id == test_user.id
        assert project.config == {"scraping_interval": 3600}
        assert project.is_active is True
        assert project.created_at is not None

    def test_project_user_relationship(self, session: Session, test_user: User):
        """Test project-user relationship."""
        project = Project(
            name="Relationship Test",
            owner_id=test_user.id
        )
        session.add(project)
        session.commit()
        session.refresh(project)

        # Test that we can access the owner through relationship
        assert project.owner_id == test_user.id

    def test_project_config_json(self, session: Session, test_user: User):
        """Test project config JSON field."""
        config_data = {
            "urls": ["https://example.com"],
            "schedule": "0 */6 * * *",
            "filters": {
                "include": ["article", "blog"],
                "exclude": ["ads"]
            }
        }
        
        project = Project(
            name="Config Test",
            owner_id=test_user.id,
            config=config_data
        )
        session.add(project)
        session.commit()
        session.refresh(project)

        assert project.config == config_data
        assert project.config["urls"] == ["https://example.com"]
        assert project.config["filters"]["include"] == ["article", "blog"]


class TestCanonicalEntityModel:
    """Test CanonicalEntity model functionality."""

    def test_create_canonical_entity(self, session: Session):
        """Test canonical entity creation with valid data."""
        entity = CanonicalEntity(
            entity_type="organization",
            primary_name="Test Company",
            normalized_name="test company",
            attributes={"industry": "technology"},
            confidence_score=0.95
        )
        session.add(entity)
        session.commit()
        session.refresh(entity)

        assert entity.id is not None
        assert entity.primary_name == "Test Company"
        assert entity.entity_type == "organization"
        assert entity.confidence_score == 0.95
        assert entity.attributes == {"industry": "technology"}
        assert entity.created_at is not None

    def test_entity_confidence_validation(self, session: Session):
        """Test entity confidence score validation."""
        # Test confidence range validation
        entity = CanonicalEntity(
            entity_type="person",
            primary_name="Test Person",
            normalized_name="test person",
            confidence_score=1.5  # Invalid: > 1.0
        )
        session.add(entity)
        
        # This should raise a validation error
        with pytest.raises(Exception):
            session.commit()


class TestStarredItemModel:
    """Test StarredItem model functionality."""

    def test_create_starred_item(self, session: Session, test_user: User, test_project: Project):
        """Test starred item creation."""
        item = StarredItem(
            user_id=test_user.id,
            item_type="project",
            item_id=test_project.id,
            project_id=test_project.id,
            personal_note="This is a test starred project",
            tags=["important", "test"]
        )
        session.add(item)
        session.commit()
        session.refresh(item)

        assert item.id is not None
        assert item.user_id == test_user.id
        assert item.item_type == "project"
        assert item.item_id == test_project.id
        assert item.personal_note == "This is a test starred project"
        assert "important" in item.tags
        assert item.created_at is not None

    def test_starred_item_uniqueness(self, session: Session, test_user: User, test_project: Project):
        """Test starred item uniqueness constraint."""
        item1 = StarredItem(
            user_id=test_user.id,
            item_type="project",
            item_id=test_project.id,
            project_id=test_project.id
        )
        item2 = StarredItem(
            user_id=test_user.id,
            item_type="project",
            item_id=test_project.id,
            project_id=test_project.id
        )
        
        session.add(item1)
        session.commit()
        
        session.add(item2)
        # This should raise an integrity error due to unique constraint
        with pytest.raises(Exception):
            session.commit()


class TestUserPlanModel:
    """Test UserPlan model functionality."""

    def test_create_user_plan(self, session: Session, test_user: User):
        """Test user plan creation."""
        user_plan = UserPlan(
            user_id=test_user.id,
            tier="flash",
            max_pages_per_minute=20,
            max_concurrent_jobs=2,
            api_access=True
        )
        session.add(user_plan)
        session.commit()
        session.refresh(user_plan)

        assert user_plan.id is not None
        assert user_plan.user_id == test_user.id
        assert user_plan.tier == "flash"
        assert user_plan.max_pages_per_minute == 20
        assert user_plan.max_concurrent_jobs == 2
        assert user_plan.api_access is True
        assert user_plan.started_at is not None

    def test_plan_tier_validation(self, session: Session, test_user: User):
        """Test plan tier validation."""
        valid_tiers = ["spark", "flash", "lightning", "unlimited"]
        
        for tier in valid_tiers:
            user_plan = UserPlan(
                user_id=test_user.id + len(valid_tiers),  # Different user ID to avoid unique constraint
                tier=tier
            )
            session.add(user_plan)
            session.commit()
            session.refresh(user_plan)
            assert user_plan.tier == tier
            
    def test_plan_default_values(self, session: Session, test_user: User):
        """Test plan default values."""
        user_plan = UserPlan(
            user_id=test_user.id
        )
        session.add(user_plan)
        session.commit()
        session.refresh(user_plan)

        assert user_plan.tier == "spark"  # Default tier
        assert user_plan.max_pages_per_minute == 10  # Default limit
        assert user_plan.max_concurrent_jobs == 1  # Default limit
        assert user_plan.is_active is True
        assert user_plan.priority_processing is False