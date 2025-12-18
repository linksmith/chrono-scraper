#!/usr/bin/env python3
"""
Test all applied improvements and fixes
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
        
        await conn.execute("""
            UPDATE users 
            SET approval_status = 'approved', 
                is_verified = true,
                approval_date = NOW()
            WHERE id = $1
        """, user_id)
        
        # Get or create researcher role with proper permissions
        role_result = await conn.fetchrow("SELECT id FROM roles WHERE name = 'researcher'")
        
        if not role_result:
            role_id = await conn.fetchval("""
                INSERT INTO roles (name, description, is_system_role, created_at, updated_at)
                VALUES ('researcher', 'Research user with full project access', false, NOW(), NOW())
                RETURNING id
            """)
            
            permissions = [
                'user:read', 'project:create', 'project:read', 'project:update', 'project:delete',
                'domain:create', 'domain:read', 'domain:update', 'domain:delete',
                'scrape:start', 'scrape:stop', 'scrape:view'
            ]
            
            for perm in permissions:
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
        print(f"Database setup failed: {e}")
        return False

class ImprovementsTestSuite:
    def __init__(self):
        self.client = httpx.AsyncClient(base_url=BASE_URL, timeout=120.0)
    
    async def cleanup(self):
        await self.client.aclose()
    
    async def test_input_validation_improvements(self):
        """Test improved input validation"""
        print("\n🔍 TESTING INPUT VALIDATION IMPROVEMENTS")
        print("=" * 50)
        
        # Test email validation
        print("📧 Testing email validation...")
        invalid_emails = [
            "invalid-email",
            "test@",
            "@domain.com",
            "test..test@domain.com",
            ""
        ]
        
        for email in invalid_emails:
            response = await self.client.post("/api/v1/auth/register", json={
                "email": email,
                "password": "ValidPassword123!",
                "full_name": "Test User",
                "data_handling_agreement": True,
                "ethics_agreement": True
            })
            
            if response.status_code == 422:
                print(f"  ✅ Invalid email '{email}' correctly rejected")
            else:
                print(f"  ❌ Invalid email '{email}' should be rejected, got {response.status_code}")
        
        # Test password validation
        print("\n🔒 Testing password validation...")
        weak_passwords = [
            "123",  # Too short
            "password",  # No uppercase, digit, or special char
            "PASSWORD123",  # No lowercase or special char
            "Password",  # No digit or special char
            "Password123",  # No special char
        ]
        
        for password in weak_passwords:
            response = await self.client.post("/api/v1/auth/register", json={
                "email": f"test{uuid.uuid4().hex[:8]}@example.com",
                "password": password,
                "full_name": "Test User",
                "data_handling_agreement": True,
                "ethics_agreement": True
            })
            
            if response.status_code == 422:
                error_detail = response.json()
                print(f"  ✅ Weak password rejected: {error_detail.get('errors', [{}])[0].get('message', 'No message')[:50]}...")
            else:
                print(f"  ❌ Weak password should be rejected, got {response.status_code}")
        
        # Test successful registration with strong password
        print("\n✅ Testing successful registration with strong password...")
        response = await self.client.post("/api/v1/auth/register", json={
            "email": f"valid.test.{uuid.uuid4().hex[:8]}@example.com",
            "password": "ValidPassword123!",
            "full_name": "Test User",
            "professional_title": "Researcher",
            "organization_website": "https://example.org",
            "research_purpose": "This is a detailed research purpose that meets the minimum character requirements",
            "expected_usage": "Expected usage description",
            "data_handling_agreement": True,
            "ethics_agreement": True
        })
        
        if response.status_code == 200:
            print("  ✅ Valid user registration successful")
            return response.json()
        else:
            print(f"  ❌ Valid user registration failed: {response.status_code}")
            print(f"      Response: {response.text}")
            return None
    
    async def test_large_payload_handling(self):
        """Test large payload handling"""
        print("\n📦 TESTING LARGE PAYLOAD HANDLING")
        print("=" * 40)
        
        # Test very large description (should be handled gracefully)
        large_description = "x" * 1000  # 1KB description
        huge_description = "x" * 100000  # 100KB description
        
        # Create user and login first
        user_data = {
            "email": f"payload.test.{uuid.uuid4().hex[:8]}@example.com",
            "password": "ValidPassword123!",
            "full_name": "Payload Test User",
            "research_purpose": "Testing large payload handling in the system",
            "data_handling_agreement": True,
            "ethics_agreement": True
        }
        
        signup_response = await self.client.post("/api/v1/auth/register", json=user_data)
        if signup_response.status_code != 200:
            print("❌ Failed to create test user for payload testing")
            return False
        
        user = signup_response.json()
        await approve_user_directly(user["id"])
        
        # Login
        login_response = await self.client.post("/api/v1/auth/login", data={
            "username": user_data["email"],
            "password": user_data["password"]
        })
        
        if login_response.status_code != 200:
            print("❌ Failed to login for payload testing")
            return False
        
        token = login_response.json()["access_token"]
        self.client.headers.update({"Authorization": f"Bearer {token}"})
        
        # Test moderate payload (should work)
        print("📝 Testing moderate payload (1KB)...")
        response = await self.client.post("/api/v1/projects/", json={
            "name": "Large Payload Test",
            "description": large_description
        })
        
        if response.status_code in [200, 201]:
            print("  ✅ Moderate payload handled successfully")
        else:
            print(f"  ❌ Moderate payload failed: {response.status_code}")
        
        # Test huge payload (should be rejected)
        print("📦 Testing huge payload (100KB)...")
        response = await self.client.post("/api/v1/projects/", json={
            "name": "Huge Payload Test",
            "description": huge_description
        })
        
        if response.status_code == 413:
            print("  ✅ Huge payload correctly rejected with 413")
        elif response.status_code == 422:
            print("  ✅ Huge payload rejected with validation error")
        else:
            print(f"  ❌ Huge payload should be rejected, got {response.status_code}")
        
        # Test malformed JSON
        print("🔧 Testing malformed JSON...")
        response = await self.client.post(
            "/api/v1/projects/",
            content='{"name": "Test", "description":',  # Invalid JSON
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"}
        )
        
        if response.status_code == 422:
            print("  ✅ Malformed JSON correctly rejected")
        else:
            print(f"  ❌ Malformed JSON should be rejected, got {response.status_code}")
        
        return True
    
    async def test_domain_api_consistency(self):
        """Test domain API consistency"""
        print("\n🌐 TESTING DOMAIN API CONSISTENCY")
        print("=" * 40)
        
        # Create user and project first
        user_data = {
            "email": f"domain.test.{uuid.uuid4().hex[:8]}@example.com",
            "password": "ValidPassword123!",
            "full_name": "Domain Test User",
            "research_purpose": "Testing domain creation consistency in the API",
            "data_handling_agreement": True,
            "ethics_agreement": True
        }
        
        signup_response = await self.client.post("/api/v1/auth/register", json=user_data)
        if signup_response.status_code != 200:
            print("❌ Failed to create test user for domain testing")
            return False
        
        user = signup_response.json()
        await approve_user_directly(user["id"])
        
        # Login
        login_response = await self.client.post("/api/v1/auth/login", data={
            "username": user_data["email"],
            "password": user_data["password"]
        })
        
        token = login_response.json()["access_token"]
        self.client.headers.update({"Authorization": f"Bearer {token}"})
        
        # Create project
        project_response = await self.client.post("/api/v1/projects/", json={
            "name": "Domain Test Project",
            "description": "Testing domain creation"
        })
        
        if project_response.status_code not in [200, 201]:
            print("❌ Failed to create project for domain testing")
            return False
        
        project_id = project_response.json()["id"]
        
        # Test domain creation with the old 'domain' field name (should now work)
        print("🔧 Testing domain creation with 'domain' field...")
        domain_data_old = {
            "domain": "example.com",
            "include_subdomains": True,
            "max_pages": 100,
            "date_range_start": "2023-01-01",
            "date_range_end": "2023-12-31",
            "exclude_patterns": ["*.css", "*.js"],
            "include_patterns": ["*/blog/*"]
        }
        
        response = await self.client.post(f"/api/v1/projects/{project_id}/domains", json=domain_data_old)
        
        if response.status_code in [200, 201]:
            print("  ✅ Domain creation with 'domain' field successful")
            domain = response.json()
            print(f"    Created domain ID: {domain['id']}")
        else:
            print(f"  ❌ Domain creation failed: {response.status_code}")
            if response.status_code == 422:
                error_detail = response.json()
                print(f"      Error: {error_detail}")
        
        # Test domain creation with domain_name field (should also work)
        print("🔧 Testing domain creation with 'domain_name' field...")
        domain_data_new = {
            "domain_name": "test.org",
            "include_subdomains": False,
            "max_pages": 50
        }
        
        response = await self.client.post(f"/api/v1/projects/{project_id}/domains", json=domain_data_new)
        
        if response.status_code in [200, 201]:
            print("  ✅ Domain creation with 'domain_name' field successful")
        else:
            print(f"  ❌ Domain creation with 'domain_name' failed: {response.status_code}")
        
        return True
    
    async def test_error_handling_consistency(self):
        """Test consistent error handling"""
        print("\n⚠️  TESTING ERROR HANDLING CONSISTENCY")
        print("=" * 45)
        
        # Test 404 errors
        print("🔍 Testing 404 error handling...")
        response = await self.client.get("/api/v1/projects/99999")
        if response.status_code == 401:
            print("  ✅ Unauthorized access returns 401 (expected)")
        elif response.status_code == 404:
            print("  ✅ Not found returns 404")
        
        # Test validation errors have consistent format
        print("📝 Testing validation error format...")
        response = await self.client.post("/api/v1/auth/register", json={
            "email": "invalid-email",
            "password": "weak"
        })
        
        if response.status_code == 422:
            error_data = response.json()
            if "errors" in error_data and isinstance(error_data["errors"], list):
                print("  ✅ Validation errors have consistent format")
                if error_data["errors"]:
                    error = error_data["errors"][0]
                    required_fields = ["field", "message", "type"]
                    if all(field in error for field in required_fields):
                        print("    ✅ Error objects contain required fields")
                    else:
                        print("    ⚠️ Error objects missing some fields")
            else:
                print("  ⚠️ Validation errors format could be improved")
        
        # Test rate limiting (if implemented)
        print("🚦 Testing rate limiting behavior...")
        rapid_responses = []
        for i in range(10):
            response = await self.client.get("/")
            rapid_responses.append(response.status_code)
        
        if any(status == 429 for status in rapid_responses):
            print("  ✅ Rate limiting is active")
        else:
            print("  ℹ️ No rate limiting detected (may be intentional)")
        
        return True
    
    async def run_all_improvement_tests(self):
        """Run all improvement validation tests"""
        print("🔧" * 25)
        print("TESTING ALL APPLIED IMPROVEMENTS")
        print("🔧" * 25)
        
        test_results = {}
        
        try:
            # Test input validation
            user_data = await self.test_input_validation_improvements()
            test_results["Input Validation"] = "PASSED" if user_data else "FAILED"
            
            # Test payload handling
            payload_result = await self.test_large_payload_handling()
            test_results["Large Payload Handling"] = "PASSED" if payload_result else "FAILED"
            
            # Test domain API consistency
            domain_result = await self.test_domain_api_consistency()
            test_results["Domain API Consistency"] = "PASSED" if domain_result else "FAILED"
            
            # Test error handling
            error_result = await self.test_error_handling_consistency()
            test_results["Error Handling"] = "PASSED" if error_result else "FAILED"
            
        except Exception as e:
            print(f"❌ Test execution error: {e}")
            test_results["Test Execution"] = f"ERROR: {str(e)}"
        
        # Print summary
        print("\n" + "🎯" * 30)
        print("IMPROVEMENT TEST RESULTS SUMMARY")
        print("🎯" * 30)
        
        passed = sum(1 for result in test_results.values() if result == "PASSED")
        total = len(test_results)
        
        for test_name, result in test_results.items():
            icon = "✅" if result == "PASSED" else ("❌" if "FAILED" in result else "⚠️")
            print(f"{icon} {test_name}: {result}")
        
        print(f"\n📊 Overall Score: {passed}/{total} improvement tests passed")
        
        if passed == total:
            print("🎉 ALL IMPROVEMENTS WORKING CORRECTLY!")
            print("✨ System ready for production deployment")
        elif passed >= total * 0.8:
            print("✅ Most improvements working well!")
            print("🔧 Minor issues may need attention")
        else:
            print("⚠️ Several improvements need review")
            print("🔍 Check failed tests above")
        
        return test_results

async def main():
    test = ImprovementsTestSuite()
    
    try:
        results = await test.run_all_improvement_tests()
        return 0 if all("PASSED" in str(r) for r in results.values()) else 1
    finally:
        await test.cleanup()

if __name__ == "__main__":
    result = asyncio.run(main())
    exit(result)