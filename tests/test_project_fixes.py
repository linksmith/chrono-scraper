#!/usr/bin/env python3
"""
Test script to verify project deletion and creation fixes after transaction handling improvements.
Tests the fixes for InFailedSQLTransactionError issues.
"""

import asyncio
import httpx
import json
import sys
from datetime import datetime
from typing import Optional

# Configuration
BASE_URL = "http://localhost:8000"
API_V1 = "/api/v1"

class ProjectTestSuite:
    def __init__(self):
        self.client = httpx.AsyncClient(timeout=30.0)
        self.auth_token: Optional[str] = None
        self.test_user_id: Optional[int] = None
        self.test_project_id: Optional[int] = None

    async def login_test_user(self) -> bool:
        """Login with test user credentials"""
        try:
            # Try to login with test user (adjust credentials as needed)
            login_data = {
                "username": "test@example.com",
                "password": "testpassword"
            }

            response = await self.client.post(
                f"{BASE_URL}{API_V1}/auth/login",
                json=login_data
            )

            if response.status_code == 200:
                data = response.json()
                self.auth_token = data.get("access_token")
                if self.auth_token:
                    # Set authorization header for future requests
                    self.client.headers.update({
                        "Authorization": f"Bearer {self.auth_token}"
                    })
                    print("✅ Successfully logged in test user")
                    return True
                else:
                    print("❌ Login response missing access token")
                    return False
            else:
                print(f"❌ Login failed with status {response.status_code}: {response.text}")
                # Try to create a test user if login fails
                return await self.create_test_user()

        except Exception as e:
            print(f"❌ Login error: {e}")
            return False

    async def create_test_user(self) -> bool:
        """Create a test user for testing"""
        try:
            # Try to create a test user
            user_data = {
                "email": "test@example.com",
                "password": "testpassword",
                "full_name": "Test User"
            }

            response = await self.client.post(
                f"{BASE_URL}{API_V1}/auth/register",
                json=user_data
            )

            if response.status_code in [200, 201]:
                print("✅ Test user created successfully")
                # Try to login again
                return await self.login_test_user()
            else:
                print(f"❌ User creation failed: {response.status_code} - {response.text}")
                return False

        except Exception as e:
            print(f"❌ User creation error: {e}")
            return False

    async def test_project_creation(self) -> bool:
        """Test project creation functionality"""
        try:
            project_data = {
                "name": f"Test Project {datetime.now().strftime('%Y%m%d_%H%M%S')}",
                "description": "Test project for verifying deletion fixes",
                "process_documents": True,
                "crawl_domains": ["example.com"],
                "match_type": "domain"
            }

            print(f"🧪 Testing project creation with data: {project_data}")

            response = await self.client.post(
                f"{BASE_URL}{API_V1}/projects",
                json=project_data
            )

            if response.status_code in [200, 201]:
                data = response.json()
                self.test_project_id = data.get("id")
                if self.test_project_id:
                    print(f"✅ Project created successfully with ID: {self.test_project_id}")
                    return True
                else:
                    print("❌ Project creation response missing project ID")
                    return False
            else:
                print(f"❌ Project creation failed with status {response.status_code}: {response.text}")
                return False

        except Exception as e:
            print(f"❌ Project creation error: {e}")
            return False

    async def test_project_deletion(self) -> bool:
        """Test project deletion functionality with the fixed transaction handling"""
        if not self.test_project_id:
            print("❌ No test project available for deletion")
            return False

        try:
            print(f"🧪 Testing project deletion for project ID: {self.test_project_id}")

            # Monitor the deletion process by checking logs
            print("📝 Monitoring deletion process...")

            response = await self.client.delete(
                f"{BASE_URL}{API_V1}/projects/{self.test_project_id}"
            )

            if response.status_code == 200:
                print("✅ Project deletion request successful")
                data = response.json()
                if data.get("success"):
                    print("✅ Project deletion completed successfully")
                    return True
                else:
                    print(f"❌ Project deletion returned success=False: {data}")
                    return False
            else:
                print(f"❌ Project deletion failed with status {response.status_code}: {response.text}")
                return False

        except Exception as e:
            print(f"❌ Project deletion error: {e}")
            return False

    async def test_multiple_operations(self) -> bool:
        """Test multiple project operations to ensure stability"""
        print("🧪 Testing multiple project operations for stability...")

        results = []

        # Create multiple projects
        for i in range(3):
            project_data = {
                "name": f"Multi Test Project {i} {datetime.now().strftime('%Y%m%d_%H%M%S')}",
                "description": f"Test project {i} for stability testing",
                "process_documents": True,
                "crawl_domains": [f"example{i}.com"],
                "match_type": "domain"
            }

            response = await self.client.post(
                f"{BASE_URL}{API_V1}/projects",
                json=project_data
            )

            if response.status_code in [200, 201]:
                data = response.json()
                project_id = data.get("id")
                results.append({"operation": "create", "project_id": project_id, "success": True})
                print(f"✅ Created project {i} with ID: {project_id}")

                # Immediately try to delete it
                delete_response = await self.client.delete(
                    f"{BASE_URL}{API_V1}/projects/{project_id}"
                )

                if delete_response.status_code == 200:
                    results.append({"operation": "delete", "project_id": project_id, "success": True})
                    print(f"✅ Deleted project {i} with ID: {project_id}")
                else:
                    results.append({"operation": "delete", "project_id": project_id, "success": False})
                    print(f"❌ Failed to delete project {i} with ID: {project_id}")
            else:
                results.append({"operation": "create", "project_id": None, "success": False})
                print(f"❌ Failed to create project {i}")

        # Check if all operations were successful
        success_count = sum(1 for r in results if r["success"])
        total_count = len(results)

        print(f"📊 Multi-operation test results: {success_count}/{total_count} successful")

        return success_count == total_count

    async def check_health(self) -> bool:
        """Check if the application is healthy"""
        try:
            response = await self.client.get(f"{BASE_URL}/health")
            if response.status_code == 200:
                print("✅ Application health check passed")
                return True
            else:
                print(f"❌ Application health check failed: {response.status_code}")
                return False
        except Exception as e:
            print(f"❌ Health check error: {e}")
            return False

    async def run_all_tests(self) -> bool:
        """Run all tests in sequence"""
        print("🚀 Starting Project Transaction Handling Test Suite")
        print("=" * 60)

        tests = [
            ("Health Check", self.check_health),
            ("User Authentication", self.login_test_user),
            ("Project Creation", self.test_project_creation),
            ("Project Deletion", self.test_project_deletion),
            ("Multiple Operations", self.test_multiple_operations),
        ]

        results = []

        for test_name, test_func in tests:
            print(f"\n📋 Running: {test_name}")
            print("-" * 40)

            try:
                result = await test_func()
                results.append({"test": test_name, "passed": result})
                status = "✅ PASSED" if result else "❌ FAILED"
                print(f"{status}: {test_name}")
            except Exception as e:
                print(f"❌ ERROR in {test_name}: {e}")
                results.append({"test": test_name, "passed": False})

        print("\n" + "=" * 60)
        print("📊 TEST RESULTS SUMMARY")
        print("=" * 60)

        passed_count = sum(1 for r in results if r["passed"])
        total_count = len(results)

        for result in results:
            status = "✅ PASSED" if result["passed"] else "❌ FAILED"
            print(f"{status}: {result['test']}")

        print(f"\n🎯 Overall: {passed_count}/{total_count} tests passed")

        if passed_count == total_count:
            print("🎉 All tests passed! Transaction handling fixes are working correctly.")
        else:
            print("⚠️  Some tests failed. Check the output above for details.")

        return passed_count == total_count

async def main():
    """Main function to run the test suite"""
    test_suite = ProjectTestSuite()

    try:
        success = await test_suite.run_all_tests()
        await test_suite.client.aclose()

        if success:
            print("\n🎉 All tests completed successfully!")
            sys.exit(0)
        else:
            print("\n❌ Some tests failed. Please check the application logs for more details.")
            sys.exit(1)

    except Exception as e:
        print(f"\n💥 Test suite error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
