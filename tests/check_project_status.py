#!/usr/bin/env python3
"""
Simple script to check project 110 status via API
"""

import requests
import json

BASE_URL = "http://localhost:8000"

def check_project_status():
    """Check project 110 status via API"""
    print("🔍 Checking Project 110 Status")
    print("=" * 40)

    try:
        # Check health
        response = requests.get(f"{BASE_URL}/health", timeout=5)
        if response.status_code == 200:
            print("✅ API Health: OK")
        else:
            print(f"❌ API Health: {response.status_code}")
            return

        # Try to get project info (will fail without auth, but shows if endpoint exists)
        response = requests.get(f"{BASE_URL}/api/v1/projects/110", timeout=5)
        print(f"📊 Project 110 API Response: {response.status_code}")
        if response.status_code == 401:
            print("   Expected 401 (Unauthorized) - project exists but needs auth")
        elif response.status_code == 404:
            print("   ❌ Project 110 not found!")
        else:
            print(f"   Response: {response.text[:200]}...")

        # Check if there are any running scraping tasks by looking at Celery
        print("\n🔄 Checking Celery Task Status...")

        # This would require Celery connection, so let's check logs instead
        print("   📝 Checking recent logs for scraping activity...")

        # Use docker to check recent logs
        import subprocess
        try:
            result = subprocess.run([
                'docker', 'compose', '-f', 'docker-compose.optimized.yml',
                'logs', '--tail', '20', 'celery_worker'
            ], capture_output=True, text=True, timeout=10)

            if 'scrape_domain_with_firecrawl' in result.stdout:
                print("   ✅ Found scraping tasks in logs")
            else:
                print("   ⚠️  No scraping tasks found in recent logs")

            if 'firecrawl' in result.stdout.lower():
                print("   ✅ Firecrawl service is being used")
            else:
                print("   ⚠️  No Firecrawl activity in logs")

        except Exception as e:
            print(f"   ❌ Could not check logs: {e}")

    except Exception as e:
        print(f"❌ Error checking status: {e}")

def main():
    check_project_status()

    print("\n💡 Troubleshooting Steps:")
    print("1. Check if domains were added to project 110")
    print("2. Verify Celery workers are running scraping tasks")
    print("3. Check Firecrawl service logs for errors")
    print("4. Ensure project has 'process_documents: true' set")

if __name__ == "__main__":
    main()
