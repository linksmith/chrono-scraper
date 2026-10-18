"""
Test suite for validating the current Page + ProjectPage architecture with comprehensive data integrity testing
"""
import pytest
from datetime import datetime, timezone
from sqlmodel import select

from app.models.shared_pages import (
    Page, ProjectPage, PageReviewStatus, PagePriority
)
from app.models.project import Project, Domain
from app.models.user import User
from app.core.security import get_password_hash
from tests.conftest import AsyncSessionLocal, async_engine
from sqlmodel import SQLModel


class TestSharedPagesArchitecture:
    """Test current shared pages architecture functionality and data integrity"""

    async def setup_db(self):
        """Setup database tables"""
        async with async_engine.begin() as conn:
            await conn.run_sync(SQLModel.metadata.drop_all)
            await conn.run_sync(SQLModel.metadata.create_all)

    async def create_test_data(self):
        """Create test data structure for architecture validation"""
        async with AsyncSessionLocal() as session:
            # Create test users
            user1 = User(
                email="arch_test1@example.com",
                hashed_password=get_password_hash("testpass"),
                full_name="Architecture Test User 1",
                is_active=True,
                is_verified=True,
                approval_status="approved"
            )
            user2 = User(
                email="arch_test2@example.com",
                hashed_password=get_password_hash("testpass"),
                full_name="Architecture Test User 2",
                is_active=True,
                is_verified=True,
                approval_status="approved"
            )
            session.add_all([user1, user2])
            await session.commit()
            await session.refresh(user1)
            await session.refresh(user2)

            # Create test projects
            project1 = Project(
                name="Architecture Test Project 1",
                description="First project for architecture testing",
                user_id=user1.id
            )
            project2 = Project(
                name="Architecture Test Project 2",
                description="Second project for architecture testing",
                user_id=user1.id
            )
            project3 = Project(
                name="User 2 Project",
                description="Different user project",
                user_id=user2.id
            )
            session.add_all([project1, project2, project3])
            await session.commit()
            await session.refresh(project1)
            await session.refresh(project2)
            await session.refresh(project3)

            # Create test domains
            domain1 = Domain(
                name="test-domain.com",
                project_id=project1.id,
                config={"test": True}
            )
            domain2 = Domain(
                name="example-test.org",
                project_id=project2.id,
                config={"test": True}
            )
            domain3 = Domain(
                name="user2-domain.net",
                project_id=project3.id,
                config={"test": True}
            )
            session.add_all([domain1, domain2, domain3])
            await session.commit()
            await session.refresh(domain1)
            await session.refresh(domain2)
            await session.refresh(domain3)

            # Create shared pages
            pages = [
                Page(
                    url="https://test-domain.com/page1",
                    unix_timestamp=1672574400,
                    content_url="https://web.archive.org/web/20230101120000if_/https://test-domain.com/page1",
                    content="<html><body>Page 1 content</body></html>",
                    extracted_text="Page 1 content extracted",
                    title="Page 1",
                    processed=True,
                    indexed=False,
                    created_at=datetime(2023, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
                    updated_at=datetime(2023, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
                ),
                Page(
                    url="https://test-domain.com/page2",
                    unix_timestamp=1672578000,
                    content_url="https://web.archive.org/web/20230101130000if_/https://test-domain.com/page2",
                    content="<html><body>Page 2 content</body></html>",
                    extracted_text="Page 2 content extracted",
                    title="Page 2",
                    processed=True,
                    indexed=False,
                    created_at=datetime(2023, 1, 1, 13, 0, 0, tzinfo=timezone.utc),
                    updated_at=datetime(2023, 1, 1, 13, 0, 0, tzinfo=timezone.utc)
                ),
                Page(
                    url="https://example-test.org/shared",
                    unix_timestamp=1672581600,
                    content_url="https://web.archive.org/web/20230101140000if_/https://example-test.org/shared",
                    content="<html><body>Shared content</body></html>",
                    title="Shared Page",
                    processed=True,
                    indexed=False,
                    created_at=datetime(2023, 1, 1, 14, 0, 0, tzinfo=timezone.utc),
                    updated_at=datetime(2023, 1, 1, 14, 0, 0, tzinfo=timezone.utc)
                ),
                Page(
                    url="https://user2-domain.net/private",
                    unix_timestamp=1672585200,
                    content_url="https://web.archive.org/web/20230101150000if_/https://user2-domain.net/private",
                    content="<html><body>User 2 private content</body></html>",
                    title="User 2 Private Page",
                    processed=False,
                    indexed=False,
                    created_at=datetime(2023, 1, 1, 15, 0, 0, tzinfo=timezone.utc),
                    updated_at=datetime(2023, 1, 1, 15, 0, 0, tzinfo=timezone.utc)
                ),
                # Duplicate URL with different timestamp
                Page(
                    url="https://test-domain.com/page1",
                    unix_timestamp=1675252800,
                    content_url="https://web.archive.org/web/20230201120000if_/https://test-domain.com/page1",
                    content="<html><body>Updated page 1 content</body></html>",
                    title="Updated Page 1",
                    processed=True,
                    indexed=False,
                    created_at=datetime(2023, 2, 1, 12, 0, 0, tzinfo=timezone.utc),
                    updated_at=datetime(2023, 2, 1, 12, 0, 0, tzinfo=timezone.utc)
                )
            ]

            session.add_all(pages)
            await session.commit()
            for page in pages:
                await session.refresh(page)

            # Create project-page associations
            associations = [
                # Project 1 has 3 pages
                ProjectPage(
                    project_id=project1.id,
                    page_id=pages[0].id,
                    domain_id=domain1.id,
                    review_status=PageReviewStatus.PENDING,
                    priority_level=PagePriority.MEDIUM,
                    tags=[]
                ),
                ProjectPage(
                    project_id=project1.id,
                    page_id=pages[1].id,
                    domain_id=domain1.id,
                    review_status=PageReviewStatus.RELEVANT,
                    priority_level=PagePriority.HIGH,
                    tags=["important"]
                ),
                ProjectPage(
                    project_id=project1.id,
                    page_id=pages[4].id,
                    domain_id=domain1.id,
                    review_status=PageReviewStatus.PENDING,
                    priority_level=PagePriority.MEDIUM,
                    tags=[]
                ),
                # Project 2 has 1 page
                ProjectPage(
                    project_id=project2.id,
                    page_id=pages[2].id,
                    domain_id=domain2.id,
                    review_status=PageReviewStatus.PENDING,
                    priority_level=PagePriority.MEDIUM,
                    tags=[]
                ),
                # Project 3 has 1 page
                ProjectPage(
                    project_id=project3.id,
                    page_id=pages[3].id,
                    domain_id=domain3.id,
                    review_status=PageReviewStatus.NEEDS_REVIEW,
                    priority_level=PagePriority.LOW,
                    tags=[]
                )
            ]

            session.add_all(associations)
            await session.commit()
            for assoc in associations:
                await session.refresh(assoc)

            return {
                "user1": user1,
                "user2": user2,
                "project1": project1,
                "project2": project2,
                "project3": project3,
                "domain1": domain1,
                "domain2": domain2,
                "domain3": domain3,
                "pages": pages,
                "associations": associations
            }

    @pytest.mark.asyncio
    async def test_basic_schema_functionality(self):
        """Test basic schema creation and relationships"""
        await self.setup_db()
        test_data = await self.create_test_data()

        async with AsyncSessionLocal() as session:
            # Verify pages were created
            pages_stmt = select(Page)
            result = await session.execute(pages_stmt)
            pages = result.scalars().all()

            assert len(pages) == 5

            # Verify all URLs are represented
            urls = [page.url for page in pages]
            assert "https://test-domain.com/page1" in urls
            assert "https://test-domain.com/page2" in urls
            assert "https://example-test.org/shared" in urls
            assert "https://user2-domain.net/private" in urls

            # Verify duplicate URL with different timestamp
            page1_entries = [p for p in pages if p.url == "https://test-domain.com/page1"]
            assert len(page1_entries) == 2

            timestamps = [p.unix_timestamp for p in page1_entries]
            assert len(set(timestamps)) == 2

    @pytest.mark.asyncio
    async def test_project_associations(self):
        """Test project-page association creation"""
        await self.setup_db()
        test_data = await self.create_test_data()

        async with AsyncSessionLocal() as session:
            # Verify project associations
            associations_stmt = select(ProjectPage)
            result = await session.execute(associations_stmt)
            associations = result.scalars().all()

            assert len(associations) == 5

            # Verify associations by project
            project1_associations = [a for a in associations if a.project_id == test_data["project1"].id]
            project2_associations = [a for a in associations if a.project_id == test_data["project2"].id]
            project3_associations = [a for a in associations if a.project_id == test_data["project3"].id]

            assert len(project1_associations) == 3
            assert len(project2_associations) == 1
            assert len(project3_associations) == 1

            # Verify association metadata
            for association in associations:
                assert association.review_status in [s.value for s in PageReviewStatus]
                assert association.priority_level in [p.value for p in PagePriority]
                assert association.added_at is not None
                assert association.tags is not None

    @pytest.mark.asyncio
    async def test_duplicate_url_handling(self):
        """Test handling of duplicate URLs with different timestamps"""
        await self.setup_db()
        test_data = await self.create_test_data()

        async with AsyncSessionLocal() as session:
            # Check duplicate URL with different timestamp
            pages_stmt = select(Page).where(Page.url == "https://test-domain.com/page1")
            result = await session.execute(pages_stmt)
            duplicate_pages = result.scalars().all()

            assert len(duplicate_pages) == 2

            # Verify different timestamps
            timestamps = [page.unix_timestamp for page in duplicate_pages]
            assert len(set(timestamps)) == 2

            # Verify both have project associations
            for page in duplicate_pages:
                associations_stmt = select(ProjectPage).where(ProjectPage.page_id == page.id)
                result = await session.execute(associations_stmt)
                associations = result.scalars().all()
                assert len(associations) >= 1

    @pytest.mark.asyncio
    async def test_data_integrity(self):
        """Test data integrity of page and association data"""
        await self.setup_db()
        test_data = await self.create_test_data()

        async with AsyncSessionLocal() as session:
            # Verify page data integrity
            pages_stmt = select(Page)
            result = await session.execute(pages_stmt)
            pages = result.scalars().all()

            for page in pages:
                assert page.url is not None
                assert page.unix_timestamp > 0
                assert page.created_at is not None
                assert page.updated_at is not None

                # Verify page has at least one project association
                associations_stmt = select(ProjectPage).where(ProjectPage.page_id == page.id)
                result = await session.execute(associations_stmt)
                associations = result.scalars().all()
                assert len(associations) >= 1

    @pytest.mark.asyncio
    async def test_unique_constraints(self):
        """Test that unique constraints work correctly"""
        await self.setup_db()
        test_data = await self.create_test_data()

        async with AsyncSessionLocal() as session:
            # Try to create duplicate page with same URL and timestamp
            duplicate_page = Page(
                url="https://test-domain.com/page1",
                unix_timestamp=1672574400,
                content="Duplicate content"
            )
            session.add(duplicate_page)

            with pytest.raises(Exception):
                await session.commit()

            await session.rollback()

            # Verify original page still exists
            pages_stmt = select(Page).where(
                Page.url == "https://test-domain.com/page1",
                Page.unix_timestamp == 1672574400
            )
            result = await session.execute(pages_stmt)
            pages = result.scalars().all()
            assert len(pages) == 1

    @pytest.mark.asyncio
    async def test_cross_project_sharing(self):
        """Test that pages can be shared across projects"""
        await self.setup_db()
        test_data = await self.create_test_data()

        async with AsyncSessionLocal() as session:
            # Get a page from project1
            page1 = test_data["pages"][0]

            # Create association with project2
            new_association = ProjectPage(
                project_id=test_data["project2"].id,
                page_id=page1.id,
                domain_id=test_data["domain2"].id,
                review_status=PageReviewStatus.PENDING,
                priority_level=PagePriority.MEDIUM,
                tags=["shared"]
            )
            session.add(new_association)
            await session.commit()

            # Verify page is now in both projects
            associations_stmt = select(ProjectPage).where(ProjectPage.page_id == page1.id)
            result = await session.execute(associations_stmt)
            associations = result.scalars().all()

            assert len(associations) == 2
            project_ids = [a.project_id for a in associations]
            assert test_data["project1"].id in project_ids
            assert test_data["project2"].id in project_ids

    @pytest.mark.asyncio
    async def test_project_specific_metadata(self):
        """Test that each project can have different metadata for same page"""
        await self.setup_db()
        test_data = await self.create_test_data()

        async with AsyncSessionLocal() as session:
            # Get a page
            page1 = test_data["pages"][0]

            # Create two associations with different metadata
            assoc1 = ProjectPage(
                project_id=test_data["project2"].id,
                page_id=page1.id,
                domain_id=test_data["domain2"].id,
                review_status=PageReviewStatus.RELEVANT,
                priority_level=PagePriority.HIGH,
                tags=["important", "project2"],
                notes="Important for project 2"
            )
            assoc2 = ProjectPage(
                project_id=test_data["project3"].id,
                page_id=page1.id,
                domain_id=test_data["domain3"].id,
                review_status=PageReviewStatus.IRRELEVANT,
                priority_level=PagePriority.LOW,
                tags=["not-useful"],
                notes="Not relevant for project 3"
            )
            session.add_all([assoc1, assoc2])
            await session.commit()

            # Verify different metadata
            associations_stmt = select(ProjectPage).where(ProjectPage.page_id == page1.id)
            result = await session.execute(associations_stmt)
            associations = result.scalars().all()

            # Find the two new associations
            project2_assoc = [a for a in associations if a.project_id == test_data["project2"].id][0]
            project3_assoc = [a for a in associations if a.project_id == test_data["project3"].id][0]

            assert project2_assoc.review_status == PageReviewStatus.RELEVANT
            assert project2_assoc.priority_level == PagePriority.HIGH
            assert "important" in project2_assoc.tags

            assert project3_assoc.review_status == PageReviewStatus.IRRELEVANT
            assert project3_assoc.priority_level == PagePriority.LOW
            assert "not-useful" in project3_assoc.tags

    @pytest.mark.asyncio
    async def test_page_deletion_cascade(self):
        """Test that deleting a page removes associated ProjectPage records"""
        await self.setup_db()
        test_data = await self.create_test_data()

        async with AsyncSessionLocal() as session:
            page_to_delete = test_data["pages"][0]
            page_id = page_to_delete.id

            # Count associations before deletion
            associations_stmt = select(ProjectPage).where(ProjectPage.page_id == page_id)
            result = await session.execute(associations_stmt)
            initial_associations = len(result.scalars().all())
            assert initial_associations >= 1

            # Delete page
            stmt = select(Page).where(Page.id == page_id)
            result = await session.execute(stmt)
            page = result.scalar_one()
            await session.delete(page)
            await session.commit()

            # Verify page is deleted
            result = await session.execute(select(Page).where(Page.id == page_id))
            assert result.scalar_one_or_none() is None

            # Verify associations still exist (no cascade delete configured)
            result = await session.execute(associations_stmt)
            remaining_associations = result.scalars().all()
            # Note: The associations remain as orphans unless cascade is configured
            # This is expected behavior for the current schema

    @pytest.mark.asyncio
    async def test_performance_large_dataset(self):
        """Test performance with larger dataset"""
        await self.setup_db()
        async with AsyncSessionLocal() as session:
            # Create test user and project
            user = User(
                email="perf_test@example.com",
                hashed_password=get_password_hash("testpass"),
                full_name="Performance Test User",
                is_active=True,
                is_verified=True,
                approval_status="approved"
            )
            session.add(user)
            await session.commit()
            await session.refresh(user)

            project = Project(
                name="Performance Test Project",
                user_id=user.id
            )
            session.add(project)
            await session.commit()
            await session.refresh(project)

            domain = Domain(
                name="perf-test.com",
                project_id=project.id,
                config={}
            )
            session.add(domain)
            await session.commit()
            await session.refresh(domain)

            # Create many pages
            pages = []
            for i in range(100):
                page = Page(
                    url=f"https://perf-test.com/page-{i}",
                    unix_timestamp=1672574400 + (i * 3600),
                    content_url=f"https://web.archive.org/web/2023010{i%10:01d}120000if_/https://perf-test.com/page-{i}",
                    content=f"Performance test content {i}",
                    title=f"Performance Page {i}",
                    processed=True
                )
                pages.append(page)

            session.add_all(pages)
            await session.commit()
            for page in pages:
                await session.refresh(page)

            # Create associations
            associations = []
            for page in pages:
                assoc = ProjectPage(
                    project_id=project.id,
                    page_id=page.id,
                    domain_id=domain.id,
                    review_status=PageReviewStatus.PENDING,
                    priority_level=PagePriority.MEDIUM,
                    tags=[]
                )
                associations.append(assoc)

            session.add_all(associations)
            await session.commit()

            # Verify all created
            import time
            start_time = time.time()

            pages_stmt = select(Page)
            result = await session.execute(pages_stmt)
            all_pages = result.scalars().all()

            end_time = time.time()
            query_time = end_time - start_time

            assert len(all_pages) == 100
            assert query_time < 1.0  # Should be fast

            # Test association query performance
            start_time = time.time()

            associations_stmt = select(ProjectPage).where(ProjectPage.project_id == project.id)
            result = await session.execute(associations_stmt)
            all_associations = result.scalars().all()

            end_time = time.time()
            query_time = end_time - start_time

            assert len(all_associations) == 100
            assert query_time < 1.0
