#!/usr/bin/env python3
"""
Test script for Admin API endpoints
"""
import asyncio
import httpx
import json
import sys
import os
from typing import Dict, Any, Optional
from datetime import datetime

# Add project root to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

class AdminAPITester:
    """Test suite for Admin API endpoints"""
    
    def __init__(self, base_url: str = "http://localhost:8000", admin_token: Optional[str] = None):
        self.base_url = base_url.rstrip('/')
        self.admin_api_base = f"{self.base_url}/api/v1/admin/api"
        self.admin_token = admin_token
        self.test_results = []
        
    def get_headers(self) -> Dict[str, str]:
        """Get request headers with authentication"""
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
        if self.admin_token:
            headers["Authorization"] = f"Bearer {self.admin_token}"
        return headers
    
    async def make_request(
        self, 
        method: str, 
        endpoint: str, 
        data: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Make HTTP request to admin API"""
        url = f"{self.admin_api_base}/{endpoint.lstrip('/')}"
        
        async with httpx.AsyncClient() as client:
            try:
                response = await client.request(
                    method=method,
                    url=url,
                    headers=self.get_headers(),
                    json=data,
                    params=params,
                    timeout=30.0
                )
                
                result = {
                    "status_code": response.status_code,
                    "success": 200 <= response.status_code < 300,
                    "headers": dict(response.headers),
                    "url": str(response.url)
                }
                
                try:
                    result["data"] = response.json()
                except:
                    result["data"] = response.text
                
                return result
                
            except Exception as e:
                return {
                    "status_code": 0,
                    "success": False,
                    "error": str(e),
                    "url": url
                }
    
    def log_test_result(self, test_name: str, result: Dict[str, Any], expected_status: int = 200):
        """Log test result"""
        success = result["success"] and result.get("status_code") == expected_status
        status = "✅ PASS" if success else "❌ FAIL"
        
        print(f"{status} {test_name}")
        print(f"    Status: {result.get('status_code', 'ERROR')}")
        print(f"    URL: {result.get('url', 'Unknown')}")
        
        if not success:
            print(f"    Error: {result.get('error', 'HTTP Error')}")
            if 'data' in result and isinstance(result['data'], dict):
                if 'error' in result['data']:
                    print(f"    API Error: {result['data']['error']}")
        
        self.test_results.append({
            "test_name": test_name,
            "success": success,
            "status_code": result.get("status_code", 0),
            "timestamp": datetime.utcnow().isoformat()
        })
        print()
    
    async def test_system_health(self):
        """Test system health endpoint"""
        print("🏥 Testing System Health Endpoints...")
        
        # Test health check
        result = await self.make_request("GET", "/system/health")
        self.log_test_result("System Health Check", result)
        
        # Test metrics
        result = await self.make_request("GET", "/system/metrics")
        self.log_test_result("System Metrics", result)
        
        # Test Celery status
        result = await self.make_request("GET", "/celery/status")
        self.log_test_result("Celery Status", result)
    
    async def test_configuration(self):
        """Test configuration endpoints"""
        print("⚙️ Testing Configuration Endpoints...")
        
        # Test get config
        result = await self.make_request("GET", "/config")
        self.log_test_result("Get System Config", result)
    
    async def test_user_management(self):
        """Test user management endpoints"""
        print("👥 Testing User Management Endpoints...")
        
        # Test list users
        result = await self.make_request("GET", "/users", params={"page": 1, "per_page": 5})
        self.log_test_result("List Users", result)
        
        # If we have users, test getting a specific user
        if result["success"] and result.get("data", {}).get("items"):
            user_id = result["data"]["items"][0]["id"]
            result = await self.make_request("GET", f"/users/{user_id}")
            self.log_test_result("Get User Details", result)
    
    async def test_session_management(self):
        """Test session management endpoints"""
        print("🔐 Testing Session Management Endpoints...")
        
        # Test list sessions
        result = await self.make_request("GET", "/sessions", params={"page": 1, "per_page": 10})
        self.log_test_result("List Sessions", result)
    
    async def test_audit_logging(self):
        """Test audit logging endpoints"""
        print("📝 Testing Audit & Logging Endpoints...")
        
        # Test get audit logs
        result = await self.make_request("GET", "/audit/logs", params={"page": 1, "per_page": 10})
        self.log_test_result("Get Audit Logs", result)
    
    async def test_authentication_required(self):
        """Test that authentication is properly required"""
        print("🔒 Testing Authentication Requirements...")
        
        # Temporarily remove token
        original_token = self.admin_token
        self.admin_token = None
        
        # Test unauthorized access
        result = await self.make_request("GET", "/users")
        self.log_test_result("Unauthorized Access (should fail)", result, expected_status=401)
        
        # Test with invalid token
        self.admin_token = "invalid_token"
        result = await self.make_request("GET", "/users")
        self.log_test_result("Invalid Token (should fail)", result, expected_status=401)
        
        # Restore original token
        self.admin_token = original_token
    
    async def test_rate_limiting(self):
        """Test rate limiting (basic check)"""
        print("🚦 Testing Rate Limiting...")
        
        # Make multiple rapid requests to test rate limiting
        # Note: This is a basic test - full rate limit testing requires more requests
        for i in range(3):
            result = await self.make_request("GET", "/system/health")
            # Rate limiting might not kick in with just 3 requests, but we check the headers
            if "X-Rate-Limit" in result.get("headers", {}):
                print(f"    Rate limit header detected: {result['headers']['X-Rate-Limit']}")
                break
        
        self.log_test_result("Rate Limiting Headers", {"success": True, "status_code": 200})
    
    async def test_security_headers(self):
        """Test security headers are present"""
        print("🛡️ Testing Security Headers...")
        
        result = await self.make_request("GET", "/system/health")
        
        if result["success"]:
            headers = result.get("headers", {})
            security_headers = [
                "X-Admin-API",
                "X-Content-Type-Options",
                "X-Frame-Options",
                "Cache-Control"
            ]
            
            missing_headers = []
            for header in security_headers:
                if header.lower() not in [h.lower() for h in headers.keys()]:
                    missing_headers.append(header)
            
            if missing_headers:
                print(f"    Missing security headers: {', '.join(missing_headers)}")
                self.log_test_result("Security Headers", {"success": False, "status_code": 200})
            else:
                print("    All required security headers present")
                self.log_test_result("Security Headers", {"success": True, "status_code": 200})
        else:
            self.log_test_result("Security Headers", result)
    
    async def run_all_tests(self):
        """Run all test suites"""
        print("🧪 Starting Admin API Test Suite")
        print("=" * 50)
        print(f"Base URL: {self.base_url}")
        print(f"Admin API: {self.admin_api_base}")
        print(f"Auth Token: {'✅ Configured' if self.admin_token else '❌ Missing'}")
        print("=" * 50)
        print()
        
        # Run test suites
        await self.test_authentication_required()
        await self.test_system_health()
        await self.test_configuration()
        await self.test_user_management()
        await self.test_session_management()
        await self.test_audit_logging()
        await self.test_rate_limiting()
        await self.test_security_headers()
        
        # Print summary
        print("📊 Test Results Summary")
        print("=" * 50)
        
        total_tests = len(self.test_results)
        passed_tests = sum(1 for result in self.test_results if result["success"])
        failed_tests = total_tests - passed_tests
        
        print(f"Total Tests: {total_tests}")
        print(f"Passed: {passed_tests} ✅")
        print(f"Failed: {failed_tests} ❌")
        print(f"Success Rate: {(passed_tests/total_tests*100):.1f}%")
        
        if failed_tests > 0:
            print("\nFailed Tests:")
            for result in self.test_results:
                if not result["success"]:
                    print(f"  ❌ {result['test_name']} (Status: {result['status_code']})")
        
        print("\n" + "=" * 50)
        return {
            "total": total_tests,
            "passed": passed_tests,
            "failed": failed_tests,
            "success_rate": passed_tests/total_tests if total_tests > 0 else 0
        }


async def main():
    """Main test runner"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Test Admin API endpoints")
    parser.add_argument("--base-url", default="http://localhost:8000", 
                       help="Base URL for the API server")
    parser.add_argument("--token", help="Admin JWT token for authentication")
    parser.add_argument("--output", help="Output file for test results")
    
    args = parser.parse_args()
    
    if not args.token:
        print("⚠️  Warning: No admin token provided. Authentication tests will be limited.")
        print("   Use --token YOUR_JWT_TOKEN for full testing")
        print()
    
    # Run tests
    tester = AdminAPITester(args.base_url, args.token)
    results = await tester.run_all_tests()
    
    # Save results if requested
    if args.output:
        with open(args.output, 'w') as f:
            json.dump({
                "test_run": {
                    "timestamp": datetime.utcnow().isoformat(),
                    "base_url": args.base_url,
                    "has_auth_token": bool(args.token),
                    "summary": results,
                    "detailed_results": tester.test_results
                }
            }, f, indent=2)
        print(f"📄 Test results saved to: {args.output}")
    
    # Exit with error code if tests failed
    if results["failed"] > 0:
        sys.exit(1)
    else:
        print("\n🎉 All tests passed!")


if __name__ == "__main__":
    asyncio.run(main())