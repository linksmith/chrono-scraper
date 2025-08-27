"""
Performance test suite for bulk operations in shared pages architecture
"""
import pytest
import asyncio
import uuid
import time
import statistics
from datetime import datetime, timezone
from typing import List, Dict, Any
from unittest.mock import AsyncMock, MagicMock, patch
from sqlmodel import Session, select
from sqlalchemy.ext.asyncio import AsyncSession
from concurrent.futures import ThreadPoolExecutor, as_completed

from app.models.shared_pages import (
    PageV2, ProjectPage, CDXPageRegistry,
    ScrapeStatus, PageReviewStatus, PageCategory, PagePriority
)
from app.models.project import Project, Domain
from app.models.user import User
from app.core.security import get_password_hash
from app.services.cdx_deduplication_service import CDXRecord, EnhancedCDXService
from app.services.page_access_control import PageAccessControl
from app.services.shared_pages_meilisearch import SharedPagesMeilisearchService
from app.services.cache_service import PageCacheService


@pytest.mark.asyncio
class TestBulkOperationsPerformance:
    """Performance tests for bulk operations"""
    
    @pytest.fixture
    async def setup_performance_test_data(self, app):
        """Setup large dataset for performance testing"""
        async with AsyncSessionLocal() as session:
            # Create test users
            users = []
            for i in range(5):
                user = User(
                    email=f"perf_user_{i}@example.com",
                    hashed_password=get_password_hash("testpass"),
                    full_name=f"Performance Test User {i}",
                    is_active=True,
                    is_verified=True,
                    approval_status="approved"
                )
                users.append(user)
            
            session.add_all(users)
            await session.commit()
            for user in users:
                await session.refresh(user)
            
            # Create test projects (2 per user)
            projects = []
            for user in users:
                for j in range(2):
                    project = Project(
                        name=f"Performance Project {user.id}-{j}",
                        description=f"Performance test project {j} for user {user.id}",
                        user_id=user.id
                    )
                    projects.append(project)
            
            session.add_all(projects)
            await session.commit()
            for project in projects:
                await session.refresh(project)
            
            # Create test domains (1 per project)
            domains = []
            for project in projects:
                domain = Domain(
                    name=f"perf-domain-{project.id}.com",
                    project_id=project.id,
                    config={"performance_test": True}
                )
                domains.append(domain)
            
            session.add_all(domains)
            await session.commit()
            for domain in domains:
                await session.refresh(domain)
            
            # Create large number of test pages
            pages = []
            for i in range(1000):  # 1000 pages for performance testing
                page = PageV2(
                    url=f"https://performance-test.com/page-{i}",
                    unix_timestamp=1234567890 + i,
                    wayback_url=f"https://web.archive.org/web/{1234567890 + i}if_/https://performance-test.com/page-{i}",
                    content=f"<html><body><h1>Performance Test Page {i}</h1><p>Content for performance testing page {i}. This content is designed to test bulk operations and database performance under load.</p></body></html>",
                    markdown_content=f"# Performance Test Page {i}\n\nContent for performance testing page {i}. This content is designed to test bulk operations and database performance under load.",
                    title=f"Performance Test Page {i}",
                    extracted_title=f"Performance Test Page {i} - Extracted",
                    extracted_text=f"Performance Test Page {i} Content for performance testing page {i}. This content is designed to test bulk operations and database performance under load.",
                    meta_description=f"Performance test page {i} for bulk operations testing",
                    meta_keywords=f"performance, test, page, {i}, bulk, operations",
                    author="Performance Test System",
                    language="en",
                    word_count=50 + (i % 100),
                    character_count=300 + (i % 500),
                    quality_score=0.5 + (i % 50) / 100,
                    processed=True,
                    indexed=(i % 2 == 0)  # Index every other page
                )
                pages.append(page)
            
            session.add_all(pages)
            await session.commit()
            for page in pages:
                await session.refresh(page)
            
            # Create project-page associations (distributed across projects)
            associations = []
            for i, page in enumerate(pages):
                # Each page belongs to 1-3 projects
                num_projects = (i % 3) + 1
                selected_projects = projects[i % len(projects):i % len(projects) + num_projects]
                
                for project in selected_projects:
                    if len(associations) >= len(pages) * 1.5:  # Limit associations
                        break
                    
                    association = ProjectPage(
                        project_id=project.id,
                        page_id=page.id,
                        domain_id=domains[projects.index(project)].id,
                        added_by=project.user_id,
                        review_status=PageReviewStatus(list(PageReviewStatus)[i % len(PageReviewStatus)]),
                        page_category=PageCategory(list(PageCategory)[i % len(PageCategory)]),
                        priority_level=PagePriority(list(PagePriority)[i % len(PagePriority)]),
                        tags=[f"tag-{i % 10}", f"category-{i % 5}", "performance-test"],
                        notes=f"Performance test notes for page {i}",
                        is_starred=(i % 10 == 0)
                    )
                    associations.append(association)
            
            session.add_all(associations)
            await session.commit()
            
            return {
                "users": users,
                "projects": projects,
                "domains": domains,
                "pages": pages,
                "associations": associations,
                "session": session
            }
    
    async def test_bulk_page_creation_performance(self, setup_performance_test_data):
        """Test performance of bulk page creation"""
        test_data = await setup_performance_test_data
        session = test_data["session"]
        
        # Create additional pages in bulk
        new_pages = []
        for i in range(500):  # Create 500 new pages
            page = PageV2(
                url=f"https://bulk-creation.com/page-{i}",
                unix_timestamp=1234567890 + 2000 + i,
                content=f"Bulk creation test content {i}",
                title=f"Bulk Created Page {i}",
                quality_score=0.8,
                processed=True,
                indexed=False
            )
            new_pages.append(page)
        
        # Measure bulk creation time
        start_time = time.time()
        
        session.add_all(new_pages)
        await session.commit()
        
        end_time = time.time()
        creation_time = end_time - start_time
        
        # Performance assertion: should create 500 pages in < 5 seconds
        assert creation_time < 5.0, f"Bulk page creation took {creation_time:.2f}s, expected < 5.0s"
        
        # Verify all pages were created
        bulk_pages_stmt = select(PageV2).where(PageV2.url.like("https://bulk-creation.com/%"))
        result = await session.execute(bulk_pages_stmt)
        created_pages = result.scalars().all()
        
        assert len(created_pages) == 500
        
        print(f"✓ Created 500 pages in {creation_time:.2f}s ({500/creation_time:.1f} pages/sec)")
    
    async def test_bulk_association_creation_performance(self, setup_performance_test_data):
        """Test performance of bulk project-page association creation"""
        test_data = await setup_performance_test_data
        session = test_data["session"]
        
        # Select subset of pages and projects for bulk association
        pages = test_data["pages"][:200]  # First 200 pages
        project = test_data["projects"][0]
        domain = test_data["domains"][0]
        
        # Create bulk associations
        new_associations = []
        for page in pages:
            association = ProjectPage(
                project_id=project.id,
                page_id=page.id,
                domain_id=domain.id,
                added_by=project.user_id,
                review_status=PageReviewStatus.PENDING,
                priority_level=PagePriority.MEDIUM,
                tags=["bulk-test"],
                is_starred=False
            )
            new_associations.append(association)
        
        # Measure bulk association creation time
        start_time = time.time()
        
        session.add_all(new_associations)
        await session.commit()
        
        end_time = time.time()
        association_time = end_time - start_time
        
        # Performance assertion: should create 200 associations in < 2 seconds
        assert association_time < 2.0, f"Bulk association creation took {association_time:.2f}s, expected < 2.0s"
        
        print(f"✓ Created 200 associations in {association_time:.2f}s ({200/association_time:.1f} associations/sec)")
    
    async def test_bulk_page_access_check_performance(self, setup_performance_test_data):
        """Test performance of bulk page access checking"""
        test_data = await setup_performance_test_data
        session = test_data["session"]
        
        # Setup access control
        cache_service = PageCacheService()
        access_control = PageAccessControl(session, cache_service)
        
        user = test_data["users"][0]
        page_ids = [page.id for page in test_data["pages"][:500]]  # Check 500 pages
        
        # Measure bulk access check time
        start_time = time.time()
        
        accessible_pages = await access_control.bulk_check_page_access(
            user.id,
            page_ids
        )
        
        end_time = time.time()
        access_check_time = end_time - start_time
        
        # Performance assertion: should check 500 pages in < 1 second
        assert access_check_time < 1.0, f"Bulk access check took {access_check_time:.2f}s, expected < 1.0s"
        
        assert len(accessible_pages) > 0  # User should have access to some pages
        
        print(f"✓ Checked access for 500 pages in {access_check_time:.2f}s ({500/access_check_time:.1f} checks/sec)")
    
    async def test_cdx_bulk_processing_performance(self, setup_performance_test_data):
        """Test performance of bulk CDX processing with deduplication"""
        test_data = await setup_performance_test_data
        session = test_data["session"]
        
        # Setup CDX service
        cache_service = PageCacheService()
        cdx_service = EnhancedCDXService(session, cache_service)
        
        project = test_data["projects"][0]
        domain = test_data["domains"][0]
        
        # Create CDX records (mix of existing and new)
        cdx_records = []
        
        # 100 existing pages (should be linked quickly)
        for i in range(100):
            existing_page = test_data["pages"][i]
            record = CDXRecord(
                url=existing_page.url,
                timestamp=existing_page.unix_timestamp
            )
            cdx_records.append(record)
        
        # 200 new pages (should be queued for scraping)
        for i in range(200):
            record = CDXRecord(
                url=f"https://new-cdx-pages.com/page-{i}",
                timestamp=1234567890 + 3000 + i
            )
            cdx_records.append(record)
        
        # Measure CDX processing time
        with patch('app.services.cdx_deduplication_service.scrape_wayback_page_deduplicated') as mock_task:
            mock_task.delay.return_value = MagicMock()
            
            start_time = time.time()
            
            stats = await cdx_service.process_cdx_results(
                cdx_records=cdx_records,
                project_id=project.id,
                domain_id=domain.id
            )
            
            end_time = time.time()
            cdx_processing_time = end_time - start_time
        
        # Performance assertion: should process 300 CDX records in < 3 seconds
        assert cdx_processing_time < 3.0, f"CDX processing took {cdx_processing_time:.2f}s, expected < 3.0s"
        
        # Verify processing stats
        assert stats.total_processed == 300
        assert stats.pages_linked == 100  # Existing pages
        assert stats.pages_to_scrape == 200  # New pages
        
        print(f"✓ Processed 300 CDX records in {cdx_processing_time:.2f}s ({300/cdx_processing_time:.1f} records/sec)")
        print(f"  - Linked {stats.pages_linked} existing pages")
        print(f"  - Queued {stats.pages_to_scrape} new pages for scraping")
    
    async def test_meilisearch_bulk_indexing_performance(self, setup_performance_test_data):
        """Test performance of Meilisearch bulk indexing"""
        test_data = await setup_performance_test_data
        session = test_data["session"]
        
        # Mock Meilisearch client for performance testing
        mock_client = MagicMock()
        mock_index = MagicMock()
        mock_client.get_index.return_value = mock_index
        mock_index.add_documents.return_value = {"taskUid": 1}
        
        with patch('app.services.shared_pages_meilisearch.meilisearch.Client', return_value=mock_client):
            meilisearch_service = SharedPagesMeilisearchService(session)
            meilisearch_service.client = mock_client
            meilisearch_service.index = mock_index
            
            # Test bulk indexing of 500 pages
            page_ids = [page.id for page in test_data["pages"][:500]]
            
            # Measure bulk indexing time
            start_time = time.time()
            
            result = await meilisearch_service.bulk_index_pages(page_ids)
            
            end_time = time.time()
            indexing_time = end_time - start_time
            
            # Performance assertion: should index 500 pages in < 2 seconds
            assert indexing_time < 2.0, f"Bulk indexing took {indexing_time:.2f}s, expected < 2.0s"
            
            # Verify indexing was called
            assert result is not None
            mock_index.add_documents.assert_called_once()
            
            # Verify all pages were included
            call_args = mock_index.add_documents.call_args[0][0]
            assert len(call_args) == 500
            
            print(f"✓ Indexed 500 pages in {indexing_time:.2f}s ({500/indexing_time:.1f} pages/sec)")
    
    async def test_concurrent_operations_performance(self, setup_performance_test_data):
        """Test performance of concurrent operations on shared resources"""
        test_data = await setup_performance_test_data
        
        # Test concurrent CDX processing
        async def process_cdx_batch(session, project_id, domain_id, batch_id, batch_size=50):
            cache_service = PageCacheService()
            cdx_service = EnhancedCDXService(session, cache_service)
            
            # Create CDX records for this batch
            cdx_records = []
            for i in range(batch_size):
                record = CDXRecord(
                    url=f"https://concurrent-{batch_id}.com/page-{i}",
                    timestamp=1234567890 + batch_id * 1000 + i
                )
                cdx_records.append(record)
            
            with patch('app.services.cdx_deduplication_service.scrape_wayback_page_deduplicated') as mock_task:
                mock_task.delay.return_value = MagicMock()
                
                return await cdx_service.process_cdx_results(
                    cdx_records=cdx_records,
                    project_id=project_id,
                    domain_id=domain_id
                )
        
        # Create concurrent sessions for testing
        async def create_session():
            async with AsyncSessionLocal() as session:
                return session
        
        # Run concurrent CDX processing
        project = test_data["projects"][0]
        domain = test_data["domains"][0]
        
        start_time = time.time()
        
        # Create multiple tasks for concurrent processing
        tasks = []
        for batch_id in range(5):  # 5 concurrent batches
            session = await create_session()
            task = process_cdx_batch(session, project.id, domain.id, batch_id)
            tasks.append(task)
        
        # Execute all tasks concurrently
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        end_time = time.time()
        concurrent_time = end_time - start_time
        
        # Performance assertion: should handle 5 concurrent batches in < 5 seconds
        assert concurrent_time < 5.0, f"Concurrent processing took {concurrent_time:.2f}s, expected < 5.0s"
        
        # Verify all tasks completed successfully
        successful_results = [r for r in results if not isinstance(r, Exception)]
        assert len(successful_results) == 5
        
        total_processed = sum(r.total_processed for r in successful_results)
        assert total_processed == 250  # 5 batches * 50 records each
        
        print(f"✓ Processed 5 concurrent batches (250 total records) in {concurrent_time:.2f}s")
    
    async def test_large_dataset_query_performance(self, setup_performance_test_data):
        """Test query performance on large datasets"""
        test_data = await setup_performance_test_data
        session = test_data["session"]
        
        # Test performance of various queries
        queries = [
            {
                "name": "User accessible pages",
                "query": lambda: session.execute(
                    select(PageV2)
                    .join(ProjectPage)
                    .join(Project)
                    .where(Project.user_id == test_data["users"][0].id)
                    .limit(100)
                )
            },
            {
                "name": "Pages by review status",
                "query": lambda: session.execute(
                    select(PageV2)
                    .join(ProjectPage)
                    .where(ProjectPage.review_status == PageReviewStatus.RELEVANT)
                    .limit(100)
                )
            },
            {
                "name": "High quality pages",
                "query": lambda: session.execute(
                    select(PageV2)
                    .where(PageV2.quality_score >= 0.8)
                    .order_by(PageV2.quality_score.desc())
                    .limit(100)
                )
            },
            {
                "name": "Project associations count",
                "query": lambda: session.execute(
                    select(ProjectPage.project_id, PageV2.id)
                    .join(PageV2)
                    .where(ProjectPage.project_id == test_data["projects"][0].id)
                )
            }
        ]
        
        query_times = []
        
        for query_test in queries:
            start_time = time.time()
            
            result = await query_test["query"]()
            rows = result.fetchall()
            
            end_time = time.time()
            query_time = end_time - start_time
            
            query_times.append(query_time)
            
            # Each query should complete in < 0.5 seconds
            assert query_time < 0.5, f"{query_test['name']} took {query_time:.3f}s, expected < 0.5s"
            
            print(f"✓ {query_test['name']}: {query_time:.3f}s ({len(rows)} results)")
        
        # Overall performance check
        avg_query_time = statistics.mean(query_times)
        assert avg_query_time < 0.3, f"Average query time {avg_query_time:.3f}s, expected < 0.3s"
        
        print(f"✓ Average query time: {avg_query_time:.3f}s")
    
    async def test_memory_usage_bulk_operations(self, setup_performance_test_data):
        """Test memory usage during bulk operations"""
        test_data = await setup_performance_test_data
        session = test_data["session"]
        
        import psutil
        import os
        
        process = psutil.Process(os.getpid())
        initial_memory = process.memory_info().rss / 1024 / 1024  # MB
        
        # Perform memory-intensive bulk operations
        operations = [
            # Load many pages
            lambda: session.execute(select(PageV2).limit(500)),
            
            # Load many associations
            lambda: session.execute(select(ProjectPage).limit(500)),
            
            # Complex join query
            lambda: session.execute(
                select(PageV2, ProjectPage, Project)
                .join(ProjectPage)
                .join(Project)
                .limit(200)
            )
        ]
        
        peak_memory = initial_memory
        
        for operation in operations:
            result = await operation()
            rows = result.fetchall()
            
            current_memory = process.memory_info().rss / 1024 / 1024  # MB
            peak_memory = max(peak_memory, current_memory)
            
            # Clear references to help garbage collection
            del result
            del rows
        
        memory_increase = peak_memory - initial_memory
        
        # Memory increase should be reasonable (< 100MB for test operations)
        assert memory_increase < 100, f"Memory increased by {memory_increase:.1f}MB, expected < 100MB"
        
        print(f"✓ Memory usage: {initial_memory:.1f}MB → {peak_memory:.1f}MB (+{memory_increase:.1f}MB)")
    
    async def test_database_connection_pool_performance(self, setup_performance_test_data):
        """Test database connection pool performance under load"""
        test_data = await setup_performance_test_data
        
        async def database_operation(operation_id: int):
            """Simulate database operation"""
            async with AsyncSessionLocal() as session:
                # Perform a simple query
                result = await session.execute(
                    select(PageV2).where(PageV2.id == test_data["pages"][operation_id % len(test_data["pages"])].id)
                )
                page = result.scalar_one_or_none()
                return page is not None
        
        # Test concurrent database operations
        num_operations = 50
        
        start_time = time.time()
        
        # Create concurrent tasks
        tasks = [database_operation(i) for i in range(num_operations)]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        end_time = time.time()
        total_time = end_time - start_time
        
        # Performance assertion: 50 concurrent operations should complete in < 3 seconds
        assert total_time < 3.0, f"Concurrent DB operations took {total_time:.2f}s, expected < 3.0s"
        
        # Verify all operations completed successfully
        successful_operations = [r for r in results if r is True]
        assert len(successful_operations) == num_operations
        
        print(f"✓ Completed {num_operations} concurrent DB operations in {total_time:.2f}s")
        print(f"  - {num_operations/total_time:.1f} operations/sec")
    
    async def test_cache_performance_impact(self, setup_performance_test_data):
        """Test performance impact of caching"""
        test_data = await setup_performance_test_data
        session = test_data["session"]
        
        cache_service = PageCacheService()
        access_control = PageAccessControl(session, cache_service)
        
        user = test_data["users"][0]
        page_ids = [page.id for page in test_data["pages"][:100]]
        
        # First call (should populate cache)
        start_time = time.time()
        result1 = await access_control.get_user_accessible_pages(user.id)
        first_call_time = time.time() - start_time
        
        # Second call (should use cache if implemented)
        start_time = time.time()
        result2 = await access_control.get_user_accessible_pages(user.id)
        second_call_time = time.time() - start_time
        
        # Results should be the same
        assert result1 == result2
        
        # Note: Cache performance improvement depends on implementation
        # This test mainly verifies that caching doesn't break functionality
        print(f"✓ First call: {first_call_time:.3f}s, Second call: {second_call_time:.3f}s")
        
        if second_call_time < first_call_time * 0.8:
            print(f"✓ Cache improved performance by {((first_call_time - second_call_time) / first_call_time * 100):.1f}%")
        else:
            print("  (Cache performance improvement not detected or not implemented)")


@pytest.mark.asyncio
class TestScalabilityLimits:
    """Test scalability limits and breaking points"""
    
    async def test_maximum_page_associations(self, app):
        """Test maximum number of associations for a single page"""
        async with AsyncSessionLocal() as session:
            # Create many users and projects
            users = []
            for i in range(20):
                user = User(
                    email=f"scale_user_{i}@example.com",
                    hashed_password=get_password_hash("testpass"),
                    full_name=f"Scale User {i}",
                    is_active=True,
                    is_verified=True,
                    approval_status="approved"
                )
                users.append(user)
            
            session.add_all(users)
            await session.commit()
            
            projects = []
            for user in users:
                for j in range(5):  # 5 projects per user = 100 total projects
                    project = Project(
                        name=f"Scale Project {user.id}-{j}",
                        user_id=user.id
                    )
                    projects.append(project)
            
            session.add_all(projects)
            await session.commit()
            
            # Create single page
            page = PageV2(
                url="https://scale-test.com/heavily-shared-page",
                unix_timestamp=1234567890,
                content="Heavily shared page content",
                title="Heavily Shared Page"
            )
            session.add(page)
            await session.commit()
            await session.refresh(page)
            
            # Create associations to all projects
            associations = []
            for project in projects:
                association = ProjectPage(
                    project_id=project.id,
                    page_id=page.id,
                    added_by=project.user_id,
                    review_status=PageReviewStatus.PENDING
                )
                associations.append(association)
            
            start_time = time.time()
            
            session.add_all(associations)
            await session.commit()
            
            end_time = time.time()
            association_time = end_time - start_time
            
            # Should handle 100 associations reasonably
            assert association_time < 5.0, f"Creating 100 associations took {association_time:.2f}s"
            
            # Verify all associations were created
            count_stmt = select(ProjectPage).where(ProjectPage.page_id == page.id)
            result = await session.execute(count_stmt)
            association_count = len(result.scalars().all())
            
            assert association_count == 100
            
            print(f"✓ Created 100 project associations for single page in {association_time:.2f}s")
    
    async def test_large_project_page_count(self, app):
        """Test performance with project containing many pages"""
        async with AsyncSessionLocal() as session:
            # Create test user and project
            user = User(
                email="large_project@example.com",
                hashed_password=get_password_hash("testpass"),
                full_name="Large Project User",
                is_active=True,
                is_verified=True,
                approval_status="approved"
            )
            session.add(user)
            await session.commit()
            await session.refresh(user)
            
            project = Project(
                name="Large Project",
                description="Project with many pages",
                user_id=user.id
            )
            session.add(project)
            await session.commit()
            await session.refresh(project)
            
            # Create many pages
            pages = []
            for i in range(2000):  # 2000 pages
                page = PageV2(
                    url=f"https://large-project.com/page-{i}",
                    unix_timestamp=1234567890 + i,
                    content=f"Large project page {i} content",
                    title=f"Large Project Page {i}",
                    quality_score=0.5 + (i % 50) / 100
                )
                pages.append(page)
            
            session.add_all(pages)
            await session.commit()
            
            # Create associations
            associations = []
            for page in pages:
                association = ProjectPage(
                    project_id=project.id,
                    page_id=page.id,
                    added_by=user.id,
                    review_status=PageReviewStatus.PENDING
                )
                associations.append(association)
            
            start_time = time.time()
            
            session.add_all(associations)
            await session.commit()
            
            association_time = time.time() - start_time
            
            # Test querying project pages
            start_time = time.time()
            
            project_pages_stmt = (
                select(PageV2)
                .join(ProjectPage)
                .where(ProjectPage.project_id == project.id)
                .limit(100)
            )
            result = await session.execute(project_pages_stmt)
            project_pages = result.scalars().all()
            
            query_time = time.time() - start_time
            
            assert len(project_pages) == 100
            assert query_time < 1.0, f"Querying 100 pages from large project took {query_time:.3f}s"
            
            print(f"✓ Created 2000 page associations in {association_time:.2f}s")
            print(f"✓ Queried 100 pages from large project in {query_time:.3f}s")


# Import AsyncSessionLocal from conftest
from tests.conftest import AsyncSessionLocal