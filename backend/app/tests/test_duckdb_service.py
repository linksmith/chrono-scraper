"""
Tests for DuckDB analytics service
"""
import asyncio
import os
import tempfile
import pytest
import pytest_asyncio
from pathlib import Path
from unittest.mock import Mock, patch, AsyncMock

from app.services.duckdb_service import (
    DuckDBService,
    DuckDBException,
    DuckDBConnectionError,
    DuckDBQueryError,
    DuckDBResourceError,
    QueryResult,
    ConnectionMetrics,
    execute_analytics_query,
    get_service_health
)


@pytest.fixture
def temp_db_path():
    """Create temporary database path for testing"""
    with tempfile.TemporaryDirectory() as temp_dir:
        yield os.path.join(temp_dir, "test_analytics.db")


@pytest.fixture
def mock_settings(temp_db_path):
    """Mock settings for testing"""
    with patch('app.services.duckdb_service.settings') as mock:
        mock.DUCKDB_DATABASE_PATH = temp_db_path
        mock.DUCKDB_MEMORY_LIMIT = "1GB"
        mock.DUCKDB_WORKER_THREADS = 2
        mock.DUCKDB_TEMP_DIRECTORY = tempfile.gettempdir()
        mock.DUCKDB_MAX_MEMORY_PERCENTAGE = 60
        mock.DUCKDB_ENABLE_S3 = False
        mock.AWS_ACCESS_KEY_ID = None
        mock.AWS_SECRET_ACCESS_KEY = None
        mock.AWS_DEFAULT_REGION = "us-east-1"
        yield mock


@pytest_asyncio.fixture
async def duckdb_service(mock_settings):
    """Create and initialize DuckDB service for testing"""
    # Create new service instance for testing
    DuckDBService._instance = None  # Reset singleton
    
    # Reset circuit breaker registry
    from app.services.circuit_breaker import circuit_registry
    circuit_registry.breakers.clear()
    
    service = DuckDBService()
    
    await service.initialize()
    
    # Ensure circuit breaker starts in closed state
    service.circuit_breaker.force_closed("Test initialization")
    
    yield service
    await service.shutdown()


class TestDuckDBService:
    """Test DuckDB service functionality"""
    
    def test_singleton_pattern(self, mock_settings):
        """Test that service follows singleton pattern"""
        # Reset singleton
        DuckDBService._instance = None
        
        service1 = DuckDBService()
        service2 = DuckDBService()
        
        assert service1 is service2
        assert id(service1) == id(service2)
    
    @pytest.mark.asyncio
    async def test_service_initialization(self, duckdb_service):
        """Test service initialization"""
        assert duckdb_service._initialized is True
        assert duckdb_service._connection_pool is not None
        assert duckdb_service._thread_pool is not None
        assert Path(duckdb_service.database_path).exists()
    
    @pytest.mark.asyncio
    async def test_basic_query_execution(self, duckdb_service):
        """Test basic query execution"""
        result = await duckdb_service.execute_query("SELECT 1 as test_value")
        
        assert result is not None
        assert isinstance(result, QueryResult)
        assert result.data == [(1,)]
        assert result.execution_time > 0
        assert result.row_count == 1
        assert result.columns == ['test_value']
    
    @pytest.mark.asyncio
    async def test_query_with_parameters(self, duckdb_service):
        """Test query execution with parameters"""
        result = await duckdb_service.execute_query(
            "SELECT ? as param_value", 
            {'1': 'test_param'}
        )
        
        assert result is not None
        assert result.data == [('test_param',)]
    
    @pytest.mark.asyncio
    async def test_different_fetch_modes(self, duckdb_service):
        """Test different fetch modes"""
        # Create test table
        await duckdb_service.execute_query(
            "CREATE TABLE test_fetch AS SELECT * FROM VALUES (1, 'a'), (2, 'b'), (3, 'c') AS t(id, name)",
            fetch_mode="none"
        )
        
        # Test fetch all
        result = await duckdb_service.execute_query("SELECT * FROM test_fetch", fetch_mode="all")
        assert len(result.data) == 3
        assert result.row_count == 3
        
        # Test fetch one
        result = await duckdb_service.execute_query("SELECT * FROM test_fetch LIMIT 1", fetch_mode="one")
        assert result.row_count == 1
        assert result.data == (1, 'a')
        
        # Test fetch none
        result = await duckdb_service.execute_query("DROP TABLE test_fetch", fetch_mode="none")
        assert result.data is None
    
    @pytest.mark.asyncio
    async def test_batch_execution(self, duckdb_service):
        """Test batch query execution with transactions"""
        queries = [
            "CREATE TABLE test_batch (id INTEGER, name VARCHAR)",
            "INSERT INTO test_batch VALUES (1, 'first')",
            "INSERT INTO test_batch VALUES (2, 'second')",
            "SELECT COUNT(*) FROM test_batch"
        ]
        
        results = await duckdb_service.execute_batch(queries)
        
        assert len(results) == 4
        assert all(isinstance(r, QueryResult) for r in results)
        
        # Last query should return count
        assert results[-1].data == [(2,)]
    
    @pytest.mark.asyncio
    async def test_batch_rollback_on_error(self, duckdb_service):
        """Test that batch execution rolls back on error"""
        queries = [
            "CREATE TABLE test_rollback (id INTEGER PRIMARY KEY)",
            "INSERT INTO test_rollback VALUES (1)",
            "INSERT INTO test_rollback VALUES (1)"  # This will fail due to primary key constraint
        ]
        
        with pytest.raises(DuckDBQueryError):
            await duckdb_service.execute_batch(queries)
        
        # Table should not exist due to rollback
        with pytest.raises(DuckDBQueryError):
            await duckdb_service.execute_query("SELECT COUNT(*) FROM test_rollback")
    
    @pytest.mark.asyncio
    async def test_transaction_context_manager(self, duckdb_service):
        """Test transaction context manager"""
        async with duckdb_service.transaction() as conn:
            # Execute queries within transaction
            await asyncio.get_event_loop().run_in_executor(
                duckdb_service._thread_pool,
                lambda: conn.execute("CREATE TABLE test_tx (id INTEGER)")
            )
            await asyncio.get_event_loop().run_in_executor(
                duckdb_service._thread_pool,
                lambda: conn.execute("INSERT INTO test_tx VALUES (1)")
            )
        
        # Verify transaction was committed
        result = await duckdb_service.execute_query("SELECT COUNT(*) FROM test_tx")
        assert result.data == [(1,)]
    
    @pytest.mark.asyncio
    async def test_transaction_rollback(self, duckdb_service):
        """Test transaction rollback on exception"""
        try:
            async with duckdb_service.transaction() as conn:
                await asyncio.get_event_loop().run_in_executor(
                    duckdb_service._thread_pool,
                    lambda: conn.execute("CREATE TABLE test_rollback_tx (id INTEGER)")
                )
                raise Exception("Test exception")
        except Exception:
            pass
        
        # Table should not exist due to rollback
        with pytest.raises(DuckDBQueryError):
            await duckdb_service.execute_query("SELECT COUNT(*) FROM test_rollback_tx")
    
    @pytest.mark.asyncio
    async def test_health_check(self, duckdb_service):
        """Test health check functionality"""
        health = await duckdb_service.health_check()
        
        assert health["status"] == "healthy"
        assert health["service_initialized"] is True
        assert health["database_exists"] is True
        assert "query_test" in health
        assert health["query_test"]["success"] is True
        assert "metrics" in health
        assert "system" in health
        assert "circuit_breaker" in health
    
    @pytest.mark.asyncio
    async def test_statistics(self, duckdb_service):
        """Test statistics collection"""
        # Execute some queries to generate statistics
        await duckdb_service.execute_query("SELECT 1")
        await duckdb_service.execute_query("SELECT 2")
        
        stats = await duckdb_service.get_statistics()
        
        assert "service" in stats
        assert "metrics" in stats
        assert "performance" in stats
        assert "system" in stats
        assert "circuit_breaker" in stats
        
        assert stats["metrics"]["total_queries"] >= 2
        assert stats["metrics"]["successful_queries"] >= 2
        assert stats["performance"]["success_rate"] > 0
    
    @pytest.mark.asyncio
    async def test_connection_pool(self, duckdb_service):
        """Test connection pooling functionality"""
        # Get multiple connections
        conn1 = await duckdb_service.get_connection()
        conn2 = await duckdb_service.get_connection()
        
        assert conn1 is not None
        assert conn2 is not None
        
        # Return connections
        duckdb_service.return_connection(conn1)
        duckdb_service.return_connection(conn2)
        
        # Pool should have connections available
        assert len(duckdb_service._connection_pool._available_connections) == 2
    
    @pytest.mark.asyncio
    async def test_circuit_breaker_integration(self, duckdb_service):
        """Test circuit breaker integration"""
        # Get circuit breaker status
        cb_status = duckdb_service.circuit_breaker.get_status()
        
        assert cb_status["name"] == "duckdb"
        assert cb_status["state"] == "closed"
        assert cb_status["failure_count"] == 0
    
    @pytest.mark.asyncio 
    async def test_error_handling(self, duckdb_service):
        """Test error handling and classification"""
        # Test syntax error
        with pytest.raises(DuckDBQueryError):
            await duckdb_service.execute_query("INVALID SQL SYNTAX")
        
        # Test table not found
        with pytest.raises(DuckDBQueryError):
            await duckdb_service.execute_query("SELECT * FROM non_existent_table")
    
    @pytest.mark.asyncio
    async def test_metrics_tracking(self, duckdb_service):
        """Test metrics tracking"""
        initial_queries = duckdb_service.metrics.total_queries
        initial_successful = duckdb_service.metrics.successful_queries
        
        # Execute successful query
        await duckdb_service.execute_query("SELECT 1")
        
        assert duckdb_service.metrics.total_queries == initial_queries + 1
        assert duckdb_service.metrics.successful_queries == initial_successful + 1
        assert duckdb_service.metrics.last_query_time is not None
        
        # Execute failed query
        try:
            await duckdb_service.execute_query("INVALID SQL")
        except:
            pass
        
        assert duckdb_service.metrics.failed_queries > 0
    
    @pytest.mark.asyncio
    async def test_parquet_support(self, duckdb_service):
        """Test Parquet file support"""
        # Create a simple table and export to parquet
        await duckdb_service.execute_query(
            "CREATE TABLE test_parquet AS SELECT * FROM VALUES (1, 'test') AS t(id, name)"
        )
        
        temp_parquet = os.path.join(duckdb_service.temp_directory, "test.parquet")
        
        await duckdb_service.execute_query(
            f"COPY test_parquet TO '{temp_parquet}' (FORMAT PARQUET)"
        )
        
        # Verify file was created
        assert Path(temp_parquet).exists()
        
        # Read back from parquet
        result = await duckdb_service.execute_query(
            f"SELECT * FROM parquet_scan('{temp_parquet}')"
        )
        
        assert result.data == [(1, 'test')]
        
        # Cleanup
        Path(temp_parquet).unlink(missing_ok=True)
    
    @pytest.mark.asyncio
    async def test_json_support(self, duckdb_service):
        """Test JSON processing support"""
        # Test JSON extraction
        result = await duckdb_service.execute_query(
            "SELECT json_extract('{\"name\": \"test\", \"value\": 123}', '$.name') as name"
        )
        
        assert result.data == [('test',)]
    
    @pytest.mark.asyncio
    async def test_concurrent_operations(self, duckdb_service):
        """Test concurrent query execution"""
        async def run_query(i):
            return await duckdb_service.execute_query(f"SELECT {i} as value")
        
        # Run multiple queries concurrently
        tasks = [run_query(i) for i in range(5)]
        results = await asyncio.gather(*tasks)
        
        assert len(results) == 5
        assert all(isinstance(r, QueryResult) for r in results)
        
        # Verify each query returned expected result
        for i, result in enumerate(results):
            assert result.data == [(i,)]


class TestUtilityFunctions:
    """Test utility functions"""
    
    @pytest.mark.asyncio
    async def test_execute_analytics_query(self, duckdb_service):
        """Test analytics query utility function"""
        with patch('app.services.duckdb_service.get_duckdb_service', return_value=duckdb_service):
            result = await execute_analytics_query("SELECT 42 as answer")
            assert result == [(42,)]
    
    @pytest.mark.asyncio
    async def test_get_service_health(self, duckdb_service):
        """Test service health utility function"""
        with patch('app.services.duckdb_service.get_duckdb_service', return_value=duckdb_service):
            health = await get_service_health()
            assert health["status"] == "healthy"


class TestErrorScenarios:
    """Test error scenarios and edge cases"""
    
    @pytest.mark.asyncio
    async def test_service_not_initialized(self, mock_settings):
        """Test operations on non-initialized service"""
        service = DuckDBService.__new__(DuckDBService)
        service._instance = None
        service.__init__()
        
        with pytest.raises(DuckDBException, match="Service not initialized"):
            await service.execute_query("SELECT 1")
        
        with pytest.raises(DuckDBException, match="Service not initialized"):
            await service.get_connection()
    
    @pytest.mark.asyncio
    async def test_invalid_database_path(self, mock_settings):
        """Test initialization with invalid database path"""
        mock_settings.DUCKDB_DATABASE_PATH = "/invalid/path/database.db"
        
        service = DuckDBService.__new__(DuckDBService)
        service._instance = None
        service.__init__()
        
        with pytest.raises(DuckDBException, match="Initialization failed"):
            await service.initialize()
    
    @pytest.mark.asyncio
    async def test_memory_limit_handling(self, duckdb_service):
        """Test memory limit configuration"""
        # Test that memory limit is properly set
        result = await duckdb_service.execute_query("SELECT current_setting('memory_limit')")
        
        # Should return some memory limit value
        assert result is not None
        assert result.data is not None
    
    @pytest.mark.asyncio
    async def test_shutdown_twice(self, duckdb_service):
        """Test that shutdown can be called multiple times safely"""
        await duckdb_service.shutdown()
        await duckdb_service.shutdown()  # Should not raise error
        
        assert duckdb_service._initialized is False
        assert duckdb_service._shutdown is True
    
    @pytest.mark.asyncio
    async def test_empty_batch_queries(self, duckdb_service):
        """Test batch execution with empty query list"""
        results = await duckdb_service.execute_batch([])
        assert results == []


class TestConfigurationIntegration:
    """Test configuration integration"""
    
    def test_configuration_loading(self, mock_settings):
        """Test that configuration is properly loaded from settings"""
        service = DuckDBService.__new__(DuckDBService)
        service._instance = None  
        service.__init__()
        
        assert service.database_path == mock_settings.DUCKDB_DATABASE_PATH
        assert service.memory_limit == mock_settings.DUCKDB_MEMORY_LIMIT
        assert service.worker_threads == mock_settings.DUCKDB_WORKER_THREADS
        assert service.temp_directory == mock_settings.DUCKDB_TEMP_DIRECTORY
        assert service.max_memory_percentage == mock_settings.DUCKDB_MAX_MEMORY_PERCENTAGE
        assert service.enable_s3 == mock_settings.DUCKDB_ENABLE_S3
    
    @pytest.mark.asyncio
    async def test_s3_configuration_disabled(self, duckdb_service):
        """Test that S3 is not configured when disabled"""
        # S3 should be disabled in test configuration
        assert duckdb_service.enable_s3 is False


class TestIntegrationScenarios:
    """Integration test scenarios"""
    
    @pytest.mark.asyncio
    async def test_full_analytics_workflow(self, duckdb_service):
        """Test complete analytics workflow"""
        # 1. Create analytics table
        await duckdb_service.execute_query("""
            CREATE TABLE page_analytics AS 
            SELECT * FROM VALUES 
                (1, 'example.com', '2024-01-01', 100),
                (2, 'test.com', '2024-01-02', 150),
                (3, 'example.com', '2024-01-03', 200)
            AS t(id, domain, date, views)
        """)
        
        # 2. Run analytics queries
        daily_stats = await duckdb_service.execute_query("""
            SELECT date, SUM(views) as total_views 
            FROM page_analytics 
            GROUP BY date 
            ORDER BY date
        """)
        
        domain_stats = await duckdb_service.execute_query("""
            SELECT domain, AVG(views) as avg_views 
            FROM page_analytics 
            GROUP BY domain
        """)
        
        # 3. Verify results
        assert len(daily_stats.data) == 3
        assert len(domain_stats.data) == 2
        
        # 4. Export to Parquet
        parquet_path = os.path.join(duckdb_service.temp_directory, "analytics.parquet")
        await duckdb_service.execute_query(
            f"COPY page_analytics TO '{parquet_path}' (FORMAT PARQUET)"
        )
        
        # 5. Read from Parquet and verify
        parquet_result = await duckdb_service.execute_query(
            f"SELECT COUNT(*) FROM parquet_scan('{parquet_path}')"
        )
        
        assert parquet_result.data == [(3,)]
        
        # Cleanup
        Path(parquet_path).unlink(missing_ok=True)
    
    @pytest.mark.asyncio
    async def test_concurrent_analytics_queries(self, duckdb_service):
        """Test concurrent analytics operations"""
        # Create test data
        await duckdb_service.execute_query("""
            CREATE TABLE concurrent_test AS 
            SELECT i, random() as value 
            FROM range(1000) t(i)
        """)
        
        # Define multiple analytics queries
        queries = [
            "SELECT COUNT(*) FROM concurrent_test",
            "SELECT AVG(value) FROM concurrent_test", 
            "SELECT MAX(value) FROM concurrent_test",
            "SELECT MIN(value) FROM concurrent_test",
            "SELECT SUM(value) FROM concurrent_test"
        ]
        
        # Run queries concurrently
        async def run_query(query):
            return await duckdb_service.execute_query(query)
        
        tasks = [run_query(q) for q in queries]
        results = await asyncio.gather(*tasks)
        
        # Verify all queries succeeded
        assert len(results) == 5
        assert all(r is not None for r in results)
        assert all(r.data is not None for r in results)
        
        # Count should be 1000
        assert results[0].data == [(1000,)]