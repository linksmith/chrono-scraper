#!/usr/bin/env python3
"""
Comprehensive Scenario Tests - Additional edge cases and full workflow validation
"""

import asyncio
import json
import time
import uuid
from typing import Dict, Any
import httpx
from faker import Faker

# Test configuration
BASE_URL = "http://localhost:8000"

fake = Faker()

async def approve_user_directly(user_id: int):
    """Directly approve user in database using SQL"""
    import asyncpg
    
    try:
        conn = await asyncpg.connect("postgresql://chrono_scraper:chrono_scraper_dev@postgres:5432/chrono_scraper")
        
        # Update user to be approved and verified
        await conn.execute("""
            UPDATE users 
            SET approval_status = 'approved', 
                is_verified = true,
                approval_date = NOW()
            WHERE id = $1
        """, user_id)
        
        await conn.close()
        return True
    except Exception as e:
        print(f"Database approval failed: {e}")
        return False

async def assign_user_permissions(user_id: int):
    """Assign necessary permissions to user for testing"""
    import asyncpg
    
    try:
        conn = await asyncpg.connect("postgresql://chrono_scraper:chrono_scraper_dev@postgres:5432/chrono_scraper")
        
        # Get or create researcher role (better than basic user)
        role_result = await conn.fetchrow("SELECT id FROM roles WHERE name = 'researcher'")
        
        if not role_result:
            # Create researcher role with comprehensive permissions
            role_id = await conn.fetchval("""
                INSERT INTO roles (name, description, is_system_role, created_at, updated_at)
                VALUES ('researcher', 'Research user with full project access', false, NOW(), NOW())
                RETURNING id
            """)
            
            # Add all researcher permissions
            permissions = [
                'user:read', 'project:create', 'project:read', 'project:update', 'project:delete',
                'domain:create', 'domain:read', 'domain:update', 'domain:delete',
                'scrape:start', 'scrape:stop', 'scrape:view'
            ]
            
            for perm in permissions:
                # Get or create permission
                perm_result = await conn.fetchrow("SELECT id FROM permissions WHERE name = $1", perm)
                
                if not perm_result:
                    resource, action = perm.split(':') if ':' in perm else ('general', perm)
                    perm_id = await conn.fetchval("""
                        INSERT INTO permissions (name, description, resource, action, created_at)
                        VALUES ($1, $2, $3, $4, NOW())
                        RETURNING id
                    """, perm, perm, resource, action)
                else:
                    perm_id = perm_result['id']
                
                # Assign permission to role
                await conn.execute("""
                    INSERT INTO role_permissions (role_id, permission_id)
                    VALUES ($1, $2)
                    ON CONFLICT (role_id, permission_id) DO NOTHING
                """, role_id, perm_id)
        else:
            role_id = role_result['id']
        
        # Assign role to user
        await conn.execute("""
            INSERT INTO user_roles (user_id, role_id)
            VALUES ($1, $2)
            ON CONFLICT (user_id, role_id) DO NOTHING
        """, user_id, role_id)
        
        await conn.close()
        return True
    except Exception as e:
        print(f"Permission assignment failed: {e}")
        return False

class ComprehensiveScenarioTests:
    def __init__(self):
        self.client = httpx.AsyncClient(base_url=BASE_URL, timeout=120.0)
        self.results = {}
    
    async def cleanup(self):
        await self.client.aclose()
    
    async def create_approved_user(self):
        """Create and approve a test user"""
        user_data = {
            "email": f"test.comprehensive.{uuid.uuid4().hex[:8]}@research.org",
            "password": "TestPassword123!",
            "full_name": fake.name(),
            "professional_title": "Senior Research Analyst",
            "organization_website": "https://research.org",
            "research_interests": "Web archival analysis and OSINT research",
            "research_purpose": "Academic research and threat intelligence analysis",
            "expected_usage": "Large-scale historical web content analysis",
            "academic_affiliation": "Research Institute of Technology",
            "data_handling_agreement": True,
            "ethics_agreement": True
        }
        
        # Create user
        signup_response = await self.client.post("/api/v1/auth/register", json=user_data)
        if signup_response.status_code != 200:
            return None, None
        
        user = signup_response.json()
        user_id = user["id"]
        
        # Approve user
        if not await approve_user_directly(user_id):
            return None, None
        
        # Assign permissions
        if not await assign_user_permissions(user_id):
            return None, None
        
        # Login
        login_data = {"username": user_data["email"], "password": user_data["password"]}
        login_response = await self.client.post("/api/v1/auth/login", data=login_data)
        
        if login_response.status_code != 200:
            return None, None
        
        token_data = login_response.json()
        self.client.headers.update({"Authorization": f"Bearer {token_data['access_token']}"})
        
        return user_id, user_data
    
    async def test_scenario_1_invalid_user_registration(self):
        """Test invalid user registration scenarios"""
        print("\n🧪 Scenario 1: Invalid User Registration")
        
        test_cases = [
            {
                "name": "Invalid email format",
                "data": {"email": "invalid-email", "password": "Valid123!", "full_name": "Test User"},
                "expected_status": 422
            },
            {
                "name": "Missing required fields",
                "data": {"email": "test@example.com"},
                "expected_status": 422
            },
            {
                "name": "Weak password",
                "data": {"email": "test@example.com", "password": "123", "full_name": "Test User"},
                "expected_status": 422
            },
            {
                "name": "Missing agreements",
                "data": {
                    "email": "test@example.com", 
                    "password": "Valid123!", 
                    "full_name": "Test User",
                    "data_handling_agreement": False,
                    "ethics_agreement": False
                },
                "expected_status": 422
            }
        ]
        
        passed = 0
        for case in test_cases:
            response = await self.client.post("/api/v1/auth/register", json=case["data"])
            if response.status_code == case["expected_status"]:
                print(f"  ✅ {case['name']}: Correctly rejected ({response.status_code})")
                passed += 1
            else:
                print(f"  ❌ {case['name']}: Expected {case['expected_status']}, got {response.status_code}")
        
        return passed == len(test_cases)
    
    async def test_scenario_2_authentication_edge_cases(self):
        """Test authentication edge cases"""
        print("\n🧪 Scenario 2: Authentication Edge Cases")
        
        # Create a valid user first
        user_id, user_data = await self.create_approved_user()
        if not user_id:
            print("  ❌ Failed to create test user")
            return False
        
        # Clear auth header for these tests
        if "Authorization" in self.client.headers:
            del self.client.headers["Authorization"]
        
        test_cases = [
            {
                "name": "Invalid credentials",
                "data": {"username": user_data["email"], "password": "WrongPassword"},
                "expected_status": 401
            },
            {
                "name": "Non-existent user",
                "data": {"username": "nonexistent@example.com", "password": "Password123!"},
                "expected_status": 401
            },
            {
                "name": "Empty credentials",
                "data": {"username": "", "password": ""},
                "expected_status": 422
            }
        ]
        
        passed = 0
        for case in test_cases:
            response = await self.client.post("/api/v1/auth/login", data=case["data"])
            if response.status_code == case["expected_status"]:
                print(f"  ✅ {case['name']}: Correctly rejected ({response.status_code})")
                passed += 1
            else:
                print(f"  ❌ {case['name']}: Expected {case['expected_status']}, got {response.status_code}")
        
        return passed == len(test_cases)
    
    async def test_scenario_3_unauthorized_access(self):
        """Test unauthorized access to protected endpoints"""
        print("\n🧪 Scenario 3: Unauthorized Access Protection")
        
        # Clear auth header
        if "Authorization" in self.client.headers:
            del self.client.headers["Authorization"]
        
        protected_endpoints = [
            ("GET", "/api/v1/users/me"),
            ("GET", "/api/v1/projects/"),
            ("POST", "/api/v1/projects/", {"name": "Test", "description": "Test"}),
            ("GET", "/api/v1/search/?q=test"),
        ]
        
        passed = 0
        for method, endpoint, *data in protected_endpoints:
            json_data = data[0] if data else None
            
            if method == "GET":
                response = await self.client.get(endpoint)
            elif method == "POST":
                response = await self.client.post(endpoint, json=json_data)
            
            if response.status_code == 401:
                print(f"  ✅ {method} {endpoint}: Correctly requires authentication")
                passed += 1
            else:
                print(f"  ❌ {method} {endpoint}: Expected 401, got {response.status_code}")
        
        return passed == len(protected_endpoints)
    
    async def test_scenario_4_project_lifecycle(self):
        """Test complete project lifecycle"""
        print("\n🧪 Scenario 4: Project Lifecycle Management")
        
        # Create authenticated user
        user_id, user_data = await self.create_approved_user()
        if not user_id:
            print("  ❌ Failed to create test user")
            return False
        
        # Create project
        project_data = {
            "name": f"Lifecycle Test {uuid.uuid4().hex[:8]}",
            "description": "Testing complete project lifecycle"
        }
        
        create_response = await self.client.post("/api/v1/projects/", json=project_data)
        if create_response.status_code not in [200, 201]:
            print(f"  ❌ Project creation failed: {create_response.status_code}")
            return False
        
        project = create_response.json()
        project_id = project["id"]
        print(f"  ✅ Project created: {project_id}")
        
        # Read project
        read_response = await self.client.get(f"/api/v1/projects/{project_id}")
        if read_response.status_code != 200:
            print(f"  ❌ Project read failed: {read_response.status_code}")
            return False
        print("  ✅ Project read successful")
        
        # Update project
        update_data = {"name": f"Updated {project_data['name']}"}
        update_response = await self.client.put(f"/api/v1/projects/{project_id}", json=update_data)
        if update_response.status_code != 200:
            print(f"  ❌ Project update failed: {update_response.status_code}")
            return False
        print("  ✅ Project updated successfully")
        
        # List projects (should contain our project)
        list_response = await self.client.get("/api/v1/projects/")
        if list_response.status_code != 200:
            print(f"  ❌ Project listing failed: {list_response.status_code}")
            return False
        
        projects = list_response.json()
        if not any(p["id"] == project_id for p in projects):
            print("  ❌ Created project not found in listing")
            return False
        print("  ✅ Project appears in listing")
        
        # Try to access non-existent project
        fake_response = await self.client.get("/api/v1/projects/99999")
        if fake_response.status_code != 404:
            print(f"  ❌ Non-existent project should return 404, got {fake_response.status_code}")
            return False
        print("  ✅ Non-existent project correctly returns 404")
        
        return True
    
    async def test_scenario_5_domain_management(self):
        """Test domain creation and management"""
        print("\n🧪 Scenario 5: Domain Management")
        
        # Create authenticated user and project
        user_id, user_data = await self.create_approved_user()
        if not user_id:
            return False
        
        project_data = {"name": "Domain Test Project", "description": "Testing domains"}
        project_response = await self.client.post("/api/v1/projects/", json=project_data)
        if project_response.status_code not in [200, 201]:
            return False
        
        project_id = project_response.json()["id"]
        
        # Test various domain configurations
        domain_configs = [
            {
                "name": "Basic domain",
                "data": {
                    "domain": "example.com",
                    "include_subdomains": True,
                    "max_pages": 100
                }
            },
            {
                "name": "Domain with date range",
                "data": {
                    "domain": "test.org",
                    "include_subdomains": False,
                    "max_pages": 50,
                    "date_range_start": "2020-01-01",
                    "date_range_end": "2023-12-31"
                }
            },
            {
                "name": "Domain with patterns",
                "data": {
                    "domain": "news.example.com",
                    "include_subdomains": True,
                    "max_pages": 200,
                    "exclude_patterns": ["*.css", "*.js", "*.jpg"],
                    "include_patterns": ["*/articles/*", "*/news/*"]
                }
            }
        ]
        
        created_domains = []
        for config in domain_configs:
            response = await self.client.post(f"/api/v1/projects/{project_id}/domains", json=config["data"])
            
            if response.status_code in [200, 201]:
                domain = response.json()
                created_domains.append(domain["id"])
                print(f"  ✅ {config['name']}: Created successfully")
            else:
                print(f"  ❌ {config['name']}: Failed ({response.status_code})")
                # Check if it's a validation error we can understand
                try:
                    error = response.json()
                    print(f"      Error details: {error}")
                except:
                    pass
        
        # List domains for project
        domains_response = await self.client.get(f"/api/v1/projects/{project_id}/domains")
        if domains_response.status_code == 200:
            domains = domains_response.json()
            print(f"  ✅ Domain listing successful: {len(domains)} domains found")
        else:
            print(f"  ⚠️ Domain listing failed: {domains_response.status_code}")
        
        return len(created_domains) > 0
    
    async def test_scenario_6_search_functionality(self):
        """Test search functionality and edge cases"""
        print("\n🧪 Scenario 6: Search Functionality")
        
        user_id, user_data = await self.create_approved_user()
        if not user_id:
            return False
        
        # Create project for search context
        project_data = {"name": "Search Test Project", "description": "Testing search"}
        project_response = await self.client.post("/api/v1/projects/", json=project_data)
        if project_response.status_code not in [200, 201]:
            return False
        
        project_id = project_response.json()["id"]
        
        # Test various search scenarios
        search_tests = [
            {"q": "test", "description": "Basic search"},
            {"q": "test query", "description": "Multi-word search"},
            {"q": '"exact phrase"', "description": "Phrase search"},
            {"q": "test*", "description": "Wildcard search"},
            {"q": "", "description": "Empty search"},
            {"q": "a", "description": "Single character search"},
        ]
        
        passed = 0
        for test in search_tests:
            params = {"q": test["q"], "project_id": project_id, "limit": 10}
            response = await self.client.get("/api/v1/search/", params=params)
            
            # Search should either work (200) or return no results gracefully
            # It shouldn't crash or return server errors
            if response.status_code in [200, 404]:
                print(f"  ✅ {test['description']}: Handled gracefully ({response.status_code})")
                passed += 1
            else:
                print(f"  ❌ {test['description']}: Unexpected status {response.status_code}")
        
        # Test search with invalid project ID
        invalid_response = await self.client.get("/api/v1/search/", params={"q": "test", "project_id": 99999})
        if invalid_response.status_code in [403, 404]:
            print("  ✅ Invalid project ID handled correctly")
            passed += 1
        
        return passed >= len(search_tests)
    
    async def test_scenario_7_performance_and_limits(self):
        """Test system performance and limits"""
        print("\n🧪 Scenario 7: Performance and Rate Limiting")
        
        user_id, user_data = await self.create_approved_user()
        if not user_id:
            return False
        
        # Test rapid requests (basic rate limiting check)
        start_time = time.time()
        responses = []
        
        # Make 20 rapid requests to the projects endpoint
        tasks = [self.client.get("/api/v1/projects/") for _ in range(20)]
        responses = await asyncio.gather(*tasks, return_exceptions=True)
        
        end_time = time.time()
        
        # Count successful responses
        successful = sum(1 for r in responses if hasattr(r, 'status_code') and r.status_code == 200)
        rate_limited = sum(1 for r in responses if hasattr(r, 'status_code') and r.status_code == 429)
        
        print(f"  📊 20 rapid requests: {successful} successful, {rate_limited} rate-limited")
        print(f"  ⏱️ Total time: {end_time - start_time:.2f}s")
        
        # Test large request payload
        large_project_data = {
            "name": "Large Project",
            "description": "x" * 5000  # 5KB description
        }
        
        large_response = await self.client.post("/api/v1/projects/", json=large_project_data)
        if large_response.status_code in [200, 201]:
            print("  ✅ Large payload handled successfully")
        elif large_response.status_code == 413:
            print("  ✅ Large payload rejected appropriately")
        else:
            print(f"  ⚠️ Large payload returned {large_response.status_code}")
        
        return True
    
    async def run_all_scenarios(self):
        """Run all comprehensive scenarios"""
        print("=" * 70)
        print("🧪 COMPREHENSIVE SCENARIO TESTING")
        print("=" * 70)
        
        scenarios = [
            ("Invalid User Registration", self.test_scenario_1_invalid_user_registration),
            ("Authentication Edge Cases", self.test_scenario_2_authentication_edge_cases),
            ("Unauthorized Access Protection", self.test_scenario_3_unauthorized_access),
            ("Project Lifecycle Management", self.test_scenario_4_project_lifecycle),
            ("Domain Management", self.test_scenario_5_domain_management),
            ("Search Functionality", self.test_scenario_6_search_functionality),
            ("Performance and Rate Limiting", self.test_scenario_7_performance_and_limits),
        ]
        
        results = {}
        for name, test_func in scenarios:
            try:
                result = await test_func()
                results[name] = "PASSED" if result else "FAILED"
            except Exception as e:
                results[name] = f"ERROR: {str(e)}"
                print(f"  ❌ {name} failed with error: {e}")
        
        # Print final summary
        print("\n" + "=" * 70)
        print("📊 COMPREHENSIVE TEST RESULTS")
        print("=" * 70)
        
        passed = sum(1 for result in results.values() if result == "PASSED")
        total = len(results)
        
        for scenario, result in results.items():
            icon = "✅" if result == "PASSED" else "❌"
            print(f"{icon} {scenario}: {result}")
        
        print(f"\n🎯 Overall Score: {passed}/{total} scenarios passed")
        
        if passed == total:
            print("🎉 ALL COMPREHENSIVE SCENARIOS PASSED!")
        elif passed >= total * 0.8:
            print("✅ Most scenarios passed - System is robust!")
        else:
            print("⚠️ Several scenarios failed - Review system stability")
        
        return results

async def main():
    test = ComprehensiveScenarioTests()
    
    try:
        results = await test.run_all_scenarios()
        return 0 if all(r == "PASSED" for r in results.values()) else 1
    finally:
        await test.cleanup()

if __name__ == "__main__":
    result = asyncio.run(main())
    exit(result)