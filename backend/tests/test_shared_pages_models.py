"""
Test suite for shared pages architecture models and database schema validation
"""
import pytest
import uuid
from datetime import datetime, timezone
from typing import List, Dict, Any
from sqlmodel import Session, select
from sqlalchemy.exc import IntegrityError
import asyncio

from app.models.shared_pages import (
    PageV2, ProjectPage, CDXPageRegistry,
    ScrapeStatus, PageReviewStatus, PageCategory, PagePriority,
    PageV2Create, PageV2Read, ProjectPageCreate, ProjectPageRead,
    CDXPageRegistryCreate, ProcessingStats
)
from app.models.project import Project, Domain
from app.models.user import User
from app.core.security import get_password_hash


class TestSharedPagesModels:
    """Test shared pages model creation, validation, and relationships"""
    
    def test_pagev2_creation(self, session: Session):
        """Test PageV2 model creation with required fields"""
        page = PageV2(
            url="https://example.com/test-page",
            unix_timestamp=1234567890,
            wayback_url="https://web.archive.org/web/1234567890if_/https://example.com/test-page",
            content="<html><body>Test content</body></html>",
            markdown_content="# Test Content\n\nThis is test content.",
            title="Test Page",
            extracted_title="Test Page Extracted",
            extracted_text="Test content extracted",
            quality_score=0.85,
            word_count=100,
            character_count=500,
            content_type="text/html",
            processed=True,
            indexed=False
        )
        
        session.add(page)
        session.commit()
        session.refresh(page)
        
        assert page.id is not None
        assert isinstance(page.id, uuid.UUID)
        assert page.url == "https://example.com/test-page"
        assert page.unix_timestamp == 1234567890
        assert page.quality_score == 0.85
        assert page.processed is True
        assert page.indexed is False
        assert page.created_at is not None
        assert page.updated_at is not None
    
    def test_pagev2_unique_constraint(self, session: Session):
        """Test unique constraint on URL and timestamp"""
        # Create first page
        page1 = PageV2(
            url="https://example.com/duplicate",
            unix_timestamp=1234567890
        )
        session.add(page1)
        session.commit()
        
        # Try to create duplicate - should fail
        page2 = PageV2(
            url="https://example.com/duplicate",
            unix_timestamp=1234567890
        )
        session.add(page2)
        
        with pytest.raises(IntegrityError):
            session.commit()
    
    def test_pagev2_optional_fields(self, session: Session):
        """Test PageV2 creation with minimal required fields"""
        page = PageV2(
            url="https://example.com/minimal",
            unix_timestamp=1234567890
        )
        
        session.add(page)
        session.commit()
        session.refresh(page)
        
        assert page.id is not None
        assert page.content is None
        assert page.title is None
        assert page.quality_score is None
        assert page.processed is False
        assert page.indexed is False
    
    def test_project_page_creation(self, session: Session):
        """Test ProjectPage association creation"""
        # Create test user
        user = User(
            email="test@example.com",
            hashed_password=get_password_hash("testpass"),
            full_name="Test User",
            is_active=True,
            is_verified=True
        )
        session.add(user)
        session.commit()
        
        # Create test project
        project = Project(
            name="Test Project",
            description="Test project for associations",
            user_id=user.id
        )
        session.add(project)
        session.commit()
        
        # Create test page
        page = PageV2(
            url="https://example.com/association-test",
            unix_timestamp=1234567890
        )
        session.add(page)
        session.commit()
        
        # Create association
        association = ProjectPage(
            project_id=project.id,
            page_id=page.id,
            review_status=PageReviewStatus.PENDING,
            page_category=PageCategory.RESEARCH,
            priority_level=PagePriority.HIGH,
            tags=["test", "research"],
            notes="Test association notes",
            is_starred=True,
            added_by=user.id
        )
        
        session.add(association)
        session.commit()
        session.refresh(association)
        
        assert association.id is not None
        assert association.project_id == project.id
        assert association.page_id == page.id
        assert association.review_status == PageReviewStatus.PENDING
        assert association.page_category == PageCategory.RESEARCH
        assert association.priority_level == PagePriority.HIGH
        assert association.tags == ["test", "research"]
        assert association.is_starred is True
        assert association.added_by == user.id
        assert association.added_at is not None
    
    def test_project_page_unique_constraint(self, session: Session):
        """Test unique constraint on project_id and page_id"""
        # Create test data
        user = User(
            email="test2@example.com",
            hashed_password=get_password_hash("testpass"),
            full_name="Test User 2",
            is_active=True,
            is_verified=True
        )
        session.add(user)
        session.commit()
        
        project = Project(
            name="Test Project 2",
            user_id=user.id
        )
        session.add(project)
        session.commit()
        
        page = PageV2(
            url="https://example.com/unique-test",
            unix_timestamp=1234567890
        )
        session.add(page)
        session.commit()
        
        # Create first association
        association1 = ProjectPage(
            project_id=project.id,
            page_id=page.id
        )
        session.add(association1)
        session.commit()
        
        # Try to create duplicate - should fail
        association2 = ProjectPage(
            project_id=project.id,
            page_id=page.id
        )
        session.add(association2)
        
        with pytest.raises(IntegrityError):
            session.commit()
    
    def test_cdx_page_registry_creation(self, session: Session):
        """Test CDXPageRegistry model creation"""
        # Create test page
        page = PageV2(
            url="https://example.com/cdx-test",
            unix_timestamp=1234567890
        )
        session.add(page)
        session.commit()
        
        # Create test project
        user = User(
            email="cdx@example.com",
            hashed_password=get_password_hash("testpass"),
            full_name="CDX User",
            is_active=True,
            is_verified=True
        )
        session.add(user)
        session.commit()
        
        project = Project(
            name="CDX Project",
            user_id=user.id
        )
        session.add(project)
        session.commit()
        
        # Create registry entry
        registry = CDXPageRegistry(
            url="https://example.com/cdx-test",
            unix_timestamp=1234567890,
            scrape_status=ScrapeStatus.PENDING,
            page_id=page.id,
            created_by_project_id=project.id
        )
        
        session.add(registry)
        session.commit()
        session.refresh(registry)
        
        assert registry.id is not None
        assert registry.url == "https://example.com/cdx-test"
        assert registry.unix_timestamp == 1234567890
        assert registry.scrape_status == ScrapeStatus.PENDING
        assert registry.page_id == page.id
        assert registry.created_by_project_id == project.id
        assert registry.first_seen_at is not None
    
    def test_cdx_registry_unique_constraint(self, session: Session):
        """Test unique constraint on CDX registry URL and timestamp"""
        # Create first registry entry
        registry1 = CDXPageRegistry(
            url="https://example.com/cdx-duplicate",
            unix_timestamp=1234567890,
            scrape_status=ScrapeStatus.PENDING
        )
        session.add(registry1)
        session.commit()
        
        # Try to create duplicate - should fail
        registry2 = CDXPageRegistry(
            url="https://example.com/cdx-duplicate",
            unix_timestamp=1234567890,
            scrape_status=ScrapeStatus.IN_PROGRESS
        )
        session.add(registry2)
        
        with pytest.raises(IntegrityError):
            session.commit()


class TestSharedPagesRelationships:
    """Test relationships between shared pages models"""
    
    def test_page_project_associations_relationship(self, session: Session):
        """Test PageV2 to ProjectPage relationship"""
        # Create test data
        user = User(
            email="rel@example.com",
            hashed_password=get_password_hash("testpass"),
            full_name="Relationship User",
            is_active=True,
            is_verified=True
        )
        session.add(user)
        session.commit()
        
        project = Project(
            name="Relationship Project",
            user_id=user.id
        )
        session.add(project)
        session.commit()
        
        page = PageV2(
            url="https://example.com/relationship-test",
            unix_timestamp=1234567890
        )
        session.add(page)
        session.commit()
        
        # Create association
        association = ProjectPage(
            project_id=project.id,
            page_id=page.id,
            added_by=user.id
        )
        session.add(association)
        session.commit()
        
        # Test relationship access
        session.refresh(page)
        assert len(page.project_associations) == 1
        assert page.project_associations[0].project_id == project.id
        
        # Test reverse relationship
        session.refresh(association)
        assert association.page.id == page.id
        assert association.project.id == project.id
    
    def test_multiple_project_associations(self, session: Session):
        """Test page shared across multiple projects"""
        # Create test users and projects
        user1 = User(
            email="multi1@example.com",
            hashed_password=get_password_hash("testpass"),
            full_name="Multi User 1",
            is_active=True,
            is_verified=True
        )
        user2 = User(
            email="multi2@example.com",
            hashed_password=get_password_hash("testpass"),
            full_name="Multi User 2",
            is_active=True,
            is_verified=True
        )
        session.add_all([user1, user2])
        session.commit()
        
        project1 = Project(
            name="Multi Project 1",
            user_id=user1.id
        )
        project2 = Project(
            name="Multi Project 2",
            user_id=user2.id
        )
        session.add_all([project1, project2])
        session.commit()
        
        # Create shared page
        page = PageV2(
            url="https://example.com/shared-page",
            unix_timestamp=1234567890,
            content="Shared content"
        )
        session.add(page)
        session.commit()
        
        # Create associations to both projects
        association1 = ProjectPage(
            project_id=project1.id,
            page_id=page.id,
            tags=["project1"],
            added_by=user1.id
        )
        association2 = ProjectPage(
            project_id=project2.id,
            page_id=page.id,
            tags=["project2"],
            added_by=user2.id
        )
        session.add_all([association1, association2])
        session.commit()
        
        # Verify page is shared across projects
        session.refresh(page)
        assert len(page.project_associations) == 2
        
        project_ids = [assoc.project_id for assoc in page.project_associations]
        assert project1.id in project_ids
        assert project2.id in project_ids
    
    def test_cdx_registry_page_relationship(self, session: Session):
        """Test CDXPageRegistry to PageV2 relationship"""
        # Create page
        page = PageV2(
            url="https://example.com/cdx-rel-test",
            unix_timestamp=1234567890
        )
        session.add(page)
        session.commit()
        
        # Create registry entries
        registry1 = CDXPageRegistry(
            url="https://example.com/cdx-rel-test",
            unix_timestamp=1234567890,
            scrape_status=ScrapeStatus.COMPLETED,
            page_id=page.id
        )
        registry2 = CDXPageRegistry(
            url="https://example.com/cdx-rel-test",
            unix_timestamp=1234567891,
            scrape_status=ScrapeStatus.PENDING
        )
        session.add_all([registry1, registry2])
        session.commit()
        
        # Test relationships
        session.refresh(page)
        assert len(page.cdx_registry_entries) == 1  # Only registry1 linked
        assert page.cdx_registry_entries[0].scrape_status == ScrapeStatus.COMPLETED
        
        session.refresh(registry1)
        assert registry1.page.id == page.id
        
        session.refresh(registry2)
        assert registry2.page is None


class TestSharedPagesSchemas:
    """Test Pydantic schemas for shared pages"""
    
    def test_pagev2_create_schema(self):
        """Test PageV2Create schema validation"""
        data = {
            "url": "https://example.com/schema-test",
            "unix_timestamp": 1234567890,
            "content": "Test content",
            "title": "Test Title",
            "quality_score": 0.9
        }
        
        schema = PageV2Create(**data)
        assert schema.url == "https://example.com/schema-test"
        assert schema.unix_timestamp == 1234567890
        assert schema.quality_score == 0.9
    
    def test_project_page_create_schema(self):
        """Test ProjectPageCreate schema validation"""
        page_id = uuid.uuid4()
        data = {
            "project_id": 1,
            "page_id": page_id,
            "domain_id": 2,
            "review_status": PageReviewStatus.RELEVANT,
            "tags": ["test", "schema"],
            "is_starred": True,
            "added_by": 1
        }
        
        schema = ProjectPageCreate(**data)
        assert schema.project_id == 1
        assert schema.page_id == page_id
        assert schema.domain_id == 2
        assert schema.review_status == PageReviewStatus.RELEVANT
        assert schema.tags == ["test", "schema"]
        assert schema.is_starred is True
    
    def test_processing_stats_schema(self):
        """Test ProcessingStats schema"""
        stats = ProcessingStats(
            pages_linked=10,
            pages_to_scrape=20,
            pages_already_processing=5,
            pages_failed=2,
            total_processed=37
        )
        
        assert stats.pages_linked == 10
        assert stats.pages_to_scrape == 20
        assert stats.pages_already_processing == 5
        assert stats.pages_failed == 2
        assert stats.total_processed == 37
    
    def test_enum_validations(self):
        """Test enum field validations"""
        # Test ScrapeStatus
        assert ScrapeStatus.PENDING == "pending"
        assert ScrapeStatus.IN_PROGRESS == "in_progress"
        assert ScrapeStatus.COMPLETED == "completed"
        assert ScrapeStatus.FAILED == "failed"
        
        # Test PageReviewStatus
        assert PageReviewStatus.PENDING == "pending"
        assert PageReviewStatus.RELEVANT == "relevant"
        assert PageReviewStatus.IRRELEVANT == "irrelevant"
        assert PageReviewStatus.NEEDS_REVIEW == "needs_review"
        assert PageReviewStatus.DUPLICATE == "duplicate"
        
        # Test PageCategory
        assert PageCategory.GOVERNMENT == "government"
        assert PageCategory.RESEARCH == "research"
        assert PageCategory.NEWS == "news"
        
        # Test PagePriority
        assert PagePriority.LOW == "low"
        assert PagePriority.MEDIUM == "medium"
        assert PagePriority.HIGH == "high"
        assert PagePriority.CRITICAL == "critical"


class TestSharedPagesDataIntegrity:
    """Test data integrity and constraints"""
    
    def test_page_deletion_cascade(self, session: Session):
        """Test that page deletion cascades properly"""
        # Create test data
        user = User(
            email="cascade@example.com",
            hashed_password=get_password_hash("testpass"),
            full_name="Cascade User",
            is_active=True,
            is_verified=True
        )
        session.add(user)
        session.commit()
        
        project = Project(
            name="Cascade Project",
            user_id=user.id
        )
        session.add(project)
        session.commit()
        
        page = PageV2(
            url="https://example.com/cascade-test",
            unix_timestamp=1234567890
        )
        session.add(page)
        session.commit()
        
        # Create association and registry entry
        association = ProjectPage(
            project_id=project.id,
            page_id=page.id
        )
        registry = CDXPageRegistry(
            url="https://example.com/cascade-test",
            unix_timestamp=1234567890,
            scrape_status=ScrapeStatus.COMPLETED,
            page_id=page.id
        )
        session.add_all([association, registry])
        session.commit()
        
        # Get IDs for verification
        page_id = page.id
        association_id = association.id
        registry_id = registry.id
        
        # Delete the page
        session.delete(page)
        session.commit()
        
        # Verify cascade deletion
        remaining_association = session.get(ProjectPage, association_id)
        assert remaining_association is None
        
        # Registry should still exist but with null page_id
        remaining_registry = session.get(CDXPageRegistry, registry_id)
        assert remaining_registry is not None
        # Note: Registry doesn't cascade delete, it just nullifies page_id
    
    def test_invalid_enum_values(self, session: Session):
        """Test that invalid enum values are rejected"""
        with pytest.raises(ValueError):
            ProjectPage(
                project_id=1,
                page_id=uuid.uuid4(),
                review_status="invalid_status"  # Invalid enum value
            )
        
        with pytest.raises(ValueError):
            CDXPageRegistry(
                url="https://example.com/invalid",
                unix_timestamp=1234567890,
                scrape_status="invalid_scrape_status"  # Invalid enum value
            )
    
    def test_quality_score_constraints(self, session: Session):
        """Test quality score numeric constraints"""
        # Valid quality score
        page = PageV2(
            url="https://example.com/quality-test",
            unix_timestamp=1234567890,
            quality_score=0.85
        )
        session.add(page)
        session.commit()
        
        # Quality scores outside 0-1 range should still be allowed
        # (business logic should handle validation)
        page2 = PageV2(
            url="https://example.com/quality-test-2",
            unix_timestamp=1234567891,
            quality_score=1.5
        )
        session.add(page2)
        session.commit()  # Should not fail at DB level
    
    def test_timestamp_data_types(self, session: Session):
        """Test timestamp field data types and constraints"""
        page = PageV2(
            url="https://example.com/timestamp-test",
            unix_timestamp=1234567890123456,  # Large timestamp
            capture_date=datetime.now(timezone.utc),
            published_date=datetime.now(timezone.utc)
        )
        
        session.add(page)
        session.commit()
        session.refresh(page)
        
        assert isinstance(page.unix_timestamp, int)
        assert isinstance(page.capture_date, datetime)
        assert isinstance(page.published_date, datetime)
        assert page.created_at is not None
        assert page.updated_at is not None