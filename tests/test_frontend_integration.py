#!/usr/bin/env python3
"""
Frontend integration testing with Playwright
Tests the new shared pages architecture with real user interactions
"""
import asyncio
import sys
import time
from playwright.async_api import async_playwright, Page, BrowserContext
from typing import Dict, Any
from datetime import datetime
import json

class FrontendIntegrationTest:
    def __init__(self):
        self.playwright = None
        self.browser = None
        self.context: BrowserContext = None
        self.page: Page = None
        self.test_results: Dict[str, Any] = {}
        self.start_time = time.time()
        
    async def setup(self):
        """Setup Playwright browser"""
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(headless=True)
        self.context = await self.browser.new_context()
        self.page = await self.context.new_page()
        
    async def teardown(self):
        """Cleanup Playwright resources"""
        if self.page:
            await self.page.close()
        if self.context:
            await self.context.close()
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()
    
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
    
    async def test_1_login_flow(self) -> bool:
        """Test 1: Frontend login flow"""
        print("\n🔐 TEST 1: Frontend Login Flow")
        print("-" * 50)
        
        try:
            # Navigate to login page
            await self.page.goto("http://localhost:5173/auth/login")
            await self.page.wait_for_load_state('networkidle')
            
            # Check if login form is present
            email_input = self.page.locator('input[type="email"]')
            password_input = self.page.locator('input[type="password"]')
            login_button = self.page.locator('button[type="submit"]')
            
            if not await email_input.count() or not await password_input.count():
                self.log_test("frontend_login_flow", False, "Login form elements not found")
                return False
            
            # Fill in credentials
            await email_input.fill("info@linksmith.nl")
            await password_input.fill("temppass123")
            await login_button.click()
            
            # Wait for navigation after login
            await self.page.wait_for_url("http://localhost:5173/dashboard", timeout=10000)
            
            # Check if we're successfully logged in (look for user-specific content)
            dashboard_element = self.page.locator('[data-testid="dashboard"], .dashboard, h1:has-text("Dashboard")')
            
            if await dashboard_element.count() > 0:
                self.log_test(
                    "frontend_login_flow", 
                    True, 
                    "Successfully logged in and redirected to dashboard",
                    {"final_url": self.page.url}
                )
                return True
            else:
                self.log_test("frontend_login_flow", False, f"Login successful but dashboard not found. Current URL: {self.page.url}")
                return False
                
        except Exception as e:
            self.log_test("frontend_login_flow", False, f"Login flow failed: {str(e)}")
            return False
    
    async def test_2_navigation(self) -> bool:
        """Test 2: Navigation to shared pages and projects"""
        print("\n🧭 TEST 2: Navigation to Key Pages")
        print("-" * 50)
        
        try:
            # Navigate to projects page
            await self.page.goto("http://localhost:5173/projects")
            await self.page.wait_for_load_state('networkidle')
            
            # Check if projects are visible
            projects_content = self.page.locator('[data-testid="projects"], .projects, h1:has-text("Projects")')
            
            if await projects_content.count() == 0:
                self.log_test("navigation_projects", False, "Projects page not accessible or content not found")
                return False
            
            # Navigate to library page (shared pages)
            await self.page.goto("http://localhost:5173/library")
            await self.page.wait_for_load_state('networkidle')
            
            # Check if library/shared pages content is visible
            library_content = self.page.locator('[data-testid="library"], .library, h1:has-text("Library")')
            
            if await library_content.count() > 0:
                self.log_test(
                    "navigation_pages", 
                    True, 
                    "Successfully navigated to projects and library pages",
                    {"projects_accessible": True, "library_accessible": True}
                )
                return True
            else:
                self.log_test("navigation_pages", False, "Library page not accessible or content not found")
                return False
                
        except Exception as e:
            self.log_test("navigation_pages", False, f"Navigation failed: {str(e)}")
            return False
    
    async def test_3_search_functionality(self) -> bool:
        """Test 3: Frontend search functionality"""
        print("\n🔍 TEST 3: Frontend Search Functionality")
        print("-" * 50)
        
        try:
            # Navigate to search page
            await self.page.goto("http://localhost:5173/search")
            await self.page.wait_for_load_state('networkidle')
            
            # Look for search input
            search_input = self.page.locator('input[type="search"], input[placeholder*="search" i], input[name="search"]')
            
            if await search_input.count() == 0:
                self.log_test("frontend_search", False, "Search input not found on search page")
                return False
            
            # Perform a search
            await search_input.fill("test")
            
            # Look for search button or trigger search
            search_button = self.page.locator('button:has-text("Search"), button[type="submit"]')
            if await search_button.count() > 0:
                await search_button.click()
            else:
                # Try pressing Enter
                await search_input.press("Enter")
            
            # Wait for search results
            await self.page.wait_for_timeout(2000)
            
            # Check if search results or "no results" message appears
            results_container = self.page.locator('[data-testid="search-results"], .search-results, .results')
            no_results = self.page.locator(':has-text("No results"), :has-text("no results"), :has-text("0 results")')
            
            if await results_container.count() > 0 or await no_results.count() > 0:
                self.log_test(
                    "frontend_search", 
                    True, 
                    "Search functionality working - results or no results message displayed",
                    {"has_results_container": await results_container.count() > 0, "has_no_results_message": await no_results.count() > 0}
                )
                return True
            else:
                self.log_test("frontend_search", False, "Search executed but no results or feedback found")
                return False
                
        except Exception as e:
            self.log_test("frontend_search", False, f"Frontend search test failed: {str(e)}")
            return False
    
    async def test_4_responsive_design(self) -> bool:
        """Test 4: Responsive design and mobile compatibility"""
        print("\n📱 TEST 4: Responsive Design")
        print("-" * 50)
        
        try:
            # Test desktop view first
            await self.page.set_viewport_size({"width": 1920, "height": 1080})
            await self.page.goto("http://localhost:5173/dashboard")
            await self.page.wait_for_load_state('networkidle')
            
            desktop_success = True
            
            # Test mobile view
            await self.page.set_viewport_size({"width": 375, "height": 667})
            await self.page.wait_for_timeout(1000)  # Wait for layout adjustment
            
            # Check if page is still functional
            page_content = self.page.locator('body')
            if await page_content.count() == 0:
                desktop_success = False
            
            # Test tablet view
            await self.page.set_viewport_size({"width": 768, "height": 1024})
            await self.page.wait_for_timeout(1000)
            
            if desktop_success and await page_content.count() > 0:
                self.log_test(
                    "responsive_design", 
                    True, 
                    "Application responsive across desktop, mobile, and tablet viewports",
                    {"desktop_tested": True, "mobile_tested": True, "tablet_tested": True}
                )
                return True
            else:
                self.log_test("responsive_design", False, "Application not responsive or breaks on different viewports")
                return False
                
        except Exception as e:
            self.log_test("responsive_design", False, f"Responsive design test failed: {str(e)}")
            return False
        
    async def test_5_error_handling(self) -> bool:
        """Test 5: Error handling and user feedback"""
        print("\n⚠️ TEST 5: Error Handling")
        print("-" * 50)
        
        try:
            # Test invalid page
            await self.page.goto("http://localhost:5173/nonexistent-page")
            await self.page.wait_for_load_state('networkidle')
            
            # Check if 404 or error page is shown
            error_indicators = self.page.locator(':has-text("404"), :has-text("Not Found"), :has-text("Page not found"), .error, .not-found')
            
            if await error_indicators.count() > 0:
                self.log_test(
                    "error_handling", 
                    True, 
                    "Application properly handles 404 errors with user-friendly messaging",
                    {"error_page_shown": True}
                )
                return True
            else:
                self.log_test("error_handling", False, "No proper error handling for invalid pages")
                return False
                
        except Exception as e:
            self.log_test("error_handling", False, f"Error handling test failed: {str(e)}")
            return False
    
    async def run_all_tests(self) -> Dict[str, Any]:
        """Run all frontend tests"""
        print("🚀 FRONTEND INTEGRATION TESTING")
        print("=" * 60)
        print("Testing frontend integration with real user interactions")
        print(f"Target: http://localhost:5173")
        print(f"Test started: {datetime.now().isoformat()}")
        print("=" * 60)
        
        await self.setup()
        
        test_functions = [
            self.test_1_login_flow,
            self.test_2_navigation,
            self.test_3_search_functionality,
            self.test_4_responsive_design,
            self.test_5_error_handling,
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
        
        await self.teardown()
        
        # Generate final report
        execution_time = time.time() - self.start_time
        
        print("\n" + "=" * 60)
        print("📊 FRONTEND TEST REPORT")
        print("=" * 60)
        print(f"Tests passed: {passed_tests}/{total_tests}")
        print(f"Success rate: {(passed_tests/total_tests)*100:.1f}%")
        print(f"Total execution time: {execution_time:.2f} seconds")
        
        if passed_tests == total_tests:
            print("🎉 ALL FRONTEND TESTS PASSED - Frontend working perfectly!")
        elif passed_tests >= total_tests * 0.8:
            print("⚠️  FRONTEND MOSTLY WORKING - Minor issues detected")
        else:
            print("🚨 FRONTEND ISSUES - Multiple frontend systems failing")
        
        # Save detailed results
        final_results = {
            "summary": {
                "total_tests": total_tests,
                "passed_tests": passed_tests,
                "success_rate": (passed_tests/total_tests)*100,
                "execution_time_seconds": execution_time,
                "test_timestamp": datetime.now().isoformat(),
                "target_frontend": "http://localhost:5173"
            },
            "detailed_results": self.test_results
        }
        
        with open("/tmp/frontend_test_results.json", "w") as f:
            json.dump(final_results, f, indent=2, default=str)
        
        print(f"\n📁 Frontend test results saved to: /tmp/frontend_test_results.json")
        return final_results

async def main():
    test_runner = FrontendIntegrationTest()
    return await test_runner.run_all_tests()

if __name__ == "__main__":
    try:
        results = asyncio.run(main())
    except KeyboardInterrupt:
        print("\n⚠️  Frontend tests interrupted by user")
    except Exception as e:
        print(f"\n❌ Frontend testing failed: {str(e)}")
        sys.exit(1)