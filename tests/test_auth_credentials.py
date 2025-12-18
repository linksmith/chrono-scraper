#!/usr/bin/env python3
"""
Test authentication with provided credentials and API endpoints
"""
import asyncio
import aiohttp
import json
import sys
from typing import Dict, Any, Optional

BASE_URL = "http://localhost:8000"

class AuthTestRunner:
    def __init__(self):
        self.session: Optional[aiohttp.ClientSession] = None
        self.access_token: Optional[str] = None
        self.user_id: Optional[int] = None
        
    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
    
    async def login(self, email: str, password: str) -> Dict[str, Any]:
        """Test user authentication"""
        print(f"🔐 Testing authentication for {email}...")
        
        login_data = {
            "email": email,
            "password": password
        }
        
        try:
            async with self.session.post(
                f"{BASE_URL}/api/v1/auth/login",
                json=login_data,  # JSON data for LoginRequest model
                headers={"Content-Type": "application/json"}
            ) as response:
                if response.status == 200:
                    result = await response.json()
                    # Session auth uses cookies, not tokens
                    print(f"✅ Login successful! User: {result.get('full_name', 'Unknown')}")
                    print(f"   Session cookie set: {response.cookies.get('session_id') is not None}")
                    return result
                else:
                    error_text = await response.text()
                    print(f"❌ Login failed: {response.status} - {error_text}")
                    return {"error": f"Login failed: {response.status}", "details": error_text}
        except Exception as e:
            print(f"❌ Login error: {str(e)}")
            return {"error": str(e)}
    
    async def get_current_user(self) -> Dict[str, Any]:
        """Test getting current user info"""
        print("👤 Testing current user endpoint...")
        
        try:
            # Session auth uses cookies, no headers needed
            async with self.session.get(f"{BASE_URL}/api/v1/auth/me") as response:
                if response.status == 200:
                    result = await response.json()
                    self.user_id = result.get("id")
                    print(f"✅ User info retrieved: {result.get('full_name')} (ID: {self.user_id})")
                    return result
                else:
                    error_text = await response.text()
                    print(f"❌ Get user failed: {response.status} - {error_text}")
                    return {"error": f"Get user failed: {response.status}", "details": error_text}
        except Exception as e:
            print(f"❌ Get user error: {str(e)}")
            return {"error": str(e)}
    
    async def test_projects_endpoint(self) -> Dict[str, Any]:
        """Test projects endpoint with authentication"""
        print("📁 Testing projects endpoint...")
        
        try:
            # Session auth uses cookies, no headers needed
            async with self.session.get(f"{BASE_URL}/api/v1/projects/") as response:
                if response.status == 200:
                    result = await response.json()
                    project_count = len(result)
                    print(f"✅ Projects retrieved: {project_count} projects found")
                    if project_count > 0:
                        print(f"   First project: {result[0].get('name', 'Unknown')}")
                    return result
                else:
                    error_text = await response.text()
                    print(f"❌ Projects failed: {response.status} - {error_text}")
                    return {"error": f"Projects failed: {response.status}", "details": error_text}
        except Exception as e:
            print(f"❌ Projects error: {str(e)}")
            return {"error": str(e)}
    
    async def test_shared_pages_endpoint(self) -> Dict[str, Any]:
        """Test shared pages endpoint"""
        print("📄 Testing shared pages endpoint...")
        
        try:
            # Session auth uses cookies, no headers needed
            async with self.session.get(f"{BASE_URL}/api/v1/shared-pages") as response:
                if response.status == 200:
                    result = await response.json()
                    if isinstance(result, list):
                        page_count = len(result)
                        print(f"✅ Shared pages retrieved: {page_count} total pages")
                        return {"pages": result, "total": page_count}
                    else:
                        page_count = result.get('total', 0)
                        print(f"✅ Shared pages retrieved: {page_count} total pages")
                        print(f"   Items in current page: {len(result.get('items', []))}")
                        return result
                else:
                    error_text = await response.text()
                    print(f"❌ Shared pages failed: {response.status} - {error_text}")
                    return {"error": f"Shared pages failed: {response.status}", "details": error_text}
        except Exception as e:
            print(f"❌ Shared pages error: {str(e)}")
            return {"error": str(e)}
    
    async def test_search_endpoint(self) -> Dict[str, Any]:
        """Test search endpoint"""
        print("🔍 Testing search endpoint...")
        
        try:
            # Session auth uses cookies, no headers needed
            search_params = {"q": "test", "limit": 5}
            async with self.session.get(f"{BASE_URL}/api/v1/search/pages", params=search_params) as response:
                if response.status == 200:
                    result = await response.json()
                    hit_count = result.get('estimatedTotalHits', 0)
                    print(f"✅ Search successful: {hit_count} total hits for 'test'")
                    print(f"   Results returned: {len(result.get('hits', []))}")
                    return result
                else:
                    error_text = await response.text()
                    print(f"❌ Search failed: {response.status} - {error_text}")
                    return {"error": f"Search failed: {response.status}", "details": error_text}
        except Exception as e:
            print(f"❌ Search error: {str(e)}")
            return {"error": str(e)}

async def main():
    print("🚀 Starting comprehensive authentication and API testing...")
    print("=" * 60)
    
    test_results = {}
    
    async with AuthTestRunner() as auth_test:
        # Test 1: Authentication
        login_result = await auth_test.login("info@linksmith.nl", "temppass123")
        test_results["login"] = login_result
        
        if "error" not in login_result:
            # Test 2: Current user
            user_result = await auth_test.get_current_user()
            test_results["current_user"] = user_result
            
            # Test 3: Projects endpoint
            projects_result = await auth_test.test_projects_endpoint()
            test_results["projects"] = projects_result
            
            # Test 4: Shared pages endpoint
            shared_pages_result = await auth_test.test_shared_pages_endpoint()
            test_results["shared_pages"] = shared_pages_result
            
            # Test 5: Search endpoint
            search_result = await auth_test.test_search_endpoint()
            test_results["search"] = search_result
        
    print("\n" + "=" * 60)
    print("📊 TEST SUMMARY")
    print("=" * 60)
    
    for test_name, result in test_results.items():
        if "error" in result:
            print(f"❌ {test_name.upper()}: FAILED - {result['error']}")
        else:
            print(f"✅ {test_name.upper()}: PASSED")
    
    # Save detailed results
    with open("/tmp/auth_test_results.json", "w") as f:
        json.dump(test_results, f, indent=2, default=str)
    
    print(f"\n📁 Detailed results saved to: /tmp/auth_test_results.json")
    
    return test_results

if __name__ == "__main__":
    asyncio.run(main())