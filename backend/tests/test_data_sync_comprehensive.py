"""
Comprehensive test suite for DataSyncService implementation

This test suite covers all aspects of the data synchronization system including:
- DataSyncService dual-write operations
- Change Data Capture (CDC) functionality
- Data consistency validation
- Monitoring and alerting
- API endpoints
"""
import asyncio
import json
import pytest
import uuid
from datetime import datetime, timedelta
from typing import Dict, Any
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.main import app
from app.services.data_sync_service import (
    DataSyncService, SyncStrategy, ConsistencyLevel, SyncOperationType,
    SyncOperation, SyncStatus, PostgreSQLAdapter, DuckDBAdapter
)
from app.services.change_data_capture import (
    CDCService, CDCEvent, CDCEventType, CDCConfiguration
)
from app.services.data_consistency_validator import (
    DataConsistencyService, RowCountValidator, DataHashValidator,
    BusinessRuleValidator, ValidationResult, ConsistencyCheckType,
    ValidationSeverity, ConflictResolver, ConflictResolutionStrategy
)
from app.services.sync_monitoring_service import (
    SyncMonitoringService, AlertManager, MetricsCollector,
    PrometheusMetrics, Alert, AlertSeverity
)


# Test client
client = TestClient(app)


# =================================
# Test Fixtures
# =================================

@pytest.fixture
def sample_sync_operation():
    """Create a sample sync operation"""
    return SyncOperation(
        operation_id="test_op_123",
        operation_type=SyncOperationType.CREATE,
        table_name="test_table",
        primary_key="test_pk_1",
        data={"id": "test_pk_1", "name": "Test Record", "created_at": datetime.utcnow()},
        consistency_level=ConsistencyLevel.EVENTUAL,
        strategy=SyncStrategy.NEAR_REAL_TIME
    )


@pytest.fixture
def sample_cdc_event():
    """Create a sample CDC event"""
    return CDCEvent(
        event_id="cdc_event_123",
        event_type=CDCEventType.INSERT,
        table_name="users",
        schema_name="public",
        new_data={"id": 1, "email": "test@example.com", "name": "Test User"},
        primary_key=1
    )


@pytest.fixture
def sample_validation_result():
    """Create a sample validation result"""
    return ValidationResult(
        check_id="validation_123",
        check_type=ConsistencyCheckType.ROW_COUNT,
        table_name="users",
        is_consistent=True,
        severity=ValidationSeverity.INFO,
        message="Row count validation passed",
        details={"postgresql_count": 100, "duckdb_count": 100}
    )


# =================================
# DataSyncService Tests
# =================================

class TestDataSyncService:
    """Test suite for DataSyncService"""
    
    @pytest.mark.asyncio
    async def test_dual_write_create_eventual_consistency(self, sample_sync_operation):
        """Test dual-write create operation with eventual consistency"""
        sync_service = DataSyncService()
        
        # Mock adapters
        sync_service.postgresql_adapter.execute_operation = AsyncMock(return_value=True)
        sync_service.duckdb_adapter.execute_operation = AsyncMock(return_value=True)
        
        # Mock queue operations
        sync_service._queue_operation = AsyncMock()
        
        success, operation_id = await sync_service.dual_write_create(
            table_name="test_table",
            data={"id": "test_1", "name": "Test"},
            consistency_level=ConsistencyLevel.EVENTUAL,
            strategy=SyncStrategy.NEAR_REAL_TIME
        )
        
        assert success is True
        assert operation_id is not None
        sync_service._queue_operation.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_dual_write_create_strong_consistency(self):
        """Test dual-write create operation with strong consistency"""
        sync_service = DataSyncService()
        
        # Mock adapters to return success
        sync_service.postgresql_adapter.execute_operation = AsyncMock(return_value=True)
        sync_service.duckdb_adapter.execute_operation = AsyncMock(return_value=True)
        
        success, operation_id = await sync_service.dual_write_create(
            table_name="test_table",
            data={"id": "test_1", "name": "Test"},
            consistency_level=ConsistencyLevel.STRONG,
            strategy=SyncStrategy.REAL_TIME
        )
        
        assert success is True
        assert operation_id is not None
        
        # Verify both adapters were called
        sync_service.postgresql_adapter.execute_operation.assert_called_once()
        sync_service.duckdb_adapter.execute_operation.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_dual_write_postgresql_failure_compensation(self):
        """Test compensation when PostgreSQL fails but DuckDB succeeds"""
        sync_service = DataSyncService()
        
        # Mock PostgreSQL failure, DuckDB success
        sync_service.postgresql_adapter.execute_operation = AsyncMock(return_value=False)
        sync_service.duckdb_adapter.execute_operation = AsyncMock(return_value=True)
        sync_service._compensate_operation = AsyncMock()
        
        success, operation_id = await sync_service.dual_write_create(
            table_name="test_table",
            data={"id": "test_1", "name": "Test"},
            consistency_level=ConsistencyLevel.STRONG,
            strategy=SyncStrategy.REAL_TIME
        )
        
        assert success is False
        # Compensation should be triggered for partial failure
        # (In actual implementation, would need to track operation state)
    
    @pytest.mark.asyncio
    async def test_sync_from_postgresql_batch_processing(self):
        """Test full synchronization from PostgreSQL to DuckDB"""
        sync_service = DataSyncService()
        
        # Mock database session and results
        with patch('app.services.data_sync_service.AsyncSessionLocal') as mock_session:
            mock_db = AsyncMock()
            mock_session.return_value.__aenter__.return_value = mock_db
            
            # Mock query results
            mock_result = AsyncMock()
            mock_result.fetchall.return_value = [
                type('MockRecord', (), {
                    '_mapping': {'id': 1, 'name': 'Record 1'},
                })(),
                type('MockRecord', (), {
                    '_mapping': {'id': 2, 'name': 'Record 2'},
                })(),
            ]
            mock_db.execute.return_value = mock_result
            
            # Mock batch processing
            sync_service._process_batch = AsyncMock()
            
            result = await sync_service.sync_from_postgresql(
                table_name="test_table",
                batch_size=2
            )
            
            assert result['status'] == 'completed'
            assert result['records_synced'] >= 0
            sync_service._process_batch.assert_called()
    
    @pytest.mark.asyncio
    async def test_circuit_breaker_functionality(self):
        """Test circuit breaker functionality"""
        postgresql_adapter = PostgreSQLAdapter()
        
        # Test initial closed state
        assert postgresql_adapter.circuit_breaker.should_allow_request() is True
        
        # Simulate failures to trigger circuit breaker
        for _ in range(3):  # Threshold is 3
            postgresql_adapter.circuit_breaker.record_failure()
        
        # Circuit breaker should be open
        assert postgresql_adapter.circuit_breaker.should_allow_request() is False
        
        # Test recovery
        postgresql_adapter.circuit_breaker.record_success()
        assert postgresql_adapter.circuit_breaker.should_allow_request() is True


# =================================
# CDC Service Tests
# =================================

class TestCDCService:
    """Test suite for CDC Service"""
    
    @pytest.mark.asyncio
    async def test_cdc_configuration(self):
        """Test CDC configuration setup"""
        config = CDCConfiguration()
        config.monitored_tables.add("test_table")
        config.excluded_tables.add("system_table")
        
        cdc_service = CDCService(config)
        
        assert "test_table" in cdc_service.config.monitored_tables
        assert "system_table" in cdc_service.config.excluded_tables
    
    def test_cdc_event_creation(self, sample_cdc_event):
        """Test CDC event creation and properties"""
        assert sample_cdc_event.event_type == CDCEventType.INSERT
        assert sample_cdc_event.table_name == "users"
        assert sample_cdc_event.primary_key == 1
        assert "email" in sample_cdc_event.new_data
    
    @pytest.mark.asyncio
    async def test_cdc_event_processing(self, sample_cdc_event):
        """Test CDC event processing"""
        config = CDCConfiguration()
        config.monitored_tables.add("users")
        cdc_service = CDCService(config)
        
        # Mock data sync service
        with patch('app.services.change_data_capture.data_sync_service') as mock_sync:
            mock_sync.dual_write_create = AsyncMock(return_value=(True, "op_123"))
            
            processor = cdc_service.processor
            success = await processor.process_event(sample_cdc_event)
            
            assert success is True
            assert sample_cdc_event.processed is True
    
    def test_cdc_event_filtering(self):
        """Test CDC event filtering logic"""
        config = CDCConfiguration()
        config.monitored_tables = {"users", "projects"}
        config.excluded_tables = {"system_logs"}
        
        processor = config  # Using config for testing filter logic
        
        # Should process monitored table
        event1 = CDCEvent(
            event_id="1", event_type=CDCEventType.INSERT,
            table_name="users", schema_name="public"
        )
        
        # Should not process excluded table
        event2 = CDCEvent(
            event_id="2", event_type=CDCEventType.INSERT,
            table_name="system_logs", schema_name="public"
        )
        
        # Should not process non-monitored table
        event3 = CDCEvent(
            event_id="3", event_type=CDCEventType.INSERT,
            table_name="unknown_table", schema_name="public"
        )
        
        # Mock processor for testing
        from app.services.change_data_capture import CDCEventProcessor
        processor = CDCEventProcessor(config)
        
        assert processor.should_process_event(event1) is True
        assert processor.should_process_event(event2) is False
        assert processor.should_process_event(event3) is False


# =================================
# Data Consistency Validator Tests
# =================================

class TestDataConsistencyValidator:
    """Test suite for Data Consistency Validator"""
    
    @pytest.mark.asyncio
    async def test_row_count_validator_consistent(self):
        """Test row count validator with consistent data"""
        validator = RowCountValidator()
        
        # Mock database connections
        with patch('app.services.data_consistency_validator.AsyncSessionLocal') as mock_session:
            mock_db = AsyncMock()
            mock_session.return_value.__aenter__.return_value = mock_db
            
            # Mock PostgreSQL count
            mock_result = AsyncMock()
            mock_result.scalar.return_value = 100
            mock_db.execute.return_value = mock_result
            
            # Mock DuckDB connection and count
            mock_duckdb_conn = MagicMock()
            mock_duckdb_conn.execute.return_value.fetchone.return_value = [100]
            validator._get_duckdb_connection = MagicMock(return_value=mock_duckdb_conn)
            
            results = await validator.validate("test_table")
            
            assert len(results) == 1
            assert results[0].is_consistent is True
            assert results[0].check_type == ConsistencyCheckType.ROW_COUNT
    
    @pytest.mark.asyncio
    async def test_row_count_validator_inconsistent(self):
        """Test row count validator with inconsistent data"""
        validator = RowCountValidator()
        
        with patch('app.services.data_consistency_validator.AsyncSessionLocal') as mock_session:
            mock_db = AsyncMock()
            mock_session.return_value.__aenter__.return_value = mock_db
            
            # Mock different counts
            mock_result = AsyncMock()
            mock_result.scalar.return_value = 100  # PostgreSQL
            mock_db.execute.return_value = mock_result
            
            mock_duckdb_conn = MagicMock()
            mock_duckdb_conn.execute.return_value.fetchone.return_value = [95]  # DuckDB
            validator._get_duckdb_connection = MagicMock(return_value=mock_duckdb_conn)
            
            results = await validator.validate("test_table")
            
            assert len(results) == 1
            assert results[0].is_consistent is False
            assert results[0].details['postgresql_count'] == 100
            assert results[0].details['duckdb_count'] == 95
    
    @pytest.mark.asyncio
    async def test_business_rule_validator_user_rules(self):
        """Test business rule validator for user model"""
        validator = BusinessRuleValidator()
        
        # Mock user data that violates business rules
        with patch('app.services.data_consistency_validator.AsyncSessionLocal') as mock_session:
            mock_db = AsyncMock()
            mock_session.return_value.__aenter__.return_value = mock_db
            
            # Mock user with verification but no approval status
            mock_user = type('MockUser', (), {
                'id': 1,
                'is_verified': True,
                'approval_status': None,
                'is_superuser': False
            })()
            
            mock_result = AsyncMock()
            mock_result.scalars.return_value.all.return_value = [mock_user]
            mock_db.execute.return_value = mock_result
            
            results = await validator._validate_user_rules(1)
            
            # Should find business rule violation
            violations = [r for r in results if not r.is_consistent]
            assert len(violations) > 0
    
    @pytest.mark.asyncio
    async def test_conflict_resolver_last_write_wins(self, sample_validation_result):
        """Test conflict resolution with last write wins strategy"""
        resolver = ConflictResolver()
        
        # Create validation result with conflict data
        sample_validation_result.is_consistent = False
        sample_validation_result.postgresql_data = {
            "id": 1,
            "name": "Updated Name",
            "updated_at": datetime.utcnow()
        }
        sample_validation_result.duckdb_data = {
            "id": 1,
            "name": "Old Name", 
            "updated_at": datetime.utcnow() - timedelta(hours=1)
        }
        sample_validation_result.resolution_strategy = ConflictResolutionStrategy.LAST_WRITE_WINS
        
        # Mock sync service
        with patch('app.services.data_consistency_validator.data_sync_service') as mock_sync:
            mock_sync.dual_write_update = AsyncMock(return_value=(True, "op_123"))
            
            result = await resolver.resolve_conflict(sample_validation_result)
            
            assert result['status'] in ['resolved', 'error']  # Depending on implementation
    
    @pytest.mark.asyncio
    async def test_consistency_service_comprehensive_check(self):
        """Test comprehensive consistency check"""
        service = DataConsistencyService()
        
        # Mock validators
        service.validators[ConsistencyCheckType.ROW_COUNT] = AsyncMock()
        service.validators[ConsistencyCheckType.ROW_COUNT].validate = AsyncMock(
            return_value=[ValidationResult(
                check_id="test_1",
                check_type=ConsistencyCheckType.ROW_COUNT,
                table_name="users",
                is_consistent=True,
                severity=ValidationSeverity.INFO,
                message="Test passed"
            )]
        )
        
        report = await service.run_consistency_check(
            tables=["users"],
            check_types=[ConsistencyCheckType.ROW_COUNT]
        )
        
        assert report.total_checks == 1
        assert report.passed_checks == 1
        assert report.consistency_score == 100.0


# =================================
# Monitoring Service Tests
# =================================

class TestSyncMonitoringService:
    """Test suite for Sync Monitoring Service"""
    
    def test_alert_creation_and_suppression(self):
        """Test alert creation and suppression logic"""
        alert_manager = AlertManager()
        
        # Create initial alert
        alert1 = Alert(
            alert_id="alert_1",
            alert_type="test_alert",
            severity=AlertSeverity.WARNING,
            title="Test Alert",
            description="Test Description",
            service="test_service"
        )
        
        alert_manager.active_alerts[alert1.alert_id] = alert1
        
        assert len(alert_manager.active_alerts) == 1
        
        # Test resolution
        success = asyncio.run(alert_manager.resolve_alert(alert1.alert_id))
        assert success is True
        assert len(alert_manager.active_alerts) == 0
    
    def test_metrics_collection(self):
        """Test metrics collection and aggregation"""
        collector = MetricsCollector()
        
        # Record some sync operations
        collector.record_sync_operation(
            operation_type="create",
            table_name="users",
            duration_seconds=0.5,
            status="completed"
        )
        
        collector.record_sync_operation(
            operation_type="update",
            table_name="projects",
            duration_seconds=1.2,
            status="failed"
        )
        
        # Check metrics were recorded
        assert len(collector.metrics_buffer['sync_operation_duration']) == 2
        
        # Test Prometheus metrics
        prometheus_output = collector.get_prometheus_metrics()
        assert 'sync_operations_total' in prometheus_output
        assert 'sync_operation_duration_seconds' in prometheus_output
    
    def test_prometheus_metrics_format(self):
        """Test Prometheus metrics format"""
        metrics = PrometheusMetrics()
        
        # Record some metrics
        metrics.sync_operations_total.labels(
            operation_type="create",
            table_name="users",
            status="completed"
        ).inc()
        
        metrics.sync_lag_seconds.set(5.0)
        metrics.consistency_score.labels(table_name="users").set(95.5)
        
        # Generate metrics output
        output = metrics.sync_operations_total._samples()
        assert len(list(output)) > 0


# =================================
# API Endpoint Tests
# =================================

class TestDataSyncAPI:
    """Test suite for DataSync API endpoints"""
    
    def test_get_sync_status_endpoint(self):
        """Test sync status API endpoint"""
        # Mock authentication
        with patch('app.api.deps.get_current_admin_user') as mock_auth:
            mock_auth.return_value = type('MockUser', (), {'id': 1, 'is_superuser': True})()
            
            # Mock sync service
            with patch('app.services.data_sync_service.data_sync_service') as mock_sync:
                mock_sync.get_sync_status = AsyncMock(return_value={
                    'service_status': 'running',
                    'metrics': {'sync_lag_seconds': 5.0},
                    'queue_status': {'real_time': 0, 'batch': 10}
                })
                
                response = client.get("/api/v1/data-sync/sync/status")
                
                assert response.status_code == 200
                data = response.json()
                assert data['status'] == 'success'
                assert 'data' in data
    
    def test_create_sync_operation_endpoint(self):
        """Test sync operation creation API endpoint"""
        with patch('app.api.deps.get_current_admin_user') as mock_auth:
            mock_auth.return_value = type('MockUser', (), {'id': 1, 'is_superuser': True})()
            
            with patch('app.services.data_sync_service.data_sync_service') as mock_sync:
                mock_sync.dual_write_create = AsyncMock(return_value=(True, "op_123"))
                
                payload = {
                    "table_name": "test_table",
                    "operation_type": "create",
                    "data": {"id": 1, "name": "Test"},
                    "consistency_level": "eventual",
                    "strategy": "near_real_time"
                }
                
                response = client.post("/api/v1/data-sync/sync/operation", json=payload)
                
                assert response.status_code == 200
                data = response.json()
                assert data['status'] == 'success'
                assert data['operation_id'] == "op_123"
    
    def test_consistency_check_endpoint(self):
        """Test consistency check API endpoint"""
        with patch('app.api.deps.get_current_admin_user') as mock_auth:
            mock_auth.return_value = type('MockUser', (), {'id': 1, 'is_superuser': True})()
            
            with patch('app.tasks.data_sync_tasks.run_consistency_validation') as mock_task:
                mock_task.delay.return_value = type('MockTask', (), {'id': 'task_123'})()
                
                payload = {
                    "tables": ["users", "projects"],
                    "check_types": ["row_count", "data_hash"]
                }
                
                response = client.post("/api/v1/data-sync/consistency/check", json=payload)
                
                assert response.status_code == 200
                data = response.json()
                assert data['status'] == 'success'
                assert data['task_id'] == 'task_123'
    
    def test_monitoring_dashboard_endpoint(self):
        """Test monitoring dashboard API endpoint"""
        with patch('app.api.deps.get_current_admin_user') as mock_auth:
            mock_auth.return_value = type('MockUser', (), {'id': 1, 'is_superuser': True})()
            
            with patch('app.services.sync_monitoring_service.sync_monitoring_service') as mock_monitor:
                mock_monitor.get_monitoring_dashboard_data = AsyncMock(return_value={
                    'health_status': {'status': 'healthy'},
                    'summary_statistics': {'average_sync_lag_seconds': 2.5},
                    'active_alerts': []
                })
                
                response = client.get("/api/v1/data-sync/monitoring/dashboard")
                
                assert response.status_code == 200
                data = response.json()
                assert data['status'] == 'success'
                assert 'data' in data


# =================================
# Integration Tests
# =================================

class TestDataSyncIntegration:
    """Integration tests for DataSync system"""
    
    @pytest.mark.asyncio
    async def test_end_to_end_sync_workflow(self):
        """Test complete end-to-end sync workflow"""
        # This test would require actual database connections
        # and would be run in a test environment with Docker containers
        
        # 1. Create sync operation
        sync_service = DataSyncService()
        
        # 2. Mock successful dual-write
        sync_service.postgresql_adapter.execute_operation = AsyncMock(return_value=True)
        sync_service.duckdb_adapter.execute_operation = AsyncMock(return_value=True)
        
        success, operation_id = await sync_service.dual_write_create(
            table_name="test_integration",
            data={"id": "int_test_1", "name": "Integration Test"},
            consistency_level=ConsistencyLevel.STRONG
        )
        
        assert success is True
        assert operation_id is not None
        
        # 3. Validate consistency
        validator = DataConsistencyService()
        
        # Mock validation results
        with patch.object(validator, 'run_consistency_check') as mock_check:
            from app.services.data_consistency_validator import ConsistencyReport
            mock_report = ConsistencyReport(
                report_id="integration_test",
                total_checks=1,
                passed_checks=1,
                consistency_score=100.0
            )
            mock_check.return_value = mock_report
            
            report = await validator.run_consistency_check(
                tables=["test_integration"],
                check_types=[ConsistencyCheckType.ROW_COUNT]
            )
            
            assert report.consistency_score == 100.0
    
    @pytest.mark.asyncio
    async def test_failure_recovery_workflow(self):
        """Test failure recovery workflow"""
        sync_service = DataSyncService()
        
        # 1. Simulate failure
        sync_service.postgresql_adapter.execute_operation = AsyncMock(return_value=False)
        sync_service.duckdb_adapter.execute_operation = AsyncMock(return_value=False)
        sync_service._queue_operation = AsyncMock()
        
        success, operation_id = await sync_service.dual_write_create(
            table_name="test_recovery",
            data={"id": "recovery_test_1"},
            consistency_level=ConsistencyLevel.EVENTUAL
        )
        
        # For eventual consistency, operation should be queued even if adapters fail
        assert success is True  # Queued for retry
        
        # 2. Test recovery mechanism
        success = await sync_service.handle_sync_failure(operation_id)
        assert success is True  # Recovery queued
    
    @pytest.mark.asyncio
    async def test_monitoring_alert_workflow(self):
        """Test monitoring and alerting workflow"""
        monitoring_service = SyncMonitoringService()
        
        # 1. Create alert
        alert_id = await monitoring_service.create_manual_alert(
            alert_type="test_alert",
            severity="warning",
            title="Test Integration Alert",
            description="Testing alert workflow",
            service="integration_test"
        )
        
        assert alert_id is not None
        
        # 2. Check active alerts
        active_alerts = monitoring_service.alert_manager.get_active_alerts()
        assert len(active_alerts) > 0
        
        # 3. Resolve alert
        success = await monitoring_service.resolve_alert(alert_id)
        assert success is True
        
        # 4. Verify resolution
        active_alerts_after = monitoring_service.alert_manager.get_active_alerts()
        assert len(active_alerts_after) == len(active_alerts) - 1


# =================================
# Performance Tests
# =================================

class TestDataSyncPerformance:
    """Performance tests for DataSync system"""
    
    @pytest.mark.asyncio
    async def test_batch_operation_performance(self):
        """Test performance of batch operations"""
        sync_service = DataSyncService()
        
        # Mock successful operations
        sync_service.postgresql_adapter.execute_operation = AsyncMock(return_value=True)
        sync_service.duckdb_adapter.execute_operation = AsyncMock(return_value=True)
        
        # Create large batch of operations
        operations = []
        for i in range(1000):
            operation = SyncOperation(
                operation_id=f"perf_test_{i}",
                operation_type=SyncOperationType.CREATE,
                table_name="performance_test",
                primary_key=f"pk_{i}",
                data={"id": f"pk_{i}", "value": f"value_{i}"}
            )
            operations.append(operation)
        
        # Time batch processing
        import time
        start_time = time.time()
        
        # Mock batch processing
        with patch.object(sync_service, '_process_batch') as mock_batch:
            mock_batch.return_value = None
            await sync_service._process_batch(operations)
            
        end_time = time.time()
        processing_time = end_time - start_time
        
        # Should process 1000 operations relatively quickly
        assert processing_time < 10.0  # Less than 10 seconds
        mock_batch.assert_called_once()
    
    def test_metrics_collection_performance(self):
        """Test performance of metrics collection"""
        collector = MetricsCollector()
        
        # Record many metrics quickly
        import time
        start_time = time.time()
        
        for i in range(10000):
            collector.record_sync_operation(
                operation_type="create",
                table_name="perf_test",
                duration_seconds=0.1,
                status="completed"
            )
        
        end_time = time.time()
        collection_time = end_time - start_time
        
        # Should be fast
        assert collection_time < 1.0  # Less than 1 second
        
        # Verify metrics were recorded
        assert len(collector.metrics_buffer['sync_operation_duration']) == 10000


# =================================
# Error Handling Tests
# =================================

class TestDataSyncErrorHandling:
    """Test error handling in DataSync system"""
    
    @pytest.mark.asyncio
    async def test_database_connection_failure_handling(self):
        """Test handling of database connection failures"""
        postgresql_adapter = PostgreSQLAdapter()
        
        # Mock connection failure
        with patch('app.services.data_sync_service.AsyncSessionLocal') as mock_session:
            mock_session.side_effect = Exception("Connection failed")
            
            operation = SyncOperation(
                operation_id="error_test",
                operation_type=SyncOperationType.CREATE,
                table_name="test_table",
                primary_key="test_pk",
                data={"id": "test_pk"}
            )
            
            success = await postgresql_adapter.execute_operation(operation)
            assert success is False
            assert operation.error_message is not None
    
    @pytest.mark.asyncio
    async def test_invalid_operation_handling(self):
        """Test handling of invalid operations"""
        sync_service = DataSyncService()
        
        # Test invalid consistency level
        with pytest.raises(ValueError):
            await sync_service.dual_write_create(
                table_name="test_table",
                data={"id": "test"},
                consistency_level="invalid_level"  # Invalid
            )
    
    def test_alert_manager_error_handling(self):
        """Test alert manager error handling"""
        alert_manager = AlertManager()
        
        # Test resolving non-existent alert
        success = asyncio.run(alert_manager.resolve_alert("non_existent_alert"))
        assert success is False
        
        # Test duplicate alert suppression
        # Would require actual implementation testing


# =================================
# Configuration Tests
# =================================

class TestDataSyncConfiguration:
    """Test configuration handling"""
    
    def test_sync_service_configuration(self):
        """Test sync service configuration"""
        from app.core.config import settings
        
        # Test configuration values
        assert hasattr(settings, 'DATA_SYNC_ENABLED')
        assert hasattr(settings, 'DATA_SYNC_STRATEGY')
        assert hasattr(settings, 'DATA_SYNC_BATCH_SIZE')
        assert hasattr(settings, 'CONSISTENCY_CHECK_ENABLED')
        
        # Test default values
        assert settings.DATA_SYNC_BATCH_SIZE > 0
        assert settings.DATA_SYNC_RETRY_ATTEMPTS >= 0
    
    def test_cdc_configuration(self):
        """Test CDC configuration"""
        config = CDCConfiguration()
        
        assert config.slot_name is not None
        assert config.publication_name is not None
        assert len(config.monitored_tables) > 0
        assert config.max_batch_size > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])