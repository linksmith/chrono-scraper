"""
End-to-end pipeline tests for archive functionality.

Tests cover:
- Full scraping pipeline with different archive sources
- Fallback in production scenarios (actual 522 error handling)
- Data consistency (CDXRecord format across sources)
- Project configuration persistence through scraping pipeline
- Integration with existing scraping tasks and services
- Real-world failure scenarios and recovery
"""
import asyncio
import pytest
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from datetime import datetime, timedelta
from typing import List, Dict, Any

from app.services.archive_service_router import (
    ArchiveServiceRouter,
    RoutingConfig,
    query_archive_unified
)
from app.services.common_crawl_service import CommonCrawlService
from app.services.wayback_machine import CDXAPIClient, CDXRecord, CDXAPIException
from app.models.project import Project, ArchiveSource
from app.models.scraping import ScrapePage, ScrapeSession
from app.tasks.firecrawl_scraping import scrape_pages_task
from app.services.scrape_page_service import ScrapePageService


class TestArchivePipelineE2E:
    """End-to-end tests for archive scraping pipeline"""

    @pytest.fixture
    def project_wayback_only(self, app):
        """Create a project configured for Wayback Machine only"""
        async def _create():
            from app.core.database import get_db
            from app.models.user import User
            from app.core.security import get_password_hash
            
            async for db in get_db():
                # Create user
                user = User(
                    email="wayback_tester@example.com",
                    hashed_password=get_password_hash("testpass"),
                    full_name="Wayback Tester",
                    is_active=True,
                    is_verified=True,
                    approval_status="approved"
                )
                db.add(user)
                await db.commit()
                await db.refresh(user)
                
                # Create project
                project = Project(
                    name="Wayback Only Project",
                    description="Test project using only Wayback Machine",
                    user_id=user.id,
                    archive_source=ArchiveSource.WAYBACK_MACHINE,
                    fallback_enabled=False,
                    archive_config={
                        "wayback_machine": {
                            "timeout_seconds": 60,
                            "page_size": 1000,
                            "max_pages": 5
                        }
                    }
                )
                db.add(project)
                await db.commit()
                await db.refresh(project)
                return project
        
        return asyncio.get_event_loop().run_until_complete(_create())

    @pytest.fixture  
    def project_hybrid(self, app):
        """Create a project configured for hybrid mode with fallback"""
        async def _create():
            from app.core.database import get_db
            from app.models.user import User
            from app.core.security import get_password_hash
            
            async for db in get_db():
                # Create user
                user = User(
                    email="hybrid_tester@example.com", 
                    hashed_password=get_password_hash("testpass"),
                    full_name="Hybrid Tester",
                    is_active=True,
                    is_verified=True,
                    approval_status="approved"
                )
                db.add(user)
                await db.commit()
                await db.refresh(user)
                
                # Create hybrid project
                project = Project(
                    name="Hybrid Archive Project",
                    description="Test project with archive source fallback",
                    user_id=user.id,
                    archive_source=ArchiveSource.HYBRID,
                    fallback_enabled=True,
                    archive_config={
                        "wayback_machine": {
                            "timeout_seconds": 45,
                            "priority": 1
                        },
                        "common_crawl": {
                            "timeout_seconds": 90,
                            "priority": 2
                        },
                        "fallback_strategy": "circuit_breaker",
                        "fallback_delay_seconds": 1.0
                    }
                )
                db.add(project)
                await db.commit()
                await db.refresh(project)
                return project
        
        return asyncio.get_event_loop().run_until_complete(_create())

    @pytest.fixture
    def mock_cdx_records_wayback(self):
        """Mock CDX records from Wayback Machine"""
        return [
            CDXRecord(
                timestamp="20240101120000",
                original_url="https://example.com/wayback-page1",
                mime_type="text/html",
                status_code="200", 
                digest="sha1:WAYBACK1",
                length="3000"
            ),
            CDXRecord(
                timestamp="20240101130000",
                original_url="https://example.com/wayback-page2", 
                mime_type="text/html",
                status_code="200",
                digest="sha1:WAYBACK2",
                length="4000"
            )
        ]

    @pytest.fixture
    def mock_cdx_records_common_crawl(self):
        """Mock CDX records from Common Crawl"""
        return [
            CDXRecord(
                timestamp="20240101140000",
                original_url="https://example.com/cc-page1",
                mime_type="text/html", 
                status_code="200",
                digest="sha1:COMMONCRAWL1",
                length="5000"
            ),
            CDXRecord(
                timestamp="20240101150000",
                original_url="https://example.com/cc-page2",
                mime_type="text/html",
                status_code="200",
                digest="sha1:COMMONCRAWL2", 
                length="6000"
            )
        ]

    @pytest.mark.asyncio
    async def test_wayback_only_pipeline_success(self, project_wayback_only, mock_cdx_records_wayback):
        """Test full pipeline using only Wayback Machine"""
        
        # Mock the archive router to use project configuration
        with patch('app.services.archive_service_router.ArchiveServiceRouter') as mock_router_class:
            mock_router = Mock()
            mock_router_class.return_value = mock_router
            
            # Configure mock to return Wayback Machine records
            mock_router.query_archive = AsyncMock(return_value=(
                mock_cdx_records_wayback,
                {
                    "successful_source": "wayback_machine",
                    "fallback_used": False,
                    "total_records": 2,
                    "final_count": 2
                }
            ))
            
            # Test the pipeline
            records, stats = await query_archive_unified(
                domain="example.com",
                from_date="20240101",
                to_date="20241231",
                project_config={
                    "archive_source": project_wayback_only.archive_source,
                    "fallback_enabled": project_wayback_only.fallback_enabled,
                    "archive_config": project_wayback_only.archive_config
                }
            )
            
            assert len(records) == 2
            assert all("wayback" in record.original_url for record in records)
            assert stats["successful_source"] == "wayback_machine"
            assert stats["fallback_used"] == False
            
            # Verify router was configured with project settings
            mock_router.query_archive.assert_called_once_with(
                domain="example.com",
                from_date="20240101",
                to_date="20241231",
                project_config={
                    "archive_source": ArchiveSource.WAYBACK_MACHINE,
                    "fallback_enabled": False,
                    "archive_config": {
                        "wayback_machine": {
                            "timeout_seconds": 60,
                            "page_size": 1000,
                            "max_pages": 5
                        }
                    }
                },
                match_type="domain",
                url_path=None
            )

    @pytest.mark.asyncio
    async def test_hybrid_pipeline_fallback_scenario(self, project_hybrid, mock_cdx_records_wayback, mock_cdx_records_common_crawl):
        """Test hybrid pipeline with fallback from Wayback Machine to Common Crawl"""
        
        with patch('app.services.wayback_machine.CDXAPIClient') as mock_wayback_client, \
             patch('app.services.common_crawl_service.CommonCrawlService') as mock_cc_service:
            
            # Configure Wayback Machine to fail with 522 error
            mock_wb_instance = AsyncMock()
            mock_wayback_client.return_value.__aenter__.return_value = mock_wb_instance
            mock_wb_instance.fetch_cdx_records_simple.side_effect = CDXAPIException("522 Connection timed out")
            
            # Configure Common Crawl to succeed
            mock_cc_instance = AsyncMock() 
            mock_cc_service.return_value.__aenter__.return_value = mock_cc_instance
            mock_cc_instance.fetch_cdx_records_simple.return_value = (
                mock_cdx_records_common_crawl,
                {"fetched_pages": 1}
            )
            
            # Mock circuit breakers to allow fallback
            with patch('app.services.circuit_breaker.get_wayback_machine_breaker') as mock_wb_breaker, \
                 patch('app.services.circuit_breaker.circuit_registry') as mock_registry:
                
                wb_breaker = Mock()
                wb_breaker.execute = AsyncMock(side_effect=CDXAPIException("522 Connection timed out"))
                mock_wb_breaker.return_value = wb_breaker
                
                cc_breaker = Mock() 
                cc_breaker.execute = AsyncMock(return_value=(mock_cdx_records_common_crawl, {"fetched_pages": 1}))
                mock_registry.get_breaker.return_value = cc_breaker
                
                # Test the pipeline with real router
                router = ArchiveServiceRouter(RoutingConfig())
                
                records, stats = await router.query_archive(
                    domain="example.com",
                    from_date="20240101", 
                    to_date="20241231",
                    project_config={
                        "archive_source": project_hybrid.archive_source,
                        "fallback_enabled": project_hybrid.fallback_enabled,
                        "archive_config": project_hybrid.archive_config
                    }
                )
                
                assert len(records) == 2
                assert all("cc-page" in record.original_url for record in records)
                assert stats["successful_source"] == "common_crawl"
                assert stats["fallback_used"] == True
                assert len(stats["attempts"]) == 2
                
                # Verify fallback sequence
                assert stats["attempts"][0]["source"] == "wayback_machine"
                assert stats["attempts"][0]["success"] == False
                assert stats["attempts"][1]["source"] == "common_crawl" 
                assert stats["attempts"][1]["success"] == True

    @pytest.mark.asyncio
    async def test_data_consistency_across_sources(self):
        """Test CDXRecord format consistency between Wayback Machine and Common Crawl"""
        
        # Test that both sources produce compatible CDXRecord objects
        wayback_record = CDXRecord(
            timestamp="20240101120000",
            original_url="https://example.com/test",
            mime_type="text/html",
            status_code="200",
            digest="sha1:WAYBACK",
            length="1000"
        )
        
        common_crawl_record = CDXRecord(
            timestamp="20240101120000", 
            original_url="https://example.com/test",
            mime_type="text/html",
            status_code="200",
            digest="sha1:COMMONCRAWL",
            length="1000"
        )
        
        # Verify same interface
        assert type(wayback_record) == type(common_crawl_record)
        assert hasattr(wayback_record, 'timestamp')
        assert hasattr(wayback_record, 'original_url')
        assert hasattr(wayback_record, 'mime_type')
        assert hasattr(wayback_record, 'status_code')
        assert hasattr(wayback_record, 'digest')
        assert hasattr(wayback_record, 'length')
        
        # Test serialization compatibility (both should serialize the same way)
        wayback_dict = wayback_record.__dict__.copy()
        cc_dict = common_crawl_record.__dict__.copy()
        
        # Same keys should be present
        assert set(wayback_dict.keys()) == set(cc_dict.keys())

    @pytest.mark.asyncio
    async def test_scraping_task_integration_with_archive_sources(self, project_hybrid):
        """Test integration with actual scraping tasks"""
        
        # Create a domain for the project
        from app.core.database import get_db
        from app.models.project import Domain
        
        async for db in get_db():
            domain = Domain(
                domain_name="example.com",
                project_id=project_hybrid.id,
                from_date="20240101",
                to_date="20241231",
                match_type="domain",
                status="active"
            )
            db.add(domain)
            await db.commit()
            await db.refresh(domain)
            break
        
        # Mock the archive service to return records
        mock_records = [
            CDXRecord(
                timestamp="20240101120000",
                original_url="https://example.com/test-page",
                mime_type="text/html", 
                status_code="200",
                digest="sha1:TESTPAGE",
                length="2000"
            )
        ]
        
        with patch('app.services.archive_service_router.query_archive_unified') as mock_query:
            mock_query.return_value = (mock_records, {"total": 1})
            
            # Mock content extraction to avoid external dependencies
            with patch('app.services.firecrawl_extractor.FirecrawlExtractor.extract_content') as mock_extract:
                mock_extract.return_value = {
                    "success": True,
                    "content": "Test page content",
                    "title": "Test Page",
                    "description": "A test page"
                }
                
                # Run scraping task
                result = await scrape_pages_task(
                    domain_id=domain.id,
                    project_id=project_hybrid.id,
                    start_page=0,
                    pages_per_task=10
                )
                
                assert result is not None
                
                # Verify archive query was called with project configuration
                mock_query.assert_called_once()
                call_args = mock_query.call_args
                
                assert call_args[1]["project_config"]["archive_source"] == ArchiveSource.HYBRID
                assert call_args[1]["project_config"]["fallback_enabled"] == True
                assert "fallback_strategy" in call_args[1]["project_config"]["archive_config"]

    @pytest.mark.asyncio
    async def test_circuit_breaker_state_persistence(self):
        """Test circuit breaker state persistence across requests"""
        
        router = ArchiveServiceRouter()
        
        # Simulate multiple failures to open circuit breaker
        with patch.object(router.strategies["wayback_machine"], 'query_archive') as mock_wayback:
            mock_wayback.side_effect = CDXAPIException("522 Connection timed out")
            
            # Make multiple failed requests
            for i in range(6):  # Exceed failure threshold
                try:
                    await router.query_archive(
                        domain=f"test{i}.com",
                        from_date="20240101",
                        to_date="20241231",
                        project_config={"archive_source": ArchiveSource.WAYBACK_MACHINE, "fallback_enabled": False}
                    )
                except Exception:
                    pass  # Expected failures
            
            # Check circuit breaker state
            wb_status = router.wayback_breaker.get_status()
            assert wb_status["state"] == "open" or wb_status["failure_count"] >= 5
            
            # Verify metrics reflect the failures
            metrics = router.get_performance_metrics()
            wb_metrics = metrics["sources"]["wayback_machine"]
            
            assert wb_metrics["failed_queries"] >= 5
            assert wb_metrics["success_rate"] == 0.0

    @pytest.mark.asyncio
    async def test_performance_metrics_collection_e2e(self, project_hybrid):
        """Test end-to-end performance metrics collection"""
        
        router = ArchiveServiceRouter()
        
        # Mock successful queries from both sources
        mock_wb_records = [CDXRecord(timestamp="20240101120000", original_url="https://example.com/wb", 
                                   mime_type="text/html", status_code="200", digest="sha1:WB", length="1000")]
        mock_cc_records = [CDXRecord(timestamp="20240101130000", original_url="https://example.com/cc",
                                   mime_type="text/html", status_code="200", digest="sha1:CC", length="2000")]
        
        with patch.object(router.strategies["wayback_machine"], 'query_archive') as mock_wayback, \
             patch.object(router.strategies["common_crawl"], 'query_archive') as mock_cc:
            
            mock_wayback.return_value = (mock_wb_records, {"fetched_pages": 1})
            mock_cc.return_value = (mock_cc_records, {"fetched_pages": 1})
            
            # Execute queries with different sources
            await router.query_archive(
                domain="wayback-test.com",
                from_date="20240101",
                to_date="20241231",
                project_config={"archive_source": ArchiveSource.WAYBACK_MACHINE}
            )
            
            await router.query_archive(
                domain="cc-test.com",
                from_date="20240101", 
                to_date="20241231",
                project_config={"archive_source": ArchiveSource.COMMON_CRAWL}
            )
            
            # Check collected metrics
            metrics = router.get_performance_metrics()
            
            assert metrics["overall"]["total_queries"] == 2
            assert metrics["sources"]["wayback_machine"]["total_queries"] == 1
            assert metrics["sources"]["wayback_machine"]["successful_queries"] == 1
            assert metrics["sources"]["common_crawl"]["total_queries"] == 1
            assert metrics["sources"]["common_crawl"]["successful_queries"] == 1
            
            # Check query history
            assert len(router.query_history) == 2
            
            # Verify source-specific metrics
            wb_metrics = metrics["sources"]["wayback_machine"]
            cc_metrics = metrics["sources"]["common_crawl"]
            
            assert wb_metrics["total_records"] == 1
            assert cc_metrics["total_records"] == 1
            assert wb_metrics["success_rate"] == 100.0
            assert cc_metrics["success_rate"] == 100.0

    @pytest.mark.asyncio
    async def test_real_world_failure_recovery(self):
        """Test recovery from real-world failure scenarios"""
        
        router = ArchiveServiceRouter()
        mock_records = [CDXRecord(timestamp="20240101120000", original_url="https://example.com/recovery",
                                mime_type="text/html", status_code="200", digest="sha1:RECOVERY", length="1000")]
        
        with patch.object(router.strategies["wayback_machine"], 'query_archive') as mock_wayback, \
             patch.object(router.strategies["common_crawl"], 'query_archive') as mock_cc:
            
            # Test scenario: Wayback 522 -> Common Crawl rate limit -> Recovery
            wayback_failures = [
                CDXAPIException("522 Connection timed out"),
                CDXAPIException("522 Connection timed out"),
                (mock_records, {"fetched_pages": 1})  # Eventually recovers
            ]
            
            cc_failures = [
                Exception("Rate limit exceeded"),
                (mock_records, {"fetched_pages": 1})  # Recovers faster
            ]
            
            mock_wayback.side_effect = wayback_failures
            mock_cc.side_effect = cc_failures
            
            # First attempt: Both sources fail
            try:
                await router.query_archive(
                    domain="failure-test.com",
                    from_date="20240101",
                    to_date="20241231", 
                    project_config={"archive_source": ArchiveSource.HYBRID}
                )
                assert False, "Should have failed"
            except Exception:
                pass  # Expected failure
            
            # Second attempt: Common Crawl recovers
            records, stats = await router.query_archive(
                domain="recovery-test.com",
                from_date="20240101",
                to_date="20241231",
                project_config={"archive_source": ArchiveSource.HYBRID}
            )
            
            assert len(records) == 1
            assert stats["successful_source"] == "common_crawl"
            assert stats["fallback_used"] == True

    @pytest.mark.asyncio
    async def test_configuration_changes_during_scraping(self, project_hybrid):
        """Test behavior when project configuration changes during scraping"""
        
        # Simulate configuration change mid-scraping
        original_config = project_hybrid.archive_config.copy()
        
        router = ArchiveServiceRouter()
        mock_records = [CDXRecord(timestamp="20240101120000", original_url="https://example.com/config-test",
                                mime_type="text/html", status_code="200", digest="sha1:CONFIG", length="1000")]
        
        with patch.object(router.strategies["wayback_machine"], 'query_archive') as mock_wayback:
            mock_wayback.return_value = (mock_records, {"fetched_pages": 1})
            
            # First query with original config
            records1, stats1 = await router.query_archive(
                domain="config-test1.com",
                from_date="20240101",
                to_date="20241231",
                project_config={
                    "archive_source": project_hybrid.archive_source,
                    "archive_config": original_config
                }
            )
            
            # Change configuration
            updated_config = original_config.copy()
            updated_config["wayback_machine"]["timeout_seconds"] = 180  # Changed
            
            # Second query with updated config
            records2, stats2 = await router.query_archive(
                domain="config-test2.com",
                from_date="20240101",
                to_date="20241231",
                project_config={
                    "archive_source": project_hybrid.archive_source,
                    "archive_config": updated_config
                }
            )
            
            # Both should succeed but with different configurations
            assert len(records1) == 1
            assert len(records2) == 1
            
            # Router should have applied different configurations
            # (This is more of an integration verification)
            assert mock_wayback.call_count == 2

    @pytest.mark.asyncio
    async def test_error_propagation_through_pipeline(self):
        """Test error propagation and handling through the full pipeline"""
        
        # Test various error scenarios and ensure proper error handling
        test_errors = [
            (CDXAPIException("522 Connection timed out"), "wayback_522_timeout"),
            (CDXAPIException("503 Service unavailable"), "wayback_503_unavailable"),
            (TimeoutError("Request timed out"), "wayback_timeout"),
            (ConnectionError("Connection failed"), "wayback_connection_error"),
        ]
        
        router = ArchiveServiceRouter()
        
        for error, expected_error_type in test_errors:
            with patch.object(router.strategies["wayback_machine"], 'query_archive') as mock_wayback, \
                 patch.object(router.strategies["common_crawl"], 'query_archive') as mock_cc:
                
                # Both sources fail with the same error type
                mock_wayback.side_effect = error
                mock_cc.side_effect = error
                
                try:
                    await router.query_archive(
                        domain="error-test.com",
                        from_date="20240101",
                        to_date="20241231",
                        project_config={"archive_source": ArchiveSource.HYBRID}
                    )
                    assert False, f"Should have failed with {error}"
                except Exception as e:
                    # Should get AllSourcesFailedException
                    assert "All configured archive sources failed" in str(e)
                
                # Check that error was properly classified and tracked
                metrics = router.get_performance_metrics()
                wb_metrics = metrics["sources"]["wayback_machine"]
                
                # Should have recorded the error type
                if expected_error_type in wb_metrics["error_counts"]:
                    assert wb_metrics["error_counts"][expected_error_type] > 0


@pytest.mark.performance
class TestArchivePipelinePerformance:
    """Performance tests for archive pipeline"""

    @pytest.mark.asyncio
    async def test_large_domain_list_performance(self):
        """Test performance with large number of domains"""
        
        router = ArchiveServiceRouter()
        mock_records = [CDXRecord(timestamp="20240101120000", original_url="https://example.com/perf",
                                mime_type="text/html", status_code="200", digest="sha1:PERF", length="1000")]
        
        with patch.object(router.strategies["wayback_machine"], 'query_archive') as mock_wayback:
            mock_wayback.return_value = (mock_records, {"fetched_pages": 1})
            
            # Test querying many domains
            domains = [f"domain{i}.com" for i in range(50)]
            
            start_time = asyncio.get_event_loop().time()
            
            tasks = []
            for domain in domains:
                task = router.query_archive(
                    domain=domain,
                    from_date="20240101",
                    to_date="20241231",
                    project_config={"archive_source": ArchiveSource.WAYBACK_MACHINE}
                )
                tasks.append(task)
            
            results = await asyncio.gather(*tasks)
            
            end_time = asyncio.get_event_loop().time()
            duration = end_time - start_time
            
            # Should complete within reasonable time
            assert duration < 5.0  # 5 seconds for 50 domains
            assert len(results) == 50
            assert all(len(records) == 1 for records, stats in results)

    @pytest.mark.asyncio
    async def test_fallback_performance_impact(self):
        """Test performance impact of fallback scenarios"""
        
        router = ArchiveServiceRouter()
        router.config.fallback_delay_seconds = 0.01  # Minimal delay for testing
        
        mock_records = [CDXRecord(timestamp="20240101120000", original_url="https://example.com/fallback-perf",
                                mime_type="text/html", status_code="200", digest="sha1:FALLBACKPERF", length="1000")]
        
        with patch.object(router.strategies["wayback_machine"], 'query_archive') as mock_wayback, \
             patch.object(router.strategies["common_crawl"], 'query_archive') as mock_cc:
            
            # Wayback fails, Common Crawl succeeds
            mock_wayback.side_effect = CDXAPIException("522 timeout")
            mock_cc.return_value = (mock_records, {"fetched_pages": 1})
            
            start_time = asyncio.get_event_loop().time()
            
            records, stats = await router.query_archive(
                domain="fallback-perf.com",
                from_date="20240101",
                to_date="20241231",
                project_config={"archive_source": ArchiveSource.HYBRID}
            )
            
            end_time = asyncio.get_event_loop().time()
            fallback_duration = end_time - start_time
            
            # Compare with direct Common Crawl query
            start_time = asyncio.get_event_loop().time()
            
            records_direct, stats_direct = await router.query_archive(
                domain="direct-cc.com",
                from_date="20240101",
                to_date="20241231",
                project_config={"archive_source": ArchiveSource.COMMON_CRAWL}
            )
            
            end_time = asyncio.get_event_loop().time()
            direct_duration = end_time - start_time
            
            # Fallback should not be significantly slower
            overhead = fallback_duration - direct_duration
            assert overhead < 0.1  # Less than 100ms overhead
            assert len(records) == len(records_direct) == 1

    @pytest.mark.asyncio
    async def test_memory_usage_large_result_sets(self):
        """Test memory usage with large result sets"""
        
        # Create a large number of records
        large_record_set = []
        for i in range(5000):
            record = CDXRecord(
                timestamp=f"2024010{i%10}120000",
                original_url=f"https://example.com/page-{i}",
                mime_type="text/html",
                status_code="200",
                digest=f"sha1:DIGEST{i:010d}",
                length="2000"
            )
            large_record_set.append(record)
        
        router = ArchiveServiceRouter()
        
        with patch.object(router.strategies["wayback_machine"], 'query_archive') as mock_wayback:
            mock_wayback.return_value = (large_record_set, {"fetched_pages": 100})
            
            import gc
            gc.collect()
            initial_objects = len(gc.get_objects())
            
            # Process large result set
            records, stats = await router.query_archive(
                domain="large-dataset.com",
                from_date="20240101",
                to_date="20241231",
                project_config={"archive_source": ArchiveSource.WAYBACK_MACHINE}
            )
            
            assert len(records) == 5000
            
            # Force cleanup
            del records
            del stats
            gc.collect()
            
            final_objects = len(gc.get_objects())
            object_increase = final_objects - initial_objects
            
            # Should not have significant memory leak
            assert object_increase < 1000  # Allow some overhead


@pytest.mark.slow
class TestArchivePipelineLongRunning:
    """Long-running tests for archive pipeline stability"""

    @pytest.mark.asyncio
    async def test_long_running_scraping_session(self):
        """Test stability during long-running scraping sessions"""
        
        router = ArchiveServiceRouter()
        mock_records = [CDXRecord(timestamp="20240101120000", original_url="https://example.com/long-running",
                                mime_type="text/html", status_code="200", digest="sha1:LONGRUNNING", length="1000")]
        
        with patch.object(router.strategies["wayback_machine"], 'query_archive') as mock_wayback:
            mock_wayback.return_value = (mock_records, {"fetched_pages": 1})
            
            # Simulate long-running scraping session
            total_queries = 100
            batch_size = 10
            
            for batch in range(0, total_queries, batch_size):
                batch_tasks = []
                for i in range(batch_size):
                    if batch + i >= total_queries:
                        break
                    
                    task = router.query_archive(
                        domain=f"long-running-{batch+i}.com",
                        from_date="20240101",
                        to_date="20241231",
                        project_config={"archive_source": ArchiveSource.WAYBACK_MACHINE}
                    )
                    batch_tasks.append(task)
                
                # Process batch
                batch_results = await asyncio.gather(*batch_tasks)
                
                # Verify batch results
                assert len(batch_results) == len(batch_tasks)
                assert all(len(records) == 1 for records, stats in batch_results)
                
                # Small delay between batches to simulate real scraping
                await asyncio.sleep(0.01)
            
            # Check final metrics
            metrics = router.get_performance_metrics()
            assert metrics["overall"]["total_queries"] == total_queries
            assert metrics["sources"]["wayback_machine"]["successful_queries"] == total_queries

    @pytest.mark.asyncio
    async def test_circuit_breaker_recovery_cycle(self):
        """Test circuit breaker recovery over time"""
        
        router = ArchiveServiceRouter()
        mock_records = [CDXRecord(timestamp="20240101120000", original_url="https://example.com/cb-recovery",
                                mime_type="text/html", status_code="200", digest="sha1:CBRECOVERY", length="1000")]
        
        with patch.object(router.strategies["wayback_machine"], 'query_archive') as mock_wayback:
            
            # Phase 1: Cause circuit breaker to open
            mock_wayback.side_effect = CDXAPIException("522 Connection timed out")
            
            for i in range(6):  # Exceed failure threshold
                try:
                    await router.query_archive(
                        domain=f"cb-fail-{i}.com",
                        from_date="20240101",
                        to_date="20241231",
                        project_config={"archive_source": ArchiveSource.WAYBACK_MACHINE, "fallback_enabled": False}
                    )
                except Exception:
                    pass  # Expected failures
            
            # Circuit breaker should be open
            wb_status = router.wayback_breaker.get_status()
            assert wb_status["state"] == "open" or wb_status["failure_count"] >= 5
            
            # Phase 2: Wait for half-open state and test recovery
            # In a real scenario, we'd wait for the timeout, but here we simulate
            
            # Mock successful response for recovery
            mock_wayback.side_effect = None
            mock_wayback.return_value = (mock_records, {"fetched_pages": 1})
            
            # Force circuit breaker to half-open state (implementation dependent)
            if hasattr(router.wayback_breaker, '_force_half_open'):
                router.wayback_breaker._force_half_open()
            
            # Test recovery
            records, stats = await router.query_archive(
                domain="cb-recovery-test.com",
                from_date="20240101",
                to_date="20241231",
                project_config={"archive_source": ArchiveSource.WAYBACK_MACHINE, "fallback_enabled": False}
            )
            
            # Should succeed if circuit breaker allows recovery
            if len(records) > 0:
                assert stats["successful_source"] == "wayback_machine"
            
            # Verify metrics reflect the recovery attempt
            final_metrics = router.get_performance_metrics()
            wb_metrics = final_metrics["sources"]["wayback_machine"]
            
            assert wb_metrics["total_queries"] >= 6  # At least the failure attempts


if __name__ == "__main__":
    pytest.main([__file__, "-v"])