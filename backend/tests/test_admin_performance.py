"""
Performance testing suite for admin bulk operations
Tests performance and scalability of admin features under load
"""
import pytest
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, Any
from fastapi.testclient import TestClient
from sqlmodel import select, func

from app.models.user import User
from app.models.project import Project
from app.models.audit_log import AuditLog
from tests.conftest import AsyncSessionLocal


class TestBulkOperationPerformance:
    """Test performance of bulk operations"""
    
    @pytest.mark.slow
    @pytest.mark.asyncio
    async def test_bulk_user_listing_performance(self, client: TestClient, admin_auth_headers):
        """Test performance of large user list retrieval"""
        # Create test users for performance testing
        await self._create_performance_test_users(100)
        
        # Test various page sizes
        page_sizes = [10, 25, 50, 100]
        
        for page_size in page_sizes:
            start_time = time.time()
            response = client.get(f"/api/v1/admin/users?per_page={page_size}", headers=admin_auth_headers)
            end_time = time.time()
            
            assert response.status_code == 200
            data = response.json()
            
            # Performance assertions
            response_time = end_time - start_time
            assert response_time < 5.0, f"Response time {response_time:.2f}s exceeded 5s for page_size={page_size}"
            
            # Data integrity assertions
            assert len(data["items"]) <= page_size
            assert data["total"] >= 100
            assert data["per_page"] == page_size
            
            print(f"Page size {page_size}: {response_time:.3f}s, {len(data['items'])} items")
    
    @pytest.mark.slow
    @pytest.mark.asyncio
    async def test_user_search_performance(self, client: TestClient, admin_auth_headers):
        """Test performance of user search functionality"""
        await self._create_performance_test_users(200)
        
        search_terms = ["test", "user", "performance", "admin", "research"]
        
        for search_term in search_terms:
            start_time = time.time()
            response = client.get(f"/api/v1/admin/users?search={search_term}&per_page=50", headers=admin_auth_headers)
            end_time = time.time()
            
            assert response.status_code == 200
            response_time = end_time - start_time
            assert response_time < 3.0, f"Search for '{search_term}' took {response_time:.2f}s (> 3s)"
            
            print(f"Search '{search_term}': {response_time:.3f}s")
    
    @pytest.mark.slow
    @pytest.mark.asyncio
    async def test_user_filtering_performance(self, client: TestClient, admin_auth_headers):
        """Test performance of user filtering operations"""
        await self._create_performance_test_users(150)
        
        filters = [
            "approval_status=approved",
            "is_active=true",
            "is_verified=true",
            "approval_status=pending&is_active=true",
            "approval_status=approved&is_verified=true&is_active=true"
        ]
        
        for filter_param in filters:
            start_time = time.time()
            response = client.get(f"/api/v1/admin/users?{filter_param}&per_page=50", headers=admin_auth_headers)
            end_time = time.time()
            
            assert response.status_code == 200
            response_time = end_time - start_time
            assert response_time < 4.0, f"Filter '{filter_param}' took {response_time:.2f}s (> 4s)"
            
            print(f"Filter '{filter_param}': {response_time:.3f}s")
    
    @pytest.mark.slow
    @pytest.mark.asyncio
    async def test_audit_log_retrieval_performance(self, client: TestClient, admin_auth_headers):
        """Test performance of audit log retrieval"""
        # Create test audit logs
        await self._create_performance_audit_logs(500)
        
        # Test different page sizes
        page_sizes = [20, 50, 100]
        
        for page_size in page_sizes:
            start_time = time.time()
            response = client.get(f"/api/v1/admin/audit/logs?per_page={page_size}", headers=admin_auth_headers)
            end_time = time.time()
            
            assert response.status_code == 200
            response_time = end_time - start_time
            assert response_time < 5.0, f"Audit log retrieval took {response_time:.2f}s (> 5s)"
            
            data = response.json()
            assert len(data["items"]) <= page_size
            
            print(f"Audit logs page_size {page_size}: {response_time:.3f}s")
    
    @pytest.mark.slow
    @pytest.mark.asyncio
    async def test_system_metrics_performance(self, client: TestClient, admin_auth_headers):
        """Test performance of system metrics calculation"""
        await self._create_performance_test_data()
        
        # Test multiple calls to ensure consistent performance
        response_times = []
        
        for i in range(10):
            start_time = time.time()
            response = client.get("/api/v1/admin/system/metrics", headers=admin_auth_headers)
            end_time = time.time()
            
            assert response.status_code == 200
            response_time = end_time - start_time
            response_times.append(response_time)
            
            # Each call should be reasonably fast
            assert response_time < 3.0, f"Metrics call {i+1} took {response_time:.2f}s (> 3s)"
        
        avg_response_time = sum(response_times) / len(response_times)
        max_response_time = max(response_times)
        
        print(f"System metrics - Avg: {avg_response_time:.3f}s, Max: {max_response_time:.3f}s")
        
        # Average should be well under 2 seconds
        assert avg_response_time < 2.0
    
    async def _create_performance_test_users(self, count: int):
        """Helper to create users for performance testing"""
        async with AsyncSessionLocal() as session:
            users = []
            for i in range(count):
                user = User(
                    email=f"perfuser{i}@test.com",
                    hashed_password="$2b$12$test_hash",  # Dummy hash for speed
                    full_name=f"Performance Test User {i}",
                    is_active=i % 10 != 0,  # 90% active
                    is_verified=i % 5 != 0,  # 80% verified
                    approval_status="approved" if i % 3 == 0 else "pending",
                    data_handling_agreement=True,
                    ethics_agreement=True,
                    research_interests=f"Performance research {i % 10}",
                    research_purpose=f"Testing purpose {i % 5}",
                    expected_usage="Performance testing"
                )
                users.append(user)
                
                # Batch insert every 50 users
                if len(users) >= 50:
                    session.add_all(users)
                    await session.commit()
                    users = []
            
            # Insert remaining users
            if users:
                session.add_all(users)
                await session.commit()
    
    async def _create_performance_audit_logs(self, count: int):
        """Helper to create audit logs for performance testing"""
        async with AsyncSessionLocal() as session:
            # Get a test admin user
            admin_result = await session.execute(select(User).where(User.is_superuser is True).limit(1))
            admin_user = admin_result.scalar_one_or_none()
            
            if not admin_user:
                # Create admin user if none exists
                admin_user = User(
                    email="perf-admin@test.com",
                    hashed_password="$2b$12$test_hash",
                    full_name="Performance Admin",
                    is_active=True,
                    is_verified=True,
                    is_superuser=True,
                    approval_status="approved",
                    data_handling_agreement=True,
                    ethics_agreement=True,
                    research_interests="Admin work",
                    research_purpose="System administration",
                    expected_usage="Administrative tasks"
                )
                session.add(admin_user)
                await session.commit()
                await session.refresh(admin_user)
            
            logs = []
            actions = ["list_users", "update_user", "create_user", "delete_user", "system_health", "get_metrics"]
            resource_types = ["user", "system", "project", "session"]
            
            for i in range(count):
                log = AuditLog(
                    admin_user_id=admin_user.id,
                    action=actions[i % len(actions)],
                    resource_type=resource_types[i % len(resource_types)],
                    resource_id=str(i) if i % 3 == 0 else None,
                    details={"performance_test": True, "iteration": i},
                    ip_address="127.0.0.1",
                    user_agent="performance-test-agent",
                    success=i % 20 != 0,  # 95% success rate
                    affected_count=1
                )
                logs.append(log)
                
                # Batch insert every 100 logs
                if len(logs) >= 100:
                    session.add_all(logs)
                    await session.commit()
                    logs = []
            
            # Insert remaining logs
            if logs:
                session.add_all(logs)
                await session.commit()
    
    async def _create_performance_test_data(self):
        """Create comprehensive test data for metrics performance testing"""
        # Create users, projects, and pages for realistic metrics
        async with AsyncSessionLocal() as session:
            # Check if data already exists
            user_count = await session.execute(select(func.count(User.id)))
            existing_users = user_count.scalar()
            
            if existing_users < 100:
                await self._create_performance_test_users(100)
            
            # Create projects
            project_count = await session.execute(select(func.count(Project.id)))
            existing_projects = project_count.scalar()
            
            if existing_projects < 50:
                user_result = await session.execute(select(User).limit(10))
                users = user_result.scalars().all()
                
                projects = []
                for i, user in enumerate(users):
                    for j in range(5):  # 5 projects per user
                        project = Project(
                            name=f"Performance Project {i}-{j}",
                            description=f"Project for performance testing {i}-{j}",
                            user_id=user.id
                        )
                        projects.append(project)
                
                session.add_all(projects)
                await session.commit()


class TestConcurrentAdminOperations:
    """Test concurrent access to admin endpoints"""
    
    @pytest.mark.slow
    @pytest.mark.asyncio
    async def test_concurrent_user_list_requests(self, client: TestClient, admin_auth_headers):
        """Test multiple concurrent user list requests"""
        def make_request(thread_id: int) -> Dict[str, Any]:
            start_time = time.time()
            response = client.get(f"/api/v1/admin/users?page={thread_id}&per_page=20", headers=admin_auth_headers)
            end_time = time.time()
            
            return {
                "thread_id": thread_id,
                "status_code": response.status_code,
                "response_time": end_time - start_time,
                "data": response.json() if response.status_code == 200 else None
            }
        
        # Execute 10 concurrent requests
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(make_request, i) for i in range(1, 11)]
            results = [future.result() for future in as_completed(futures)]
        
        # All requests should succeed
        assert all(result["status_code"] == 200 for result in results)
        
        # Calculate performance metrics
        response_times = [result["response_time"] for result in results]
        avg_time = sum(response_times) / len(response_times)
        max_time = max(response_times)
        
        print(f"Concurrent requests - Avg: {avg_time:.3f}s, Max: {max_time:.3f}s")
        
        # No request should take too long
        assert max_time < 10.0
        assert avg_time < 5.0
    
    @pytest.mark.slow
    @pytest.mark.asyncio
    async def test_concurrent_system_health_checks(self, client: TestClient, admin_auth_headers):
        """Test concurrent system health checks"""
        def check_health(thread_id: int) -> Dict[str, Any]:
            start_time = time.time()
            response = client.get("/api/v1/admin/system/health", headers=admin_auth_headers)
            end_time = time.time()
            
            return {
                "thread_id": thread_id,
                "status_code": response.status_code,
                "response_time": end_time - start_time
            }
        
        # Execute 5 concurrent health checks
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(check_health, i) for i in range(5)]
            results = [future.result() for future in as_completed(futures)]
        
        # All health checks should succeed
        assert all(result["status_code"] == 200 for result in results)
        
        # Calculate performance metrics
        response_times = [result["response_time"] for result in results]
        avg_time = sum(response_times) / len(response_times)
        max_time = max(response_times)
        
        print(f"Concurrent health checks - Avg: {avg_time:.3f}s, Max: {max_time:.3f}s")
        
        # Health checks should be fast even under concurrent load
        assert max_time < 5.0
        assert avg_time < 3.0
    
    @pytest.mark.slow
    @pytest.mark.asyncio
    async def test_mixed_concurrent_operations(self, client: TestClient, admin_auth_headers):
        """Test mixed concurrent admin operations"""
        def user_list_request():
            return client.get("/api/v1/admin/users?per_page=25", headers=admin_auth_headers)
        
        def system_health_request():
            return client.get("/api/v1/admin/system/health", headers=admin_auth_headers)
        
        def system_metrics_request():
            return client.get("/api/v1/admin/system/metrics", headers=admin_auth_headers)
        
        def audit_logs_request():
            return client.get("/api/v1/admin/audit/logs?per_page=20", headers=admin_auth_headers)
        
        operations = [
            user_list_request, system_health_request, 
            system_metrics_request, audit_logs_request
        ]
        
        # Execute mixed operations concurrently
        results = []
        start_time = time.time()
        
        with ThreadPoolExecutor(max_workers=8) as executor:
            futures = []
            
            # Submit 8 random operations
            for i in range(8):
                operation = operations[i % len(operations)]
                future = executor.submit(operation)
                futures.append((i, operation.__name__, future))
            
            # Collect results
            for i, op_name, future in futures:
                try:
                    response = future.result(timeout=10)
                    results.append({
                        "operation": op_name,
                        "status_code": response.status_code,
                        "success": response.status_code == 200
                    })
                except Exception as e:
                    results.append({
                        "operation": op_name,
                        "status_code": 500,
                        "success": False,
                        "error": str(e)
                    })
        
        end_time = time.time()
        total_time = end_time - start_time
        
        # All operations should succeed
        success_rate = sum(1 for r in results if r["success"]) / len(results)
        assert success_rate >= 0.9, f"Success rate {success_rate:.2f} below 90%"
        
        # Should complete in reasonable time
        assert total_time < 15.0, f"Mixed operations took {total_time:.2f}s (> 15s)"
        
        print(f"Mixed concurrent operations: {total_time:.3f}s, Success rate: {success_rate:.2%}")


class TestMemoryAndResourceUsage:
    """Test memory usage and resource consumption"""
    
    @pytest.mark.slow
    @pytest.mark.asyncio
    async def test_memory_usage_large_datasets(self, client: TestClient, admin_auth_headers):
        """Test memory usage with large datasets"""
        import psutil
        import os
        
        process = psutil.Process(os.getpid())
        
        # Get baseline memory usage
        baseline_memory = process.memory_info().rss / 1024 / 1024  # MB
        
        # Create large dataset
        await self._create_performance_test_users(500)
        
        # Make requests that handle large datasets
        large_requests = [
            "/api/v1/admin/users?per_page=100",
            "/api/v1/admin/system/metrics",
            "/api/v1/admin/audit/logs?per_page=100"
        ]
        
        for endpoint in large_requests:
            # Measure memory before request
            memory_before = process.memory_info().rss / 1024 / 1024
            
            # Make request
            response = client.get(endpoint, headers=admin_auth_headers)
            assert response.status_code == 200
            
            # Measure memory after request
            memory_after = process.memory_info().rss / 1024 / 1024
            memory_increase = memory_after - memory_before
            
            print(f"Endpoint {endpoint}: Memory increase {memory_increase:.2f} MB")
            
            # Memory increase should be reasonable
            assert memory_increase < 100, f"Memory increase {memory_increase:.2f} MB too high"
        
        # Final memory should not be excessive
        final_memory = process.memory_info().rss / 1024 / 1024
        total_increase = final_memory - baseline_memory
        
        print(f"Total memory increase: {total_increase:.2f} MB")
        assert total_increase < 200, f"Total memory increase {total_increase:.2f} MB excessive"
    
    async def _create_performance_test_users(self, count: int):
        """Helper to create users for performance testing (reused from above)"""
        async with AsyncSessionLocal() as session:
            # Check if users already exist to avoid duplicates
            existing_count = await session.execute(select(func.count(User.id)))
            current_count = existing_count.scalar()
            
            if current_count >= count:
                return  # Already have enough users
            
            users_to_create = count - current_count
            users = []
            
            for i in range(current_count, current_count + users_to_create):
                user = User(
                    email=f"perfuser{i}@test.com",
                    hashed_password="$2b$12$test_hash",
                    full_name=f"Performance Test User {i}",
                    is_active=i % 10 != 0,
                    is_verified=i % 5 != 0,
                    approval_status="approved" if i % 3 == 0 else "pending",
                    data_handling_agreement=True,
                    ethics_agreement=True,
                    research_interests=f"Performance research {i % 10}",
                    research_purpose=f"Testing purpose {i % 5}",
                    expected_usage="Performance testing"
                )
                users.append(user)
                
                # Batch insert every 50 users
                if len(users) >= 50:
                    session.add_all(users)
                    await session.commit()
                    users = []
            
            # Insert remaining users
            if users:
                session.add_all(users)
                await session.commit()


class TestScalabilityLimits:
    """Test system behavior at scale limits"""
    
    @pytest.mark.slow
    @pytest.mark.asyncio
    async def test_maximum_page_size_handling(self, client: TestClient, admin_auth_headers):
        """Test handling of maximum page size requests"""
        # Test various page sizes including edge cases
        page_sizes = [1, 10, 50, 100, 101, 500, 1000]
        
        for page_size in page_sizes:
            response = client.get(f"/api/v1/admin/users?per_page={page_size}", headers=admin_auth_headers)
            
            if page_size <= 100:
                # Should accept reasonable page sizes
                assert response.status_code == 200
                data = response.json()
                assert data["per_page"] <= page_size
            else:
                # Should either cap at max or reject excessive requests
                if response.status_code == 200:
                    data = response.json()
                    assert data["per_page"] <= 100  # Should be capped
                else:
                    assert response.status_code == 422  # Validation error
            
            print(f"Page size {page_size}: Status {response.status_code}")
    
    @pytest.mark.slow
    @pytest.mark.asyncio
    async def test_deep_pagination_performance(self, client: TestClient, admin_auth_headers):
        """Test performance of deep pagination"""
        await self._create_performance_test_users(200)
        
        # Test deep pagination pages
        pages_to_test = [1, 5, 10, 15, 20]
        
        for page in pages_to_test:
            start_time = time.time()
            response = client.get(f"/api/v1/admin/users?page={page}&per_page=10", headers=admin_auth_headers)
            end_time = time.time()
            
            assert response.status_code == 200
            response_time = end_time - start_time
            
            # Deep pages should still be reasonably fast
            assert response_time < 5.0, f"Page {page} took {response_time:.2f}s (> 5s)"
            
            print(f"Page {page}: {response_time:.3f}s")
        
        # Later pages shouldn't be significantly slower than early pages
        # This would indicate pagination performance issues
    
    async def _create_performance_test_users(self, count: int):
        """Helper method (same as above)"""
        async with AsyncSessionLocal() as session:
            existing_count = await session.execute(select(func.count(User.id)))
            current_count = existing_count.scalar()
            
            if current_count >= count:
                return
            
            users_to_create = count - current_count
            users = []
            
            for i in range(current_count, current_count + users_to_create):
                user = User(
                    email=f"scalabilityuser{i}@test.com",
                    hashed_password="$2b$12$test_hash",
                    full_name=f"Scalability Test User {i}",
                    is_active=True,
                    is_verified=True,
                    approval_status="approved",
                    data_handling_agreement=True,
                    ethics_agreement=True,
                    research_interests="Scalability testing",
                    research_purpose="Performance evaluation",
                    expected_usage="Load testing"
                )
                users.append(user)
                
                if len(users) >= 50:
                    session.add_all(users)
                    await session.commit()
                    users = []
            
            if users:
                session.add_all(users)
                await session.commit()


# Cleanup fixture usage
@pytest.mark.asyncio
async def test_performance_cleanup(cleanup_admin_test_data):
    """Cleanup performance test data"""
    # Additional cleanup for performance test data
    async with AsyncSessionLocal() as session:
        await session.execute("DELETE FROM users WHERE email LIKE '%perfuser%@test.com'")
        await session.execute("DELETE FROM users WHERE email LIKE '%scalabilityuser%@test.com'")
        await session.execute("DELETE FROM audit_logs WHERE user_agent = 'performance-test-agent'")
        await session.commit()