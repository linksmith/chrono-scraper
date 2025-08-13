"""
Tests for service layer functionality
"""
import pytest
from unittest.mock import Mock, patch, AsyncMock
from sqlmodel import Session

from app.services import auth
from app.services.entity_extraction import EntityExtractionService
from app.services.content_extraction import ContentExtractionService
from app.services.library_service import LibraryService
from app.models.user import User
from app.models.project import Project
from app.models.entities import CanonicalEntity, ExtractedEntity
from app.models.library import StarredItem


class TestSecurityFunctions:
    """Test security and authentication functions."""

    def test_create_access_token(self):
        """Test access token creation."""
        from app.core.security import create_access_token
        
        token = create_access_token(subject="user@example.com")
        
        assert token is not None
        assert isinstance(token, str)
        assert len(token) > 20

    def test_password_hashing(self):
        """Test password hashing and verification."""
        from app.core.security import get_password_hash, verify_password
        
        password = "testpassword123"
        hashed = get_password_hash(password)
        
        assert hashed != password
        assert len(hashed) > 50  # Bcrypt hashes are longer
        assert verify_password(password, hashed) is True
        assert verify_password("wrongpassword", hashed) is False

    @pytest.mark.asyncio
    async def test_create_user_function(self):
        """Test user creation function."""
        # This is a basic test for the auth service function structure
        # In a real test, you'd need proper database session setup
        from app.models.user import UserCreate
        
        user_data = UserCreate(
            email="test@example.com",
            password="testpassword123",
            full_name="Test User"
        )
        
        # Test that UserCreate model validates correctly
        assert user_data.email == "test@example.com"
        assert user_data.full_name == "Test User"


class TestEntityExtractionService:
    """Test entity extraction service functionality."""

    @pytest.fixture
    def entity_service(self):
        """Create entity extraction service instance."""
        return EntityExtractionService()

    def test_entity_service_initialization(self, entity_service):
        """Test that entity extraction service can be initialized."""
        assert entity_service is not None
        assert entity_service.extraction_patterns is not None
        assert entity_service.confidence_threshold == 0.7


class TestContentExtractionService:
    """Test content extraction service functionality."""

    @pytest.fixture
    def content_service(self):
        """Create content extraction service instance."""
        return ContentExtractionService()

    def test_content_service_initialization(self, content_service):
        """Test that content extraction service can be initialized."""
        assert content_service is not None


class TestLibraryService:
    """Test library service functionality."""

    @pytest.fixture
    def library_service(self):
        """Create library service instance."""
        return LibraryService()

    def test_library_service_initialization(self, library_service):
        """Test that library service can be initialized."""
        assert library_service is not None
        
    def test_starred_item_model_creation(self, session: Session, test_user: User, test_project: Project):
        """Test creating starred items using the StarredItem model."""
        starred_item = StarredItem(
            user_id=test_user.id,
            item_type="project",
            item_id=test_project.id,
            project_id=test_project.id,
            personal_note="Test starred project"
        )
        session.add(starred_item)
        session.commit()
        session.refresh(starred_item)
        
        assert starred_item.id is not None
        assert starred_item.user_id == test_user.id
        assert starred_item.item_type == "project"
        assert starred_item.personal_note == "Test starred project"