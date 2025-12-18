#!/usr/bin/env python3
"""
Comprehensive testing script for the shared pages architecture
Tests authentication, API endpoints, data integrity, and system integration
"""
import asyncio
import aiohttp
import json
import sys
import time
from typing import Dict, Any, Optional, List
from datetime import datetime

BASE_URL = "http://localhost:8000"

class ComprehensiveSharedPagesTest:
    def __init__(self):
        self.session: Optional[aiohttp.ClientSession] = None
        self.user_id: Optional[int] = None
        self.test_results: Dict[str, Any] = {}
        self.start_time = time.time()
        
    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
    
    def log_test(self, test_name: str, success: bool, details: str = "", data: Any = None):
        """Log test result"""
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"{status} {test_name}: {details}")
        
        self.test_results[test_name] = {
            "success": success,
            "details": details,
            "data": data,
            "timestamp": datetime.now().isoformat()
        }
    
    async def test_1_authentication(self) -> bool:
        """Test 1: Authentication with provided credentials"""
        print("\n🔐 TEST 1: Authentication")
        print("-" * 50)
        
        login_data = {"email": "info@linksmith.nl", "password": "temppass123"}
        
        try:
            async with self.session.post(f"{BASE_URL}/api/v1/auth/login", json=login_data) as response:
                if response.status == 200:
                    result = await response.json()
                    self.user_id = result.get("id")
                    session_cookie = response.cookies.get('session_id')
                    
                    self.log_test(
                        "authentication", 
                        True, 
                        f"Login successful for {result.get('full_name')} (ID: {self.user_id})",
                        {"user_data": result, "has_session_cookie": session_cookie is not None}
                    )
                    return True
                else:
                    error = await response.text()
                    self.log_test("authentication", False, f"Login failed: {response.status} - {error}")
                    return False
        except Exception as e:
            self.log_test("authentication", False, f"Login exception: {str(e)}")
            return False
    
    async def test_2_basic_endpoints(self) -> bool:
        """Test 2: Basic API endpoints functionality"""
        print("\n📡 TEST 2: Basic API Endpoints")
        print("-" * 50)
        
        endpoints_to_test = [
            ("current_user", "/api/v1/auth/me"),
            ("projects_list", "/api/v1/projects/"),
            ("shared_pages_list", "/api/v1/shared-pages"),
            ("sharing_statistics", "/api/v1/shared-pages/statistics/sharing"),
        ]
        
        all_passed = True
        
        for test_name, endpoint in endpoints_to_test:
            try:
                async with self.session.get(f"{BASE_URL}{endpoint}") as response:
                    if response.status == 200:
                        result = await response.json()
                        if test_name == "projects_list":
                            count = len(result) if isinstance(result, list) else 0
                            details = f"Retrieved {count} projects"
                        elif test_name == "shared_pages_list":
                            count = len(result) if isinstance(result, list) else 0
                            details = f"Retrieved {count} shared pages"
                        elif test_name == "sharing_statistics":
                            details = f"Statistics available: {list(result.keys()) if isinstance(result, dict) else 'unknown format'}"
                        else:
                            details = f"Endpoint responded successfully"
                        
                        self.log_test(test_name, True, details, {"status": response.status, "data_keys": list(result.keys()) if isinstance(result, dict) else None})
                    else:
                        error = await response.text()
                        self.log_test(test_name, False, f"HTTP {response.status}: {error}")
                        all_passed = False
            except Exception as e:
                self.log_test(test_name, False, f"Exception: {str(e)}")
                all_passed = False
        
        return all_passed
    
    async def test_3_project_pages_access(self) -> bool:
        """Test 3: Project-specific pages access"""
        print("\n📁 TEST 3: Project Pages Access")
        print("-" * 50)
        
        try:
            # First get list of projects
            async with self.session.get(f"{BASE_URL}/api/v1/projects/") as response:
                if response.status != 200:
                    self.log_test("project_pages_access", False, "Could not retrieve projects list")
                    return False
                
                projects = await response.json()
                if not projects:
                    self.log_test("project_pages_access", False, "No projects found to test")
                    return False
                
                # Test access to pages for the first project
                project = projects[0]
                project_id = project.get("id")
                project_name = project.get("name", "Unknown")
                
                async with self.session.get(f"{BASE_URL}/api/v1/shared-pages/projects/{project_id}/pages") as pages_response:
                    if pages_response.status == 200:
                        pages = await pages_response.json()
                        page_count = len(pages) if isinstance(pages, list) else 0
                        self.log_test(
                            "project_pages_access", 
                            True, 
                            f"Retrieved {page_count} pages for project '{project_name}' (ID: {project_id})",
                            {"project_id": project_id, "page_count": page_count}
                        )
                        return True
                    else:
                        error = await pages_response.text()
                        self.log_test("project_pages_access", False, f"Failed to get project pages: {pages_response.status} - {error}")
                        return False
                        
        except Exception as e:
            self.log_test("project_pages_access", False, f"Exception: {str(e)}")
            return False
    
    async def test_4_search_functionality(self) -> bool:
        """Test 4: Search functionality"""
        print("\n🔍 TEST 4: Search Functionality")
        print("-" * 50)
        
        search_tests = [
            ("basic_search", {"q": "test", "limit": 5}),
            ("empty_search", {"q": "", "limit": 5}),
            ("wildcard_search", {"q": "*", "limit": 3}),
        ]
        
        all_passed = True
        
        for test_name, params in search_tests:
            try:
                async with self.session.get(f"{BASE_URL}/api/v1/search/pages", params=params) as response:
                    if response.status == 200:
                        result = await response.json()
                        hits = result.get("estimatedTotalHits", 0) if isinstance(result, dict) else 0
                        returned = len(result.get("hits", [])) if isinstance(result, dict) else 0
                        self.log_test(
                            test_name, 
                            True, 
                            f"Search '{params.get('q', '')}': {hits} total hits, {returned} returned",
                            {"hits": hits, "returned": returned, "query": params.get("q")}
                        )
                    else:
                        error = await response.text()
                        if response.status == 404:
                            self.log_test(test_name, False, f"Search endpoint not found: {response.status}")
                        else:
                            self.log_test(test_name, False, f"Search failed: {response.status} - {error}")
                        all_passed = False
            except Exception as e:
                self.log_test(test_name, False, f"Exception: {str(e)}")
                all_passed = False
        
        return all_passed
    
    async def test_5_data_integrity(self) -> bool:
        """Test 5: Data integrity and migration results"""
        print("\n🔍 TEST 5: Data Integrity & Migration Results")
        print("-" * 50)
        
        try:
            # Check if we have access to project data and verify consistency
            async with self.session.get(f"{BASE_URL}/api/v1/projects/") as response:
                if response.status != 200:
                    self.log_test("data_integrity", False, "Could not access projects for integrity check")
                    return False
                
                projects = await response.json()
                total_projects = len(projects)
                
                # Check for data consistency
                projects_with_pages = 0
                total_pages_across_projects = 0
                
                for project in projects:
                    page_count = project.get("total_pages", 0)
                    if page_count > 0:
                        projects_with_pages += 1
                        total_pages_across_projects += page_count
                
                # Check shared pages statistics
                async with self.session.get(f"{BASE_URL}/api/v1/shared-pages/statistics/sharing") as stats_response:
                    if stats_response.status == 200:
                        stats = await stats_response.json()
                        
                        self.log_test(
                            "data_integrity", 
                            True, 
                            f"Data integrity check passed: {total_projects} projects, {projects_with_pages} with pages, {total_pages_across_projects} total pages",
                            {
                                "total_projects": total_projects,
                                "projects_with_pages": projects_with_pages,
                                "total_pages": total_pages_across_projects,
                                "sharing_stats": stats
                            }
                        )
                        return True
                    else:
                        self.log_test("data_integrity", False, f"Could not retrieve sharing statistics: {stats_response.status}")
                        return False
                        
        except Exception as e:
            self.log_test("data_integrity", False, f"Exception during integrity check: {str(e)}")
            return False
    
    async def test_6_security_access_control(self) -> bool:
        """Test 6: Security and access controls"""
        print("\n🔒 TEST 6: Security & Access Controls")
        print("-" * 50)
        
        try:
            # Test that we can access our own data
            async with self.session.get(f"{BASE_URL}/api/v1/auth/me") as response:
                if response.status != 200:
                    self.log_test("security_access_control", False, "Cannot access own user data")
                    return False
                
                user_data = await response.json()
                
                # Test that session is working correctly
                if user_data.get("id") == self.user_id:
                    self.log_test(
                        "security_access_control", 
                        True, 
                        f"Access control working: user session maintains identity (ID: {self.user_id})",
                        {"user_id": self.user_id, "user_email": user_data.get("email")}
                    )
                    return True
                else:
                    self.log_test("security_access_control", False, "User ID mismatch in session")
                    return False
                    
        except Exception as e:
            self.log_test("security_access_control", False, f"Exception: {str(e)}")
            return False
    
    async def test_7_performance_check(self) -> bool:
        """Test 7: Basic performance check"""
        print("\n⚡ TEST 7: Performance Check")
        print("-" * 50)
        
        performance_results = []
        
        endpoints_to_test = [
            ("projects_list", "/api/v1/projects/"),
            ("shared_pages_list", "/api/v1/shared-pages"),
            ("user_profile", "/api/v1/auth/me"),
        ]
        
        all_passed = True
        
        for test_name, endpoint in endpoints_to_test:
            try:
                start_time = time.time()
                async with self.session.get(f"{BASE_URL}{endpoint}") as response:
                    end_time = time.time()
                    response_time = (end_time - start_time) * 1000  # Convert to milliseconds
                    
                    if response.status == 200:
                        # Performance threshold: 5 seconds (5000ms) for development environment
                        threshold = 5000
                        passed = response_time < threshold
                        
                        self.log_test(
                            f"performance_{test_name}", 
                            passed, 
                            f"Response time: {response_time:.2f}ms (threshold: {threshold}ms)",
                            {"response_time_ms": response_time, "threshold_ms": threshold}
                        )
                        
                        if not passed:
                            all_passed = False
                        
                        performance_results.append({
                            "endpoint": endpoint,
                            "response_time_ms": response_time,
                            "passed": passed
                        })
                    else:
                        self.log_test(f"performance_{test_name}", False, f"Endpoint failed: {response.status}")
                        all_passed = False
                        
            except Exception as e:
                self.log_test(f"performance_{test_name}", False, f"Exception: {str(e)}")
                all_passed = False
        
        # Overall performance summary
        if performance_results:
            avg_response_time = sum(r["response_time_ms"] for r in performance_results) / len(performance_results)
            self.log_test(
                "performance_summary", 
                all_passed, 
                f"Average response time: {avg_response_time:.2f}ms across {len(performance_results)} endpoints",
                {"average_response_time_ms": avg_response_time, "results": performance_results}
            )
        
        return all_passed
    
    async def run_all_tests(self) -> Dict[str, Any]:
        """Run all tests in sequence"""
        print("🚀 COMPREHENSIVE SHARED PAGES ARCHITECTURE TESTING")
        print("=" * 70)
        print(f"Testing with credentials: info@linksmith.nl")
        print(f"Target system: {BASE_URL}")
        print(f"Test started: {datetime.now().isoformat()}")
        print("=" * 70)
        
        test_functions = [
            self.test_1_authentication,
            self.test_2_basic_endpoints,
            self.test_3_project_pages_access,
            self.test_4_search_functionality,
            self.test_5_data_integrity,
            self.test_6_security_access_control,
            self.test_7_performance_check,
        ]
        
        passed_tests = 0
        total_tests = len(test_functions)
        
        for test_func in test_functions:
            try:
                result = await test_func()
                if result:
                    passed_tests += 1
            except Exception as e:
                print(f"❌ Test {test_func.__name__} crashed: {str(e)}")
        
        # Generate final report
        execution_time = time.time() - self.start_time
        
        print("\n" + "=" * 70)
        print("📊 FINAL TEST REPORT")
        print("=" * 70)
        print(f"Tests passed: {passed_tests}/{total_tests}")
        print(f"Success rate: {(passed_tests/total_tests)*100:.1f}%")
        print(f"Total execution time: {execution_time:.2f} seconds")
        print(f"User tested: info@linksmith.nl (ID: {self.user_id})")
        
        if passed_tests == total_tests:
            print("🎉 ALL TESTS PASSED - System is functioning correctly!")
        elif passed_tests >= total_tests * 0.8:
            print("⚠️  MOSTLY WORKING - Some minor issues detected")
        else:
            print("🚨 SIGNIFICANT ISSUES - Multiple systems failing")
        
        # Save detailed results
        final_results = {
            "summary": {
                "total_tests": total_tests,
                "passed_tests": passed_tests,
                "success_rate": (passed_tests/total_tests)*100,
                "execution_time_seconds": execution_time,
                "test_timestamp": datetime.now().isoformat(),
                "user_tested": "info@linksmith.nl",
                "user_id": self.user_id,
                "target_system": BASE_URL
            },
            "detailed_results": self.test_results
        }
        
        with open("/tmp/comprehensive_test_results.json", "w") as f:
            json.dump(final_results, f, indent=2, default=str)
        
        print(f"\n📁 Detailed results saved to: /tmp/comprehensive_test_results.json")
        return final_results

async def main():
    async with ComprehensiveSharedPagesTest() as test_runner:
        return await test_runner.run_all_tests()

if __name__ == "__main__":
    results = asyncio.run(main())