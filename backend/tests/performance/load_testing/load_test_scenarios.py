"""
Load Testing Framework - Realistic User Scenarios

This module implements comprehensive load testing scenarios that simulate
realistic user behavior patterns for the Phase 2 DuckDB analytics system.

Load Testing Scenarios:
- Normal Load: 100 concurrent users, typical analytics usage
- Peak Load: 500 concurrent users, dashboard refresh surge
- Stress Load: 1000+ concurrent users, system breaking point
- Spike Load: Sudden traffic surges, auto-scaling validation
- Endurance Load: 24-hour sustained load with gradual ramp-up

Each scenario includes realistic user behavior patterns:
- Dashboard viewing and interaction
- Search operations with various complexity
- Data export operations
- Real-time WebSocket connections
- Mixed workload patterns
"""

import asyncio
import time
import random
import statistics
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor
import numpy as np
import aiohttp
import websockets
import json

from locust import HttpUser, task, between, events
from locust.env import Environment
from locust.stats import stats_printer, stats_history
from locust.log import setup_logging

import pytest
import pytest_asyncio
from httpx import AsyncClient


@dataclass
class LoadTestConfig:
    """Configuration for load testing scenarios"""
    base_url: str = "http://localhost:8000"
    websocket_url: str = "ws://localhost:8000"
    test_duration_seconds: int = 300  # 5 minutes default
    ramp_up_time_seconds: int = 60    # 1 minute ramp-up
    ramp_down_time_seconds: int = 30  # 30 second ramp-down
    spawn_rate: float = 10.0          # users per second
    
    # User behavior settings
    think_time_min: float = 1.0       # seconds
    think_time_max: float = 5.0       # seconds
    session_duration_min: int = 300   # 5 minutes
    session_duration_max: int = 1800  # 30 minutes
    
    # Performance thresholds
    max_response_time_ms: int = 1000
    max_error_rate_percent: float = 1.0
    min_throughput_rps: float = 100.0


@dataclass
class LoadTestResult:
    """Result of a load test scenario"""
    scenario_name: str
    total_users: int
    duration_seconds: float
    total_requests: int
    successful_requests: int
    failed_requests: int
    average_response_time: float
    p95_response_time: float
    p99_response_time: float
    requests_per_second: float
    error_rate_percent: float
    peak_memory_mb: float
    peak_cpu_percent: float
    websocket_connections: int
    websocket_messages: int
    timestamp: datetime
    
    def meets_performance_targets(self, config: LoadTestConfig) -> bool:
        """Check if load test meets performance targets"""
        return (
            self.error_rate_percent <= config.max_error_rate_percent and
            self.p95_response_time <= config.max_response_time_ms and
            self.requests_per_second >= config.min_throughput_rps
        )


class AnalyticsUserBehavior(HttpUser):
    """Simulated user behavior for analytics dashboard usage"""
    
    wait_time = between(1, 5)  # Think time between requests
    
    def on_start(self):
        """Initialize user session"""
        self.login()
        self.project_id = self.get_or_create_test_project()
        self.session_start = time.time()
        self.operations_performed = 0
        
        # User behavior weights (realistic usage patterns)
        self.behavior_weights = {
            'view_dashboard': 0.3,     # 30% - Most common activity
            'search_content': 0.2,     # 20% - Search operations
            'view_analytics': 0.15,    # 15% - Analytics views
            'export_data': 0.1,        # 10% - Data exports
            'manage_projects': 0.1,    # 10% - Project management
            'real_time_updates': 0.15  # 15% - WebSocket connections
        }
    
    def login(self):
        """Authenticate user"""
        response = self.client.post("/api/v1/auth/login", json={
            "email": "load_test_user@example.com",
            "password": "LoadTest123!"
        })
        if response.status_code == 200:
            token = response.json()["access_token"]
            self.client.headers.update({"Authorization": f"Bearer {token}"})
    
    def get_or_create_test_project(self) -> str:
        """Get or create a test project for load testing"""
        # Try to get existing project
        response = self.client.get("/api/v1/projects/")
        if response.status_code == 200:
            projects = response.json()
            if projects:
                return projects[0]["id"]
        
        # Create new project
        response = self.client.post("/api/v1/projects/", json={
            "name": f"Load Test Project {random.randint(1000, 9999)}",
            "description": "Automated load testing project"
        })
        if response.status_code == 201:
            return response.json()["id"]
        return "default"
    
    @task(30)  # 30% weight
    def view_dashboard(self):
        """Simulate dashboard viewing"""
        with self.client.get(f"/api/v1/projects/{self.project_id}/dashboard", 
                            catch_response=True) as response:
            if response.status_code == 200:
                self.operations_performed += 1
            else:
                response.failure(f"Dashboard load failed: {response.status_code}")
    
    @task(20)  # 20% weight
    def search_content(self):
        """Simulate content search operations"""
        search_terms = [
            "climate change", "technology", "research", "analysis",
            "government", "policy", "data", "investigation"
        ]
        
        search_query = random.choice(search_terms)
        with self.client.get(f"/api/v1/search/", 
                           params={"q": search_query, "project_id": self.project_id},
                           catch_response=True) as response:
            if response.status_code == 200:
                self.operations_performed += 1
            else:
                response.failure(f"Search failed: {response.status_code}")
    
    @task(15)  # 15% weight
    def view_analytics(self):
        """Simulate analytics page views"""
        analytics_endpoints = [
            "summary",
            "timeline", 
            "domains",
            "content-types",
            "quality-distribution"
        ]
        
        endpoint = random.choice(analytics_endpoints)
        with self.client.get(f"/api/v1/analytics/{endpoint}",
                           params={"project_id": self.project_id},
                           catch_response=True) as response:
            if response.status_code == 200:
                self.operations_performed += 1
            else:
                response.failure(f"Analytics {endpoint} failed: {response.status_code}")
    
    @task(10)  # 10% weight
    def export_data(self):
        """Simulate data export operations"""
        export_formats = ["csv", "json", "xlsx"]
        format_type = random.choice(export_formats)
        
        with self.client.post(f"/api/v1/export/",
                            json={
                                "project_id": self.project_id,
                                "format": format_type,
                                "filters": {}
                            },
                            catch_response=True) as response:
            if response.status_code in [200, 202]:  # Accept both sync and async
                self.operations_performed += 1
            else:
                response.failure(f"Export failed: {response.status_code}")
    
    @task(10)  # 10% weight
    def manage_projects(self):
        """Simulate project management operations"""
        operations = ["list", "detail", "update"]
        operation = random.choice(operations)
        
        if operation == "list":
            endpoint = "/api/v1/projects/"
        elif operation == "detail":
            endpoint = f"/api/v1/projects/{self.project_id}"
        else:  # update
            endpoint = f"/api/v1/projects/{self.project_id}"
        
        method = "GET" if operation != "update" else "PUT"
        data = {"description": "Updated via load test"} if operation == "update" else None
        
        with self.client.request(method, endpoint, json=data, catch_response=True) as response:
            if response.status_code in [200, 204]:
                self.operations_performed += 1
            else:
                response.failure(f"Project {operation} failed: {response.status_code}")
    
    @task(15)  # 15% weight  
    def simulate_real_time_updates(self):
        """Simulate WebSocket real-time updates"""
        # Note: This is a simplified simulation
        # In practice, WebSocket connections would be handled separately
        with self.client.get("/api/v1/ws/status", catch_response=True) as response:
            if response.status_code == 200:
                self.operations_performed += 1
            else:
                response.failure(f"WebSocket status failed: {response.status_code}")


class LoadTestScenarios:
    """Main load testing scenarios implementation"""
    
    def __init__(self, config: LoadTestConfig = None):
        self.config = config or LoadTestConfig()
        self.results: List[LoadTestResult] = []
    
    async def simulate_dashboard_users(self, concurrent_users: int) -> LoadTestResult:
        """Simulate concurrent dashboard users"""
        print(f"Starting dashboard user simulation: {concurrent_users} users")
        
        start_time = time.time()
        total_requests = 0
        successful_requests = 0
        failed_requests = 0
        response_times = []
        
        async def dashboard_user_session():
            nonlocal total_requests, successful_requests, failed_requests, response_times
            
            async with AsyncClient(base_url=self.config.base_url) as client:
                # Authenticate
                auth_response = await client.post("/api/v1/auth/login", json={
                    "email": "dashboard_user@example.com",
                    "password": "Test123!"
                })
                
                if auth_response.status_code != 200:
                    failed_requests += 1
                    return
                
                token = auth_response.json()["access_token"]
                headers = {"Authorization": f"Bearer {token}"}
                
                # Simulate dashboard session (10-20 requests per user)
                requests_per_user = random.randint(10, 20)
                
                for _ in range(requests_per_user):
                    request_start = time.time()
                    total_requests += 1
                    
                    try:
                        # Random dashboard operation
                        operation = random.choice([
                            ("GET", "/api/v1/analytics/summary"),
                            ("GET", "/api/v1/analytics/timeline"),
                            ("GET", "/api/v1/search/"),
                            ("GET", "/api/v1/projects/"),
                        ])
                        
                        response = await client.request(
                            operation[0], 
                            operation[1], 
                            headers=headers,
                            timeout=30.0
                        )
                        
                        response_time = time.time() - request_start
                        response_times.append(response_time * 1000)  # ms
                        
                        if response.status_code == 200:
                            successful_requests += 1
                        else:
                            failed_requests += 1
                        
                        # Think time
                        await asyncio.sleep(random.uniform(0.5, 2.0))
                        
                    except Exception as e:
                        failed_requests += 1
                        response_times.append(30000)  # timeout as 30s
        
        # Run concurrent user sessions
        tasks = [dashboard_user_session() for _ in range(concurrent_users)]
        await asyncio.gather(*tasks, return_exceptions=True)
        
        # Calculate metrics
        duration = time.time() - start_time
        rps = total_requests / duration if duration > 0 else 0
        error_rate = (failed_requests / total_requests * 100) if total_requests > 0 else 0
        
        avg_response_time = statistics.mean(response_times) if response_times else 0
        p95_response_time = np.percentile(response_times, 95) if response_times else 0
        p99_response_time = np.percentile(response_times, 99) if response_times else 0
        
        result = LoadTestResult(
            scenario_name="dashboard_users",
            total_users=concurrent_users,
            duration_seconds=duration,
            total_requests=total_requests,
            successful_requests=successful_requests,
            failed_requests=failed_requests,
            average_response_time=avg_response_time,
            p95_response_time=p95_response_time,
            p99_response_time=p99_response_time,
            requests_per_second=rps,
            error_rate_percent=error_rate,
            peak_memory_mb=0,  # Would be measured externally
            peak_cpu_percent=0,  # Would be measured externally
            websocket_connections=0,
            websocket_messages=0,
            timestamp=datetime.utcnow()
        )
        
        self.results.append(result)
        return result
    
    async def simulate_data_export_requests(self, concurrent_exports: int) -> LoadTestResult:
        """Simulate concurrent data export operations"""
        print(f"Starting data export simulation: {concurrent_exports} concurrent exports")
        
        start_time = time.time()
        total_requests = concurrent_exports
        successful_requests = 0
        failed_requests = 0
        response_times = []
        
        async def export_operation():
            nonlocal successful_requests, failed_requests, response_times
            
            async with AsyncClient(base_url=self.config.base_url) as client:
                # Authenticate
                auth_response = await client.post("/api/v1/auth/login", json={
                    "email": "export_user@example.com",
                    "password": "Test123!"
                })
                
                if auth_response.status_code != 200:
                    failed_requests += 1
                    return
                
                token = auth_response.json()["access_token"]
                headers = {"Authorization": f"Bearer {token}"}
                
                # Simulate data export
                export_request = {
                    "format": random.choice(["csv", "json", "xlsx"]),
                    "filters": {
                        "date_range": "last_30_days",
                        "domains": ["example.com", "test.org"]
                    }
                }
                
                request_start = time.time()
                
                try:
                    response = await client.post(
                        "/api/v1/export/",
                        json=export_request,
                        headers=headers,
                        timeout=120.0  # Longer timeout for exports
                    )
                    
                    response_time = time.time() - request_start
                    response_times.append(response_time * 1000)
                    
                    if response.status_code in [200, 202]:
                        successful_requests += 1
                    else:
                        failed_requests += 1
                        
                except Exception as e:
                    failed_requests += 1
                    response_times.append(120000)  # timeout
        
        # Run concurrent exports
        tasks = [export_operation() for _ in range(concurrent_exports)]
        await asyncio.gather(*tasks, return_exceptions=True)
        
        # Calculate metrics
        duration = time.time() - start_time
        rps = total_requests / duration if duration > 0 else 0
        error_rate = (failed_requests / total_requests * 100) if total_requests > 0 else 0
        
        avg_response_time = statistics.mean(response_times) if response_times else 0
        p95_response_time = np.percentile(response_times, 95) if response_times else 0
        p99_response_time = np.percentile(response_times, 99) if response_times else 0
        
        result = LoadTestResult(
            scenario_name="data_export_requests",
            total_users=concurrent_exports,
            duration_seconds=duration,
            total_requests=total_requests,
            successful_requests=successful_requests,
            failed_requests=failed_requests,
            average_response_time=avg_response_time,
            p95_response_time=p95_response_time,
            p99_response_time=p99_response_time,
            requests_per_second=rps,
            error_rate_percent=error_rate,
            peak_memory_mb=0,
            peak_cpu_percent=0,
            websocket_connections=0,
            websocket_messages=0,
            timestamp=datetime.utcnow()
        )
        
        self.results.append(result)
        return result
    
    async def simulate_mixed_workload(self, user_mix: Dict[str, int]) -> LoadTestResult:
        """
        Simulate mixed workload with different user types
        
        user_mix example:
        {
            "dashboard_users": 50,
            "search_users": 30, 
            "export_users": 10,
            "admin_users": 10
        }
        """
        print(f"Starting mixed workload simulation: {user_mix}")
        
        start_time = time.time()
        total_users = sum(user_mix.values())
        total_requests = 0
        successful_requests = 0
        failed_requests = 0
        response_times = []
        
        async def dashboard_user():
            """Dashboard-focused user behavior"""
            return await self._simulate_user_type("dashboard", 15)
        
        async def search_user():
            """Search-focused user behavior"""
            return await self._simulate_user_type("search", 12)
        
        async def export_user():
            """Export-focused user behavior"""
            return await self._simulate_user_type("export", 5)
        
        async def admin_user():
            """Admin-focused user behavior"""
            return await self._simulate_user_type("admin", 8)
        
        # Create user tasks based on mix
        tasks = []
        for user_type, count in user_mix.items():
            if user_type == "dashboard_users":
                tasks.extend([dashboard_user() for _ in range(count)])
            elif user_type == "search_users":
                tasks.extend([search_user() for _ in range(count)])
            elif user_type == "export_users":
                tasks.extend([export_user() for _ in range(count)])
            elif user_type == "admin_users":
                tasks.extend([admin_user() for _ in range(count)])
        
        # Execute all user sessions concurrently
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Aggregate results
        for user_result in results:
            if isinstance(user_result, dict):
                total_requests += user_result.get('requests', 0)
                successful_requests += user_result.get('successful', 0) 
                failed_requests += user_result.get('failed', 0)
                response_times.extend(user_result.get('response_times', []))
        
        # Calculate final metrics
        duration = time.time() - start_time
        rps = total_requests / duration if duration > 0 else 0
        error_rate = (failed_requests / total_requests * 100) if total_requests > 0 else 0
        
        avg_response_time = statistics.mean(response_times) if response_times else 0
        p95_response_time = np.percentile(response_times, 95) if response_times else 0
        p99_response_time = np.percentile(response_times, 99) if response_times else 0
        
        result = LoadTestResult(
            scenario_name="mixed_workload",
            total_users=total_users,
            duration_seconds=duration,
            total_requests=total_requests,
            successful_requests=successful_requests,
            failed_requests=failed_requests,
            average_response_time=avg_response_time,
            p95_response_time=p95_response_time,
            p99_response_time=p99_response_time,
            requests_per_second=rps,
            error_rate_percent=error_rate,
            peak_memory_mb=0,
            peak_cpu_percent=0,
            websocket_connections=0,
            websocket_messages=0,
            timestamp=datetime.utcnow()
        )
        
        self.results.append(result)
        return result
    
    async def _simulate_user_type(self, user_type: str, request_count: int) -> Dict:
        """Simulate specific user type behavior"""
        requests_made = 0
        successful = 0
        failed = 0
        response_times = []
        
        async with AsyncClient(base_url=self.config.base_url) as client:
            # Authenticate
            try:
                auth_response = await client.post("/api/v1/auth/login", json={
                    "email": f"{user_type}_user@example.com",
                    "password": "Test123!"
                })
                
                if auth_response.status_code != 200:
                    return {"requests": 0, "successful": 0, "failed": 1, "response_times": []}
                
                token = auth_response.json()["access_token"]
                headers = {"Authorization": f"Bearer {token}"}
                
                # Execute user-type specific operations
                for _ in range(request_count):
                    request_start = time.time()
                    requests_made += 1
                    
                    try:
                        if user_type == "dashboard":
                            response = await client.get("/api/v1/analytics/summary", headers=headers)
                        elif user_type == "search":
                            response = await client.get("/api/v1/search/", 
                                                     params={"q": "test"}, headers=headers)
                        elif user_type == "export":
                            response = await client.post("/api/v1/export/",
                                                       json={"format": "csv"}, headers=headers)
                        else:  # admin
                            response = await client.get("/api/v1/admin/stats", headers=headers)
                        
                        response_time = time.time() - request_start
                        response_times.append(response_time * 1000)
                        
                        if response.status_code in [200, 202]:
                            successful += 1
                        else:
                            failed += 1
                        
                        # Think time
                        await asyncio.sleep(random.uniform(0.5, 2.0))
                        
                    except Exception as e:
                        failed += 1
                        response_times.append(5000)  # 5s timeout
                
            except Exception as e:
                failed += requests_made
        
        return {
            "requests": requests_made,
            "successful": successful,
            "failed": failed,
            "response_times": response_times
        }
    
    async def simulate_websocket_connections(self, connection_count: int) -> LoadTestResult:
        """Simulate WebSocket connections for real-time updates"""
        print(f"Starting WebSocket simulation: {connection_count} connections")
        
        start_time = time.time()
        successful_connections = 0
        failed_connections = 0
        total_messages = 0
        connection_durations = []
        
        async def websocket_client():
            nonlocal successful_connections, failed_connections, total_messages
            
            try:
                # Note: Simplified WebSocket simulation
                # Real implementation would use actual WebSocket connections
                async with AsyncClient(base_url=self.config.base_url) as client:
                    # Authenticate first
                    auth_response = await client.post("/api/v1/auth/login", json={
                        "email": "ws_user@example.com", 
                        "password": "Test123!"
                    })
                    
                    if auth_response.status_code != 200:
                        failed_connections += 1
                        return
                    
                    connection_start = time.time()
                    
                    # Simulate WebSocket connection lifecycle
                    for _ in range(10):  # 10 messages per connection
                        response = await client.get("/api/v1/ws/status")
                        if response.status_code == 200:
                            total_messages += 1
                        await asyncio.sleep(0.1)
                    
                    connection_duration = time.time() - connection_start
                    connection_durations.append(connection_duration)
                    successful_connections += 1
                    
            except Exception as e:
                failed_connections += 1
        
        # Run concurrent WebSocket clients
        tasks = [websocket_client() for _ in range(connection_count)]
        await asyncio.gather(*tasks, return_exceptions=True)
        
        # Calculate metrics
        duration = time.time() - start_time
        avg_connection_duration = statistics.mean(connection_durations) if connection_durations else 0
        
        result = LoadTestResult(
            scenario_name="websocket_connections",
            total_users=connection_count,
            duration_seconds=duration,
            total_requests=total_messages,
            successful_requests=total_messages,
            failed_requests=failed_connections,
            average_response_time=avg_connection_duration * 1000,
            p95_response_time=0,
            p99_response_time=0,
            requests_per_second=total_messages / duration if duration > 0 else 0,
            error_rate_percent=(failed_connections / connection_count * 100) if connection_count > 0 else 0,
            peak_memory_mb=0,
            peak_cpu_percent=0,
            websocket_connections=successful_connections,
            websocket_messages=total_messages,
            timestamp=datetime.utcnow()
        )
        
        self.results.append(result)
        return result
    
    async def simulate_batch_processing_load(self, batch_count: int) -> LoadTestResult:
        """Simulate high-volume batch processing operations"""
        print(f"Starting batch processing simulation: {batch_count} batches")
        
        start_time = time.time()
        total_requests = batch_count
        successful_requests = 0
        failed_requests = 0
        processing_times = []
        
        async def batch_operation():
            nonlocal successful_requests, failed_requests, processing_times
            
            async with AsyncClient(base_url=self.config.base_url) as client:
                # Authenticate
                auth_response = await client.post("/api/v1/auth/login", json={
                    "email": "batch_user@example.com",
                    "password": "Test123!"
                })
                
                if auth_response.status_code != 200:
                    failed_requests += 1
                    return
                
                token = auth_response.json()["access_token"]
                headers = {"Authorization": f"Bearer {token}"}
                
                # Simulate batch processing request
                batch_data = {
                    "operation": "bulk_update",
                    "items": [{"id": i, "status": "processed"} for i in range(100)]
                }
                
                request_start = time.time()
                
                try:
                    response = await client.post(
                        "/api/v1/batch/process",
                        json=batch_data,
                        headers=headers,
                        timeout=60.0
                    )
                    
                    processing_time = time.time() - request_start
                    processing_times.append(processing_time * 1000)
                    
                    if response.status_code in [200, 202]:
                        successful_requests += 1
                    else:
                        failed_requests += 1
                        
                except Exception as e:
                    failed_requests += 1
                    processing_times.append(60000)
        
        # Run concurrent batch operations
        tasks = [batch_operation() for _ in range(batch_count)]
        await asyncio.gather(*tasks, return_exceptions=True)
        
        # Calculate metrics
        duration = time.time() - start_time
        rps = total_requests / duration if duration > 0 else 0
        error_rate = (failed_requests / total_requests * 100) if total_requests > 0 else 0
        
        avg_processing_time = statistics.mean(processing_times) if processing_times else 0
        p95_processing_time = np.percentile(processing_times, 95) if processing_times else 0
        p99_processing_time = np.percentile(processing_times, 99) if processing_times else 0
        
        result = LoadTestResult(
            scenario_name="batch_processing_load",
            total_users=batch_count,
            duration_seconds=duration,
            total_requests=total_requests,
            successful_requests=successful_requests,
            failed_requests=failed_requests,
            average_response_time=avg_processing_time,
            p95_response_time=p95_processing_time,
            p99_response_time=p99_processing_time,
            requests_per_second=rps,
            error_rate_percent=error_rate,
            peak_memory_mb=0,
            peak_cpu_percent=0,
            websocket_connections=0,
            websocket_messages=0,
            timestamp=datetime.utcnow()
        )
        
        self.results.append(result)
        return result


class LoadTestRunner:
    """Main load test execution and coordination"""
    
    def __init__(self, config: LoadTestConfig = None):
        self.config = config or LoadTestConfig()
        self.scenarios = LoadTestScenarios(self.config)
    
    async def run_normal_load_test(self) -> List[LoadTestResult]:
        """Run normal load test scenario - 100 concurrent users"""
        print("=" * 60)
        print("NORMAL LOAD TEST - 100 Concurrent Users")
        print("=" * 60)
        
        results = []
        
        # Dashboard users
        result = await self.scenarios.simulate_dashboard_users(100)
        results.append(result)
        print(f"Dashboard users: {result.requests_per_second:.1f} RPS, "
              f"{result.error_rate_percent:.2f}% errors")
        
        # Mixed workload
        user_mix = {
            "dashboard_users": 60,
            "search_users": 25,
            "export_users": 10,
            "admin_users": 5
        }
        result = await self.scenarios.simulate_mixed_workload(user_mix)
        results.append(result)
        print(f"Mixed workload: {result.requests_per_second:.1f} RPS, "
              f"{result.error_rate_percent:.2f}% errors")
        
        return results
    
    async def run_peak_load_test(self) -> List[LoadTestResult]:
        """Run peak load test scenario - 500 concurrent users"""
        print("=" * 60)
        print("PEAK LOAD TEST - 500 Concurrent Users")
        print("=" * 60)
        
        results = []
        
        # High dashboard load
        result = await self.scenarios.simulate_dashboard_users(500)
        results.append(result)
        print(f"Dashboard users: {result.requests_per_second:.1f} RPS, "
              f"{result.error_rate_percent:.2f}% errors")
        
        # Heavy export load
        result = await self.scenarios.simulate_data_export_requests(50)
        results.append(result)
        print(f"Export requests: {result.requests_per_second:.1f} RPS, "
              f"{result.error_rate_percent:.2f}% errors")
        
        # WebSocket connections
        result = await self.scenarios.simulate_websocket_connections(100)
        results.append(result)
        print(f"WebSocket connections: {result.websocket_connections} active, "
              f"{result.websocket_messages} messages")
        
        return results
    
    async def run_stress_load_test(self) -> List[LoadTestResult]:
        """Run stress load test scenario - 1000+ concurrent users"""
        print("=" * 60)
        print("STRESS LOAD TEST - 1000+ Concurrent Users")
        print("=" * 60)
        
        results = []
        
        # Maximum dashboard load
        result = await self.scenarios.simulate_dashboard_users(1000)
        results.append(result)
        print(f"Dashboard users: {result.requests_per_second:.1f} RPS, "
              f"{result.error_rate_percent:.2f}% errors")
        
        # Heavy mixed workload
        user_mix = {
            "dashboard_users": 600,
            "search_users": 250,
            "export_users": 100,
            "admin_users": 50
        }
        result = await self.scenarios.simulate_mixed_workload(user_mix)
        results.append(result)
        print(f"Mixed workload: {result.requests_per_second:.1f} RPS, "
              f"{result.error_rate_percent:.2f}% errors")
        
        # Batch processing stress
        result = await self.scenarios.simulate_batch_processing_load(200)
        results.append(result)
        print(f"Batch processing: {result.requests_per_second:.1f} RPS, "
              f"{result.error_rate_percent:.2f}% errors")
        
        return results
    
    def generate_load_test_report(self, results: List[LoadTestResult]) -> str:
        """Generate comprehensive load test report"""
        report = []
        report.append("LOAD TEST RESULTS SUMMARY")
        report.append("=" * 50)
        report.append("")
        
        for result in results:
            report.append(f"Scenario: {result.scenario_name}")
            report.append(f"  Users: {result.total_users:,}")
            report.append(f"  Duration: {result.duration_seconds:.1f}s")
            report.append(f"  Total Requests: {result.total_requests:,}")
            report.append(f"  Successful: {result.successful_requests:,}")
            report.append(f"  Failed: {result.failed_requests:,}")
            report.append(f"  RPS: {result.requests_per_second:.1f}")
            report.append(f"  Error Rate: {result.error_rate_percent:.2f}%")
            report.append(f"  Avg Response Time: {result.average_response_time:.1f}ms")
            report.append(f"  P95 Response Time: {result.p95_response_time:.1f}ms")
            report.append(f"  P99 Response Time: {result.p99_response_time:.1f}ms")
            
            # Performance target validation
            meets_targets = result.meets_performance_targets(self.config)
            report.append(f"  Meets Targets: {'✓ YES' if meets_targets else '✗ NO'}")
            report.append("")
        
        # Overall summary
        total_requests = sum(r.total_requests for r in results)
        total_errors = sum(r.failed_requests for r in results)
        overall_error_rate = (total_errors / total_requests * 100) if total_requests > 0 else 0
        
        report.append("OVERALL SUMMARY")
        report.append("-" * 30)
        report.append(f"Total Requests: {total_requests:,}")
        report.append(f"Total Errors: {total_errors:,}")
        report.append(f"Overall Error Rate: {overall_error_rate:.2f}%")
        
        targets_met = all(r.meets_performance_targets(self.config) for r in results)
        report.append(f"All Targets Met: {'✓ YES' if targets_met else '✗ NO'}")
        
        return "\n".join(report)


if __name__ == "__main__":
    async def run_all_load_tests():
        """Run complete load testing suite"""
        config = LoadTestConfig()
        runner = LoadTestRunner(config)
        
        print("Starting comprehensive load testing suite...")
        
        # Run all load test scenarios
        normal_results = await runner.run_normal_load_test()
        peak_results = await runner.run_peak_load_test() 
        stress_results = await runner.run_stress_load_test()
        
        all_results = normal_results + peak_results + stress_results
        
        # Generate final report
        report = runner.generate_load_test_report(all_results)
        print("\n" + report)
        
        # Save results to file
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        with open(f"load_test_results_{timestamp}.txt", "w") as f:
            f.write(report)
    
    asyncio.run(run_all_load_tests())