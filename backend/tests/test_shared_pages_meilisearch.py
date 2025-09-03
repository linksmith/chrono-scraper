"""
Test suite for shared pages Meilisearch integration with comprehensive search functionality testing
"""
import pytest
import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.shared_pages_meilisearch import (
    SharedPagesMeilisearchService, get_shared_pages_meilisearch_service
)
from app.models.shared_pages import (
    PageV2, ProjectPage, PageReviewStatus, PageCategory, PagePriority
)
from app.models.project import Project
from app.models.user import User
from app.core.security import get_password_hash


@pytest.mark.asyncio
class TestSharedPagesMeilisearchService:
    """Test Meilisearch integration for shared pages"""
    
    @pytest.fixture
    async def setup_meilisearch_test_data(self, app):
        """Setup test data for Meilisearch testing"""
        async with AsyncSessionLocal() as session:
            # Create test users
            user1 = User(
                email="meilisearch1@example.com",
                hashed_password=get_password_hash("testpass"),
                full_name="Meilisearch Test User 1",
                is_active=True,
                is_verified=True,
                approval_status="approved"
            )
            user2 = User(
                email="meilisearch2@example.com",
                hashed_password=get_password_hash("testpass"),
                full_name="Meilisearch Test User 2",
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
                name="Meilisearch Test Project 1",
                description="Research project for search testing",
                user_id=user1.id
            )
            project2 = Project(
                name="Meilisearch Test Project 2",
                description="Government analysis project",
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
            
            # Create test pages with rich content
            page1 = PageV2(
                url="https://research.example.com/climate-study",
                unix_timestamp=1234567890,
                content="<html><body><h1>Climate Change Research</h1><p>This comprehensive study examines the impact of climate change on arctic ecosystems. The research methodology involved extensive field work and data collection over five years.</p></body></html>",
                markdown_content="# Climate Change Research\n\nThis comprehensive study examines the impact of climate change on arctic ecosystems. The research methodology involved extensive field work and data collection over five years.",
                title="Climate Change Research Study",
                extracted_title="Climate Change Research Study - Arctic Ecosystems",
                extracted_text="Climate Change Research This comprehensive study examines the impact of climate change on arctic ecosystems. The research methodology involved extensive field work and data collection over five years.",
                meta_description="Comprehensive climate change research study focusing on arctic ecosystems",
                meta_keywords="climate change, arctic, ecosystems, research, environment",
                author="Dr. Jane Smith",
                published_date=datetime(2023, 1, 15, tzinfo=timezone.utc),
                language="en",
                word_count=1250,
                character_count=8500,
                quality_score=0.92,
                processed=True,
                indexed=True
            )
            
            page2 = PageV2(
                url="https://gov.example.com/policy-document",
                unix_timestamp=1234567891,
                content="<html><body><h1>Environmental Policy Framework</h1><p>Official government policy document outlining new environmental regulations and compliance requirements for industrial operations.</p></body></html>",
                markdown_content="# Environmental Policy Framework\n\nOfficial government policy document outlining new environmental regulations and compliance requirements for industrial operations.",
                title="Environmental Policy Framework 2023",
                extracted_title="Environmental Policy Framework 2023 - Government Document",
                extracted_text="Environmental Policy Framework Official government policy document outlining new environmental regulations and compliance requirements for industrial operations.",
                meta_description="Government environmental policy framework and regulations",
                meta_keywords="policy, environment, government, regulations, compliance",
                author="Department of Environment",
                published_date=datetime(2023, 3, 10, tzinfo=timezone.utc),
                language="en",
                word_count=3200,
                character_count=18000,
                quality_score=0.88,
                processed=True,
                indexed=True
            )
            
            page3 = PageV2(
                url="https://news.example.com/breaking-news",
                unix_timestamp=1234567892,
                content="<html><body><h1>Breaking: New Climate Agreement</h1><p>World leaders reach historic climate agreement at international summit. The agreement includes binding emissions targets and funding mechanisms.</p></body></html>",
                title="Breaking: New Climate Agreement Reached",
                extracted_text="Breaking: New Climate Agreement World leaders reach historic climate agreement at international summit. The agreement includes binding emissions targets and funding mechanisms.",
                word_count=800,
                character_count=4200,
                quality_score=0.75,
                processed=True,
                indexed=True
            )
            
            page4 = PageV2(
                url="https://private.example.com/internal-doc",
                unix_timestamp=1234567893,
                content="<html><body><h1>Internal Document</h1><p>This is a private internal document not accessible to other users.</p></body></html>",
                title="Internal Document",
                processed=True,
                indexed=True
            )
            
            session.add_all([page1, page2, page3, page4])
            await session.commit()
            await session.refresh(page1)
            await session.refresh(page2)
            await session.refresh(page3)
            await session.refresh(page4)
            
            # Create project-page associations with different metadata
            associations = [
                # User 1, Project 1 - Research focus
                ProjectPage(
                    project_id=project1.id,
                    page_id=page1.id,
                    added_by=user1.id,
                    review_status=PageReviewStatus.RELEVANT,
                    page_category=PageCategory.RESEARCH,
                    priority_level=PagePriority.HIGH,
                    tags=["climate", "research", "arctic", "important"],
                    notes="Key research paper for our climate analysis",
                    is_starred=True
                ),
                ProjectPage(
                    project_id=project1.id,
                    page_id=page3.id,
                    added_by=user1.id,
                    review_status=PageReviewStatus.RELEVANT,
                    page_category=PageCategory.NEWS,
                    priority_level=PagePriority.MEDIUM,
                    tags=["climate", "news", "agreement"]
                ),
                
                # User 1, Project 2 - Government focus
                ProjectPage(
                    project_id=project2.id,
                    page_id=page2.id,
                    added_by=user1.id,
                    review_status=PageReviewStatus.RELEVANT,
                    page_category=PageCategory.GOVERNMENT,
                    priority_level=PagePriority.CRITICAL,
                    tags=["government", "policy", "regulations", "compliance"],
                    notes="Official policy framework document"
                ),
                ProjectPage(
                    project_id=project2.id,
                    page_id=page3.id,
                    added_by=user1.id,
                    review_status=PageReviewStatus.NEEDS_REVIEW,
                    page_category=PageCategory.NEWS,
                    priority_level=PagePriority.HIGH,
                    tags=["climate", "government", "international"]
                ),
                
                # User 2, Project 3 - Private access
                ProjectPage(
                    project_id=project3.id,
                    page_id=page4.id,
                    added_by=user2.id,
                    review_status=PageReviewStatus.PENDING,
                    page_category=PageCategory.COMMERCIAL,
                    priority_level=PagePriority.LOW,
                    tags=["internal", "private"]
                )
            ]
            
            session.add_all(associations)
            await session.commit()
            
            return {
                "user1": user1,
                "user2": user2,
                "project1": project1,
                "project2": project2,
                "project3": project3,
                "page1": page1,
                "page2": page2,
                "page3": page3,
                "page4": page4,
                "session": session
            }
    
    @pytest.fixture
    def mock_meilisearch_client(self):
        """Mock Meilisearch client for testing"""
        mock_client = MagicMock()
        mock_index = MagicMock()
        
        # Setup mock responses
        mock_client.get_index.return_value = mock_index
        mock_index.search.return_value = {
            "hits": [],
            "totalHits": 0,
            "processingTimeMs": 5,
            "query": "",
            "facetDistribution": {}
        }
        mock_index.add_documents.return_value = {"taskUid": 1}
        mock_index.update_documents.return_value = {"taskUid": 2}
        mock_index.delete_document.return_value = {"taskUid": 3}
        mock_index.delete_all_documents.return_value = {"taskUid": 4}
        mock_index.get_stats.return_value = {"numberOfDocuments": 0}
        
        return mock_client
    
    @pytest.fixture
    def meilisearch_service(self, app, mock_meilisearch_client):
        """Create SharedPagesMeilisearchService with mocked client"""
        async def get_session():
            async with AsyncSessionLocal() as session:
                yield session
        
        session_gen = get_session()
        session = asyncio.get_event_loop().run_until_complete(session_gen.__anext__())
        
        with patch('app.services.shared_pages_meilisearch.meilisearch.Client', return_value=mock_meilisearch_client):
            service = SharedPagesMeilisearchService(session)
            service.client = mock_meilisearch_client
            service.index = mock_meilisearch_client.get_index("shared_pages")
            
        return service
    
    async def test_index_page_success(self, meilisearch_service, setup_meilisearch_test_data):
        """Test successful page indexing"""
        test_data = await setup_meilisearch_test_data
        
        # Index page1 for project1
        result = await meilisearch_service.index_page(
            test_data["page1"],
            test_data["project1"].id
        )
        
        assert result is not None
        
        # Verify the document structure passed to Meilisearch
        meilisearch_service.index.add_documents.assert_called_once()
        call_args = meilisearch_service.index.add_documents.call_args[0][0]
        
        assert len(call_args) == 1
        doc = call_args[0]
        
        assert doc["id"] == str(test_data["page1"].id)
        assert doc["url"] == "https://research.example.com/climate-study"
        assert doc["title"] == "Climate Change Research Study"
        assert doc["extracted_text"] == test_data["page1"].extracted_text
        assert doc["quality_score"] == 0.92
        assert doc["processed"] is True
        assert doc["indexed"] is True
        
        # Check project-specific metadata
        assert test_data["project1"].id in doc["project_ids"]
        assert "climate" in doc["tags"]
        assert "research" in doc["tags"]
        assert doc["review_statuses"] == ["relevant"]
        assert doc["page_categories"] == ["research"]
        assert doc["priority_levels"] == ["high"]
    
    async def test_index_shared_page_multiple_projects(self, meilisearch_service, setup_meilisearch_test_data):
        """Test indexing page shared across multiple projects"""
        test_data = await setup_meilisearch_test_data
        
        # Index page3 which appears in both project1 and project2
        result = await meilisearch_service.index_page(
            test_data["page3"],
            test_data["project1"].id
        )
        
        assert result is not None
        
        # Verify document includes data from all projects
        call_args = meilisearch_service.index.add_documents.call_args[0][0]
        doc = call_args[0]
        
        assert doc["id"] == str(test_data["page3"].id)
        assert test_data["project1"].id in doc["project_ids"]
        assert test_data["project2"].id in doc["project_ids"]
        
        # Should include tags from all projects
        assert "climate" in doc["tags"]
        assert "news" in doc["tags"]
        assert "government" in doc["tags"]
        assert "international" in doc["tags"]
        
        # Should include all review statuses
        assert "relevant" in doc["review_statuses"]
        assert "needs_review" in doc["review_statuses"]
    
    async def test_bulk_index_pages(self, meilisearch_service, setup_meilisearch_test_data):
        """Test bulk indexing of multiple pages"""
        test_data = await setup_meilisearch_test_data
        
        page_ids = [test_data["page1"].id, test_data["page2"].id, test_data["page3"].id]
        
        result = await meilisearch_service.bulk_index_pages(page_ids)
        
        assert result is not None
        
        # Verify bulk indexing call
        meilisearch_service.index.add_documents.assert_called_once()
        call_args = meilisearch_service.index.add_documents.call_args[0][0]
        
        assert len(call_args) == 3
        
        # Verify all pages were included
        indexed_ids = [doc["id"] for doc in call_args]
        assert str(test_data["page1"].id) in indexed_ids
        assert str(test_data["page2"].id) in indexed_ids
        assert str(test_data["page3"].id) in indexed_ids
    
    async def test_search_user_pages_basic(self, meilisearch_service, setup_meilisearch_test_data):
        """Test basic user page search"""
        test_data = await setup_meilisearch_test_data
        
        # Mock search response
        mock_response = {
            "hits": [
                {
                    "id": str(test_data["page1"].id),
                    "url": "https://research.example.com/climate-study",
                    "title": "Climate Change Research Study",
                    "extracted_text": "Climate change research content...",
                    "project_ids": [test_data["project1"].id],
                    "tags": ["climate", "research"],
                    "review_statuses": ["relevant"]
                }
            ],
            "totalHits": 1,
            "processingTimeMs": 8,
            "query": "climate research"
        }
        
        meilisearch_service.index.search.return_value = mock_response
        
        # Test search
        results = await meilisearch_service.search_user_pages(
            user_id=test_data["user1"].id,
            query="climate research",
            limit=10,
            offset=0
        )
        
        assert results == mock_response
        
        # Verify search was called with proper filters
        meilisearch_service.index.search.assert_called_once()
        call_args = meilisearch_service.index.search.call_args
        
        assert call_args[0][0] == "climate research"  # Query
        search_options = call_args[1]
        
        # Should filter by user's accessible project IDs
        assert "filter" in search_options
        filter_expr = search_options["filter"]
        assert f"project_ids = {test_data['project1'].id}" in filter_expr
        assert f"project_ids = {test_data['project2'].id}" in filter_expr
    
    async def test_search_user_pages_with_project_filter(self, meilisearch_service, setup_meilisearch_test_data):
        """Test user page search filtered by specific project"""
        test_data = await setup_meilisearch_test_data
        
        mock_response = {
            "hits": [],
            "totalHits": 0,
            "processingTimeMs": 3,
            "query": "policy"
        }
        
        meilisearch_service.index.search.return_value = mock_response
        
        # Search with project filter
        await meilisearch_service.search_user_pages(
            user_id=test_data["user1"].id,
            query="policy",
            project_id=test_data["project2"].id,
            limit=10,
            offset=0
        )
        
        # Verify project filter was applied
        call_args = meilisearch_service.index.search.call_args[1]
        filter_expr = call_args["filter"]
        
        # Should only filter by specified project
        assert f"project_ids = {test_data['project2'].id}" in filter_expr
        assert f"project_ids = {test_data['project1'].id}" not in filter_expr
    
    async def test_search_user_pages_with_filters(self, meilisearch_service, setup_meilisearch_test_data):
        """Test user page search with additional filters"""
        test_data = await setup_meilisearch_test_data
        
        mock_response = {
            "hits": [],
            "totalHits": 0,
            "processingTimeMs": 5,
            "query": "research"
        }
        
        meilisearch_service.index.search.return_value = mock_response
        
        # Search with multiple filters
        filters = {
            "review_status": ["relevant", "needs_review"],
            "page_category": ["research", "government"],
            "priority_level": ["high", "critical"],
            "tags": ["climate"],
            "quality_score_min": 0.8,
            "word_count_min": 1000
        }
        
        await meilisearch_service.search_user_pages(
            user_id=test_data["user1"].id,
            query="research",
            filters=filters,
            limit=10,
            offset=0
        )
        
        # Verify filters were applied
        call_args = meilisearch_service.index.search.call_args[1]
        filter_expr = call_args["filter"]
        
        assert "review_statuses IN ['relevant', 'needs_review']" in filter_expr
        assert "page_categories IN ['research', 'government']" in filter_expr
        assert "priority_levels IN ['high', 'critical']" in filter_expr
        assert "tags IN ['climate']" in filter_expr
        assert "quality_score >= 0.8" in filter_expr
        assert "word_count >= 1000" in filter_expr
    
    async def test_search_user_pages_with_sorting(self, meilisearch_service, setup_meilisearch_test_data):
        """Test user page search with custom sorting"""
        test_data = await setup_meilisearch_test_data
        
        mock_response = {"hits": [], "totalHits": 0, "processingTimeMs": 4}
        meilisearch_service.index.search.return_value = mock_response
        
        # Test different sort options
        sort_options = [
            ["quality_score:desc"],
            ["published_date:desc"],
            ["word_count:desc"],
            ["created_at:asc"]
        ]
        
        for sort in sort_options:
            await meilisearch_service.search_user_pages(
                user_id=test_data["user1"].id,
                query="test",
                sort=sort,
                limit=10
            )
            
            # Verify sort was applied
            call_args = meilisearch_service.index.search.call_args[1]
            assert call_args["sort"] == sort
    
    async def test_search_user_pages_no_access(self, meilisearch_service, setup_meilisearch_test_data):
        """Test search returns empty for user with no accessible projects"""
        await setup_meilisearch_test_data
        
        # Create user with no projects
        async with AsyncSessionLocal() as session:
            user_no_access = User(
                email="noaccess@example.com",
                hashed_password=get_password_hash("testpass"),
                full_name="No Access User",
                is_active=True,
                is_verified=True,
                approval_status="approved"
            )
            session.add(user_no_access)
            await session.commit()
            await session.refresh(user_no_access)
        
        results = await meilisearch_service.search_user_pages(
            user_id=user_no_access.id,
            query="anything",
            limit=10
        )
        
        # Should return empty results without calling Meilisearch
        assert results == {
            "hits": [],
            "totalHits": 0,
            "processingTimeMs": 0,
            "query": "anything"
        }
        
        # Meilisearch should not be called
        meilisearch_service.index.search.assert_not_called()
    
    async def test_remove_page_from_index(self, meilisearch_service, setup_meilisearch_test_data):
        """Test removing page from search index"""
        test_data = await setup_meilisearch_test_data
        
        page_id = test_data["page1"].id
        
        result = await meilisearch_service.remove_page_from_index(page_id)
        
        assert result is not None
        
        # Verify delete was called
        meilisearch_service.index.delete_document.assert_called_once_with(str(page_id))
    
    async def test_update_page_project_association(self, meilisearch_service, setup_meilisearch_test_data):
        """Test updating page project association in index"""
        test_data = await setup_meilisearch_test_data
        
        # Mock current document state
        current_doc = {
            "id": str(test_data["page3"].id),
            "project_ids": [test_data["project1"].id, test_data["project2"].id],
            "tags": ["climate", "news", "government"],
            "review_statuses": ["relevant", "needs_review"]
        }
        
        meilisearch_service.index.get_document.return_value = current_doc
        
        # Test removing association
        result = await meilisearch_service.update_page_project_association(
            test_data["page3"].id,
            test_data["project1"].id,
            "remove"
        )
        
        assert result is not None
        
        # Verify update was called
        meilisearch_service.index.update_documents.assert_called_once()
        
        # Test adding association
        meilisearch_service.index.reset_mock()
        
        result = await meilisearch_service.update_page_project_association(
            test_data["page3"].id,
            test_data["project1"].id,
            "add"
        )
        
        # Should trigger re-indexing
        meilisearch_service.index.add_documents.assert_called_once()
    
    async def test_get_search_statistics(self, meilisearch_service, setup_meilisearch_test_data):
        """Test getting search statistics"""
        test_data = await setup_meilisearch_test_data
        
        # Mock index stats
        meilisearch_service.index.get_stats.return_value = {
            "numberOfDocuments": 3,
            "isIndexing": False,
            "fieldDistribution": {
                "title": 3,
                "content": 3,
                "tags": 3
            }
        }
        
        stats = await meilisearch_service.get_search_statistics(test_data["user1"].id)
        
        assert "indexed_pages" in stats
        assert "search_queries_count" in stats
        assert "index_status" in stats
        
        assert stats["indexed_pages"] == 3
        assert stats["index_status"] == "ready"
    
    async def test_clear_user_pages_from_index(self, meilisearch_service, setup_meilisearch_test_data):
        """Test clearing all user pages from index"""
        test_data = await setup_meilisearch_test_data
        
        # Mock search to return user's pages
        mock_search_response = {
            "hits": [
                {"id": str(test_data["page1"].id)},
                {"id": str(test_data["page2"].id)},
                {"id": str(test_data["page3"].id)}
            ],
            "totalHits": 3
        }
        
        meilisearch_service.index.search.return_value = mock_search_response
        
        result = await meilisearch_service.clear_user_pages_from_index(test_data["user1"].id)
        
        assert result is not None
        
        # Verify search was called to find user's pages
        meilisearch_service.index.search.assert_called_once()
        
        # Verify documents were deleted
        assert meilisearch_service.index.delete_document.call_count == 3
    
    async def test_reindex_all_pages(self, meilisearch_service, setup_meilisearch_test_data):
        """Test reindexing all pages"""
        await setup_meilisearch_test_data
        
        result = await meilisearch_service.reindex_all_pages()
        
        assert result is not None
        
        # Verify all documents were cleared and re-added
        meilisearch_service.index.delete_all_documents.assert_called_once()
        meilisearch_service.index.add_documents.assert_called_once()
        
        # Verify all pages were included in reindex
        call_args = meilisearch_service.index.add_documents.call_args[0][0]
        assert len(call_args) >= 3  # At least our test pages
    
    async def test_search_with_facets(self, meilisearch_service, setup_meilisearch_test_data):
        """Test search with facet aggregation"""
        test_data = await setup_meilisearch_test_data
        
        mock_response = {
            "hits": [],
            "totalHits": 0,
            "processingTimeMs": 6,
            "facetDistribution": {
                "page_categories": {
                    "research": 2,
                    "government": 1,
                    "news": 1
                },
                "priority_levels": {
                    "high": 2,
                    "critical": 1,
                    "medium": 1
                }
            }
        }
        
        meilisearch_service.index.search.return_value = mock_response
        
        results = await meilisearch_service.search_user_pages(
            user_id=test_data["user1"].id,
            query="*",
            filters={},
            facets=["page_categories", "priority_levels"],
            limit=0  # Only want facets
        )
        
        # Verify facets were requested
        call_args = meilisearch_service.index.search.call_args[1]
        assert "facets" in call_args
        assert "page_categories" in call_args["facets"]
        assert "priority_levels" in call_args["facets"]
        
        # Verify facet results
        assert "facetDistribution" in results
        assert results["facetDistribution"]["page_categories"]["research"] == 2
    
    async def test_error_handling(self, meilisearch_service, setup_meilisearch_test_data):
        """Test error handling in Meilisearch operations"""
        test_data = await setup_meilisearch_test_data
        
        # Mock Meilisearch error
        meilisearch_service.index.search.side_effect = Exception("Meilisearch connection error")
        
        # Search should handle error gracefully
        results = await meilisearch_service.search_user_pages(
            user_id=test_data["user1"].id,
            query="test"
        )
        
        # Should return empty results on error
        assert results == {
            "hits": [],
            "totalHits": 0,
            "processingTimeMs": 0,
            "query": "test",
            "error": "Search failed"
        }
    
    async def test_pagination_handling(self, meilisearch_service, setup_meilisearch_test_data):
        """Test pagination in search results"""
        test_data = await setup_meilisearch_test_data
        
        mock_response = {"hits": [], "totalHits": 100, "processingTimeMs": 4}
        meilisearch_service.index.search.return_value = mock_response
        
        # Test different pagination scenarios
        pagination_tests = [
            {"limit": 20, "offset": 0},
            {"limit": 50, "offset": 100},
            {"limit": 10, "offset": 90}
        ]
        
        for pagination in pagination_tests:
            await meilisearch_service.search_user_pages(
                user_id=test_data["user1"].id,
                query="test",
                limit=pagination["limit"],
                offset=pagination["offset"]
            )
            
            # Verify pagination parameters were passed
            call_args = meilisearch_service.index.search.call_args[1]
            assert call_args["limit"] == pagination["limit"]
            assert call_args["offset"] == pagination["offset"]


@pytest.mark.asyncio
class TestSharedPagesMeilisearchDependency:
    """Test Meilisearch service dependency injection"""
    
    async def test_get_shared_pages_meilisearch_service_dependency(self):
        """Test SharedPagesMeilisearchService dependency injection"""
        # Mock database session
        mock_db = AsyncMock(spec=AsyncSession)
        
        with patch('app.services.shared_pages_meilisearch.meilisearch.Client'):
            # Get service
            service = await get_shared_pages_meilisearch_service(mock_db)
            
            assert isinstance(service, SharedPagesMeilisearchService)
            assert service.db == mock_db


@pytest.mark.asyncio 
class TestSharedPagesMeilisearchPerformance:
    """Test performance aspects of Meilisearch integration"""
    
    async def test_bulk_indexing_performance(self, app):
        """Test performance of bulk indexing operations"""
        async with AsyncSessionLocal() as session:
            # Create many test pages
            pages = []
            for i in range(100):
                page = PageV2(
                    url=f"https://performance.example.com/page-{i}",
                    unix_timestamp=1234567890 + i,
                    content=f"Performance test content {i}",
                    title=f"Performance Test Page {i}",
                    word_count=100 + i,
                    quality_score=0.5 + (i % 50) / 100,
                    processed=True,
                    indexed=False
                )
                pages.append(page)
            
            session.add_all(pages)
            await session.commit()
            
            # Create service with mocked client
            mock_client = MagicMock()
            mock_index = MagicMock()
            mock_client.get_index.return_value = mock_index
            mock_index.add_documents.return_value = {"taskUid": 1}
            
            with patch('app.services.shared_pages_meilisearch.meilisearch.Client', return_value=mock_client):
                service = SharedPagesMeilisearchService(session)
                service.client = mock_client
                service.index = mock_index
                
                # Test bulk indexing performance
                page_ids = [page.id for page in pages]
                
                import time
                start_time = time.time()
                
                result = await service.bulk_index_pages(page_ids)
                
                end_time = time.time()
                execution_time = end_time - start_time
                
                # Should complete quickly (< 1 second for 100 pages)
                assert execution_time < 1.0
                assert result is not None
                
                # Should make single bulk call rather than individual calls
                assert mock_index.add_documents.call_count == 1
                
                # Verify all pages were included
                call_args = mock_index.add_documents.call_args[0][0]
                assert len(call_args) == 100


# Import AsyncSessionLocal from conftest
from tests.conftest import AsyncSessionLocal